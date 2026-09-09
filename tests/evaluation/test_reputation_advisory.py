from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.agents.models import AgentRegistryEntry, AgentRole, AgentState
from app.evaluation.ablation import (
    AblationComparison,
    AblationMetricDelta,
    aggregate_ablation,
)
from app.evaluation.models import AgentMetrics, Metric
from app.evaluation.reputation import ReputationPolicy, build_agent_reputation
from app.evaluation.reputation_advisory import (
    ReputationAdvisoryService,
    build_agent_state_evidence,
)
from app.evaluation.reputation_policy import (
    EvidenceSufficiency,
    ReputationPolicyThresholds,
    StateRecommendationAction,
)

D = Decimal
START = datetime(2026, 1, 1, tzinfo=UTC)


def metric(value: str) -> Metric:
    return Metric.available(D(value))


def agent_metrics(*, agent_id: str = "rio", calls: int = 40, cost: str = "2") -> AgentMetrics:
    return AgentMetrics(
        agent_id=agent_id,
        call_count=calls,
        attempt_count=calls,
        total_cost_eur=D(cost),
        average_cost_eur=metric("0.05"),
        average_latency_ms=metric("100"),
        participation_frequency=metric("0.5"),
        disagreement_frequency=metric("0.2"),
        average_confidence=metric("0.7"),
        stance_counts={},
        final_decision_counts={},
        prompt_versions=("v1",),
        route_ids=("core_reasoning",),
        model_ids=("model-1",),
    )


def registry_entry(
    *,
    agent_id: str = "rio",
    state: AgentState = AgentState.ON_DEMAND,
    core: bool = False,
) -> AgentRegistryEntry:
    return AgentRegistryEntry(
        agent_id=agent_id,
        role=AgentRole.DERIVATIVES_POSITIONING,
        state=state,
        prompt_version="v1",
        model_route="core_reasoning",
        core=core,
    )


def comparison(
    *,
    index: int,
    economic: str | None,
    drawdown: str = "0.10",
    oos: bool = True,
    agent_id: str = "rio",
) -> AblationComparison:
    economic_delta = (
        AblationMetricDelta.unavailable("NO_ECONOMIC_NET")
        if economic is None
        else AblationMetricDelta.available(D(economic))
    )
    return AblationComparison(
        agent_id=agent_id,
        comparison_fingerprint=f"experiment-{index}",
        baseline_run_id=f"baseline-{index}",
        ablated_run_id=f"without-{agent_id}-{index}",
        dataset_id="dataset-1",
        role="OOS" if oos else "VALIDATION",
        period_start=START,
        period_end=START,
        processed_candles=100,
        opportunity_count=10,
        closed_trade_count_delta=1,
        marginal_trading_net=AblationMetricDelta.available(D("1")),
        marginal_economic_net=economic_delta,
        drawdown_reduction_pct=AblationMetricDelta.available(D(drawdown)),
        additional_ai_cost_eur=D("0.5"),
        is_out_of_sample=oos,
    )


def reputation_policy() -> ReputationPolicy:
    return ReputationPolicy(
        min_calls=30,
        min_oos_ablation_comparisons=3,
        max_allowed_drawdown_worsening_pct=D("0.50"),
    )


def state_thresholds() -> ReputationPolicyThresholds:
    return ReputationPolicyThresholds(
        min_evaluation_samples=30,
        min_ablation_comparisons=3,
        promotion_beneficial_ratio=D("0.67"),
        demotion_harmful_ratio=D("0.67"),
        min_economic_net_contribution_eur=D("1.00"),
        max_drawdown_increase_pct=D("0.50"),
        max_ai_cost_share_pct=D("0.25"),
    )


def service() -> ReputationAdvisoryService:
    return ReputationAdvisoryService(
        reputation_policy=reputation_policy(),
        state_policy_thresholds=state_thresholds(),
    )


def test_adapter_maps_step1_aggregate_to_step2_evidence_without_hidden_score() -> None:
    metrics = agent_metrics(cost="2")
    aggregate = aggregate_ablation(
        (
            comparison(index=1, economic="2"),
            comparison(index=2, economic="1"),
            comparison(index=3, economic=None),
        )
    )
    profile = build_agent_reputation(metrics, ablation=aggregate, policy=reputation_policy())

    evidence = build_agent_state_evidence(
        profile,
        metrics=metrics,
        registry_entry=registry_entry(state=AgentState.SHADOW),
        ablation=aggregate,
        total_ai_cost_eur=D("10"),
    )

    assert evidence.current_state is AgentState.SHADOW
    assert evidence.evaluation_sample_count == 40
    assert evidence.ablation_comparison_count == 3
    assert evidence.beneficial_ablation_count == 2
    assert evidence.harmful_ablation_count == 0
    assert evidence.inconclusive_ablation_count == 1
    assert evidence.economic_net_contribution_eur == D("1.5")
    assert evidence.drawdown_reduction_pct == D("0.10")
    assert evidence.ai_cost_share_pct == D("0.2")


def test_adapter_rejects_mixed_oos_and_non_oos_for_state_policy() -> None:
    metrics = agent_metrics()
    aggregate = aggregate_ablation(
        (
            comparison(index=1, economic="2", oos=True),
            comparison(index=2, economic="2", oos=False),
        )
    )
    profile = build_agent_reputation(metrics, ablation=aggregate, policy=reputation_policy())

    with pytest.raises(ValueError, match="OOS-only"):
        build_agent_state_evidence(
            profile,
            metrics=metrics,
            registry_entry=registry_entry(),
            ablation=aggregate,
            total_ai_cost_eur=D("10"),
        )


def test_adapter_rejects_cross_scope_ai_costs() -> None:
    metrics = agent_metrics(cost="3")
    profile = build_agent_reputation(metrics, policy=reputation_policy())

    with pytest.raises(ValueError, match="cannot exceed"):
        build_agent_state_evidence(
            profile,
            metrics=metrics,
            registry_entry=registry_entry(),
            ablation=None,
            total_ai_cost_eur=D("2"),
        )


def test_zero_total_ai_cost_maps_zero_agent_cost_to_zero_share() -> None:
    metrics = agent_metrics(cost="0")
    profile = build_agent_reputation(metrics, policy=reputation_policy())

    evidence = build_agent_state_evidence(
        profile,
        metrics=metrics,
        registry_entry=registry_entry(),
        ablation=None,
        total_ai_cost_eur=D("0"),
    )

    assert evidence.ai_cost_share_pct == D("0")


def test_report_preserves_provenance_and_recommends_one_step_only() -> None:
    report = service().build(
        metrics=agent_metrics(cost="2"),
        registry_entry=registry_entry(state=AgentState.SHADOW),
        comparisons=(
            comparison(index=3, economic="2"),
            comparison(index=1, economic="2"),
            comparison(index=2, economic="2"),
        ),
        total_ai_cost_eur=D("10"),
        evaluation_report_version="batch10.evaluation.v1",
    )

    assert report.report_version == "batch18.reputation-advisory.v1"
    assert report.provenance.comparison_count == 3
    assert report.provenance.oos_comparison_count == 3
    assert report.provenance.baseline_run_ids == (
        "baseline-1",
        "baseline-2",
        "baseline-3",
    )
    assert report.recommendation.action is StateRecommendationAction.PROMOTE
    assert report.recommendation.recommended_state is AgentState.PROBATION
    assert report.recommendation.auto_apply is False
    assert report.auto_apply is False
    assert len(report.audit_fingerprint_sha256) == 64


def test_report_fingerprint_is_deterministic_under_input_order() -> None:
    comparisons = (
        comparison(index=1, economic="2"),
        comparison(index=2, economic="2"),
        comparison(index=3, economic="2"),
    )
    kwargs = dict(
        metrics=agent_metrics(),
        registry_entry=registry_entry(state=AgentState.SHADOW),
        total_ai_cost_eur=D("10"),
        evaluation_report_version="batch10.evaluation.v1",
    )

    left = service().build(comparisons=comparisons, **kwargs)
    right = service().build(comparisons=tuple(reversed(comparisons)), **kwargs)

    assert left.audit_fingerprint_sha256 == right.audit_fingerprint_sha256
    assert left.recommendation == right.recommendation


def test_report_without_ablation_holds_fail_closed() -> None:
    report = service().build(
        metrics=agent_metrics(),
        registry_entry=registry_entry(state=AgentState.ON_DEMAND),
        comparisons=(),
        total_ai_cost_eur=D("10"),
        evaluation_report_version="batch10.evaluation.v1",
    )

    assert report.evidence.ablation_comparison_count == 0
    assert report.recommendation.action is StateRecommendationAction.HOLD
    assert report.recommendation.evidence_sufficiency is EvidenceSufficiency.INSUFFICIENT
    assert "INSUFFICIENT_ABLATION_COMPARISONS" in report.recommendation.reason_codes


def test_report_rejects_duplicate_ablation_run_pair() -> None:
    item = comparison(index=1, economic="2")

    with pytest.raises(ValueError, match="duplicate ablation run pair"):
        service().build(
            metrics=agent_metrics(),
            registry_entry=registry_entry(),
            comparisons=(item, item),
            total_ai_cost_eur=D("10"),
            evaluation_report_version="batch10.evaluation.v1",
        )


def test_report_rejects_cross_agent_registry_entry() -> None:
    with pytest.raises(ValueError, match="one agent"):
        service().build(
            metrics=agent_metrics(agent_id="rio"),
            registry_entry=registry_entry(agent_id="berlin"),
            comparisons=(),
            total_ai_cost_eur=D("10"),
            evaluation_report_version="batch10.evaluation.v1",
        )
