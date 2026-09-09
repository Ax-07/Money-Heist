from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import RecruitmentCandidateSpec, RecruitmentCandidateState


class RecruitmentLifecycleAction(StrEnum):
    """Operator-gated actions for the recruitment-only lifecycle."""

    ENTER_SHADOW = "ENTER_SHADOW"
    EXTEND_SHADOW = "EXTEND_SHADOW"
    ENTER_PROBATION = "ENTER_PROBATION"
    EXTEND_PROBATION = "EXTEND_PROBATION"
    RETURN_TO_SHADOW = "RETURN_TO_SHADOW"
    REJECT = "REJECT"
    REOPEN_CANDIDATE = "REOPEN_CANDIDATE"
    RECOMMEND_PROMOTION = "RECOMMEND_PROMOTION"
    WITHDRAW_PROMOTION_RECOMMENDATION = "WITHDRAW_PROMOTION_RECOMMENDATION"


_ALLOWED_TRANSITIONS: dict[
    RecruitmentCandidateState,
    dict[RecruitmentLifecycleAction, RecruitmentCandidateState],
] = {
    RecruitmentCandidateState.CANDIDATE: {
        RecruitmentLifecycleAction.ENTER_SHADOW: RecruitmentCandidateState.SHADOW,
        RecruitmentLifecycleAction.REJECT: RecruitmentCandidateState.REJECTED,
    },
    RecruitmentCandidateState.SHADOW: {
        RecruitmentLifecycleAction.EXTEND_SHADOW: RecruitmentCandidateState.SHADOW,
        RecruitmentLifecycleAction.ENTER_PROBATION: RecruitmentCandidateState.PROBATION,
        RecruitmentLifecycleAction.REJECT: RecruitmentCandidateState.REJECTED,
    },
    RecruitmentCandidateState.PROBATION: {
        RecruitmentLifecycleAction.EXTEND_PROBATION: RecruitmentCandidateState.PROBATION,
        RecruitmentLifecycleAction.RETURN_TO_SHADOW: RecruitmentCandidateState.SHADOW,
        RecruitmentLifecycleAction.REJECT: RecruitmentCandidateState.REJECTED,
        RecruitmentLifecycleAction.RECOMMEND_PROMOTION: (
            RecruitmentCandidateState.PROMOTION_RECOMMENDED
        ),
    },
    RecruitmentCandidateState.PROMOTION_RECOMMENDED: {
        RecruitmentLifecycleAction.WITHDRAW_PROMOTION_RECOMMENDATION: (
            RecruitmentCandidateState.PROBATION
        ),
        RecruitmentLifecycleAction.RETURN_TO_SHADOW: RecruitmentCandidateState.SHADOW,
        RecruitmentLifecycleAction.REJECT: RecruitmentCandidateState.REJECTED,
    },
    RecruitmentCandidateState.REJECTED: {
        RecruitmentLifecycleAction.REOPEN_CANDIDATE: RecruitmentCandidateState.CANDIDATE,
    },
}


class RecruitmentLifecycleRecord(BaseModel):
    """Immutable recruitment state; never an AgentRegistry entry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    recruitment_id: str = Field(min_length=1, max_length=200)
    proposed_name: str = Field(min_length=1, max_length=100)
    current_state: RecruitmentCandidateState
    revision: int = Field(default=0, ge=0)
    transition_ids: tuple[str, ...] = ()
    auto_apply: Literal[False] = False
    registry_mutation: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("recruitment_id", "proposed_name")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("transition_ids")
    @classmethod
    def _validate_transition_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(len(value) != 64 for value in values):
            raise ValueError("transition_ids must contain SHA-256 hex digests")
        if len(set(values)) != len(values):
            raise ValueError("transition_ids must not contain duplicates")
        return values


class RecruitmentTransitionPlan(BaseModel):
    """Advisory transition plan. Planning never changes candidate or registry state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["batch19.recruitment-lifecycle.v1"] = (
        "batch19.recruitment-lifecycle.v1"
    )
    transition_id: str = Field(min_length=64, max_length=64)
    recruitment_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=0)
    action: RecruitmentLifecycleAction
    from_state: RecruitmentCandidateState
    to_state: RecruitmentCandidateState
    reason_codes: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    auto_apply: Literal[False] = False
    registry_mutation: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("recruitment_id")
    @classmethod
    def _strip_recruitment_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("reason_codes", "evidence_refs")
    @classmethod
    def _canonical_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("audit references must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("audit references must not contain duplicates")
        return tuple(sorted(normalized))


def start_recruitment_lifecycle(
    candidate: RecruitmentCandidateSpec,
) -> RecruitmentLifecycleRecord:
    """Create the recruitment-only state record from a frozen candidate specification."""

    return RecruitmentLifecycleRecord(
        recruitment_id=candidate.recruitment_id,
        proposed_name=candidate.proposed_name,
        current_state=RecruitmentCandidateState.CANDIDATE,
    )


def plan_recruitment_transition(
    record: RecruitmentLifecycleRecord,
    *,
    action: RecruitmentLifecycleAction,
    reason_codes: tuple[str, ...],
    evidence_refs: tuple[str, ...],
) -> RecruitmentTransitionPlan:
    """Build a deterministic transition plan without applying it."""

    transitions = _ALLOWED_TRANSITIONS.get(record.current_state, {})
    to_state = transitions.get(action)
    if to_state is None:
        raise ValueError(
            f"transition {action.value} is not allowed from {record.current_state.value}"
        )

    canonical_reasons = _canonical_values(reason_codes, name="reason_codes")
    canonical_evidence = _canonical_values(evidence_refs, name="evidence_refs")
    transition_id = _transition_fingerprint(
        recruitment_id=record.recruitment_id,
        expected_revision=record.revision,
        action=action,
        from_state=record.current_state,
        to_state=to_state,
        reason_codes=canonical_reasons,
        evidence_refs=canonical_evidence,
    )
    return RecruitmentTransitionPlan(
        transition_id=transition_id,
        recruitment_id=record.recruitment_id,
        expected_revision=record.revision,
        action=action,
        from_state=record.current_state,
        to_state=to_state,
        reason_codes=canonical_reasons,
        evidence_refs=canonical_evidence,
    )


def record_recruitment_transition(
    record: RecruitmentLifecycleRecord,
    plan: RecruitmentTransitionPlan,
    *,
    operator_authorized: bool,
) -> RecruitmentLifecycleRecord:
    """Record an explicitly authorized recruitment-state transition.

    This only advances the recruitment lifecycle record. It never mutates AgentRegistry,
    creates operational permissions, or converts PROMOTION_RECOMMENDED into a promotion.
    """

    if operator_authorized is not True:
        raise PermissionError(
            "recruitment transition requires explicit operator authorization"
        )
    if plan.recruitment_id != record.recruitment_id:
        raise ValueError("transition plan targets a different recruitment_id")
    if plan.expected_revision != record.revision:
        raise ValueError("stale recruitment transition plan revision")
    if plan.from_state is not record.current_state:
        raise ValueError("stale recruitment transition plan state")

    expected = _ALLOWED_TRANSITIONS.get(record.current_state, {}).get(plan.action)
    if expected is None or expected is not plan.to_state:
        raise ValueError("transition plan is inconsistent with lifecycle policy")
    if plan.transition_id in record.transition_ids:
        raise ValueError("transition plan has already been recorded")

    return RecruitmentLifecycleRecord(
        recruitment_id=record.recruitment_id,
        proposed_name=record.proposed_name,
        current_state=plan.to_state,
        revision=record.revision + 1,
        transition_ids=(*record.transition_ids, plan.transition_id),
    )


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
    recruitment_id: str,
    expected_revision: int,
    action: RecruitmentLifecycleAction,
    from_state: RecruitmentCandidateState,
    to_state: RecruitmentCandidateState,
    reason_codes: tuple[str, ...],
    evidence_refs: tuple[str, ...],
) -> str:
    payload = {
        "policy_version": "batch19.recruitment-lifecycle.v1",
        "recruitment_id": recruitment_id,
        "expected_revision": expected_revision,
        "action": action.value,
        "from_state": from_state.value,
        "to_state": to_state.value,
        "reason_codes": reason_codes,
        "evidence_refs": evidence_refs,
        "auto_apply": False,
        "registry_mutation": False,
        "live_authority": False,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
