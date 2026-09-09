from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.market.exchange import (
    DerivativesPositioningSnapshot,
    ExchangeNetworkError,
    MarketSidecarRefreshStatus,
)
from app.services.orchestration import (
    KrakenFuturesRioContextProvider,
    RioContextDiagnosticStatus,
)

NOW = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class Analytics:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls: list[str] = []

    async def get_positioning_snapshot(self, symbol: str):
        self.calls.append(symbol)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def positioning(
    *,
    observed_at: datetime = NOW - timedelta(minutes=5),
    funding_rate: Decimal | None = Decimal("0.0002"),
    open_interest: Decimal | None = Decimal("1000000"),
    open_interest_change_pct: Decimal | None = Decimal("2.5"),
    long_short_ratio: Decimal | None = Decimal("1.2"),
) -> DerivativesPositioningSnapshot:
    return DerivativesPositioningSnapshot(
        source="kraken_futures_analytics",
        symbol="BTC/EUR",
        instrument="PF_XBTUSD",
        observed_at=observed_at,
        received_at=max(observed_at, NOW - timedelta(minutes=4)),
        funding_rate=funding_rate,
        open_interest=open_interest,
        open_interest_change_pct=open_interest_change_pct,
        long_short_ratio=long_short_ratio,
        missing_fields=(
            "long_liquidations_notional",
            "short_liquidations_notional",
        ),
    )


def test_diagnostic_reports_refreshed_reliable_context_without_new_io() -> None:
    analytics = Analytics(positioning())
    provider = KrakenFuturesRioContextProvider(
        analytics,
        min_refresh_interval=timedelta(0),
        now=lambda: NOW,
    )

    run(provider.refresh_for_market(symbol="BTC/EUR", observed_at=NOW))
    diagnostic = provider.diagnostic_for(symbol="BTC/EUR", decision_time=NOW)

    assert diagnostic.status is RioContextDiagnosticStatus.REFRESHED
    assert diagnostic.data_quality == "RELIABLE"
    assert diagnostic.instrument == "PF_XBTUSD"
    assert diagnostic.age_seconds == 300.0
    assert "long_liquidations_notional" in diagnostic.missing_fields
    assert analytics.calls == ["BTC/EUR"]


def test_diagnostic_distinguishes_cache_hit_after_cooldown_reuse() -> None:
    analytics = Analytics(positioning())
    provider = KrakenFuturesRioContextProvider(
        analytics,
        min_refresh_interval=timedelta(minutes=2),
        now=lambda: NOW,
    )

    run(provider.refresh_for_market(symbol="BTC/EUR", observed_at=NOW))
    run(provider.refresh_for_market(symbol="BTC/EUR", observed_at=NOW))
    diagnostic = provider.diagnostic_for(symbol="BTC/EUR", decision_time=NOW)

    assert diagnostic.status is RioContextDiagnosticStatus.CACHE_HIT
    assert diagnostic.last_refresh_status is MarketSidecarRefreshStatus.CACHED
    assert analytics.calls == ["BTC/EUR"]


def test_diagnostic_marks_partial_real_metrics_as_degraded() -> None:
    analytics = Analytics(
        positioning(
            funding_rate=None,
            long_short_ratio=None,
        )
    )
    provider = KrakenFuturesRioContextProvider(
        analytics,
        min_refresh_interval=timedelta(0),
        now=lambda: NOW,
    )

    run(provider.refresh_for_market(symbol="BTC/EUR", observed_at=NOW))
    diagnostic = provider.diagnostic_for(symbol="BTC/EUR", decision_time=NOW)

    assert diagnostic.status is RioContextDiagnosticStatus.DEGRADED
    assert diagnostic.data_quality == "DEGRADED"


def test_diagnostic_reports_stale_cache_without_exposing_it_to_rio() -> None:
    analytics = Analytics(ExchangeNetworkError("offline"))
    provider = KrakenFuturesRioContextProvider(
        analytics,
        max_context_age=timedelta(minutes=20),
        now=lambda: NOW,
    )
    provider.update(positioning(observed_at=NOW - timedelta(minutes=30)))

    diagnostic = provider.diagnostic_for(symbol="BTC/EUR", decision_time=NOW)

    assert diagnostic.status is RioContextDiagnosticStatus.STALE
    assert diagnostic.age_seconds == 1800.0


def test_diagnostic_reports_unavailable_before_any_snapshot() -> None:
    analytics = Analytics(ExchangeNetworkError("offline"))
    provider = KrakenFuturesRioContextProvider(analytics, now=lambda: NOW)

    diagnostic = provider.diagnostic_for(symbol="BTC/EUR", decision_time=NOW)

    assert diagnostic.status is RioContextDiagnosticStatus.UNAVAILABLE
    assert diagnostic.observed_at is None
    assert analytics.calls == []
