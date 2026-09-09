from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.evaluation.models import Metric
from app.evaluation.task_force import (
    TaskForceRunOutcome,
    compare_task_force_outcomes,
    evaluate_task_force,
    task_force_report_fingerprint,
)
from app.evaluation.task_force_replay import (
    TaskForceReplayCampaignReport,
    TaskForceReplayVariantExecution,
    build_task_force_replay_plan,
)
from app.evaluation.task_force_replay_audit import (
    TaskForceReplayAuditStatus,
    assert_task_force_replay_fresh,
    audit_task_force_replay,
    recompute_task_force_replay_fingerprint,
    seal_task_force_replay,
    task_force_replay_campaign_fingerprint,
    task_force_replay_plan_fingerprint,
)
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.reports import BacktestMetricSnapshot, BacktestPeriodReport
from app.services.backtest.splits import BacktestPeriodRole
from app.task_force.aggregation import (
    TaskForceAggregatedFinding,
    TaskForceAggregatedMember,
    TaskForceReport,
    task_force_execution_fingerprint,
)
from app.task_force.execution import TaskForceMemberAnalysis, TaskForceMemberFinding
from app.task_force.execution_runtime import (
    TaskForceExecutionRunStatus,
    TaskForceExecutionUsageSnapshot,
    TaskForceMemberExecutionRecord,
    TaskForceMemberUsageSnapshot,
    TaskForceMultiMemberExecution,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _source_run() -> BacktestRun:
    dataset = DatasetRef(
        dataset_id="btc-h1-2026",
        version="v1",
        content_sha256="d" * 64,
        symbol="BTCUSDT",
        timeframe="1h",
        source="fixture",
        candle_count=100,
        start_at=NOW - timedelta(days=30),
        end_at=NOW,
    )
    config = BacktestConfig(system_id="balanced_v1", risk_version="risk-v1")
    return BacktestRun.create(dataset=dataset, config=config)


def _task_force_artifacts(opportunity_id: str):
    analysis = TaskForceMemberAnalysis(
        task_force_id="tf-1",
        execution_run_id="tf-run-1",
        member_id="member-1",
        agent_id="berlin",
        answer="trend remains constructive",
        findings=(
            TaskForceMemberFinding(
                finding_id="f-1",
                summary="trend evidence",
                evidence_refs=("market.close",),
            ),
        ),
        uncertainties=("regime may shift",),
        follow_up_questions=("confirm volume",),
        confidence=Decimal("0.70"),
    )
    record = TaskForceMemberExecutionRecord(
        member_id="member-1",
        agent_id="berlin",
        gateway_request_id="11111111-1111-4111-8111-111111111111",
        compute_quote_fingerprint_sha256=SHA_A,
        compute_gate_fingerprint_sha256=SHA_B,
        route_id="economy",
        model_id="mock-economy",
        attempts=1,
        usage_record_count=1,
        actual_cost_eur=Decimal("0.05"),
        latency_ms_total=10,
        analysis=analysis,
    )
    usage_before = TaskForceExecutionUsageSnapshot(
        task_force_id="tf-1",
        spent_total_eur=Decimal("0"),
        used_total_calls=0,
        members=(
            TaskForceMemberUsageSnapshot(
                member_id="member-1",
                agent_id="berlin",
                spent_eur=Decimal("0"),
                used_calls=0,
            ),
        ),
    )
    usage_after = TaskForceExecutionUsageSnapshot(
        task_force_id="tf-1",
        spent_total_eur=Decimal("0.05"),
        used_total_calls=1,
        members=(
            TaskForceMemberUsageSnapshot(
                member_id="member-1",
                agent_id="berlin",
                spent_eur=Decimal("0.05"),
                used_calls=1,
            ),
        ),
    )
    execution = TaskForceMultiMemberExecution(
        task_force_id="tf-1",
        execution_run_id="tf-run-1",
        execution_contract_fingerprint_sha256=SHA_C,
        started_at=NOW - timedelta(seconds=2),
        status=TaskForceExecutionRunStatus.COMPLETED,
        expected_member_count=1,
        completed_member_count=1,
        member_records=(record,),
        usage_before=usage_before,
        usage_after=usage_after,
        gateway_calls_performed=True,
        cost_accounting_complete=True,
        aggregation_ready=True,
    )
    member = TaskForceAggregatedMember(
        member_id="member-1",
        agent_id="berlin",
        task_role="analysis",
        answer=analysis.answer,
        confidence=analysis.confidence,
        finding_ids=("f-1",),
        uncertainties=analysis.uncertainties,
        follow_up_questions=analysis.follow_up_questions,
    )
    finding = TaskForceAggregatedFinding(
        member_id="member-1",
        agent_id="berlin",
        finding_id="f-1",
        summary="trend evidence",
        evidence_refs=("market.close",),
    )
    report = TaskForceReport(
        task_force_id="tf-1",
        execution_run_id="tf-run-1",
        request_id="request-1",
        system_id="balanced_v1",
        opportunity_id=opportunity_id,
        objective="deep analysis",
        question="what matters?",
        execution_contract_fingerprint_sha256=SHA_C,
        execution_fingerprint_sha256=task_force_execution_fingerprint(execution),
        members=(member,),
        findings=(finding,),
        uncertainties=analysis.uncertainties,
        follow_up_questions=analysis.follow_up_questions,
        red_team_required=False,
        red_team_present=False,
        member_actual_cost_eur=Decimal("0.05"),
        member_attempt_count=1,
        aggregated_at=NOW,
        report_fingerprint_sha256=SHA_A,
    )
    report = report.model_copy(
        update={"report_fingerprint_sha256": task_force_report_fingerprint(report)}
    )
    return report, execution


def _period_report(variant, *, trading: str, economic: str, drawdown: str, business: str):
    return BacktestPeriodReport(
        role=BacktestPeriodRole.OOS,
        run_id=variant.run.run_id,
        dataset_id=variant.run.dataset.dataset_id,
        period_start=variant.run.period_start,
        period_end=variant.run.period_end,
        processed_candles=100,
        opportunity_count=10,
        executed_order_count=1,
        closed_trade_count=1,
        trading_net=BacktestMetricSnapshot(Decimal(trading), "AVAILABLE"),
        max_drawdown_pct=BacktestMetricSnapshot(Decimal(drawdown), "AVAILABLE"),
        ai_cost_eur=Decimal("0.10"),
        economic_net=BacktestMetricSnapshot(Decimal(economic), "AVAILABLE"),
        self_funding_ratio=None,
        self_funding_status="AVAILABLE",
        business_sha256=business,
    )


def _campaign():
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    tf_report, tf_execution = _task_force_artifacts(plan.target_opportunity_id)
    baseline_period = _period_report(
        plan.baseline,
        trading="10",
        economic="8",
        drawdown="0.12",
        business="1" * 64,
    )
    treatment_period = _period_report(
        plan.treatment,
        trading="13",
        economic="10",
        drawdown="0.09",
        business="2" * 64,
    )
    baseline = TaskForceReplayVariantExecution(
        variant=plan.baseline,
        period_report=baseline_period,
        replay_result=object(),
        evaluation_bundle=object(),
        task_force_report=None,
        task_force_execution=None,
    )
    treatment = TaskForceReplayVariantExecution(
        variant=plan.treatment,
        period_report=treatment_period,
        replay_result=object(),
        evaluation_bundle=object(),
        task_force_report=tf_report,
        task_force_execution=tf_execution,
    )
    baseline_outcome = TaskForceRunOutcome(
        run_id=baseline_period.run_id,
        comparison_fingerprint=plan.comparison_fingerprint,
        dataset_id=baseline_period.dataset_id,
        role=baseline_period.role.value,
        period_start=baseline_period.period_start,
        period_end=baseline_period.period_end,
        opportunity_count=baseline_period.opportunity_count,
        trading_net=Metric.available(Decimal("10")),
        economic_net=Metric.available(Decimal("8")),
        max_drawdown_pct=Metric.available(Decimal("0.12")),
        includes_task_force=False,
        task_force_report_fingerprint_sha256=None,
        is_out_of_sample=True,
    )
    treatment_outcome = TaskForceRunOutcome(
        run_id=treatment_period.run_id,
        comparison_fingerprint=plan.comparison_fingerprint,
        dataset_id=treatment_period.dataset_id,
        role=treatment_period.role.value,
        period_start=treatment_period.period_start,
        period_end=treatment_period.period_end,
        opportunity_count=treatment_period.opportunity_count,
        trading_net=Metric.available(Decimal("13")),
        economic_net=Metric.available(Decimal("10")),
        max_drawdown_pct=Metric.available(Decimal("0.09")),
        includes_task_force=True,
        task_force_report_fingerprint_sha256=tf_report.report_fingerprint_sha256,
        is_out_of_sample=True,
    )
    comparison = compare_task_force_outcomes(
        baseline_outcome,
        treatment_outcome,
        report=tf_report,
    )
    evaluation = evaluate_task_force(tf_report, tf_execution, comparison=comparison)
    campaign = TaskForceReplayCampaignReport(
        campaign_id=plan.campaign_id,
        comparison_fingerprint=plan.comparison_fingerprint,
        target_opportunity_id=plan.target_opportunity_id,
        role=BacktestPeriodRole.OOS,
        baseline=baseline,
        treatment=treatment,
        comparison=comparison,
        task_force_evaluation=evaluation,
        replay_fingerprint_sha256=SHA_A,
    )
    campaign = replace(
        campaign,
        replay_fingerprint_sha256=recompute_task_force_replay_fingerprint(campaign),
    )
    return plan, campaign


def test_seal_binds_all_replay_evidence_without_authority():
    plan, campaign = _campaign()
    seal = seal_task_force_replay(plan, campaign, sealed_at=NOW + timedelta(minutes=1))
    assert seal.campaign_id == campaign.campaign_id
    assert seal.plan_fingerprint_sha256 == task_force_replay_plan_fingerprint(plan)
    assert seal.campaign_fingerprint_sha256 == task_force_replay_campaign_fingerprint(campaign)
    assert seal.paper_only is True
    assert seal.advisory_only is True
    assert seal.execution_authorized is False
    assert seal.risk_authority is False
    assert seal.live_authority is False


def test_seal_is_deterministic_for_same_inputs_except_explicit_timestamp():
    plan, campaign = _campaign()
    first = seal_task_force_replay(plan, campaign, sealed_at=NOW)
    second = seal_task_force_replay(plan, campaign, sealed_at=NOW)
    assert first == second


def test_seal_rejects_stale_replay_fingerprint():
    plan, campaign = _campaign()
    stale = replace(campaign, replay_fingerprint_sha256="f" * 64)
    with pytest.raises(ValueError, match="replay fingerprint is stale"):
        seal_task_force_replay(plan, stale, sealed_at=NOW)


def test_seal_rejects_stale_task_force_report_fingerprint():
    plan, campaign = _campaign()
    tf_report = campaign.treatment.task_force_report
    assert tf_report is not None
    stale_tf = tf_report.model_copy(update={"report_fingerprint_sha256": "e" * 64})
    treatment = replace(campaign.treatment, task_force_report=stale_tf)
    stale = replace(campaign, treatment=treatment)
    with pytest.raises(ValueError, match="Task Force report fingerprint is stale"):
        seal_task_force_replay(plan, stale, sealed_at=NOW)


def test_seal_rejects_plan_report_binding_mismatch():
    plan, campaign = _campaign()
    other = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-2")
    with pytest.raises(ValueError, match="campaign_id"):
        seal_task_force_replay(other, campaign, sealed_at=NOW)


def test_fresh_audit_and_assertion_pass():
    plan, campaign = _campaign()
    seal = seal_task_force_replay(plan, campaign, sealed_at=NOW)
    audit = audit_task_force_replay(seal, plan, campaign, audited_at=NOW + timedelta(minutes=1))
    assert audit.status is TaskForceReplayAuditStatus.FRESH
    assert audit.reason_codes == ("REPLAY_SEAL_FRESH",)
    assert audit.execution_authorized is False
    assert_task_force_replay_fresh(audit)


def test_plan_change_is_stale():
    plan, campaign = _campaign()
    seal = seal_task_force_replay(plan, campaign, sealed_at=NOW)
    changed = replace(plan, source_run_id="different-source-run")
    audit = audit_task_force_replay(seal, changed, campaign, audited_at=NOW)
    assert audit.status is TaskForceReplayAuditStatus.STALE
    assert "PLAN_CHANGED" in audit.reason_codes


def test_baseline_business_change_is_stale():
    plan, campaign = _campaign()
    seal = seal_task_force_replay(plan, campaign, sealed_at=NOW)
    period = replace(campaign.baseline.period_report, business_sha256="3" * 64)
    baseline = replace(campaign.baseline, period_report=period)
    changed = replace(campaign, baseline=baseline)
    audit = audit_task_force_replay(seal, plan, changed, audited_at=NOW)
    assert "BASELINE_BUSINESS_CHANGED" in audit.reason_codes
    assert "CAMPAIGN_REPORT_CHANGED" in audit.reason_codes


def test_treatment_business_change_is_stale():
    plan, campaign = _campaign()
    seal = seal_task_force_replay(plan, campaign, sealed_at=NOW)
    period = replace(campaign.treatment.period_report, business_sha256="4" * 64)
    treatment = replace(campaign.treatment, period_report=period)
    changed = replace(campaign, treatment=treatment)
    audit = audit_task_force_replay(seal, plan, changed, audited_at=NOW)
    assert "TREATMENT_BUSINESS_CHANGED" in audit.reason_codes


def test_outcome_comparison_change_is_stale_even_if_outer_replay_hash_is_unchanged():
    plan, campaign = _campaign()
    seal = seal_task_force_replay(plan, campaign, sealed_at=NOW)
    changed_comparison = replace(
        campaign.comparison,
        marginal_economic_net=Metric.available(Decimal("999")),
    )
    changed = replace(campaign, comparison=changed_comparison)
    audit = audit_task_force_replay(seal, plan, changed, audited_at=NOW)
    assert "OUTCOME_COMPARISON_CHANGED" in audit.reason_codes
    assert "CAMPAIGN_REPORT_CHANGED" in audit.reason_codes


def test_task_force_evaluation_change_is_stale():
    plan, campaign = _campaign()
    seal = seal_task_force_replay(plan, campaign, sealed_at=NOW)
    changed_eval = replace(campaign.task_force_evaluation, finding_count=42)
    changed = replace(campaign, task_force_evaluation=changed_eval)
    audit = audit_task_force_replay(seal, plan, changed, audited_at=NOW)
    assert "TASK_FORCE_EVALUATION_CHANGED" in audit.reason_codes


def test_internal_replay_fingerprint_staleness_is_detected():
    plan, campaign = _campaign()
    seal = seal_task_force_replay(plan, campaign, sealed_at=NOW)
    changed = replace(campaign, replay_fingerprint_sha256="9" * 64)
    audit = audit_task_force_replay(seal, plan, changed, audited_at=NOW)
    assert "REPLAY_FINGERPRINT_CHANGED" in audit.reason_codes
    assert "REPLAY_FINGERPRINT_STALE" in audit.reason_codes


def test_internal_task_force_report_staleness_is_detected():
    plan, campaign = _campaign()
    seal = seal_task_force_replay(plan, campaign, sealed_at=NOW)
    tf_report = campaign.treatment.task_force_report
    assert tf_report is not None
    stale_tf = tf_report.model_copy(update={"report_fingerprint_sha256": "8" * 64})
    treatment = replace(campaign.treatment, task_force_report=stale_tf)
    changed = replace(campaign, treatment=treatment)
    audit = audit_task_force_replay(seal, plan, changed, audited_at=NOW)
    assert "TASK_FORCE_REPORT_CHANGED" in audit.reason_codes
    assert "TASK_FORCE_REPORT_FINGERPRINT_STALE" in audit.reason_codes


def test_assert_fresh_rejects_stale_audit():
    plan, campaign = _campaign()
    seal = seal_task_force_replay(plan, campaign, sealed_at=NOW)
    changed = replace(plan, source_run_id="different-source-run")
    audit = audit_task_force_replay(seal, changed, campaign, audited_at=NOW)
    with pytest.raises(PermissionError, match="stale"):
        assert_task_force_replay_fresh(audit)


def test_seal_requires_timezone_aware_timestamp():
    plan, campaign = _campaign()
    with pytest.raises(ValueError, match="timezone-aware"):
        seal_task_force_replay(plan, campaign, sealed_at=datetime(2026, 9, 9, 12, 0))
