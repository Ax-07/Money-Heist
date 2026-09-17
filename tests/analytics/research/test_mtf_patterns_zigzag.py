from types import SimpleNamespace

import pytest

from app.analytics.patterns import PatternStatus, PatternType
from app.analytics.research import (
    AnalyticsConditionSpec,
    AnalyticsContextResolver,
    AnalyticsObservationIndex,
    IndicatorOperator,
)
from app.analytics.research.registry import (
    AnalyticsConditionType,
    PatternConditionMode,
    StructureField,
)
from app.analytics.zigzag import ZigZagPivotKind
from app.market.structure import BreakoutState, RangeLocation, SwingStructure

from .conftest import (
    FakeEvent,
    FakeIndicatorSnapshot,
    FakeIndicatorValue,
    bars,
    context_definition,
    fake_research_run,
)


def test_mtf_indicator_uses_last_available_closed_snapshot(t0, event_types):
    stamps = bars(t0, 7)
    anchor = FakeEvent(event_types[0], stamps[3], event_id="anchor", fp="a" * 64)
    one_h = tuple(
        FakeIndicatorSnapshot(
            symbol="BTC/EUR",
            timeframe="1h",
            as_of=t,
            values={},
            fp=f"{i:064x}"
        ) for i,
        t in enumerate(stamps)
    )
    four_h_old = FakeIndicatorSnapshot(
        symbol="BTC/EUR",
        timeframe="4h",
        as_of=stamps[0],
        values={"rsi_14": FakeIndicatorValue(40, True, True)},
        fp="b" * 64
    )
    four_h_future = FakeIndicatorSnapshot(
        symbol="BTC/EUR",
        timeframe="4h",
        as_of=stamps[4],
        values={"rsi_14": FakeIndicatorValue(60, True, True)},
        fp="c" * 64
    )
    condition = AnalyticsConditionSpec(
        "mtf-rsi",
        AnalyticsConditionType.INDICATOR,
        "4h",
        indicator_id="rsi_14",
        operator=IndicatorOperator.LT,
        value=50
    )
    definition = context_definition(event_types[0], (condition,))
    index = AnalyticsObservationIndex.build(
        as_of=stamps[6],
        indicator_snapshots=(*one_h, four_h_old, four_h_future),
        technical_events=(anchor,)
    )
    matches = AnalyticsContextResolver().resolve(
        definition=definition,
        research_run=fake_research_run(definition),
        observation_index=index,
        symbol="BTC/EUR",
        as_of=stamps[3]
    )
    assert len(matches) == 1
    assert matches[0].condition_results[0].observed_value == 40


def test_incomplete_or_future_higher_timeframe_structure_is_invisible(t0, event_types):
    stamps = bars(t0, 6)
    anchor = FakeEvent(event_types[0], stamps[3], event_id="anchor", fp="a" * 64)
    one_h = tuple(
        FakeIndicatorSnapshot(
            symbol="BTC/EUR",
            timeframe="1h",
            as_of=t,
            values={},
            fp=f"{i:064x}"
        ) for i,
        t in enumerate(stamps)
    )
    summary = SimpleNamespace(
        structure_ready=True,
        swing_structure=SwingStructure.BULLISH_HH_HL,
        breakout_state=BreakoutState.INSIDE_RANGE,
        range_location=RangeLocation.INSIDE_RANGE
    )
    future_structure = SimpleNamespace(
        symbol="BTC/EUR",
        as_of=stamps[4],
        fingerprint="d"*64,
        context=SimpleNamespace(timeframes={"4h": summary})
    )
    condition = AnalyticsConditionSpec(
        "structure",
        AnalyticsConditionType.STRUCTURE,
        "4h",
        structure_field=StructureField.SWING_STRUCTURE,
        expected_state=SwingStructure.BULLISH_HH_HL.value
    )
    definition = context_definition(event_types[0], (condition,))
    index = AnalyticsObservationIndex.build(
        as_of=stamps[5],
        indicator_snapshots=one_h,
        technical_events=(anchor,),
        structure_observations=(future_structure,)
    )
    assert AnalyticsContextResolver().resolve(
        definition=definition,
        research_run=fake_research_run(definition),
        observation_index=index,
        symbol="BTC/EUR",
        as_of=stamps[3]
    ) == ()


@pytest.mark.parametrize(
    "status",
    [
        PatternStatus.FORMING,
        PatternStatus.CONFIRMED,
        PatternStatus.FAILED,
        PatternStatus.INVALIDATED
    ]
)
def test_pattern_transition_statuses_are_visible_only_when_available(t0, event_types, status):
    stamps = bars(t0, 6)
    anchor = FakeEvent(event_types[0], stamps[4], event_id="anchor", fp="a" * 64)
    one_h = tuple(
        FakeIndicatorSnapshot(
            symbol="BTC/EUR",
            timeframe="1h",
            as_of=t,
            values={},
            fp=f"{i:064x}"
        ) for i,
        t in enumerate(stamps)
    )
    transition = SimpleNamespace(status=status, available_at=stamps[3], fingerprint="e"*64)
    pattern = SimpleNamespace(
        pattern_id="pattern-1",
        pattern_type=PatternType.DOUBLE_BOTTOM,
        symbol="BTC/EUR",
        timeframe="1h",
        detected_at=stamps[2],
        pattern_fingerprint="f"*64,
        transitions=(transition,)
    )
    condition = AnalyticsConditionSpec(
        "pattern",
        AnalyticsConditionType.PATTERN_TRANSITION,
        "1h",
        pattern_type=PatternType.DOUBLE_BOTTOM,
        pattern_status=status,
        pattern_mode=PatternConditionMode.CURRENT_STATUS
    )
    definition = context_definition(event_types[0], (condition,))
    index = AnalyticsObservationIndex.build(
        as_of=stamps[4],
        indicator_snapshots=one_h,
        technical_events=(anchor,),
        pattern_occurrences=(pattern,)
    )
    assert len(AnalyticsContextResolver().resolve(
        definition=definition,
        research_run=fake_research_run(definition),
        observation_index=index,
        symbol="BTC/EUR",
        as_of=stamps[4]
    )) == 1


def test_future_pattern_transition_cannot_change_context_at_t(t0, event_types):
    stamps = bars(t0, 7)
    anchor = FakeEvent(event_types[0], stamps[4], event_id="anchor", fp="a" * 64)
    one_h = tuple(
        FakeIndicatorSnapshot(
            symbol="BTC/EUR",
            timeframe="1h",
            as_of=t,
            values={},
            fp=f"{i:064x}"
        ) for i,
        t in enumerate(stamps)
    )
    confirmed = SimpleNamespace(
        status=PatternStatus.CONFIRMED,
        available_at=stamps[3],
        fingerprint="e"*64
    )
    invalidated = SimpleNamespace(
        status=PatternStatus.INVALIDATED,
        available_at=stamps[6],
        fingerprint="d"*64
    )
    pattern = SimpleNamespace(
        pattern_id="pattern-1",
        pattern_type=PatternType.DOUBLE_BOTTOM,
        symbol="BTC/EUR",
        timeframe="1h",
        detected_at=stamps[2],
        pattern_fingerprint="f"*64,
        transitions=(confirmed, invalidated)
    )
    condition = AnalyticsConditionSpec(
        "pattern",
        AnalyticsConditionType.PATTERN_TRANSITION,
        "1h",
        pattern_type=PatternType.DOUBLE_BOTTOM,
        pattern_status=PatternStatus.CONFIRMED,
        pattern_mode=PatternConditionMode.CURRENT_STATUS
    )
    definition = context_definition(event_types[0], (condition,))
    index = AnalyticsObservationIndex.build(
        as_of=stamps[6],
        indicator_snapshots=one_h,
        technical_events=(anchor,),
        pattern_occurrences=(pattern,)
    )
    assert len(AnalyticsContextResolver().resolve(
        definition=definition,
        research_run=fake_research_run(definition),
        observation_index=index,
        symbol="BTC/EUR",
        as_of=stamps[4]
    )) == 1


def test_zigzag_uses_confirmed_at_not_pivot_at_and_future_pivot_is_hidden(t0, event_types):
    stamps = bars(t0, 8)
    anchor = FakeEvent(event_types[0], stamps[5], event_id="anchor", fp="a" * 64)
    one_h = tuple(
        FakeIndicatorSnapshot(
            symbol="BTC/EUR",
            timeframe="1h",
            as_of=t,
            values={},
            fp=f"{i:064x}"
        ) for i,
        t in enumerate(stamps)
    )
    visible = SimpleNamespace(
        symbol="BTC/EUR",
        timeframe="1h",
        kind=ZigZagPivotKind.LOW,
        pivot_at=stamps[1],
        confirmed_at=stamps[3],
        pivot_id="pivot-visible",
        pivot_fingerprint="b"*64,
        price=100
    )
    future = SimpleNamespace(
        symbol="BTC/EUR",
        timeframe="1h",
        kind=ZigZagPivotKind.LOW,
        pivot_at=stamps[4],
        confirmed_at=stamps[6],
        pivot_id="pivot-future",
        pivot_fingerprint="c"*64,
        price=90
    )
    condition = AnalyticsConditionSpec(
        "pivot",
        AnalyticsConditionType.ZIGZAG,
        "1h",
        pivot_kind=ZigZagPivotKind.LOW,
        max_bars_since=2
    )
    definition = context_definition(event_types[0], (condition,))
    index = AnalyticsObservationIndex.build(
        as_of=stamps[7],
        indicator_snapshots=one_h,
        technical_events=(anchor,),
        zigzag_pivots=(visible, future)
    )
    match = AnalyticsContextResolver().resolve(
        definition=definition,
        research_run=fake_research_run(definition),
        observation_index=index,
        symbol="BTC/EUR",
        as_of=stamps[5]
    )[0]
    assert match.condition_results[0].source_ref == "pivot-visible"
    assert match.condition_results[0].source_available_at == stamps[3]
