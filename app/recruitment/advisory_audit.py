from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .advisory import RecruitmentAdvisoryReport
from .advisory_transition import (
    RecruitmentAdvisoryTransitionPlan,
    RecruitmentAdvisoryTransitionStatus,
    plan_recruitment_advisory_transition,
)
from .campaign import candidate_runtime_agent_id
from .evidence_package import RecruitmentCandidateEvidencePackage
from .gates import RecruitmentCapacityPolicy, RecruitmentCapacitySnapshot
from .lifecycle import RecruitmentLifecycleRecord
from .models import RecruitmentCandidateSpec, RecruitmentCandidateState


class RecruitmentAdvisoryAuditFreshness(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"


def _require_sha256(value: str, *, field_name: str) -> None:
    normalized = value.lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")


def _candidate_spec_fingerprint(candidate: RecruitmentCandidateSpec) -> str:
    return stable_digest(
        {
            "schema": "money-heist.recruitment-candidate-spec.v1",
            "candidate": candidate.model_dump(mode="json"),
        }
    )


def _capacity_context_fingerprint(
    policy: RecruitmentCapacityPolicy,
    snapshot: RecruitmentCapacitySnapshot,
) -> str:
    return stable_digest(
        {
            "schema": "money-heist.recruitment-capacity-context.v1",
            "policy": policy.model_dump(mode="json"),
            "snapshot": snapshot.model_dump(mode="json"),
        }
    )


def _audit_payload(
    *,
    recruitment_id: str,
    candidate_agent_id: str,
    lifecycle_revision: int,
    lifecycle_state: RecruitmentCandidateState,
    candidate_spec_fingerprint_sha256: str,
    evidence_package_fingerprint_sha256: str,
    advisory_fingerprint_sha256: str,
    planning_fingerprint_sha256: str,
    capacity_context_fingerprint_sha256: str,
    policy_id: str,
    period_id: str,
    planning_status: RecruitmentAdvisoryTransitionStatus,
    transition_id: str | None,
) -> dict[str, object]:
    return {
        "schema": "money-heist.recruitment-advisory-audit.v1",
        "recruitment_id": recruitment_id,
        "candidate_agent_id": candidate_agent_id,
        "lifecycle_revision": lifecycle_revision,
        "lifecycle_state": lifecycle_state,
        "candidate_spec_fingerprint_sha256": candidate_spec_fingerprint_sha256,
        "evidence_package_fingerprint_sha256": evidence_package_fingerprint_sha256,
        "advisory_fingerprint_sha256": advisory_fingerprint_sha256,
        "planning_fingerprint_sha256": planning_fingerprint_sha256,
        "capacity_context_fingerprint_sha256": capacity_context_fingerprint_sha256,
        "policy_id": policy_id,
        "period_id": period_id,
        "planning_status": planning_status,
        "transition_id": transition_id,
        "operator_authorization_required": True,
        "auto_apply": False,
        "registry_mutation": False,
        "lifecycle_transition_applied": False,
        "promotion_applied": False,
        "live_authority": False,
    }


def _audit_fingerprint(**kwargs: object) -> str:
    return stable_digest(_audit_payload(**kwargs))


@dataclass(frozen=True, slots=True)
class RecruitmentAdvisoryAuditRecord:
    """Immutable lineage record for one advisory and its operator-gated transition plan."""

    recruitment_id: str
    candidate_agent_id: str
    lifecycle_revision: int
    lifecycle_state: RecruitmentCandidateState
    candidate_spec_fingerprint_sha256: str
    evidence_package_fingerprint_sha256: str
    advisory_fingerprint_sha256: str
    planning_fingerprint_sha256: str
    capacity_context_fingerprint_sha256: str
    policy_id: str
    period_id: str
    planning_status: RecruitmentAdvisoryTransitionStatus
    transition_id: str | None
    audit_fingerprint_sha256: str
    audit_version: str = "batch19.recruitment-advisory-audit.v1"
    operator_authorization_required: bool = True
    auto_apply: bool = False
    registry_mutation: bool = False
    lifecycle_transition_applied: bool = False
    promotion_applied: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        if not self.recruitment_id.strip() or not self.candidate_agent_id.strip():
            raise ValueError("recruitment_id and candidate_agent_id must not be blank")
        if not self.policy_id.strip() or not self.period_id.strip():
            raise ValueError("policy_id and period_id must not be blank")
        if self.lifecycle_revision < 0:
            raise ValueError("lifecycle_revision must be >= 0")
        for field_name in (
            "candidate_spec_fingerprint_sha256",
            "evidence_package_fingerprint_sha256",
            "advisory_fingerprint_sha256",
            "planning_fingerprint_sha256",
            "capacity_context_fingerprint_sha256",
            "audit_fingerprint_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name=field_name)
        if self.transition_id is not None:
            _require_sha256(self.transition_id, field_name="transition_id")
        if self.planning_status is RecruitmentAdvisoryTransitionStatus.READY:
            if self.transition_id is None:
                raise ValueError("READY advisory audit requires a transition_id")
        elif self.transition_id is not None:
            raise ValueError("BLOCKED advisory audit cannot carry a transition_id")
        if not self.operator_authorization_required:
            raise ValueError("operator authorization must remain required")
        if (
            self.auto_apply
            or self.registry_mutation
            or self.lifecycle_transition_applied
            or self.promotion_applied
            or self.live_authority
        ):
            raise ValueError("advisory audit cannot apply operational changes")
        expected = _audit_fingerprint(
            recruitment_id=self.recruitment_id,
            candidate_agent_id=self.candidate_agent_id,
            lifecycle_revision=self.lifecycle_revision,
            lifecycle_state=self.lifecycle_state,
            candidate_spec_fingerprint_sha256=self.candidate_spec_fingerprint_sha256,
            evidence_package_fingerprint_sha256=self.evidence_package_fingerprint_sha256,
            advisory_fingerprint_sha256=self.advisory_fingerprint_sha256,
            planning_fingerprint_sha256=self.planning_fingerprint_sha256,
            capacity_context_fingerprint_sha256=self.capacity_context_fingerprint_sha256,
            policy_id=self.policy_id,
            period_id=self.period_id,
            planning_status=self.planning_status,
            transition_id=self.transition_id,
        )
        if expected != self.audit_fingerprint_sha256:
            raise ValueError("recruitment advisory audit fingerprint does not match payload")


@dataclass(frozen=True, slots=True)
class RecruitmentAdvisoryAuditValidation:
    """Read-only freshness result; never authorizes or records a transition."""

    recruitment_id: str
    freshness: RecruitmentAdvisoryAuditFreshness
    reason_codes: tuple[str, ...]
    audit_fingerprint_sha256: str
    current_capacity_context_fingerprint_sha256: str
    current_planning_fingerprint_sha256: str
    operator_authorization_required: bool = True
    record_transition: bool = False
    auto_apply: bool = False
    registry_mutation: bool = False
    promotion_applied: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        if not self.recruitment_id.strip():
            raise ValueError("recruitment_id must not be blank")
        if not self.reason_codes:
            raise ValueError("reason_codes must not be empty")
        reasons = tuple(sorted(code.strip() for code in self.reason_codes))
        if any(not code for code in reasons):
            raise ValueError("reason_codes must not contain blanks")
        if len(set(reasons)) != len(reasons):
            raise ValueError("reason_codes must not contain duplicates")
        object.__setattr__(self, "reason_codes", reasons)
        for field_name in (
            "audit_fingerprint_sha256",
            "current_capacity_context_fingerprint_sha256",
            "current_planning_fingerprint_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name=field_name)
        if not self.operator_authorization_required:
            raise ValueError("operator authorization must remain required")
        if (
            self.record_transition
            or self.auto_apply
            or self.registry_mutation
            or self.promotion_applied
            or self.live_authority
        ):
            raise ValueError("audit validation cannot apply operational changes")


def _assert_current_chain(
    candidate: RecruitmentCandidateSpec,
    package: RecruitmentCandidateEvidencePackage,
    lifecycle: RecruitmentLifecycleRecord,
    advisory: RecruitmentAdvisoryReport,
    planning: RecruitmentAdvisoryTransitionPlan,
) -> None:
    ids = {
        candidate.recruitment_id,
        package.recruitment_id,
        lifecycle.recruitment_id,
        advisory.recruitment_id,
        planning.recruitment_id,
    }
    if len(ids) != 1:
        raise ValueError("candidate, evidence, lifecycle, advisory and planning must target one recruitment_id")
    agent_id = candidate_runtime_agent_id(candidate)
    if package.candidate_agent_id != agent_id:
        raise ValueError("candidate runtime identity does not match evidence package")
    if advisory.candidate_agent_id != agent_id or planning.candidate_agent_id != agent_id:
        raise ValueError("candidate runtime identity does not match advisory lineage")
    if advisory.evidence_package_fingerprint_sha256 != package.audit_fingerprint_sha256:
        raise ValueError("advisory does not reference supplied evidence package")
    if planning.evidence_package_fingerprint_sha256 != package.audit_fingerprint_sha256:
        raise ValueError("planning does not reference supplied evidence package")
    if planning.advisory_fingerprint_sha256 != advisory.audit_fingerprint_sha256:
        raise ValueError("planning does not reference supplied advisory")
    if advisory.lifecycle_revision != lifecycle.revision or planning.lifecycle_revision != lifecycle.revision:
        raise ValueError("stale lifecycle revision in advisory lineage")
    if advisory.current_state is not lifecycle.current_state or planning.current_state is not lifecycle.current_state:
        raise ValueError("stale lifecycle state in advisory lineage")


def build_recruitment_advisory_audit(
    candidate: RecruitmentCandidateSpec,
    package: RecruitmentCandidateEvidencePackage,
    lifecycle: RecruitmentLifecycleRecord,
    advisory: RecruitmentAdvisoryReport,
    planning: RecruitmentAdvisoryTransitionPlan,
    *,
    policy: RecruitmentCapacityPolicy,
    snapshot: RecruitmentCapacitySnapshot,
) -> RecruitmentAdvisoryAuditRecord:
    """Freeze the complete advisory lineage after reproducing the transition planner output."""

    _assert_current_chain(candidate, package, lifecycle, advisory, planning)
    reproduced = plan_recruitment_advisory_transition(
        candidate,
        package,
        lifecycle,
        advisory,
        policy=policy,
        snapshot=snapshot,
    )
    if reproduced != planning:
        raise ValueError("supplied advisory transition plan is not reproducible from current context")

    candidate_fingerprint = _candidate_spec_fingerprint(candidate)
    if candidate_fingerprint != package.lineage.candidate_spec_fingerprint_sha256:
        raise ValueError("candidate spec changed after evidence packaging")
    capacity_fingerprint = _capacity_context_fingerprint(policy, snapshot)
    if capacity_fingerprint != planning.capacity_context_fingerprint_sha256:
        raise ValueError("planning capacity context does not match supplied policy and snapshot")

    transition_id = (
        planning.transition_plan.transition_id
        if planning.transition_plan is not None
        else None
    )
    fingerprint = _audit_fingerprint(
        recruitment_id=candidate.recruitment_id,
        candidate_agent_id=planning.candidate_agent_id,
        lifecycle_revision=lifecycle.revision,
        lifecycle_state=lifecycle.current_state,
        candidate_spec_fingerprint_sha256=candidate_fingerprint,
        evidence_package_fingerprint_sha256=package.audit_fingerprint_sha256,
        advisory_fingerprint_sha256=advisory.audit_fingerprint_sha256,
        planning_fingerprint_sha256=planning.audit_fingerprint_sha256,
        capacity_context_fingerprint_sha256=capacity_fingerprint,
        policy_id=policy.policy_id,
        period_id=snapshot.period_id,
        planning_status=planning.status,
        transition_id=transition_id,
    )
    return RecruitmentAdvisoryAuditRecord(
        recruitment_id=candidate.recruitment_id,
        candidate_agent_id=planning.candidate_agent_id,
        lifecycle_revision=lifecycle.revision,
        lifecycle_state=lifecycle.current_state,
        candidate_spec_fingerprint_sha256=candidate_fingerprint,
        evidence_package_fingerprint_sha256=package.audit_fingerprint_sha256,
        advisory_fingerprint_sha256=advisory.audit_fingerprint_sha256,
        planning_fingerprint_sha256=planning.audit_fingerprint_sha256,
        capacity_context_fingerprint_sha256=capacity_fingerprint,
        policy_id=policy.policy_id,
        period_id=snapshot.period_id,
        planning_status=planning.status,
        transition_id=transition_id,
        audit_fingerprint_sha256=fingerprint,
    )


def revalidate_recruitment_advisory_audit(
    audit: RecruitmentAdvisoryAuditRecord,
    candidate: RecruitmentCandidateSpec,
    package: RecruitmentCandidateEvidencePackage,
    lifecycle: RecruitmentLifecycleRecord,
    advisory: RecruitmentAdvisoryReport,
    planning: RecruitmentAdvisoryTransitionPlan,
    *,
    policy: RecruitmentCapacityPolicy,
    snapshot: RecruitmentCapacitySnapshot,
) -> RecruitmentAdvisoryAuditValidation:
    """Compare an audit against the exact current context and mark stale on any drift."""

    reasons: set[str] = set()
    current_candidate_fp = _candidate_spec_fingerprint(candidate)
    current_capacity_fp = _capacity_context_fingerprint(policy, snapshot)
    current_planning_fp = planning.audit_fingerprint_sha256

    if candidate.recruitment_id != audit.recruitment_id:
        reasons.add("RECRUITMENT_ID_CHANGED")
    if candidate_runtime_agent_id(candidate) != audit.candidate_agent_id:
        reasons.add("CANDIDATE_RUNTIME_ID_CHANGED")
    if current_candidate_fp != audit.candidate_spec_fingerprint_sha256:
        reasons.add("CANDIDATE_SPEC_CHANGED")
    if package.audit_fingerprint_sha256 != audit.evidence_package_fingerprint_sha256:
        reasons.add("EVIDENCE_PACKAGE_CHANGED")
    if advisory.audit_fingerprint_sha256 != audit.advisory_fingerprint_sha256:
        reasons.add("ADVISORY_CHANGED")
    if planning.audit_fingerprint_sha256 != audit.planning_fingerprint_sha256:
        reasons.add("TRANSITION_PLANNING_CHANGED")
    if lifecycle.revision != audit.lifecycle_revision:
        reasons.add("LIFECYCLE_REVISION_CHANGED")
    if lifecycle.current_state is not audit.lifecycle_state:
        reasons.add("LIFECYCLE_STATE_CHANGED")
    if policy.policy_id != audit.policy_id:
        reasons.add("CAPACITY_POLICY_ID_CHANGED")
    if snapshot.period_id != audit.period_id:
        reasons.add("CAPACITY_PERIOD_CHANGED")
    if current_capacity_fp != audit.capacity_context_fingerprint_sha256:
        reasons.add("CAPACITY_CONTEXT_CHANGED")
    if planning.capacity_context_fingerprint_sha256 != audit.capacity_context_fingerprint_sha256:
        reasons.add("PLANNING_CAPACITY_CONTEXT_CHANGED")
    if planning.status is not audit.planning_status:
        reasons.add("PLANNING_STATUS_CHANGED")
    current_transition_id = (
        planning.transition_plan.transition_id
        if planning.transition_plan is not None
        else None
    )
    if current_transition_id != audit.transition_id:
        reasons.add("TRANSITION_ID_CHANGED")

    if reasons:
        freshness = RecruitmentAdvisoryAuditFreshness.STALE
    else:
        freshness = RecruitmentAdvisoryAuditFreshness.FRESH
        reasons.add("AUDIT_CONTEXT_FRESH")

    return RecruitmentAdvisoryAuditValidation(
        recruitment_id=audit.recruitment_id,
        freshness=freshness,
        reason_codes=tuple(sorted(reasons)),
        audit_fingerprint_sha256=audit.audit_fingerprint_sha256,
        current_capacity_context_fingerprint_sha256=current_capacity_fp,
        current_planning_fingerprint_sha256=current_planning_fp,
    )


def require_fresh_recruitment_advisory_audit(
    audit: RecruitmentAdvisoryAuditRecord,
    candidate: RecruitmentCandidateSpec,
    package: RecruitmentCandidateEvidencePackage,
    lifecycle: RecruitmentLifecycleRecord,
    advisory: RecruitmentAdvisoryReport,
    planning: RecruitmentAdvisoryTransitionPlan,
    *,
    policy: RecruitmentCapacityPolicy,
    snapshot: RecruitmentCapacitySnapshot,
) -> RecruitmentAdvisoryAuditValidation:
    """Fail closed if an operator-facing advisory plan no longer matches its audited context."""

    validation = revalidate_recruitment_advisory_audit(
        audit,
        candidate,
        package,
        lifecycle,
        advisory,
        planning,
        policy=policy,
        snapshot=snapshot,
    )
    if validation.freshness is RecruitmentAdvisoryAuditFreshness.STALE:
        raise ValueError(
            "stale recruitment advisory audit: " + ",".join(validation.reason_codes)
        )
    return validation


def assert_recruitment_advisory_audit_reproducible(
    first: RecruitmentAdvisoryAuditRecord,
    second: RecruitmentAdvisoryAuditRecord,
) -> None:
    """Assert byte-equivalent advisory lineage fingerprints for repeated identical inputs."""

    if first.recruitment_id != second.recruitment_id:
        raise AssertionError("recruitment advisory audit recruitment_id differs")
    if first.audit_fingerprint_sha256 != second.audit_fingerprint_sha256:
        raise AssertionError("recruitment advisory audit outputs differ")
    if first != second:
        raise AssertionError("recruitment advisory audit payloads differ")


__all__ = [
    "RecruitmentAdvisoryAuditFreshness",
    "RecruitmentAdvisoryAuditRecord",
    "RecruitmentAdvisoryAuditValidation",
    "assert_recruitment_advisory_audit_reproducible",
    "build_recruitment_advisory_audit",
    "require_fresh_recruitment_advisory_audit",
    "revalidate_recruitment_advisory_audit",
]
