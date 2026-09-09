from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.models import AgentRole

from .models import (
    TaskForceOperatorPolicy,
    TaskForcePlan,
    TaskForceRequest,
    task_force_composition_fingerprint,
    task_force_policy_fingerprint,
    task_force_request_fingerprint,
)


class TaskForceGateStatus(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


class TaskForceCapacitySnapshot(BaseModel):
    """Read-only population snapshot for one explicit operator policy period."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    period_id: str = Field(min_length=1, max_length=200)
    concurrent_task_forces: int = Field(ge=0)
    task_forces_started: int = Field(ge=0)

    @field_validator("period_id")
    @classmethod
    def _strip_period_id(cls, value: str) -> str:
        return value.strip()


class TaskForcePlanGateDecision(BaseModel):
    """Fail-closed admission result. ALLOW never executes the Task Force."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gate_version: Literal["batch20.task-force-plan-gate.v1"] = (
        "batch20.task-force-plan-gate.v1"
    )
    task_force_id: str = Field(min_length=1, max_length=200)
    request_id: str = Field(min_length=1, max_length=200)
    policy_id: str = Field(min_length=1, max_length=200)
    period_id: str = Field(min_length=1, max_length=200)
    status: TaskForceGateStatus
    reason_codes: tuple[str, ...] = Field(min_length=1)
    missing_roles: tuple[str, ...] = ()
    missing_capabilities: tuple[str, ...] = ()
    request_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    policy_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    composition_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    capacity_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    audit_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    operator_authorization_required: Literal[True] = True
    execute_task_force: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("task_force_id", "request_id", "policy_id", "period_id")
    @classmethod
    def _strip_ids(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "request_fingerprint_sha256",
        "policy_fingerprint_sha256",
        "composition_fingerprint_sha256",
        "capacity_fingerprint_sha256",
        "audit_fingerprint_sha256",
    )
    @classmethod
    def _validate_fingerprint(cls, value: str) -> str:
        return _validate_sha256(value, field_name="fingerprint")

    @field_validator("reason_codes", "missing_roles", "missing_capabilities")
    @classmethod
    def _canonical_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("audit values must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("audit values must not contain duplicates")
        return tuple(sorted(normalized))


class TaskForceComputeRequest(BaseModel):
    """Prospective Task Force AI charge. This object cannot call a provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_force_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=100)
    spent_total_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    spent_member_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    used_total_calls: int = Field(ge=0)
    used_member_calls: int = Field(ge=0)
    requested_eur: Decimal = Field(gt=0, allow_inf_nan=False)
    retry_index: int = Field(default=0, ge=0)

    @field_validator("task_force_id", "agent_id")
    @classmethod
    def _strip_ids(cls, value: str) -> str:
        return value.strip()


class TaskForceComputeDecision(BaseModel):
    """Task-Force-scoped compute gate; AI Gateway hard budget remains authoritative."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gate_version: Literal["batch20.task-force-compute-gate.v1"] = (
        "batch20.task-force-compute-gate.v1"
    )
    task_force_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=100)
    policy_id: str = Field(min_length=1, max_length=200)
    status: TaskForceGateStatus
    reason_codes: tuple[str, ...] = Field(min_length=1)
    effective_total_budget_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    effective_member_budget_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    effective_total_call_limit: int = Field(ge=0)
    effective_member_call_limit: int = Field(ge=0)
    projected_total_spend_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    projected_member_spend_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    projected_total_calls: int = Field(ge=0)
    projected_member_calls: int = Field(ge=0)
    retry_index: int = Field(ge=0)
    audit_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    gateway_budget_still_required: Literal[True] = True
    execute_compute: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("task_force_id", "agent_id", "policy_id")
    @classmethod
    def _strip_ids(cls, value: str) -> str:
        return value.strip()

    @field_validator("audit_fingerprint_sha256")
    @classmethod
    def _validate_audit_fingerprint(cls, value: str) -> str:
        return _validate_sha256(value, field_name="audit_fingerprint_sha256")

    @field_validator("reason_codes")
    @classmethod
    def _canonical_reasons(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("reason_codes must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("reason_codes must not contain duplicates")
        return tuple(sorted(normalized))

    @model_validator(mode="after")
    def _coherent_projection(self) -> TaskForceComputeDecision:
        if self.projected_total_calls < 1 or self.projected_member_calls < 1:
            raise ValueError("projected call counts must include the prospective call")
        return self


def evaluate_task_force_plan(
    request: TaskForceRequest,
    plan: TaskForcePlan,
    policy: TaskForceOperatorPolicy,
    *,
    capacity: TaskForceCapacitySnapshot,
    evaluated_at: datetime,
) -> TaskForcePlanGateDecision:
    """Evaluate one frozen plan without changing lifecycle or external state."""

    evaluated_at = _ensure_utc(evaluated_at, field_name="evaluated_at")
    reasons: list[str] = []

    expected_request = task_force_request_fingerprint(request)
    expected_policy = task_force_policy_fingerprint(policy)
    expected_composition = task_force_composition_fingerprint(
        request_fingerprint_sha256=expected_request,
        policy_fingerprint_sha256=expected_policy,
        members=plan.members,
    )

    if plan.request_id != request.request_id:
        reasons.append("REQUEST_ID_MISMATCH")
    if plan.policy_id != policy.policy_id:
        reasons.append("POLICY_ID_MISMATCH")
    if plan.request_fingerprint_sha256 != expected_request:
        reasons.append("STALE_REQUEST_FINGERPRINT")
    if plan.policy_fingerprint_sha256 != expected_policy:
        reasons.append("STALE_POLICY_FINGERPRINT")
    if plan.composition_fingerprint_sha256 != expected_composition:
        reasons.append("STALE_COMPOSITION_FINGERPRINT")

    if evaluated_at >= request.expires_at or evaluated_at >= plan.expires_at:
        reasons.append("TASK_FORCE_EXPIRED")
    if plan.created_at < request.created_at:
        reasons.append("PLAN_PREDATES_REQUEST")
    if plan.expires_at > request.expires_at:
        reasons.append("PLAN_EXPIRY_EXCEEDS_REQUEST")

    if capacity.concurrent_task_forces >= policy.max_concurrent_task_forces:
        reasons.append("CONCURRENT_TASK_FORCE_CAP_REACHED")
    if capacity.task_forces_started >= policy.max_task_forces_per_period:
        reasons.append("TASK_FORCE_FREQUENCY_CAP_REACHED")
    if len(plan.members) > policy.max_task_force_members:
        reasons.append("TASK_FORCE_MEMBER_CAP_EXCEEDED")

    if plan.total_budget_eur > policy.max_total_budget_eur:
        reasons.append("TASK_FORCE_TOTAL_BUDGET_EXCEEDED")
    if plan.total_call_limit > policy.max_total_calls:
        reasons.append("TASK_FORCE_TOTAL_CALL_LIMIT_EXCEEDED")

    present_roles: set[str] = set()
    present_capabilities: set[str] = set()
    red_team_present = False
    for member in plan.members:
        agent = member.agent
        present_roles.add(agent.role.value)
        present_capabilities.update(member.capabilities)
        if agent.role is AgentRole.RED_TEAM:
            red_team_present = True
        if agent.state not in policy.allowed_agent_states:
            reasons.append("AGENT_STATE_NOT_ALLOWED")
        if agent.agent_id in policy.blocked_agent_ids:
            reasons.append("BLOCKED_AGENT_SELECTED")
        if agent.core and agent.agent_id not in policy.allowed_core_agent_ids:
            reasons.append("CORE_AGENT_NOT_ALLOWED")
        if member.member_budget_eur > policy.max_budget_per_member_eur:
            reasons.append("MEMBER_BUDGET_EXCEEDED")
        if member.max_calls > policy.max_calls_per_member:
            reasons.append("MEMBER_CALL_LIMIT_EXCEEDED")

    missing_roles = tuple(sorted(set(request.required_roles) - present_roles))
    missing_capabilities = tuple(
        sorted(set(request.required_capabilities) - present_capabilities)
    )
    if missing_roles:
        reasons.append("REQUIRED_ROLE_COVERAGE_INCOMPLETE")
    if missing_capabilities:
        reasons.append("REQUIRED_CAPABILITY_COVERAGE_INCOMPLETE")
    if request.red_team_required and not red_team_present:
        reasons.append("RED_TEAM_REQUIRED_BUT_MISSING")

    if reasons:
        status = TaskForceGateStatus.BLOCK
    else:
        status = TaskForceGateStatus.ALLOW
        reasons.append("WITHIN_EXPLICIT_TASK_FORCE_LIMITS")

    canonical_reasons = tuple(sorted(set(reasons)))
    capacity_fingerprint = _capacity_fingerprint(capacity)
    audit_fingerprint = _plan_gate_fingerprint(
        request=request,
        plan=plan,
        policy=policy,
        capacity=capacity,
        evaluated_at=evaluated_at,
        status=status,
        reason_codes=canonical_reasons,
        missing_roles=missing_roles,
        missing_capabilities=missing_capabilities,
        expected_request=expected_request,
        expected_policy=expected_policy,
        expected_composition=expected_composition,
    )
    return TaskForcePlanGateDecision(
        task_force_id=plan.task_force_id,
        request_id=request.request_id,
        policy_id=policy.policy_id,
        period_id=capacity.period_id,
        status=status,
        reason_codes=canonical_reasons,
        missing_roles=missing_roles,
        missing_capabilities=missing_capabilities,
        request_fingerprint_sha256=expected_request,
        policy_fingerprint_sha256=expected_policy,
        composition_fingerprint_sha256=expected_composition,
        capacity_fingerprint_sha256=capacity_fingerprint,
        audit_fingerprint_sha256=audit_fingerprint,
    )


def evaluate_task_force_compute(
    plan: TaskForcePlan,
    policy: TaskForceOperatorPolicy,
    request: TaskForceComputeRequest,
) -> TaskForceComputeDecision:
    """Check one prospective member call against Task Force limits only."""

    if request.task_force_id != plan.task_force_id:
        raise ValueError("compute request targets a different task_force_id")

    member = next(
        (item for item in plan.members if item.agent.agent_id == request.agent_id),
        None,
    )
    if member is None:
        raise ValueError("compute request targets an agent outside the Task Force plan")

    effective_total_budget = min(plan.total_budget_eur, policy.max_total_budget_eur)
    effective_member_budget = min(
        member.member_budget_eur,
        policy.max_budget_per_member_eur,
    )
    effective_total_calls = min(plan.total_call_limit, policy.max_total_calls)
    effective_member_calls = min(member.max_calls, policy.max_calls_per_member)

    projected_total_spend = request.spent_total_eur + request.requested_eur
    projected_member_spend = request.spent_member_eur + request.requested_eur
    projected_total_calls = request.used_total_calls + 1
    projected_member_calls = request.used_member_calls + 1

    reasons: list[str] = []
    if plan.policy_id != policy.policy_id:
        reasons.append("POLICY_ID_MISMATCH")
    if plan.policy_fingerprint_sha256 != task_force_policy_fingerprint(policy):
        reasons.append("STALE_POLICY_FINGERPRINT")
    if request.spent_total_eur > effective_total_budget:
        reasons.append("TASK_FORCE_BUDGET_ALREADY_EXCEEDED")
    if projected_total_spend > effective_total_budget:
        reasons.append("TASK_FORCE_COMPUTE_BUDGET_EXCEEDED")
    if request.spent_member_eur > effective_member_budget:
        reasons.append("MEMBER_BUDGET_ALREADY_EXCEEDED")
    if projected_member_spend > effective_member_budget:
        reasons.append("MEMBER_COMPUTE_BUDGET_EXCEEDED")
    if request.used_total_calls > effective_total_calls:
        reasons.append("TASK_FORCE_CALL_LIMIT_ALREADY_EXCEEDED")
    if projected_total_calls > effective_total_calls:
        reasons.append("TASK_FORCE_CALL_LIMIT_EXCEEDED")
    if request.used_member_calls > effective_member_calls:
        reasons.append("MEMBER_CALL_LIMIT_ALREADY_EXCEEDED")
    if projected_member_calls > effective_member_calls:
        reasons.append("MEMBER_CALL_LIMIT_EXCEEDED")
    if request.retry_index > policy.max_retries_per_call:
        reasons.append("RETRY_LIMIT_EXCEEDED")

    if reasons:
        status = TaskForceGateStatus.BLOCK
    else:
        status = TaskForceGateStatus.ALLOW
        reasons.append("WITHIN_EXPLICIT_TASK_FORCE_COMPUTE_LIMITS")

    canonical_reasons = tuple(sorted(set(reasons)))
    audit_fingerprint = _compute_gate_fingerprint(
        plan=plan,
        policy=policy,
        request=request,
        status=status,
        reason_codes=canonical_reasons,
        effective_total_budget=effective_total_budget,
        effective_member_budget=effective_member_budget,
        effective_total_calls=effective_total_calls,
        effective_member_calls=effective_member_calls,
        projected_total_spend=projected_total_spend,
        projected_member_spend=projected_member_spend,
        projected_total_calls=projected_total_calls,
        projected_member_calls=projected_member_calls,
    )
    return TaskForceComputeDecision(
        task_force_id=plan.task_force_id,
        agent_id=request.agent_id,
        policy_id=policy.policy_id,
        status=status,
        reason_codes=canonical_reasons,
        effective_total_budget_eur=effective_total_budget,
        effective_member_budget_eur=effective_member_budget,
        effective_total_call_limit=effective_total_calls,
        effective_member_call_limit=effective_member_calls,
        projected_total_spend_eur=projected_total_spend,
        projected_member_spend_eur=projected_member_spend,
        projected_total_calls=projected_total_calls,
        projected_member_calls=projected_member_calls,
        retry_index=request.retry_index,
        audit_fingerprint_sha256=audit_fingerprint,
    )


def _ensure_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _validate_sha256(value: str, *, field_name: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a SHA-256 hexadecimal digest")
    return normalized


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _capacity_fingerprint(capacity: TaskForceCapacitySnapshot) -> str:
    return _canonical_sha256(capacity.model_dump(mode="json"))


def _plan_gate_fingerprint(
    *,
    request: TaskForceRequest,
    plan: TaskForcePlan,
    policy: TaskForceOperatorPolicy,
    capacity: TaskForceCapacitySnapshot,
    evaluated_at: datetime,
    status: TaskForceGateStatus,
    reason_codes: tuple[str, ...],
    missing_roles: tuple[str, ...],
    missing_capabilities: tuple[str, ...],
    expected_request: str,
    expected_policy: str,
    expected_composition: str,
) -> str:
    return _canonical_sha256(
        {
            "gate_version": "batch20.task-force-plan-gate.v1",
            "task_force_id": plan.task_force_id,
            "request_id": request.request_id,
            "policy_id": policy.policy_id,
            "period_id": capacity.period_id,
            "evaluated_at": evaluated_at.isoformat(),
            "status": status.value,
            "reason_codes": reason_codes,
            "missing_roles": missing_roles,
            "missing_capabilities": missing_capabilities,
            "request_fingerprint_sha256": expected_request,
            "policy_fingerprint_sha256": expected_policy,
            "composition_fingerprint_sha256": expected_composition,
            "capacity_fingerprint_sha256": _capacity_fingerprint(capacity),
            "operator_authorization_required": True,
            "execute_task_force": False,
            "registry_mutation": False,
            "risk_authority": False,
            "live_authority": False,
        }
    )


def _compute_gate_fingerprint(
    *,
    plan: TaskForcePlan,
    policy: TaskForceOperatorPolicy,
    request: TaskForceComputeRequest,
    status: TaskForceGateStatus,
    reason_codes: tuple[str, ...],
    effective_total_budget: Decimal,
    effective_member_budget: Decimal,
    effective_total_calls: int,
    effective_member_calls: int,
    projected_total_spend: Decimal,
    projected_member_spend: Decimal,
    projected_total_calls: int,
    projected_member_calls: int,
) -> str:
    return _canonical_sha256(
        {
            "gate_version": "batch20.task-force-compute-gate.v1",
            "task_force_id": plan.task_force_id,
            "agent_id": request.agent_id,
            "policy_id": policy.policy_id,
            "status": status.value,
            "reason_codes": reason_codes,
            "effective_total_budget_eur": str(effective_total_budget),
            "effective_member_budget_eur": str(effective_member_budget),
            "effective_total_call_limit": effective_total_calls,
            "effective_member_call_limit": effective_member_calls,
            "spent_total_eur": str(request.spent_total_eur),
            "spent_member_eur": str(request.spent_member_eur),
            "requested_eur": str(request.requested_eur),
            "projected_total_spend_eur": str(projected_total_spend),
            "projected_member_spend_eur": str(projected_member_spend),
            "projected_total_calls": projected_total_calls,
            "projected_member_calls": projected_member_calls,
            "retry_index": request.retry_index,
            "gateway_budget_still_required": True,
            "execute_compute": False,
            "registry_mutation": False,
            "risk_authority": False,
            "live_authority": False,
        }
    )
