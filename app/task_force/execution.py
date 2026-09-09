from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.intelligence.ai_gateway.models import AIGatewayRequest

from .composition_closure import (
    TaskForceCompositionClosure,
    task_force_plan_fingerprint,
)
from .gates import TaskForceGateStatus, TaskForcePlanGateDecision
from .lifecycle import TaskForceLifecycleRecord
from .models import (
    TaskForceInfluenceScope,
    TaskForceMemberAssignment,
    TaskForceRequest,
    TaskForceState,
    task_force_request_fingerprint,
)


class TaskForceMemberFinding(BaseModel):
    """One grounded advisory finding returned by a Task Force member."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=3000)
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("finding_id", "summary")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("evidence_refs")
    @classmethod
    def _canonical_evidence(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_values(values, field_name="evidence_refs")


class TaskForceMemberAnalysis(BaseModel):
    """Neutral structured AI output for one temporary Task Force member."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    task_force_id: str = Field(min_length=1, max_length=200)
    execution_run_id: str = Field(min_length=1, max_length=200)
    member_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=100)
    answer: str = Field(min_length=1, max_length=6000)
    findings: tuple[TaskForceMemberFinding, ...] = ()
    uncertainties: tuple[str, ...] = ()
    follow_up_questions: tuple[str, ...] = ()
    confidence: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    trade_proposal_authority: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator(
        "task_force_id",
        "execution_run_id",
        "member_id",
        "agent_id",
        "answer",
    )
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("uncertainties", "follow_up_questions")
    @classmethod
    def _canonical_text_tuple(cls, values: tuple[str, ...], info: Any) -> tuple[str, ...]:
        return _canonical_values(values, field_name=info.field_name, allow_empty=True)

    @model_validator(mode="after")
    def _unique_findings(self) -> TaskForceMemberAnalysis:
        finding_ids = [finding.finding_id for finding in self.findings]
        if len(set(finding_ids)) != len(finding_ids):
            raise ValueError("findings must have unique finding_id values")
        return self


class TaskForceMemberExecutionSpec(BaseModel):
    """Frozen member-to-gateway binding; it does not perform the gateway call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    member_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=100)
    task_role: str = Field(min_length=1, max_length=200)
    capabilities: tuple[str, ...] = Field(min_length=1)
    tool_allowlist: tuple[str, ...] = ()
    prompt_version: str = Field(min_length=1, max_length=100)
    model_route: str = Field(min_length=1, max_length=100)
    gateway_request_id: UUID
    max_output_tokens: int = Field(ge=1)
    member_budget_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    member_call_limit: int = Field(ge=0)
    analysis_schema: Literal["TaskForceMemberAnalysis"] = "TaskForceMemberAnalysis"
    trade_proposal_authority: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("member_id", "agent_id", "task_role", "prompt_version", "model_route")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("capabilities", "tool_allowlist")
    @classmethod
    def _canonical_tuple(cls, values: tuple[str, ...], info: Any) -> tuple[str, ...]:
        return _canonical_values(values, field_name=info.field_name, allow_empty=True)


class TaskForceExecutionContract(BaseModel):
    """Approved analysis-only handoff from Batch 20b into future member execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["batch20.task-force-execution-contract.v1"] = (
        "batch20.task-force-execution-contract.v1"
    )
    execution_run_id: str = Field(min_length=1, max_length=200)
    task_force_id: str = Field(min_length=1, max_length=200)
    request_id: str = Field(min_length=1, max_length=200)
    system_id: str = Field(min_length=1, max_length=100)
    opportunity_id: str | None = Field(default=None, max_length=200)
    influence_scope: TaskForceInfluenceScope
    objective: str = Field(min_length=1, max_length=2000)
    question: str = Field(min_length=1, max_length=4000)
    context_refs: tuple[str, ...] = Field(min_length=1)
    integration_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    plan_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    plan_gate_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    lifecycle_revision: int = Field(ge=1)
    approval_transition_id: str = Field(min_length=64, max_length=64)
    member_specs: tuple[TaskForceMemberExecutionSpec, ...] = Field(min_length=1)
    prepared_at: datetime
    expires_at: datetime
    execution_contract_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    member_analysis_authorized: Literal[True] = True
    gateway_required: Literal[True] = True
    gateway_calls_performed: Literal[False] = False
    trade_proposal_authority: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("execution_run_id", "task_force_id", "request_id", "system_id")
    @classmethod
    def _strip_ids(cls, value: str) -> str:
        return value.strip()

    @field_validator("opportunity_id")
    @classmethod
    def _strip_opportunity_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("opportunity_id must not be blank")
        return normalized

    @field_validator("objective", "question")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("context_refs")
    @classmethod
    def _canonical_context_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_values(values, field_name="context_refs")

    @field_validator(
        "integration_fingerprint_sha256",
        "plan_fingerprint_sha256",
        "plan_gate_fingerprint_sha256",
        "approval_transition_id",
        "execution_contract_fingerprint_sha256",
    )
    @classmethod
    def _validate_sha(cls, value: str) -> str:
        return _validate_sha256(value)

    @field_validator("prepared_at", "expires_at")
    @classmethod
    def _validate_time(cls, value: datetime, info: Any) -> datetime:
        return _ensure_utc(value, field_name=info.field_name)

    @model_validator(mode="after")
    def _validate_contract(self) -> TaskForceExecutionContract:
        if self.prepared_at >= self.expires_at:
            raise ValueError("execution contract must be prepared before expiry")
        member_ids = [spec.member_id for spec in self.member_specs]
        agent_ids = [spec.agent_id for spec in self.member_specs]
        gateway_ids = [spec.gateway_request_id for spec in self.member_specs]
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("member_specs must have unique member_id values")
        if len(set(agent_ids)) != len(agent_ids):
            raise ValueError("member_specs must have unique agent_id values")
        if len(set(gateway_ids)) != len(gateway_ids):
            raise ValueError("member_specs must have unique gateway_request_id values")
        return self


def build_task_force_execution_contract(
    *,
    execution_run_id: str,
    closure: TaskForceCompositionClosure,
    request: TaskForceRequest,
    lifecycle: TaskForceLifecycleRecord,
    plan_gate: TaskForcePlanGateDecision,
    max_output_tokens: int,
    prepared_at: datetime,
) -> TaskForceExecutionContract:
    """Build the analysis execution contract after gate ALLOW + operator approval.

    The function performs no AI call and grants no trading, Risk, broker, registry, or LIVE
    authority. The future runtime must still pass the per-call Task Force compute gate and
    the AI Gateway hard budget before each model call.
    """

    prepared_at = _ensure_utc(prepared_at, field_name="prepared_at")
    execution_run_id = execution_run_id.strip()
    if not execution_run_id:
        raise ValueError("execution_run_id must not be blank")
    if max_output_tokens < 1:
        raise ValueError("max_output_tokens must be >= 1")

    _validate_execution_readiness(
        closure=closure,
        request=request,
        lifecycle=lifecycle,
        plan_gate=plan_gate,
        prepared_at=prepared_at,
    )
    context_refs = _canonical_values(request.context_refs, field_name="context_refs")
    member_specs = tuple(
        _build_member_spec(
            execution_run_id=execution_run_id,
            task_force_id=closure.plan.task_force_id,
            member=member,
            max_output_tokens=max_output_tokens,
        )
        for member in closure.plan.members
    )
    approval_transition_id = lifecycle.transition_ids[-1]
    plan_fingerprint = task_force_plan_fingerprint(closure.plan)
    material = {
        "contract_version": "batch20.task-force-execution-contract.v1",
        "execution_run_id": execution_run_id,
        "task_force_id": closure.plan.task_force_id,
        "request_id": closure.plan.request_id,
        "system_id": request.system_id,
        "opportunity_id": request.opportunity_id,
        "influence_scope": request.influence_scope.value,
        "objective": request.objective,
        "question": request.question,
        "context_refs": sorted(context_refs),
        "integration_fingerprint_sha256": closure.manifest.integration_fingerprint_sha256,
        "plan_fingerprint_sha256": plan_fingerprint,
        "plan_gate_fingerprint_sha256": plan_gate.audit_fingerprint_sha256,
        "lifecycle_revision": lifecycle.revision,
        "approval_transition_id": approval_transition_id,
        "member_specs": [spec.model_dump(mode="json") for spec in member_specs],
        "prepared_at": prepared_at.isoformat(),
        "expires_at": closure.plan.expires_at.isoformat(),
        "member_analysis_authorized": True,
        "gateway_required": True,
        "gateway_calls_performed": False,
        "trade_proposal_authority": False,
        "registry_mutation": False,
        "risk_authority": False,
        "live_authority": False,
    }
    fingerprint = _canonical_sha256(material)
    return TaskForceExecutionContract(
        **material,
        execution_contract_fingerprint_sha256=fingerprint,
    )


def build_member_ai_gateway_request(
    contract: TaskForceExecutionContract,
    *,
    member_id: str,
    context_payload: dict[str, Any],
) -> AIGatewayRequest:
    """Build one real AIGatewayRequest without invoking the gateway or a provider."""

    member_id = member_id.strip()
    spec = next((item for item in contract.member_specs if item.member_id == member_id), None)
    if spec is None:
        raise ValueError("member_id is not part of this Task Force execution contract")
    if not context_payload:
        raise ValueError("context_payload must not be empty")

    context_json = _canonical_json(context_payload)
    input_payload = {
        "task_force_id": contract.task_force_id,
        "execution_run_id": contract.execution_run_id,
        "member_id": spec.member_id,
        "agent_id": spec.agent_id,
        "task_role": spec.task_role,
        "capabilities": list(spec.capabilities),
        "objective": contract.objective,
        "question": contract.question,
        "context_refs": list(contract.context_refs),
        "context": json.loads(context_json),
    }
    instructions = (
        "Return only a grounded advisory TaskForceMemberAnalysis. "
        "Use only the supplied context and identify uncertainty explicitly. "
        "Do not create orders, TradeProposal objects, Risk decisions, permissions, "
        "registry mutations, broker actions, or LIVE actions. "
        f"Echo task_force_id={contract.task_force_id}, "
        f"execution_run_id={contract.execution_run_id}, member_id={spec.member_id}, "
        f"agent_id={spec.agent_id}."
    )
    metadata = {
        "phase": "task_force_member_analysis",
        "task_force_id": contract.task_force_id,
        "execution_run_id": contract.execution_run_id,
        "member_id": spec.member_id,
        "task_role": spec.task_role,
        "influence_scope": contract.influence_scope.value,
        "execution_contract_fingerprint_sha256": (
            contract.execution_contract_fingerprint_sha256
        ),
    }
    return AIGatewayRequest(
        request_id=spec.gateway_request_id,
        system_id=contract.system_id,
        agent_id=spec.agent_id,
        prompt_version=spec.prompt_version,
        model_route=spec.model_route,
        input_text=_canonical_json(input_payload),
        instructions=instructions,
        max_output_tokens=spec.max_output_tokens,
        opportunity_id=_optional_uuid(contract.opportunity_id),
        metadata=metadata,
    )


def validate_task_force_member_analysis(
    contract: TaskForceExecutionContract,
    analysis: TaskForceMemberAnalysis,
) -> TaskForceMemberAnalysis:
    """Fail closed if structured AI output claims a different member or execution."""

    spec = next(
        (item for item in contract.member_specs if item.member_id == analysis.member_id),
        None,
    )
    if spec is None:
        raise ValueError("analysis member_id is outside the Task Force execution contract")
    if analysis.task_force_id != contract.task_force_id:
        raise ValueError("analysis task_force_id does not match execution contract")
    if analysis.execution_run_id != contract.execution_run_id:
        raise ValueError("analysis execution_run_id does not match execution contract")
    if analysis.agent_id != spec.agent_id:
        raise ValueError("analysis agent_id does not match member execution spec")
    return analysis


def _validate_execution_readiness(
    *,
    closure: TaskForceCompositionClosure,
    request: TaskForceRequest,
    lifecycle: TaskForceLifecycleRecord,
    plan_gate: TaskForcePlanGateDecision,
    prepared_at: datetime,
) -> None:
    plan = closure.plan
    manifest = closure.manifest
    if request.request_id != plan.request_id:
        raise ValueError("request_id does not match closed plan")
    if task_force_request_fingerprint(request) != plan.request_fingerprint_sha256:
        raise ValueError("request fingerprint is stale")
    expected_plan_fingerprint = task_force_plan_fingerprint(plan)
    if manifest.plan_fingerprint_sha256 != expected_plan_fingerprint:
        raise ValueError("composition closure plan fingerprint is inconsistent")
    if plan_gate.status is not TaskForceGateStatus.ALLOW:
        raise PermissionError("Task Force plan gate must ALLOW before member execution")
    if plan_gate.task_force_id != plan.task_force_id:
        raise ValueError("plan gate task_force_id does not match closed plan")
    if plan_gate.request_id != plan.request_id:
        raise ValueError("plan gate request_id does not match closed plan")
    if plan_gate.policy_id != plan.policy_id:
        raise ValueError("plan gate policy_id does not match closed plan")
    if plan_gate.request_fingerprint_sha256 != plan.request_fingerprint_sha256:
        raise ValueError("plan gate request fingerprint is stale")
    if plan_gate.policy_fingerprint_sha256 != plan.policy_fingerprint_sha256:
        raise ValueError("plan gate policy fingerprint is stale")
    if plan_gate.composition_fingerprint_sha256 != plan.composition_fingerprint_sha256:
        raise ValueError("plan gate composition fingerprint is stale")
    if lifecycle.task_force_id != plan.task_force_id or lifecycle.request_id != plan.request_id:
        raise ValueError("lifecycle identity does not match closed plan")
    if lifecycle.current_state is not TaskForceState.APPROVED_FOR_EXECUTION:
        raise PermissionError("Task Force lifecycle must be APPROVED_FOR_EXECUTION")
    if lifecycle.revision < 1 or not lifecycle.transition_ids:
        raise ValueError("approved Task Force lifecycle must include approval transition evidence")
    if lifecycle.request_fingerprint_sha256 != plan.request_fingerprint_sha256:
        raise ValueError("lifecycle request fingerprint is stale")
    if lifecycle.policy_fingerprint_sha256 != plan.policy_fingerprint_sha256:
        raise ValueError("lifecycle policy fingerprint is stale")
    if lifecycle.composition_fingerprint_sha256 != plan.composition_fingerprint_sha256:
        raise ValueError("lifecycle composition fingerprint is stale")
    if prepared_at < lifecycle.updated_at:
        raise ValueError("execution contract cannot predate lifecycle approval")
    if prepared_at >= min(plan.expires_at, lifecycle.expires_at):
        raise ValueError("expired Task Force cannot prepare an execution contract")


def _build_member_spec(
    *,
    execution_run_id: str,
    task_force_id: str,
    member: TaskForceMemberAssignment,
    max_output_tokens: int,
) -> TaskForceMemberExecutionSpec:
    gateway_request_id = uuid5(
        NAMESPACE_URL,
        f"money-heist/task-force/{task_force_id}/{execution_run_id}/{member.member_id}",
    )
    return TaskForceMemberExecutionSpec(
        member_id=member.member_id,
        agent_id=member.agent.agent_id,
        task_role=member.task_role,
        capabilities=member.capabilities,
        tool_allowlist=member.tool_allowlist,
        prompt_version=member.agent.prompt_version,
        model_route=member.agent.model_route,
        gateway_request_id=gateway_request_id,
        max_output_tokens=max_output_tokens,
        member_budget_eur=member.member_budget_eur,
        member_call_limit=member.max_calls,
    )


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError("optional text must not be blank")
    return normalized


def _canonical_values(
    values: tuple[str, ...],
    *,
    field_name: str,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not values and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    normalized = tuple(value.strip() for value in values)
    if any(not value for value in normalized):
        raise ValueError(f"{field_name} must not contain blanks")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return tuple(sorted(normalized))


def _validate_sha256(value: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError("fingerprint must be a SHA-256 hexadecimal digest")
    return normalized


def _ensure_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _canonical_json(payload: Any) -> str:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=_reject_non_json_value,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must be JSON-serializable") from exc


def _reject_non_json_value(value: Any) -> Any:
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _canonical_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _optional_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None
