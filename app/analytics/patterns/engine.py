from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from math import sqrt
from statistics import fmean

from app.market.models import Candle

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


def patterns_at(
    *,
    candles: Sequence[Candle],
    pivots: Sequence[PatternPivot],
    as_of: datetime,
    analytics_run_id: str,
    source_cursor_fingerprint: str,
) -> tuple[PatternOccurrence, ...]:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    cutoff = as_of.astimezone(UTC)
    visible_candles = tuple(
        candle for candle in candles if candle.is_closed and candle.close_time <= cutoff
    )
    if not visible_candles:
        return ()

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
        return ()
    if any(pivot.symbol != symbol or pivot.timeframe != timeframe for pivot in visible_pivots):
        raise ValueError("pivot symbol/timeframe differs from candles")
    sources = {pivot.source for pivot in visible_pivots}
    if len(sources) != 1:
        raise ValueError("one pattern computation cannot mix pivot sources")

    # The as-of cursor belongs to the snapshot. Occurrence provenance is anchored
    # to the cursor fingerprint of the last required pivot so it remains stable
    # while the same occurrence progresses through its lifecycle.
    if not source_cursor_fingerprint:
        raise ValueError("source_cursor_fingerprint must not be empty")

    alternating = _alternating(visible_pivots)
    atr = _atr_series(visible_candles, 14)
    candidates: list[PatternOccurrence] = []
    for index in range(len(alternating)):
        if index >= 2:
            item = _detect_double(
                visible_candles,
                atr,
                alternating[index - 2 : index + 1],
                analytics_run_id,
            )
            if item is not None:
                candidates.append(item)
        if index >= 4:
            item = _detect_hs(
                visible_candles,
                atr,
                alternating[index - 4 : index + 1],
                analytics_run_id,
            )
            if item is not None:
                candidates.append(item)
        if index >= 5:
            item = _detect_geometry(
                visible_candles,
                atr,
                alternating[index - 5 : index + 1],
                analytics_run_id,
            )
            if item is not None:
                candidates.append(item)
    return tuple(_suppress_duplicates(candidates))


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


def _detect_double(candles, atr, pivots, run_id):
    kinds = tuple(pivot.kind for pivot in pivots)
    if kinds not in {("HIGH", "LOW", "HIGH"), ("LOW", "HIGH", "LOW")}:
        return None
    bearish = kinds[0] == "HIGH"
    pattern_type = PatternType.DOUBLE_TOP if bearish else PatternType.DOUBLE_BOTTOM
    direction = PatternDirection.BEARISH if bearish else PatternDirection.BULLISH
    spacing = pivots[2].candle_index - pivots[0].candle_index
    if not DOUBLE_MIN_SPACING_BARS <= spacing <= DOUBLE_MAX_SPACING_BARS:
        return None
    atr_ref = _pivot_atr_ref(pivots)
    outer_mean = (float(pivots[0].price) + float(pivots[2].price)) / 2
    mismatch = abs(float(pivots[0].price) - float(pivots[2].price)) / atr_ref
    if mismatch > DOUBLE_MAX_LEVEL_MISMATCH_ATR:
        return None
    neckline = float(pivots[1].price)
    depth = (outer_mean - neckline) if bearish else (neckline - outer_mean)
    depth_atr = depth / atr_ref
    if depth_atr < DOUBLE_MIN_DEPTH_ATR:
        return None
    expected = "up" if bearish else "down"
    trend, strength, slope = _prior_trend(candles, atr, pivots[0].candle_index)
    if trend not in {expected, "unknown"}:
        return None
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
    roles = ("TOP_1", "TROUGH", "TOP_2") if bearish else ("BOTTOM_1", "PEAK", "BOTTOM_2")
    points = _points(pivots, roles)
    segments = _outline(pivots, points)
    return _finalize_level(
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
    )


def _detect_hs(candles, atr, pivots, run_id):
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
    atr_ref = _pivot_atr_ref(pivots)
    left = float(pivots[0].price)
    head = float(pivots[2].price)
    right = float(pivots[4].price)
    shoulder_mismatch = abs(left - right) / atr_ref
    neckline_mismatch = abs(float(pivots[1].price) - float(pivots[3].price)) / atr_ref
    if (
        shoulder_mismatch > HS_MAX_SHOULDER_MISMATCH_ATR
        or neckline_mismatch > HS_MAX_NECKLINE_MISMATCH_ATR
    ):
        return None
    shoulder_ref = max(left, right) if bearish else min(left, right)
    prominence = (head - shoulder_ref) if bearish else (shoulder_ref - head)
    prominence_atr = prominence / atr_ref
    if prominence_atr < HS_MIN_HEAD_PROMINENCE_ATR:
        return None
    left_duration = pivots[2].candle_index - pivots[0].candle_index
    right_duration = pivots[4].candle_index - pivots[2].candle_index
    if left_duration <= 0 or right_duration <= 0:
        return None
    symmetry = left_duration / right_duration
    if not HS_MIN_TIME_SYMMETRY <= symmetry <= HS_MAX_TIME_SYMMETRY:
        return None
    expected = "up" if bearish else "down"
    trend, strength, trend_slope = _prior_trend(
        candles,
        atr,
        pivots[0].candle_index,
    )
    if trend not in {expected, "unknown"}:
        return None
    slope, intercept = _fit(pivots[1::2])
    roles = (
        "LEFT_SHOULDER",
        "NECKLINE_1",
        "HEAD",
        "NECKLINE_2",
        "RIGHT_SHOULDER",
    )
    points = _points(pivots, roles)
    segments = _outline(pivots, points) + (_line_segment("NECKLINE", pivots[1], pivots[3], slope),)
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
    return _finalize_sloped(
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
    )


def _detect_geometry(candles, atr, pivots, run_id):
    highs = [pivot for pivot in pivots if pivot.kind == "HIGH"]
    lows = [pivot for pivot in pivots if pivot.kind == "LOW"]
    if len(highs) != 3 or len(lows) != 3:
        return None
    start = min(pivot.candle_index for pivot in pivots)
    end = max(pivot.candle_index for pivot in pivots)
    duration = end - start
    if not GEOMETRY_MIN_DURATION_BARS <= duration <= GEOMETRY_MAX_DURATION_BARS:
        return None
    atr_ref = _pivot_atr_ref(pivots)
    high_slope, high_intercept = _fit(highs)
    low_slope, low_intercept = _fit(lows)
    high_error = _fit_error(highs, high_slope, high_intercept, atr_ref)
    low_error = _fit_error(lows, low_slope, low_intercept, atr_ref)
    if max(high_error, low_error) > GEOMETRY_MAX_LINE_ERROR_ATR:
        return None
    upper_start = high_slope * start + high_intercept
    lower_start = low_slope * start + low_intercept
    upper_end = high_slope * end + high_intercept
    lower_end = low_slope * end + low_intercept
    width_start = upper_start - lower_start
    width_end = upper_end - lower_end
    if (
        width_start <= 0
        or width_end <= 0
        or min(width_start, width_end) / atr_ref < GEOMETRY_MIN_WIDTH_ATR
    ):
        return None
    width_ratio = width_end / width_start
    classified = _classify_geometry(
        high_slope / atr_ref,
        low_slope / atr_ref,
        width_ratio,
    )
    if classified is None:
        return None
    pattern_type, family, converging = classified
    apex = None
    if converging:
        delta = high_slope - low_slope
        if abs(delta) <= EPSILON:
            return None
        apex = (low_intercept - high_intercept) / delta
        if apex <= end + 1 or apex > end + duration * GEOMETRY_MAX_APEX_MULTIPLE:
            return None
    roles = tuple(f"{pivot.kind}_TOUCH_{index + 1}" for index, pivot in enumerate(pivots))
    points = _points(pivots, roles)
    segments = (
        _regression_segment("UPPER_BOUND", highs, high_slope, high_intercept),
        _regression_segment("LOWER_BOUND", lows, low_slope, low_intercept),
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
        "apex_index": apex,
        "methodology": "p5.v2_adapted_causal_zigzag",
    }
    detected = max(pivot.confirmed_at for pivot in pivots)
    transitions = [
        PatternTransition.create(
            PatternStatus.FORMING,
            detected,
            reason="geometry_detected",
        )
    ]
    confirmation_index = None
    breakout_level = None
    direction = PatternDirection.NEUTRAL
    first_future = end + 1
    deadline = first_future + _lookahead(duration)
    if apex is not None:
        deadline = min(deadline, max(first_future + 1, int(apex) + 1))
    horizon = min(len(candles), deadline)

    for index in range(first_future, horizon):
        upper = high_slope * index + high_intercept
        lower = low_slope * index + low_intercept
        if upper <= lower:
            transitions.append(
                PatternTransition.create(
                    PatternStatus.FAILED,
                    candles[index].close_time,
                    reason="bounds_crossed",
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
                candles[deadline - 1].close_time,
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
    start = max(pivot.candle_index for pivot in pivots) + 1
    duration = pivots[-1].candle_index - pivots[0].candle_index
    transitions = [
        PatternTransition.create(
            PatternStatus.FORMING,
            max(pivot.confirmed_at for pivot in pivots),
            reason="pivot_sequence_detected",
        )
    ]
    confirmation_index = None
    deadline = start + _lookahead(duration)
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
                candles[deadline - 1].close_time,
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
    start = max(pivot.candle_index for pivot in pivots) + 1
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
    deadline = start + _lookahead(duration)
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
                candles[deadline - 1].close_time,
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
    accepted = []
    for candidate in sorted(
        patterns,
        key=lambda pattern: (
            pattern.detected_at,
            pattern.pattern_type.value,
            pattern.pattern_id,
        ),
    ):
        ids = {point.pivot_id for point in candidate.points}
        duplicate = False
        for previous in accepted:
            if previous.pattern_type != candidate.pattern_type:
                continue
            previous_ids = {point.pivot_id for point in previous.points}
            common = len(ids & previous_ids)
            required = 4 if len(candidate.points) >= 6 else 2
            if common >= required:
                duplicate = True
                break
            left = max(candidate.start_at, previous.start_at)
            right = min(candidate.detected_at, previous.detected_at)
            overlap = max(0.0, (right - left).total_seconds())
            span = min(
                max((candidate.detected_at - candidate.start_at).total_seconds(), 1.0),
                max((previous.detected_at - previous.start_at).total_seconds(), 1.0),
            )
            if overlap / span >= OVERLAP_SUPPRESSION_RATIO:
                duplicate = True
                break
        if not duplicate:
            accepted.append(candidate)
    return accepted
