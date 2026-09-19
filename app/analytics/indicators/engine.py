from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite, sqrt
from typing import Any

from .models import AnalyticsIndicatorSnapshot, IndicatorValue
from .registry import INDICATOR_REGISTRY


class IndicatorInputError(ValueError):
    """Raised when a visible candle cannot safely feed the Analytics engine."""


class _RollingMean:
    def __init__(self, period: int) -> None:
        self.period = period
        self.values: deque[float] = deque()
        self.total = 0.0

    def push(self, value: float) -> float | None:
        self.values.append(value)
        self.total += value
        if len(self.values) > self.period:
            self.total -= self.values.popleft()
        if len(self.values) < self.period:
            return None
        return self.total / self.period


class _RollingStats:
    def __init__(self, period: int) -> None:
        self.period = period
        self.values: deque[float] = deque()
        self.total = 0.0
        self.total_sq = 0.0

    def push(self, value: float) -> tuple[float, float] | None:
        self.values.append(value)
        self.total += value
        self.total_sq += value * value
        if len(self.values) > self.period:
            removed = self.values.popleft()
            self.total -= removed
            self.total_sq -= removed * removed
        if len(self.values) < self.period:
            return None
        mean = self.total / self.period
        variance = max(0.0, self.total_sq / self.period - mean * mean)
        return mean, sqrt(variance)


class _RollingSum:
    def __init__(self, period: int) -> None:
        self.period = period
        self.values: deque[float] = deque()
        self.total = 0.0

    def push(self, value: float) -> float | None:
        self.values.append(value)
        self.total += value
        if len(self.values) > self.period:
            self.total -= self.values.popleft()
        if len(self.values) < self.period:
            return None
        return self.total


class _EMA:
    def __init__(self, period: int) -> None:
        self.period = period
        self.alpha = 2.0 / (period + 1.0)
        self.seed: list[float] = []
        self.value: float | None = None

    def push(self, value: float) -> float | None:
        if self.value is None:
            self.seed.append(value)
            if len(self.seed) < self.period:
                return None
            self.value = sum(self.seed) / self.period
            self.seed.clear()
            return self.value
        self.value = self.value + self.alpha * (value - self.value)
        return self.value


class _WilderAverage:
    def __init__(self, period: int) -> None:
        self.period = period
        self.seed: list[float] = []
        self.value: float | None = None

    def push(self, value: float) -> float | None:
        if self.value is None:
            self.seed.append(value)
            if len(self.seed) < self.period:
                return None
            self.value = sum(self.seed) / self.period
            self.seed.clear()
            return self.value
        self.value = ((self.value * (self.period - 1)) + value) / self.period
        return self.value


class _RSIState:
    def __init__(self, period: int) -> None:
        self.avg_gain = _WilderAverage(period)
        self.avg_loss = _WilderAverage(period)
        self.previous_close: float | None = None

    def push(self, close: float) -> float | None:
        if self.previous_close is None:
            self.previous_close = close
            return None
        change = close - self.previous_close
        self.previous_close = close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = self.avg_gain.push(gain)
        avg_loss = self.avg_loss.push(loss)
        if avg_gain is None or avg_loss is None:
            return None
        if avg_loss == 0.0:
            return 100.0 if avg_gain > 0.0 else 50.0
        if avg_gain == 0.0:
            return 0.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))


class _ATRState:
    def __init__(self, period: int) -> None:
        self.average = _WilderAverage(period)
        self.previous_close: float | None = None

    def push(self, high: float, low: float, close: float) -> float | None:
        true_range = (
            high - low
            if self.previous_close is None
            else max(high - low, abs(high - self.previous_close), abs(low - self.previous_close))
        )
        self.previous_close = close
        return self.average.push(true_range)


class _ADXState:
    """Wilder ADX using first-transition TR/DM seeding (Analytics semantics)."""

    def __init__(self, period: int) -> None:
        self.period = period
        self.previous_high: float | None = None
        self.previous_low: float | None = None
        self.previous_close: float | None = None
        self.tr_sum = 0.0
        self.plus_dm_sum = 0.0
        self.minus_dm_sum = 0.0
        self.seed_count = 0
        self.dx_seed: list[float] = []
        self.adx: float | None = None

    def push(
        self, high: float, low: float, close: float
    ) -> tuple[float | None, float | None, float | None]:
        if self.previous_high is None or self.previous_low is None or self.previous_close is None:
            self.previous_high = high
            self.previous_low = low
            self.previous_close = close
            return None, None, None

        up_move = high - self.previous_high
        down_move = self.previous_low - low
        plus_dm = up_move if up_move > down_move and up_move > 0.0 else 0.0
        minus_dm = down_move if down_move > up_move and down_move > 0.0 else 0.0
        tr = max(high - low, abs(high - self.previous_close), abs(low - self.previous_close))
        self.previous_high = high
        self.previous_low = low
        self.previous_close = close

        if self.seed_count < self.period:
            self.tr_sum += tr
            self.plus_dm_sum += plus_dm
            self.minus_dm_sum += minus_dm
            self.seed_count += 1
            if self.seed_count < self.period:
                return None, None, None
        else:
            self.tr_sum = self.tr_sum - (self.tr_sum / self.period) + tr
            self.plus_dm_sum = self.plus_dm_sum - (self.plus_dm_sum / self.period) + plus_dm
            self.minus_dm_sum = self.minus_dm_sum - (self.minus_dm_sum / self.period) + minus_dm

        if self.tr_sum == 0.0:
            plus_di = 0.0
            minus_di = 0.0
        else:
            plus_di = 100.0 * self.plus_dm_sum / self.tr_sum
            minus_di = 100.0 * self.minus_dm_sum / self.tr_sum

        denominator = plus_di + minus_di
        dx = 0.0 if denominator == 0.0 else 100.0 * abs(plus_di - minus_di) / denominator
        if self.adx is None:
            self.dx_seed.append(dx)
            if len(self.dx_seed) == self.period:
                self.adx = sum(self.dx_seed) / self.period
                self.dx_seed.clear()
        else:
            self.adx = ((self.adx * (self.period - 1)) + dx) / self.period
        return self.adx, plus_di, minus_di


class _RollingExtrema:
    def __init__(self, period: int, *, maximum: bool) -> None:
        self.period = period
        self.maximum = maximum
        self.index = -1
        self.queue: deque[tuple[int, float]] = deque()

    def current(self) -> float | None:
        if self.index + 1 < self.period or not self.queue:
            return None
        return self.queue[0][1]

    def push(self, value: float) -> None:
        self.index += 1
        minimum_index = self.index - self.period + 1
        while self.queue and self.queue[0][0] < minimum_index:
            self.queue.popleft()
        if self.maximum:
            while self.queue and self.queue[-1][1] <= value:
                self.queue.pop()
        else:
            while self.queue and self.queue[-1][1] >= value:
                self.queue.pop()
        self.queue.append((self.index, value))


class _StochRSIState:
    def __init__(
        self,
        rsi_period: int = 14,
        stoch_period: int = 14,
        smooth_k: int = 3,
        smooth_d: int = 3,
    ) -> None:
        self.rsi = _RSIState(rsi_period)
        self.stoch_period = stoch_period
        self.rsi_window: deque[float] = deque(maxlen=stoch_period)
        self.k_mean = _RollingMean(smooth_k)
        self.d_mean = _RollingMean(smooth_d)

    def push(self, close: float) -> tuple[float | None, float | None]:
        rsi = self.rsi.push(close)
        if rsi is None:
            return None, None
        self.rsi_window.append(rsi)
        if len(self.rsi_window) < self.stoch_period:
            return None, None
        minimum = min(self.rsi_window)
        maximum = max(self.rsi_window)
        raw = 0.0 if maximum == minimum else 100.0 * (rsi - minimum) / (maximum - minimum)
        k = self.k_mean.push(raw)
        if k is None:
            return None, None
        return k, self.d_mean.push(k)


class _MFIState:
    def __init__(self, period: int) -> None:
        self.period = period
        self.previous_typical: float | None = None
        self.positive: deque[float] = deque()
        self.negative: deque[float] = deque()
        self.positive_sum = 0.0
        self.negative_sum = 0.0

    def push(self, high: float, low: float, close: float, volume: float) -> float | None:
        typical = (high + low + close) / 3.0
        if self.previous_typical is None:
            self.previous_typical = typical
            return None
        flow = typical * volume
        positive = flow if typical > self.previous_typical else 0.0
        negative = flow if typical < self.previous_typical else 0.0
        self.previous_typical = typical
        self.positive.append(positive)
        self.negative.append(negative)
        self.positive_sum += positive
        self.negative_sum += negative
        if len(self.positive) > self.period:
            self.positive_sum -= self.positive.popleft()
            self.negative_sum -= self.negative.popleft()
        if len(self.positive) < self.period:
            return None
        if self.negative_sum == 0.0:
            return 100.0 if self.positive_sum > 0.0 else 50.0
        ratio = self.positive_sum / self.negative_sum
        return 100.0 - (100.0 / (1.0 + ratio))


@dataclass(frozen=True, slots=True)
class _Candle:
    symbol: str
    timeframe: str
    close_time: datetime
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class _EngineState:
    sma: dict[int, _RollingMean]
    ema: dict[int, _EMA]
    ema_previous: dict[int, float | None]
    rsi: _RSIState
    rsi_previous: float | None
    stoch_rsi: _StochRSIState
    roc_closes: deque[float]
    macd_fast: _EMA
    macd_slow: _EMA
    macd_signal: _EMA
    atr: _ATRState
    bollinger: _RollingStats
    adx: _ADXState
    volume_sma: _RollingMean
    obv: float
    obv_previous_close: float | None
    mfi: _MFIState
    cmf_mfv: _RollingSum
    cmf_volume: _RollingSum
    vwap_pv: _RollingSum
    vwap_volume: _RollingSum
    extrema_high: dict[int, _RollingExtrema]
    extrema_low: dict[int, _RollingExtrema]


def _new_state() -> _EngineState:
    return _EngineState(
        sma={period: _RollingMean(period) for period in (20, 50, 100, 200)},
        ema={period: _EMA(period) for period in (9, 20, 50, 100, 200)},
        ema_previous={period: None for period in (9, 20, 50, 100, 200)},
        rsi=_RSIState(14),
        rsi_previous=None,
        stoch_rsi=_StochRSIState(),
        roc_closes=deque(maxlen=13),
        macd_fast=_EMA(12),
        macd_slow=_EMA(26),
        macd_signal=_EMA(9),
        atr=_ATRState(14),
        bollinger=_RollingStats(20),
        adx=_ADXState(14),
        volume_sma=_RollingMean(20),
        obv=0.0,
        obv_previous_close=None,
        mfi=_MFIState(14),
        cmf_mfv=_RollingSum(20),
        cmf_volume=_RollingSum(20),
        vwap_pv=_RollingSum(20),
        vwap_volume=_RollingSum(20),
        extrema_high={period: _RollingExtrema(period, maximum=True) for period in (20, 50, 100)},
        extrema_low={period: _RollingExtrema(period, maximum=False) for period in (20, 50, 100)},
    )


class AnalyticsIndicatorEngine:
    """Deterministic, observation-only indicator engine over canonical closed candles."""

    def compute(
        self,
        candles: Sequence[Any],
        *,
        symbol: str,
        timeframe: str,
        as_of: datetime,
        source_cursor_fingerprint: str,
    ) -> AnalyticsIndicatorSnapshot:
        cutoff = _as_utc(as_of, field="as_of")
        visible = self._visible_candles(
            candles,
            symbol=symbol,
            timeframe=timeframe,
            as_of=cutoff,
        )
        latest = self._compute_latest_values(visible)
        count = len(visible)
        values = tuple(
            IndicatorValue(
                indicator_id=definition.indicator_id,
                value=latest[definition.indicator_id],
                available=latest[definition.indicator_id] is not None,
                warmup_complete=count >= definition.warmup_bars,
                definition_version=definition.definition_version,
            )
            for definition in INDICATOR_REGISTRY
        )
        return AnalyticsIndicatorSnapshot.create(
            symbol=symbol,
            timeframe=timeframe,
            as_of=cutoff,
            source_cursor_fingerprint=source_cursor_fingerprint,
            candle_count=count,
            values=values,
        )

    def _visible_candles(
        self,
        candles: Sequence[Any],
        *,
        symbol: str,
        timeframe: str,
        as_of: datetime,
    ) -> tuple[_Candle, ...]:
        output: list[_Candle] = []
        for raw in candles:
            close_time_raw = _read(raw, "close_time")
            close_time = _as_utc(_coerce_datetime(close_time_raw), field="candle.close_time")
            if close_time > as_of:
                # Future OHLCV is deliberately not parsed or validated. A malformed future
                # value must not alter a snapshot at T through an exception side channel.
                continue
            if not bool(_read_optional(raw, "is_closed", default=True)):
                continue
            candle_symbol = str(_read(raw, "symbol")).strip()
            candle_timeframe = str(_read(raw, "timeframe")).strip().lower()
            if candle_symbol != symbol:
                raise IndicatorInputError("visible candle symbol does not match requested symbol")
            if candle_timeframe != timeframe.strip().lower():
                raise IndicatorInputError(
                    "visible candle timeframe does not match requested timeframe"
                )
            high = _coerce_float(_read(raw, "high"), field="high")
            low = _coerce_float(_read(raw, "low"), field="low")
            close = _coerce_float(_read(raw, "close"), field="close")
            volume = _coerce_float(_read(raw, "volume"), field="volume")
            if high < low:
                raise IndicatorInputError("candle high must be >= low")
            if high < close or low > close:
                raise IndicatorInputError("candle close must stay inside high/low")
            if volume < 0.0:
                raise IndicatorInputError("candle volume must be >= 0")
            output.append(
                _Candle(
                    symbol=candle_symbol,
                    timeframe=candle_timeframe,
                    close_time=close_time,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                )
            )
        output.sort(key=lambda item: item.close_time)
        close_times = [item.close_time for item in output]
        if len(close_times) != len(set(close_times)):
            raise IndicatorInputError("duplicate visible candle close_time is not allowed")
        return tuple(output)

    @staticmethod
    def _compute_latest_values(candles: Sequence[_Candle]) -> dict[str, float | None]:
        state = _new_state()
        values: dict[str, float | None] = {
            definition.indicator_id: None for definition in INDICATOR_REGISTRY
        }
        for candle in candles:
            high = candle.high
            low = candle.low
            close = candle.close
            volume = candle.volume

            for period, rolling in state.sma.items():
                values[f"sma_{period}"] = rolling.push(close)

            for period, ema in state.ema.items():
                current = ema.push(close)
                values[f"ema_{period}"] = current
                if period in (20, 50, 200):
                    values[f"ema_{period}_distance_pct"] = _pct_distance(close, current)
                    previous = state.ema_previous[period]
                    values[f"ema_{period}_slope_pct"] = _pct_change(current, previous)
                state.ema_previous[period] = current

            rsi = state.rsi.push(close)
            values["rsi_14"] = rsi
            values["rsi_delta_14"] = _difference(rsi, state.rsi_previous)
            state.rsi_previous = rsi

            stoch_k, stoch_d = state.stoch_rsi.push(close)
            values["stoch_rsi_k_14_14_3_3"] = stoch_k
            values["stoch_rsi_d_14_14_3_3"] = stoch_d

            state.roc_closes.append(close)
            if len(state.roc_closes) == 13:
                base = state.roc_closes[0]
                values["roc_12"] = None if base == 0.0 else (close / base - 1.0) * 100.0

            macd_fast = state.macd_fast.push(close)
            macd_slow = state.macd_slow.push(close)
            macd = None if macd_fast is None or macd_slow is None else macd_fast - macd_slow
            values["macd_12_26_9"] = macd
            macd_signal = None if macd is None else state.macd_signal.push(macd)
            values["macd_signal_12_26_9"] = macd_signal
            values["macd_hist_12_26_9"] = (
                None if macd is None or macd_signal is None else macd - macd_signal
            )

            atr = state.atr.push(high, low, close)
            values["atr_14"] = atr
            values["atr_pct_14"] = None if atr is None or close == 0.0 else atr / close * 100.0

            bb = state.bollinger.push(close)
            if bb is not None:
                middle, stddev = bb
                upper = middle + 2.0 * stddev
                lower = middle - 2.0 * stddev
                values["bb_mid_20_2"] = middle
                values["bb_upper_20_2"] = upper
                values["bb_lower_20_2"] = lower
                values["bb_width_pct_20_2"] = (
                    None if middle == 0.0 else (upper - lower) / middle * 100.0
                )
                values["bb_position_20_2"] = _position(close, lower, upper)

            adx, plus_di, minus_di = state.adx.push(high, low, close)
            values["adx_14"] = adx
            values["plus_di_14"] = plus_di
            values["minus_di_14"] = minus_di

            volume_sma = state.volume_sma.push(volume)
            values["volume_sma_20"] = volume_sma
            values["volume_ratio_20"] = None if volume_sma in (None, 0.0) else volume / volume_sma

            if state.obv_previous_close is not None:
                if close > state.obv_previous_close:
                    state.obv += volume
                elif close < state.obv_previous_close:
                    state.obv -= volume
            state.obv_previous_close = close
            values["obv"] = state.obv

            values["mfi_14"] = state.mfi.push(high, low, close, volume)

            denominator = high - low
            multiplier = (
                0.0 if denominator == 0.0 else ((close - low) - (high - close)) / denominator
            )
            mfv_sum = state.cmf_mfv.push(multiplier * volume)
            cmf_volume_sum = state.cmf_volume.push(volume)
            values["cmf_20"] = (
                None
                if mfv_sum is None or cmf_volume_sum in (None, 0.0)
                else mfv_sum / cmf_volume_sum
            )

            typical_price = (high + low + close) / 3.0
            pv_sum = state.vwap_pv.push(typical_price * volume)
            vwap_volume_sum = state.vwap_volume.push(volume)
            values["rolling_vwap_20"] = (
                None
                if pv_sum is None or vwap_volume_sum in (None, 0.0)
                else pv_sum / vwap_volume_sum
            )

            previous_extrema = {
                period: (
                    state.extrema_high[period].current(),
                    state.extrema_low[period].current(),
                )
                for period in (20, 50, 100)
            }
            for period, (previous_high, previous_low) in previous_extrema.items():
                values[f"rolling_high_prev_{period}"] = previous_high
                values[f"rolling_low_prev_{period}"] = previous_low
            donchian_upper, donchian_lower = previous_extrema[20]
            values["donchian_upper_20"] = donchian_upper
            values["donchian_lower_20"] = donchian_lower
            if donchian_upper is not None and donchian_lower is not None:
                values["donchian_position_20"] = _position(close, donchian_lower, donchian_upper)
                values["distance_to_high_20_pct"] = _pct_distance(close, donchian_upper)
                values["distance_to_low_20_pct"] = _pct_distance(close, donchian_lower)

            for period in (20, 50, 100):
                state.extrema_high[period].push(high)
                state.extrema_low[period].push(low)
        return values


def _position(value: float, lower: float, upper: float) -> float | None:
    width = upper - lower
    return None if width == 0.0 else (value - lower) / width


def _pct_distance(value: float, reference: float | None) -> float | None:
    if reference in (None, 0.0):
        return None
    return (value / reference - 1.0) * 100.0


def _pct_change(value: float | None, previous: float | None) -> float | None:
    if value is None or previous in (None, 0.0):
        return None
    return (value / previous - 1.0) * 100.0


def _difference(value: float | None, previous: float | None) -> float | None:
    if value is None or previous is None:
        return None
    return value - previous


def _read(raw: Any, name: str) -> Any:
    sentinel = object()
    value = _read_optional(raw, name, default=sentinel)
    if value is sentinel:
        raise IndicatorInputError(f"candle is missing required field {name!r}")
    return value


def _read_optional(raw: Any, name: str, *, default: Any) -> Any:
    if isinstance(raw, Mapping):
        return raw.get(name, default)
    return getattr(raw, name, default)


def _coerce_float(value: Any, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise IndicatorInputError(f"candle {field} must be numeric") from exc
    if not isfinite(number):
        raise IndicatorInputError(f"candle {field} must be finite")
    return number


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise IndicatorInputError("candle close_time must be ISO-8601") from exc
    raise IndicatorInputError("candle close_time must be datetime or ISO-8601")


def _as_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise IndicatorInputError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


__all__ = ["AnalyticsIndicatorEngine", "IndicatorInputError"]
