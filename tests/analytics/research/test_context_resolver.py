import pytest

from app.analytics.research import (
    AnalyticsConditionSpec,
    AnalyticsContextResolver,
    AnalyticsObservationIndex,
    IndicatorOperator,
    TemporalScope,
)
from app.analytics.research.contexts import _numeric_match
from app.analytics.research.registry import AnalyticsConditionType

from .conftest import (
    FakeEvent,
    FakeIndicatorSnapshot,
    FakeIndicatorValue,
    bars,
    context_definition,
    fake_research_run,
)


@pytest.mark.parametrize(("op","value","expected"), [
    (IndicatorOperator.GT, 31, True),
    (IndicatorOperator.GTE, 30, True),
    (IndicatorOperator.LT, 29, True),
    (IndicatorOperator.LTE, 30, True),
    (IndicatorOperator.EQ, 30, True),
])
def test_indicator_operators(op, value, expected):
    condition = AnalyticsConditionSpec(
        "c",
        AnalyticsConditionType.INDICATOR,
        "1h",
        indicator_id="rsi_14",
        operator=op,
        value=30
    )
    assert _numeric_match(value, condition) is expected


def test_between_is_inclusive():
    condition = AnalyticsConditionSpec(
        "c",
        AnalyticsConditionType.INDICATOR,
        "1h",
        indicator_id="rsi_14",
        operator=IndicatorOperator.BETWEEN,
        min_value=20,
        max_value=30
    )
    assert _numeric_match(20, condition)
    assert _numeric_match(30, condition)
    assert not _numeric_match(30.01, condition)


def test_context_prefix_invariance_and_future_observation_isolation(t0, event_types):
    stamps = bars(t0, 8)
    anchor_event = FakeEvent(event_types[0], stamps[5], event_id="anchor", fp="a"*64)
    future_event = FakeEvent(event_types[1], stamps[7], event_id="future", fp="b"*64)
    snapshots = tuple(
        FakeIndicatorSnapshot(
            symbol="BTC/EUR",
            timeframe="1h",
            as_of=t,
            values={"rsi_14": FakeIndicatorValue(28.0, True, True)},
            fp=f"{i:064x}"
        ) for i,
        t in enumerate(stamps)
    )
    condition = AnalyticsConditionSpec(
        "rsi",
        AnalyticsConditionType.INDICATOR,
        "1h",
        indicator_id="rsi_14",
        operator=IndicatorOperator.LT,
        value=30
    )
    definition = context_definition(event_types[0], (condition,))
    run = fake_research_run(definition)
    full = AnalyticsObservationIndex.build(
        as_of=stamps[7],
        indicator_snapshots=snapshots,
        technical_events=(anchor_event, future_event)
    )
    prefix = AnalyticsObservationIndex.build(
        as_of=stamps[5],
        indicator_snapshots=snapshots[:6],
        technical_events=(anchor_event,)
    )
    resolver = AnalyticsContextResolver()
    left = resolver.resolve(
        definition=definition,
        research_run=run,
        observation_index=full,
        symbol="BTC/EUR",
        as_of=stamps[5]
    )
    right = resolver.resolve(
        definition=definition,
        research_run=run,
        observation_index=prefix,
        symbol="BTC/EUR",
        as_of=stamps[5]
    )
    assert left == right
    assert len(left) == 1


def test_event_lookback_boundaries(t0, event_types):
    stamps = bars(t0, 9)
    anchor = FakeEvent(event_types[0], stamps[6], event_id="anchor", fp="a"*64)
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
    for distance, should_match in ((3, True), (5, True), (6, False)):
        prior = FakeEvent(
            event_types[1],
            stamps[6-distance],
            event_id=f"prior-{distance}",
            fp=f"{distance:064x}"
        )
        condition = AnalyticsConditionSpec(
            "event",
            AnalyticsConditionType.TECHNICAL_EVENT,
            "1h",
            scope=TemporalScope.WITHIN_PREVIOUS_BARS,
            within_previous_bars=5,
            event_type=event_types[1]
        )
        definition = context_definition(event_types[0], (condition,))
        result = AnalyticsContextResolver().resolve(
            definition=definition,
            research_run=fake_research_run(definition),
            observation_index=AnalyticsObservationIndex.build(
                as_of=stamps[6],
                indicator_snapshots=snapshots,
                technical_events=(anchor, prior)
            ),
            symbol="BTC/EUR",
            as_of=stamps[6]
        )
        assert bool(result) is should_match


def test_missing_or_warmup_indicator_does_not_match(t0, event_types):
    anchor = FakeEvent(event_types[0], t0, event_id="anchor", fp="a"*64)
    condition = AnalyticsConditionSpec(
        "rsi",
        AnalyticsConditionType.INDICATOR,
        "1h",
        indicator_id="rsi_14",
        operator=IndicatorOperator.LT,
        value=30
    )
    definition = context_definition(event_types[0], (condition,))
    snapshot = FakeIndicatorSnapshot(
        symbol="BTC/EUR",
        timeframe="1h",
        as_of=t0,
        values={"rsi_14": FakeIndicatorValue(None, False, False)},
        fp="c"*64
    )
    result = AnalyticsContextResolver().resolve(
        definition=definition,
        research_run=fake_research_run(definition),
        observation_index=AnalyticsObservationIndex.build(
            as_of=t0,
            indicator_snapshots=(snapshot,),
            technical_events=(anchor,)
        ),
        symbol="BTC/EUR",
        as_of=t0
    )
    assert result == ()
