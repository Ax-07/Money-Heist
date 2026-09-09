from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import TaskForcePlan, TaskForceState


class TaskForceLifecycleAction(StrEnum):
    """Explicit actions for the Task Force lifecycle."""

    APPROVE_EXECUTION = "APPROVE_EXECUTION"
    START_EXECUTION = "START_EXECUTION"
    COMPLETE = "COMPLETE"
    BLOCK = "BLOCK"
    CANCEL = "CANCEL"
    FAIL = "FAIL"


_ALLOWED_TRANSITIONS: dict[
    TaskForceState,
    dict[TaskForceLifecycleAction, TaskForceState],
] = {
    TaskForceState.PLANNED: {
        TaskForceLifecycleAction.APPROVE_EXECUTION: TaskForceState.APPROVED_FOR_EXECUTION,
        TaskForceLifecycleAction.BLOCK: TaskForceState.BLOCKED,
        TaskForceLifecycleAction.CANCEL: TaskForceState.CANCELLED,
    },
    TaskForceState.APPROVED_FOR_EXECUTION: {
        TaskForceLifecycleAction.START_EXECUTION: TaskForceState.RUNNING,
        TaskForceLifecycleAction.BLOCK: TaskForceState.BLOCKED,
        TaskForceLifecycleAction.CANCEL: TaskForceState.CANCELLED,
    },
    TaskForceState.RUNNING: {
        TaskForceLifecycleAction.COMPLETE: TaskForceState.COMPLETED,
        TaskForceLifecycleAction.CANCEL: TaskForceState.CANCELLED,
        TaskForceLifecycleAction.FAIL: TaskForceState.FAILED,
    },
}


class TaskForceLifecycleRecord(BaseModel):
    """Immutable Task Force state, separate from every member AgentState."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    task_force_id: str = Field(min_length=1, max_length=200)
    request_id: str = Field(min_length=1, max_length=200)
    request_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    policy_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    composition_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    current_state: TaskForceState
    revision: int = Field(default=0, ge=0)
    transition_ids: tuple[str, ...] = ()
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    auto_execute: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("task_force_id", "request_id")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "request_fingerprint_sha256",
        "policy_fingerprint_sha256",
        "composition_fingerprint_sha256",
    )
    @classmethod
    def _validate_fingerprint(cls, value: str) -> str:
        return _validate_sha256(value, field_name="fingerprint")

    @field_validator("transition_ids")
    @classmethod
    def _validate_transition_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(
            _validate_sha256(value, field_name="transition_id") for value in values
        )
        if len(set(normalized)) != len(normalized):
            raise ValueError("transition_ids must not contain duplicates")
        return normalized

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value, field_name="created_at")

    @field_validator("updated_at")
    @classmethod
    def _validate_updated_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value, field_name="updated_at")

    @field_validator("expires_at")
    @classmethod
    def _validate_expires_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value, field_name="expires_at")

    @model_validator(mode="after")
    def _validate_times(self) -> TaskForceLifecycleRecord:
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        return self


class TaskForceTransitionPlan(BaseModel):
    """Deterministic lifecycle transition plan; it never executes Task Force work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["batch20.task-force-lifecycle.v1"] = (
        "batch20.task-force-lifecycle.v1"
    )
    transition_id: str = Field(min_length=64, max_length=64)
    task_force_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=0)
    action: TaskForceLifecycleAction
    from_state: TaskForceState
    to_state: TaskForceState
    request_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    policy_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    composition_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    reason_codes: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    planned_at: datetime
    operator_authorization_required: bool
    auto_apply: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("transition_id")
    @classmethod
    def _validate_transition_id(cls, value: str) -> str:
        return _validate_sha256(value, field_name="transition_id")

    @field_validator("task_force_id")
    @classmethod
    def _strip_task_force_id(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "request_fingerprint_sha256",
        "policy_fingerprint_sha256",
        "composition_fingerprint_sha256",
    )
    @classmethod
    def _validate_fingerprint(cls, value: str) -> str:
        return _validate_sha256(value, field_name="fingerprint")

    @field_validator("reason_codes", "evidence_refs")
    @classmethod
    def _canonical_tuple(cls, values: tuple[str, ...], info) -> tuple[str, ...]:
        return _canonical_values(values, name=info.field_name)

    @field_validator("planned_at")
    @classmethod
    def _validate_planned_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value, field_name="planned_at")

    @model_validator(mode="after")
    def _validate_authorization_requirement(self) -> TaskForceTransitionPlan:
        expected = self.action is TaskForceLifecycleAction.APPROVE_EXECUTION
        if self.operator_authorization_required is not expected:
            raise ValueError(
                "operator_authorization_required must be true only for APPROVE_EXECUTION"
            )
        return self


def start_task_force_lifecycle(plan: TaskForcePlan) -> TaskForceLifecycleRecord:
    """Create the Task Force lifecycle from a frozen Step 1 plan."""

    return TaskForceLifecycleRecord(
        task_force_id=plan.task_force_id,
        request_id=plan.request_id,
        request_fingerprint_sha256=plan.request_fingerprint_sha256,
        policy_fingerprint_sha256=plan.policy_fingerprint_sha256,
        composition_fingerprint_sha256=plan.composition_fingerprint_sha256,
        current_state=TaskForceState.PLANNED,
        created_at=plan.created_at,
        updated_at=plan.created_at,
        expires_at=plan.expires_at,
    )


def plan_task_force_transition(
    record: TaskForceLifecycleRecord,
    *,
    action: TaskForceLifecycleAction,
    reason_codes: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    planned_at: datetime,
) -> TaskForceTransitionPlan:
    """Build a transition plan without applying lifecycle state or executing members."""

    to_state = _ALLOWED_TRANSITIONS.get(record.current_state, {}).get(action)
    if to_state is None:
        raise ValueError(
            f"transition {action.value} is not allowed from {record.current_state.value}"
        )

    planned_at = _ensure_utc(planned_at, field_name="planned_at")
    if planned_at < record.updated_at:
        raise ValueError("planned_at cannot be earlier than lifecycle updated_at")
    if action in {
        TaskForceLifecycleAction.APPROVE_EXECUTION,
        TaskForceLifecycleAction.START_EXECUTION,
    } and planned_at >= record.expires_at:
        raise ValueError("expired Task Force cannot be approved or started")

    canonical_reasons = _canonical_values(reason_codes, name="reason_codes")
    canonical_evidence = _canonical_values(evidence_refs, name="evidence_refs")
    operator_required = action is TaskForceLifecycleAction.APPROVE_EXECUTION
    transition_id = _transition_fingerprint(
        record=record,
        action=action,
        to_state=to_state,
        reason_codes=canonical_reasons,
        evidence_refs=canonical_evidence,
        planned_at=planned_at,
        operator_authorization_required=operator_required,
    )
    return TaskForceTransitionPlan(
        transition_id=transition_id,
        task_force_id=record.task_force_id,
        expected_revision=record.revision,
        action=action,
        from_state=record.current_state,
        to_state=to_state,
        request_fingerprint_sha256=record.request_fingerprint_sha256,
        policy_fingerprint_sha256=record.policy_fingerprint_sha256,
        composition_fingerprint_sha256=record.composition_fingerprint_sha256,
        reason_codes=canonical_reasons,
        evidence_refs=canonical_evidence,
        planned_at=planned_at,
        operator_authorization_required=operator_required,
    )


def record_task_force_transition(
    record: TaskForceLifecycleRecord,
    plan: TaskForceTransitionPlan,
    *,
    operator_authorized: bool = False,
) -> TaskForceLifecycleRecord:
    """Record one lifecycle transition without executing work or mutating external state."""

    if plan.operator_authorization_required and operator_authorized is not True:
        raise PermissionError("Task Force execution approval requires operator authorization")
    if plan.task_force_id != record.task_force_id:
        raise ValueError("transition plan targets a different task_force_id")
    if plan.expected_revision != record.revision:
        raise ValueError("stale Task Force transition plan revision")
    if plan.from_state is not record.current_state:
        raise ValueError("stale Task Force transition plan state")
    if (
        plan.request_fingerprint_sha256 != record.request_fingerprint_sha256
        or plan.policy_fingerprint_sha256 != record.policy_fingerprint_sha256
        or plan.composition_fingerprint_sha256 != record.composition_fingerprint_sha256
    ):
        raise ValueError("stale Task Force transition plan fingerprints")
    if plan.planned_at < record.updated_at:
        raise ValueError("stale Task Force transition plan timestamp")
    if plan.action in {
        TaskForceLifecycleAction.APPROVE_EXECUTION,
        TaskForceLifecycleAction.START_EXECUTION,
    } and plan.planned_at >= record.expires_at:
        raise ValueError("expired Task Force cannot be approved or started")

    expected = _ALLOWED_TRANSITIONS.get(record.current_state, {}).get(plan.action)
    if expected is None or expected is not plan.to_state:
        raise ValueError("transition plan is inconsistent with Task Force lifecycle policy")
    if plan.transition_id in record.transition_ids:
        raise ValueError("transition plan has already been recorded")

    return TaskForceLifecycleRecord(
        task_force_id=record.task_force_id,
        request_id=record.request_id,
        request_fingerprint_sha256=record.request_fingerprint_sha256,
        policy_fingerprint_sha256=record.policy_fingerprint_sha256,
        composition_fingerprint_sha256=record.composition_fingerprint_sha256,
        current_state=plan.to_state,
        revision=record.revision + 1,
        transition_ids=(*record.transition_ids, plan.transition_id),
        created_at=record.created_at,
        updated_at=plan.planned_at,
        expires_at=record.expires_at,
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


def _canonical_values(values: tuple[str, ...], *, name: str) -> tuple[str, ...]:
    if not values:
        raise ValueError(f"{name} must not be empty")
    normalized = tuple(value.strip() for value in values)
    if any(not value for value in normalized):
        raise ValueError(f"{name} must not contain blanks")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


def _transition_fingerprint(
    *,
    record: TaskForceLifecycleRecord,
    action: TaskForceLifecycleAction,
    to_state: TaskForceState,
    reason_codes: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    planned_at: datetime,
    operator_authorization_required: bool,
) -> str:
    payload = {
        "policy_version": "batch20.task-force-lifecycle.v1",
        "task_force_id": record.task_force_id,
        "expected_revision": record.revision,
        "action": action.value,
        "from_state": record.current_state.value,
        "to_state": to_state.value,
        "request_fingerprint_sha256": record.request_fingerprint_sha256,
        "policy_fingerprint_sha256": record.policy_fingerprint_sha256,
        "composition_fingerprint_sha256": record.composition_fingerprint_sha256,
        "reason_codes": reason_codes,
        "evidence_refs": evidence_refs,
        "planned_at": planned_at.isoformat(),
        "operator_authorization_required": operator_authorization_required,
        "auto_apply": False,
        "registry_mutation": False,
        "risk_authority": False,
        "live_authority": False,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
