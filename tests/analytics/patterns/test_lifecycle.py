from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.analytics.patterns.lifecycle import occurrence_at
from app.analytics.patterns.models import (
    PatternDirection,
    PatternOccurrence,
    PatternPoint,
    PatternStatus,
    PatternTransition,
)
from app.analytics.patterns.registry import PatternFamily, PatternType
from app.analytics.structure import StructureSource


def _points():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return (
        PatternPoint(
            "TOP_1",
            "p1",
            "HIGH",
            Decimal("110"),
            base,
            base + timedelta(hours=1),
        ),
        PatternPoint(
            "TROUGH",
            "p2",
            "LOW",
            Decimal("100"),
            base + timedelta(hours=2),
            base + timedelta(hours=3),
        ),
        PatternPoint(
            "TOP_2",
            "p3",
            "HIGH",
            Decimal("110"),
            base + timedelta(hours=4),
            base + timedelta(hours=5),
        ),
    )


def _occurrence():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    transitions = (
        PatternTransition.create(
            PatternStatus.FORMING,
            base + timedelta(hours=5),
            reason="detected",
        ),
        PatternTransition.create(
            PatternStatus.CONFIRMED,
            base + timedelta(hours=8),
            reason="breakout",
        ),
        PatternTransition.create(
            PatternStatus.INVALIDATED,
            base + timedelta(hours=12),
            reason="reentry",
        ),
    )
    return PatternOccurrence.create(
        analytics_run_id="run-1",
        pattern_type=PatternType.DOUBLE_TOP,
        family=PatternFamily.REVERSAL,
        direction=PatternDirection.BEARISH,
        pivot_source=StructureSource.CAUSAL_ZIGZAG,
        symbol="BTC/EUR",
        timeframe="1h",
        points=_points(),
        segments=(),
        transitions=transitions,
        breakout_level=Decimal("100"),
        metrics={},
        diagnostic_flags=(),
        source_cursor_fingerprint="a" * 64,
        source_pivot_fingerprints=("b" * 64, "c" * 64, "d" * 64),
    )


def test_pattern_final_status_not_backpropagated():
    occurrence = _occurrence()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    forming = occurrence_at(occurrence, base + timedelta(hours=7))
    confirmed = occurrence_at(occurrence, base + timedelta(hours=9))
    invalidated = occurrence_at(occurrence, base + timedelta(hours=12))
    assert forming is not None
    assert confirmed is not None
    assert invalidated is not None
    assert forming.current_status == PatternStatus.FORMING
    assert confirmed.current_status == PatternStatus.CONFIRMED
    assert confirmed.invalidated_at is None
    assert invalidated.current_status == PatternStatus.INVALIDATED


def test_pattern_id_stable_across_lifecycle_and_fingerprint_evolves():
    occurrence = _occurrence()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    forming = occurrence_at(occurrence, base + timedelta(hours=7))
    confirmed = occurrence_at(occurrence, base + timedelta(hours=9))
    assert forming is not None
    assert confirmed is not None
    assert forming.pattern_id == confirmed.pattern_id
    assert forming.pattern_fingerprint != confirmed.pattern_fingerprint


def test_geometry_direction_is_not_backpropagated_before_confirmation():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    transitions = (
        PatternTransition.create(
            PatternStatus.FORMING,
            base + timedelta(hours=5),
            reason="detected",
        ),
        PatternTransition.create(
            PatternStatus.CONFIRMED,
            base + timedelta(hours=8),
            reason="breakout",
        ),
    )
    occurrence = PatternOccurrence.create(
        analytics_run_id="run-1",
        pattern_type=PatternType.ASCENDING_TRIANGLE,
        family=PatternFamily.CONSOLIDATION,
        direction=PatternDirection.BULLISH,
        pivot_source=StructureSource.CAUSAL_ZIGZAG,
        symbol="BTC/EUR",
        timeframe="1h",
        points=_points(),
        segments=(),
        transitions=transitions,
        breakout_level=Decimal("111"),
        metrics={},
        diagnostic_flags=(),
        source_cursor_fingerprint="a" * 64,
        source_pivot_fingerprints=("b" * 64, "c" * 64, "d" * 64),
    )
    forming = occurrence_at(occurrence, base + timedelta(hours=7))
    assert forming is not None
    assert forming.current_status == PatternStatus.FORMING
    assert forming.direction == PatternDirection.NEUTRAL
    assert forming.breakout_level is None


def test_impossible_transition_is_rejected():
    occurrence = _occurrence()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    invalid = (
        PatternTransition.create(
            PatternStatus.FORMING,
            base + timedelta(hours=5),
            reason="detected",
        ),
        PatternTransition.create(
            PatternStatus.INVALIDATED,
            base + timedelta(hours=6),
            reason="impossible",
        ),
    )
    with pytest.raises(ValueError, match="invalid pattern transition"):
        PatternOccurrence.create(
            analytics_run_id=occurrence.analytics_run_id,
            pattern_type=occurrence.pattern_type,
            family=occurrence.family,
            direction=occurrence.direction,
            pivot_source=occurrence.pivot_source,
            symbol=occurrence.symbol,
            timeframe=occurrence.timeframe,
            points=occurrence.points,
            segments=occurrence.segments,
            transitions=invalid,
            breakout_level=None,
            metrics={},
            diagnostic_flags=(),
            source_cursor_fingerprint="a" * 64,
            source_pivot_fingerprints=occurrence.source_pivot_fingerprints,
        )
