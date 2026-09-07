from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

from .indicators import (
    adx,
    atr_series,
    bollinger,
    ema,
    macd,
    realized_volatility_pct,
    rsi,
    sma,
)
from .models import FeatureQuality, FeatureSnapshot, MarketRegime


class InsufficientHistoryError(ValueError):
    """Raised only when no usable closed candles are available."""


@dataclass(frozen=True, slots=True)
class FeatureEngineConfig:
    feature_version: str = "feature-engine-v1"
    ema_fast_period: int = 12
    ema_slow_period: int = 26
    rsi_period: int = 14
    atr_period: int = 14
    adx_period: int = 14
    bollinger_period: int = 20
    volume_period: int = 20
    structure_lookback: int = 20
    volatility_period: int = 20
    atr_expansion_lookback: int = 20
    trend_adx_threshold: float = 25.0
    trend_ema_spread_pct_threshold: float = 0.15

    @property
    def warmup_bars(self) -> int:
        # MACD needs slow + signal - 1 points; ADX needs roughly 2*period.
        return max(
            self.ema_slow_period + 9,
            self.adx_period * 2,
            self.bollinger_period,
            self.volume_period + 1,
            self.structure_lookback + 1,
            self.volatility_period + 1,
            self.atr_period + self.atr_expansion_lookback,
        )


@dataclass(frozen=True, slots=True)
class _Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool


class FeatureEngine:
    """Compute deterministic, replay-safe features from normalized OHLCV candles."""

    def __init__(self, config: FeatureEngineConfig | None = None) -> None:
        self.config = config or FeatureEngineConfig()

    def compute(
        self,
        candles: Sequence[Any],
        *,
        symbol: str,
        timeframe: str,
        source_snapshot_id: str | None = None,
        observed_at: datetime | None = None,
    ) -> FeatureSnapshot:
        normalized = [self._normalize_candle(candle) for candle in candles]
        normalized.sort(key=lambda candle: candle.timestamp)
        self._validate_unique_timestamps(normalized)

        closed = [candle for candle in normalized if candle.is_closed]
        ignored_open = len(normalized) - len(closed)
        if not closed:
            raise InsufficientHistoryError("at least one closed candle is required")

        opens = [candle.open for candle in closed]
        highs = [candle.high for candle in closed]
        lows = [candle.low for candle in closed]
        closes = [candle.close for candle in closed]
        volumes = [candle.volume for candle in closed]
        del opens  # retained in normalization validation; not needed by V1 indicators.

        timestamp = self._as_utc(observed_at or closed[-1].timestamp)
        fast = ema(closes, self.config.ema_fast_period)
        slow = ema(closes, self.config.ema_slow_period)
        spread_pct = self._percent_difference(fast, slow)
        rsi_value = rsi(closes, self.config.rsi_period)
        macd_line, macd_signal, macd_hist = macd(closes)

        atr_values = atr_series(highs, lows, closes, self.config.atr_period)
        atr_value = atr_values[-1]
        atr_pct = self._percent_of(atr_value, closes[-1])
        atr_expansion_ratio = self._atr_expansion_ratio(atr_values)

        adx_value = adx(highs, lows, closes, self.config.adx_period)
        bollinger_mid, bollinger_upper, bollinger_lower = bollinger(
            closes, self.config.bollinger_period
        )
        bollinger_width_pct = self._bollinger_width_pct(
            bollinger_mid, bollinger_upper, bollinger_lower
        )
        bollinger_position = self._bollinger_position(
            closes[-1], bollinger_upper, bollinger_lower
        )

        volume_sma = self._prior_sma(volumes, self.config.volume_period)
        volume_ratio = self._ratio(volumes[-1], volume_sma)
        realized_vol = realized_volatility_pct(closes, self.config.volatility_period)

        prior_high, prior_low = self._prior_range(highs, lows, self.config.structure_lookback)
        distance_high = self._signed_distance_pct(closes[-1], prior_high)
        distance_low = self._signed_distance_pct(closes[-1], prior_low)

        regime = self._classify_regime(
            close=closes[-1],
            ema_fast_value=fast,
            ema_slow_value=slow,
            ema_spread_pct=spread_pct,
            adx_value=adx_value,
        )

        feature_values = {
            "ema_fast": fast,
            "ema_slow": slow,
            "ema_spread_pct": spread_pct,
            "rsi_14": rsi_value,
            "macd_line": macd_line,
            "macd_signal": macd_signal,
            "macd_histogram": macd_hist,
            "atr_14": atr_value,
            "atr_pct": atr_pct,
            "atr_expansion_ratio": atr_expansion_ratio,
            "adx_14": adx_value,
            "bollinger_mid": bollinger_mid,
            "bollinger_upper": bollinger_upper,
            "bollinger_lower": bollinger_lower,
            "bollinger_width_pct": bollinger_width_pct,
            "bollinger_position": bollinger_position,
            "volume_sma_20": volume_sma,
            "volume_ratio": volume_ratio,
            "realized_volatility_20_pct": realized_vol,
            "prior_range_high_20": prior_high,
            "prior_range_low_20": prior_low,
            "distance_to_range_high_pct": distance_high,
            "distance_to_range_low_pct": distance_low,
        }
        missing = tuple(name for name, value in feature_values.items() if value is None)
        snapshot_id = source_snapshot_id or self._deterministic_snapshot_id(
            symbol=symbol,
            timeframe=timeframe,
            observed_at=timestamp,
            candle_count=len(closed),
            last_close=closes[-1],
        )

        return FeatureSnapshot(
            feature_version=self.config.feature_version,
            snapshot_id=snapshot_id,
            source_snapshot_id=source_snapshot_id,
            symbol=symbol,
            timeframe=timeframe,
            observed_at=timestamp,
            candle_count=len(closed),
            close=closes[-1],
            ema_fast=fast,
            ema_slow=slow,
            ema_spread_pct=spread_pct,
            rsi_14=rsi_value,
            macd_line=macd_line,
            macd_signal=macd_signal,
            macd_histogram=macd_hist,
            atr_14=atr_value,
            atr_pct=atr_pct,
            atr_expansion_ratio=atr_expansion_ratio,
            adx_14=adx_value,
            bollinger_mid=bollinger_mid,
            bollinger_upper=bollinger_upper,
            bollinger_lower=bollinger_lower,
            bollinger_width_pct=bollinger_width_pct,
            bollinger_position=bollinger_position,
            volume_sma_20=volume_sma,
            volume_ratio=volume_ratio,
            realized_volatility_20_pct=realized_vol,
            prior_range_high_20=prior_high,
            prior_range_low_20=prior_low,
            distance_to_range_high_pct=distance_high,
            distance_to_range_low_pct=distance_low,
            regime=regime,
            quality=FeatureQuality(
                warmup_complete=len(closed) >= self.config.warmup_bars,
                closed_candle_count=len(closed),
                missing_features=missing,
                ignored_open_candles=ignored_open,
            ),
        )

    def _atr_expansion_ratio(self, atr_values: Sequence[float | None]) -> float | None:
        current = atr_values[-1] if atr_values else None
        historical = [value for value in atr_values[:-1] if value is not None]
        if current is None or len(historical) < self.config.atr_expansion_lookback:
            return None
        baseline = sum(historical[-self.config.atr_expansion_lookback :]) / self.config.atr_expansion_lookback
        return self._ratio(current, baseline)

    def _classify_regime(
        self,
        *,
        close: float,
        ema_fast_value: float | None,
        ema_slow_value: float | None,
        ema_spread_pct: float | None,
        adx_value: float | None,
    ) -> MarketRegime:
        if None in (ema_fast_value, ema_slow_value, ema_spread_pct, adx_value):
            return MarketRegime.UNKNOWN
        assert ema_fast_value is not None
        assert ema_slow_value is not None
        assert ema_spread_pct is not None
        assert adx_value is not None
        if adx_value < self.config.trend_adx_threshold:
            return MarketRegime.RANGE
        if abs(ema_spread_pct) < self.config.trend_ema_spread_pct_threshold:
            return MarketRegime.RANGE
        if close > ema_fast_value > ema_slow_value:
            return MarketRegime.BULLISH_TREND
        if close < ema_fast_value < ema_slow_value:
            return MarketRegime.BEARISH_TREND
        return MarketRegime.RANGE

    def _prior_range(
        self, highs: Sequence[float], lows: Sequence[float], lookback: int
    ) -> tuple[float | None, float | None]:
        if len(highs) < lookback + 1:
            return None, None
        return max(highs[-(lookback + 1) : -1]), min(lows[-(lookback + 1) : -1])

    @staticmethod
    def _prior_sma(values: Sequence[float], period: int) -> float | None:
        if len(values) < period + 1:
            return None
        return sma(values[:-1], period)

    @staticmethod
    def _percent_difference(first: float | None, second: float | None) -> float | None:
        if first is None or second is None or second == 0.0:
            return None
        return (first - second) / abs(second) * 100.0

    @staticmethod
    def _percent_of(value: float | None, base: float) -> float | None:
        if value is None or base == 0.0:
            return None
        return value / abs(base) * 100.0

    @staticmethod
    def _ratio(value: float | None, base: float | None) -> float | None:
        if value is None or base is None or base == 0.0:
            return None
        return value / base

    @staticmethod
    def _signed_distance_pct(value: float, reference: float | None) -> float | None:
        if reference is None or reference == 0.0:
            return None
        return (value - reference) / abs(reference) * 100.0

    @staticmethod
    def _bollinger_width_pct(
        mid: float | None, upper: float | None, lower: float | None
    ) -> float | None:
        if mid is None or upper is None or lower is None or mid == 0.0:
            return None
        return (upper - lower) / abs(mid) * 100.0

    @staticmethod
    def _bollinger_position(
        close: float, upper: float | None, lower: float | None
    ) -> float | None:
        if upper is None or lower is None or upper == lower:
            return None
        return (close - lower) / (upper - lower)

    def _deterministic_snapshot_id(
        self,
        *,
        symbol: str,
        timeframe: str,
        observed_at: datetime,
        candle_count: int,
        last_close: float,
    ) -> str:
        key = (
            f"money-heist:{self.config.feature_version}:{symbol}:{timeframe}:"
            f"{observed_at.isoformat()}:{candle_count}:{last_close:.12g}"
        )
        return str(uuid5(NAMESPACE_URL, key))

    def _normalize_candle(self, candle: Any) -> _Candle:
        timestamp = self._read(candle, "timestamp", "open_time", "observed_at")
        open_price = self._read(candle, "open", "open_price")
        high = self._read(candle, "high", "high_price")
        low = self._read(candle, "low", "low_price")
        close = self._read(candle, "close", "close_price")
        volume = self._read(candle, "volume")
        is_closed = self._read_optional(candle, "is_closed", default=True)

        normalized = _Candle(
            timestamp=self._as_utc(self._coerce_datetime(timestamp)),
            open=self._coerce_float(open_price, "open"),
            high=self._coerce_float(high, "high"),
            low=self._coerce_float(low, "low"),
            close=self._coerce_float(close, "close"),
            volume=self._coerce_float(volume, "volume"),
            is_closed=bool(is_closed),
        )
        if normalized.high < normalized.low:
            raise ValueError("candle high must be greater than or equal to low")
        if normalized.high < max(normalized.open, normalized.close):
            raise ValueError("candle high is lower than open/close")
        if normalized.low > min(normalized.open, normalized.close):
            raise ValueError("candle low is greater than open/close")
        if normalized.volume < 0.0:
            raise ValueError("candle volume cannot be negative")
        return normalized

    @staticmethod
    def _read(candle: Any, *names: str) -> Any:
        sentinel = object()
        value = FeatureEngine._read_optional(candle, *names, default=sentinel)
        if value is sentinel:
            raise ValueError(f"candle is missing required field; expected one of {names}")
        return value

    @staticmethod
    def _read_optional(candle: Any, *names: str, default: Any) -> Any:
        if isinstance(candle, Mapping):
            for name in names:
                if name in candle:
                    return candle[name]
        else:
            for name in names:
                if hasattr(candle, name):
                    return getattr(candle, name)
        return default

    @staticmethod
    def _coerce_float(value: Any, field: str) -> float:
        number = float(value)
        if not isfinite(number):
            raise ValueError(f"candle {field} must be finite")
        return number

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise ValueError("candle timestamp must be a datetime or ISO-8601 string")

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _validate_unique_timestamps(candles: Sequence[_Candle]) -> None:
        timestamps = [candle.timestamp for candle in candles]
        if len(timestamps) != len(set(timestamps)):
            raise ValueError("duplicate candle timestamps are not allowed")
