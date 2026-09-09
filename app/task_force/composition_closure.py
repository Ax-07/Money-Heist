from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .composition import TaskForceCompositionResult
from .composition_audit import (
    TaskForceCompositionAudit,
    TaskForceCompositionAuditStatus,
    TaskForceCompositionProvenance,
)
from .models import (
    TaskForceOperatorPolicy,
    TaskForcePlan,
    TaskForceRequest,
    TaskForceState,
    build_task_force_plan,
    task_force_policy_fingerprint,
    task_force_request_fingerprint,
)


class TaskForceCompositionClosureManifest(BaseModel):
    """Immutable handoff manifest from composition to later execution work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_version: Literal["batch20.task-force-composition-closure.v1"] = (
        "batch20.task-force-composition-closure.v1"
    )
    task_force_id: str = Field(min_length=1, max_length=200)
    request_id: str = Field(min_length=1, max_length=200)
    operator_policy_id: str = Field(min_length=1, max_length=200)
    composition_policy_id: str = Field(min_length=1, max_length=200)
    request_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    operator_policy_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    composition_source_bundle_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    composition_result_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    plan_composition_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    plan_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    integration_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    member_agent_ids: tuple[str, ...] = Field(min_length=1)
    reputation_advisory_fingerprints: tuple[str, ...] = ()
    composition_complete: Literal[True] = True
    composition_audit_status: Literal[TaskForceCompositionAuditStatus.FRESH] = (
        TaskForceCompositionAuditStatus.FRESH
    )
    plan_state: Literal[TaskForceState.PLANNED] = TaskForceState.PLANNED
    operator_authorization_required: Literal[True] = True
    execution_authorized: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator(
        "task_force_id",
        "request_id",
        "operator_policy_id",
        "composition_policy_id",
    )
    @classmethod
    def _strip_ids(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "request_fingerprint_sha256",
        "operator_policy_fingerprint_sha256",
        "composition_source_bundle_fingerprint_sha256",
        "composition_result_fingerprint_sha256",
        "plan_composition_fingerprint_sha256",
        "plan_fingerprint_sha256",
        "integration_fingerprint_sha256",
    )
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("fingerprints must be lowercase SHA-256 hexadecimal digests")
        return normalized

    @field_validator("member_agent_ids", "reputation_advisory_fingerprints")
    @classmethod
    def _canonical_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("manifest tuples must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("manifest tuples must not contain duplicates")
        return tuple(sorted(normalized))


class TaskForceCompositionClosure(BaseModel):
    """Closed composition package. It is not approval and cannot execute anything."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: TaskForceCompositionClosureManifest
    plan: TaskForcePlan
    execution_authorized: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False


def task_force_plan_fingerprint(plan: TaskForcePlan) -> str:
    """Stable digest of the exact frozen plan handed to future lifecycle/execution code."""

    return _canonical_sha256(plan.model_dump(mode="json"))


def close_task_force_composition(
    *,
    task_force_id: str,
    request: TaskForceRequest,
    operator_policy: TaskForceOperatorPolicy,
    result: TaskForceCompositionResult,
    provenance: TaskForceCompositionProvenance,
    audit: TaskForceCompositionAudit,
    created_at: datetime,
    expires_at: datetime,
) -> TaskForceCompositionClosure:
    """Close one fresh complete composition into a PLANNED TaskForcePlan.

    This function deliberately does not evaluate the admission gate, change lifecycle state,
    authorize execution, mutate AgentRegistry, call the AI Gateway, or touch Risk/LIVE paths.
    """

    created_at = _ensure_utc(created_at, field_name="created_at")
    expires_at = _ensure_utc(expires_at, field_name="expires_at")

    _validate_composition_inputs(
        request=request,
        operator_policy=operator_policy,
        result=result,
        provenance=provenance,
        audit=audit,
    )
    if created_at < request.created_at:
        raise ValueError("composition closure cannot predate the Task Force request")
    if expires_at > request.expires_at:
        raise ValueError("composition closure expiry cannot exceed request expiry")
    if expires_at <= created_at:
        raise ValueError("expires_at must be later than created_at")

    plan = build_task_force_plan(
        task_force_id=task_force_id,
        request=request,
        policy=operator_policy,
        members=result.members,
        created_at=created_at,
        expires_at=expires_at,
    )
    plan_fingerprint = task_force_plan_fingerprint(plan)
    manifest_material = {
        "manifest_version": "batch20.task-force-composition-closure.v1",
        "task_force_id": plan.task_force_id,
        "request_id": request.request_id,
        "operator_policy_id": operator_policy.policy_id,
        "composition_policy_id": result.composition_policy_id,
        "request_fingerprint_sha256": plan.request_fingerprint_sha256,
        "operator_policy_fingerprint_sha256": plan.policy_fingerprint_sha256,
        "composition_source_bundle_fingerprint_sha256": (
            provenance.source_bundle_fingerprint_sha256
        ),
        "composition_result_fingerprint_sha256": result.composition_fingerprint_sha256,
        "plan_composition_fingerprint_sha256": plan.composition_fingerprint_sha256,
        "plan_fingerprint_sha256": plan_fingerprint,
        "member_agent_ids": sorted(member.agent.agent_id for member in plan.members),
        "reputation_advisory_fingerprints": sorted(
            provenance.reputation_advisory_fingerprints
        ),
        "composition_complete": True,
        "composition_audit_status": TaskForceCompositionAuditStatus.FRESH.value,
        "plan_state": TaskForceState.PLANNED.value,
        "operator_authorization_required": True,
        "execution_authorized": False,
        "registry_mutation": False,
        "risk_authority": False,
        "live_authority": False,
    }
    integration_fingerprint = _canonical_sha256(manifest_material)
    manifest = TaskForceCompositionClosureManifest(
        **manifest_material,
        integration_fingerprint_sha256=integration_fingerprint,
    )
    return TaskForceCompositionClosure(manifest=manifest, plan=plan)


def _validate_composition_inputs(
    *,
    request: TaskForceRequest,
    operator_policy: TaskForceOperatorPolicy,
    result: TaskForceCompositionResult,
    provenance: TaskForceCompositionProvenance,
    audit: TaskForceCompositionAudit,
) -> None:
    if result.request_id != request.request_id:
        raise ValueError("composition result request_id does not match request")
    if not result.complete:
        raise ValueError("cannot close an incomplete Task Force composition")
    if not result.members:
        raise ValueError("cannot close a composition without members")
    if audit.status is not TaskForceCompositionAuditStatus.FRESH or audit.stale:
        raise ValueError("cannot close a stale Task Force composition")
    if audit.reason_codes:
        raise ValueError("fresh composition audit must not contain stale reason codes")
    if provenance.request_id != request.request_id:
        raise ValueError("composition provenance request_id does not match request")
    if provenance.result_fingerprint_sha256 != result.composition_fingerprint_sha256:
        raise ValueError("composition provenance does not match result fingerprint")
    if provenance.request_fingerprint_sha256 != task_force_request_fingerprint(request):
        raise ValueError("composition provenance request fingerprint does not match request")
    if provenance.operator_policy_fingerprint_sha256 != task_force_policy_fingerprint(
        operator_policy
    ):
        raise ValueError("composition provenance operator policy fingerprint is stale")
    if audit.original_source_bundle_fingerprint_sha256 != (
        provenance.source_bundle_fingerprint_sha256
    ):
        raise ValueError("composition audit original source bundle does not match provenance")
    if audit.current_source_bundle_fingerprint_sha256 != (
        provenance.source_bundle_fingerprint_sha256
    ):
        raise ValueError("fresh composition audit current source bundle must match provenance")
    if audit.original_result_fingerprint_sha256 != result.composition_fingerprint_sha256:
        raise ValueError("composition audit original result does not match composition result")
    if audit.recomposed_result_fingerprint_sha256 != result.composition_fingerprint_sha256:
        raise ValueError("fresh composition audit recomposed result must match original result")
    expected_member_ids = tuple(sorted(member.agent.agent_id for member in result.members))
    if tuple(sorted(audit.original_member_agent_ids)) != expected_member_ids:
        raise ValueError("composition audit original members do not match result")
    if tuple(sorted(audit.recomposed_member_agent_ids)) != expected_member_ids:
        raise ValueError("fresh composition audit recomposed members do not match result")



def _ensure_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _canonical_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
