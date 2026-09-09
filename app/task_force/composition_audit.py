from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.registry import AgentRegistry

from .composition import (
    TaskForceCapabilityProfile,
    TaskForceCompositionPolicy,
    TaskForceCompositionResult,
    TaskForceReputationSnapshot,
    compose_task_force_members,
)
from .models import (
    TaskForceOperatorPolicy,
    TaskForceRequest,
    task_force_policy_fingerprint,
    task_force_request_fingerprint,
)

if TYPE_CHECKING:
    from app.evaluation.reputation_advisory import AgentReputationAdvisoryReport


class TaskForceCompositionAuditStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"


class TaskForceCompositionProvenance(BaseModel):
    """Content-addressed provenance for one deterministic composition result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance_version: Literal["batch20.task-force-composition-provenance.v1"] = (
        "batch20.task-force-composition-provenance.v1"
    )
    request_id: str = Field(min_length=1, max_length=200)
    composition_policy_id: str = Field(min_length=1, max_length=200)
    request_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    operator_policy_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    composition_policy_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    registry_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    capability_profiles_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    reputation_evidence_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    result_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    source_bundle_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    registry_agent_ids: tuple[str, ...]
    reputation_advisory_fingerprints: tuple[str, ...]
    aggregate_reputation_score: Literal[None] = None
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("request_id", "composition_policy_id")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "request_fingerprint_sha256",
        "operator_policy_fingerprint_sha256",
        "composition_policy_fingerprint_sha256",
        "registry_fingerprint_sha256",
        "capability_profiles_fingerprint_sha256",
        "reputation_evidence_fingerprint_sha256",
        "result_fingerprint_sha256",
        "source_bundle_fingerprint_sha256",
    )
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        return _sha256_hex(value)

    @field_validator("registry_agent_ids", "reputation_advisory_fingerprints")
    @classmethod
    def _canonical_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() for value in values):
            raise ValueError("provenance tuples must not contain blanks")
        if len(set(values)) != len(values):
            raise ValueError("provenance tuples must not contain duplicates")
        return tuple(sorted(values))


class TaskForceCompositionAudit(BaseModel):
    """Fail-closed freshness audit; it never authorizes or executes a Task Force."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_version: Literal["batch20.task-force-composition-audit.v1"] = (
        "batch20.task-force-composition-audit.v1"
    )
    status: TaskForceCompositionAuditStatus
    stale: bool
    reason_codes: tuple[str, ...]
    original_source_bundle_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    current_source_bundle_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    original_result_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    recomposed_result_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    original_member_agent_ids: tuple[str, ...]
    recomposed_member_agent_ids: tuple[str, ...]
    execution_authorized: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator(
        "original_source_bundle_fingerprint_sha256",
        "current_source_bundle_fingerprint_sha256",
        "original_result_fingerprint_sha256",
        "recomposed_result_fingerprint_sha256",
    )
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        return _sha256_hex(value)

    @field_validator("reason_codes")
    @classmethod
    def _normalize_reasons(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("reason_codes must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("reason_codes must not contain duplicates")
        return tuple(sorted(normalized))


def task_force_composition_policy_fingerprint(policy: TaskForceCompositionPolicy) -> str:
    payload = policy.model_dump(mode="json")
    payload["state_preference"] = [state.value for state in policy.state_preference]
    payload["reputation_priority"] = [item.value for item in policy.reputation_priority]
    return _canonical_sha256(payload)


def task_force_registry_fingerprint(registry: AgentRegistry) -> str:
    entries = sorted(registry.list(), key=lambda item: item.agent_id)
    payload = [entry.model_dump(mode="json") for entry in entries]
    return _canonical_sha256({"registry_entries": payload})


def task_force_capability_profiles_fingerprint(
    profiles: tuple[TaskForceCapabilityProfile, ...],
) -> str:
    payload = [
        profile.model_dump(mode="json")
        for profile in sorted(profiles, key=lambda item: item.agent_id)
    ]
    return _canonical_sha256({"capability_profiles": payload})


def task_force_reputation_evidence_fingerprint(
    reports: tuple[AgentReputationAdvisoryReport, ...],
) -> str:
    snapshots = _reputation_snapshots(reports)
    payload = [snapshot.model_dump(mode="json") for snapshot in snapshots]
    return _canonical_sha256({"reputation_snapshots": payload})


def capture_task_force_composition_provenance(
    result: TaskForceCompositionResult,
    request: TaskForceRequest,
    operator_policy: TaskForceOperatorPolicy,
    composition_policy: TaskForceCompositionPolicy,
    *,
    registry: AgentRegistry,
    capability_profiles: tuple[TaskForceCapabilityProfile, ...] = (),
    reputation_reports: tuple[AgentReputationAdvisoryReport, ...] = (),
) -> TaskForceCompositionProvenance:
    """Bind a composition result to every material source used to reproduce it."""

    if result.request_id != request.request_id:
        raise ValueError("composition result request_id does not match request")
    if result.composition_policy_id != composition_policy.composition_policy_id:
        raise ValueError("composition result policy id does not match composition policy")

    recomposed = compose_task_force_members(
        request,
        operator_policy,
        composition_policy,
        registry=registry,
        capability_profiles=capability_profiles,
        reputation_reports=reputation_reports,
    )
    if recomposed.composition_fingerprint_sha256 != result.composition_fingerprint_sha256:
        raise ValueError("composition result cannot be reproduced from supplied sources")

    components = _source_components(
        request,
        operator_policy,
        composition_policy,
        registry=registry,
        capability_profiles=capability_profiles,
        reputation_reports=reputation_reports,
    )
    return TaskForceCompositionProvenance(
        request_id=request.request_id,
        composition_policy_id=composition_policy.composition_policy_id,
        result_fingerprint_sha256=result.composition_fingerprint_sha256,
        registry_agent_ids=tuple(entry.agent_id for entry in registry.list()),
        reputation_advisory_fingerprints=tuple(
            snapshot.advisory_fingerprint_sha256
            for snapshot in _reputation_snapshots(reputation_reports)
        ),
        **components,
        source_bundle_fingerprint_sha256=_source_bundle_fingerprint(components),
    )


def audit_task_force_composition(
    provenance: TaskForceCompositionProvenance,
    original_result: TaskForceCompositionResult,
    request: TaskForceRequest,
    operator_policy: TaskForceOperatorPolicy,
    composition_policy: TaskForceCompositionPolicy,
    *,
    registry: AgentRegistry,
    capability_profiles: tuple[TaskForceCapabilityProfile, ...] = (),
    reputation_reports: tuple[AgentReputationAdvisoryReport, ...] = (),
) -> TaskForceCompositionAudit:
    """Recompose from current sources and mark the original result stale if anything moved."""

    if provenance.result_fingerprint_sha256 != original_result.composition_fingerprint_sha256:
        raise ValueError("original composition result does not match captured provenance")
    if provenance.request_id != original_result.request_id:
        raise ValueError("original composition request_id does not match provenance")
    if provenance.composition_policy_id != original_result.composition_policy_id:
        raise ValueError("original composition policy id does not match provenance")

    current = _source_components(
        request,
        operator_policy,
        composition_policy,
        registry=registry,
        capability_profiles=capability_profiles,
        reputation_reports=reputation_reports,
    )
    current_bundle = _source_bundle_fingerprint(current)
    recomposed = compose_task_force_members(
        request,
        operator_policy,
        composition_policy,
        registry=registry,
        capability_profiles=capability_profiles,
        reputation_reports=reputation_reports,
    )

    reasons: list[str] = []
    comparisons = (
        (
            "REQUEST_CHANGED",
            provenance.request_fingerprint_sha256,
            current["request_fingerprint_sha256"],
        ),
        (
            "OPERATOR_POLICY_CHANGED",
            provenance.operator_policy_fingerprint_sha256,
            current["operator_policy_fingerprint_sha256"],
        ),
        (
            "COMPOSITION_POLICY_CHANGED",
            provenance.composition_policy_fingerprint_sha256,
            current["composition_policy_fingerprint_sha256"],
        ),
        (
            "REGISTRY_CHANGED",
            provenance.registry_fingerprint_sha256,
            current["registry_fingerprint_sha256"],
        ),
        (
            "CAPABILITY_PROFILES_CHANGED",
            provenance.capability_profiles_fingerprint_sha256,
            current["capability_profiles_fingerprint_sha256"],
        ),
        (
            "REPUTATION_EVIDENCE_CHANGED",
            provenance.reputation_evidence_fingerprint_sha256,
            current["reputation_evidence_fingerprint_sha256"],
        ),
    )
    for reason, before, after in comparisons:
        if before != after:
            reasons.append(reason)
    if (
        provenance.result_fingerprint_sha256
        != recomposed.composition_fingerprint_sha256
    ):
        reasons.append("RECOMPOSED_RESULT_CHANGED")

    status = (
        TaskForceCompositionAuditStatus.STALE
        if reasons
        else TaskForceCompositionAuditStatus.FRESH
    )
    return TaskForceCompositionAudit(
        status=status,
        stale=bool(reasons),
        reason_codes=tuple(reasons),
        original_source_bundle_fingerprint_sha256=(
            provenance.source_bundle_fingerprint_sha256
        ),
        current_source_bundle_fingerprint_sha256=current_bundle,
        original_result_fingerprint_sha256=provenance.result_fingerprint_sha256,
        recomposed_result_fingerprint_sha256=recomposed.composition_fingerprint_sha256,
        original_member_agent_ids=tuple(
            member.agent.agent_id for member in original_result.members
        ),
        recomposed_member_agent_ids=tuple(
            member.agent.agent_id for member in recomposed.members
        ),
    )


def _source_components(
    request: TaskForceRequest,
    operator_policy: TaskForceOperatorPolicy,
    composition_policy: TaskForceCompositionPolicy,
    *,
    registry: AgentRegistry,
    capability_profiles: tuple[TaskForceCapabilityProfile, ...],
    reputation_reports: tuple[AgentReputationAdvisoryReport, ...],
) -> dict[str, str]:
    return {
        "request_fingerprint_sha256": task_force_request_fingerprint(request),
        "operator_policy_fingerprint_sha256": task_force_policy_fingerprint(
            operator_policy
        ),
        "composition_policy_fingerprint_sha256": (
            task_force_composition_policy_fingerprint(composition_policy)
        ),
        "registry_fingerprint_sha256": task_force_registry_fingerprint(registry),
        "capability_profiles_fingerprint_sha256": (
            task_force_capability_profiles_fingerprint(capability_profiles)
        ),
        "reputation_evidence_fingerprint_sha256": (
            task_force_reputation_evidence_fingerprint(reputation_reports)
        ),
    }


def _source_bundle_fingerprint(components: dict[str, str]) -> str:
    return _canonical_sha256({"source_components": components})


def _reputation_snapshots(
    reports: tuple[AgentReputationAdvisoryReport, ...],
) -> tuple[TaskForceReputationSnapshot, ...]:
    by_agent: dict[str, TaskForceReputationSnapshot] = {}
    for report in reports:
        snapshot = TaskForceReputationSnapshot.from_advisory(report)
        if snapshot.agent_id in by_agent:
            raise ValueError(f"duplicate reputation report: {snapshot.agent_id}")
        by_agent[snapshot.agent_id] = snapshot
    return tuple(by_agent[agent_id] for agent_id in sorted(by_agent))


def _canonical_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sha256_hex(value: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise ValueError("value must be lowercase SHA-256 hex")
    return normalized
