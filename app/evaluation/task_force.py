from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from app.task_force.aggregation import (
    TaskForceReport,
    task_force_execution_fingerprint,
)
from app.task_force.execution_runtime import (
    TaskForceExecutionRunStatus,
    TaskForceMultiMemberExecution,
)

from .models import Metric, MetricStatus, ZERO


@dataclass(frozen=True, slots=True)
class TaskForceRunOutcome:
    """One comparable run outcome for baseline-vs-Task-Force evaluation."""

    run_id: str
    comparison_fingerprint: str
    dataset_id: str
    role: str
    period_start: datetime
    period_end: datetime
    opportunity_count: int
    trading_net: Metric
    economic_net: Metric
    max_drawdown_pct: Metric
    includes_task_force: bool
    task_force_report_fingerprint_sha256: str | None
    is_out_of_sample: bool

    def __post_init__(self) -> None:
        for field_name in ("run_id", "dataset_id", "role"):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValueError(f"{field_name} must not be blank")
            object.__setattr__(self, field_name, value)
        object.__setattr__(
            self,
            "comparison_fingerprint",
            _validate_sha256(self.comparison_fingerprint),
        )
        start = _ensure_utc(self.period_start, field_name="period_start")
        end = _ensure_utc(self.period_end, field_name="period_end")
        if end <= start:
            raise ValueError("period_end must be after period_start")
        object.__setattr__(self, "period_start", start)
        object.__setattr__(self, "period_end", end)
        if self.opportunity_count < 0:
            raise ValueError("opportunity_count must be >= 0")
        fingerprint = self.task_force_report_fingerprint_sha256
        if self.includes_task_force:
            if fingerprint is None:
                raise ValueError("Task Force treatment run must bind a report fingerprint")
            object.__setattr__(
                self,
                "task_force_report_fingerprint_sha256",
                _validate_sha256(fingerprint),
            )
        elif fingerprint is not None:
            raise ValueError("baseline without Task Force cannot bind a Task Force report")


@dataclass(frozen=True, slots=True)
class TaskForceOutcomeComparison:
    """Deterministic treatment-minus-baseline economic evidence."""

    task_force_id: str
    report_fingerprint_sha256: str
    comparison_fingerprint: str
    baseline_run_id: str
    treatment_run_id: str
    dataset_id: str
    role: str
    period_start: datetime
    period_end: datetime
    opportunity_count: int
    marginal_trading_net: Metric
    marginal_economic_net: Metric
    drawdown_reduction_pct: Metric
    is_out_of_sample: bool


@dataclass(frozen=True, slots=True)
class TaskForceEvaluationReport:
    """Multidimensional Task Force evaluation; never a promotion or trading score."""

    report_version: str
    task_force_id: str
    execution_run_id: str
    task_force_report_fingerprint_sha256: str
    member_count: int
    completed_member_count: int
    red_team_required: bool
    red_team_present: bool
    total_actual_cost_eur: Decimal
    cost_by_agent: Mapping[str, Decimal]
    total_attempt_count: int
    total_usage_record_count: int
    total_latency_ms: int
    wall_clock_duration_ms: int
    average_cost_per_member: Metric
    average_attempts_per_member: Metric
    average_latency_ms_per_member: Metric
    finding_count: int
    uncertainty_count: int
    follow_up_question_count: int
    marginal_trading_net: Metric
    marginal_economic_net: Metric
    drawdown_reduction_pct: Metric
    marginal_economic_net_per_ai_eur: Metric
    comparison_fingerprint: str | None
    comparison_is_out_of_sample: bool | None
    evaluation_fingerprint_sha256: str
    advisory_only: bool = True
    automatic_state_change: bool = False
    trade_proposal_authority: bool = False
    registry_mutation: bool = False
    risk_authority: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        if self.report_version != "batch20.task-force-evaluation.v1":
            raise ValueError("unexpected Task Force evaluation report version")
        object.__setattr__(
            self,
            "task_force_report_fingerprint_sha256",
            _validate_sha256(self.task_force_report_fingerprint_sha256),
        )
        object.__setattr__(
            self,
            "evaluation_fingerprint_sha256",
            _validate_sha256(self.evaluation_fingerprint_sha256),
        )
        if self.comparison_fingerprint is not None:
            object.__setattr__(
                self,
                "comparison_fingerprint",
                _validate_sha256(self.comparison_fingerprint),
            )
        object.__setattr__(
            self,
            "cost_by_agent",
            MappingProxyType(dict(sorted(self.cost_by_agent.items()))),
        )
        if not self.advisory_only:
            raise ValueError("Task Force evaluation must remain advisory-only")
        if any(
            (
                self.automatic_state_change,
                self.trade_proposal_authority,
                self.registry_mutation,
                self.risk_authority,
                self.live_authority,
            )
        ):
            raise ValueError("Task Force evaluation cannot hold operational authority")


def compare_task_force_outcomes(
    baseline: TaskForceRunOutcome,
    treatment: TaskForceRunOutcome,
    *,
    report: TaskForceReport,
) -> TaskForceOutcomeComparison:
    """Compare identical run scopes where only Task Force participation changes."""

    _validate_comparable_outcomes(baseline, treatment, report=report)
    return TaskForceOutcomeComparison(
        task_force_id=report.task_force_id,
        report_fingerprint_sha256=report.report_fingerprint_sha256,
        comparison_fingerprint=baseline.comparison_fingerprint,
        baseline_run_id=baseline.run_id,
        treatment_run_id=treatment.run_id,
        dataset_id=baseline.dataset_id,
        role=baseline.role,
        period_start=baseline.period_start,
        period_end=baseline.period_end,
        opportunity_count=baseline.opportunity_count,
        marginal_trading_net=_difference(
            treatment.trading_net,
            baseline.trading_net,
            unavailable_reason="TRADING_NET_UNAVAILABLE",
        ),
        marginal_economic_net=_difference(
            treatment.economic_net,
            baseline.economic_net,
            unavailable_reason="ECONOMIC_NET_UNAVAILABLE",
        ),
        drawdown_reduction_pct=_difference(
            baseline.max_drawdown_pct,
            treatment.max_drawdown_pct,
            unavailable_reason="MAX_DRAWDOWN_UNAVAILABLE",
        ),
        is_out_of_sample=baseline.is_out_of_sample,
    )


def evaluate_task_force(
    report: TaskForceReport,
    execution: TaskForceMultiMemberExecution,
    *,
    comparison: TaskForceOutcomeComparison | None = None,
) -> TaskForceEvaluationReport:
    """Evaluate cost/latency plus optional comparable economic contribution."""

    _validate_execution_evidence(report, execution)
    if comparison is not None:
        _validate_comparison_binding(report, comparison)

    records = execution.member_records
    total_cost = sum((record.actual_cost_eur for record in records), ZERO)
    total_attempts = sum(record.attempts for record in records)
    total_usage_records = sum(record.usage_record_count for record in records)
    total_latency_ms = sum(record.latency_ms_total for record in records)
    duration_ms = int((report.aggregated_at - execution.started_at).total_seconds() * 1000)
    member_count = len(report.members)

    costs: dict[str, Decimal] = {}
    for record in records:
        costs[record.agent_id] = costs.get(record.agent_id, ZERO) + record.actual_cost_eur

    if comparison is None:
        marginal_trading = Metric.unavailable("NO_COMPARABLE_TASK_FORCE_BASELINE")
        marginal_economic = Metric.unavailable("NO_COMPARABLE_TASK_FORCE_BASELINE")
        drawdown_reduction = Metric.unavailable("NO_COMPARABLE_TASK_FORCE_BASELINE")
        comparison_fingerprint = None
        comparison_oos = None
    else:
        marginal_trading = comparison.marginal_trading_net
        marginal_economic = comparison.marginal_economic_net
        drawdown_reduction = comparison.drawdown_reduction_pct
        comparison_fingerprint = comparison.comparison_fingerprint
        comparison_oos = comparison.is_out_of_sample

    economic_per_ai_eur = _economic_value_per_ai_eur(marginal_economic, total_cost)
    average_cost = Metric.available(total_cost / Decimal(member_count))
    average_attempts = Metric.available(Decimal(total_attempts) / Decimal(member_count))
    average_latency = Metric.available(Decimal(total_latency_ms) / Decimal(member_count))

    material = {
        "report_version": "batch20.task-force-evaluation.v1",
        "task_force_id": report.task_force_id,
        "execution_run_id": report.execution_run_id,
        "task_force_report_fingerprint_sha256": report.report_fingerprint_sha256,
        "member_count": member_count,
        "completed_member_count": execution.completed_member_count,
        "red_team_required": report.red_team_required,
        "red_team_present": report.red_team_present,
        "total_actual_cost_eur": str(total_cost),
        "cost_by_agent": {key: str(value) for key, value in sorted(costs.items())},
        "total_attempt_count": total_attempts,
        "total_usage_record_count": total_usage_records,
        "total_latency_ms": total_latency_ms,
        "wall_clock_duration_ms": duration_ms,
        "average_cost_per_member": _metric_payload(average_cost),
        "average_attempts_per_member": _metric_payload(average_attempts),
        "average_latency_ms_per_member": _metric_payload(average_latency),
        "finding_count": len(report.findings),
        "uncertainty_count": len(report.uncertainties),
        "follow_up_question_count": len(report.follow_up_questions),
        "marginal_trading_net": _metric_payload(marginal_trading),
        "marginal_economic_net": _metric_payload(marginal_economic),
        "drawdown_reduction_pct": _metric_payload(drawdown_reduction),
        "marginal_economic_net_per_ai_eur": _metric_payload(economic_per_ai_eur),
        "comparison_fingerprint": comparison_fingerprint,
        "comparison_is_out_of_sample": comparison_oos,
        "advisory_only": True,
        "automatic_state_change": False,
        "trade_proposal_authority": False,
        "registry_mutation": False,
        "risk_authority": False,
        "live_authority": False,
    }
    return TaskForceEvaluationReport(
        report_version="batch20.task-force-evaluation.v1",
        task_force_id=report.task_force_id,
        execution_run_id=report.execution_run_id,
        task_force_report_fingerprint_sha256=report.report_fingerprint_sha256,
        member_count=member_count,
        completed_member_count=execution.completed_member_count,
        red_team_required=report.red_team_required,
        red_team_present=report.red_team_present,
        total_actual_cost_eur=total_cost,
        cost_by_agent=costs,
        total_attempt_count=total_attempts,
        total_usage_record_count=total_usage_records,
        total_latency_ms=total_latency_ms,
        wall_clock_duration_ms=duration_ms,
        average_cost_per_member=average_cost,
        average_attempts_per_member=average_attempts,
        average_latency_ms_per_member=average_latency,
        finding_count=len(report.findings),
        uncertainty_count=len(report.uncertainties),
        follow_up_question_count=len(report.follow_up_questions),
        marginal_trading_net=marginal_trading,
        marginal_economic_net=marginal_economic,
        drawdown_reduction_pct=drawdown_reduction,
        marginal_economic_net_per_ai_eur=economic_per_ai_eur,
        comparison_fingerprint=comparison_fingerprint,
        comparison_is_out_of_sample=comparison_oos,
        evaluation_fingerprint_sha256=_canonical_sha256(material),
    )


def task_force_report_fingerprint(report: TaskForceReport) -> str:
    """Recompute the Batch 20c report fingerprint without orchestration imports."""

    material = report.model_dump(
        mode="json",
        exclude={"aggregated_at", "report_fingerprint_sha256"},
    )
    return _canonical_sha256(material)


def _validate_execution_evidence(
    report: TaskForceReport,
    execution: TaskForceMultiMemberExecution,
) -> None:
    if task_force_report_fingerprint(report) != report.report_fingerprint_sha256:
        raise ValueError("Task Force report fingerprint is stale or inconsistent")
    if execution.status is not TaskForceExecutionRunStatus.COMPLETED:
        raise PermissionError("only completed Task Force executions can be evaluated")
    if not execution.aggregation_ready or not execution.cost_accounting_complete:
        raise PermissionError("Task Force execution accounting must be complete")
    if execution.failure is not None:
        raise ValueError("completed Task Force execution cannot contain failure evidence")
    if execution.task_force_id != report.task_force_id:
        raise ValueError("Task Force execution task_force_id does not match report")
    if execution.execution_run_id != report.execution_run_id:
        raise ValueError("Task Force execution_run_id does not match report")
    if (
        execution.execution_contract_fingerprint_sha256
        != report.execution_contract_fingerprint_sha256
    ):
        raise ValueError("Task Force execution contract fingerprint does not match report")
    if task_force_execution_fingerprint(execution) != report.execution_fingerprint_sha256:
        raise ValueError("Task Force execution fingerprint is stale or inconsistent")
    observed = [(item.member_id, item.agent_id) for item in execution.member_records]
    expected = [(item.member_id, item.agent_id) for item in report.members]
    if observed != expected:
        raise ValueError("Task Force report members do not match execution evidence")
    total_cost = sum((record.actual_cost_eur for record in execution.member_records), ZERO)
    if total_cost != report.member_actual_cost_eur:
        raise ValueError("Task Force report cost does not match execution evidence")
    total_attempts = sum(record.attempts for record in execution.member_records)
    if total_attempts != report.member_attempt_count:
        raise ValueError("Task Force report attempts do not match execution evidence")
    if report.aggregated_at < execution.started_at:
        raise ValueError("Task Force report cannot predate execution")


def _validate_comparable_outcomes(
    baseline: TaskForceRunOutcome,
    treatment: TaskForceRunOutcome,
    *,
    report: TaskForceReport,
) -> None:
    if baseline.run_id == treatment.run_id:
        raise ValueError("baseline and treatment run ids must differ")
    if baseline.includes_task_force:
        raise ValueError("baseline run must exclude the Task Force")
    if not treatment.includes_task_force:
        raise ValueError("treatment run must include the Task Force")
    if treatment.task_force_report_fingerprint_sha256 != report.report_fingerprint_sha256:
        raise ValueError("treatment run does not bind the evaluated Task Force report")
    comparable = (
        (
            "comparison_fingerprint",
            baseline.comparison_fingerprint,
            treatment.comparison_fingerprint,
        ),
        ("dataset_id", baseline.dataset_id, treatment.dataset_id),
        ("role", baseline.role, treatment.role),
        ("period_start", baseline.period_start, treatment.period_start),
        ("period_end", baseline.period_end, treatment.period_end),
        ("opportunity_count", baseline.opportunity_count, treatment.opportunity_count),
        ("is_out_of_sample", baseline.is_out_of_sample, treatment.is_out_of_sample),
    )
    for field_name, left, right in comparable:
        if left != right:
            raise ValueError(f"Task Force comparison runs differ on {field_name}")


def _validate_comparison_binding(
    report: TaskForceReport,
    comparison: TaskForceOutcomeComparison,
) -> None:
    if comparison.task_force_id != report.task_force_id:
        raise ValueError("Task Force comparison targets a different task_force_id")
    if comparison.report_fingerprint_sha256 != report.report_fingerprint_sha256:
        raise ValueError("Task Force comparison report fingerprint is stale")


def _difference(
    left: Metric,
    right: Metric,
    *,
    unavailable_reason: str,
) -> Metric:
    if left.status is not MetricStatus.AVAILABLE or right.status is not MetricStatus.AVAILABLE:
        return Metric.unavailable(unavailable_reason)
    assert left.value is not None and right.value is not None
    return Metric.available(left.value - right.value)


def _economic_value_per_ai_eur(metric: Metric, cost: Decimal) -> Metric:
    if metric.status is not MetricStatus.AVAILABLE or metric.value is None:
        return Metric.unavailable("MARGINAL_ECONOMIC_NET_UNAVAILABLE")
    if cost == ZERO:
        return Metric.unavailable("ZERO_TASK_FORCE_AI_COST")
    return Metric.available(metric.value / cost)


def _metric_payload(metric: Metric) -> dict[str, str | None]:
    return {
        "value": None if metric.value is None else str(metric.value),
        "status": metric.status.value,
        "reason": metric.reason,
    }


def _canonical_sha256(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_sha256(value: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise ValueError("fingerprint must be lowercase hexadecimal SHA-256")
    return normalized


def _ensure_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
