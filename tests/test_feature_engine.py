from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.market.features import FeatureEngine, InsufficientHistoryError, MarketRegime


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool = True


def make_candles(count: int = 60, *, trend: float = 0.5) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles: list[Candle] = []
    for index in range(count):
        close = 100.0 + trend * index
        candles.append(
            Candle(
                timestamp=start + timedelta(minutes=5 * index),
                open=close - 0.2,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=1000.0 + index,
            )
        )
    return candles


def test_compute_builds_compact_feature_snapshot() -> None:
    snapshot = FeatureEngine().compute(make_candles(), symbol="BTCUSDT", timeframe="5m")
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.timeframe == "5m"
    assert snapshot.quality.warmup_complete is True
    assert snapshot.ema_fast is not None
    assert snapshot.rsi_14 is not None
    assert snapshot.atr_14 is not None
    assert snapshot.adx_14 is not None
    assert snapshot.volume_ratio is not None


def test_compute_is_reproducible_for_same_input() -> None:
    engine = FeatureEngine()
    candles = make_candles()
    first = engine.compute(candles, symbol="ETHUSDT", timeframe="15m")
    second = engine.compute(candles, symbol="ETHUSDT", timeframe="15m")
    assert first.model_dump() == second.model_dump()


def test_source_snapshot_id_is_preserved() -> None:
    snapshot = FeatureEngine().compute(
        make_candles(),
        symbol="SOLUSDT",
        timeframe="5m",
        source_snapshot_id="market-snapshot-123",
    )
    assert snapshot.snapshot_id == "market-snapshot-123"
    assert snapshot.source_snapshot_id == "market-snapshot-123"


def test_open_candle_is_ignored() -> None:
    candles = make_candles()
    open_candle = Candle(
        timestamp=candles[-1].timestamp + timedelta(minutes=5),
        open=200.0,
        high=250.0,
        low=190.0,
        close=240.0,
        volume=999999.0,
        is_closed=False,
    )
    baseline = FeatureEngine().compute(candles, symbol="BTCUSDT", timeframe="5m")
    with_open = FeatureEngine().compute(candles + [open_candle], symbol="BTCUSDT", timeframe="5m")
    assert baseline.close == with_open.close
    assert baseline.volume_ratio == with_open.volume_ratio
    assert with_open.quality.ignored_open_candles == 1


def test_only_open_candles_raise_explicit_error() -> None:
    candle = make_candles(1)[0]
    open_candle = Candle(**{**candle.__dict__, "is_closed": False})
    with pytest.raises(InsufficientHistoryError):
        FeatureEngine().compute([open_candle], symbol="BTCUSDT", timeframe="5m")


def test_duplicate_timestamps_are_rejected() -> None:
    candles = make_candles(2)
    with pytest.raises(ValueError, match="duplicate candle timestamps"):
        FeatureEngine().compute(candles + [candles[-1]], symbol="BTCUSDT", timeframe="5m")


def test_market_regime_is_bullish_on_strong_uptrend() -> None:
    snapshot = FeatureEngine().compute(make_candles(80, trend=1.0), symbol="BTCUSDT", timeframe="5m")
    assert snapshot.regime == MarketRegime.BULLISH_TREND
