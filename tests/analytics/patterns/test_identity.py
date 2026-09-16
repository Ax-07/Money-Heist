from datetime import UTC, datetime, timedelta
from decimal import Decimal

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
        PatternPoint("TOP_1", "p1", "HIGH", Decimal("110"), base, base),
        PatternPoint(
            "TROUGH",
            "p2",
            "LOW",
            Decimal("100"),
            base + timedelta(hours=2),
            base + timedelta(hours=2),
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


def _occurrence(source):
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
    return PatternOccurrence.create(
        analytics_run_id="run-1",
        pattern_type=PatternType.DOUBLE_TOP,
        family=PatternFamily.REVERSAL,
        direction=PatternDirection.BEARISH,
        pivot_source=source,
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


def test_pivot_source_is_part_of_occurrence_identity():
    zigzag = _occurrence(StructureSource.CAUSAL_ZIGZAG)
    structure = _occurrence(StructureSource.MONEY_HEIST_STRUCTURE)
    assert zigzag.pattern_id != structure.pattern_id


def test_state_fingerprint_changes_without_changing_occurrence_identity():
    occurrence = _occurrence(StructureSource.CAUSAL_ZIGZAG)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    forming = occurrence_at(occurrence, base + timedelta(hours=6))
    confirmed = occurrence_at(occurrence, base + timedelta(hours=9))
    assert forming is not None
    assert confirmed is not None
    assert forming.pattern_id == confirmed.pattern_id
    assert forming.pattern_fingerprint != confirmed.pattern_fingerprint
