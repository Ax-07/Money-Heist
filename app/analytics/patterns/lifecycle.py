from __future__ import annotations

from datetime import UTC, datetime

from .models import PatternDirection, PatternOccurrence, PatternStatus, PatternTransition
from .registry import PatternFamily


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return value.astimezone(UTC)


def transitions_at(
    transitions: tuple[PatternTransition, ...],
    as_of: datetime,
) -> tuple[PatternTransition, ...]:
    cutoff = _as_utc(as_of)
    return tuple(item for item in transitions if item.available_at <= cutoff)


def occurrence_at(
    occurrence: PatternOccurrence,
    as_of: datetime,
) -> PatternOccurrence | None:
    visible = transitions_at(occurrence.transitions, as_of)
    if not visible:
        return None

    has_confirmation = any(transition.status == PatternStatus.CONFIRMED for transition in visible)
    direction = occurrence.direction
    if occurrence.family != PatternFamily.REVERSAL and not has_confirmation:
        direction = PatternDirection.NEUTRAL

    return PatternOccurrence.create(
        analytics_run_id=occurrence.analytics_run_id,
        pattern_type=occurrence.pattern_type,
        family=occurrence.family,
        direction=direction,
        pivot_source=occurrence.pivot_source,
        symbol=occurrence.symbol,
        timeframe=occurrence.timeframe,
        points=occurrence.points,
        segments=occurrence.segments,
        transitions=visible,
        breakout_level=occurrence.breakout_level if has_confirmation else None,
        metrics=occurrence.metrics,
        diagnostic_flags=occurrence.diagnostic_flags,
        source_cursor_fingerprint=occurrence.source_cursor_fingerprint,
        source_pivot_fingerprints=occurrence.source_pivot_fingerprints,
    )
