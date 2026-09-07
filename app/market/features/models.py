from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MarketRegime(StrEnum):
    """Coarse deterministic regime used as compact context, not as a trade signal."""

    BULLISH_TREND = "bullish_trend"
    BEARISH_TREND = "bearish_trend"
    RANGE = "range"
    UNKNOWN = "unknown"


FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
OptionalFiniteFloat = Annotated[float | None, Field(default=None, allow_inf_nan=False)]


class FeatureQuality(BaseModel):
    """Quality metadata attached to every feature snapshot."""

    model_config = ConfigDict(frozen=True)

    warmup_complete: bool
    closed_candle_count: int = Field(ge=0)
    missing_features: tuple[str, ...] = ()
    ignored_open_candles: int = Field(default=0, ge=0)


class FeatureSnapshot(BaseModel):
    """Compact deterministic representation of a candle history.

    The object deliberately contains no LONG/SHORT recommendation. It is safe to
    pass to the deterministic scanner and later to the AI layer as market context.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    feature_version: str
    snapshot_id: str
    source_snapshot_id: str | None = None
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    observed_at: datetime
    candle_count: int = Field(ge=1)

    close: FiniteFloat
    ema_fast: OptionalFiniteFloat = None
    ema_slow: OptionalFiniteFloat = None
    ema_spread_pct: OptionalFiniteFloat = None
    rsi_14: OptionalFiniteFloat = None
    macd_line: OptionalFiniteFloat = None
    macd_signal: OptionalFiniteFloat = None
    macd_histogram: OptionalFiniteFloat = None
    atr_14: OptionalFiniteFloat = None
    atr_pct: OptionalFiniteFloat = None
    atr_expansion_ratio: OptionalFiniteFloat = None
    adx_14: OptionalFiniteFloat = None
    bollinger_mid: OptionalFiniteFloat = None
    bollinger_upper: OptionalFiniteFloat = None
    bollinger_lower: OptionalFiniteFloat = None
    bollinger_width_pct: OptionalFiniteFloat = None
    bollinger_position: OptionalFiniteFloat = None
    volume_sma_20: OptionalFiniteFloat = None
    volume_ratio: OptionalFiniteFloat = None
    realized_volatility_20_pct: OptionalFiniteFloat = None
    prior_range_high_20: OptionalFiniteFloat = None
    prior_range_low_20: OptionalFiniteFloat = None
    distance_to_range_high_pct: OptionalFiniteFloat = None
    distance_to_range_low_pct: OptionalFiniteFloat = None
    regime: MarketRegime = MarketRegime.UNKNOWN
    quality: FeatureQuality

    @field_validator("observed_at")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
