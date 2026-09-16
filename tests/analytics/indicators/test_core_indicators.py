from __future__ import annotations

from math import sqrt

import pytest

from app.analytics.indicators import AnalyticsIndicatorEngine

SHA = "a" * 64


def _snapshot(candles):
    return AnalyticsIndicatorEngine().compute(
        candles,
        symbol="BTC/EUR",
        timeframe="1h",
        as_of=candles[-1].close_time,
        source_cursor_fingerprint=SHA,
    )


def test_trend_momentum_volatility_volume_and_structure_golden(trend_candles_factory) -> None:
    candles = trend_candles_factory(260)
    snapshot = _snapshot(candles)

    def value(key: str) -> float | None:
        return snapshot.value(key).value

    assert value("sma_20") == pytest.approx(349.5)
    assert value("ema_20") == pytest.approx(349.5)
    assert value("sma_200") == pytest.approx(259.5)
    assert value("ema_200") == pytest.approx(259.5)
    assert value("ema_20_distance_pct") == pytest.approx((359.0 / 349.5 - 1.0) * 100.0)
    assert value("ema_20_slope_pct") == pytest.approx((349.5 / 348.5 - 1.0) * 100.0)

    assert value("rsi_14") == pytest.approx(100.0)
    assert value("rsi_delta_14") == pytest.approx(0.0)
    assert value("stoch_rsi_k_14_14_3_3") == pytest.approx(0.0)
    assert value("stoch_rsi_d_14_14_3_3") == pytest.approx(0.0)
    assert value("roc_12") == pytest.approx((359.0 / 347.0 - 1.0) * 100.0)
    assert value("macd_12_26_9") == pytest.approx(7.0)
    assert value("macd_signal_12_26_9") == pytest.approx(7.0)
    assert value("macd_hist_12_26_9") == pytest.approx(0.0)

    assert value("atr_14") == pytest.approx(2.0)
    assert value("atr_pct_14") == pytest.approx(2.0 / 359.0 * 100.0)
    bb_std = sqrt((20.0**2 - 1.0) / 12.0)
    assert value("bb_mid_20_2") == pytest.approx(349.5)
    assert value("bb_upper_20_2") == pytest.approx(349.5 + 2.0 * bb_std)
    assert value("bb_lower_20_2") == pytest.approx(349.5 - 2.0 * bb_std)
    assert value("adx_14") == pytest.approx(100.0)
    assert value("plus_di_14") == pytest.approx(50.0)
    assert value("minus_di_14") == pytest.approx(0.0)

    assert value("volume_sma_20") == pytest.approx(100.0)
    assert value("volume_ratio_20") == pytest.approx(1.0)
    assert value("obv") == pytest.approx(25900.0)
    assert value("mfi_14") == pytest.approx(100.0)
    assert value("cmf_20") == pytest.approx(0.0)
    assert value("rolling_vwap_20") == pytest.approx(349.5)

    assert value("rolling_high_prev_20") == pytest.approx(359.0)
    assert value("rolling_low_prev_20") == pytest.approx(338.0)
    assert value("donchian_upper_20") == pytest.approx(359.0)
    assert value("donchian_lower_20") == pytest.approx(338.0)
    assert value("donchian_position_20") == pytest.approx(1.0)


def test_flat_market_edge_cases_are_deterministic(trend_candles_factory) -> None:
    candles = trend_candles_factory(80, step=0.0)
    snapshot = _snapshot(candles)
    assert snapshot.value("rsi_14").value == pytest.approx(50.0)
    assert snapshot.value("stoch_rsi_k_14_14_3_3").value == pytest.approx(0.0)
    assert snapshot.value("adx_14").value == pytest.approx(0.0)
    assert snapshot.value("mfi_14").value == pytest.approx(50.0)
    assert snapshot.value("obv").value == pytest.approx(0.0)


def test_volume_spike_ratio_includes_current_candle(trend_candles_factory) -> None:
    candles = trend_candles_factory(20)
    candles[-1] = candles[-1].model_copy(update={"volume": 1000})
    snapshot = _snapshot(candles)
    assert snapshot.value("volume_sma_20").value == pytest.approx(145.0)
    assert snapshot.value("volume_ratio_20").value == pytest.approx(1000.0 / 145.0)


def test_insufficient_warmup_is_explicit_not_zero(trend_candles_factory) -> None:
    candles = trend_candles_factory(10)
    snapshot = _snapshot(candles)
    for key in ("sma_20", "ema_20", "rsi_14", "atr_14", "adx_14", "mfi_14", "cmf_20"):
        item = snapshot.value(key)
        assert item.value is None
        assert item.available is False
        assert item.warmup_complete is False
    assert snapshot.value("obv").warmup_complete is True
    assert snapshot.value("obv").available is True
