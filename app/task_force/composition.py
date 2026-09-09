from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.models import AgentState
from app.agents.registry import AgentRegistry

from .models import (
    TaskForceMemberAssignment,
    TaskForceOperatorPolicy,
    TaskForceRegistryAgentSnapshot,
    TaskForceRequest,
)

if TYPE_CHECKING:
    from app.evaluation.reputation_advisory import AgentReputationAdvisoryReport


class TaskForceReputationDimension(StrEnum):
    OOS_EVIDENCE = "OOS_EVIDENCE"
    MARGINAL_ECONOMIC_NET = "MARGINAL_ECONOMIC_NET"
    DRAWDOWN_REDUCTION = "DRAWDOWN_REDUCTION"
    AVERAGE_COST = "AVERAGE_COST"
    AVERAGE_LATENCY = "AVERAGE_LATENCY"


class TaskForceCapabilityProfile(BaseModel):
    """Explicit capabilities available to the composer; no capability is inferred."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(min_length=1, max_length=100)
    capabilities: tuple[str, ...] = ()

    @field_validator("agent_id")
    @classmethod
    def _strip_agent_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("capabilities")
    @classmethod
    def _normalize_capabilities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("capabilities must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("capabilities must not contain duplicates")
        return tuple(sorted(normalized))


class TaskForceReputationSnapshot(BaseModel):
    """Multidimensional Batch 18 evidence, preserved without an aggregate score."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(min_length=1, max_length=100)
    advisory_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    evaluation_sample_count: int = Field(ge=0)
    oos_ablation_comparison_count: int = Field(ge=0)
    marginal_economic_net_eur: Decimal | None = None
    drawdown_reduction_pct: Decimal | None = None
    average_cost_eur: Decimal | None = Field(default=None, ge=0)
    average_latency_ms: Decimal | None = Field(default=None, ge=0)
    recommended_state: AgentState
    evidence_sufficiency: str = Field(min_length=1, max_length=100)
    recommendation_action: str = Field(min_length=1, max_length=100)
    auto_apply: Literal[False] = False

    @field_validator("agent_id", "evidence_sufficiency", "recommendation_action")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("advisory_fingerprint_sha256")
    @classmethod
    def _validate_fingerprint(cls, value: str) -> str:
        normalized = value.lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("advisory fingerprint must be lowercase SHA-256 hex")
        return normalized

    @classmethod
    def from_advisory(
        cls,
        report: AgentReputationAdvisoryReport,
    ) -> TaskForceReputationSnapshot:
        reputation = report.reputation
        return cls(
            agent_id=report.agent_id,
            advisory_fingerprint_sha256=report.audit_fingerprint_sha256,
            evaluation_sample_count=reputation.call_count,
            oos_ablation_comparison_count=reputation.oos_ablation_comparison_count,
            marginal_economic_net_eur=_metric_value(reputation.marginal_economic_net),
            drawdown_reduction_pct=_metric_value(reputation.drawdown_reduction_pct),
            average_cost_eur=_metric_value(reputation.average_cost_eur),
            average_latency_ms=_metric_value(reputation.average_latency_ms),
            recommended_state=report.recommendation.recommended_state,
            evidence_sufficiency=report.recommendation.evidence_sufficiency.value,
            recommendation_action=report.recommendation.action.value,
        )


class TaskForceCompositionPolicy(BaseModel):
    """Explicit operator-owned selection preferences; no hidden weighted score."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["batch20.task-force-composition.v1"] = (
        "batch20.task-force-composition.v1"
    )
    composition_policy_id: str = Field(min_length=1, max_length=200)
    target_member_count: int = Field(ge=1)
    member_budget_eur: Decimal = Field(ge=0)
    member_max_calls: int = Field(ge=0)
    state_preference: tuple[AgentState, ...] = Field(min_length=1)
    reputation_priority: tuple[TaskForceReputationDimension, ...] = ()
    require_reputation_evidence: bool = False
    require_sufficient_reputation_evidence: bool = False

    @field_validator("composition_policy_id")
    @classmethod
    def _strip_policy_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("state_preference")
    @classmethod
    def _validate_state_preference(
        cls,
        values: tuple[AgentState, ...],
    ) -> tuple[AgentState, ...]:
        if len(set(values)) != len(values):
            raise ValueError("state_preference must not contain duplicates")
        if AgentState.DISABLED in values:
            raise ValueError("DISABLED cannot be preferred for a Task Force")
        return values

    @field_validator("reputation_priority")
    @classmethod
    def _validate_reputation_priority(
        cls,
        values: tuple[TaskForceReputationDimension, ...],
    ) -> tuple[TaskForceReputationDimension, ...]:
        if len(set(values)) != len(values):
            raise ValueError("reputation_priority must not contain duplicates")
        return values


class TaskForceCompositionExclusion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(min_length=1, max_length=100)
    reason_codes: tuple[str, ...] = Field(min_length=1)

    @field_validator("agent_id")
    @classmethod
    def _strip_agent_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("reason_codes")
    @classmethod
    def _normalize_reasons(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("reason_codes must not contain blanks")
        return tuple(sorted(set(normalized)))


class TaskForceCompositionResult(BaseModel):
    """Advisory composition only; it neither builds approval nor executes members."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    result_version: Literal["batch20.task-force-composition-result.v1"] = (
        "batch20.task-force-composition-result.v1"
    )
    request_id: str = Field(min_length=1, max_length=200)
    composition_policy_id: str = Field(min_length=1, max_length=200)
    members: tuple[TaskForceMemberAssignment, ...]
    exclusions: tuple[TaskForceCompositionExclusion, ...]
    uncovered_roles: tuple[str, ...]
    uncovered_capabilities: tuple[str, ...]
    red_team_covered: bool
    composition_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    complete: bool
    aggregate_reputation_score: Literal[None] = None
    auto_execute: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False


class _Candidate:
    def __init__(
        self,
        *,
        agent: TaskForceRegistryAgentSnapshot,
        capabilities: tuple[str, ...],
        reputation: TaskForceReputationSnapshot | None,
    ) -> None:
        self.agent = agent
        self.capabilities = capabilities
        self.reputation = reputation


def compose_task_force_members(
    request: TaskForceRequest,
    operator_policy: TaskForceOperatorPolicy,
    composition_policy: TaskForceCompositionPolicy,
    *,
    registry: AgentRegistry,
    capability_profiles: tuple[TaskForceCapabilityProfile, ...] = (),
    reputation_reports: tuple[AgentReputationAdvisoryReport, ...] = (),
) -> TaskForceCompositionResult:
    """Select registry-backed members deterministically without mutating any source state."""

    if composition_policy.target_member_count > operator_policy.max_task_force_members:
        raise ValueError("target_member_count exceeds operator max_task_force_members")
    if composition_policy.member_budget_eur > operator_policy.max_budget_per_member_eur:
        raise ValueError("member_budget_eur exceeds operator max_budget_per_member_eur")
    if composition_policy.member_max_calls > operator_policy.max_calls_per_member:
        raise ValueError("member_max_calls exceeds operator max_calls_per_member")

    capability_by_agent = _capability_map(capability_profiles)
    reputation_by_agent = _reputation_map(reputation_reports)
    candidates: list[_Candidate] = []
    exclusions: list[TaskForceCompositionExclusion] = []

    for entry in registry.available():
        reasons: list[str] = []
        if entry.state not in operator_policy.allowed_agent_states:
            reasons.append("STATE_NOT_ALLOWED_BY_OPERATOR_POLICY")
        if entry.agent_id in operator_policy.blocked_agent_ids:
            reasons.append("AGENT_BLOCKED_BY_OPERATOR_POLICY")
        if entry.core and entry.agent_id not in operator_policy.allowed_core_agent_ids:
            reasons.append("CORE_AGENT_NOT_EXPLICITLY_ALLOWED")

        reputation = reputation_by_agent.get(entry.agent_id)
        if composition_policy.require_reputation_evidence and reputation is None:
            reasons.append("REPUTATION_EVIDENCE_REQUIRED")
        if (
            composition_policy.require_sufficient_reputation_evidence
            and reputation is not None
            and reputation.evidence_sufficiency != "SUFFICIENT"
        ):
            reasons.append("REPUTATION_EVIDENCE_INSUFFICIENT")

        if reasons:
            exclusions.append(
                TaskForceCompositionExclusion(
                    agent_id=entry.agent_id,
                    reason_codes=tuple(reasons),
                )
            )
            continue
        candidates.append(
            _Candidate(
                agent=TaskForceRegistryAgentSnapshot.from_registry_entry(entry),
                capabilities=capability_by_agent.get(entry.agent_id, ()),
                reputation=reputation,
            )
        )

    uncovered_roles = set(request.required_roles)
    uncovered_capabilities = set(request.required_capabilities)
    red_team_needed = request.red_team_required
    selected: list[_Candidate] = []

    while candidates and len(selected) < composition_policy.target_member_count:
        ranked = sorted(
            candidates,
            key=lambda item: _candidate_key(
                item,
                uncovered_roles=uncovered_roles,
                uncovered_capabilities=uncovered_capabilities,
                red_team_needed=red_team_needed,
                policy=composition_policy,
            ),
        )
        best = ranked[0]
        coverage = _coverage_count(
            best,
            uncovered_roles=uncovered_roles,
            uncovered_capabilities=uncovered_capabilities,
            red_team_needed=red_team_needed,
        )
        if coverage == 0 and (uncovered_roles or uncovered_capabilities or red_team_needed):
            break
        selected.append(best)
        candidates.remove(best)
        uncovered_roles.discard(best.agent.role.value)
        uncovered_capabilities.difference_update(best.capabilities)
        if best.agent.role.value == "red_team":
            red_team_needed = False

    while candidates and len(selected) < composition_policy.target_member_count:
        best = sorted(
            candidates,
            key=lambda item: _candidate_key(
                item,
                uncovered_roles=set(),
                uncovered_capabilities=set(),
                red_team_needed=False,
                policy=composition_policy,
            ),
        )[0]
        selected.append(best)
        candidates.remove(best)

    members = tuple(_assignment(item, composition_policy) for item in selected)
    complete = (
        len(selected) == composition_policy.target_member_count
        and not uncovered_roles
        and not uncovered_capabilities
        and not red_team_needed
    )
    fingerprint = _composition_fingerprint(
        request=request,
        operator_policy=operator_policy,
        composition_policy=composition_policy,
        members=members,
        exclusions=tuple(exclusions),
        uncovered_roles=tuple(sorted(uncovered_roles)),
        uncovered_capabilities=tuple(sorted(uncovered_capabilities)),
        red_team_covered=not red_team_needed,
    )
    return TaskForceCompositionResult(
        request_id=request.request_id,
        composition_policy_id=composition_policy.composition_policy_id,
        members=members,
        exclusions=tuple(sorted(exclusions, key=lambda item: item.agent_id)),
        uncovered_roles=tuple(sorted(uncovered_roles)),
        uncovered_capabilities=tuple(sorted(uncovered_capabilities)),
        red_team_covered=not red_team_needed,
        composition_fingerprint_sha256=fingerprint,
        complete=complete,
    )


def _capability_map(
    profiles: tuple[TaskForceCapabilityProfile, ...],
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for profile in profiles:
        if profile.agent_id in result:
            raise ValueError(f"duplicate capability profile: {profile.agent_id}")
        result[profile.agent_id] = profile.capabilities
    return result


def _reputation_map(
    reports: tuple[AgentReputationAdvisoryReport, ...],
) -> dict[str, TaskForceReputationSnapshot]:
    result: dict[str, TaskForceReputationSnapshot] = {}
    for report in reports:
        snapshot = TaskForceReputationSnapshot.from_advisory(report)
        if snapshot.agent_id in result:
            raise ValueError(f"duplicate reputation report: {snapshot.agent_id}")
        result[snapshot.agent_id] = snapshot
    return result


def _metric_value(metric: Any) -> Decimal | None:
    status = getattr(metric.status, "value", str(metric.status))
    if status != "AVAILABLE":
        return None
    return metric.value


def _coverage_count(
    candidate: _Candidate,
    *,
    uncovered_roles: set[str],
    uncovered_capabilities: set[str],
    red_team_needed: bool,
) -> int:
    count = int(candidate.agent.role.value in uncovered_roles)
    count += len(set(candidate.capabilities) & uncovered_capabilities)
    if red_team_needed and candidate.agent.role.value == "red_team":
        count += 1
    return count


def _candidate_key(
    candidate: _Candidate,
    *,
    uncovered_roles: set[str],
    uncovered_capabilities: set[str],
    red_team_needed: bool,
    policy: TaskForceCompositionPolicy,
) -> tuple[Any, ...]:
    coverage = _coverage_count(
        candidate,
        uncovered_roles=uncovered_roles,
        uncovered_capabilities=uncovered_capabilities,
        red_team_needed=red_team_needed,
    )
    try:
        state_rank = policy.state_preference.index(candidate.agent.state)
    except ValueError:
        state_rank = len(policy.state_preference)
    reputation_key = tuple(
        _reputation_dimension_key(candidate.reputation, dimension)
        for dimension in policy.reputation_priority
    )
    return (-coverage, state_rank, *reputation_key, candidate.agent.agent_id)


def _reputation_dimension_key(
    snapshot: TaskForceReputationSnapshot | None,
    dimension: TaskForceReputationDimension,
) -> tuple[int, Decimal]:
    if snapshot is None:
        return (1, Decimal("0"))
    if dimension is TaskForceReputationDimension.OOS_EVIDENCE:
        return (0, -Decimal(snapshot.oos_ablation_comparison_count))
    if dimension is TaskForceReputationDimension.MARGINAL_ECONOMIC_NET:
        return _descending_optional(snapshot.marginal_economic_net_eur)
    if dimension is TaskForceReputationDimension.DRAWDOWN_REDUCTION:
        return _descending_optional(snapshot.drawdown_reduction_pct)
    if dimension is TaskForceReputationDimension.AVERAGE_COST:
        return _ascending_optional(snapshot.average_cost_eur)
    return _ascending_optional(snapshot.average_latency_ms)


def _descending_optional(value: Decimal | None) -> tuple[int, Decimal]:
    if value is None:
        return (1, Decimal("0"))
    return (0, -value)


def _ascending_optional(value: Decimal | None) -> tuple[int, Decimal]:
    if value is None:
        return (1, Decimal("0"))
    return (0, value)


def _assignment(
    candidate: _Candidate,
    policy: TaskForceCompositionPolicy,
) -> TaskForceMemberAssignment:
    reasons = ["REGISTRY_ELIGIBLE", f"STATE:{candidate.agent.state.value}"]
    if candidate.reputation is not None:
        reasons.append("BATCH18_REPUTATION_EVIDENCE_ATTACHED")
    return TaskForceMemberAssignment(
        member_id=f"member:{candidate.agent.agent_id}",
        agent=candidate.agent,
        task_role=candidate.agent.role.value,
        capabilities=candidate.capabilities or (candidate.agent.role.value,),
        selection_reasons=tuple(reasons),
        reputation_evidence_refs=(
            ()
            if candidate.reputation is None
            else (candidate.reputation.advisory_fingerprint_sha256,)
        ),
        tool_allowlist=(),
        member_budget_eur=policy.member_budget_eur,
        max_calls=policy.member_max_calls,
    )


def _composition_fingerprint(**payload: Any) -> str:
    serializable = {
        "request": payload["request"].model_dump(mode="json"),
        "operator_policy": payload["operator_policy"].model_dump(mode="json"),
        "composition_policy": payload["composition_policy"].model_dump(mode="json"),
        "members": [item.model_dump(mode="json") for item in payload["members"]],
        "exclusions": [item.model_dump(mode="json") for item in payload["exclusions"]],
        "uncovered_roles": payload["uncovered_roles"],
        "uncovered_capabilities": payload["uncovered_capabilities"],
        "red_team_covered": payload["red_team_covered"],
        "aggregate_reputation_score": None,
    }
    canonical = json.dumps(
        serializable,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
