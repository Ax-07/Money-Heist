from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.market.exchange import DerivativesPositioningSnapshot
from app.market.features.models import FeatureQuality, FeatureSnapshot, MarketRegime
from app.market.scanner.models import CandidateOpportunity, ScannerTrigger
from app.services.orchestration import KrakenFuturesRioContextProvider

NOW = datetime(2026, 9, 9, 0, 0, tzinfo=UTC)


class StubAnalytics:
    def __init__(self, snapshot: DerivativesPositioningSnapshot) -> None:
        self.snapshot = snapshot
        self.calls: list[str] = []

    async def get_positioning_snapshot(self, symbol: str) -> DerivativesPositioningSnapshot:
        self.calls.append(symbol)
        return self.snapshot


def run(coro):
    return asyncio.run(coro)


def snapshot(
    *,
    observed_at: datetime = NOW - timedelta(minutes=5),
    funding_rate: Decimal | None = Decimal("0.0002"),
    open_interest: Decimal | None = Decimal("1000000"),
    open_interest_change_pct: Decimal | None = Decimal("2.5"),
    long_short_ratio: Decimal | None = Decimal("1.2"),
) -> DerivativesPositioningSnapshot:
    missing = []
    values = {
        "funding_rate": funding_rate,
        "open_interest": open_interest,
        "open_interest_change_pct": open_interest_change_pct,
        "long_short_ratio": long_short_ratio,
        "long_liquidations_notional": None,
        "short_liquidations_notional": None,
    }
    missing.extend(key for key, value in values.items() if value is None)
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
        missing_fields=tuple(sorted(missing)),
    )


def market_context(*, observed_at: datetime = NOW) -> FeatureSnapshot:
    return FeatureSnapshot(
        feature_version="features-v1",
        snapshot_id="snapshot-rio-1",
        source_snapshot_id="source-rio-1",
        symbol="BTC/EUR",
        timeframe="5m",
        observed_at=observed_at,
        candle_count=100,
        close=100.0,
        regime=MarketRegime.BULLISH_TREND,
        quality=FeatureQuality(
            warmup_complete=True,
            closed_candle_count=100,
        ),
    )


def opportunity() -> CandidateOpportunity:
    return CandidateOpportunity(
        scanner_version="scanner-v1",
        opportunity_id="10000000-0000-0000-0000-000000000017",
        snapshot_id="snapshot-rio-1",
        system_id="balanced_v1",
        symbol="BTC/EUR",
        timeframe="5m",
        priority_score=80,
        triggers=(ScannerTrigger.TREND_STRENGTH,),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )


def test_refresh_caches_real_snapshot_and_exposes_reliable_rio_context() -> None:
    raw = snapshot()
    analytics = StubAnalytics(raw)
    provider = KrakenFuturesRioContextProvider(analytics)

    refreshed = run(provider.refresh("BTC/EUR"))
    contexts = provider.contexts_for(
        opportunity=opportunity(),
        market_context=market_context(),
    )

    assert refreshed is raw
    assert analytics.calls == ["BTC/EUR"]
    assert set(contexts) == {"rio"}
    rio = contexts["rio"]
    assert rio.source == "kraken_futures_analytics"
    assert rio.instrument == "PF_XBTUSD"
    assert rio.observed_at == NOW - timedelta(minutes=5)
    assert rio.data_quality == "RELIABLE"
    assert rio.funding_rate == 0.0002
    assert rio.open_interest == 1_000_000.0
    assert rio.open_interest_change_pct == 2.5
    assert rio.long_short_ratio == 1.2
    assert rio.long_liquidations_notional is None
    assert rio.short_liquidations_notional is None


def test_partial_real_metrics_are_degraded_not_fabricated() -> None:
    raw = snapshot(funding_rate=None)
    provider = KrakenFuturesRioContextProvider(StubAnalytics(raw))
    provider.update(raw)

    rio = provider.contexts_for(
        opportunity=opportunity(),
        market_context=market_context(),
    )["rio"]

    assert rio.data_quality == "DEGRADED"
    assert rio.funding_rate is None
    assert rio.open_interest == 1_000_000.0
    assert "funding_rate" in rio.missing_fields


def test_context_later_than_market_decision_is_not_exposed() -> None:
    raw = snapshot(observed_at=NOW + timedelta(minutes=1))
    provider = KrakenFuturesRioContextProvider(StubAnalytics(raw))
    provider.update(raw)

    contexts = provider.contexts_for(
        opportunity=opportunity(),
        market_context=market_context(observed_at=NOW),
    )

    assert contexts == {}


def test_context_older_than_max_age_is_not_exposed() -> None:
    raw = snapshot(observed_at=NOW - timedelta(minutes=30))
    provider = KrakenFuturesRioContextProvider(
        StubAnalytics(raw),
        max_context_age=timedelta(minutes=20),
    )
    provider.update(raw)

    contexts = provider.contexts_for(
        opportunity=opportunity(),
        market_context=market_context(observed_at=NOW),
    )

    assert contexts == {}


def test_older_refresh_cannot_roll_cache_backwards() -> None:
    current = snapshot(observed_at=NOW - timedelta(minutes=5))
    older = snapshot(observed_at=NOW - timedelta(minutes=10), open_interest=Decimal("1"))
    provider = KrakenFuturesRioContextProvider(StubAnalytics(current))
    provider.update(current)
    provider.update(older)

    rio = provider.contexts_for(
        opportunity=opportunity(),
        market_context=market_context(),
    )["rio"]

    assert rio.open_interest == 1_000_000.0
    assert rio.observed_at == NOW - timedelta(minutes=5)


def test_mismatched_opportunity_and_market_context_fail_closed_at_provider_boundary() -> None:
    raw = snapshot()
    provider = KrakenFuturesRioContextProvider(StubAnalytics(raw))
    provider.update(raw)
    other = market_context().model_copy(update={"symbol": "ETH/EUR"})

    contexts = provider.contexts_for(
        opportunity=opportunity(),
        market_context=other,
    )

    assert contexts == {}
