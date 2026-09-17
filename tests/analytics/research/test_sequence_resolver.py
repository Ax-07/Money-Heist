from app.analytics.models import AnalyticsPeriodRole
from app.analytics.research import (
    AnalyticsAnchorSpec,
    AnalyticsObservationIndex,
    AnalyticsSequenceDefinition,
    AnalyticsSequenceResolver,
    AnalyticsSequenceStep,
)
from app.analytics.research.registry import AnalyticsAnchorType

from .conftest import FakeEvent, FakeIndicatorSnapshot, bars, fake_research_run


def _definition(event_types, *, b_window=5, c_window=3):
    a, b, c = event_types[:3]
    return AnalyticsSequenceDefinition.create(
        definition_id="abc",
        revision_number=1,
        name="A-B-C",
        description="",
        steps=(
            AnalyticsSequenceStep(
                "a",
                AnalyticsAnchorSpec(AnalyticsAnchorType.TECHNICAL_EVENT, "1h", event_type=a)
            ),
            AnalyticsSequenceStep(
                "b",
                AnalyticsAnchorSpec(AnalyticsAnchorType.TECHNICAL_EVENT, "1h", event_type=b),
                within_bars=b_window
            ),
            AnalyticsSequenceStep(
                "c",
                AnalyticsAnchorSpec(AnalyticsAnchorType.TECHNICAL_EVENT, "1h", event_type=c),
                within_bars=c_window
            ),
        ),
        final_conditions=(),
        timeframe="1h",
        origin_period_role=AnalyticsPeriodRole.DESIGN,
    )


def _index(t0, event_types, positions, cutoff):
    stamps = bars(t0, 15)
    snapshots = tuple(
        FakeIndicatorSnapshot(
            symbol="BTC/EUR",
            timeframe="1h",
            as_of=t,
            values={},
            fp=f"{i:064x}"
        ) for i,
        t in enumerate(stamps)
    )
    events = tuple(
        FakeEvent(
            event_types[i],
            stamps[pos],
            event_id=f"e-{i}-{pos}",
            fp=f"{100+i+pos:064x}"
        ) for i,
        pos in enumerate(positions)
    )
    return AnalyticsObservationIndex.build(
        as_of=stamps[cutoff],
        indicator_snapshots=snapshots,
        technical_events=events
    ), stamps


def test_three_step_sequence_and_exact_window_boundaries(t0, event_types):
    definition = _definition(event_types, b_window=5, c_window=3)
    index, stamps = _index(t0, event_types, (1, 6, 9), 9)
    matches = AnalyticsSequenceResolver().resolve(
        definition=definition,
        research_run=fake_research_run(definition),
        observation_index=index,
        symbol="BTC/EUR",
        as_of=stamps[9]
    )
    assert len(matches) == 1
    assert tuple(step.occurred_at for step in matches[0].step_matches) == (
        stamps[1],
        stamps[6],
        stamps[9]
    )


def test_outside_window_does_not_complete(t0, event_types):
    definition = _definition(event_types, b_window=4, c_window=3)
    index, stamps = _index(t0, event_types, (1, 6, 9), 9)
    assert AnalyticsSequenceResolver().resolve(
        definition=definition,
        research_run=fake_research_run(definition),
        observation_index=index,
        symbol="BTC/EUR",
        as_of=stamps[9]
    ) == ()


def test_sequence_is_not_back_propagated_and_prefix_invariant(t0, event_types):
    definition = _definition(event_types)
    index, stamps = _index(t0, event_types, (1, 4, 7), 10)
    resolver = AnalyticsSequenceResolver()
    assert resolver.resolve(
        definition=definition,
        research_run=fake_research_run(definition),
        observation_index=index,
        symbol="BTC/EUR",
        as_of=stamps[6]
    ) == ()
    full_at_t7 = resolver.resolve(
        definition=definition,
        research_run=fake_research_run(definition),
        observation_index=index,
        symbol="BTC/EUR",
        as_of=stamps[7]
    )
    prefix, _ = _index(t0, event_types, (1, 4, 7), 7)
    prefix_at_t7 = resolver.resolve(
        definition=definition,
        research_run=fake_research_run(definition),
        observation_index=prefix,
        symbol="BTC/EUR",
        as_of=stamps[7]
    )
    assert full_at_t7 == prefix_at_t7
    assert len(full_at_t7) == 1


def test_same_bar_then_is_rejected(t0, event_types):
    definition = _definition(event_types)
    # A and B are on the same bar; strict THEN must not invent intrabar order.
    index, stamps = _index(t0, event_types, (2, 2, 4), 4)
    assert AnalyticsSequenceResolver().resolve(
        definition=definition,
        research_run=fake_research_run(definition),
        observation_index=index,
        symbol="BTC/EUR",
        as_of=stamps[4]
    ) == ()


def test_latest_predecessor_policy_is_deterministic(t0, event_types):
    a, b, c = event_types[:3]
    definition = _definition(event_types, b_window=5, c_window=5)
    stamps = bars(t0, 10)
    snapshots = tuple(
        FakeIndicatorSnapshot(
            symbol="BTC/EUR",
            timeframe="1h",
            as_of=t,
            values={},
            fp=f"{i:064x}"
        ) for i,
        t in enumerate(stamps)
    )
    events = (
        FakeEvent(a, stamps[1], event_id="a1", fp="1"*64),
        FakeEvent(a, stamps[3], event_id="a3", fp="2"*64),
        FakeEvent(b, stamps[5], event_id="b5", fp="3"*64),
        FakeEvent(c, stamps[7], event_id="c7", fp="4"*64),
    )
    index = AnalyticsObservationIndex.build(
        as_of=stamps[7],
        indicator_snapshots=snapshots,
        technical_events=events
    )
    match = AnalyticsSequenceResolver().resolve(
        definition=definition,
        research_run=fake_research_run(definition),
        observation_index=index,
        symbol="BTC/EUR",
        as_of=stamps[7]
    )[0]
    assert match.step_matches[0].source_ref == "a3"
