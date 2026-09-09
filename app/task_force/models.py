from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.models import AgentRegistryEntry, AgentRole, AgentState


_UNSAFE_TOOL_FRAGMENTS = (
    "broker",
    "exchange",
    "secret",
    "risk_engine",
    "shell",
    "filesystem",
    "withdraw",
    "live_order",
    "permission",
)


class TaskForceTrigger(StrEnum):
    COMPLEX_OPPORTUNITY = "COMPLEX_OPPORTUNITY"
    SPECIALIST_DISAGREEMENT = "SPECIALIST_DISAGREEMENT"
    UNUSUAL_MARKET_REGIME = "UNUSUAL_MARKET_REGIME"
    CONTRADICTORY_SIGNAL = "CONTRADICTORY_SIGNAL"
    RED_TEAM_REQUEST = "RED_TEAM_REQUEST"
    DEEP_DIVE = "DEEP_DIVE"
    INCIDENT_OR_ANOMALY = "INCIDENT_OR_ANOMALY"
    OPERATOR_REQUEST = "OPERATOR_REQUEST"


class TaskForceInfluenceScope(StrEnum):
    ORCHESTRATION_ADVISORY = "ORCHESTRATION_ADVISORY"
    EVALUATION_ONLY = "EVALUATION_ONLY"


class TaskForceState(StrEnum):
    PLANNED = "PLANNED"
    APPROVED_FOR_EXECUTION = "APPROVED_FOR_EXECUTION"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


def _ensure_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _normalize_unique(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if any(not value for value in normalized):
        raise ValueError(f"{field_name} must not contain blanks")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _assert_safe_tools(values: tuple[str, ...]) -> tuple[str, ...]:
    for tool in values:
        normalized = tool.lower()
        if any(fragment in normalized for fragment in _UNSAFE_TOOL_FRAGMENTS):
            raise ValueError(f"unsafe task-force tool: {tool}")
    return values


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class TaskForceRequest(BaseModel):
    """Explicit, non-trading request for a temporary multi-agent analysis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    request_id: str = Field(min_length=1, max_length=200)
    system_id: str = Field(min_length=1, max_length=100)
    opportunity_id: str | None = Field(default=None, max_length=200)
    trigger: TaskForceTrigger
    influence_scope: TaskForceInfluenceScope
    objective: str = Field(min_length=1, max_length=2000)
    question: str = Field(min_length=1, max_length=4000)
    requested_by: str = Field(min_length=1, max_length=200)
    context_refs: tuple[str, ...] = Field(min_length=1)
    required_roles: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    red_team_required: bool = False
    created_at: datetime
    expires_at: datetime
    auto_execute: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator(
        "request_id",
        "system_id",
        "objective",
        "question",
        "requested_by",
    )
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("opportunity_id")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("opportunity_id must not be blank")
        return stripped

    @field_validator("context_refs", "required_roles", "required_capabilities")
    @classmethod
    def _validate_tuple(cls, values: tuple[str, ...], info: Any) -> tuple[str, ...]:
        return _normalize_unique(values, field_name=info.field_name)

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value, field_name="created_at")

    @field_validator("expires_at")
    @classmethod
    def _validate_expires_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value, field_name="expires_at")

    @model_validator(mode="after")
    def _validate_expiry(self) -> TaskForceRequest:
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
        return self


class TaskForceOperatorPolicy(BaseModel):
    """Operator-owned Task Force limits; no production thresholds are inferred."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    policy_id: str = Field(min_length=1, max_length=200)
    max_task_force_members: int = Field(ge=1)
    max_concurrent_task_forces: int = Field(ge=0)
    max_task_forces_per_period: int = Field(ge=0)
    max_total_budget_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    max_budget_per_member_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    max_total_calls: int = Field(ge=0)
    max_calls_per_member: int = Field(ge=0)
    max_retries_per_call: int = Field(ge=0)
    allowed_agent_states: tuple[AgentState, ...] = Field(min_length=1)
    allowed_core_agent_ids: tuple[str, ...] = ()
    blocked_agent_ids: tuple[str, ...] = ()

    @field_validator("policy_id")
    @classmethod
    def _strip_policy_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("allowed_core_agent_ids", "blocked_agent_ids")
    @classmethod
    def _validate_agent_ids(cls, values: tuple[str, ...], info: Any) -> tuple[str, ...]:
        return _normalize_unique(values, field_name=info.field_name)

    @field_validator("allowed_agent_states")
    @classmethod
    def _validate_states(cls, values: tuple[AgentState, ...]) -> tuple[AgentState, ...]:
        if len(set(values)) != len(values):
            raise ValueError("allowed_agent_states must not contain duplicates")
        if AgentState.DISABLED in values:
            raise ValueError("DISABLED cannot be allowed by Task Force policy")
        return values

    @model_validator(mode="after")
    def _validate_agent_policy(self) -> TaskForceOperatorPolicy:
        overlap = set(self.allowed_core_agent_ids) & set(self.blocked_agent_ids)
        if overlap:
            raise ValueError("an agent cannot be both core-allowed and blocked")
        return self


class TaskForceRegistryAgentSnapshot(BaseModel):
    """Immutable audit snapshot derived only from an existing AgentRegistryEntry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    source: Literal["AGENT_REGISTRY"] = "AGENT_REGISTRY"
    agent_id: str = Field(min_length=1, max_length=100)
    role: AgentRole
    state: AgentState
    prompt_version: str = Field(min_length=1, max_length=100)
    model_route: str = Field(min_length=1, max_length=100)
    allowed_tools: tuple[str, ...] = ()
    budget_policy_id: str = Field(min_length=1, max_length=100)
    core: bool

    @field_validator("agent_id", "prompt_version", "model_route", "budget_policy_id")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("allowed_tools")
    @classmethod
    def _validate_tools(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = _normalize_unique(values, field_name="allowed_tools")
        return _assert_safe_tools(normalized)

    @classmethod
    def from_registry_entry(
        cls,
        entry: AgentRegistryEntry,
    ) -> TaskForceRegistryAgentSnapshot:
        return cls(
            agent_id=entry.agent_id,
            role=entry.role,
            state=entry.state,
            prompt_version=entry.prompt_version,
            model_route=entry.model_route,
            allowed_tools=entry.allowed_tools,
            budget_policy_id=entry.budget_policy_id,
            core=entry.core,
        )


class TaskForceMemberAssignment(BaseModel):
    """One already-selected member assignment; selection itself belongs to Batch 20b."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    member_id: str = Field(min_length=1, max_length=200)
    agent: TaskForceRegistryAgentSnapshot
    task_role: str = Field(min_length=1, max_length=200)
    capabilities: tuple[str, ...] = Field(min_length=1)
    selection_reasons: tuple[str, ...] = Field(min_length=1)
    reputation_evidence_refs: tuple[str, ...] = ()
    tool_allowlist: tuple[str, ...] = ()
    member_budget_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    max_calls: int = Field(ge=0)

    @field_validator("member_id", "task_role")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "capabilities",
        "selection_reasons",
        "reputation_evidence_refs",
        "tool_allowlist",
    )
    @classmethod
    def _validate_tuple(cls, values: tuple[str, ...], info: Any) -> tuple[str, ...]:
        normalized = _normalize_unique(values, field_name=info.field_name)
        if info.field_name == "tool_allowlist":
            _assert_safe_tools(normalized)
        return normalized

    @model_validator(mode="after")
    def _validate_tool_subset(self) -> TaskForceMemberAssignment:
        extra_tools = set(self.tool_allowlist) - set(self.agent.allowed_tools)
        if extra_tools:
            raise ValueError("Task Force membership cannot grant tools absent from AgentRegistry")
        return self


class TaskForcePlan(BaseModel):
    """Frozen plan contract. It is not execution approval and has no trading authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    task_force_id: str = Field(min_length=1, max_length=200)
    request_id: str = Field(min_length=1, max_length=200)
    request_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    policy_id: str = Field(min_length=1, max_length=200)
    policy_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    members: tuple[TaskForceMemberAssignment, ...] = Field(min_length=1)
    total_budget_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    total_call_limit: int = Field(ge=0)
    composition_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    state: Literal[TaskForceState.PLANNED] = TaskForceState.PLANNED
    created_at: datetime
    expires_at: datetime
    operator_authorization_required: Literal[True] = True
    auto_execute: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("task_force_id", "request_id", "policy_id")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "request_fingerprint_sha256",
        "policy_fingerprint_sha256",
        "composition_fingerprint_sha256",
    )
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("fingerprint must be lowercase hexadecimal SHA-256")
        return normalized

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value, field_name="created_at")

    @field_validator("expires_at")
    @classmethod
    def _validate_expires_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value, field_name="expires_at")

    @model_validator(mode="after")
    def _validate_plan(self) -> TaskForcePlan:
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
        member_ids = [member.member_id for member in self.members]
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("Task Force member_id values must be unique")
        agent_ids = [member.agent.agent_id for member in self.members]
        if len(set(agent_ids)) != len(agent_ids):
            raise ValueError("an agent cannot appear twice in the same Task Force plan")
        expected_budget = sum(
            (member.member_budget_eur for member in self.members),
            Decimal("0"),
        )
        if self.total_budget_eur != expected_budget:
            raise ValueError("total_budget_eur must equal the sum of member budgets")
        expected_calls = sum(member.max_calls for member in self.members)
        if self.total_call_limit != expected_calls:
            raise ValueError("total_call_limit must equal the sum of member max_calls")
        return self


def task_force_request_fingerprint(request: TaskForceRequest) -> str:
    payload = {
        "schema_version": request.schema_version,
        "system_id": request.system_id,
        "opportunity_id": request.opportunity_id,
        "trigger": request.trigger.value,
        "influence_scope": request.influence_scope.value,
        "objective": request.objective,
        "question": request.question,
        "requested_by": request.requested_by,
        "context_refs": sorted(request.context_refs),
        "required_roles": sorted(request.required_roles),
        "required_capabilities": sorted(request.required_capabilities),
        "red_team_required": request.red_team_required,
        "expires_at": request.expires_at.isoformat(),
    }
    return _canonical_sha256(payload)


def task_force_policy_fingerprint(policy: TaskForceOperatorPolicy) -> str:
    payload = policy.model_dump(mode="json")
    payload["allowed_agent_states"] = sorted(state.value for state in policy.allowed_agent_states)
    payload["allowed_core_agent_ids"] = sorted(policy.allowed_core_agent_ids)
    payload["blocked_agent_ids"] = sorted(policy.blocked_agent_ids)
    return _canonical_sha256(payload)


def task_force_composition_fingerprint(
    *,
    request_fingerprint_sha256: str,
    policy_fingerprint_sha256: str,
    members: tuple[TaskForceMemberAssignment, ...],
) -> str:
    member_payloads: list[dict[str, Any]] = []
    for member in sorted(members, key=lambda item: (item.agent.agent_id, item.task_role)):
        member_payloads.append(
            {
                "agent": member.agent.model_dump(mode="json"),
                "task_role": member.task_role,
                "capabilities": sorted(member.capabilities),
                "selection_reasons": sorted(member.selection_reasons),
                "reputation_evidence_refs": sorted(member.reputation_evidence_refs),
                "tool_allowlist": sorted(member.tool_allowlist),
                "member_budget_eur": str(member.member_budget_eur),
                "max_calls": member.max_calls,
            }
        )
    return _canonical_sha256(
        {
            "request_fingerprint_sha256": request_fingerprint_sha256,
            "policy_fingerprint_sha256": policy_fingerprint_sha256,
            "members": member_payloads,
        }
    )


def build_task_force_plan(
    *,
    task_force_id: str,
    request: TaskForceRequest,
    policy: TaskForceOperatorPolicy,
    members: tuple[TaskForceMemberAssignment, ...],
    created_at: datetime,
    expires_at: datetime,
) -> TaskForcePlan:
    """Package already-selected members into a deterministic plan; no gate is evaluated."""

    request_fingerprint = task_force_request_fingerprint(request)
    policy_fingerprint = task_force_policy_fingerprint(policy)
    composition_fingerprint = task_force_composition_fingerprint(
        request_fingerprint_sha256=request_fingerprint,
        policy_fingerprint_sha256=policy_fingerprint,
        members=members,
    )
    return TaskForcePlan(
        task_force_id=task_force_id,
        request_id=request.request_id,
        request_fingerprint_sha256=request_fingerprint,
        policy_id=policy.policy_id,
        policy_fingerprint_sha256=policy_fingerprint,
        members=members,
        total_budget_eur=sum(
            (member.member_budget_eur for member in members),
            Decimal("0"),
        ),
        total_call_limit=sum(member.max_calls for member in members),
        composition_fingerprint_sha256=composition_fingerprint,
        created_at=created_at,
        expires_at=expires_at,
    )
