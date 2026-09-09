from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .advisory import RecruitmentAdvisoryAction, RecruitmentAdvisoryReport
from .campaign import candidate_runtime_agent_id
from .evidence_package import RecruitmentCandidateEvidencePackage
from .gates import (
    RecruitmentCapacityPolicy,
    RecruitmentCapacitySnapshot,
    RecruitmentGateDecision,
    RecruitmentGateStatus,
    evaluate_shadow_admission,
)
from .lifecycle import (
    RecruitmentLifecycleAction,
    RecruitmentLifecycleRecord,
    RecruitmentTransitionPlan,
    plan_recruitment_transition,
)
from .models import RecruitmentCandidateSpec, RecruitmentCandidateState


class RecruitmentAdvisoryTransitionStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


def _require_sha256(value: str, *, field_name: str) -> None:
    normalized = value.lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")


def _canonical_reason_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    if not values:
        raise ValueError("reason_codes must not be empty")
    normalized = tuple(sorted(value.strip() for value in values))
    if any(not value for value in normalized):
        raise ValueError("reason_codes must not contain blanks")
    if len(set(normalized)) != len(normalized):
        raise ValueError("reason_codes must not contain duplicates")
    return normalized


def _candidate_spec_fingerprint(candidate: RecruitmentCandidateSpec) -> str:
    return stable_digest(
        {
            "schema": "money-heist.recruitment-candidate-spec.v1",
            "candidate": candidate.model_dump(mode="json"),
        }
    )


def _transition_payload(plan: RecruitmentTransitionPlan | None) -> dict[str, object] | None:
    if plan is None:
        return None
    return plan.model_dump(mode="json")


def _capacity_gate_payload(
    decision: RecruitmentGateDecision | None,
) -> dict[str, object] | None:
    if decision is None:
        return None
    return decision.model_dump(mode="json")


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


def _planning_fingerprint(
    *,
    recruitment_id: str,
    candidate_agent_id: str,
    lifecycle_revision: int,
    current_state: RecruitmentCandidateState,
    advisory_action: RecruitmentAdvisoryAction,
    advisory_fingerprint_sha256: str,
    evidence_package_fingerprint_sha256: str,
    capacity_context_fingerprint_sha256: str,
    status: RecruitmentAdvisoryTransitionStatus,
    reason_codes: tuple[str, ...],
    capacity_gate: RecruitmentGateDecision | None,
    transition_plan: RecruitmentTransitionPlan | None,
) -> str:
    return stable_digest(
        {
            "schema": "money-heist.recruitment-advisory-transition-plan.v1",
            "recruitment_id": recruitment_id,
            "candidate_agent_id": candidate_agent_id,
            "lifecycle_revision": lifecycle_revision,
            "current_state": current_state,
            "advisory_action": advisory_action,
            "advisory_fingerprint_sha256": advisory_fingerprint_sha256,
            "evidence_package_fingerprint_sha256": evidence_package_fingerprint_sha256,
            "capacity_context_fingerprint_sha256": capacity_context_fingerprint_sha256,
            "status": status,
            "reason_codes": reason_codes,
            "capacity_gate": _capacity_gate_payload(capacity_gate),
            "transition_plan": _transition_payload(transition_plan),
            "operator_authorization_required": True,
            "auto_apply": False,
            "registry_mutation": False,
            "lifecycle_transition_applied": False,
            "promotion_applied": False,
            "live_authority": False,
        }
    )


@dataclass(frozen=True, slots=True)
class RecruitmentAdvisoryTransitionPlan:
    """Safety-checked bridge from advisory output to an operator-gated lifecycle plan.

    READY means a deterministic ``RecruitmentTransitionPlan`` may be presented to an
    operator. It does not mean the transition has been applied. BLOCKED deliberately
    carries no transition plan.
    """

    recruitment_id: str
    candidate_agent_id: str
    lifecycle_revision: int
    current_state: RecruitmentCandidateState
    advisory_action: RecruitmentAdvisoryAction
    advisory_fingerprint_sha256: str
    evidence_package_fingerprint_sha256: str
    policy_id: str
    period_id: str
    capacity_context_fingerprint_sha256: str
    status: RecruitmentAdvisoryTransitionStatus
    reason_codes: tuple[str, ...]
    capacity_gate: RecruitmentGateDecision | None
    transition_plan: RecruitmentTransitionPlan | None
    audit_fingerprint_sha256: str
    planner_version: str = "batch19.recruitment-advisory-transition.v1"
    operator_authorization_required: bool = True
    auto_apply: bool = False
    registry_mutation: bool = False
    lifecycle_transition_applied: bool = False
    promotion_applied: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        if not self.recruitment_id.strip():
            raise ValueError("recruitment_id must not be blank")
        if not self.candidate_agent_id.strip():
            raise ValueError("candidate_agent_id must not be blank")
        if not self.policy_id.strip() or not self.period_id.strip():
            raise ValueError("policy_id and period_id must not be blank")
        if self.lifecycle_revision < 0:
            raise ValueError("lifecycle_revision must be >= 0")
        _require_sha256(
            self.advisory_fingerprint_sha256,
            field_name="advisory_fingerprint_sha256",
        )
        _require_sha256(
            self.evidence_package_fingerprint_sha256,
            field_name="evidence_package_fingerprint_sha256",
        )
        _require_sha256(
            self.capacity_context_fingerprint_sha256,
            field_name="capacity_context_fingerprint_sha256",
        )
        _require_sha256(self.audit_fingerprint_sha256, field_name="audit_fingerprint_sha256")
        canonical_reasons = _canonical_reason_codes(self.reason_codes)
        object.__setattr__(self, "reason_codes", canonical_reasons)

        if not self.operator_authorization_required:
            raise ValueError("operator authorization must remain required")
        if (
            self.auto_apply
            or self.registry_mutation
            or self.lifecycle_transition_applied
            or self.promotion_applied
            or self.live_authority
        ):
            raise ValueError("advisory transition planning cannot apply operational changes")

        if self.status is RecruitmentAdvisoryTransitionStatus.READY:
            if self.transition_plan is None:
                raise ValueError("READY planning requires a RecruitmentTransitionPlan")
            if self.transition_plan.recruitment_id != self.recruitment_id:
                raise ValueError("transition plan targets a different recruitment_id")
            if self.transition_plan.expected_revision != self.lifecycle_revision:
                raise ValueError("transition plan revision does not match planning revision")
            if self.transition_plan.from_state is not self.current_state:
                raise ValueError("transition plan state does not match planning state")
        elif self.transition_plan is not None:
            raise ValueError("BLOCKED planning cannot carry a transition plan")

        if self.capacity_gate is not None:
            if self.capacity_gate.recruitment_id != self.recruitment_id:
                raise ValueError("capacity gate targets a different recruitment_id")
            if self.capacity_gate.policy_id != self.policy_id:
                raise ValueError("capacity gate policy_id does not match planning policy")
            if self.capacity_gate.period_id != self.period_id:
                raise ValueError("capacity gate period_id does not match planning period")

        expected_fingerprint = _planning_fingerprint(
            recruitment_id=self.recruitment_id,
            candidate_agent_id=self.candidate_agent_id,
            lifecycle_revision=self.lifecycle_revision,
            current_state=self.current_state,
            advisory_action=self.advisory_action,
            advisory_fingerprint_sha256=self.advisory_fingerprint_sha256,
            evidence_package_fingerprint_sha256=self.evidence_package_fingerprint_sha256,
            capacity_context_fingerprint_sha256=self.capacity_context_fingerprint_sha256,
            status=self.status,
            reason_codes=self.reason_codes,
            capacity_gate=self.capacity_gate,
            transition_plan=self.transition_plan,
        )
        if expected_fingerprint != self.audit_fingerprint_sha256:
            raise ValueError("advisory transition planning fingerprint does not match payload")


def _expected_lifecycle_action(
    advisory: RecruitmentAdvisoryReport,
    lifecycle: RecruitmentLifecycleRecord,
) -> RecruitmentLifecycleAction:
    if advisory.action is RecruitmentAdvisoryAction.REJECT:
        return RecruitmentLifecycleAction.REJECT
    if advisory.action is RecruitmentAdvisoryAction.PROBATION:
        if lifecycle.current_state is not RecruitmentCandidateState.SHADOW:
            raise ValueError("PROBATION advisory requires SHADOW lifecycle state")
        return RecruitmentLifecycleAction.ENTER_PROBATION
    if advisory.action is RecruitmentAdvisoryAction.RECOMMEND_PROMOTION:
        if lifecycle.current_state is not RecruitmentCandidateState.PROBATION:
            raise ValueError("promotion recommendation requires PROBATION lifecycle state")
        return RecruitmentLifecycleAction.RECOMMEND_PROMOTION
    if advisory.action is RecruitmentAdvisoryAction.EXTEND:
        if lifecycle.current_state is RecruitmentCandidateState.CANDIDATE:
            return RecruitmentLifecycleAction.ENTER_SHADOW
        if lifecycle.current_state is RecruitmentCandidateState.SHADOW:
            return RecruitmentLifecycleAction.EXTEND_SHADOW
        if lifecycle.current_state is RecruitmentCandidateState.PROBATION:
            return RecruitmentLifecycleAction.EXTEND_PROBATION
    raise ValueError("advisory action cannot be mapped to current recruitment lifecycle state")


def _assert_identity_and_lineage(
    candidate: RecruitmentCandidateSpec,
    package: RecruitmentCandidateEvidencePackage,
    lifecycle: RecruitmentLifecycleRecord,
    advisory: RecruitmentAdvisoryReport,
) -> None:
    ids = {
        candidate.recruitment_id,
        package.recruitment_id,
        lifecycle.recruitment_id,
        advisory.recruitment_id,
    }
    if len(ids) != 1:
        raise ValueError("candidate, package, lifecycle and advisory must target one recruitment_id")
    if candidate_runtime_agent_id(candidate) != advisory.candidate_agent_id:
        raise ValueError("candidate runtime identity does not match advisory")
    if package.candidate_agent_id != advisory.candidate_agent_id:
        raise ValueError("evidence package candidate identity does not match advisory")
    if advisory.evidence_package_fingerprint_sha256 != package.audit_fingerprint_sha256:
        raise ValueError("advisory was not built from the supplied evidence package")
    if advisory.lifecycle_revision != lifecycle.revision:
        raise ValueError("stale recruitment advisory lifecycle revision")
    if advisory.current_state is not lifecycle.current_state:
        raise ValueError("stale recruitment advisory lifecycle state")
    candidate_fingerprint = _candidate_spec_fingerprint(candidate)
    if candidate_fingerprint != package.lineage.candidate_spec_fingerprint_sha256:
        raise ValueError("candidate spec changed after evidence packaging")


def _progression_block_reasons(
    *,
    action: RecruitmentLifecycleAction,
    candidate: RecruitmentCandidateSpec,
    package: RecruitmentCandidateEvidencePackage,
    policy: RecruitmentCapacityPolicy,
    snapshot: RecruitmentCapacitySnapshot,
) -> tuple[str, ...]:
    if action not in {
        RecruitmentLifecycleAction.ENTER_PROBATION,
        RecruitmentLifecycleAction.RECOMMEND_PROMOTION,
    }:
        return ()

    reasons: set[str] = set()
    if candidate.budget_limit_eur > policy.max_compute_per_candidate_eur:
        reasons.add("CANDIDATE_BUDGET_ABOVE_POLICY")
    direct_cost = package.reputation_evidence.costs.candidate_direct_ai_cost_eur
    if direct_cost > policy.max_compute_per_candidate_eur:
        reasons.add("CANDIDATE_DIRECT_AI_COST_ABOVE_POLICY")

    if (
        action is RecruitmentLifecycleAction.RECOMMEND_PROMOTION
        and snapshot.active_specialists >= policy.max_active_specialists
    ):
        reasons.add("ACTIVE_SPECIALIST_CAP_REACHED_FOR_PROMOTION_RECOMMENDATION")
    return tuple(sorted(reasons))


def plan_recruitment_advisory_transition(
    candidate: RecruitmentCandidateSpec,
    package: RecruitmentCandidateEvidencePackage,
    lifecycle: RecruitmentLifecycleRecord,
    advisory: RecruitmentAdvisoryReport,
    *,
    policy: RecruitmentCapacityPolicy,
    snapshot: RecruitmentCapacitySnapshot,
) -> RecruitmentAdvisoryTransitionPlan:
    """Translate one valid advisory into a safety-checked lifecycle transition plan.

    The function never calls ``record_recruitment_transition``. A READY result still
    requires explicit operator authorization before the underlying transition plan can
    be recorded by the existing lifecycle service.
    """

    _assert_identity_and_lineage(candidate, package, lifecycle, advisory)
    action = _expected_lifecycle_action(advisory, lifecycle)
    capacity_gate: RecruitmentGateDecision | None = None
    block_reasons: tuple[str, ...] = ()

    if action is RecruitmentLifecycleAction.ENTER_SHADOW:
        capacity_gate = evaluate_shadow_admission(
            candidate,
            lifecycle,
            policy=policy,
            snapshot=snapshot,
        )
        if capacity_gate.status is RecruitmentGateStatus.BLOCK:
            block_reasons = tuple(
                sorted(f"SHADOW_ADMISSION_BLOCKED:{code}" for code in capacity_gate.reason_codes)
            )
    elif action is not RecruitmentLifecycleAction.REJECT:
        block_reasons = _progression_block_reasons(
            action=action,
            candidate=candidate,
            package=package,
            policy=policy,
            snapshot=snapshot,
        )

    if block_reasons:
        status = RecruitmentAdvisoryTransitionStatus.BLOCKED
        transition_plan = None
        reasons = tuple(sorted(set((*advisory.reason_codes, *block_reasons))))
    else:
        status = RecruitmentAdvisoryTransitionStatus.READY
        extra_reasons: tuple[str, ...] = ()
        if capacity_gate is not None:
            extra_reasons = ("SHADOW_ADMISSION_GATE_ALLOWED",)
        reasons = tuple(
            sorted(
                set(
                    (
                        *advisory.reason_codes,
                        *extra_reasons,
                        f"ADVISORY_ACTION:{advisory.action.value}",
                    )
                )
            )
        )
        evidence_refs = [
            f"advisory:{advisory.audit_fingerprint_sha256}",
            f"evidence-package:{package.audit_fingerprint_sha256}",
            f"capacity-policy:{policy.policy_id}",
            f"capacity-period:{snapshot.period_id}",
        ]
        if capacity_gate is not None:
            evidence_refs.append(f"capacity-gate:{capacity_gate.audit_fingerprint_sha256}")
        transition_plan = plan_recruitment_transition(
            lifecycle,
            action=action,
            reason_codes=reasons,
            evidence_refs=tuple(evidence_refs),
        )

    capacity_context_fingerprint = _capacity_context_fingerprint(policy, snapshot)
    fingerprint = _planning_fingerprint(
        recruitment_id=candidate.recruitment_id,
        candidate_agent_id=advisory.candidate_agent_id,
        lifecycle_revision=lifecycle.revision,
        current_state=lifecycle.current_state,
        advisory_action=advisory.action,
        advisory_fingerprint_sha256=advisory.audit_fingerprint_sha256,
        evidence_package_fingerprint_sha256=package.audit_fingerprint_sha256,
        capacity_context_fingerprint_sha256=capacity_context_fingerprint,
        status=status,
        reason_codes=reasons,
        capacity_gate=capacity_gate,
        transition_plan=transition_plan,
    )
    result = RecruitmentAdvisoryTransitionPlan(
        recruitment_id=candidate.recruitment_id,
        candidate_agent_id=advisory.candidate_agent_id,
        lifecycle_revision=lifecycle.revision,
        current_state=lifecycle.current_state,
        advisory_action=advisory.action,
        advisory_fingerprint_sha256=advisory.audit_fingerprint_sha256,
        evidence_package_fingerprint_sha256=package.audit_fingerprint_sha256,
        policy_id=policy.policy_id,
        period_id=snapshot.period_id,
        capacity_context_fingerprint_sha256=capacity_context_fingerprint,
        status=status,
        reason_codes=reasons,
        capacity_gate=capacity_gate,
        transition_plan=transition_plan,
        audit_fingerprint_sha256=fingerprint,
    )

    expected = _planning_fingerprint(
        recruitment_id=result.recruitment_id,
        candidate_agent_id=result.candidate_agent_id,
        lifecycle_revision=result.lifecycle_revision,
        current_state=result.current_state,
        advisory_action=result.advisory_action,
        advisory_fingerprint_sha256=result.advisory_fingerprint_sha256,
        evidence_package_fingerprint_sha256=result.evidence_package_fingerprint_sha256,
        capacity_context_fingerprint_sha256=result.capacity_context_fingerprint_sha256,
        status=result.status,
        reason_codes=result.reason_codes,
        capacity_gate=result.capacity_gate,
        transition_plan=result.transition_plan,
    )
    if expected != result.audit_fingerprint_sha256:  # defensive builder invariant
        raise ValueError("advisory transition planning fingerprint mismatch")
    return result


__all__ = [
    "RecruitmentAdvisoryTransitionPlan",
    "RecruitmentAdvisoryTransitionStatus",
    "plan_recruitment_advisory_transition",
]
