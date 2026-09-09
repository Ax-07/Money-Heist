from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import runpy

import pytest

from app.recruitment import (
    RecruitmentAdvisoryAuditFreshness,
    RecruitmentAdvisoryTransitionStatus,
    RecruitmentCandidateState,
    assert_recruitment_advisory_audit_reproducible,
    build_recruitment_advisory_audit,
    evaluate_recruitment_advisory,
    plan_recruitment_advisory_transition,
    require_fresh_recruitment_advisory_audit,
    revalidate_recruitment_advisory_audit,
)

_advisory_helpers = runpy.run_path(str(Path(__file__).with_name("test_recruitment_advisory.py")))
_transition_helpers = runpy.run_path(
    str(Path(__file__).with_name("test_recruitment_advisory_transition.py"))
)
_candidate = _advisory_helpers["_candidate"]
_criterion = _advisory_helpers["_criterion"]
_lifecycle = _advisory_helpers["_lifecycle"]
_package = _advisory_helpers["_package"]
_policy = _transition_helpers["_policy"]
_snapshot = _transition_helpers["_snapshot"]


def _context(*, state=RecruitmentCandidateState.SHADOW, policy=None, snapshot=None):
    candidate = _candidate()
    package = _package()
    lifecycle = _lifecycle(package, state)
    advisory = evaluate_recruitment_advisory(package, lifecycle)
    policy = policy or _policy()
    snapshot = snapshot or _snapshot()
    planning = plan_recruitment_advisory_transition(
        candidate,
        package,
        lifecycle,
        advisory,
        policy=policy,
        snapshot=snapshot,
    )
    return candidate, package, lifecycle, advisory, planning, policy, snapshot


def _audit_from_context(context):
    candidate, package, lifecycle, advisory, planning, policy, snapshot = context
    return build_recruitment_advisory_audit(
        candidate,
        package,
        lifecycle,
        advisory,
        planning,
        policy=policy,
        snapshot=snapshot,
    )


def test_ready_plan_builds_complete_operator_gated_audit_lineage() -> None:
    context = _context()
    audit = _audit_from_context(context)
    planning = context[4]

    assert audit.planning_status is RecruitmentAdvisoryTransitionStatus.READY
    assert audit.transition_id == planning.transition_plan.transition_id
    assert audit.planning_fingerprint_sha256 == planning.audit_fingerprint_sha256
    assert audit.operator_authorization_required is True
    assert audit.auto_apply is False
    assert audit.registry_mutation is False
    assert audit.lifecycle_transition_applied is False
    assert audit.promotion_applied is False
    assert audit.live_authority is False


def test_blocked_plan_is_auditable_without_transition_id() -> None:
    context = _context(
        state=RecruitmentCandidateState.PROBATION,
        snapshot=_snapshot(active_specialists=5),
    )
    audit = _audit_from_context(context)

    assert audit.planning_status is RecruitmentAdvisoryTransitionStatus.BLOCKED
    assert audit.transition_id is None


def test_same_inputs_produce_identical_advisory_audit() -> None:
    context = _context()
    first = _audit_from_context(context)
    second = _audit_from_context(context)

    assert first == second
    assert_recruitment_advisory_audit_reproducible(first, second)


def test_reproducibility_assertion_rejects_different_audit_outputs() -> None:
    first = _audit_from_context(_context())
    second = _audit_from_context(_context(policy=_policy(policy_id="operator-policy-other")))

    with pytest.raises(AssertionError, match="outputs differ"):
        assert_recruitment_advisory_audit_reproducible(first, second)


def test_audit_contract_detects_tampering_with_stale_fingerprint() -> None:
    audit = _audit_from_context(_context())

    with pytest.raises(ValueError, match="audit fingerprint does not match payload"):
        replace(audit, lifecycle_revision=audit.lifecycle_revision + 1)


def test_revalidation_is_fresh_for_exact_same_context() -> None:
    context = _context()
    audit = _audit_from_context(context)
    validation = revalidate_recruitment_advisory_audit(
        audit,
        *context[:5],
        policy=context[5],
        snapshot=context[6],
    )

    assert validation.freshness is RecruitmentAdvisoryAuditFreshness.FRESH
    assert validation.reason_codes == ("AUDIT_CONTEXT_FRESH",)
    assert validation.operator_authorization_required is True
    assert validation.record_transition is False
    assert validation.auto_apply is False


def test_lifecycle_revision_change_marks_audit_stale() -> None:
    context = list(_context())
    audit = _audit_from_context(tuple(context))
    lifecycle = context[2]
    context[2] = lifecycle.model_copy(update={"revision": lifecycle.revision + 1})

    validation = revalidate_recruitment_advisory_audit(
        audit,
        *context[:5],
        policy=context[5],
        snapshot=context[6],
    )

    assert validation.freshness is RecruitmentAdvisoryAuditFreshness.STALE
    assert "LIFECYCLE_REVISION_CHANGED" in validation.reason_codes


def test_capacity_snapshot_change_marks_ready_plan_stale_even_if_plan_object_is_reused() -> None:
    context = list(_context())
    audit = _audit_from_context(tuple(context))
    context[6] = _snapshot(shadow_candidates=1)

    validation = revalidate_recruitment_advisory_audit(
        audit,
        *context[:5],
        policy=context[5],
        snapshot=context[6],
    )

    assert validation.freshness is RecruitmentAdvisoryAuditFreshness.STALE
    assert "CAPACITY_CONTEXT_CHANGED" in validation.reason_codes


def test_policy_threshold_change_marks_audit_stale_without_needing_new_policy_id() -> None:
    context = list(_context())
    audit = _audit_from_context(tuple(context))
    context[5] = _policy(max_compute_per_candidate_eur=Decimal("9"))

    validation = revalidate_recruitment_advisory_audit(
        audit,
        *context[:5],
        policy=context[5],
        snapshot=context[6],
    )

    assert validation.freshness is RecruitmentAdvisoryAuditFreshness.STALE
    assert "CAPACITY_CONTEXT_CHANGED" in validation.reason_codes


def test_evidence_package_change_marks_audit_stale() -> None:
    context = list(_context())
    audit = _audit_from_context(tuple(context))
    other_criteria = (_criterion("average_confidence"),)
    context[1] = _package(criteria=other_criteria)

    validation = revalidate_recruitment_advisory_audit(
        audit,
        *context[:5],
        policy=context[5],
        snapshot=context[6],
    )

    assert validation.freshness is RecruitmentAdvisoryAuditFreshness.STALE
    assert "EVIDENCE_PACKAGE_CHANGED" in validation.reason_codes


def test_regenerated_planning_under_changed_capacity_marks_original_audit_stale() -> None:
    context = list(_context(state=RecruitmentCandidateState.PROBATION))
    audit = _audit_from_context(tuple(context))
    changed_snapshot = _snapshot(active_specialists=5)
    context[4] = plan_recruitment_advisory_transition(
        context[0],
        context[1],
        context[2],
        context[3],
        policy=context[5],
        snapshot=changed_snapshot,
    )
    context[6] = changed_snapshot

    validation = revalidate_recruitment_advisory_audit(
        audit,
        *context[:5],
        policy=context[5],
        snapshot=context[6],
    )

    assert validation.freshness is RecruitmentAdvisoryAuditFreshness.STALE
    assert "TRANSITION_PLANNING_CHANGED" in validation.reason_codes
    assert "PLANNING_STATUS_CHANGED" in validation.reason_codes


def test_require_fresh_guard_fails_closed_on_stale_capacity_context() -> None:
    context = list(_context())
    audit = _audit_from_context(tuple(context))
    context[6] = _snapshot(recruitments_started=1)

    with pytest.raises(ValueError, match="stale recruitment advisory audit"):
        require_fresh_recruitment_advisory_audit(
            audit,
            *context[:5],
            policy=context[5],
            snapshot=context[6],
        )


def test_require_fresh_guard_returns_read_only_validation_not_transition_execution() -> None:
    context = _context()
    audit = _audit_from_context(context)

    validation = require_fresh_recruitment_advisory_audit(
        audit,
        *context[:5],
        policy=context[5],
        snapshot=context[6],
    )

    assert validation.freshness is RecruitmentAdvisoryAuditFreshness.FRESH
    assert validation.record_transition is False
    assert validation.operator_authorization_required is True
    assert context[2].current_state is RecruitmentCandidateState.SHADOW


def test_audit_builder_rejects_plan_created_under_different_capacity_context() -> None:
    context = list(_context())
    changed_snapshot = _snapshot(shadow_candidates=1)

    with pytest.raises(ValueError, match="not reproducible from current context"):
        build_recruitment_advisory_audit(
            *context[:5],
            policy=context[5],
            snapshot=changed_snapshot,
        )
