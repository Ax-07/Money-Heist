from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.evaluation.models import Metric, MetricStatus
from app.evaluation.task_force import (
    TaskForceRunOutcome,
    compare_task_force_outcomes,
    evaluate_task_force,
    task_force_report_fingerprint,
)
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


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def _analysis(member_id: str, agent_id: str, finding_id: str) -> TaskForceMemberAnalysis:
    return TaskForceMemberAnalysis(
        task_force_id="tf-1",
        execution_run_id="run-1",
        member_id=member_id,
        agent_id=agent_id,
        answer=f"analysis from {agent_id}",
        findings=(
            TaskForceMemberFinding(
                finding_id=finding_id,
                summary=f"finding from {agent_id}",
                evidence_refs=("market.close",),
            ),
        ),
        uncertainties=(f"uncertainty-{agent_id}",),
        follow_up_questions=(f"question-{agent_id}",),
        confidence=Decimal("0.70"),
    )


def _record(
    member_id: str,
    agent_id: str,
    finding_id: str,
    *,
    cost: str,
    latency_ms: int,
    attempts: int = 1,
) -> TaskForceMemberExecutionRecord:
    return TaskForceMemberExecutionRecord(
        member_id=member_id,
        agent_id=agent_id,
        gateway_request_id=str(uuid4()),
        compute_quote_fingerprint_sha256=SHA_A,
        compute_gate_fingerprint_sha256=SHA_B,
        route_id="economy",
        model_id="mock-economy",
        attempts=attempts,
        usage_record_count=attempts,
        actual_cost_eur=Decimal(cost),
        latency_ms_total=latency_ms,
        analysis=_analysis(member_id, agent_id, finding_id),
    )


def _fixtures(*, zero_cost: bool = False):
    first_cost = "0" if zero_cost else "0.03"
    second_cost = "0" if zero_cost else "0.02"
    records = (
        _record("member-1", "berlin", "f-1", cost=first_cost, latency_ms=10),
        _record("member-2", "tokyo", "f-2", cost=second_cost, latency_ms=20, attempts=2),
    )
    total_cost = sum((item.actual_cost_eur for item in records), Decimal("0"))
    usage_members = tuple(
        TaskForceMemberUsageSnapshot(
            member_id=item.member_id,
            agent_id=item.agent_id,
            spent_eur=item.actual_cost_eur,
            used_calls=1,
        )
        for item in records
    )
    usage_after = TaskForceExecutionUsageSnapshot(
        task_force_id="tf-1",
        spent_total_eur=total_cost,
        used_total_calls=2,
        members=usage_members,
    )
    usage_before = TaskForceExecutionUsageSnapshot(
        task_force_id="tf-1",
        spent_total_eur=Decimal("0"),
        used_total_calls=0,
        members=tuple(
            TaskForceMemberUsageSnapshot(
                member_id=item.member_id,
                agent_id=item.agent_id,
                spent_eur=Decimal("0"),
                used_calls=0,
            )
            for item in records
        ),
    )
    execution = TaskForceMultiMemberExecution(
        task_force_id="tf-1",
        execution_run_id="run-1",
        execution_contract_fingerprint_sha256=SHA_C,
        started_at=NOW,
        status=TaskForceExecutionRunStatus.COMPLETED,
        expected_member_count=2,
        completed_member_count=2,
        member_records=records,
        usage_before=usage_before,
        usage_after=usage_after,
        gateway_calls_performed=True,
        cost_accounting_complete=True,
        aggregation_ready=True,
    )
    members = tuple(
        TaskForceAggregatedMember(
            member_id=item.member_id,
            agent_id=item.agent_id,
            task_role="analysis",
            answer=item.analysis.answer,
            confidence=item.analysis.confidence,
            finding_ids=tuple(f.finding_id for f in item.analysis.findings),
            uncertainties=item.analysis.uncertainties,
            follow_up_questions=item.analysis.follow_up_questions,
        )
        for item in records
    )
    findings = tuple(
        TaskForceAggregatedFinding(
            member_id=item.member_id,
            agent_id=item.agent_id,
            finding_id=finding.finding_id,
            summary=finding.summary,
            evidence_refs=finding.evidence_refs,
        )
        for item in records
        for finding in item.analysis.findings
    )
    report = TaskForceReport(
        task_force_id="tf-1",
        execution_run_id="run-1",
        request_id="request-1",
        system_id="balanced_v1",
        opportunity_id="opportunity-1",
        objective="deep analysis",
        question="what matters?",
        execution_contract_fingerprint_sha256=SHA_C,
        execution_fingerprint_sha256=task_force_execution_fingerprint(execution),
        members=members,
        findings=findings,
        uncertainties=("uncertainty-berlin", "uncertainty-tokyo"),
        follow_up_questions=("question-berlin", "question-tokyo"),
        red_team_required=False,
        red_team_present=False,
        member_actual_cost_eur=total_cost,
        member_attempt_count=sum(item.attempts for item in records),
        aggregated_at=NOW + timedelta(seconds=2),
        report_fingerprint_sha256=SHA_A,
    )
    report = report.model_copy(
        update={"report_fingerprint_sha256": task_force_report_fingerprint(report)}
    )
    return report, execution


def _outcomes(report: TaskForceReport):
    common = dict(
        comparison_fingerprint="d" * 64,
        dataset_id="btc-h1-2026",
        role="OOS",
        period_start=NOW - timedelta(days=30),
        period_end=NOW - timedelta(days=1),
        opportunity_count=25,
        is_out_of_sample=True,
    )
    baseline = TaskForceRunOutcome(
        run_id="baseline",
        trading_net=Metric.available(Decimal("10")),
        economic_net=Metric.available(Decimal("8")),
        max_drawdown_pct=Metric.available(Decimal("0.12")),
        includes_task_force=False,
        task_force_report_fingerprint_sha256=None,
        **common,
    )
    treatment = TaskForceRunOutcome(
        run_id="treatment",
        trading_net=Metric.available(Decimal("13")),
        economic_net=Metric.available(Decimal("10")),
        max_drawdown_pct=Metric.available(Decimal("0.09")),
        includes_task_force=True,
        task_force_report_fingerprint_sha256=report.report_fingerprint_sha256,
        **common,
    )
    return baseline, treatment


def test_operational_metrics_are_available_without_economic_baseline():
    report, execution = _fixtures()
    result = evaluate_task_force(report, execution)
    assert result.member_count == 2
    assert result.total_actual_cost_eur == Decimal("0.05")
    assert dict(result.cost_by_agent) == {
        "berlin": Decimal("0.03"),
        "tokyo": Decimal("0.02"),
    }
    assert result.total_attempt_count == 3
    assert result.total_usage_record_count == 3
    assert result.total_latency_ms == 30
    assert result.wall_clock_duration_ms == 2000
    assert result.average_cost_per_member.value == Decimal("0.025")
    assert result.marginal_economic_net.status is MetricStatus.UNAVAILABLE
    assert result.comparison_fingerprint is None


def test_explicit_comparison_computes_marginal_metrics_with_expected_signs():
    report, _ = _fixtures()
    baseline, treatment = _outcomes(report)
    comparison = compare_task_force_outcomes(baseline, treatment, report=report)
    assert comparison.marginal_trading_net.value == Decimal("3")
    assert comparison.marginal_economic_net.value == Decimal("2")
    assert comparison.drawdown_reduction_pct.value == Decimal("0.03")
    assert comparison.is_out_of_sample is True


def test_evaluation_uses_comparison_without_creating_magic_score():
    report, execution = _fixtures()
    baseline, treatment = _outcomes(report)
    comparison = compare_task_force_outcomes(baseline, treatment, report=report)
    result = evaluate_task_force(report, execution, comparison=comparison)
    assert result.marginal_economic_net.value == Decimal("2")
    assert result.marginal_economic_net_per_ai_eur.value == Decimal("4E+1")
    assert result.comparison_is_out_of_sample is True
    assert len(result.evaluation_fingerprint_sha256) == 64
    assert result.advisory_only is True
    assert result.automatic_state_change is False
    assert result.trade_proposal_authority is False
    assert result.risk_authority is False
    assert result.live_authority is False


def test_comparison_requires_identical_comparison_fingerprint():
    report, _ = _fixtures()
    baseline, treatment = _outcomes(report)
    treatment = replace(treatment, comparison_fingerprint="e" * 64)
    with pytest.raises(ValueError, match="comparison_fingerprint"):
        compare_task_force_outcomes(baseline, treatment, report=report)


def test_baseline_must_exclude_task_force():
    report, _ = _fixtures()
    baseline, treatment = _outcomes(report)
    with pytest.raises(ValueError, match="baseline run must exclude"):
        compare_task_force_outcomes(
            TaskForceRunOutcome(
                run_id="bad-baseline",
                comparison_fingerprint=baseline.comparison_fingerprint,
                dataset_id=baseline.dataset_id,
                role=baseline.role,
                period_start=baseline.period_start,
                period_end=baseline.period_end,
                opportunity_count=baseline.opportunity_count,
                trading_net=baseline.trading_net,
                economic_net=baseline.economic_net,
                max_drawdown_pct=baseline.max_drawdown_pct,
                includes_task_force=True,
                task_force_report_fingerprint_sha256=report.report_fingerprint_sha256,
                is_out_of_sample=baseline.is_out_of_sample,
            ),
            treatment,
            report=report,
        )


def test_treatment_must_bind_exact_evaluated_report():
    report, _ = _fixtures()
    baseline, treatment = _outcomes(report)
    treatment = TaskForceRunOutcome(
        run_id=treatment.run_id,
        comparison_fingerprint=treatment.comparison_fingerprint,
        dataset_id=treatment.dataset_id,
        role=treatment.role,
        period_start=treatment.period_start,
        period_end=treatment.period_end,
        opportunity_count=treatment.opportunity_count,
        trading_net=treatment.trading_net,
        economic_net=treatment.economic_net,
        max_drawdown_pct=treatment.max_drawdown_pct,
        includes_task_force=True,
        task_force_report_fingerprint_sha256="e" * 64,
        is_out_of_sample=treatment.is_out_of_sample,
    )
    with pytest.raises(ValueError, match="does not bind"):
        compare_task_force_outcomes(baseline, treatment, report=report)


def test_report_execution_identity_mismatch_is_rejected():
    report, execution = _fixtures()
    execution = execution.model_copy(update={"task_force_id": "other"})
    with pytest.raises(ValueError, match="task_force_id"):
        evaluate_task_force(report, execution)


def test_stale_report_fingerprint_is_rejected():
    report, execution = _fixtures()
    report = report.model_copy(update={"objective": "tampered"})
    with pytest.raises(ValueError, match="report fingerprint"):
        evaluate_task_force(report, execution)


def test_non_completed_execution_is_rejected():
    report, execution = _fixtures()
    execution = execution.model_copy(
        update={
            "status": TaskForceExecutionRunStatus.BLOCKED,
            "aggregation_ready": False,
        }
    )
    with pytest.raises(PermissionError, match="completed"):
        evaluate_task_force(report, execution)


def test_report_cost_must_match_execution_records():
    report, execution = _fixtures()
    report = report.model_copy(update={"member_actual_cost_eur": Decimal("0.99")})
    report = report.model_copy(
        update={"report_fingerprint_sha256": task_force_report_fingerprint(report)}
    )
    with pytest.raises(ValueError, match="report cost"):
        evaluate_task_force(report, execution)


def test_execution_fingerprint_must_match_report():
    report, execution = _fixtures()
    report = report.model_copy(update={"execution_fingerprint_sha256": "f" * 64})
    report = report.model_copy(
        update={"report_fingerprint_sha256": task_force_report_fingerprint(report)}
    )
    with pytest.raises(ValueError, match="execution fingerprint"):
        evaluate_task_force(report, execution)


def test_evaluation_fingerprint_is_deterministic():
    report, execution = _fixtures()
    baseline, treatment = _outcomes(report)
    comparison = compare_task_force_outcomes(baseline, treatment, report=report)
    first = evaluate_task_force(report, execution, comparison=comparison)
    second = evaluate_task_force(report, execution, comparison=comparison)
    assert first.evaluation_fingerprint_sha256 == second.evaluation_fingerprint_sha256


def test_zero_task_force_cost_does_not_invent_infinite_economic_efficiency():
    report, execution = _fixtures(zero_cost=True)
    baseline, treatment = _outcomes(report)
    comparison = compare_task_force_outcomes(baseline, treatment, report=report)
    result = evaluate_task_force(report, execution, comparison=comparison)
    assert result.marginal_economic_net.value == Decimal("2")
    assert result.marginal_economic_net_per_ai_eur.status is MetricStatus.UNAVAILABLE
    assert result.marginal_economic_net_per_ai_eur.reason == "ZERO_TASK_FORCE_AI_COST"
