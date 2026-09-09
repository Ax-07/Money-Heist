from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.evaluation.models import AgentMetrics, Metric
from app.recruitment import (
    RecruitmentBaselineSpec,
    RecruitmentCampaignExecutionReport,
    RecruitmentCostEvidenceBasis,
    RecruitmentEvidencePurpose,
    RecruitmentMetricDirection,
    RecruitmentProposal,
    RecruitmentSuccessCriterion,
    RecruitmentVariantExecution,
    bridge_recruitment_to_ablation,
    build_candidate_reputation_evidence,
    build_recruitment_campaign,
    evaluate_recruitment_evidence,
    specify_recruitment_candidate,
)
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.reports import BacktestMetricSnapshot, BacktestPeriodReport
from app.services.backtest.splits import BacktestPeriodRole


def _candidate(*, budget: str = "5"):
    proposal = RecruitmentProposal(
        recruitment_id="recruitment-19c-002",
        proposed_name="Marseille",
        role="liquidation_specialist",
        problem="Liquidation context is not covered by the incumbent crew.",
        hypothesis="The candidate improves OOS economic evidence net of AI cost.",
        trigger_evidence_refs=("eval:error-family:liquidation",),
    )
    return specify_recruitment_candidate(
        proposal,
        required_data=("liquidations",),
        allowed_tools=("get_liquidation_context",),
        model_class="specialist-small",
        budget_limit_eur=Decimal(budget),
        evaluation_window="frozen DESIGN/VALIDATION/OOS windows",
        baseline=RecruitmentBaselineSpec(
            baseline_id="balanced-v1-incumbent",
            system_id="balanced_v1",
            description="Existing crew without the candidate.",
        ),
        success_criteria=(
            RecruitmentSuccessCriterion(
                metric_key="marginal_economic_net_eur",
                direction=RecruitmentMetricDirection.AT_LEAST,
                threshold=Decimal("0"),
                primary=True,
                rationale="Primary criterion frozen before OOS.",
            ),
        ),
    )


def _source_run() -> BacktestRun:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = []
    for index in range(3):
        open_at = start + timedelta(hours=index)
        candles.append(
            {
                "open_time": open_at,
                "close_time": open_at + timedelta(minutes=59),
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100.5"),
                "volume": Decimal("1"),
            }
        )
    dataset = DatasetRef.from_candles(
        candles,
        symbol="BTC/EUR",
        timeframe="1h",
        source="test",
    )
    return BacktestRun.create(
        dataset=dataset,
        config=BacktestConfig(
            system_id="balanced_v1",
            risk_version="risk-v1",
            code_version="96b2288-test",
        ),
    )


def _metric(value: str) -> BacktestMetricSnapshot:
    return BacktestMetricSnapshot(value=Decimal(value), status="AVAILABLE")


def _period_report(variant, *, with_candidate: bool, ai_cost: str | None = None):
    if with_candidate:
        trading_net = "13"
        economic_net = "11"
        drawdown = "9"
        total_ai = ai_cost or "3.5"
        closed = 3
        marker = "b"
    else:
        trading_net = "10"
        economic_net = "8"
        drawdown = "12"
        total_ai = ai_cost or "2"
        closed = 2
        marker = "a"
    return BacktestPeriodReport(
        role=variant.role,
        run_id=variant.run.run_id,
        dataset_id=variant.run.dataset.dataset_id,
        period_start=variant.run.period_start,
        period_end=variant.run.period_end,
        processed_candles=3,
        opportunity_count=2,
        executed_order_count=closed,
        closed_trade_count=closed,
        trading_net=_metric(trading_net),
        max_drawdown_pct=_metric(drawdown),
        ai_cost_eur=Decimal(total_ai),
        economic_net=_metric(economic_net),
        self_funding_ratio=None,
        self_funding_status="UNAVAILABLE",
        business_sha256=marker * 64,
    )


def _agent_metrics(agent_id: str, *, cost: str = "1.2") -> AgentMetrics:
    return AgentMetrics(
        agent_id=agent_id,
        call_count=4,
        attempt_count=4,
        total_cost_eur=Decimal(cost),
        average_cost_eur=Metric.available(Decimal(cost) / Decimal("4")),
        average_latency_ms=Metric.available(Decimal("120")),
        participation_frequency=Metric.available(Decimal("0.8")),
        disagreement_frequency=Metric.available(Decimal("0.25")),
        average_confidence=Metric.available(Decimal("0.7")),
        stance_counts={"LONG": 3, "NEUTRAL": 1},
        final_decision_counts={"TRADE": 2, "NO_TRADE": 2},
        prompt_versions=("candidate-v1",),
        route_ids=("specialist",),
        model_ids=("specialist-small",),
    )


def _eval_bundle(*, total_cost: str, agents=(), by_agent=None, version: str = "batch10.v1"):
    return SimpleNamespace(
        report=SimpleNamespace(
            report_version=version,
            agents=tuple(agents),
            ai_costs=SimpleNamespace(
                total_cost_eur=Decimal(total_cost),
                by_agent={} if by_agent is None else dict(by_agent),
            ),
        )
    )


def _case(
    role: BacktestPeriodRole = BacktestPeriodRole.OOS,
    *,
    budget: str = "5",
    direct_candidate_cost: str = "1.2",
    with_total_cost: str = "3.5",
):
    candidate = _candidate(budget=budget)
    plan = build_recruitment_campaign(
        _source_run(),
        candidate,
        role=role,
        baseline_agents=("berlin", "tokyo"),
    )
    metrics = _agent_metrics(plan.candidate_agent_id, cost=direct_candidate_cost)
    baseline = RecruitmentVariantExecution(
        variant=plan.baseline,
        period_report=_period_report(plan.baseline, with_candidate=False),
        replay_result=object(),
        evaluation_bundle=_eval_bundle(
            total_cost="2",
            agents=(),
            by_agent={"berlin": Decimal("2")},
        ),
    )
    with_candidate = RecruitmentVariantExecution(
        variant=plan.with_candidate,
        period_report=_period_report(
            plan.with_candidate,
            with_candidate=True,
            ai_cost=with_total_cost,
        ),
        replay_result=object(),
        evaluation_bundle=_eval_bundle(
            total_cost=with_total_cost,
            agents=(metrics,),
            by_agent={
                plan.candidate_agent_id: Decimal(direct_candidate_cost),
                "berlin": Decimal(with_total_cost) - Decimal(direct_candidate_cost),
            },
        ),
    )
    execution = RecruitmentCampaignExecutionReport(
        campaign_id=plan.campaign_id,
        comparison_fingerprint=plan.comparison_fingerprint,
        recruitment_id=plan.recruitment_id,
        role=plan.role,
        executions=(baseline, with_candidate),
        execution_fingerprint="e" * 64,
    )
    purpose = (
        RecruitmentEvidencePurpose.PROMOTION
        if role is BacktestPeriodRole.OOS
        else RecruitmentEvidencePurpose.DIAGNOSTIC
    )
    gate = evaluate_recruitment_evidence(plan, candidate, execution, purpose=purpose)
    bridge = bridge_recruitment_to_ablation(plan, candidate, execution, gate)
    return candidate, plan, execution, gate, bridge


def test_builds_batch18_reputation_dimensions_and_distinct_candidate_costs() -> None:
    candidate, plan, execution, gate, bridge = _case()
    report = build_candidate_reputation_evidence(
        plan,
        candidate,
        execution,
        gate,
        bridge,
    )

    assert report.candidate_agent_id == plan.candidate_agent_id
    assert report.reputation.call_count == 4
    assert report.reputation.ablation_comparison_count == 1
    assert report.reputation.oos_ablation_comparison_count == 1
    assert report.reputation.directional_agreement.value == Decimal("0.75")
    assert report.reputation.marginal_trading_net.value == Decimal("3")
    assert report.reputation.marginal_economic_net.value == Decimal("3")
    assert report.reputation.drawdown_reduction_pct.value == Decimal("3")

    assert report.costs.candidate_direct_ai_cost_eur == Decimal("1.2")
    assert report.costs.marginal_total_ai_cost_eur == Decimal("1.5")
    assert report.costs.candidate_direct_ai_cost_eur != report.costs.marginal_total_ai_cost_eur
    assert report.costs.candidate_direct_cost_share_ratio == Decimal("1.2") / Decimal("3.5")
    assert report.costs.candidate_budget_utilization_ratio == Decimal("0.24")
    assert report.costs.candidate_direct_cost_within_budget is True
    assert report.costs.basis is RecruitmentCostEvidenceBasis.ESTIMATED_AI_USAGE_EUR_IN_SIMULATED_HISTORICAL_REPLAY_PAPER


def test_candidate_reputation_evidence_has_no_operational_state_or_promotion_authority() -> None:
    candidate, plan, execution, gate, bridge = _case()
    report = build_candidate_reputation_evidence(plan, candidate, execution, gate, bridge)

    assert not hasattr(report.reputation, "suggested_state")
    assert not hasattr(report.reputation, "state_reasons")
    assert report.reputation.operational_state_advisory_used is False
    assert report.auto_apply is False
    assert report.registry_mutation is False
    assert report.promotion_action is False
    assert report.live_authority is False


def test_over_budget_is_recorded_as_evidence_not_auto_action() -> None:
    candidate, plan, execution, gate, bridge = _case(
        budget="1",
        direct_candidate_cost="1.2",
    )
    report = build_candidate_reputation_evidence(plan, candidate, execution, gate, bridge)

    assert report.costs.candidate_budget_utilization_ratio == Decimal("1.2")
    assert report.costs.candidate_direct_cost_within_budget is False
    assert report.auto_apply is False
    assert report.promotion_action is False


def test_diagnostic_design_evidence_retains_non_oos_reputation_count() -> None:
    candidate, plan, execution, gate, bridge = _case(BacktestPeriodRole.DESIGN)
    report = build_candidate_reputation_evidence(plan, candidate, execution, gate, bridge)

    assert report.purpose is RecruitmentEvidencePurpose.DIAGNOSTIC
    assert report.reputation.ablation_comparison_count == 1
    assert report.reputation.oos_ablation_comparison_count == 0


def test_missing_candidate_agent_metrics_is_rejected() -> None:
    candidate, plan, execution, gate, bridge = _case()
    bad_candidate = replace(
        execution.with_candidate,
        evaluation_bundle=_eval_bundle(
            total_cost="3.5",
            agents=(),
            by_agent={plan.candidate_agent_id: Decimal("1.2"), "berlin": Decimal("2.3")},
        ),
    )
    bad_execution = replace(execution, executions=(execution.baseline, bad_candidate))
    with pytest.raises(ValueError, match="exactly one candidate AgentMetrics"):
        build_candidate_reputation_evidence(plan, candidate, bad_execution, gate, bridge)


def test_candidate_presence_in_baseline_metrics_is_rejected() -> None:
    candidate, plan, execution, gate, bridge = _case()
    contaminated = _agent_metrics(plan.candidate_agent_id, cost="0")
    bad_baseline = replace(
        execution.baseline,
        evaluation_bundle=_eval_bundle(
            total_cost="2",
            agents=(contaminated,),
            by_agent={"berlin": Decimal("2")},
        ),
    )
    bad_execution = replace(execution, executions=(bad_baseline, execution.with_candidate))
    with pytest.raises(ValueError, match="BASELINE evaluation must not contain"):
        build_candidate_reputation_evidence(plan, candidate, bad_execution, gate, bridge)


def test_candidate_agent_metrics_cost_must_match_by_agent_cost() -> None:
    candidate, plan, execution, gate, bridge = _case()
    bad_bundle = _eval_bundle(
        total_cost="3.5",
        agents=(_agent_metrics(plan.candidate_agent_id, cost="1.2"),),
        by_agent={plan.candidate_agent_id: Decimal("1.1"), "berlin": Decimal("2.4")},
    )
    bad_candidate = replace(execution.with_candidate, evaluation_bundle=bad_bundle)
    bad_execution = replace(execution, executions=(execution.baseline, bad_candidate))
    with pytest.raises(ValueError, match="cost does not match ai_costs.by_agent"):
        build_candidate_reputation_evidence(plan, candidate, bad_execution, gate, bridge)


def test_stale_ablation_bridge_is_rejected() -> None:
    candidate, plan, execution, gate, bridge = _case()
    stale = replace(bridge, audit_fingerprint_sha256="f" * 64)
    with pytest.raises(ValueError, match="ablation bridge is stale"):
        build_candidate_reputation_evidence(plan, candidate, execution, gate, stale)


def test_same_frozen_evidence_is_deterministic() -> None:
    candidate, plan, execution, gate, bridge = _case()
    first = build_candidate_reputation_evidence(plan, candidate, execution, gate, bridge)
    second = build_candidate_reputation_evidence(plan, candidate, execution, gate, bridge)
    assert first == second
    assert first.audit_fingerprint_sha256 == second.audit_fingerprint_sha256
