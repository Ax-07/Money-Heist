from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from app.common.canonical import stable_digest

ANALYTICS_INDICATOR_REGISTRY_VERSION = "money-heist.analytics-indicators.v1"


class IndicatorFamily(StrEnum):
    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    STRENGTH = "strength"
    VOLUME = "volume"
    STRUCTURE = "structure"
    DERIVED = "derived"


class IndicatorOutputType(StrEnum):
    PRICE = "price"
    OSCILLATOR = "oscillator"
    HISTOGRAM = "histogram"
    METRIC = "metric"


def _freeze_parameters(values: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(sorted((values or {}).items())))


@dataclass(frozen=True, slots=True)
class IndicatorDefinition:
    indicator_id: str
    family: IndicatorFamily
    name: str
    parameters: Mapping[str, Any]
    output_type: IndicatorOutputType
    warmup_bars: int
    definition_version: str
    description: str

    def __post_init__(self) -> None:
        indicator_id = self.indicator_id.strip()
        name = self.name.strip()
        definition_version = self.definition_version.strip()
        description = self.description.strip()
        if not indicator_id:
            raise ValueError("indicator_id must not be empty")
        if not name:
            raise ValueError("name must not be empty")
        if self.warmup_bars < 1:
            raise ValueError("warmup_bars must be >= 1")
        if not definition_version:
            raise ValueError("definition_version must not be empty")
        if not description:
            raise ValueError("description must not be empty")
        object.__setattr__(self, "indicator_id", indicator_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "definition_version", definition_version)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "parameters", _freeze_parameters(self.parameters))

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "indicator_id": self.indicator_id,
            "family": self.family,
            "name": self.name,
            "parameters": self.parameters,
            "output_type": self.output_type,
            "warmup_bars": self.warmup_bars,
            "definition_version": self.definition_version,
            "description": self.description,
        }


def _def(
    indicator_id: str,
    family: IndicatorFamily,
    name: str,
    *,
    parameters: Mapping[str, Any] | None,
    output_type: IndicatorOutputType,
    warmup_bars: int,
    description: str,
    definition_version: str = "v1",
) -> IndicatorDefinition:
    return IndicatorDefinition(
        indicator_id=indicator_id,
        family=family,
        name=name,
        parameters=_freeze_parameters(parameters),
        output_type=output_type,
        warmup_bars=warmup_bars,
        definition_version=definition_version,
        description=description,
    )


INDICATOR_REGISTRY: tuple[IndicatorDefinition, ...] = (
    *(
        _def(
            f"sma_{period}",
            IndicatorFamily.TREND,
            f"SMA {period}",
            parameters={"period": period},
            output_type=IndicatorOutputType.PRICE,
            warmup_bars=period,
            description=(
                f"Simple moving average of the latest {period} closed candles, current included."
            ),
        )
        for period in (20, 50, 100, 200)
    ),
    *(
        _def(
            f"ema_{period}",
            IndicatorFamily.TREND,
            f"EMA {period}",
            parameters={"period": period, "seed": "sma"},
            output_type=IndicatorOutputType.PRICE,
            warmup_bars=period,
            description=f"EMA({period}) seeded by the first {period}-candle SMA.",
        )
        for period in (9, 20, 50, 100, 200)
    ),
    *(
        _def(
            f"ema_{period}_distance_pct",
            IndicatorFamily.DERIVED,
            f"Distance to EMA {period} %",
            parameters={"period": period, "formula": "close/ema-1"},
            output_type=IndicatorOutputType.METRIC,
            warmup_bars=period,
            description=f"Percentage distance (close / EMA{period} - 1) * 100.",
        )
        for period in (20, 50, 200)
    ),
    *(
        _def(
            f"ema_{period}_slope_pct",
            IndicatorFamily.DERIVED,
            f"EMA {period} slope %",
            parameters={"period": period, "lag": 1},
            output_type=IndicatorOutputType.METRIC,
            warmup_bars=period + 1,
            description=f"One-candle percentage change of EMA{period}.",
        )
        for period in (20, 50, 200)
    ),
    _def(
        "rsi_14",
        IndicatorFamily.MOMENTUM,
        "RSI 14",
        parameters={"period": 14, "smoothing": "wilder"},
        output_type=IndicatorOutputType.OSCILLATOR,
        warmup_bars=15,
        description="Wilder RSI over 14 close-to-close changes.",
    ),
    _def(
        "rsi_delta_14",
        IndicatorFamily.DERIVED,
        "RSI 14 delta",
        parameters={"period": 14, "lag": 1},
        output_type=IndicatorOutputType.METRIC,
        warmup_bars=16,
        description="One-candle arithmetic change in RSI 14.",
    ),
    _def(
        "stoch_rsi_k_14_14_3_3",
        IndicatorFamily.MOMENTUM,
        "Stochastic RSI %K",
        parameters={"rsi_period": 14, "stoch_period": 14, "smooth_k": 3, "smooth_d": 3},
        output_type=IndicatorOutputType.OSCILLATOR,
        warmup_bars=30,
        description="Stochastic RSI 14/14 with three-value SMA smoothing for %K.",
    ),
    _def(
        "stoch_rsi_d_14_14_3_3",
        IndicatorFamily.MOMENTUM,
        "Stochastic RSI %D",
        parameters={"rsi_period": 14, "stoch_period": 14, "smooth_k": 3, "smooth_d": 3},
        output_type=IndicatorOutputType.OSCILLATOR,
        warmup_bars=32,
        description="Three-value SMA of Stochastic RSI %K.",
    ),
    _def(
        "roc_12",
        IndicatorFamily.MOMENTUM,
        "ROC 12",
        parameters={"period": 12},
        output_type=IndicatorOutputType.OSCILLATOR,
        warmup_bars=13,
        description="Twelve-candle rate of change: (close / close[-12] - 1) * 100.",
    ),
    _def(
        "macd_12_26_9",
        IndicatorFamily.MOMENTUM,
        "MACD line 12/26/9",
        parameters={"fast": 12, "slow": 26, "signal": 9, "seed": "sma"},
        output_type=IndicatorOutputType.OSCILLATOR,
        warmup_bars=26,
        description="EMA12 minus EMA26, both SMA-seeded.",
    ),
    _def(
        "macd_signal_12_26_9",
        IndicatorFamily.MOMENTUM,
        "MACD signal 12/26/9",
        parameters={"fast": 12, "slow": 26, "signal": 9, "seed": "sma"},
        output_type=IndicatorOutputType.OSCILLATOR,
        warmup_bars=34,
        description="Nine-value SMA-seeded EMA of the MACD line.",
    ),
    _def(
        "macd_hist_12_26_9",
        IndicatorFamily.MOMENTUM,
        "MACD histogram 12/26/9",
        parameters={"fast": 12, "slow": 26, "signal": 9, "seed": "sma"},
        output_type=IndicatorOutputType.HISTOGRAM,
        warmup_bars=34,
        description="MACD line minus MACD signal.",
    ),
    _def(
        "atr_14",
        IndicatorFamily.VOLATILITY,
        "ATR 14",
        parameters={"period": 14, "smoothing": "wilder", "first_tr": "high-low"},
        output_type=IndicatorOutputType.METRIC,
        warmup_bars=14,
        description="Wilder ATR14; first true range is the first candle high-low.",
    ),
    _def(
        "atr_pct_14",
        IndicatorFamily.DERIVED,
        "ATR 14 %",
        parameters={"period": 14},
        output_type=IndicatorOutputType.METRIC,
        warmup_bars=14,
        description="ATR14 / close * 100.",
    ),
    _def(
        "bb_mid_20_2",
        IndicatorFamily.VOLATILITY,
        "Bollinger middle 20/2",
        parameters={"period": 20, "stddev_multiplier": 2.0, "ddof": 0},
        output_type=IndicatorOutputType.PRICE,
        warmup_bars=20,
        description="Twenty-candle SMA used as the Bollinger middle band.",
    ),
    _def(
        "bb_upper_20_2",
        IndicatorFamily.VOLATILITY,
        "Bollinger upper 20/2",
        parameters={"period": 20, "stddev_multiplier": 2.0, "ddof": 0},
        output_type=IndicatorOutputType.PRICE,
        warmup_bars=20,
        description="SMA20 plus two population standard deviations (ddof=0).",
    ),
    _def(
        "bb_lower_20_2",
        IndicatorFamily.VOLATILITY,
        "Bollinger lower 20/2",
        parameters={"period": 20, "stddev_multiplier": 2.0, "ddof": 0},
        output_type=IndicatorOutputType.PRICE,
        warmup_bars=20,
        description="SMA20 minus two population standard deviations (ddof=0).",
    ),
    _def(
        "bb_width_pct_20_2",
        IndicatorFamily.DERIVED,
        "Bollinger width % 20/2",
        parameters={"period": 20, "stddev_multiplier": 2.0, "ddof": 0},
        output_type=IndicatorOutputType.METRIC,
        warmup_bars=20,
        description="(upper-lower)/middle * 100.",
    ),
    _def(
        "bb_position_20_2",
        IndicatorFamily.DERIVED,
        "Bollinger position 20/2",
        parameters={"period": 20, "stddev_multiplier": 2.0, "ddof": 0},
        output_type=IndicatorOutputType.OSCILLATOR,
        warmup_bars=20,
        description="(close-lower)/(upper-lower); unavailable when the band width is zero.",
    ),
    _def(
        "adx_14",
        IndicatorFamily.STRENGTH,
        "ADX 14",
        parameters={"period": 14, "smoothing": "wilder", "initialization": "first-transition"},
        output_type=IndicatorOutputType.OSCILLATOR,
        warmup_bars=28,
        description=(
            "Wilder ADX seeded from TR/DM transitions after the first candle; "
            "intentionally differs from the production Feature Engine initialization."
        ),
    ),
    _def(
        "plus_di_14",
        IndicatorFamily.STRENGTH,
        "+DI 14",
        parameters={"period": 14, "smoothing": "wilder", "initialization": "first-transition"},
        output_type=IndicatorOutputType.OSCILLATOR,
        warmup_bars=15,
        description="Positive Directional Indicator using the Analytics first-transition DMI seed.",
    ),
    _def(
        "minus_di_14",
        IndicatorFamily.STRENGTH,
        "-DI 14",
        parameters={"period": 14, "smoothing": "wilder", "initialization": "first-transition"},
        output_type=IndicatorOutputType.OSCILLATOR,
        warmup_bars=15,
        description="Negative Directional Indicator using the Analytics first-transition DMI seed.",
    ),
    _def(
        "volume_sma_20",
        IndicatorFamily.VOLUME,
        "Volume SMA 20",
        parameters={"period": 20, "current_candle": "included"},
        output_type=IndicatorOutputType.HISTOGRAM,
        warmup_bars=20,
        description="Twenty-candle volume SMA including the current candle.",
    ),
    _def(
        "volume_ratio_20",
        IndicatorFamily.DERIVED,
        "Volume ratio 20",
        parameters={"period": 20, "denominator_current_candle": "included"},
        output_type=IndicatorOutputType.METRIC,
        warmup_bars=20,
        description=(
            "Current volume divided by the twenty-candle volume SMA that includes the current "
            "candle; intentionally differs from the production Feature Engine."
        ),
    ),
    _def(
        "obv",
        IndicatorFamily.VOLUME,
        "On-Balance Volume",
        parameters={"initial_value": 0.0},
        output_type=IndicatorOutputType.METRIC,
        warmup_bars=1,
        description=(
            "OBV initialized at zero; each later candle adds/subtracts its volume "
            "according to close direction."
        ),
    ),
    _def(
        "mfi_14",
        IndicatorFamily.VOLUME,
        "MFI 14",
        parameters={"period": 14, "price": "typical"},
        output_type=IndicatorOutputType.OSCILLATOR,
        warmup_bars=15,
        description="Money Flow Index over 14 typical-price transitions.",
    ),
    _def(
        "cmf_20",
        IndicatorFamily.VOLUME,
        "CMF 20",
        parameters={"period": 20},
        output_type=IndicatorOutputType.OSCILLATOR,
        warmup_bars=20,
        description="Chaikin Money Flow over the latest 20 candles, current included.",
    ),
    _def(
        "rolling_vwap_20",
        IndicatorFamily.VOLUME,
        "Rolling VWAP 20",
        parameters={"period": 20, "price": "typical"},
        output_type=IndicatorOutputType.PRICE,
        warmup_bars=20,
        description=(
            "Twenty-candle rolling VWAP using typical price and base volume, current included."
        ),
    ),
    *(
        _def(
            f"rolling_high_prev_{period}",
            IndicatorFamily.STRUCTURE,
            f"Previous rolling high {period}",
            parameters={"period": period, "current_candle": "excluded"},
            output_type=IndicatorOutputType.PRICE,
            warmup_bars=period + 1,
            description=(
                f"Highest high of the previous {period} closed candles; current candle excluded."
            ),
        )
        for period in (20, 50, 100)
    ),
    *(
        _def(
            f"rolling_low_prev_{period}",
            IndicatorFamily.STRUCTURE,
            f"Previous rolling low {period}",
            parameters={"period": period, "current_candle": "excluded"},
            output_type=IndicatorOutputType.PRICE,
            warmup_bars=period + 1,
            description=(
                f"Lowest low of the previous {period} closed candles; current candle excluded."
            ),
        )
        for period in (20, 50, 100)
    ),
    _def(
        "donchian_upper_20",
        IndicatorFamily.STRUCTURE,
        "Donchian upper 20",
        parameters={"period": 20, "current_candle": "excluded"},
        output_type=IndicatorOutputType.PRICE,
        warmup_bars=21,
        description="Highest high of the previous 20 closed candles; current candle excluded.",
    ),
    _def(
        "donchian_lower_20",
        IndicatorFamily.STRUCTURE,
        "Donchian lower 20",
        parameters={"period": 20, "current_candle": "excluded"},
        output_type=IndicatorOutputType.PRICE,
        warmup_bars=21,
        description="Lowest low of the previous 20 closed candles; current candle excluded.",
    ),
    _def(
        "donchian_position_20",
        IndicatorFamily.DERIVED,
        "Donchian position 20",
        parameters={"period": 20, "current_candle": "excluded"},
        output_type=IndicatorOutputType.OSCILLATOR,
        warmup_bars=21,
        description="Close position in the previous 20-candle high/low range.",
    ),
    _def(
        "distance_to_high_20_pct",
        IndicatorFamily.DERIVED,
        "Distance to previous high 20 %",
        parameters={"period": 20, "current_candle": "excluded"},
        output_type=IndicatorOutputType.METRIC,
        warmup_bars=21,
        description="(close / previous rolling high20 - 1) * 100.",
    ),
    _def(
        "distance_to_low_20_pct",
        IndicatorFamily.DERIVED,
        "Distance to previous low 20 %",
        parameters={"period": 20, "current_candle": "excluded"},
        output_type=IndicatorOutputType.METRIC,
        warmup_bars=21,
        description="(close / previous rolling low20 - 1) * 100.",
    ),
)

INDICATOR_BY_ID: Mapping[str, IndicatorDefinition] = MappingProxyType(
    {definition.indicator_id: definition for definition in INDICATOR_REGISTRY}
)
INDICATOR_IDS: tuple[str, ...] = tuple(definition.indicator_id for definition in INDICATOR_REGISTRY)

if len(INDICATOR_BY_ID) != len(INDICATOR_REGISTRY):
    raise RuntimeError("analytics indicator registry contains duplicate indicator ids")

ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT = stable_digest(
    {
        "registry_version": ANALYTICS_INDICATOR_REGISTRY_VERSION,
        "definitions": tuple(item.canonical_payload() for item in INDICATOR_REGISTRY),
    }
)
ANALYTICS_INDICATOR_REGISTRY_IDENTITY = (
    f"{ANALYTICS_INDICATOR_REGISTRY_VERSION}@sha256:{ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT}"
)


def registry_payload() -> dict[str, Any]:
    return {
        "registry_version": ANALYTICS_INDICATOR_REGISTRY_VERSION,
        "registry_fingerprint": ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT,
        "definitions": tuple(item.canonical_payload() for item in INDICATOR_REGISTRY),
    }


__all__ = [
    "ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT",
    "ANALYTICS_INDICATOR_REGISTRY_IDENTITY",
    "ANALYTICS_INDICATOR_REGISTRY_VERSION",
    "INDICATOR_BY_ID",
    "INDICATOR_IDS",
    "INDICATOR_REGISTRY",
    "IndicatorDefinition",
    "IndicatorFamily",
    "IndicatorOutputType",
    "registry_payload",
]
