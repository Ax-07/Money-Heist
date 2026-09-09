from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .lifecycle import RecruitmentLifecycleRecord
from .models import RecruitmentCandidateSpec, RecruitmentCandidateState

ZERO = Decimal("0")


class RecruitmentGateStatus(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


class RecruitmentCapacityPolicy(BaseModel):
    """Operator-owned recruitment capacity limits.

    No production value is inferred here. Every material threshold must be supplied
    explicitly by configuration/operator policy before the gate is evaluated.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str = Field(min_length=1, max_length=200)
    max_active_specialists: int = Field(ge=0)
    max_shadow_candidates: int = Field(ge=0)
    max_recruitments_per_period: int = Field(ge=0)
    max_compute_per_candidate_eur: Decimal = Field(ge=0, allow_inf_nan=False)

    @field_validator("policy_id")
    @classmethod
    def _strip_policy_id(cls, value: str) -> str:
        return value.strip()


class RecruitmentCapacitySnapshot(BaseModel):
    """Read-only population/frequency snapshot for one explicit policy period."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    period_id: str = Field(min_length=1, max_length=200)
    active_specialists: int = Field(ge=0)
    shadow_candidates: int = Field(ge=0)
    recruitments_started: int = Field(ge=0)

    @field_validator("period_id")
    @classmethod
    def _strip_period_id(cls, value: str) -> str:
        return value.strip()


class RecruitmentGateDecision(BaseModel):
    """Deterministic, audit-only gate result. It never changes lifecycle state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gate_version: Literal["batch19.recruitment-capacity-gate.v1"] = (
        "batch19.recruitment-capacity-gate.v1"
    )
    recruitment_id: str = Field(min_length=1, max_length=200)
    policy_id: str = Field(min_length=1, max_length=200)
    period_id: str = Field(min_length=1, max_length=200)
    status: RecruitmentGateStatus
    reason_codes: tuple[str, ...] = Field(min_length=1)
    audit_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    auto_apply: Literal[False] = False
    registry_mutation: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("recruitment_id", "policy_id", "period_id")
    @classmethod
    def _strip_ids(cls, value: str) -> str:
        return value.strip()

    @field_validator("reason_codes")
    @classmethod
    def _canonical_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("reason_codes must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("reason_codes must not contain duplicates")
        return tuple(sorted(normalized))


class RecruitmentComputeRequest(BaseModel):
    """One prospective compute charge. This object cannot spend money by itself."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    recruitment_id: str = Field(min_length=1, max_length=200)
    spent_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    requested_eur: Decimal = Field(gt=0, allow_inf_nan=False)

    @field_validator("recruitment_id")
    @classmethod
    def _strip_recruitment_id(cls, value: str) -> str:
        return value.strip()


class RecruitmentComputeDecision(BaseModel):
    """Fail-closed candidate compute-budget decision; does not execute a provider call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gate_version: Literal["batch19.recruitment-compute-gate.v1"] = (
        "batch19.recruitment-compute-gate.v1"
    )
    recruitment_id: str = Field(min_length=1, max_length=200)
    policy_id: str = Field(min_length=1, max_length=200)
    status: RecruitmentGateStatus
    reason_codes: tuple[str, ...] = Field(min_length=1)
    effective_budget_limit_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    spent_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    requested_eur: Decimal = Field(gt=0, allow_inf_nan=False)
    projected_spend_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    audit_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    execute_compute: Literal[False] = False
    auto_apply: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("recruitment_id", "policy_id")
    @classmethod
    def _strip_ids(cls, value: str) -> str:
        return value.strip()

    @field_validator("reason_codes")
    @classmethod
    def _canonical_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("reason_codes must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("reason_codes must not contain duplicates")
        return tuple(sorted(normalized))

    @model_validator(mode="after")
    def _coherent_projected_spend(self) -> RecruitmentComputeDecision:
        if self.projected_spend_eur != self.spent_eur + self.requested_eur:
            raise ValueError("projected_spend_eur must equal spent_eur + requested_eur")
        return self


def evaluate_shadow_admission(
    candidate: RecruitmentCandidateSpec,
    lifecycle: RecruitmentLifecycleRecord,
    *,
    policy: RecruitmentCapacityPolicy,
    snapshot: RecruitmentCapacitySnapshot,
) -> RecruitmentGateDecision:
    """Check whether a CANDIDATE is eligible to be *planned* for SHADOW admission.

    ALLOW is not a state transition. Step 2 operator authorization is still required
    to record ENTER_SHADOW, and this function never mutates AgentRegistry.
    """

    if candidate.recruitment_id != lifecycle.recruitment_id:
        raise ValueError("candidate and lifecycle must target the same recruitment_id")

    reasons: list[str] = []
    if lifecycle.current_state is not RecruitmentCandidateState.CANDIDATE:
        reasons.append("CANDIDATE_STATE_REQUIRED")
    if snapshot.active_specialists > policy.max_active_specialists:
        reasons.append("ACTIVE_SPECIALIST_CAP_ALREADY_EXCEEDED")
    if snapshot.shadow_candidates >= policy.max_shadow_candidates:
        reasons.append("SHADOW_CANDIDATE_CAP_REACHED")
    if snapshot.recruitments_started >= policy.max_recruitments_per_period:
        reasons.append("RECRUITMENT_FREQUENCY_CAP_REACHED")
    if candidate.budget_limit_eur > policy.max_compute_per_candidate_eur:
        reasons.append("CANDIDATE_BUDGET_ABOVE_POLICY")

    if reasons:
        status = RecruitmentGateStatus.BLOCK
    else:
        status = RecruitmentGateStatus.ALLOW
        reasons.append("WITHIN_EXPLICIT_RECRUITMENT_LIMITS")

    canonical_reasons = tuple(sorted(reasons))
    fingerprint = _capacity_fingerprint(
        candidate=candidate,
        lifecycle=lifecycle,
        policy=policy,
        snapshot=snapshot,
        status=status,
        reason_codes=canonical_reasons,
    )
    return RecruitmentGateDecision(
        recruitment_id=candidate.recruitment_id,
        policy_id=policy.policy_id,
        period_id=snapshot.period_id,
        status=status,
        reason_codes=canonical_reasons,
        audit_fingerprint_sha256=fingerprint,
    )


def evaluate_candidate_compute(
    candidate: RecruitmentCandidateSpec,
    request: RecruitmentComputeRequest,
    *,
    policy: RecruitmentCapacityPolicy,
) -> RecruitmentComputeDecision:
    """Check a prospective candidate compute charge against both explicit caps.

    The effective limit is the stricter of the candidate's pre-registered budget and
    the operator-owned population policy. This function authorizes no provider call.
    """

    if request.recruitment_id != candidate.recruitment_id:
        raise ValueError("compute request targets a different recruitment_id")

    effective_limit = min(candidate.budget_limit_eur, policy.max_compute_per_candidate_eur)
    projected = request.spent_eur + request.requested_eur
    reasons: list[str] = []

    if candidate.budget_limit_eur > policy.max_compute_per_candidate_eur:
        reasons.append("CANDIDATE_BUDGET_ABOVE_POLICY")
    if request.spent_eur > effective_limit:
        reasons.append("CANDIDATE_BUDGET_ALREADY_EXCEEDED")
    if projected > effective_limit:
        reasons.append("CANDIDATE_COMPUTE_BUDGET_EXCEEDED")

    if reasons:
        status = RecruitmentGateStatus.BLOCK
    else:
        status = RecruitmentGateStatus.ALLOW
        reasons.append("WITHIN_EXPLICIT_CANDIDATE_COMPUTE_BUDGET")

    canonical_reasons = tuple(sorted(reasons))
    fingerprint = _compute_fingerprint(
        candidate=candidate,
        request=request,
        policy=policy,
        effective_limit=effective_limit,
        projected=projected,
        status=status,
        reason_codes=canonical_reasons,
    )
    return RecruitmentComputeDecision(
        recruitment_id=candidate.recruitment_id,
        policy_id=policy.policy_id,
        status=status,
        reason_codes=canonical_reasons,
        effective_budget_limit_eur=effective_limit,
        spent_eur=request.spent_eur,
        requested_eur=request.requested_eur,
        projected_spend_eur=projected,
        audit_fingerprint_sha256=fingerprint,
    )


def _capacity_fingerprint(
    *,
    candidate: RecruitmentCandidateSpec,
    lifecycle: RecruitmentLifecycleRecord,
    policy: RecruitmentCapacityPolicy,
    snapshot: RecruitmentCapacitySnapshot,
    status: RecruitmentGateStatus,
    reason_codes: tuple[str, ...],
) -> str:
    payload = {
        "gate_version": "batch19.recruitment-capacity-gate.v1",
        "recruitment_id": candidate.recruitment_id,
        "candidate_budget_limit_eur": str(candidate.budget_limit_eur),
        "lifecycle_state": lifecycle.current_state.value,
        "lifecycle_revision": lifecycle.revision,
        "policy": {
            "policy_id": policy.policy_id,
            "max_active_specialists": policy.max_active_specialists,
            "max_shadow_candidates": policy.max_shadow_candidates,
            "max_recruitments_per_period": policy.max_recruitments_per_period,
            "max_compute_per_candidate_eur": str(policy.max_compute_per_candidate_eur),
        },
        "snapshot": {
            "period_id": snapshot.period_id,
            "active_specialists": snapshot.active_specialists,
            "shadow_candidates": snapshot.shadow_candidates,
            "recruitments_started": snapshot.recruitments_started,
        },
        "status": status.value,
        "reason_codes": reason_codes,
        "auto_apply": False,
        "registry_mutation": False,
        "live_authority": False,
    }
    return _sha256(payload)


def _compute_fingerprint(
    *,
    candidate: RecruitmentCandidateSpec,
    request: RecruitmentComputeRequest,
    policy: RecruitmentCapacityPolicy,
    effective_limit: Decimal,
    projected: Decimal,
    status: RecruitmentGateStatus,
    reason_codes: tuple[str, ...],
) -> str:
    payload = {
        "gate_version": "batch19.recruitment-compute-gate.v1",
        "recruitment_id": candidate.recruitment_id,
        "candidate_budget_limit_eur": str(candidate.budget_limit_eur),
        "policy_id": policy.policy_id,
        "policy_max_compute_per_candidate_eur": str(policy.max_compute_per_candidate_eur),
        "effective_budget_limit_eur": str(effective_limit),
        "spent_eur": str(request.spent_eur),
        "requested_eur": str(request.requested_eur),
        "projected_spend_eur": str(projected),
        "status": status.value,
        "reason_codes": reason_codes,
        "execute_compute": False,
        "auto_apply": False,
        "live_authority": False,
    }
    return _sha256(payload)


def _sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
