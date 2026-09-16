from __future__ import annotations

from decimal import Decimal

from app.analytics.indicators import AnalyticsIndicatorEngine

SHA = "b" * 64


def test_indicator_prefix_invariance(trend_candles_factory) -> None:
    candles = trend_candles_factory(150)
    cutoff_index = 89
    cutoff = candles[cutoff_index].close_time
    engine = AnalyticsIndicatorEngine()
    full = engine.compute(
        candles,
        symbol="BTC/EUR",
        timeframe="1h",
        as_of=cutoff,
        source_cursor_fingerprint=SHA,
    )
    prefix = engine.compute(
        candles[: cutoff_index + 1],
        symbol="BTC/EUR",
        timeframe="1h",
        as_of=cutoff,
        source_cursor_fingerprint=SHA,
    )
    assert full == prefix
    assert full.snapshot_fingerprint == prefix.snapshot_fingerprint


def test_future_candle_does_not_change_snapshot_at_T(trend_candles_factory) -> None:
    candles = trend_candles_factory(80)
    cutoff = candles[59].close_time
    baseline = AnalyticsIndicatorEngine().compute(
        candles[:60],
        symbol="BTC/EUR",
        timeframe="1h",
        as_of=cutoff,
        source_cursor_fingerprint=SHA,
    )
    future = candles[60].model_copy(
        update={
            "high": Decimal("999999"),
            "low": Decimal("0.01"),
            "close": Decimal("500000"),
            "volume": Decimal("999999999"),
        }
    )
    full = AnalyticsIndicatorEngine().compute(
        [*candles[:60], future, *candles[61:]],
        symbol="BTC/EUR",
        timeframe="1h",
        as_of=cutoff,
        source_cursor_fingerprint=SHA,
    )
    assert full == baseline


def test_same_inputs_are_idempotent(trend_candles_factory) -> None:
    candles = trend_candles_factory(220)
    kwargs = dict(
        symbol="BTC/EUR",
        timeframe="1h",
        as_of=candles[-1].close_time,
        source_cursor_fingerprint=SHA,
    )
    first = AnalyticsIndicatorEngine().compute(candles, **kwargs)
    second = AnalyticsIndicatorEngine().compute(candles, **kwargs)
    assert first == second
    assert first.snapshot_fingerprint == second.snapshot_fingerprint
