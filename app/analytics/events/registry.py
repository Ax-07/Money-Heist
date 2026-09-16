from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import Any

from app.analytics.indicators.registry import INDICATOR_BY_ID
from app.common.canonical import stable_digest

ANALYTICS_TECHNICAL_EVENT_REGISTRY_VERSION = "money-heist.analytics-technical-events.v1"


class TechnicalEventFamily(StrEnum):
    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    TREND_STRENGTH = "trend_strength"
    VOLUME = "volume"
    STRUCTURE = "structure"


class TechnicalEventDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class TechnicalEventCondition(StrEnum):
    PAIR_CROSS_ABOVE = "pair_cross_above"
    PAIR_CROSS_BELOW = "pair_cross_below"
    THRESHOLD_CROSS_ABOVE = "threshold_cross_above"
    THRESHOLD_CROSS_BELOW = "threshold_cross_below"
    ENTER_BELOW = "enter_below"
    EXIT_BELOW = "exit_below"
    ENTER_ABOVE = "enter_above"
    EXIT_ABOVE = "exit_above"
    ENTER_AT_OR_ABOVE = "enter_at_or_above"


def _freeze_parameters(values: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(sorted((values or {}).items())))


@dataclass(frozen=True, slots=True)
class TechnicalEventDefinition:
    event_type: str
    family: TechnicalEventFamily
    direction: TechnicalEventDirection
    required_indicators: tuple[str, ...]
    condition: TechnicalEventCondition
    parameters: Mapping[str, Any]
    definition_version: str
    description: str

    def __post_init__(self) -> None:
        event_type = self.event_type.strip()
        definition_version = self.definition_version.strip()
        description = self.description.strip()
        if not event_type:
            raise ValueError("event_type must not be empty")
        if not definition_version:
            raise ValueError("definition_version must not be empty")
        if not description:
            raise ValueError("description must not be empty")
        if not self.required_indicators:
            raise ValueError("required_indicators must not be empty")
        if len(set(self.required_indicators)) != len(self.required_indicators):
            raise ValueError("required_indicators must not contain duplicates")
        unknown = tuple(item for item in self.required_indicators if item not in INDICATOR_BY_ID)
        if unknown:
            raise ValueError(f"unknown required analytics indicators: {unknown!r}")

        pair_conditions = {
            TechnicalEventCondition.PAIR_CROSS_ABOVE,
            TechnicalEventCondition.PAIR_CROSS_BELOW,
        }
        if self.condition in pair_conditions and len(self.required_indicators) != 2:
            raise ValueError("pair crossover conditions require exactly two indicators")
        if self.condition not in pair_conditions and len(self.required_indicators) != 1:
            raise ValueError("threshold conditions require exactly one indicator")

        parameters = _freeze_parameters(self.parameters)
        if self.condition not in pair_conditions:
            if "threshold" not in parameters:
                raise ValueError("threshold conditions require a threshold parameter")
            threshold = parameters["threshold"]
            if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
                raise ValueError("threshold must be numeric")
            if not isfinite(float(threshold)):
                raise ValueError("threshold must be finite")

        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "definition_version", definition_version)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "parameters", parameters)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "family": self.family,
            "direction": self.direction,
            "required_indicators": self.required_indicators,
            "condition": self.condition,
            "parameters": self.parameters,
            "definition_version": self.definition_version,
            "description": self.description,
        }


def _event(
    event_type: str,
    family: TechnicalEventFamily,
    direction: TechnicalEventDirection,
    required_indicators: tuple[str, ...],
    condition: TechnicalEventCondition,
    *,
    parameters: Mapping[str, Any] | None = None,
    description: str,
    definition_version: str = "v1",
) -> TechnicalEventDefinition:
    return TechnicalEventDefinition(
        event_type=event_type,
        family=family,
        direction=direction,
        required_indicators=required_indicators,
        condition=condition,
        parameters=_freeze_parameters(parameters),
        definition_version=definition_version,
        description=description,
    )


TECHNICAL_EVENT_REGISTRY: tuple[TechnicalEventDefinition, ...] = (
    _event(
        "EMA_9_CROSS_ABOVE_EMA_20",
        TechnicalEventFamily.TREND,
        TechnicalEventDirection.BULLISH,
        ("ema_9", "ema_20"),
        TechnicalEventCondition.PAIR_CROSS_ABOVE,
        description="EMA9 crosses from at-or-below EMA20 to strictly above EMA20.",
    ),
    _event(
        "EMA_9_CROSS_BELOW_EMA_20",
        TechnicalEventFamily.TREND,
        TechnicalEventDirection.BEARISH,
        ("ema_9", "ema_20"),
        TechnicalEventCondition.PAIR_CROSS_BELOW,
        description="EMA9 crosses from at-or-above EMA20 to strictly below EMA20.",
    ),
    _event(
        "EMA_20_CROSS_ABOVE_EMA_50",
        TechnicalEventFamily.TREND,
        TechnicalEventDirection.BULLISH,
        ("ema_20", "ema_50"),
        TechnicalEventCondition.PAIR_CROSS_ABOVE,
        description="EMA20 crosses from at-or-below EMA50 to strictly above EMA50.",
    ),
    _event(
        "EMA_20_CROSS_BELOW_EMA_50",
        TechnicalEventFamily.TREND,
        TechnicalEventDirection.BEARISH,
        ("ema_20", "ema_50"),
        TechnicalEventCondition.PAIR_CROSS_BELOW,
        description="EMA20 crosses from at-or-above EMA50 to strictly below EMA50.",
    ),
    _event(
        "EMA_50_CROSS_ABOVE_EMA_200",
        TechnicalEventFamily.TREND,
        TechnicalEventDirection.BULLISH,
        ("ema_50", "ema_200"),
        TechnicalEventCondition.PAIR_CROSS_ABOVE,
        description="EMA50 crosses from at-or-below EMA200 to strictly above EMA200.",
    ),
    _event(
        "EMA_50_CROSS_BELOW_EMA_200",
        TechnicalEventFamily.TREND,
        TechnicalEventDirection.BEARISH,
        ("ema_50", "ema_200"),
        TechnicalEventCondition.PAIR_CROSS_BELOW,
        description="EMA50 crosses from at-or-above EMA200 to strictly below EMA200.",
    ),
    _event(
        "PRICE_CROSS_ABOVE_EMA_200",
        TechnicalEventFamily.TREND,
        TechnicalEventDirection.BULLISH,
        ("ema_200_distance_pct",),
        TechnicalEventCondition.THRESHOLD_CROSS_ABOVE,
        parameters={"threshold": 0.0},
        description="Close crosses EMA200 upward, observed through Analytics EMA200 distance %.",
    ),
    _event(
        "PRICE_CROSS_BELOW_EMA_200",
        TechnicalEventFamily.TREND,
        TechnicalEventDirection.BEARISH,
        ("ema_200_distance_pct",),
        TechnicalEventCondition.THRESHOLD_CROSS_BELOW,
        parameters={"threshold": 0.0},
        description="Close crosses EMA200 downward, observed through Analytics EMA200 distance %.",
    ),
    _event(
        "RSI_14_ENTER_OVERSOLD",
        TechnicalEventFamily.MOMENTUM,
        TechnicalEventDirection.BEARISH,
        ("rsi_14",),
        TechnicalEventCondition.ENTER_BELOW,
        parameters={"threshold": 30.0},
        description="RSI14 enters the strictly-below-30 state.",
    ),
    _event(
        "RSI_14_EXIT_OVERSOLD",
        TechnicalEventFamily.MOMENTUM,
        TechnicalEventDirection.BULLISH,
        ("rsi_14",),
        TechnicalEventCondition.EXIT_BELOW,
        parameters={"threshold": 30.0},
        description="RSI14 exits the below-30 state at or above 30.",
    ),
    _event(
        "RSI_14_CROSS_ABOVE_50",
        TechnicalEventFamily.MOMENTUM,
        TechnicalEventDirection.BULLISH,
        ("rsi_14",),
        TechnicalEventCondition.THRESHOLD_CROSS_ABOVE,
        parameters={"threshold": 50.0},
        description="RSI14 crosses from at-or-below 50 to strictly above 50.",
    ),
    _event(
        "RSI_14_CROSS_BELOW_50",
        TechnicalEventFamily.MOMENTUM,
        TechnicalEventDirection.BEARISH,
        ("rsi_14",),
        TechnicalEventCondition.THRESHOLD_CROSS_BELOW,
        parameters={"threshold": 50.0},
        description="RSI14 crosses from at-or-above 50 to strictly below 50.",
    ),
    _event(
        "RSI_14_ENTER_OVERBOUGHT",
        TechnicalEventFamily.MOMENTUM,
        TechnicalEventDirection.BULLISH,
        ("rsi_14",),
        TechnicalEventCondition.ENTER_ABOVE,
        parameters={"threshold": 70.0},
        description="RSI14 enters the strictly-above-70 state.",
    ),
    _event(
        "RSI_14_EXIT_OVERBOUGHT",
        TechnicalEventFamily.MOMENTUM,
        TechnicalEventDirection.BEARISH,
        ("rsi_14",),
        TechnicalEventCondition.EXIT_ABOVE,
        parameters={"threshold": 70.0},
        description="RSI14 exits the above-70 state at or below 70.",
    ),
    _event(
        "MACD_CROSS_ABOVE_SIGNAL",
        TechnicalEventFamily.MOMENTUM,
        TechnicalEventDirection.BULLISH,
        ("macd_12_26_9", "macd_signal_12_26_9"),
        TechnicalEventCondition.PAIR_CROSS_ABOVE,
        description="MACD 12/26/9 line crosses above its signal line.",
    ),
    _event(
        "MACD_CROSS_BELOW_SIGNAL",
        TechnicalEventFamily.MOMENTUM,
        TechnicalEventDirection.BEARISH,
        ("macd_12_26_9", "macd_signal_12_26_9"),
        TechnicalEventCondition.PAIR_CROSS_BELOW,
        description="MACD 12/26/9 line crosses below its signal line.",
    ),
    _event(
        "MACD_HISTOGRAM_CROSS_ABOVE_ZERO",
        TechnicalEventFamily.MOMENTUM,
        TechnicalEventDirection.BULLISH,
        ("macd_hist_12_26_9",),
        TechnicalEventCondition.THRESHOLD_CROSS_ABOVE,
        parameters={"threshold": 0.0},
        description="MACD histogram crosses from zero-or-negative to strictly positive.",
    ),
    _event(
        "MACD_HISTOGRAM_CROSS_BELOW_ZERO",
        TechnicalEventFamily.MOMENTUM,
        TechnicalEventDirection.BEARISH,
        ("macd_hist_12_26_9",),
        TechnicalEventCondition.THRESHOLD_CROSS_BELOW,
        parameters={"threshold": 0.0},
        description="MACD histogram crosses from zero-or-positive to strictly negative.",
    ),
    _event(
        "ROC_12_CROSS_ABOVE_ZERO",
        TechnicalEventFamily.MOMENTUM,
        TechnicalEventDirection.BULLISH,
        ("roc_12",),
        TechnicalEventCondition.THRESHOLD_CROSS_ABOVE,
        parameters={"threshold": 0.0},
        description="ROC12 crosses from zero-or-negative to strictly positive.",
    ),
    _event(
        "ROC_12_CROSS_BELOW_ZERO",
        TechnicalEventFamily.MOMENTUM,
        TechnicalEventDirection.BEARISH,
        ("roc_12",),
        TechnicalEventCondition.THRESHOLD_CROSS_BELOW,
        parameters={"threshold": 0.0},
        description="ROC12 crosses from zero-or-positive to strictly negative.",
    ),
    _event(
        "ADX_14_CROSS_ABOVE_25",
        TechnicalEventFamily.TREND_STRENGTH,
        TechnicalEventDirection.NEUTRAL,
        ("adx_14",),
        TechnicalEventCondition.THRESHOLD_CROSS_ABOVE,
        parameters={"threshold": 25.0},
        description="Analytics ADX14 crosses from at-or-below 25 to strictly above 25.",
    ),
    _event(
        "ADX_14_CROSS_BELOW_25",
        TechnicalEventFamily.TREND_STRENGTH,
        TechnicalEventDirection.NEUTRAL,
        ("adx_14",),
        TechnicalEventCondition.THRESHOLD_CROSS_BELOW,
        parameters={"threshold": 25.0},
        description="Analytics ADX14 crosses from at-or-above 25 to strictly below 25.",
    ),
    _event(
        "PLUS_DI_CROSS_ABOVE_MINUS_DI",
        TechnicalEventFamily.TREND_STRENGTH,
        TechnicalEventDirection.BULLISH,
        ("plus_di_14", "minus_di_14"),
        TechnicalEventCondition.PAIR_CROSS_ABOVE,
        description="Analytics +DI14 crosses above Analytics -DI14.",
    ),
    _event(
        "PLUS_DI_CROSS_BELOW_MINUS_DI",
        TechnicalEventFamily.TREND_STRENGTH,
        TechnicalEventDirection.BEARISH,
        ("plus_di_14", "minus_di_14"),
        TechnicalEventCondition.PAIR_CROSS_BELOW,
        description="Analytics +DI14 crosses below Analytics -DI14.",
    ),
    _event(
        "PRICE_BREAK_ABOVE_BOLLINGER_UPPER",
        TechnicalEventFamily.VOLATILITY,
        TechnicalEventDirection.BULLISH,
        ("bb_position_20_2",),
        TechnicalEventCondition.ENTER_ABOVE,
        parameters={"threshold": 1.0},
        description="Close enters above the Analytics Bollinger upper band (position > 1).",
    ),
    _event(
        "PRICE_RETURN_INSIDE_FROM_ABOVE_BOLLINGER",
        TechnicalEventFamily.VOLATILITY,
        TechnicalEventDirection.BEARISH,
        ("bb_position_20_2",),
        TechnicalEventCondition.EXIT_ABOVE,
        parameters={"threshold": 1.0},
        description="Close returns to or below the Analytics Bollinger upper band.",
    ),
    _event(
        "PRICE_BREAK_BELOW_BOLLINGER_LOWER",
        TechnicalEventFamily.VOLATILITY,
        TechnicalEventDirection.BEARISH,
        ("bb_position_20_2",),
        TechnicalEventCondition.ENTER_BELOW,
        parameters={"threshold": 0.0},
        description="Close enters below the Analytics Bollinger lower band (position < 0).",
    ),
    _event(
        "PRICE_RETURN_INSIDE_FROM_BELOW_BOLLINGER",
        TechnicalEventFamily.VOLATILITY,
        TechnicalEventDirection.BULLISH,
        ("bb_position_20_2",),
        TechnicalEventCondition.EXIT_BELOW,
        parameters={"threshold": 0.0},
        description="Close returns to or above the Analytics Bollinger lower band.",
    ),
    _event(
        "PRICE_BREAK_ABOVE_DONCHIAN_20",
        TechnicalEventFamily.STRUCTURE,
        TechnicalEventDirection.BULLISH,
        ("distance_to_high_20_pct",),
        TechnicalEventCondition.THRESHOLD_CROSS_ABOVE,
        parameters={"threshold": 0.0},
        description="Close crosses above the previous 20-candle Analytics Donchian upper bound.",
    ),
    _event(
        "PRICE_BREAK_BELOW_DONCHIAN_20",
        TechnicalEventFamily.STRUCTURE,
        TechnicalEventDirection.BEARISH,
        ("distance_to_low_20_pct",),
        TechnicalEventCondition.THRESHOLD_CROSS_BELOW,
        parameters={"threshold": 0.0},
        description="Close crosses below the previous 20-candle Analytics Donchian lower bound.",
    ),
    _event(
        "VOLUME_SPIKE_20",
        TechnicalEventFamily.VOLUME,
        TechnicalEventDirection.NEUTRAL,
        ("volume_ratio_20",),
        TechnicalEventCondition.ENTER_AT_OR_ABOVE,
        parameters={"threshold": 1.5},
        description="Analytics volume_ratio_20 enters the >= 1.5 state.",
    ),
    _event(
        "MFI_14_ENTER_OVERSOLD",
        TechnicalEventFamily.VOLUME,
        TechnicalEventDirection.BEARISH,
        ("mfi_14",),
        TechnicalEventCondition.ENTER_BELOW,
        parameters={"threshold": 20.0},
        description="MFI14 enters the strictly-below-20 state.",
    ),
    _event(
        "MFI_14_EXIT_OVERSOLD",
        TechnicalEventFamily.VOLUME,
        TechnicalEventDirection.BULLISH,
        ("mfi_14",),
        TechnicalEventCondition.EXIT_BELOW,
        parameters={"threshold": 20.0},
        description="MFI14 exits the below-20 state at or above 20.",
    ),
    _event(
        "MFI_14_ENTER_OVERBOUGHT",
        TechnicalEventFamily.VOLUME,
        TechnicalEventDirection.BULLISH,
        ("mfi_14",),
        TechnicalEventCondition.ENTER_ABOVE,
        parameters={"threshold": 80.0},
        description="MFI14 enters the strictly-above-80 state.",
    ),
    _event(
        "MFI_14_EXIT_OVERBOUGHT",
        TechnicalEventFamily.VOLUME,
        TechnicalEventDirection.BEARISH,
        ("mfi_14",),
        TechnicalEventCondition.EXIT_ABOVE,
        parameters={"threshold": 80.0},
        description="MFI14 exits the above-80 state at or below 80.",
    ),
)

TECHNICAL_EVENT_BY_TYPE: Mapping[str, TechnicalEventDefinition] = MappingProxyType(
    {definition.event_type: definition for definition in TECHNICAL_EVENT_REGISTRY}
)
TECHNICAL_EVENT_TYPES: tuple[str, ...] = tuple(
    definition.event_type for definition in TECHNICAL_EVENT_REGISTRY
)

if len(TECHNICAL_EVENT_BY_TYPE) != len(TECHNICAL_EVENT_REGISTRY):
    raise RuntimeError("analytics technical event registry contains duplicate event types")

ANALYTICS_TECHNICAL_EVENT_REGISTRY_FINGERPRINT = stable_digest(
    {
        "registry_version": ANALYTICS_TECHNICAL_EVENT_REGISTRY_VERSION,
        "definitions": tuple(item.canonical_payload() for item in TECHNICAL_EVENT_REGISTRY),
    }
)
ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY = (
    f"{ANALYTICS_TECHNICAL_EVENT_REGISTRY_VERSION}"
    f"@sha256:{ANALYTICS_TECHNICAL_EVENT_REGISTRY_FINGERPRINT}"
)


def registry_payload() -> dict[str, Any]:
    return {
        "registry_version": ANALYTICS_TECHNICAL_EVENT_REGISTRY_VERSION,
        "registry_fingerprint": ANALYTICS_TECHNICAL_EVENT_REGISTRY_FINGERPRINT,
        "definitions": tuple(item.canonical_payload() for item in TECHNICAL_EVENT_REGISTRY),
    }


__all__ = [
    "ANALYTICS_TECHNICAL_EVENT_REGISTRY_FINGERPRINT",
    "ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY",
    "ANALYTICS_TECHNICAL_EVENT_REGISTRY_VERSION",
    "TECHNICAL_EVENT_BY_TYPE",
    "TECHNICAL_EVENT_REGISTRY",
    "TECHNICAL_EVENT_TYPES",
    "TechnicalEventCondition",
    "TechnicalEventDefinition",
    "TechnicalEventDirection",
    "TechnicalEventFamily",
    "registry_payload",
]
