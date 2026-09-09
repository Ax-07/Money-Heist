from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.market.exchange import (
    MarketSidecarRefreshResult,
    MarketSidecarRefreshStatus,
    PaperShadowMarketFeed,
)
from app.market.models import Candle, MarketSnapshot, SnapshotQuality

NOW = datetime(2026, 9, 9, 1, 30, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


def candle() -> Candle:
    return Candle(
        symbol="BTC/EUR",
        timeframe="1m",
        open_time=NOW - timedelta(minutes=1),
        close_time=NOW,
        open="100",
        high="102",
        low="99",
        close="101",
        volume="5",
        is_closed=True,
    )


def snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        symbol="BTC/EUR",
        source="kraken_spot",
        observed_at=NOW - timedelta(seconds=5),
        received_at=NOW,
        last_price="101",
        candles={"1m": (candle(),)},
        quality=SnapshotQuality(),
    )


class SpotProvider:
    async def get_snapshot(self, symbol: str) -> MarketSnapshot:
        assert symbol == "BTC/EUR"
        return snapshot()

    async def get_candles(self, symbol: str, timeframe: str, limit: int):
        return (candle(),)


class Features:
    def compute(self, candles, **kwargs):
        return SimpleNamespace(
            snapshot_id="feature-1",
            symbol=kwargs["symbol"],
            timeframe=kwargs["timeframe"],
            observed_at=kwargs["observed_at"],
        )


class Scanner:
    def __init__(self, *, with_opportunity: bool = True) -> None:
        self.with_opportunity = with_opportunity

    def scan(self, current, **kwargs):
        opportunity = SimpleNamespace(opportunity_id="opp-1") if self.with_opportunity else None
        return SimpleNamespace(opportunity=opportunity)


class Refresher:
    refresher_id = "test.sidecar"

    def __init__(self) -> None:
        self.calls = []

    async def refresh_for_market(self, *, symbol: str, observed_at: datetime):
        self.calls.append((symbol, observed_at))
        return MarketSidecarRefreshResult(
            refresher_id=self.refresher_id,
            status=MarketSidecarRefreshStatus.REFRESHED,
            symbol=symbol,
            observed_at=observed_at - timedelta(minutes=1),
        )


class ExplodingRefresher:
    refresher_id = "test.exploding"

    async def refresh_for_market(self, *, symbol: str, observed_at: datetime):
        raise RuntimeError("sidecar boom")


def test_sidecar_refresh_runs_only_after_scanner_produces_opportunity() -> None:
    refresher = Refresher()
    feed = PaperShadowMarketFeed(
        SpotProvider(),
        feature_engine=Features(),
        scanner=Scanner(with_opportunity=True),
        root_system_id="shadow_root",
        sidecar_refreshers=(refresher,),
    )

    result = run(feed.build(symbol="BTC/EUR", timeframe="1m"))

    assert len(refresher.calls) == 1
    assert refresher.calls[0][0] == "BTC/EUR"
    assert len(result.sidecar_refreshes) == 1
    assert result.sidecar_refreshes[0].status is MarketSidecarRefreshStatus.REFRESHED


def test_no_opportunity_skips_all_derivatives_sidecar_network_work() -> None:
    refresher = Refresher()
    feed = PaperShadowMarketFeed(
        SpotProvider(),
        feature_engine=Features(),
        scanner=Scanner(with_opportunity=False),
        root_system_id="shadow_root",
        sidecar_refreshers=(refresher,),
    )

    result = run(feed.build(symbol="BTC/EUR", timeframe="1m"))

    assert refresher.calls == []
    assert result.sidecar_refreshes == ()


def test_sidecar_failure_does_not_block_valid_spot_paper_shadow_input() -> None:
    feed = PaperShadowMarketFeed(
        SpotProvider(),
        feature_engine=Features(),
        scanner=Scanner(),
        root_system_id="shadow_root",
        sidecar_refreshers=(ExplodingRefresher(),),
    )

    result = run(feed.build(symbol="BTC/EUR", timeframe="1m"))

    assert result.opportunity is not None
    assert result.market_snapshot.quality.is_valid is True
    assert result.sidecar_refreshes[0].status is MarketSidecarRefreshStatus.FAILED
    assert "RuntimeError" in (result.sidecar_refreshes[0].message or "")


def test_feed_rejects_duplicate_sidecar_ids_to_keep_diagnostics_unambiguous() -> None:
    with pytest.raises(ValueError, match="unique"):
        PaperShadowMarketFeed(
            SpotProvider(),
            feature_engine=Features(),
            scanner=Scanner(),
            root_system_id="shadow_root",
            sidecar_refreshers=(Refresher(), Refresher()),
        )
