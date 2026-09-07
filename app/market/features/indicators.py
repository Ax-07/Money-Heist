from __future__ import annotations

from math import log, sqrt
from statistics import fmean, pstdev
from typing import Sequence


def sma(values: Sequence[float], period: int) -> float | None:
    _validate_period(period)
    if len(values) < period:
        return None
    return fmean(values[-period:])


def ema_series(values: Sequence[float], period: int) -> list[float | None]:
    _validate_period(period)
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result

    seed = fmean(values[:period])
    result[period - 1] = seed
    alpha = 2.0 / (period + 1.0)
    previous = seed
    for index in range(period, len(values)):
        previous = alpha * values[index] + (1.0 - alpha) * previous
        result[index] = previous
    return result


def ema(values: Sequence[float], period: int) -> float | None:
    series = ema_series(values, period)
    return series[-1] if series else None


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    _validate_period(period)
    if len(values) < period + 1:
        return None

    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values, values[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = fmean(gains[:period])
    avg_loss = fmean(losses[:period])
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    if avg_gain == 0.0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def true_ranges(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> list[float]:
    _same_length(highs, lows, closes)
    if not closes:
        return []

    result = [highs[0] - lows[0]]
    for index in range(1, len(closes)):
        result.append(
            max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            )
        )
    return result


def wilder_series(values: Sequence[float], period: int) -> list[float | None]:
    _validate_period(period)
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result

    previous = fmean(values[:period])
    result[period - 1] = previous
    for index in range(period, len(values)):
        previous = ((previous * (period - 1)) + values[index]) / period
        result[index] = previous
    return result


def atr_series(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14
) -> list[float | None]:
    return wilder_series(true_ranges(highs, lows, closes), period)


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> float | None:
    series = atr_series(highs, lows, closes, period)
    return series[-1] if series else None


def macd(
    values: Sequence[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
) -> tuple[float | None, float | None, float | None]:
    if fast_period >= slow_period:
        raise ValueError("fast_period must be lower than slow_period")

    fast = ema_series(values, fast_period)
    slow = ema_series(values, slow_period)
    macd_points: list[tuple[int, float]] = []
    for index, (fast_value, slow_value) in enumerate(zip(fast, slow)):
        if fast_value is not None and slow_value is not None:
            macd_points.append((index, fast_value - slow_value))

    if not macd_points:
        return None, None, None

    macd_values = [value for _, value in macd_points]
    signal_values = ema_series(macd_values, signal_period)
    line = macd_values[-1]
    signal = signal_values[-1]
    histogram = None if signal is None else line - signal
    return line, signal, histogram


def bollinger(values: Sequence[float], period: int = 20, stddev_multiplier: float = 2.0) -> tuple[float | None, float | None, float | None]:
    _validate_period(period)
    if len(values) < period:
        return None, None, None
    window = list(values[-period:])
    mid = fmean(window)
    deviation = pstdev(window)
    return mid, mid + stddev_multiplier * deviation, mid - stddev_multiplier * deviation


def adx(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14
) -> float | None:
    _same_length(highs, lows, closes)
    _validate_period(period)
    if len(closes) < (period * 2):
        return None

    tr = true_ranges(highs, lows, closes)
    plus_dm = [0.0]
    minus_dm = [0.0]
    for index in range(1, len(closes)):
        up_move = highs[index] - highs[index - 1]
        down_move = lows[index - 1] - lows[index]
        plus_dm.append(up_move if up_move > down_move and up_move > 0.0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0.0 else 0.0)

    atr_values = wilder_series(tr, period)
    plus_values = wilder_series(plus_dm, period)
    minus_values = wilder_series(minus_dm, period)

    dx_values: list[float] = []
    for atr_value, plus_value, minus_value in zip(atr_values, plus_values, minus_values):
        if atr_value is None or plus_value is None or minus_value is None or atr_value == 0.0:
            continue
        plus_di = 100.0 * plus_value / atr_value
        minus_di = 100.0 * minus_value / atr_value
        denominator = plus_di + minus_di
        dx_values.append(0.0 if denominator == 0.0 else 100.0 * abs(plus_di - minus_di) / denominator)

    if len(dx_values) < period:
        return None
    smoothed = wilder_series(dx_values, period)
    return smoothed[-1]


def realized_volatility_pct(values: Sequence[float], period: int = 20) -> float | None:
    _validate_period(period)
    if len(values) < period + 1:
        return None
    window = values[-(period + 1) :]
    if any(value <= 0.0 for value in window):
        return None
    returns = [log(current / previous) for previous, current in zip(window, window[1:])]
    return pstdev(returns) * sqrt(period) * 100.0


def _validate_period(period: int) -> None:
    if period <= 0:
        raise ValueError("period must be greater than zero")


def _same_length(*series: Sequence[float]) -> None:
    lengths = {len(values) for values in series}
    if len(lengths) > 1:
        raise ValueError("indicator input series must have identical lengths")
