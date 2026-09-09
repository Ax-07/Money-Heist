from __future__ import annotations

from decimal import Decimal
from types import MappingProxyType

import pytest

from app.agents.models import AgentState
from app.evaluation import (
    AblationAggregate,
    AblationMetricDelta,
    AgentMetrics,
    Metric,
    ReputationPolicy,
    build_agent_reputation,
)


def available(value: str) -> Metric:
    return Metric.available(Decimal(value))


def metrics(*, agent_id: str = "rio", call_count: int = 20) -> AgentMetrics:
    return AgentMetrics(
        agent_id=agent_id,
        call_count=call_count,
        attempt_count=call_count,
        total_cost_eur=Decimal("1"),
        average_cost_eur=available("0.05"),
        average_latency_ms=available("120"),
        participation_frequency=available("0.40"),
        disagreement_frequency=available("0.25"),
        average_confidence=available("0.65"),
        stance_counts=MappingProxyType({"LONG": 4}),
        final_decision_counts=MappingProxyType({"LONG": 3}),
        prompt_versions=("v1",),
        route_ids=("core_reasoning",),
        model_ids=("model",),
    )


def aggregate(
    *,
    agent_id: str = "rio",
    oos: int = 3,
    economic: str = "1.5",
    drawdown: str = "0.01",
) -> AblationAggregate:
    return AblationAggregate(
        agent_id=agent_id,
        comparison_count=oos,
        oos_comparison_count=oos,
        economic_metric_count=oos,
        positive_economic_count=oos if Decimal(economic) > 0 else 0,
        negative_economic_count=oos if Decimal(economic) < 0 else 0,
        zero_economic_count=oos if Decimal(economic) == 0 else 0,
        mean_marginal_trading_net=AblationMetricDelta.available(Decimal("2")),
        mean_marginal_economic_net=AblationMetricDelta.available(Decimal(economic)),
        mean_drawdown_reduction_pct=AblationMetricDelta.available(Decimal(drawdown)),
        mean_additional_ai_cost_eur=Decimal("0.05"),
    )


def test_reputation_is_multidimensional_and_has_no_single_magic_score():
    profile = build_agent_reputation(metrics(), ablation=aggregate())

    assert profile.directional_agreement.value == Decimal("0.75")
    assert profile.marginal_economic_net.value == Decimal("1.5")
    assert profile.drawdown_reduction_pct.value == Decimal("0.01")
    assert not hasattr(profile, "score")
    assert not hasattr(profile, "reputation_score")


def test_positive_sufficient_oos_evidence_recommends_probation_not_active():
    profile = build_agent_reputation(metrics(), ablation=aggregate())

    assert profile.suggested_state is AgentState.PROBATION
    assert profile.state_reasons == ("POSITIVE_OOS_MARGINAL_ECONOMIC_NET",)


def test_insufficient_calls_or_oos_evidence_remains_shadow():
    low_calls = build_agent_reputation(metrics(call_count=2), ablation=aggregate())
    low_oos = build_agent_reputation(metrics(), ablation=aggregate(oos=1))

    assert low_calls.suggested_state is AgentState.SHADOW
    assert "INSUFFICIENT_CALLS" in low_calls.state_reasons
    assert low_oos.suggested_state is AgentState.SHADOW
    assert "INSUFFICIENT_OOS_ABLATION" in low_oos.state_reasons


def test_negative_marginal_economics_recommends_on_demand():
    profile = build_agent_reputation(
        metrics(),
        ablation=aggregate(economic="-0.25"),
    )

    assert profile.suggested_state is AgentState.ON_DEMAND
    assert profile.state_reasons == ("NEGATIVE_OOS_MARGINAL_ECONOMIC_NET",)


def test_drawdown_worsening_blocks_probation_even_with_positive_economics():
    profile = build_agent_reputation(
        metrics(),
        ablation=aggregate(economic="2", drawdown="-0.02"),
        policy=ReputationPolicy(max_allowed_drawdown_worsening_pct=Decimal("0.01")),
    )

    assert profile.suggested_state is AgentState.ON_DEMAND
    assert profile.state_reasons == ("DRAWDOWN_WORSENED_IN_ABLATION",)


def test_no_ablation_evidence_stays_shadow_and_does_not_invent_marginal_metrics():
    profile = build_agent_reputation(metrics())

    assert profile.suggested_state is AgentState.SHADOW
    assert "NO_ABLATION_EVIDENCE" in profile.state_reasons
    assert profile.marginal_economic_net.value is None


def test_reputation_rejects_cross_agent_ablation():
    with pytest.raises(ValueError, match="agent_id"):
        build_agent_reputation(metrics(agent_id="rio"), ablation=aggregate(agent_id="denver"))
