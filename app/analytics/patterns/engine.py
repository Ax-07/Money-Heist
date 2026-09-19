from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from math import sqrt
from statistics import fmean

from app.market.models import Candle

from .diagnostics import (
    PatternCandidateEvaluation,
    PatternCandidateFamily,
    PatternEvaluationResult,
    PatternRejectionReason,
    PatternRuleEvaluation,
)
from .models import (
    PatternDirection,
    PatternOccurrence,
    PatternPivot,
    PatternPoint,
    PatternSegment,
    PatternStatus,
    PatternTransition,
)
from .registry import (
    BREAKOUT_BUFFER_ATR,
    DOUBLE_MAX_LEVEL_MISMATCH_ATR,
    DOUBLE_MAX_SPACING_BARS,
    DOUBLE_MIN_DEPTH_ATR,
    DOUBLE_MIN_SPACING_BARS,
    GEOMETRY_CHANNEL_MAX_WIDTH_RATIO,
    GEOMETRY_CHANNEL_MIN_WIDTH_RATIO,
    GEOMETRY_FLAT_SLOPE_ATR_PER_BAR,
    GEOMETRY_MAX_APEX_MULTIPLE,
    GEOMETRY_MAX_CONVERGENCE_RATIO,
    GEOMETRY_MAX_DURATION_BARS,
    GEOMETRY_MAX_LINE_ERROR_ATR,
    GEOMETRY_MIN_DURATION_BARS,
    GEOMETRY_MIN_WIDTH_ATR,
    GEOMETRY_PARALLEL_SLOPE_ATR_PER_BAR,
    HS_MAX_NECKLINE_MISMATCH_ATR,
    HS_MAX_SHOULDER_MISMATCH_ATR,
    HS_MAX_TIME_SYMMETRY,
    HS_MIN_HEAD_PROMINENCE_ATR,
    HS_MIN_TIME_SYMMETRY,
    MAX_LOOKAHEAD_MAX_BARS,
    MAX_LOOKAHEAD_MIN_BARS,
    OVERLAP_SUPPRESSION_RATIO,
    POST_CONFIRM_INVALIDATION_MAX_BARS,
    POST_CONFIRM_INVALIDATION_MIN_BARS,
    PRIOR_TREND_LOOKBACK,
    PRIOR_TREND_MIN_BARS,
    PRIOR_TREND_MIN_DISPLACEMENT_ATR,
    PatternFamily,
    PatternType,
)

EPSILON = 1e-12


class _CandidateTrace:
    def __init__(self, family: PatternCandidateFamily) -> None:
        self.family = family
        self.pattern_type = None
        self.rules: list[PatternRuleEvaluation] = []
        self.metrics: dict[str, object] = {}
        self.flags: list[str] = []


def _rule(
    trace: _CandidateTrace | None,
    *,
    rule_id: str,
    passed: bool,
    reason: PatternRejectionReason,
    observed: dict[str, object],
    required: dict[str, object],
) -> bool:
    if trace is not None:
        trace.rules.append(
            PatternRuleEvaluation(
                rule_id=rule_id,
                passed=passed,
                observed=observed,
                required=required,
                rejection_reason=None if passed else reason,
            )
        )
    return passed


def patterns_at(
    *,
    candles: Sequence[Candle],
    pivots: Sequence[PatternPivot],
    as_of: datetime,
    analytics_run_id: str,
    source_cursor_fingerprint: str,
) -> tuple[PatternOccurrence, ...]:
    return pattern_evaluations_at(
        candles=candles,
        pivots=pivots,
        as_of=as_of,
        analytics_run_id=analytics_run_id,
        source_cursor_fingerprint=source_cursor_fingerprint,
    ).patterns


def pattern_evaluations_at(
    *,
    candles: Sequence[Candle],
    pivots: Sequence[PatternPivot],
    as_of: datetime,
    analytics_run_id: str,
    source_cursor_fingerprint: str,
) -> PatternEvaluationResult:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    cutoff = as_of.astimezone(UTC)
    visible_candles = tuple(
        candle for candle in candles if candle.is_closed and candle.close_time <= cutoff
    )
    if not visible_candles:
        return PatternEvaluationResult(patterns=(), candidates=())

    _validate_candle_order(visible_candles)
    symbol = visible_candles[0].symbol
    timeframe = visible_candles[0].timeframe
    if any(candle.symbol != symbol or candle.timeframe != timeframe for candle in visible_candles):
        raise ValueError("patterns require one symbol/timeframe")

    visible_pivots = tuple(
        pivot
        for pivot in pivots
        if pivot.confirmed_at <= cutoff
        and pivot.candle_index < len(visible_candles)
        and pivot.confirmed_index < len(visible_candles)
    )
    if not visible_pivots:
        return PatternEvaluationResult(patterns=(), candidates=())
    if any(pivot.symbol != symbol or pivot.timeframe != timeframe for pivot in visible_pivots):
        raise ValueError("pivot symbol/timeframe differs from candles")
    if len({pivot.source for pivot in visible_pivots}) != 1:
        raise ValueError("one pattern computation cannot mix pivot sources")
    if not source_cursor_fingerprint:
        raise ValueError("source_cursor_fingerprint must not be empty")

    alternating = _alternating(visible_pivots)
    atr = _atr_series(visible_candles, 14)
    records: list[tuple[_CandidateTrace, tuple[PatternPivot, ...], PatternOccurrence | None]] = []
    provisional: list[PatternOccurrence] = []
    for index in range(len(alternating)):
        if index >= 2:
            window = tuple(alternating[index - 2 : index + 1])
            trace = _CandidateTrace(PatternCandidateFamily.DOUBLE)
            item = _detect_double(visible_candles, atr, window, analytics_run_id, trace=trace)
            records.append((trace, window, item))
            if item is not None:
                provisional.append(item)
        if index >= 4:
            window = tuple(alternating[index - 4 : index + 1])
            trace = _CandidateTrace(PatternCandidateFamily.HEAD_SHOULDERS)
            item = _detect_hs(visible_candles, atr, window, analytics_run_id, trace=trace)
            records.append((trace, window, item))
            if item is not None:
                provisional.append(item)
        if index >= 5:
            window = tuple(alternating[index - 5 : index + 1])
            trace = _CandidateTrace(PatternCandidateFamily.GEOMETRY)
            item = _detect_geometry(visible_candles, atr, window, analytics_run_id, trace=trace)
            records.append((trace, window, item))
            if item is not None:
                provisional.append(item)

    retained, suppressions = _suppress_duplicates_with_diagnostics(provisional)
    retained_ids = {item.pattern_id for item in retained}
    diagnostics: list[PatternCandidateEvaluation] = []
    for trace, window, occurrence in records:
        geometry_accepted = occurrence is not None
        accepted = geometry_accepted and occurrence.pattern_id in retained_ids
        rules = list(trace.rules)
        flags = list(trace.flags)
        reasons = [
            rule.rejection_reason
            for rule in rules
            if not rule.passed and rule.rejection_reason is not None
        ]
        if geometry_accepted and not accepted:
            evidence = suppressions[occurrence.pattern_id]
            rules.append(
                PatternRuleEvaluation(
                    rule_id="ENGINE.DEDUPLICATION",
                    passed=False,
                    observed=evidence,
                    required={"retained": True},
                    rejection_reason=PatternRejectionReason.DUPLICATE_SUPPRESSED,
                )
            )
            reasons.append(PatternRejectionReason.DUPLICATE_SUPPRESSED)
            flags.append("GEOMETRY_ACCEPTED_BEFORE_DEDUP")
        diagnostics.append(
            PatternCandidateEvaluation.create(
                family=trace.family,
                pattern_type=trace.pattern_type,
                pivots=window,
                geometry_accepted=geometry_accepted,
                accepted=accepted,
                occurrence=occurrence,
                rejection_reasons=reasons,
                diagnostic_flags=flags,
                metrics=trace.metrics,
                rule_evaluations=rules,
            )
        )
    return PatternEvaluationResult(
        patterns=tuple(retained),
        candidates=tuple(
            sorted(diagnostics, key=lambda item: (item.detected_at, item.candidate_id))
        ),
    )

def _validate_candle_order(candles: Sequence[Candle]) -> None:
    for previous, current in zip(candles, candles[1:], strict=False):
        if current.close_time <= previous.close_time:
            raise ValueError("pattern candles must be strictly chronological")


def _alternating(pivots: Sequence[PatternPivot]) -> list[PatternPivot]:
    result: list[PatternPivot] = []
    for pivot in sorted(
        pivots,
        key=lambda item: (item.candle_index, item.confirmed_at, item.pivot_id),
    ):
        if not result or result[-1].kind != pivot.kind:
            result.append(pivot)
            continue
        previous = result[-1]
        more_extreme = (
            pivot.price > previous.price if pivot.kind == "HIGH" else pivot.price < previous.price
        )
        if more_extreme:
            result[-1] = pivot
    return result


def _first_causal_evaluation_index(pivots: Sequence[PatternPivot]) -> int:
    return max(pivot.confirmed_index for pivot in pivots) + 1


def _detect_double(candles, atr, pivots, run_id, trace=None):
    kinds = tuple(pivot.kind for pivot in pivots)
    if kinds not in {("HIGH", "LOW", "HIGH"), ("LOW", "HIGH", "LOW")}:
        return None
    bearish = kinds[0] == "HIGH"
    pattern_type = PatternType.DOUBLE_TOP if bearish else PatternType.DOUBLE_BOTTOM
    direction = PatternDirection.BEARISH if bearish else PatternDirection.BULLISH
    if trace is not None:
        trace.pattern_type = pattern_type
    ordered = all(
        right.candle_index > left.candle_index
        for left, right in zip(pivots, pivots[1:], strict=False)
    )
    spacing = pivots[2].candle_index - pivots[0].candle_index
    atr_ref = _pivot_atr_ref(pivots)
    outer_mean = (float(pivots[0].price) + float(pivots[2].price)) / 2
    mismatch = abs(float(pivots[0].price) - float(pivots[2].price)) / atr_ref
    neckline = float(pivots[1].price)
    depth = (outer_mean - neckline) if bearish else (neckline - outer_mean)
    depth_atr = depth / atr_ref
    expected = "up" if bearish else "down"
    trend, strength, slope = _prior_trend(candles, atr, pivots[0].candle_index)
    checks = (
        _rule(
            trace, rule_id="COMMON.VALID_PIVOT_ORDER", passed=ordered,
            reason=PatternRejectionReason.INVALID_PIVOT_ORDER,
            observed={"candle_indexes": tuple(p.candle_index for p in pivots)},
            required={"strictly_increasing": True},
        ),
        _rule(
            trace, rule_id="DOUBLE.MIN_SPACING", passed=spacing >= DOUBLE_MIN_SPACING_BARS,
            reason=PatternRejectionReason.SPACING_TOO_SHORT,
            observed={"spacing_bars": spacing}, required={"minimum_bars": DOUBLE_MIN_SPACING_BARS},
        ),
        _rule(
            trace, rule_id="DOUBLE.MAX_SPACING", passed=spacing <= DOUBLE_MAX_SPACING_BARS,
            reason=PatternRejectionReason.SPACING_TOO_LONG,
            observed={"spacing_bars": spacing}, required={"maximum_bars": DOUBLE_MAX_SPACING_BARS},
        ),
        _rule(
            trace, rule_id="DOUBLE.MAX_LEVEL_MISMATCH",
            passed=mismatch <= DOUBLE_MAX_LEVEL_MISMATCH_ATR,
            reason=PatternRejectionReason.OUTER_LEVELS_TOO_FAR_APART,
            observed={"level_mismatch_atr": mismatch},
            required={"maximum_atr": DOUBLE_MAX_LEVEL_MISMATCH_ATR},
        ),
        _rule(
            trace, rule_id="DOUBLE.MIN_DEPTH", passed=depth_atr >= DOUBLE_MIN_DEPTH_ATR,
            reason=PatternRejectionReason.INTERMEDIATE_RETRACEMENT_TOO_SHALLOW,
            observed={"depth_atr": depth_atr}, required={"minimum_atr": DOUBLE_MIN_DEPTH_ATR},
        ),
        _rule(
            trace, rule_id="DOUBLE.PRIOR_TREND", passed=trend in {expected, "unknown"},
            reason=PatternRejectionReason.PRIOR_TREND_CONFLICT,
            observed={"prior_trend": trend}, required={"allowed": (expected, "unknown")},
        ),
    )
    invalidation = (
        max(float(pivots[0].price), float(pivots[2].price))
        if bearish
        else min(float(pivots[0].price), float(pivots[2].price))
    )
    metrics = {
        "level_mismatch_atr": mismatch,
        "depth_atr": depth_atr,
        "spacing_bars": spacing,
        "prior_trend": trend,
        "prior_trend_strength_atr": strength,
        "prior_trend_slope_atr_per_bar": slope,
        "invalidation_level": invalidation,
        "methodology": "p5.v2_adapted_causal_zigzag",
    }
    if trace is not None:
        trace.metrics.update(metrics)
    if not all(checks):
        return None
    roles = ("TOP_1", "TROUGH", "TOP_2") if bearish else ("BOTTOM_1", "PEAK", "BOTTOM_2")
    points = _points(pivots, roles)
    segments = _outline(pivots, points)
    return _finalize_level(
        candles, atr, pivots, run_id, pattern_type, direction, neckline,
        invalidation, points, segments, metrics,
    )

def _detect_hs(candles, atr, pivots, run_id, trace=None):
    kinds = tuple(pivot.kind for pivot in pivots)
    if kinds not in {
        ("HIGH", "LOW", "HIGH", "LOW", "HIGH"),
        ("LOW", "HIGH", "LOW", "HIGH", "LOW"),
    }:
        return None
    bearish = kinds[0] == "HIGH"
    pattern_type = (
        PatternType.HEAD_AND_SHOULDERS if bearish else PatternType.INVERSE_HEAD_AND_SHOULDERS
    )
    direction = PatternDirection.BEARISH if bearish else PatternDirection.BULLISH
    if trace is not None:
        trace.pattern_type = pattern_type
    ordered = all(
        right.candle_index > left.candle_index
        for left, right in zip(pivots, pivots[1:], strict=False)
    )
    atr_ref = _pivot_atr_ref(pivots)
    left = float(pivots[0].price)
    head = float(pivots[2].price)
    right = float(pivots[4].price)
    shoulder_mismatch = abs(left - right) / atr_ref
    neckline_mismatch = abs(float(pivots[1].price) - float(pivots[3].price)) / atr_ref
    shoulder_ref = max(left, right) if bearish else min(left, right)
    prominence = (head - shoulder_ref) if bearish else (shoulder_ref - head)
    prominence_atr = prominence / atr_ref
    left_duration = pivots[2].candle_index - pivots[0].candle_index
    right_duration = pivots[4].candle_index - pivots[2].candle_index
    valid_time_order = left_duration > 0 and right_duration > 0
    symmetry = left_duration / right_duration if valid_time_order else 0.0
    expected = "up" if bearish else "down"
    trend, strength, trend_slope = _prior_trend(candles, atr, pivots[0].candle_index)
    checks = (
        _rule(
            trace, rule_id="COMMON.VALID_PIVOT_ORDER", passed=ordered and valid_time_order,
            reason=PatternRejectionReason.INVALID_PIVOT_ORDER,
            observed={"left_duration": left_duration, "right_duration": right_duration},
            required={"positive_durations": True},
        ),
        _rule(
            trace, rule_id="HS.MAX_SHOULDER_MISMATCH",
            passed=shoulder_mismatch <= HS_MAX_SHOULDER_MISMATCH_ATR,
            reason=PatternRejectionReason.SHOULDERS_TOO_ASYMMETRIC,
            observed={"shoulder_mismatch_atr": shoulder_mismatch},
            required={"maximum_atr": HS_MAX_SHOULDER_MISMATCH_ATR},
        ),
        _rule(
            trace, rule_id="HS.MAX_NECKLINE_MISMATCH",
            passed=neckline_mismatch <= HS_MAX_NECKLINE_MISMATCH_ATR,
            reason=PatternRejectionReason.NECKLINE_POINTS_TOO_ASYMMETRIC,
            observed={"neckline_mismatch_atr": neckline_mismatch},
            required={"maximum_atr": HS_MAX_NECKLINE_MISMATCH_ATR},
        ),
        _rule(
            trace, rule_id="HS.MIN_HEAD_PROMINENCE",
            passed=prominence_atr >= HS_MIN_HEAD_PROMINENCE_ATR,
            reason=PatternRejectionReason.HEAD_NOT_PROMINENT_ENOUGH,
            observed={"head_prominence_atr": prominence_atr},
            required={"minimum_atr": HS_MIN_HEAD_PROMINENCE_ATR},
        ),
        _rule(
            trace, rule_id="HS.TIME_SYMMETRY_RANGE",
            passed=valid_time_order and HS_MIN_TIME_SYMMETRY <= symmetry <= HS_MAX_TIME_SYMMETRY,
            reason=PatternRejectionReason.TIME_SYMMETRY_OUT_OF_RANGE,
            observed={"time_symmetry_ratio": symmetry},
            required={"minimum": HS_MIN_TIME_SYMMETRY, "maximum": HS_MAX_TIME_SYMMETRY},
        ),
        _rule(
            trace, rule_id="HS.PRIOR_TREND", passed=trend in {expected, "unknown"},
            reason=PatternRejectionReason.PRIOR_TREND_CONFLICT,
            observed={"prior_trend": trend}, required={"allowed": (expected, "unknown")},
        ),
    )
    slope, intercept = _fit(pivots[1::2])
    metrics = {
        "shoulder_mismatch_atr": shoulder_mismatch,
        "neckline_mismatch_atr": neckline_mismatch,
        "head_prominence_atr": prominence_atr,
        "time_symmetry_ratio": symmetry,
        "prior_trend": trend,
        "prior_trend_strength_atr": strength,
        "prior_trend_slope_atr_per_bar": trend_slope,
        "neckline_slope_atr_per_bar": slope / atr_ref,
        "methodology": "p5.v2_adapted_causal_zigzag",
    }
    if trace is not None:
        trace.metrics.update(metrics)
    if not all(checks):
        return None
    roles = ("LEFT_SHOULDER", "NECKLINE_1", "HEAD", "NECKLINE_2", "RIGHT_SHOULDER")
    points = _points(pivots, roles)
    segments = _outline(pivots, points) + (
        _line_segment("NECKLINE", pivots[1], pivots[3], slope),
    )
    return _finalize_sloped(
        candles, atr, pivots, run_id, pattern_type, direction, slope, intercept,
        head, points, segments, metrics,
    )

def _detect_geometry(candles, atr, pivots, run_id, trace=None):
    highs = [pivot for pivot in pivots if pivot.kind == "HIGH"]
    lows = [pivot for pivot in pivots if pivot.kind == "LOW"]
    if len(highs) != 3 or len(lows) != 3:
        return None
    ordered = all(
        right.candle_index > left.candle_index
        for left, right in zip(pivots, pivots[1:], strict=False)
    )
    start = min(pivot.candle_index for pivot in pivots)
    end = max(pivot.candle_index for pivot in pivots)
    duration = end - start
    atr_ref = _pivot_atr_ref(pivots)
    high_slope, high_intercept = _fit(highs)
    low_slope, low_intercept = _fit(lows)
    high_error = _fit_error(highs, high_slope, high_intercept, atr_ref)
    low_error = _fit_error(lows, low_slope, low_intercept, atr_ref)
    upper_start = high_slope * start + high_intercept
    lower_start = low_slope * start + low_intercept
    upper_end = high_slope * end + high_intercept
    lower_end = low_slope * end + low_intercept
    width_start = upper_start - lower_start
    width_end = upper_end - lower_end
    widths_positive = width_start > 0 and width_end > 0
    width_ratio = width_end / width_start if width_start > EPSILON else 0.0
    classified = _classify_geometry(high_slope / atr_ref, low_slope / atr_ref, width_ratio)
    pattern_type = classified[0] if classified is not None else None
    family = classified[1] if classified is not None else None
    converging = classified[2] if classified is not None else False
    if trace is not None:
        trace.pattern_type = pattern_type
    delta = high_slope - low_slope
    apex = (
        (low_intercept - high_intercept) / delta
        if converging and abs(delta) > EPSILON
        else None
    )
    checks = [
        _rule(
            trace, rule_id="COMMON.VALID_PIVOT_ORDER", passed=ordered,
            reason=PatternRejectionReason.INVALID_PIVOT_ORDER,
            observed={"candle_indexes": tuple(p.candle_index for p in pivots)},
            required={"strictly_increasing": True},
        ),
        _rule(
            trace, rule_id="GEOMETRY.MIN_DURATION", passed=duration >= GEOMETRY_MIN_DURATION_BARS,
            reason=PatternRejectionReason.DURATION_TOO_SHORT,
            observed={"duration_bars": duration},
            required={"minimum_bars": GEOMETRY_MIN_DURATION_BARS},
        ),
        _rule(
            trace, rule_id="GEOMETRY.MAX_DURATION", passed=duration <= GEOMETRY_MAX_DURATION_BARS,
            reason=PatternRejectionReason.DURATION_TOO_LONG,
            observed={"duration_bars": duration},
            required={"maximum_bars": GEOMETRY_MAX_DURATION_BARS},
        ),
        _rule(
            trace, rule_id="GEOMETRY.MAX_LINE_ERROR",
            passed=max(high_error, low_error) <= GEOMETRY_MAX_LINE_ERROR_ATR,
            reason=PatternRejectionReason.TRENDLINE_FIT_ERROR_TOO_HIGH,
            observed={"high_error_atr": high_error, "low_error_atr": low_error},
            required={"maximum_atr": GEOMETRY_MAX_LINE_ERROR_ATR},
        ),
        _rule(
            trace, rule_id="GEOMETRY.POSITIVE_BOUNDS", passed=widths_positive,
            reason=PatternRejectionReason.TRENDLINE_BOUNDS_CROSSED,
            observed={"width_start": width_start, "width_end": width_end},
            required={"both_positive": True},
        ),
        _rule(
            trace, rule_id="GEOMETRY.MIN_WIDTH",
            passed=widths_positive
            and min(width_start, width_end) / atr_ref >= GEOMETRY_MIN_WIDTH_ATR,
            reason=PatternRejectionReason.STRUCTURE_TOO_NARROW,
            observed={
                "minimum_width_atr": min(width_start, width_end) / atr_ref
                if widths_positive
                else 0.0
            },
            required={"minimum_atr": GEOMETRY_MIN_WIDTH_ATR},
        ),
        _rule(
            trace, rule_id="GEOMETRY.CLASSIFIABLE", passed=classified is not None,
            reason=PatternRejectionReason.GEOMETRY_NOT_CLASSIFIED,
            observed={
                "high_slope_atr_per_bar": high_slope / atr_ref,
                "low_slope_atr_per_bar": low_slope / atr_ref,
                "width_ratio": width_ratio,
            },
            required={"registered_geometry": True},
        ),
    ]
    if converging:
        checks.extend(
            [
                _rule(
                    trace, rule_id="GEOMETRY.NONZERO_APEX_DELTA", passed=abs(delta) > EPSILON,
                    reason=PatternRejectionReason.PARALLEL_LINES_HAVE_NO_APEX,
                    observed={"slope_delta": delta}, required={"nonzero": True},
                ),
                _rule(
                    trace, rule_id="GEOMETRY.APEX_IN_FUTURE",
                    passed=apex is not None and apex > end + 1,
                    reason=PatternRejectionReason.APEX_NOT_IN_FUTURE,
                    observed={"apex_index": apex, "end_index": end},
                    required={"minimum_exclusive": end + 1},
                ),
                _rule(
                    trace, rule_id="GEOMETRY.MAX_APEX_DISTANCE",
                    passed=apex is not None
                    and apex <= end + duration * GEOMETRY_MAX_APEX_MULTIPLE,
                    reason=PatternRejectionReason.APEX_TOO_FAR,
                    observed={"apex_index": apex},
                    required={"maximum_index": end + duration * GEOMETRY_MAX_APEX_MULTIPLE},
                ),
            ]
        )
    metrics = {
        "high_slope_atr_per_bar": high_slope / atr_ref,
        "low_slope_atr_per_bar": low_slope / atr_ref,
        "high_line_error_atr": high_error,
        "low_line_error_atr": low_error,
        "width_start_atr": width_start / atr_ref,
        "width_end_atr": width_end / atr_ref,
        "width_ratio": width_ratio,
        "duration_bars": duration,
        "apex_index": apex if converging else None,
        "methodology": "p5.v2_adapted_causal_zigzag",
    }
    if trace is not None:
        trace.metrics.update(metrics)
    if not all(checks) or classified is None or family is None:
        return None
    roles = tuple(f"{pivot.kind}_TOUCH_{index + 1}" for index, pivot in enumerate(pivots))
    points = _points(pivots, roles)
    segments = (
        _regression_segment("UPPER_BOUND", highs, high_slope, high_intercept),
        _regression_segment("LOWER_BOUND", lows, low_slope, low_intercept),
    )
    detected = max(pivot.confirmed_at for pivot in pivots)
    transitions = [
        PatternTransition.create(PatternStatus.FORMING, detected, reason="geometry_detected")
    ]
    confirmation_index = None
    breakout_level = None
    direction = PatternDirection.NEUTRAL
    structural_start = end + 1
    first_future = max(structural_start, _first_causal_evaluation_index(pivots))
    deadline = structural_start + _lookahead(duration)
    if apex is not None:
        deadline = min(deadline, max(structural_start + 1, int(apex) + 1))
    horizon = min(len(candles), deadline)
    for index in range(first_future, horizon):
        upper = high_slope * index + high_intercept
        lower = low_slope * index + low_intercept
        if upper <= lower:
            transitions.append(
                PatternTransition.create(
                    PatternStatus.FAILED, candles[index].close_time, reason="bounds_crossed"
                )
            )
            break
        close = float(candles[index].close)
        buffer = BREAKOUT_BUFFER_ATR * max(atr[index], EPSILON)
        if close > upper + buffer:
            direction = PatternDirection.BULLISH
            confirmation_index = index
            breakout_level = Decimal(str(upper))
            transitions.append(
                PatternTransition.create(
                    PatternStatus.CONFIRMED,
                    candles[index].close_time,
                    reason="close_breakout_upper",
                    evidence={"breakout_level": upper},
                )
            )
            break
        if close < lower - buffer:
            direction = PatternDirection.BEARISH
            confirmation_index = index
            breakout_level = Decimal(str(lower))
            transitions.append(
                PatternTransition.create(
                    PatternStatus.CONFIRMED,
                    candles[index].close_time,
                    reason="close_breakout_lower",
                    evidence={"breakout_level": lower},
                )
            )
            break
    if transitions[-1].status == PatternStatus.FORMING and len(candles) >= deadline:
        transitions.append(
            PatternTransition.create(
                PatternStatus.FAILED,
                max(candles[deadline - 1].close_time, transitions[0].available_at),
                reason="timeout",
            )
        )
    if confirmation_index is not None:
        invalid = _geometry_invalidation(
            candles,
            atr,
            confirmation_index,
            high_slope,
            high_intercept,
            low_slope,
            low_intercept,
            direction,
            duration,
        )
        if invalid is not None:
            transitions.append(
                PatternTransition.create(
                    PatternStatus.INVALIDATED,
                    invalid,
                    reason="breakout_reentered_structure",
                )
            )
    return _make_occurrence(
        run_id,
        pivots,
        pattern_type,
        family,
        direction,
        points,
        segments,
        tuple(transitions),
        breakout_level,
        metrics,
    )

def _finalize_level(
    candles,
    atr,
    pivots,
    run_id,
    pattern_type,
    direction,
    neckline,
    invalidation,
    points,
    segments,
    metrics,
):
    structural_start = max(pivot.candle_index for pivot in pivots) + 1
    start = max(structural_start, _first_causal_evaluation_index(pivots))
    duration = pivots[-1].candle_index - pivots[0].candle_index
    transitions = [
        PatternTransition.create(
            PatternStatus.FORMING,
            max(pivot.confirmed_at for pivot in pivots),
            reason="pivot_sequence_detected",
        )
    ]
    confirmation_index = None
    deadline = structural_start + _lookahead(duration)
    horizon = min(len(candles), deadline)
    for index in range(start, horizon):
        close = float(candles[index].close)
        buffer = BREAKOUT_BUFFER_ATR * max(atr[index], EPSILON)
        confirmed = (
            close < neckline - buffer
            if direction == PatternDirection.BEARISH
            else close > neckline + buffer
        )
        failed = (
            close > invalidation + buffer
            if direction == PatternDirection.BEARISH
            else close < invalidation - buffer
        )
        if confirmed:
            confirmation_index = index
            transitions.append(
                PatternTransition.create(
                    PatternStatus.CONFIRMED,
                    candles[index].close_time,
                    reason="close_breakout",
                    evidence={"breakout_level": neckline},
                )
            )
            break
        if failed:
            transitions.append(
                PatternTransition.create(
                    PatternStatus.FAILED,
                    candles[index].close_time,
                    reason="structure_broken",
                )
            )
            break
    if transitions[-1].status == PatternStatus.FORMING and len(candles) >= deadline:
        transitions.append(
            PatternTransition.create(
                PatternStatus.FAILED,
                max(candles[deadline - 1].close_time, transitions[0].available_at),
                reason="timeout",
            )
        )
    if confirmation_index is not None:
        invalid_at = _level_invalidation(
            candles,
            atr,
            confirmation_index,
            direction,
            neckline,
            duration,
        )
        if invalid_at is not None:
            transitions.append(
                PatternTransition.create(
                    PatternStatus.INVALIDATED,
                    invalid_at,
                    reason="breakout_reentered_structure",
                )
            )
    return _make_occurrence(
        run_id,
        pivots,
        pattern_type,
        PatternFamily.REVERSAL,
        direction,
        points,
        segments,
        tuple(transitions),
        Decimal(str(neckline)),
        metrics,
    )


def _finalize_sloped(
    candles,
    atr,
    pivots,
    run_id,
    pattern_type,
    direction,
    slope,
    intercept,
    head,
    points,
    segments,
    metrics,
):
    structural_start = max(pivot.candle_index for pivot in pivots) + 1
    start = max(structural_start, _first_causal_evaluation_index(pivots))
    duration = pivots[-1].candle_index - pivots[0].candle_index
    transitions = [
        PatternTransition.create(
            PatternStatus.FORMING,
            max(pivot.confirmed_at for pivot in pivots),
            reason="pivot_sequence_detected",
        )
    ]
    confirmation_index = None
    breakout_level = None
    deadline = structural_start + _lookahead(duration)
    horizon = min(len(candles), deadline)
    for index in range(start, horizon):
        neckline = slope * index + intercept
        close = float(candles[index].close)
        buffer = BREAKOUT_BUFFER_ATR * max(atr[index], EPSILON)
        confirmed = (
            close < neckline - buffer
            if direction == PatternDirection.BEARISH
            else close > neckline + buffer
        )
        failed = (
            close > head + buffer
            if direction == PatternDirection.BEARISH
            else close < head - buffer
        )
        if confirmed:
            confirmation_index = index
            breakout_level = Decimal(str(neckline))
            transitions.append(
                PatternTransition.create(
                    PatternStatus.CONFIRMED,
                    candles[index].close_time,
                    reason="close_breakout",
                    evidence={"breakout_level": neckline},
                )
            )
            break
        if failed:
            transitions.append(
                PatternTransition.create(
                    PatternStatus.FAILED,
                    candles[index].close_time,
                    reason="head_broken",
                )
            )
            break
    if transitions[-1].status == PatternStatus.FORMING and len(candles) >= deadline:
        transitions.append(
            PatternTransition.create(
                PatternStatus.FAILED,
                max(candles[deadline - 1].close_time, transitions[0].available_at),
                reason="timeout",
            )
        )
    if confirmation_index is not None:
        invalid_at = _sloped_invalidation(
            candles,
            atr,
            confirmation_index,
            direction,
            slope,
            intercept,
            duration,
        )
        if invalid_at is not None:
            transitions.append(
                PatternTransition.create(
                    PatternStatus.INVALIDATED,
                    invalid_at,
                    reason="breakout_reentered_structure",
                )
            )
    return _make_occurrence(
        run_id,
        pivots,
        pattern_type,
        PatternFamily.REVERSAL,
        direction,
        points,
        segments,
        tuple(transitions),
        breakout_level,
        metrics,
    )


def _make_occurrence(
    run_id,
    pivots,
    pattern_type,
    family,
    direction,
    points,
    segments,
    transitions,
    breakout_level,
    metrics,
):
    detection_pivot = max(
        pivots,
        key=lambda pivot: (pivot.confirmed_at, pivot.confirmed_index, pivot.pivot_id),
    )
    return PatternOccurrence.create(
        analytics_run_id=run_id,
        pattern_type=pattern_type,
        family=family,
        direction=direction,
        pivot_source=pivots[0].source,
        symbol=pivots[0].symbol,
        timeframe=pivots[0].timeframe,
        points=points,
        segments=segments,
        transitions=transitions,
        breakout_level=breakout_level,
        metrics=metrics,
        diagnostic_flags=(),
        source_cursor_fingerprint=detection_pivot.source_cursor_fingerprint,
        source_pivot_fingerprints=tuple(pivot.source_fingerprint for pivot in pivots),
    )


def _classify_geometry(high, low, width_ratio):
    flat = GEOMETRY_FLAT_SLOPE_ATR_PER_BAR
    parallel = GEOMETRY_PARALLEL_SLOPE_ATR_PER_BAR
    high_flat = abs(high) <= flat
    low_flat = abs(low) <= flat
    converging = width_ratio <= GEOMETRY_MAX_CONVERGENCE_RATIO
    stable = GEOMETRY_CHANNEL_MIN_WIDTH_RATIO <= width_ratio <= GEOMETRY_CHANNEL_MAX_WIDTH_RATIO
    if high_flat and low_flat and stable:
        return PatternType.RANGE, PatternFamily.RANGE, False
    if high_flat and low > flat and converging:
        return PatternType.ASCENDING_TRIANGLE, PatternFamily.CONSOLIDATION, True
    if high < -flat and low_flat and converging:
        return PatternType.DESCENDING_TRIANGLE, PatternFamily.CONSOLIDATION, True
    if high < -flat and low > flat and converging:
        return PatternType.SYMMETRICAL_TRIANGLE, PatternFamily.CONSOLIDATION, True
    if high > flat and low > flat:
        if abs(high - low) <= parallel and stable:
            return PatternType.ASCENDING_CHANNEL, PatternFamily.CHANNEL, False
        if low > high + parallel / 2 and converging:
            return PatternType.RISING_WEDGE, PatternFamily.CONSOLIDATION, True
    if high < -flat and low < -flat:
        if abs(high - low) <= parallel and stable:
            return PatternType.DESCENDING_CHANNEL, PatternFamily.CHANNEL, False
        if high < low - parallel / 2 and converging:
            return PatternType.FALLING_WEDGE, PatternFamily.CONSOLIDATION, True
    return None


def _points(pivots, roles):
    return tuple(
        PatternPoint(
            role,
            pivot.pivot_id,
            pivot.kind,
            pivot.price,
            pivot.pivot_at,
            pivot.confirmed_at,
        )
        for role, pivot in zip(roles, pivots, strict=True)
    )


def _outline(pivots, points):
    segments = []
    for index, ((left_pivot, right_pivot), (left, right)) in enumerate(
        zip(
            zip(pivots, pivots[1:], strict=False),
            zip(points, points[1:], strict=False),
            strict=True,
        ),
        1,
    ):
        bars = right_pivot.candle_index - left_pivot.candle_index
        if bars <= 0:
            raise ValueError("pattern outline requires increasing candle indexes")
        slope = (right.price - left.price) / Decimal(bars)
        segments.append(
            PatternSegment(
                f"OUTLINE_{index}",
                left.pivot_at,
                left.price,
                right.pivot_at,
                right.price,
                slope,
            )
        )
    return tuple(segments)


def _line_segment(role, left, right, slope):
    return PatternSegment(
        role,
        left.pivot_at,
        left.price,
        right.pivot_at,
        right.price,
        Decimal(str(slope)),
    )


def _regression_segment(role, points, slope, intercept):
    left = min(points, key=lambda point: point.candle_index)
    right = max(points, key=lambda point: point.candle_index)
    return PatternSegment(
        role,
        left.pivot_at,
        Decimal(str(slope * left.candle_index + intercept)),
        right.pivot_at,
        Decimal(str(slope * right.candle_index + intercept)),
        Decimal(str(slope)),
    )


def _fit(points):
    xs = [float(point.candle_index) for point in points]
    ys = [float(point.price) for point in points]
    x_mean = fmean(xs)
    y_mean = fmean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator <= EPSILON:
        return 0.0, y_mean
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True)) / denominator
    return slope, y_mean - slope * x_mean


def _fit_error(points, slope, intercept, atr_ref):
    residuals = [float(point.price) - (slope * point.candle_index + intercept) for point in points]
    return sqrt(fmean(value * value for value in residuals)) / max(atr_ref, EPSILON)


def _pivot_atr_ref(pivots):
    return max(fmean(float(pivot.atr_at_pivot) for pivot in pivots), EPSILON)


def _prior_trend(candles, atr, end_index):
    available = min(PRIOR_TREND_LOOKBACK, end_index)
    if available < PRIOR_TREND_MIN_BARS:
        return "unknown", 0.0, 0.0
    start = end_index - available
    closes = [float(candle.close) for candle in candles[start : end_index + 1]]
    xs = list(range(len(closes)))
    x_mean = fmean(xs)
    y_mean = fmean(closes)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = (
        0.0
        if denominator <= EPSILON
        else sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, closes, strict=True)) / denominator
    )
    atr_ref = max(fmean(atr[start : end_index + 1]), EPSILON)
    displacement = (closes[-1] - closes[0]) / atr_ref
    slope_atr = slope / atr_ref
    if displacement >= PRIOR_TREND_MIN_DISPLACEMENT_ATR and slope_atr > 0:
        return "up", abs(displacement), slope_atr
    if displacement <= -PRIOR_TREND_MIN_DISPLACEMENT_ATR and slope_atr < 0:
        return "down", abs(displacement), slope_atr
    return "flat", abs(displacement), slope_atr


def _atr_series(candles, period):
    true_ranges = []
    previous_close = None
    for candle in candles:
        high = float(candle.high)
        low = float(candle.low)
        close = float(candle.close)
        value = (
            high - low
            if previous_close is None
            else max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        )
        true_ranges.append(max(value, EPSILON))
        previous_close = close
    result = []
    running = 0.0
    for index, value in enumerate(true_ranges):
        running += value
        if index >= period:
            running -= true_ranges[index - period]
        result.append(max(running / min(index + 1, period), EPSILON))
    return result


def _lookahead(duration):
    return max(
        MAX_LOOKAHEAD_MIN_BARS,
        min(MAX_LOOKAHEAD_MAX_BARS, int(round(duration * 1.5))),
    )


def _invalidation_bars(duration):
    return max(
        POST_CONFIRM_INVALIDATION_MIN_BARS,
        min(POST_CONFIRM_INVALIDATION_MAX_BARS, int(round(duration * 0.75))),
    )


def _level_invalidation(candles, atr, confirmation, direction, neckline, duration):
    end = min(len(candles), confirmation + 1 + _invalidation_bars(duration))
    for index in range(confirmation + 1, end):
        close = float(candles[index].close)
        buffer = BREAKOUT_BUFFER_ATR * max(atr[index], EPSILON)
        invalid = (
            close > neckline + buffer
            if direction == PatternDirection.BEARISH
            else close < neckline - buffer
        )
        if invalid:
            return candles[index].close_time
    return None


def _sloped_invalidation(
    candles,
    atr,
    confirmation,
    direction,
    slope,
    intercept,
    duration,
):
    end = min(len(candles), confirmation + 1 + _invalidation_bars(duration))
    for index in range(confirmation + 1, end):
        neckline = slope * index + intercept
        close = float(candles[index].close)
        buffer = BREAKOUT_BUFFER_ATR * max(atr[index], EPSILON)
        invalid = (
            close > neckline + buffer
            if direction == PatternDirection.BEARISH
            else close < neckline - buffer
        )
        if invalid:
            return candles[index].close_time
    return None


def _geometry_invalidation(
    candles,
    atr,
    confirmation,
    high_slope,
    high_intercept,
    low_slope,
    low_intercept,
    direction,
    duration,
):
    end = min(len(candles), confirmation + 1 + _invalidation_bars(duration))
    for index in range(confirmation + 1, end):
        upper = high_slope * index + high_intercept
        lower = low_slope * index + low_intercept
        close = float(candles[index].close)
        buffer = BREAKOUT_BUFFER_ATR * max(atr[index], EPSILON)
        invalid = (
            close < upper - buffer
            if direction == PatternDirection.BULLISH
            else close > lower + buffer
        )
        if invalid:
            return candles[index].close_time
    return None


def _suppress_duplicates(patterns):
    return _suppress_duplicates_with_diagnostics(patterns)[0]


def _suppress_duplicates_with_diagnostics(patterns):
    accepted = []
    suppressions = {}
    for candidate in sorted(
        patterns,
        key=lambda pattern: (
            pattern.detected_at,
            pattern.pattern_type.value,
            pattern.pattern_id,
        ),
    ):
        ids = {point.pivot_id for point in candidate.points}
        suppressed = None
        for previous in accepted:
            if previous.pattern_type != candidate.pattern_type:
                continue
            previous_ids = {point.pivot_id for point in previous.points}
            common = len(ids & previous_ids)
            required = 4 if len(candidate.points) >= 6 else 2
            if common >= required:
                suppressed = {
                    "mode": "shared_pivots",
                    "common_pivots": common,
                    "required_common_pivots": required,
                    "retained_source_pivot_ids": tuple(sorted(previous_ids)),
                }
                break
            left = max(candidate.start_at, previous.start_at)
            right = min(candidate.detected_at, previous.detected_at)
            overlap = max(0.0, (right - left).total_seconds())
            span = min(
                max((candidate.detected_at - candidate.start_at).total_seconds(), 1.0),
                max((previous.detected_at - previous.start_at).total_seconds(), 1.0),
            )
            ratio = overlap / span
            if ratio >= OVERLAP_SUPPRESSION_RATIO:
                suppressed = {
                    "mode": "temporal_overlap",
                    "overlap_ratio": ratio,
                    "threshold": OVERLAP_SUPPRESSION_RATIO,
                    "retained_source_pivot_ids": tuple(sorted(previous_ids)),
                }
                break
        if suppressed is None:
            accepted.append(candidate)
        else:
            suppressions[candidate.pattern_id] = suppressed
    return accepted, suppressions
