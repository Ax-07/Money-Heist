from __future__ import annotations

import pytest

from app.market.features.indicators import adx, atr, bollinger, ema, macd, realized_volatility_pct, rsi, sma


def test_sma_returns_expected_value() -> None:
    assert sma([1, 2, 3, 4, 5], 3) == pytest.approx(4.0)


def test_ema_constant_series_stays_constant() -> None:
    assert ema([7.0] * 30, 12) == pytest.approx(7.0)


def test_rsi_strictly_rising_series_is_100() -> None:
    assert rsi([float(value) for value in range(1, 20)], 14) == pytest.approx(100.0)


def test_atr_constant_range_is_stable() -> None:
    highs = [11.0] * 20
    lows = [9.0] * 20
    closes = [10.0] * 20
    assert atr(highs, lows, closes, 14) == pytest.approx(2.0)


def test_macd_constant_series_is_zero_after_warmup() -> None:
    line, signal, histogram = macd([10.0] * 60)
    assert line == pytest.approx(0.0)
    assert signal == pytest.approx(0.0)
    assert histogram == pytest.approx(0.0)


def test_bollinger_constant_series_collapses_to_midline() -> None:
    mid, upper, lower = bollinger([10.0] * 20)
    assert mid == upper == lower == pytest.approx(10.0)


def test_adx_detects_strong_monotonic_trend() -> None:
    closes = [100.0 + index for index in range(40)]
    highs = [value + 0.5 for value in closes]
    lows = [value - 0.5 for value in closes]
    value = adx(highs, lows, closes)
    assert value is not None
    assert value > 90.0


def test_realized_volatility_is_zero_for_constant_prices() -> None:
    assert realized_volatility_pct([100.0] * 25, 20) == pytest.approx(0.0)
