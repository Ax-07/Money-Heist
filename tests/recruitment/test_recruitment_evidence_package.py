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
    RecruitmentEvidenceBasis,
    RecruitmentEvidencePackageBasis,
    RecruitmentEvidencePurpose,
    RecruitmentMetricDirection,
    RecruitmentProposal,
    RecruitmentSuccessCriterion,
    RecruitmentVariantExecution,
    bridge_recruitment_to_ablation,
    build_candidate_evidence_package,
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



def _package_case(role: BacktestPeriodRole = BacktestPeriodRole.OOS):
    candidate, plan, execution, gate, bridge = _case(role)
    reputation = build_candidate_reputation_evidence(
        plan,
        candidate,
        execution,
        gate,
        bridge,
    )
    package = build_candidate_evidence_package(
        plan,
        candidate,
        execution,
        gate,
        bridge,
        reputation,
    )
    return candidate, plan, execution, gate, bridge, reputation, package


def test_package_freezes_complete_verified_evidence_chain() -> None:
    candidate, plan, execution, gate, bridge, reputation, package = _package_case()

    assert package.recruitment_id == plan.recruitment_id
    assert package.candidate_agent_id == plan.candidate_agent_id
    assert package.purpose is RecruitmentEvidencePurpose.PROMOTION
    assert package.evidence_gate == gate
    assert package.ablation_bridge == bridge
    assert package.reputation_evidence == reputation
    assert package.success_criteria_snapshot == candidate.success_criteria
    assert package.lineage.campaign_id == plan.campaign_id
    assert package.lineage.execution_fingerprint == execution.execution_fingerprint
    assert package.lineage.evidence_gate_fingerprint_sha256 == gate.audit_fingerprint_sha256
    assert package.lineage.ablation_bridge_fingerprint_sha256 == bridge.audit_fingerprint_sha256
    assert package.lineage.reputation_evidence_fingerprint_sha256 == reputation.audit_fingerprint_sha256


def test_package_lineage_preserves_simulated_paper_provenance() -> None:
    _, plan, execution, _, _, _, package = _package_case()

    assert package.lineage.evidence_basis is RecruitmentEvidenceBasis.SIMULATED_HISTORICAL_REPLAY_PAPER
    assert package.lineage.baseline_run_id == plan.baseline.run.run_id
    assert package.lineage.candidate_run_id == plan.with_candidate.run.run_id
    assert package.lineage.baseline_business_sha256 == execution.baseline.period_report.business_sha256
    assert package.lineage.candidate_business_sha256 == execution.with_candidate.period_report.business_sha256
    assert package.basis is RecruitmentEvidencePackageBasis.AUDITABLE_CANDIDATE_EVIDENCE


def test_package_explicitly_does_not_evaluate_criteria_or_recommend() -> None:
    _, _, _, _, _, _, package = _package_case()

    assert package.criteria_evaluation_performed is False
    assert package.recommendation_generated is False
    assert package.auto_apply is False
    assert package.registry_mutation is False
    assert package.promotion_action is False
    assert package.live_authority is False


def test_diagnostic_design_package_stays_diagnostic_and_non_oos() -> None:
    _, _, _, _, _, _, package = _package_case(BacktestPeriodRole.DESIGN)

    assert package.purpose is RecruitmentEvidencePurpose.DIAGNOSTIC
    assert package.evidence_gate.is_out_of_sample is False
    assert package.ablation_bridge.is_out_of_sample is False
    assert package.reputation_evidence.reputation.oos_ablation_comparison_count == 0


def test_same_frozen_inputs_produce_same_package_and_fingerprint() -> None:
    candidate, plan, execution, gate, bridge, reputation, first = _package_case()
    second = build_candidate_evidence_package(
        plan,
        candidate,
        execution,
        gate,
        bridge,
        reputation,
    )

    assert first == second
    assert first.audit_fingerprint_sha256 == second.audit_fingerprint_sha256
    assert len(first.lineage.candidate_spec_fingerprint_sha256) == 64


def test_stale_gate_is_rejected_before_packaging() -> None:
    candidate, plan, execution, gate, bridge, reputation, _ = _package_case()
    stale = replace(gate, audit_fingerprint_sha256="f" * 64)

    with pytest.raises(ValueError, match="evidence gate is stale"):
        build_candidate_evidence_package(
            plan,
            candidate,
            execution,
            stale,
            bridge,
            reputation,
        )


def test_stale_bridge_is_rejected_before_packaging() -> None:
    candidate, plan, execution, gate, bridge, reputation, _ = _package_case()
    stale = replace(bridge, audit_fingerprint_sha256="f" * 64)

    with pytest.raises(ValueError, match="ablation bridge is stale"):
        build_candidate_evidence_package(
            plan,
            candidate,
            execution,
            gate,
            stale,
            reputation,
        )


def test_stale_reputation_evidence_is_rejected_before_packaging() -> None:
    candidate, plan, execution, gate, bridge, reputation, _ = _package_case()
    stale = replace(reputation, audit_fingerprint_sha256="f" * 64)

    with pytest.raises(ValueError, match="candidate reputation evidence is stale"):
        build_candidate_evidence_package(
            plan,
            candidate,
            execution,
            gate,
            bridge,
            stale,
        )


def test_candidate_spec_drift_after_campaign_planning_is_rejected() -> None:
    candidate, plan, execution, gate, bridge, reputation, _ = _package_case()
    drifted = candidate.model_copy(update={"budget_limit_eur": Decimal("999")})

    with pytest.raises(ValueError, match="candidate spec changed after campaign planning"):
        build_candidate_evidence_package(
            plan,
            drifted,
            execution,
            gate,
            bridge,
            reputation,
        )



def test_model_or_tool_drift_after_campaign_planning_is_rejected() -> None:
    candidate, plan, execution, gate, bridge, reputation, _ = _package_case()
    drifted = candidate.model_copy(
        update={
            "model_class": "specialist-large",
            "allowed_tools": ("get_liquidation_context", "get_extra_context"),
        }
    )

    with pytest.raises(ValueError, match="candidate spec changed after campaign planning"):
        build_candidate_evidence_package(
            plan,
            drifted,
            execution,
            gate,
            bridge,
            reputation,
        )

def test_package_rejects_tampered_lineage_with_stale_package_fingerprint() -> None:
    _, _, _, _, _, _, package = _package_case()
    tampered_lineage = replace(
        package.lineage,
        candidate_spec_fingerprint_sha256="f" * 64,
    )

    with pytest.raises(ValueError, match="package fingerprint does not match payload"):
        replace(package, lineage=tampered_lineage)
