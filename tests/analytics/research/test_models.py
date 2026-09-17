from dataclasses import FrozenInstanceError

import pytest

from app.analytics.models import AnalyticsPeriodRole
from app.analytics.research import (
    AnalyticsAnchorSpec,
    AnalyticsConditionSpec,
    AnalyticsContextDefinition,
    AnalyticsSequenceDefinition,
    AnalyticsSequenceStep,
    IndicatorOperator,
)
from app.analytics.research.registry import AnalyticsAnchorType, AnalyticsConditionType


def test_context_revision_is_immutable_and_material_change_changes_fingerprint(event_types):
    anchor = AnalyticsAnchorSpec(
        AnalyticsAnchorType.TECHNICAL_EVENT,
        "1h",
        event_type=event_types[0]
    )
    c1 = AnalyticsConditionSpec(
        "rsi",
        AnalyticsConditionType.INDICATOR,
        "1h",
        indicator_id="rsi_14",
        operator=IndicatorOperator.LT,
        value=30
    )
    c2 = AnalyticsConditionSpec(
        "rsi",
        AnalyticsConditionType.INDICATOR,
        "1h",
        indicator_id="rsi_14",
        operator=IndicatorOperator.LT,
        value=25
    )
    d1 = AnalyticsContextDefinition.create(
        definition_id="oversold",
        revision_number=1,
        name="oversold",
        description="",
        anchor=anchor,
        conditions=(c1,),
        timeframe="1h",
        origin_period_role=AnalyticsPeriodRole.DESIGN
    )
    d2 = AnalyticsContextDefinition.create(
        definition_id="oversold",
        revision_number=2,
        name="oversold",
        description="",
        anchor=anchor,
        conditions=(c2,),
        timeframe="1h",
        origin_period_role=AnalyticsPeriodRole.DESIGN
    )
    assert d1.revision_id != d2.revision_id
    assert d1.definition_fingerprint != d2.definition_fingerprint
    with pytest.raises(FrozenInstanceError):
        d1.name = "mutated"


def test_sequence_step_bounds_and_strict_windows(event_types):
    anchor = AnalyticsAnchorSpec(
        AnalyticsAnchorType.TECHNICAL_EVENT,
        "1h",
        event_type=event_types[0]
    )
    steps10 = (AnalyticsSequenceStep(
        "s0",
        anchor
    ),) + tuple(AnalyticsSequenceStep(f"s{i}", anchor, within_bars=5) for i in range(1, 10))
    definition = AnalyticsSequenceDefinition.create(
        definition_id="seq",
        revision_number=1,
        name="seq",
        description="",
        steps=steps10,
        final_conditions=(),
        timeframe="1h",
        origin_period_role=AnalyticsPeriodRole.DESIGN
    )
    assert len(definition.steps) == 10
    steps11 = steps10 + (AnalyticsSequenceStep("s10", anchor, within_bars=5),)
    with pytest.raises(ValueError, match="2 to 10"):
        AnalyticsSequenceDefinition.create(
            definition_id="seq2",
            revision_number=1,
            name="seq",
            description="",
            steps=steps11,
            final_conditions=(),
            timeframe="1h",
            origin_period_role=AnalyticsPeriodRole.DESIGN
        )
