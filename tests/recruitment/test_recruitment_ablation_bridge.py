from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.recruitment import (
    RecruitmentBaselineSpec,
    RecruitmentCampaignExecutionReport,
    RecruitmentEvidencePurpose,
    RecruitmentMetricDirection,
    RecruitmentProposal,
    RecruitmentSuccessCriterion,
    RecruitmentVariantExecution,
    RecruitmentAblationSemantics,
    bridge_recruitment_to_ablation,
    build_recruitment_campaign,
    evaluate_recruitment_evidence,
    specify_recruitment_candidate,
)
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.reports import BacktestMetricSnapshot, BacktestPeriodReport
from app.services.backtest.splits import BacktestPeriodRole


def _candidate():
    proposal = RecruitmentProposal(
        recruitment_id="recruitment-19c-001",
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
        budget_limit_eur=Decimal("5"),
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


def _report(variant, *, with_candidate: bool) -> BacktestPeriodReport:
    if with_candidate:
        trading_net = "13"
        economic_net = "11"
        drawdown = "9"
        ai_cost = "3.5"
        closed = 3
        marker = "b"
    else:
        trading_net = "10"
        economic_net = "8"
        drawdown = "12"
        ai_cost = "2"
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
        ai_cost_eur=Decimal(ai_cost),
        economic_net=_metric(economic_net),
        self_funding_ratio=None,
        self_funding_status="UNAVAILABLE",
        business_sha256=marker * 64,
    )


def _case(role: BacktestPeriodRole = BacktestPeriodRole.OOS):
    candidate = _candidate()
    plan = build_recruitment_campaign(
        _source_run(),
        candidate,
        role=role,
        baseline_agents=("berlin", "tokyo"),
    )
    baseline = RecruitmentVariantExecution(
        variant=plan.baseline,
        period_report=_report(plan.baseline, with_candidate=False),
        replay_result=object(),
        evaluation_bundle=object(),
    )
    with_candidate = RecruitmentVariantExecution(
        variant=plan.with_candidate,
        period_report=_report(plan.with_candidate, with_candidate=True),
        replay_result=object(),
        evaluation_bundle=object(),
    )
    execution = RecruitmentCampaignExecutionReport(
        campaign_id=plan.campaign_id,
        comparison_fingerprint=plan.comparison_fingerprint,
        recruitment_id=plan.recruitment_id,
        role=plan.role,
        executions=(baseline, with_candidate),
        execution_fingerprint="e" * 64,
    )
    return candidate, plan, execution


def test_oos_promotion_evidence_bridges_to_batch18_ablation_semantics() -> None:
    candidate, plan, execution = _case()
    gate = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.PROMOTION,
    )
    bridged = bridge_recruitment_to_ablation(plan, candidate, execution, gate)
    comparison = bridged.comparison

    assert bridged.semantics is RecruitmentAblationSemantics.FULL_WITH_CANDIDATE_VS_WITHOUT_CANDIDATE_BASELINE
    assert comparison.agent_id == plan.candidate_agent_id
    assert comparison.baseline_run_id == plan.with_candidate.run.run_id
    assert comparison.ablated_run_id == plan.baseline.run.run_id
    assert comparison.marginal_trading_net.value == Decimal("3")
    assert comparison.marginal_economic_net.value == Decimal("3")
    assert comparison.drawdown_reduction_pct.value == Decimal("3")
    assert comparison.additional_ai_cost_eur == Decimal("1.5")
    assert comparison.closed_trade_count_delta == 1
    assert comparison.is_out_of_sample is True


def test_bridge_reuses_batch18_comparison_fingerprint_and_no_authority() -> None:
    candidate, plan, execution = _case()
    gate = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.PROMOTION,
    )
    bridged = bridge_recruitment_to_ablation(plan, candidate, execution, gate)

    assert bridged.comparison.comparison_fingerprint == plan.comparison_fingerprint
    assert bridged.evidence_gate_fingerprint_sha256 == gate.audit_fingerprint_sha256
    assert len(bridged.audit_fingerprint_sha256) == 64
    assert bridged.auto_apply is False
    assert bridged.registry_mutation is False
    assert bridged.promotion_action is False
    assert bridged.live_authority is False


def test_diagnostic_design_evidence_can_bridge_but_stays_non_oos() -> None:
    candidate, plan, execution = _case(BacktestPeriodRole.DESIGN)
    gate = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.DIAGNOSTIC,
    )
    bridged = bridge_recruitment_to_ablation(plan, candidate, execution, gate)

    assert bridged.purpose is RecruitmentEvidencePurpose.DIAGNOSTIC
    assert bridged.is_out_of_sample is False
    assert bridged.comparison.role == "DESIGN"


def test_blocked_non_oos_promotion_gate_cannot_bridge() -> None:
    candidate, plan, execution = _case(BacktestPeriodRole.DESIGN)
    gate = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.PROMOTION,
    )
    with pytest.raises(ValueError, match="blocked recruitment evidence"):
        bridge_recruitment_to_ablation(plan, candidate, execution, gate)


def test_tampered_gate_fingerprint_cannot_bridge() -> None:
    candidate, plan, execution = _case()
    gate = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.PROMOTION,
    )
    tampered = replace(gate, audit_fingerprint_sha256="f" * 64)
    with pytest.raises(ValueError, match="stale or does not match"):
        bridge_recruitment_to_ablation(plan, candidate, execution, tampered)


def test_bridge_is_deterministic_for_same_frozen_inputs() -> None:
    candidate, plan, execution = _case()
    gate = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.PROMOTION,
    )
    first = bridge_recruitment_to_ablation(plan, candidate, execution, gate)
    second = bridge_recruitment_to_ablation(plan, candidate, execution, gate)
    assert first == second
    assert first.audit_fingerprint_sha256 == second.audit_fingerprint_sha256
