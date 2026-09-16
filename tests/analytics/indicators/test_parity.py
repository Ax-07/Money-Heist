from __future__ import annotations

import pytest

from app.analytics.indicators import PARITY_BY_INDICATOR, AnalyticsIndicatorEngine, ParityStatus
from app.market.features.indicators import adx, atr, bollinger, ema, macd, rsi

SHA = "c" * 64


def _analytics(candles):
    return AnalyticsIndicatorEngine().compute(
        candles,
        symbol="BTC/EUR",
        timeframe="1h",
        as_of=candles[-1].close_time,
        source_cursor_fingerprint=SHA,
    )


def _hlc(candles):
    highs = [float(candle.high) for candle in candles]
    lows = [float(candle.low) for candle in candles]
    closes = [float(candle.close) for candle in candles]
    return highs, lows, closes


def test_verified_same_semantics_ema_rsi_atr_bollinger_macd(trend_candles_factory) -> None:
    candles = trend_candles_factory(120)
    snapshot = _analytics(candles)
    highs, lows, closes = _hlc(candles)

    assert snapshot.value("ema_20").value == pytest.approx(ema(closes, 20))
    assert snapshot.value("rsi_14").value == pytest.approx(rsi(closes, 14))
    assert snapshot.value("atr_14").value == pytest.approx(atr(highs, lows, closes, 14))
    middle, upper, lower = bollinger(closes, period=20, stddev_multiplier=2.0)
    assert snapshot.value("bb_mid_20_2").value == pytest.approx(middle)
    assert snapshot.value("bb_upper_20_2").value == pytest.approx(upper)
    assert snapshot.value("bb_lower_20_2").value == pytest.approx(lower)
    production_macd = macd(closes, fast_period=12, slow_period=26, signal_period=9)
    assert snapshot.value("macd_12_26_9").value == pytest.approx(production_macd[0])
    assert snapshot.value("macd_signal_12_26_9").value == pytest.approx(production_macd[1])
    assert snapshot.value("macd_hist_12_26_9").value == pytest.approx(production_macd[2])


def test_adx_semantic_difference_is_intentional_and_observable(trend_candles_factory) -> None:
    candles = trend_candles_factory(60)
    # Add alternating directional expansion so the initialization difference remains observable.
    adjusted = []
    for index, candle in enumerate(candles):
        if index == 0:
            adjusted.append(candle.model_copy(update={"high": 180, "low": 20, "close": 100}))
        elif index % 2:
            adjusted.append(
                candle.model_copy(
                    update={
                        "high": float(candle.high) + 8,
                        "low": float(candle.low),
                        "close": float(candle.close) + 4,
                    }
                )
            )
        else:
            adjusted.append(
                candle.model_copy(
                    update={
                        "high": float(candle.high),
                        "low": max(1.0, float(candle.low) - 7),
                        "close": max(1.0, float(candle.close) - 3),
                    }
                )
            )
    snapshot = _analytics(adjusted)
    highs, lows, closes = _hlc(adjusted)
    feature_value = adx(highs, lows, closes, 14)
    analytics_value = snapshot.value("adx_14").value
    assert feature_value is not None and analytics_value is not None
    assert analytics_value != pytest.approx(feature_value, rel=1e-10, abs=1e-10)
    assert PARITY_BY_INDICATOR["adx_14"].status is ParityStatus.INTENTIONAL_DIVERGENCE


def test_volume_ratio_semantic_difference_is_intentional(trend_candles_factory) -> None:
    candles = trend_candles_factory(21)
    candles = [c.model_copy(update={"volume": index + 1}) for index, c in enumerate(candles)]
    snapshot = _analytics(candles)
    analytics_ratio = snapshot.value("volume_ratio_20").value
    production_prior_sma = sum(range(1, 21)) / 20.0
    production_ratio = 21.0 / production_prior_sma
    analytics_current_sma = sum(range(2, 22)) / 20.0
    assert analytics_ratio == pytest.approx(21.0 / analytics_current_sma)
    assert analytics_ratio != pytest.approx(production_ratio)
    assert PARITY_BY_INDICATOR["volume_ratio_20"].status is ParityStatus.INTENTIONAL_DIVERGENCE
