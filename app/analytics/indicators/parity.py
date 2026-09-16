from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ParityStatus(StrEnum):
    SAME_SEMANTICS = "same_semantics"
    COMPATIBLE_SEMANTICS = "compatible_semantics"
    INTENTIONAL_DIVERGENCE = "intentional_divergence"
    ANALYTICS_ONLY = "analytics_only"
    NOT_COMPARABLE = "not_comparable"


@dataclass(frozen=True, slots=True)
class IndicatorParityEntry:
    indicator_id: str
    feature_engine: bool
    analytics_lab: bool
    btc_analytics_v1: bool
    status: ParityStatus
    notes: str


PARITY_CATALOGUE: tuple[IndicatorParityEntry, ...] = (
    IndicatorParityEntry(
        "ema_20",
        True,
        True,
        True,
        ParityStatus.SAME_SEMANTICS,
        "EMA uses alpha=2/(N+1) and a first-SMA seed in both engines.",
    ),
    IndicatorParityEntry(
        "rsi_14",
        True,
        True,
        True,
        ParityStatus.SAME_SEMANTICS,
        (
            "Wilder averages are seeded from the first 14 close changes; flat seed "
            "resolves to RSI=50."
        ),
    ),
    IndicatorParityEntry(
        "macd_12_26_9",
        True,
        True,
        True,
        ParityStatus.SAME_SEMANTICS,
        "SMA-seeded EMA12/EMA26 and SMA-seeded EMA9 signal.",
    ),
    IndicatorParityEntry(
        "atr_14",
        True,
        True,
        True,
        ParityStatus.SAME_SEMANTICS,
        ("First TR is first candle high-low; subsequent TR uses previous close; Wilder smoothing."),
    ),
    IndicatorParityEntry(
        "bb_mid_20_2",
        True,
        True,
        True,
        ParityStatus.SAME_SEMANTICS,
        "SMA20 with population standard deviation (ddof=0).",
    ),
    IndicatorParityEntry(
        "bb_upper_20_2",
        True,
        True,
        True,
        ParityStatus.SAME_SEMANTICS,
        "Middle + 2 population standard deviations.",
    ),
    IndicatorParityEntry(
        "bb_lower_20_2",
        True,
        True,
        True,
        ParityStatus.SAME_SEMANTICS,
        "Middle - 2 population standard deviations.",
    ),
    IndicatorParityEntry(
        "adx_14",
        True,
        True,
        True,
        ParityStatus.INTENTIONAL_DIVERGENCE,
        (
            "Production Feature Engine seeds TR/DM with the first candle (DM+=DM-=0); "
            "Analytics follows btc_analytics_v1 and starts TR/DM on the first transition."
        ),
    ),
    IndicatorParityEntry(
        "plus_di_14",
        False,
        True,
        True,
        ParityStatus.ANALYTICS_ONLY,
        (
            "Typed DMI output is exposed by Analytics but not by the production "
            "FeatureSnapshot contract."
        ),
    ),
    IndicatorParityEntry(
        "minus_di_14",
        False,
        True,
        True,
        ParityStatus.ANALYTICS_ONLY,
        (
            "Typed DMI output is exposed by Analytics but not by the production "
            "FeatureSnapshot contract."
        ),
    ),
    IndicatorParityEntry(
        "volume_sma_20",
        True,
        True,
        True,
        ParityStatus.INTENTIONAL_DIVERGENCE,
        (
            "Production volume SMA is the previous 20 volumes; Analytics/btc_analytics_v1 "
            "include current volume."
        ),
    ),
    IndicatorParityEntry(
        "volume_ratio_20",
        True,
        True,
        True,
        ParityStatus.INTENTIONAL_DIVERGENCE,
        (
            "Production divides current volume by the previous-20 SMA; "
            "Analytics/btc_analytics_v1 divide by a 20-candle SMA including current."
        ),
    ),
    IndicatorParityEntry(
        "rolling_high_prev_20",
        True,
        True,
        True,
        ParityStatus.COMPATIBLE_SEMANTICS,
        ("Equivalent to production prior_range_high_20: previous 20 highs, current excluded."),
    ),
    IndicatorParityEntry(
        "rolling_low_prev_20",
        True,
        True,
        True,
        ParityStatus.COMPATIBLE_SEMANTICS,
        ("Equivalent to production prior_range_low_20: previous 20 lows, current excluded."),
    ),
    IndicatorParityEntry(
        "donchian_upper_20",
        True,
        True,
        True,
        ParityStatus.COMPATIBLE_SEMANTICS,
        ("Numerically equivalent to production prior-range high20; naming/purpose differs."),
    ),
    IndicatorParityEntry(
        "donchian_lower_20",
        True,
        True,
        True,
        ParityStatus.COMPATIBLE_SEMANTICS,
        ("Numerically equivalent to production prior-range low20; naming/purpose differs."),
    ),
    IndicatorParityEntry(
        "stoch_rsi_k_14_14_3_3",
        False,
        True,
        True,
        ParityStatus.ANALYTICS_ONLY,
        "No production FeatureSnapshot equivalent.",
    ),
    IndicatorParityEntry(
        "stoch_rsi_d_14_14_3_3",
        False,
        True,
        True,
        ParityStatus.ANALYTICS_ONLY,
        "No production FeatureSnapshot equivalent.",
    ),
    IndicatorParityEntry(
        "roc_12",
        False,
        True,
        True,
        ParityStatus.ANALYTICS_ONLY,
        "No production FeatureSnapshot equivalent.",
    ),
    IndicatorParityEntry(
        "obv",
        False,
        True,
        True,
        ParityStatus.ANALYTICS_ONLY,
        "No production FeatureSnapshot equivalent.",
    ),
    IndicatorParityEntry(
        "mfi_14",
        False,
        True,
        True,
        ParityStatus.ANALYTICS_ONLY,
        "No production FeatureSnapshot equivalent.",
    ),
    IndicatorParityEntry(
        "cmf_20",
        False,
        True,
        True,
        ParityStatus.ANALYTICS_ONLY,
        "No production FeatureSnapshot equivalent.",
    ),
    IndicatorParityEntry(
        "rolling_vwap_20",
        False,
        True,
        True,
        ParityStatus.ANALYTICS_ONLY,
        "No production FeatureSnapshot equivalent.",
    ),
)

PARITY_BY_INDICATOR = {entry.indicator_id: entry for entry in PARITY_CATALOGUE}


__all__ = [
    "IndicatorParityEntry",
    "PARITY_BY_INDICATOR",
    "PARITY_CATALOGUE",
    "ParityStatus",
]
