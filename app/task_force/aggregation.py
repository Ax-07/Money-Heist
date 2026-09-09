from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .composition_closure import task_force_plan_fingerprint
from .execution import TaskForceExecutionContract
from .execution_runtime import (
    TaskForceExecutionRunStatus,
    TaskForceMultiMemberExecution,
)
from .models import (
    TaskForcePlan,
    TaskForceRequest,
    task_force_request_fingerprint,
)


ZERO = Decimal("0")


class TaskForceAggregatedMember(BaseModel):
    """One member contribution preserved without semantic re-weighting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    member_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=100)
    task_role: str = Field(min_length=1, max_length=200)
    answer: str = Field(min_length=1, max_length=6000)
    confidence: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    finding_ids: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    follow_up_questions: tuple[str, ...] = ()

    @field_validator("member_id", "agent_id", "task_role", "answer")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class TaskForceAggregatedFinding(BaseModel):
    """Finding with exact member provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    member_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=100)
    finding_id: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=3000)
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("member_id", "agent_id", "finding_id", "summary")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class TaskForceRedTeamContribution(BaseModel):
    """Red-team evidence already produced by an executed Task Force member."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    member_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=100)
    answer: str = Field(min_length=1, max_length=6000)
    confidence: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    finding_ids: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()


class TaskForceReport(BaseModel):
    """Advisory-only Task Force report with no semantic vote or trading authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_version: Literal["batch20.task-force-report.v1"] = "batch20.task-force-report.v1"
    task_force_id: str = Field(min_length=1, max_length=200)
    execution_run_id: str = Field(min_length=1, max_length=200)
    request_id: str = Field(min_length=1, max_length=200)
    system_id: str = Field(min_length=1, max_length=100)
    opportunity_id: str | None = Field(default=None, max_length=200)
    objective: str = Field(min_length=1, max_length=2000)
    question: str = Field(min_length=1, max_length=4000)
    execution_contract_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    execution_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    members: tuple[TaskForceAggregatedMember, ...] = Field(min_length=1)
    findings: tuple[TaskForceAggregatedFinding, ...] = ()
    uncertainties: tuple[str, ...] = ()
    follow_up_questions: tuple[str, ...] = ()
    red_team_required: bool
    red_team_present: bool
    red_team_contributions: tuple[TaskForceRedTeamContribution, ...] = ()
    member_actual_cost_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    member_attempt_count: int = Field(ge=1)
    aggregation_method: Literal["PROVENANCE_PRESERVING_NO_SEMANTIC_VOTE"] = (
        "PROVENANCE_PRESERVING_NO_SEMANTIC_VOTE"
    )
    semantic_consensus_computed: Literal[False] = False
    aggregate_confidence_computed: Literal[False] = False
    aggregated_at: datetime
    report_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    advisory_only: Literal[True] = True
    trade_proposal_authority: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator(
        "execution_contract_fingerprint_sha256",
        "execution_fingerprint_sha256",
        "report_fingerprint_sha256",
    )
    @classmethod
    def _validate_sha(cls, value: str) -> str:
        return _validate_sha256(value)

    @field_validator("aggregated_at")
    @classmethod
    def _validate_aggregated_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value, field_name="aggregated_at")

    @model_validator(mode="after")
    def _coherent_red_team(self) -> TaskForceReport:
        if self.red_team_present != bool(self.red_team_contributions):
            raise ValueError("red_team_present must match red_team_contributions")
        if self.red_team_required and not self.red_team_present:
            raise ValueError("required Red Team contribution is missing")
        member_ids = [member.member_id for member in self.members]
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("report members must have unique member_id values")
        return self


def task_force_execution_fingerprint(execution: TaskForceMultiMemberExecution) -> str:
    """Fingerprint the exact execution evidence consumed by aggregation."""

    return _canonical_sha256(execution.model_dump(mode="json"))


def aggregate_task_force_execution(
    contract: TaskForceExecutionContract,
    execution: TaskForceMultiMemberExecution,
    plan: TaskForcePlan,
    request: TaskForceRequest,
    *,
    aggregated_at: datetime,
) -> TaskForceReport:
    """Aggregate completed member outputs without creating semantic consensus.

    Red Team is optional at request level. If requested, the red-team member must already
    be present in the approved composition and completed execution. This function performs
    no AI call and does not substitute for the main orchestration PalermoReview contract.
    """

    aggregated_at = _ensure_utc(aggregated_at, field_name="aggregated_at")
    _validate_aggregation_inputs(
        contract=contract,
        execution=execution,
        plan=plan,
        request=request,
        aggregated_at=aggregated_at,
    )

    specs_by_member = {spec.member_id: spec for spec in contract.member_specs}
    members: list[TaskForceAggregatedMember] = []
    findings: list[TaskForceAggregatedFinding] = []
    red_team: list[TaskForceRedTeamContribution] = []
    uncertainties: list[str] = []
    follow_up_questions: list[str] = []

    for record in execution.member_records:
        spec = specs_by_member[record.member_id]
        analysis = record.analysis
        finding_ids = tuple(finding.finding_id for finding in analysis.findings)
        members.append(
            TaskForceAggregatedMember(
                member_id=record.member_id,
                agent_id=record.agent_id,
                task_role=spec.task_role,
                answer=analysis.answer,
                confidence=analysis.confidence,
                finding_ids=finding_ids,
                uncertainties=analysis.uncertainties,
                follow_up_questions=analysis.follow_up_questions,
            )
        )
        findings.extend(
            TaskForceAggregatedFinding(
                member_id=record.member_id,
                agent_id=record.agent_id,
                finding_id=finding.finding_id,
                summary=finding.summary,
                evidence_refs=finding.evidence_refs,
            )
            for finding in analysis.findings
        )
        uncertainties.extend(analysis.uncertainties)
        follow_up_questions.extend(analysis.follow_up_questions)
        if spec.task_role == "red_team":
            red_team.append(
                TaskForceRedTeamContribution(
                    member_id=record.member_id,
                    agent_id=record.agent_id,
                    answer=analysis.answer,
                    confidence=analysis.confidence,
                    finding_ids=finding_ids,
                    uncertainties=analysis.uncertainties,
                )
            )

    if request.red_team_required and not red_team:
        raise ValueError("request requires Red Team but completed execution has none")

    execution_fingerprint = task_force_execution_fingerprint(execution)
    total_cost = sum((record.actual_cost_eur for record in execution.member_records), ZERO)
    total_attempts = sum(record.attempts for record in execution.member_records)
    material = {
        "report_version": "batch20.task-force-report.v1",
        "task_force_id": contract.task_force_id,
        "execution_run_id": contract.execution_run_id,
        "request_id": contract.request_id,
        "system_id": contract.system_id,
        "opportunity_id": contract.opportunity_id,
        "objective": contract.objective,
        "question": contract.question,
        "execution_contract_fingerprint_sha256": (
            contract.execution_contract_fingerprint_sha256
        ),
        "execution_fingerprint_sha256": execution_fingerprint,
        "members": [member.model_dump(mode="json") for member in members],
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "uncertainties": _stable_unique(uncertainties),
        "follow_up_questions": _stable_unique(follow_up_questions),
        "red_team_required": request.red_team_required,
        "red_team_present": bool(red_team),
        "red_team_contributions": [item.model_dump(mode="json") for item in red_team],
        "member_actual_cost_eur": str(total_cost),
        "member_attempt_count": total_attempts,
        "aggregation_method": "PROVENANCE_PRESERVING_NO_SEMANTIC_VOTE",
        "semantic_consensus_computed": False,
        "aggregate_confidence_computed": False,
        "advisory_only": True,
        "trade_proposal_authority": False,
        "registry_mutation": False,
        "risk_authority": False,
        "live_authority": False,
    }
    return TaskForceReport(
        **material,
        aggregated_at=aggregated_at,
        report_fingerprint_sha256=_canonical_sha256(material),
    )


def _validate_aggregation_inputs(
    *,
    contract: TaskForceExecutionContract,
    execution: TaskForceMultiMemberExecution,
    plan: TaskForcePlan,
    request: TaskForceRequest,
    aggregated_at: datetime,
) -> None:
    if aggregated_at < execution.started_at:
        raise ValueError("Task Force aggregation cannot predate member execution")
    if aggregated_at >= contract.expires_at:
        raise PermissionError("expired Task Force cannot produce a new report")
    if execution.status is not TaskForceExecutionRunStatus.COMPLETED:
        raise PermissionError("only completed Task Force execution can be aggregated")
    if not execution.aggregation_ready or not execution.cost_accounting_complete:
        raise PermissionError("execution must be aggregation-ready with complete accounting")
    if execution.failure is not None:
        raise ValueError("completed Task Force execution cannot contain failure evidence")
    if execution.task_force_id != contract.task_force_id:
        raise ValueError("execution task_force_id does not match contract")
    if execution.execution_run_id != contract.execution_run_id:
        raise ValueError("execution_run_id does not match contract")
    if (
        execution.execution_contract_fingerprint_sha256
        != contract.execution_contract_fingerprint_sha256
    ):
        raise ValueError("execution contract fingerprint is stale")
    if task_force_plan_fingerprint(plan) != contract.plan_fingerprint_sha256:
        raise ValueError("aggregation plan fingerprint is stale")
    if plan.task_force_id != contract.task_force_id or plan.request_id != contract.request_id:
        raise ValueError("aggregation plan identity does not match contract")
    if request.request_id != contract.request_id or request.system_id != contract.system_id:
        raise ValueError("aggregation request identity does not match contract")
    if task_force_request_fingerprint(request) != plan.request_fingerprint_sha256:
        raise ValueError("aggregation request fingerprint is stale")
    if request.opportunity_id != contract.opportunity_id:
        raise ValueError("aggregation opportunity_id does not match contract")
    if request.objective != contract.objective or request.question != contract.question:
        raise ValueError("aggregation request content does not match contract")

    expected = [(spec.member_id, spec.agent_id) for spec in contract.member_specs]
    observed = [(record.member_id, record.agent_id) for record in execution.member_records]
    if observed != expected:
        raise ValueError("execution member order or identity does not match contract")


def _stable_unique(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        value = raw.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


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
