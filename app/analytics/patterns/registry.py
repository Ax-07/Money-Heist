from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.common.canonical import stable_digest

ANALYTICS_PATTERN_REGISTRY_VERSION = "money-heist.pattern-registry.p5-adapted.v1"
ANALYTICS_PATTERN_INTRABAR_POLICY_VERSION = "money-heist.pattern-intrabar-conservative.v1"

DOUBLE_MIN_SPACING_BARS = 5
DOUBLE_MAX_SPACING_BARS = 120
DOUBLE_MAX_LEVEL_MISMATCH_ATR = 1.0
DOUBLE_MIN_DEPTH_ATR = 1.25
HS_MAX_SHOULDER_MISMATCH_ATR = 1.25
HS_MAX_NECKLINE_MISMATCH_ATR = 1.5
HS_MIN_HEAD_PROMINENCE_ATR = 1.0
HS_MIN_TIME_SYMMETRY = 0.35
HS_MAX_TIME_SYMMETRY = 2.85
GEOMETRY_MIN_DURATION_BARS = 10
GEOMETRY_MAX_DURATION_BARS = 180
GEOMETRY_MAX_LINE_ERROR_ATR = 0.65
GEOMETRY_FLAT_SLOPE_ATR_PER_BAR = 0.035
GEOMETRY_PARALLEL_SLOPE_ATR_PER_BAR = 0.045
GEOMETRY_MIN_WIDTH_ATR = 1.5
GEOMETRY_MAX_CONVERGENCE_RATIO = 0.80
GEOMETRY_CHANNEL_MIN_WIDTH_RATIO = 0.65
GEOMETRY_CHANNEL_MAX_WIDTH_RATIO = 1.35
GEOMETRY_MAX_APEX_MULTIPLE = 4.0
BREAKOUT_BUFFER_ATR = 0.10
MAX_LOOKAHEAD_MIN_BARS = 12
MAX_LOOKAHEAD_MAX_BARS = 90
POST_CONFIRM_INVALIDATION_MIN_BARS = 6
POST_CONFIRM_INVALIDATION_MAX_BARS = 30
OVERLAP_SUPPRESSION_RATIO = 0.72
PRIOR_TREND_LOOKBACK = 30
PRIOR_TREND_MIN_BARS = 8
PRIOR_TREND_MIN_DISPLACEMENT_ATR = 1.5


class PatternType(StrEnum):
    DOUBLE_TOP = "DOUBLE_TOP"
    DOUBLE_BOTTOM = "DOUBLE_BOTTOM"
    HEAD_AND_SHOULDERS = "HEAD_AND_SHOULDERS"
    INVERSE_HEAD_AND_SHOULDERS = "INVERSE_HEAD_AND_SHOULDERS"
    ASCENDING_TRIANGLE = "ASCENDING_TRIANGLE"
    DESCENDING_TRIANGLE = "DESCENDING_TRIANGLE"
    SYMMETRICAL_TRIANGLE = "SYMMETRICAL_TRIANGLE"
    RISING_WEDGE = "RISING_WEDGE"
    FALLING_WEDGE = "FALLING_WEDGE"
    ASCENDING_CHANNEL = "ASCENDING_CHANNEL"
    DESCENDING_CHANNEL = "DESCENDING_CHANNEL"
    RANGE = "RANGE"


class PatternFamily(StrEnum):
    REVERSAL = "REVERSAL"
    CONSOLIDATION = "CONSOLIDATION"
    CHANNEL = "CHANNEL"
    RANGE = "RANGE"


@dataclass(frozen=True, slots=True)
class PatternDefinition:
    pattern_type: PatternType
    family: PatternFamily
    minimum_pivots: int
    pivot_sequence: tuple[str, ...] | None
    geometry_constraints: tuple[str, ...]
    atr_normalization_rules: tuple[str, ...]
    trend_constraints: tuple[str, ...]
    breakout_semantics: str
    lifecycle_rules: tuple[str, ...]
    source_requirements: tuple[str, ...]
    parameter_names: tuple[str, ...]
    experimental: bool = True
    definition_version: str = ANALYTICS_PATTERN_REGISTRY_VERSION


_COMMON_ATR = (
    "geometry thresholds are expressed as ATR multiples or ATR-normalized slopes",
    "ATR is evaluated causally from closed candles",
)
_COMMON_BREAKOUT = "closed candle close beyond boundary plus BREAKOUT_BUFFER_ATR"
_COMMON_LIFECYCLE = (
    "FORMING at max(source pivot confirmed_at)",
    "CONFIRMED at first causal close breakout",
    "FAILED on pre-confirmation structural break or timeout",
    "INVALIDATED on post-confirmation close re-entry",
)
_COMMON_SOURCE = (
    "single pivot source per computation",
    "pivot confirmed_at must be <= as_of",
    "closed-candle context only",
)


def _reversal_definition(
    pattern_type: PatternType,
    sequence: tuple[str, ...],
    geometry: tuple[str, ...],
    parameters: tuple[str, ...],
) -> PatternDefinition:
    return PatternDefinition(
        pattern_type=pattern_type,
        family=PatternFamily.REVERSAL,
        minimum_pivots=len(sequence),
        pivot_sequence=sequence,
        geometry_constraints=geometry,
        atr_normalization_rules=_COMMON_ATR,
        trend_constraints=(
            "expected prior reversal trend or unknown when history is insufficient",
        ),
        breakout_semantics=_COMMON_BREAKOUT,
        lifecycle_rules=_COMMON_LIFECYCLE,
        source_requirements=_COMMON_SOURCE,
        parameter_names=parameters,
    )


def _geometry_definition(
    pattern_type: PatternType,
    family: PatternFamily,
    geometry: tuple[str, ...],
) -> PatternDefinition:
    return PatternDefinition(
        pattern_type=pattern_type,
        family=family,
        minimum_pivots=6,
        pivot_sequence=None,
        geometry_constraints=geometry,
        atr_normalization_rules=_COMMON_ATR,
        trend_constraints=(),
        breakout_semantics=_COMMON_BREAKOUT,
        lifecycle_rules=_COMMON_LIFECYCLE,
        source_requirements=_COMMON_SOURCE,
        parameter_names=(
            "GEOMETRY_MIN_DURATION_BARS",
            "GEOMETRY_MAX_DURATION_BARS",
            "GEOMETRY_MAX_LINE_ERROR_ATR",
            "GEOMETRY_MIN_WIDTH_ATR",
            "BREAKOUT_BUFFER_ATR",
        ),
    )


PATTERN_DEFINITIONS = (
    _reversal_definition(
        PatternType.DOUBLE_TOP,
        ("HIGH", "LOW", "HIGH"),
        ("outer highs similar", "intermediate trough deep enough"),
        (
            "DOUBLE_MIN_SPACING_BARS",
            "DOUBLE_MAX_SPACING_BARS",
            "DOUBLE_MAX_LEVEL_MISMATCH_ATR",
            "DOUBLE_MIN_DEPTH_ATR",
            "BREAKOUT_BUFFER_ATR",
        ),
    ),
    _reversal_definition(
        PatternType.DOUBLE_BOTTOM,
        ("LOW", "HIGH", "LOW"),
        ("outer lows similar", "intermediate peak high enough"),
        (
            "DOUBLE_MIN_SPACING_BARS",
            "DOUBLE_MAX_SPACING_BARS",
            "DOUBLE_MAX_LEVEL_MISMATCH_ATR",
            "DOUBLE_MIN_DEPTH_ATR",
            "BREAKOUT_BUFFER_ATR",
        ),
    ),
    _reversal_definition(
        PatternType.HEAD_AND_SHOULDERS,
        ("HIGH", "LOW", "HIGH", "LOW", "HIGH"),
        ("head prominent", "shoulders similar", "neckline points compatible"),
        (
            "HS_MAX_SHOULDER_MISMATCH_ATR",
            "HS_MAX_NECKLINE_MISMATCH_ATR",
            "HS_MIN_HEAD_PROMINENCE_ATR",
            "HS_MIN_TIME_SYMMETRY",
            "HS_MAX_TIME_SYMMETRY",
            "BREAKOUT_BUFFER_ATR",
        ),
    ),
    _reversal_definition(
        PatternType.INVERSE_HEAD_AND_SHOULDERS,
        ("LOW", "HIGH", "LOW", "HIGH", "LOW"),
        ("head prominent", "shoulders similar", "neckline points compatible"),
        (
            "HS_MAX_SHOULDER_MISMATCH_ATR",
            "HS_MAX_NECKLINE_MISMATCH_ATR",
            "HS_MIN_HEAD_PROMINENCE_ATR",
            "HS_MIN_TIME_SYMMETRY",
            "HS_MAX_TIME_SYMMETRY",
            "BREAKOUT_BUFFER_ATR",
        ),
    ),
    _geometry_definition(
        PatternType.ASCENDING_TRIANGLE,
        PatternFamily.CONSOLIDATION,
        ("upper line flat", "lower line rising", "bounds converging"),
    ),
    _geometry_definition(
        PatternType.DESCENDING_TRIANGLE,
        PatternFamily.CONSOLIDATION,
        ("upper line falling", "lower line flat", "bounds converging"),
    ),
    _geometry_definition(
        PatternType.SYMMETRICAL_TRIANGLE,
        PatternFamily.CONSOLIDATION,
        ("upper line falling", "lower line rising", "bounds converging"),
    ),
    _geometry_definition(
        PatternType.RISING_WEDGE,
        PatternFamily.CONSOLIDATION,
        ("both lines rising", "lower slope steeper", "bounds converging"),
    ),
    _geometry_definition(
        PatternType.FALLING_WEDGE,
        PatternFamily.CONSOLIDATION,
        ("both lines falling", "upper slope steeper", "bounds converging"),
    ),
    _geometry_definition(
        PatternType.ASCENDING_CHANNEL,
        PatternFamily.CHANNEL,
        ("both lines rising", "slopes approximately parallel", "width stable"),
    ),
    _geometry_definition(
        PatternType.DESCENDING_CHANNEL,
        PatternFamily.CHANNEL,
        ("both lines falling", "slopes approximately parallel", "width stable"),
    ),
    _geometry_definition(
        PatternType.RANGE,
        PatternFamily.RANGE,
        ("upper and lower lines approximately flat", "width stable"),
    ),
)

PATTERN_BY_TYPE = {item.pattern_type: item for item in PATTERN_DEFINITIONS}

_PATTERN_PARAMETERS = {
    "double_min_spacing_bars": DOUBLE_MIN_SPACING_BARS,
    "double_max_spacing_bars": DOUBLE_MAX_SPACING_BARS,
    "double_max_level_mismatch_atr": DOUBLE_MAX_LEVEL_MISMATCH_ATR,
    "double_min_depth_atr": DOUBLE_MIN_DEPTH_ATR,
    "hs_max_shoulder_mismatch_atr": HS_MAX_SHOULDER_MISMATCH_ATR,
    "hs_max_neckline_mismatch_atr": HS_MAX_NECKLINE_MISMATCH_ATR,
    "hs_min_head_prominence_atr": HS_MIN_HEAD_PROMINENCE_ATR,
    "hs_min_time_symmetry": HS_MIN_TIME_SYMMETRY,
    "hs_max_time_symmetry": HS_MAX_TIME_SYMMETRY,
    "geometry_min_duration_bars": GEOMETRY_MIN_DURATION_BARS,
    "geometry_max_duration_bars": GEOMETRY_MAX_DURATION_BARS,
    "geometry_max_line_error_atr": GEOMETRY_MAX_LINE_ERROR_ATR,
    "geometry_flat_slope_atr_per_bar": GEOMETRY_FLAT_SLOPE_ATR_PER_BAR,
    "geometry_parallel_slope_atr_per_bar": GEOMETRY_PARALLEL_SLOPE_ATR_PER_BAR,
    "geometry_min_width_atr": GEOMETRY_MIN_WIDTH_ATR,
    "geometry_max_convergence_ratio": GEOMETRY_MAX_CONVERGENCE_RATIO,
    "geometry_channel_min_width_ratio": GEOMETRY_CHANNEL_MIN_WIDTH_RATIO,
    "geometry_channel_max_width_ratio": GEOMETRY_CHANNEL_MAX_WIDTH_RATIO,
    "geometry_max_apex_multiple": GEOMETRY_MAX_APEX_MULTIPLE,
    "breakout_buffer_atr": BREAKOUT_BUFFER_ATR,
    "max_lookahead_min_bars": MAX_LOOKAHEAD_MIN_BARS,
    "max_lookahead_max_bars": MAX_LOOKAHEAD_MAX_BARS,
    "post_confirm_invalidation_min_bars": POST_CONFIRM_INVALIDATION_MIN_BARS,
    "post_confirm_invalidation_max_bars": POST_CONFIRM_INVALIDATION_MAX_BARS,
    "overlap_suppression_ratio": OVERLAP_SUPPRESSION_RATIO,
    "prior_trend_lookback": PRIOR_TREND_LOOKBACK,
    "prior_trend_min_bars": PRIOR_TREND_MIN_BARS,
    "prior_trend_min_displacement_atr": PRIOR_TREND_MIN_DISPLACEMENT_ATR,
}

ANALYTICS_PATTERN_REGISTRY_FINGERPRINT = stable_digest(
    {
        "version": ANALYTICS_PATTERN_REGISTRY_VERSION,
        "intrabar_policy": ANALYTICS_PATTERN_INTRABAR_POLICY_VERSION,
        "definitions": PATTERN_DEFINITIONS,
        "parameters": _PATTERN_PARAMETERS,
    }
)
ANALYTICS_PATTERN_REGISTRY_IDENTITY = (
    f"{ANALYTICS_PATTERN_REGISTRY_VERSION}:{ANALYTICS_PATTERN_REGISTRY_FINGERPRINT}"
)
