from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.market.exchange import PaperShadowMarketFeed, UnsafeMarketDataError
from app.market.models import Candle, MarketSnapshot, SnapshotQuality

from ._helpers import BASE_NOW


def run(coro):
    return asyncio.run(coro)


def candle(timeframe: str = "1m") -> Candle:
    return Candle(
        symbol="BTC/EUR",
        timeframe=timeframe,
        open_time=BASE_NOW - timedelta(minutes=1),
        close_time=BASE_NOW,
        open="100",
        high="102",
        low="99",
        close="101",
        volume="5",
        is_closed=True,
    )


def snapshot(*, quality: SnapshotQuality | None = None, candles=None) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="BTC/EUR",
        source="kraken_spot",
        observed_at=BASE_NOW - timedelta(seconds=5),
        received_at=BASE_NOW,
        last_price="101",
        candles=candles if candles is not None else {"1m": (candle(),)},
        quality=quality or SnapshotQuality(),
    )


class Provider:
    def __init__(self, value: MarketSnapshot) -> None:
        self.value = value
        self.calls = []

    async def get_snapshot(self, symbol: str):
        self.calls.append(symbol)
        return self.value

    async def get_candles(self, symbol: str, timeframe: str, limit: int):
        return self.value.candles[timeframe][-limit:]


class FeatureEngine:
    def __init__(self) -> None:
        self.calls = []
        self.result = SimpleNamespace(snapshot_id="feature-1", symbol="BTC/EUR", timeframe="1m")

    def compute(self, candles, **kwargs):
        self.calls.append((candles, kwargs))
        return self.result


class Scanner:
    def __init__(self) -> None:
        self.calls = []
        self.result = SimpleNamespace(opportunity=SimpleNamespace(opportunity_id="opp-1"))

    def scan(self, current, **kwargs):
        self.calls.append((current, kwargs))
        return self.result


def test_feed_passes_normalized_snapshot_into_existing_feature_engine_and_scanner():
    raw = snapshot()
    provider = Provider(raw)
    features = FeatureEngine()
    scanner = Scanner()
    feed = PaperShadowMarketFeed(
        provider, feature_engine=features, scanner=scanner, root_system_id="shadow_root"
    )

    result = run(feed.build(symbol="BTC/EUR", timeframe="1m"))

    assert result.market_snapshot is raw
    assert result.market_context is features.result
    assert result.scan_result is scanner.result
    assert result.opportunity.opportunity_id == "opp-1"
    assert provider.calls == ["BTC/EUR"]
    _, feature_kwargs = features.calls[0]
    assert feature_kwargs["source_snapshot_id"] == str(raw.snapshot_id)
    _, scan_kwargs = scanner.calls[0]
    assert scan_kwargs["system_id"] == "shadow_root"


def test_feed_forwards_previous_market_context_for_regime_change_logic():
    previous = object()
    features = FeatureEngine()
    scanner = Scanner()
    feed = PaperShadowMarketFeed(
        Provider(snapshot()),
        feature_engine=features,
        scanner=scanner,
        root_system_id="shadow_root",
    )

    run(feed.build(symbol="BTC/EUR", timeframe="1m", previous_market_context=previous))

    assert scanner.calls[0][1]["previous"] is previous


def test_feed_rejects_blank_root_system_id():
    with pytest.raises(ValueError, match="root_system_id"):
        PaperShadowMarketFeed(
            Provider(snapshot()),
            feature_engine=FeatureEngine(),
            scanner=Scanner(),
            root_system_id=" ",
        )


def test_feed_fails_closed_if_snapshot_quality_is_invalid():
    invalid = SnapshotQuality(is_stale=True, is_valid=False)
    feed = PaperShadowMarketFeed(
        Provider(snapshot(quality=invalid)),
        feature_engine=FeatureEngine(),
        scanner=Scanner(),
        root_system_id="shadow_root",
    )

    with pytest.raises(UnsafeMarketDataError, match="invalid MarketSnapshot"):
        run(feed.build(symbol="BTC/EUR", timeframe="1m"))


def test_feed_fails_closed_if_requested_timeframe_is_unavailable():
    feed = PaperShadowMarketFeed(
        Provider(snapshot(candles={"5m": (candle("5m"),)})),
        feature_engine=FeatureEngine(),
        scanner=Scanner(),
        root_system_id="shadow_root",
    )

    with pytest.raises(UnsafeMarketDataError, match="no candles"):
        run(feed.build(symbol="BTC/EUR", timeframe="1m"))


def test_feed_never_calls_any_broker_or_risk_authority():
    features = FeatureEngine()
    scanner = Scanner()
    feed = PaperShadowMarketFeed(
        Provider(snapshot()),
        feature_engine=features,
        scanner=scanner,
        root_system_id="shadow_root",
    )
    assert not hasattr(feed, "broker")
    assert not hasattr(feed, "risk_engine")
    run(feed.build(symbol="BTC/EUR", timeframe="1m"))
