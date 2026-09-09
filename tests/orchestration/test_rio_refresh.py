from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.market.exchange import (
    DerivativesPositioningSnapshot,
    ExchangeNetworkError,
    MarketSidecarRefreshStatus,
)
from app.services.orchestration import KrakenFuturesRioContextProvider

NOW = datetime(2026, 9, 9, 1, 30, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class StubAnalytics:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls: list[str] = []

    async def get_positioning_snapshot(self, symbol: str):
        self.calls.append(symbol)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def snapshot(*, observed_at: datetime = NOW - timedelta(minutes=5)):
    return DerivativesPositioningSnapshot(
        source="kraken_futures_analytics",
        symbol="BTC/EUR",
        instrument="PF_XBTUSD",
        observed_at=observed_at,
        received_at=max(observed_at, NOW - timedelta(minutes=4)),
        funding_rate=Decimal("0.0002"),
        open_interest=Decimal("1000000"),
        open_interest_change_pct=Decimal("2.5"),
        long_short_ratio=Decimal("1.2"),
        missing_fields=(
            "long_liquidations_notional",
            "short_liquidations_notional",
        ),
    )


def test_expected_exchange_failure_is_non_critical_and_exposes_unavailable() -> None:
    analytics = StubAnalytics(ExchangeNetworkError("offline"))
    provider = KrakenFuturesRioContextProvider(
        analytics,
        min_refresh_interval=timedelta(0),
        now=lambda: NOW,
    )

    outcome = run(
        provider.refresh_for_market(
            symbol="BTC/EUR",
            observed_at=NOW,
        )
    )

    assert outcome.status is MarketSidecarRefreshStatus.UNAVAILABLE
    assert "ExchangeNetworkError" in (outcome.message or "")
    assert analytics.calls == ["BTC/EUR"]


def test_failed_refresh_can_retain_prior_cache_only_while_it_is_still_fresh() -> None:
    clock = Clock(NOW)
    analytics = StubAnalytics(snapshot())
    provider = KrakenFuturesRioContextProvider(
        analytics,
        min_refresh_interval=timedelta(0),
        max_context_age=timedelta(minutes=20),
        now=clock,
    )
    first = run(provider.refresh_for_market(symbol="BTC/EUR", observed_at=NOW))
    assert first.status is MarketSidecarRefreshStatus.REFRESHED

    analytics.outcome = ExchangeNetworkError("temporary outage")
    clock.value = NOW + timedelta(minutes=3)
    second = run(
        provider.refresh_for_market(
            symbol="BTC/EUR",
            observed_at=clock.value,
        )
    )

    assert second.status is MarketSidecarRefreshStatus.CACHED
    assert "retained fresh cache" in (second.message or "")
    assert analytics.calls == ["BTC/EUR", "BTC/EUR"]

    clock.value = NOW + timedelta(minutes=30)
    third = run(
        provider.refresh_for_market(
            symbol="BTC/EUR",
            observed_at=clock.value,
        )
    )
    assert third.status is MarketSidecarRefreshStatus.UNAVAILABLE


def test_refresh_interval_reuses_cache_without_repeating_public_http_work() -> None:
    analytics = StubAnalytics(snapshot())
    provider = KrakenFuturesRioContextProvider(
        analytics,
        min_refresh_interval=timedelta(minutes=2),
        now=lambda: NOW,
    )

    first = run(provider.refresh_for_market(symbol="BTC/EUR", observed_at=NOW))
    second = run(provider.refresh_for_market(symbol="BTC/EUR", observed_at=NOW))

    assert first.status is MarketSidecarRefreshStatus.REFRESHED
    assert second.status is MarketSidecarRefreshStatus.CACHED
    assert analytics.calls == ["BTC/EUR"]
