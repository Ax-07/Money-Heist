from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import runpy

import pytest

from app.recruitment import (
    RecruitmentAdvisoryAction,
    RecruitmentAdvisoryTransitionStatus,
    RecruitmentCandidateState,
    RecruitmentCapacityPolicy,
    RecruitmentCapacitySnapshot,
    RecruitmentLifecycleAction,
    RecruitmentMetricDirection,
    RecruitmentTransitionPlan,
    evaluate_recruitment_advisory,
    plan_recruitment_advisory_transition,
    record_recruitment_transition,
)

_helpers = runpy.run_path(str(Path(__file__).with_name("test_recruitment_advisory.py")))
_candidate = _helpers["_candidate"]
_criterion = _helpers["_criterion"]
_lifecycle = _helpers["_lifecycle"]
_package = _helpers["_package"]


def _policy(**overrides):
    values = {
        "policy_id": "operator-policy-19d2-v1",
        "max_active_specialists": 5,
        "max_shadow_candidates": 2,
        "max_recruitments_per_period": 2,
        "max_compute_per_candidate_eur": Decimal("10"),
    }
    values.update(overrides)
    return RecruitmentCapacityPolicy(**values)


def _snapshot(**overrides):
    values = {
        "period_id": "2026-Q3-recruitment-advisory",
        "active_specialists": 3,
        "shadow_candidates": 0,
        "recruitments_started": 0,
    }
    values.update(overrides)
    return RecruitmentCapacitySnapshot(**values)


def _plan(candidate, package, lifecycle, *, policy=None, snapshot=None):
    advisory = evaluate_recruitment_advisory(package, lifecycle)
    result = plan_recruitment_advisory_transition(
        candidate,
        package,
        lifecycle,
        advisory,
        policy=policy or _policy(),
        snapshot=snapshot or _snapshot(),
    )
    return advisory, result


def test_shadow_probation_advisory_builds_operator_gated_enter_probation_plan() -> None:
    candidate = _candidate()
    package = _package()
    lifecycle = _lifecycle(package, RecruitmentCandidateState.SHADOW)

    advisory, result = _plan(candidate, package, lifecycle)

    assert advisory.action is RecruitmentAdvisoryAction.PROBATION
    assert result.status is RecruitmentAdvisoryTransitionStatus.READY
    assert isinstance(result.transition_plan, RecruitmentTransitionPlan)
    assert result.transition_plan.action is RecruitmentLifecycleAction.ENTER_PROBATION
    assert result.transition_plan.from_state is RecruitmentCandidateState.SHADOW
    assert result.transition_plan.to_state is RecruitmentCandidateState.PROBATION
    assert result.operator_authorization_required is True
    assert result.auto_apply is False
    assert result.registry_mutation is False
    assert result.lifecycle_transition_applied is False
    assert result.promotion_applied is False
    assert result.live_authority is False
    assert lifecycle.current_state is RecruitmentCandidateState.SHADOW


def test_probation_promotion_advisory_builds_recommendation_plan_only_when_capacity_exists() -> None:
    candidate = _candidate()
    package = _package()
    lifecycle = _lifecycle(package, RecruitmentCandidateState.PROBATION)

    advisory, result = _plan(candidate, package, lifecycle)

    assert advisory.action is RecruitmentAdvisoryAction.RECOMMEND_PROMOTION
    assert result.status is RecruitmentAdvisoryTransitionStatus.READY
    assert result.transition_plan is not None
    assert result.transition_plan.action is RecruitmentLifecycleAction.RECOMMEND_PROMOTION
    assert result.transition_plan.to_state is RecruitmentCandidateState.PROMOTION_RECOMMENDED
    assert result.promotion_applied is False


def test_promotion_recommendation_is_blocked_when_active_specialist_cap_is_reached() -> None:
    candidate = _candidate()
    package = _package()
    lifecycle = _lifecycle(package, RecruitmentCandidateState.PROBATION)

    advisory, result = _plan(
        candidate,
        package,
        lifecycle,
        snapshot=_snapshot(active_specialists=5),
    )

    assert advisory.action is RecruitmentAdvisoryAction.RECOMMEND_PROMOTION
    assert result.status is RecruitmentAdvisoryTransitionStatus.BLOCKED
    assert result.transition_plan is None
    assert "ACTIVE_SPECIALIST_CAP_REACHED_FOR_PROMOTION_RECOMMENDATION" in result.reason_codes


def test_candidate_extend_may_plan_enter_shadow_only_after_capacity_gate_allow() -> None:
    candidate = _candidate()
    package = _package()
    lifecycle = _lifecycle(package, RecruitmentCandidateState.CANDIDATE)

    advisory, result = _plan(candidate, package, lifecycle)

    assert advisory.action is RecruitmentAdvisoryAction.EXTEND
    assert result.status is RecruitmentAdvisoryTransitionStatus.READY
    assert result.capacity_gate is not None
    assert result.capacity_gate.status.value == "ALLOW"
    assert result.transition_plan is not None
    assert result.transition_plan.action is RecruitmentLifecycleAction.ENTER_SHADOW
    assert "SHADOW_ADMISSION_GATE_ALLOWED" in result.reason_codes


def test_candidate_enter_shadow_is_blocked_when_shadow_capacity_gate_blocks() -> None:
    candidate = _candidate()
    package = _package()
    lifecycle = _lifecycle(package, RecruitmentCandidateState.CANDIDATE)

    _, result = _plan(
        candidate,
        package,
        lifecycle,
        snapshot=_snapshot(shadow_candidates=2, recruitments_started=2),
    )

    assert result.status is RecruitmentAdvisoryTransitionStatus.BLOCKED
    assert result.transition_plan is None
    assert result.capacity_gate is not None
    assert any(code.startswith("SHADOW_ADMISSION_BLOCKED:") for code in result.reason_codes)
    assert "SHADOW_ADMISSION_BLOCKED:SHADOW_CANDIDATE_CAP_REACHED" in result.reason_codes
    assert "SHADOW_ADMISSION_BLOCKED:RECRUITMENT_FREQUENCY_CAP_REACHED" in result.reason_codes


def test_shadow_extend_advisory_preserves_shadow_without_forcing_progression() -> None:
    criteria = (_criterion("profit_factor"),)
    candidate = _candidate(criteria=criteria)
    package = _package(criteria=criteria)
    lifecycle = _lifecycle(package, RecruitmentCandidateState.SHADOW)

    advisory, result = _plan(candidate, package, lifecycle)

    assert advisory.action is RecruitmentAdvisoryAction.EXTEND
    assert result.status is RecruitmentAdvisoryTransitionStatus.READY
    assert result.transition_plan is not None
    assert result.transition_plan.action is RecruitmentLifecycleAction.EXTEND_SHADOW
    assert result.transition_plan.to_state is RecruitmentCandidateState.SHADOW


def test_reject_advisory_can_always_build_reject_plan_even_when_capacity_is_exhausted() -> None:
    criteria = (
        _criterion(
            "average_confidence",
            direction=RecruitmentMetricDirection.AT_LEAST,
            threshold="0.95",
        ),
    )
    candidate = _candidate(criteria=criteria)
    package = _package(criteria=criteria)
    lifecycle = _lifecycle(package, RecruitmentCandidateState.SHADOW)

    advisory, result = _plan(
        candidate,
        package,
        lifecycle,
        policy=_policy(
            max_active_specialists=0,
            max_shadow_candidates=0,
            max_recruitments_per_period=0,
            max_compute_per_candidate_eur=Decimal("0"),
        ),
        snapshot=_snapshot(active_specialists=9, shadow_candidates=9, recruitments_started=9),
    )

    assert advisory.action is RecruitmentAdvisoryAction.REJECT
    assert result.status is RecruitmentAdvisoryTransitionStatus.READY
    assert result.transition_plan is not None
    assert result.transition_plan.action is RecruitmentLifecycleAction.REJECT
    assert result.transition_plan.to_state is RecruitmentCandidateState.REJECTED


def test_positive_progression_blocks_candidate_budget_above_operator_policy() -> None:
    candidate = _candidate(budget="10")
    package = _package(budget="10", direct_candidate_cost="6", with_total_cost="7")
    lifecycle = _lifecycle(package, RecruitmentCandidateState.SHADOW)

    advisory, result = _plan(
        candidate,
        package,
        lifecycle,
        policy=_policy(max_compute_per_candidate_eur=Decimal("5")),
    )

    assert advisory.action is RecruitmentAdvisoryAction.PROBATION
    assert result.status is RecruitmentAdvisoryTransitionStatus.BLOCKED
    assert result.transition_plan is None
    assert "CANDIDATE_BUDGET_ABOVE_POLICY" in result.reason_codes
    assert "CANDIDATE_DIRECT_AI_COST_ABOVE_POLICY" in result.reason_codes


def test_stale_advisory_revision_is_rejected_before_planning() -> None:
    candidate = _candidate()
    package = _package()
    lifecycle = _lifecycle(package, RecruitmentCandidateState.SHADOW)
    advisory = evaluate_recruitment_advisory(package, lifecycle)
    advanced = lifecycle.model_copy(update={"revision": lifecycle.revision + 1})

    with pytest.raises(ValueError, match="stale recruitment advisory lifecycle revision"):
        plan_recruitment_advisory_transition(
            candidate,
            package,
            advanced,
            advisory,
            policy=_policy(),
            snapshot=_snapshot(),
        )


def test_advisory_must_reference_the_exact_supplied_evidence_package() -> None:
    package = _package()
    lifecycle = _lifecycle(package, RecruitmentCandidateState.SHADOW)
    advisory = evaluate_recruitment_advisory(package, lifecycle)
    other_criteria = (_criterion("average_confidence"),)
    other_candidate = _candidate(criteria=other_criteria)
    other_package = _package(criteria=other_criteria)

    with pytest.raises(ValueError, match="advisory was not built from the supplied evidence package"):
        plan_recruitment_advisory_transition(
            other_candidate,
            other_package,
            lifecycle,
            advisory,
            policy=_policy(),
            snapshot=_snapshot(),
        )


def test_candidate_spec_changed_after_evidence_package_is_rejected() -> None:
    candidate = _candidate()
    package = _package()
    lifecycle = _lifecycle(package, RecruitmentCandidateState.SHADOW)
    advisory = evaluate_recruitment_advisory(package, lifecycle)
    changed = candidate.model_copy(update={"budget_limit_eur": Decimal("6")})

    with pytest.raises(ValueError, match="candidate spec changed after evidence packaging"):
        plan_recruitment_advisory_transition(
            changed,
            package,
            lifecycle,
            advisory,
            policy=_policy(),
            snapshot=_snapshot(),
        )


def test_same_inputs_produce_same_advisory_transition_plan_and_fingerprint() -> None:
    candidate = _candidate()
    package = _package()
    lifecycle = _lifecycle(package, RecruitmentCandidateState.SHADOW)
    advisory = evaluate_recruitment_advisory(package, lifecycle)
    kwargs = {"policy": _policy(), "snapshot": _snapshot()}

    first = plan_recruitment_advisory_transition(candidate, package, lifecycle, advisory, **kwargs)
    second = plan_recruitment_advisory_transition(candidate, package, lifecycle, advisory, **kwargs)

    assert first == second
    assert first.audit_fingerprint_sha256 == second.audit_fingerprint_sha256
    assert len(first.capacity_context_fingerprint_sha256) == 64


def test_transition_planning_contract_detects_tampering_with_stale_fingerprint() -> None:
    candidate = _candidate()
    package = _package()
    lifecycle = _lifecycle(package, RecruitmentCandidateState.SHADOW)
    _, result = _plan(candidate, package, lifecycle)

    with pytest.raises(ValueError, match="fingerprint does not match payload"):
        replace(result, reason_codes=(*result.reason_codes, "TAMPERED"))


def test_ready_transition_remains_operator_gated_when_recording_is_attempted() -> None:
    candidate = _candidate()
    package = _package()
    lifecycle = _lifecycle(package, RecruitmentCandidateState.SHADOW)
    _, result = _plan(candidate, package, lifecycle)
    assert result.transition_plan is not None

    with pytest.raises(PermissionError, match="explicit operator authorization"):
        record_recruitment_transition(
            lifecycle,
            result.transition_plan,
            operator_authorized=False,
        )

    assert lifecycle.current_state is RecruitmentCandidateState.SHADOW
