from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .task_force import task_force_report_fingerprint
from .task_force_replay import TaskForceReplayCampaignReport, TaskForceReplayPlan


class TaskForceReplayAuditStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"


def _validate_sha256(value: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise ValueError("fingerprint must be lowercase hexadecimal SHA-256")
    return normalized


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def task_force_replay_plan_fingerprint(plan: TaskForceReplayPlan) -> str:
    return stable_digest(
        {
            "schema": "money-heist.task-force-replay-plan-seal.v1",
            "plan": plan,
        }
    )


def task_force_replay_campaign_fingerprint(report: TaskForceReplayCampaignReport) -> str:
    treatment_report = report.treatment.task_force_report
    treatment_execution = report.treatment.task_force_execution
    return stable_digest(
        {
            "schema": "money-heist.task-force-replay-campaign-seal.v1",
            "campaign_id": report.campaign_id,
            "comparison_fingerprint": report.comparison_fingerprint,
            "target_opportunity_id": report.target_opportunity_id,
            "role": report.role,
            "baseline": {
                "variant": report.baseline.variant,
                "period_report": report.baseline.period_report,
            },
            "treatment": {
                "variant": report.treatment.variant,
                "period_report": report.treatment.period_report,
                "task_force_report": (
                    treatment_report.model_dump(mode="json")
                    if treatment_report is not None
                    else None
                ),
                "task_force_execution": (
                    treatment_execution.model_dump(mode="json")
                    if treatment_execution is not None
                    else None
                ),
            },
            "comparison": report.comparison,
            "task_force_evaluation": report.task_force_evaluation,
            "replay_fingerprint_sha256": report.replay_fingerprint_sha256,
        }
    )


def task_force_replay_evaluation_fingerprint(report: TaskForceReplayCampaignReport) -> str:
    return stable_digest(
        {
            "schema": "money-heist.task-force-evaluation-seal.v1",
            "evaluation": report.task_force_evaluation,
        }
    )


def task_force_replay_comparison_fingerprint(report: TaskForceReplayCampaignReport) -> str:
    return stable_digest(
        {
            "schema": "money-heist.task-force-outcome-comparison-seal.v1",
            "comparison": report.comparison,
        }
    )


def recompute_task_force_replay_fingerprint(report: TaskForceReplayCampaignReport) -> str:
    treatment_report = report.treatment.task_force_report
    if treatment_report is None:
        raise ValueError("Task Force replay treatment is missing Task Force report")
    return stable_digest(
        {
            "schema": "money-heist.task-force-replay-execution.v1",
            "campaign_id": report.campaign_id,
            "comparison_fingerprint": report.comparison_fingerprint,
            "target_opportunity_id": report.target_opportunity_id,
            "role": report.role,
            "baseline_variant_id": report.baseline.variant.variant_id,
            "baseline_report": report.baseline.period_report,
            "treatment_variant_id": report.treatment.variant.variant_id,
            "treatment_report": report.treatment.period_report,
            "task_force_report_fingerprint": treatment_report.report_fingerprint_sha256,
            "task_force_evaluation_fingerprint": (
                report.task_force_evaluation.evaluation_fingerprint_sha256
            ),
        }
    )


def _validate_binding(plan: TaskForceReplayPlan, report: TaskForceReplayCampaignReport) -> None:
    if report.campaign_id != plan.campaign_id:
        raise ValueError("campaign report does not match replay plan campaign_id")
    if report.comparison_fingerprint != plan.comparison_fingerprint:
        raise ValueError("campaign report does not match replay plan comparison fingerprint")
    if report.target_opportunity_id != plan.target_opportunity_id:
        raise ValueError("campaign report does not match replay plan target opportunity")
    if report.baseline.variant != plan.baseline:
        raise ValueError("campaign report baseline variant does not match replay plan")
    if report.treatment.variant != plan.treatment:
        raise ValueError("campaign report treatment variant does not match replay plan")
    if report.baseline.period_report.role is not report.role:
        raise ValueError("baseline period role does not match campaign report role")
    if report.treatment.period_report.role is not report.role:
        raise ValueError("treatment period role does not match campaign report role")
    if report.comparison.comparison_fingerprint != plan.comparison_fingerprint:
        raise ValueError("outcome comparison does not match replay plan fingerprint")
    if report.comparison.baseline_run_id != plan.baseline.run.run_id:
        raise ValueError("outcome comparison baseline run does not match replay plan")
    if report.comparison.treatment_run_id != plan.treatment.run.run_id:
        raise ValueError("outcome comparison treatment run does not match replay plan")
    treatment_report = report.treatment.task_force_report
    treatment_execution = report.treatment.task_force_execution
    if treatment_report is None or treatment_execution is None:
        raise ValueError("treatment replay requires Task Force report and execution")
    if report.baseline.task_force_report is not None:
        raise ValueError("baseline replay cannot contain Task Force report")
    if report.baseline.task_force_execution is not None:
        raise ValueError("baseline replay cannot contain Task Force execution")
    if treatment_report.opportunity_id != plan.target_opportunity_id:
        raise ValueError("Task Force report targets the wrong replay opportunity")
    if treatment_report.system_id != plan.treatment.run.config.system_id:
        raise ValueError("Task Force report targets the wrong replay system")
    if treatment_execution.task_force_id != treatment_report.task_force_id:
        raise ValueError("Task Force execution does not match Task Force report")
    if treatment_execution.execution_run_id != treatment_report.execution_run_id:
        raise ValueError("Task Force execution run does not match Task Force report")
    if report.task_force_evaluation.task_force_id != treatment_report.task_force_id:
        raise ValueError("Task Force evaluation does not match Task Force report")
    if (
        report.task_force_evaluation.task_force_report_fingerprint_sha256
        != treatment_report.report_fingerprint_sha256
    ):
        raise ValueError("Task Force evaluation report fingerprint binding is inconsistent")


def _assert_internal_fingerprints_fresh(report: TaskForceReplayCampaignReport) -> None:
    treatment_report = report.treatment.task_force_report
    if treatment_report is None:
        raise ValueError("treatment replay is missing Task Force report")
    current_report_fingerprint = task_force_report_fingerprint(treatment_report)
    if current_report_fingerprint != treatment_report.report_fingerprint_sha256:
        raise ValueError("Task Force report fingerprint is stale")
    if recompute_task_force_replay_fingerprint(report) != report.replay_fingerprint_sha256:
        raise ValueError("Task Force replay fingerprint is stale")


@dataclass(frozen=True, slots=True)
class TaskForceReplaySeal:
    seal_version: str
    campaign_id: str
    comparison_fingerprint: str
    target_opportunity_id: str
    role: str
    plan_fingerprint_sha256: str
    replay_fingerprint_sha256: str
    campaign_fingerprint_sha256: str
    comparison_object_fingerprint_sha256: str
    evaluation_object_fingerprint_sha256: str
    baseline_business_sha256: str
    treatment_business_sha256: str
    task_force_report_fingerprint_sha256: str
    task_force_evaluation_fingerprint_sha256: str
    sealed_at: datetime
    paper_only: bool = True
    advisory_only: bool = True
    execution_authorized: bool = False
    automatic_state_change: bool = False
    trade_proposal_authority: bool = False
    registry_mutation: bool = False
    risk_authority: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        if self.seal_version != "batch20.task-force-replay-seal.v1":
            raise ValueError("unexpected Task Force replay seal version")
        for field_name in (
            "comparison_fingerprint",
            "plan_fingerprint_sha256",
            "replay_fingerprint_sha256",
            "campaign_fingerprint_sha256",
            "comparison_object_fingerprint_sha256",
            "evaluation_object_fingerprint_sha256",
            "baseline_business_sha256",
            "treatment_business_sha256",
            "task_force_report_fingerprint_sha256",
            "task_force_evaluation_fingerprint_sha256",
        ):
            object.__setattr__(self, field_name, _validate_sha256(getattr(self, field_name)))
        object.__setattr__(self, "sealed_at", _as_utc(self.sealed_at, field_name="sealed_at"))
        if not self.campaign_id.strip() or not self.target_opportunity_id.strip() or not self.role:
            raise ValueError("seal identity fields must not be blank")
        if not self.paper_only or not self.advisory_only:
            raise ValueError("Task Force replay seal must remain PAPER/advisory-only")
        if any(
            (
                self.execution_authorized,
                self.automatic_state_change,
                self.trade_proposal_authority,
                self.registry_mutation,
                self.risk_authority,
                self.live_authority,
            )
        ):
            raise ValueError("Task Force replay seal cannot hold operational authority")


@dataclass(frozen=True, slots=True)
class TaskForceReplayAudit:
    audit_version: str
    campaign_id: str
    status: TaskForceReplayAuditStatus
    reason_codes: tuple[str, ...]
    sealed_campaign_fingerprint_sha256: str
    current_campaign_fingerprint_sha256: str
    sealed_plan_fingerprint_sha256: str
    current_plan_fingerprint_sha256: str
    replay_fingerprint_sha256: str
    audited_at: datetime
    execution_authorized: bool = False
    automatic_state_change: bool = False
    trade_proposal_authority: bool = False
    registry_mutation: bool = False
    risk_authority: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        if self.audit_version != "batch20.task-force-replay-audit.v1":
            raise ValueError("unexpected Task Force replay audit version")
        for field_name in (
            "sealed_campaign_fingerprint_sha256",
            "current_campaign_fingerprint_sha256",
            "sealed_plan_fingerprint_sha256",
            "current_plan_fingerprint_sha256",
            "replay_fingerprint_sha256",
        ):
            object.__setattr__(self, field_name, _validate_sha256(getattr(self, field_name)))
        object.__setattr__(self, "audited_at", _as_utc(self.audited_at, field_name="audited_at"))
        if self.status is TaskForceReplayAuditStatus.FRESH and self.reason_codes != (
            "REPLAY_SEAL_FRESH",
        ):
            raise ValueError("FRESH audit must contain only REPLAY_SEAL_FRESH")
        if self.status is TaskForceReplayAuditStatus.STALE and not self.reason_codes:
            raise ValueError("STALE audit requires reason codes")
        if any(
            (
                self.execution_authorized,
                self.automatic_state_change,
                self.trade_proposal_authority,
                self.registry_mutation,
                self.risk_authority,
                self.live_authority,
            )
        ):
            raise ValueError("Task Force replay audit cannot hold operational authority")


def seal_task_force_replay(
    plan: TaskForceReplayPlan,
    report: TaskForceReplayCampaignReport,
    *,
    sealed_at: datetime,
) -> TaskForceReplaySeal:
    _assert_internal_fingerprints_fresh(report)
    _validate_binding(plan, report)
    treatment_report = report.treatment.task_force_report
    assert treatment_report is not None
    return TaskForceReplaySeal(
        seal_version="batch20.task-force-replay-seal.v1",
        campaign_id=report.campaign_id,
        comparison_fingerprint=report.comparison_fingerprint,
        target_opportunity_id=report.target_opportunity_id,
        role=report.role.value,
        plan_fingerprint_sha256=task_force_replay_plan_fingerprint(plan),
        replay_fingerprint_sha256=report.replay_fingerprint_sha256,
        campaign_fingerprint_sha256=task_force_replay_campaign_fingerprint(report),
        comparison_object_fingerprint_sha256=task_force_replay_comparison_fingerprint(report),
        evaluation_object_fingerprint_sha256=task_force_replay_evaluation_fingerprint(report),
        baseline_business_sha256=report.baseline.period_report.business_sha256,
        treatment_business_sha256=report.treatment.period_report.business_sha256,
        task_force_report_fingerprint_sha256=treatment_report.report_fingerprint_sha256,
        task_force_evaluation_fingerprint_sha256=(
            report.task_force_evaluation.evaluation_fingerprint_sha256
        ),
        sealed_at=sealed_at,
    )


def audit_task_force_replay(
    seal: TaskForceReplaySeal,
    plan: TaskForceReplayPlan,
    report: TaskForceReplayCampaignReport,
    *,
    audited_at: datetime,
) -> TaskForceReplayAudit:
    reasons: set[str] = set()
    plan_fingerprint = task_force_replay_plan_fingerprint(plan)
    campaign_fingerprint = task_force_replay_campaign_fingerprint(report)

    try:
        _validate_binding(plan, report)
    except ValueError:
        reasons.add("PLAN_REPORT_BINDING_CHANGED")

    if seal.campaign_id != report.campaign_id or seal.campaign_id != plan.campaign_id:
        reasons.add("CAMPAIGN_ID_CHANGED")
    if seal.comparison_fingerprint != report.comparison_fingerprint:
        reasons.add("COMPARISON_FINGERPRINT_CHANGED")
    if seal.target_opportunity_id != report.target_opportunity_id:
        reasons.add("TARGET_OPPORTUNITY_CHANGED")
    if seal.role != report.role.value:
        reasons.add("REPLAY_ROLE_CHANGED")
    if seal.plan_fingerprint_sha256 != plan_fingerprint:
        reasons.add("PLAN_CHANGED")
    if seal.campaign_fingerprint_sha256 != campaign_fingerprint:
        reasons.add("CAMPAIGN_REPORT_CHANGED")
    if seal.replay_fingerprint_sha256 != report.replay_fingerprint_sha256:
        reasons.add("REPLAY_FINGERPRINT_CHANGED")
    if seal.baseline_business_sha256 != report.baseline.period_report.business_sha256:
        reasons.add("BASELINE_BUSINESS_CHANGED")
    if seal.treatment_business_sha256 != report.treatment.period_report.business_sha256:
        reasons.add("TREATMENT_BUSINESS_CHANGED")
    if (
        seal.comparison_object_fingerprint_sha256
        != task_force_replay_comparison_fingerprint(report)
    ):
        reasons.add("OUTCOME_COMPARISON_CHANGED")
    if (
        seal.evaluation_object_fingerprint_sha256
        != task_force_replay_evaluation_fingerprint(report)
    ):
        reasons.add("TASK_FORCE_EVALUATION_CHANGED")
    if (
        seal.task_force_evaluation_fingerprint_sha256
        != report.task_force_evaluation.evaluation_fingerprint_sha256
    ):
        reasons.add("TASK_FORCE_EVALUATION_FINGERPRINT_CHANGED")

    treatment_report = report.treatment.task_force_report
    if treatment_report is None:
        reasons.add("TASK_FORCE_REPORT_MISSING")
    else:
        if (
            seal.task_force_report_fingerprint_sha256
            != treatment_report.report_fingerprint_sha256
        ):
            reasons.add("TASK_FORCE_REPORT_CHANGED")
        try:
            current_tf_fingerprint = task_force_report_fingerprint(treatment_report)
        except Exception:
            reasons.add("TASK_FORCE_REPORT_FINGERPRINT_STALE")
        else:
            if current_tf_fingerprint != treatment_report.report_fingerprint_sha256:
                reasons.add("TASK_FORCE_REPORT_FINGERPRINT_STALE")

    try:
        replay_fingerprint = recompute_task_force_replay_fingerprint(report)
    except Exception:
        reasons.add("REPLAY_FINGERPRINT_STALE")
    else:
        if replay_fingerprint != report.replay_fingerprint_sha256:
            reasons.add("REPLAY_FINGERPRINT_STALE")

    if reasons:
        status = TaskForceReplayAuditStatus.STALE
        reason_codes = tuple(sorted(reasons))
    else:
        status = TaskForceReplayAuditStatus.FRESH
        reason_codes = ("REPLAY_SEAL_FRESH",)

    return TaskForceReplayAudit(
        audit_version="batch20.task-force-replay-audit.v1",
        campaign_id=report.campaign_id,
        status=status,
        reason_codes=reason_codes,
        sealed_campaign_fingerprint_sha256=seal.campaign_fingerprint_sha256,
        current_campaign_fingerprint_sha256=campaign_fingerprint,
        sealed_plan_fingerprint_sha256=seal.plan_fingerprint_sha256,
        current_plan_fingerprint_sha256=plan_fingerprint,
        replay_fingerprint_sha256=report.replay_fingerprint_sha256,
        audited_at=audited_at,
    )


def assert_task_force_replay_fresh(audit: TaskForceReplayAudit) -> None:
    if audit.status is not TaskForceReplayAuditStatus.FRESH:
        raise PermissionError(
            "Task Force replay seal is stale: " + ", ".join(audit.reason_codes)
        )


__all__ = [
    "TaskForceReplayAudit",
    "TaskForceReplayAuditStatus",
    "TaskForceReplaySeal",
    "assert_task_force_replay_fresh",
    "audit_task_force_replay",
    "recompute_task_force_replay_fingerprint",
    "seal_task_force_replay",
    "task_force_replay_campaign_fingerprint",
    "task_force_replay_comparison_fingerprint",
    "task_force_replay_evaluation_fingerprint",
    "task_force_replay_plan_fingerprint",
]
