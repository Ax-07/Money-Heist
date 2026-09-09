from __future__ import annotations

from decimal import Decimal

from app.recruitment import (
    RecruitmentBaselineSpec,
    RecruitmentCandidateState,
    RecruitmentCapacityPolicy,
    RecruitmentCapacitySnapshot,
    RecruitmentComputeRequest,
    RecruitmentGateStatus,
    RecruitmentLifecycleAction,
    RecruitmentMetricDirection,
    RecruitmentProposal,
    RecruitmentSuccessCriterion,
    evaluate_candidate_compute,
    evaluate_shadow_admission,
    plan_recruitment_transition,
    record_recruitment_transition,
    specify_recruitment_candidate,
    start_recruitment_lifecycle,
)


def _candidate(*, budget: str = "5"):
    proposal = RecruitmentProposal(
        recruitment_id="recruitment-19a-001",
        proposed_name="Marseille",
        role="liquidation_specialist",
        problem="Liquidation context is not covered by the current candidate hypothesis.",
        hypothesis=(
            "A liquidation specialist may improve OOS economic net without worsening "
            "drawdown."
        ),
        trigger_evidence_refs=("eval:error-family:liquidation",),
    )
    return specify_recruitment_candidate(
        proposal,
        required_data=("liquidations",),
        allowed_tools=("get_liquidation_context",),
        model_class="specialist-small",
        budget_limit_eur=Decimal(budget),
        evaluation_window="three frozen DESIGN/VALIDATION/OOS campaign windows",
        baseline=RecruitmentBaselineSpec(
            baseline_id="balanced-v1-incumbent",
            system_id="balanced_v1",
            description="Existing crew without the candidate.",
        ),
        success_criteria=(
            RecruitmentSuccessCriterion(
                metric_key="marginal_economic_net_eur",
                direction=RecruitmentMetricDirection.AT_LEAST,
                threshold=Decimal("0"),
                primary=True,
                rationale="Candidate must not reduce OOS Economic Net.",
            ),
        ),
    )


def _policy(**overrides):
    values = {
        "policy_id": "operator-policy-test-v1",
        "max_active_specialists": 5,
        "max_shadow_candidates": 2,
        "max_recruitments_per_period": 2,
        "max_compute_per_candidate_eur": Decimal("10"),
    }
    values.update(overrides)
    return RecruitmentCapacityPolicy(**values)


def _snapshot(**overrides):
    values = {
        "period_id": "2026-Q3-test-window",
        "active_specialists": 3,
        "shadow_candidates": 0,
        "recruitments_started": 0,
    }
    values.update(overrides)
    return RecruitmentCapacitySnapshot(**values)


def test_shadow_admission_allows_only_within_explicit_limits() -> None:
    candidate = _candidate()
    lifecycle = start_recruitment_lifecycle(candidate)

    decision = evaluate_shadow_admission(
        candidate,
        lifecycle,
        policy=_policy(),
        snapshot=_snapshot(),
    )

    assert decision.status is RecruitmentGateStatus.ALLOW
    assert decision.reason_codes == ("WITHIN_EXPLICIT_RECRUITMENT_LIMITS",)
    assert len(decision.audit_fingerprint_sha256) == 64
    assert decision.auto_apply is False
    assert decision.registry_mutation is False
    assert decision.live_authority is False
    assert lifecycle.current_state is RecruitmentCandidateState.CANDIDATE


def test_shadow_admission_blocks_population_frequency_and_budget_violations() -> None:
    candidate = _candidate(budget="12")
    lifecycle = start_recruitment_lifecycle(candidate)

    decision = evaluate_shadow_admission(
        candidate,
        lifecycle,
        policy=_policy(max_compute_per_candidate_eur=Decimal("10")),
        snapshot=_snapshot(
            active_specialists=6,
            shadow_candidates=2,
            recruitments_started=2,
        ),
    )

    assert decision.status is RecruitmentGateStatus.BLOCK
    assert set(decision.reason_codes) == {
        "ACTIVE_SPECIALIST_CAP_ALREADY_EXCEEDED",
        "CANDIDATE_BUDGET_ABOVE_POLICY",
        "RECRUITMENT_FREQUENCY_CAP_REACHED",
        "SHADOW_CANDIDATE_CAP_REACHED",
    }


def test_shadow_admission_requires_candidate_lifecycle_state() -> None:
    candidate = _candidate()
    record = start_recruitment_lifecycle(candidate)
    plan = plan_recruitment_transition(
        record,
        action=RecruitmentLifecycleAction.ENTER_SHADOW,
        reason_codes=("CAPACITY_GATE_ALLOWED",),
        evidence_refs=("gate:capacity:abc",),
    )
    shadow = record_recruitment_transition(record, plan, operator_authorized=True)

    decision = evaluate_shadow_admission(
        candidate,
        shadow,
        policy=_policy(),
        snapshot=_snapshot(),
    )

    assert decision.status is RecruitmentGateStatus.BLOCK
    assert "CANDIDATE_STATE_REQUIRED" in decision.reason_codes


def test_capacity_gate_is_deterministic() -> None:
    candidate = _candidate()
    lifecycle = start_recruitment_lifecycle(candidate)
    kwargs = {
        "policy": _policy(),
        "snapshot": _snapshot(),
    }

    left = evaluate_shadow_admission(candidate, lifecycle, **kwargs)
    right = evaluate_shadow_admission(candidate, lifecycle, **kwargs)

    assert left == right
    assert left.audit_fingerprint_sha256 == right.audit_fingerprint_sha256


def test_compute_gate_uses_stricter_candidate_and_operator_budget() -> None:
    candidate = _candidate(budget="5")
    policy = _policy(max_compute_per_candidate_eur=Decimal("10"))

    allowed = evaluate_candidate_compute(
        candidate,
        RecruitmentComputeRequest(
            recruitment_id=candidate.recruitment_id,
            spent_eur=Decimal("3"),
            requested_eur=Decimal("2"),
        ),
        policy=policy,
    )
    blocked = evaluate_candidate_compute(
        candidate,
        RecruitmentComputeRequest(
            recruitment_id=candidate.recruitment_id,
            spent_eur=Decimal("4.5"),
            requested_eur=Decimal("0.6"),
        ),
        policy=policy,
    )

    assert allowed.status is RecruitmentGateStatus.ALLOW
    assert allowed.effective_budget_limit_eur == Decimal("5")
    assert allowed.projected_spend_eur == Decimal("5")
    assert allowed.execute_compute is False
    assert blocked.status is RecruitmentGateStatus.BLOCK
    assert blocked.reason_codes == ("CANDIDATE_COMPUTE_BUDGET_EXCEEDED",)


def test_compute_gate_blocks_candidate_budget_above_operator_policy() -> None:
    candidate = _candidate(budget="12")
    policy = _policy(max_compute_per_candidate_eur=Decimal("10"))

    decision = evaluate_candidate_compute(
        candidate,
        RecruitmentComputeRequest(
            recruitment_id=candidate.recruitment_id,
            spent_eur=Decimal("0"),
            requested_eur=Decimal("1"),
        ),
        policy=policy,
    )

    assert decision.status is RecruitmentGateStatus.BLOCK
    assert decision.effective_budget_limit_eur == Decimal("10")
    assert decision.reason_codes == ("CANDIDATE_BUDGET_ABOVE_POLICY",)
    assert decision.execute_compute is False
    assert decision.auto_apply is False
    assert decision.live_authority is False


def test_gate_rejects_identity_mismatch() -> None:
    candidate = _candidate()
    lifecycle = start_recruitment_lifecycle(candidate).model_copy(
        update={"recruitment_id": "other-recruitment"}
    )

    try:
        evaluate_shadow_admission(
            candidate,
            lifecycle,
            policy=_policy(),
            snapshot=_snapshot(),
        )
    except ValueError as exc:
        assert "same recruitment_id" in str(exc)
    else:
        raise AssertionError("identity mismatch must be rejected")


def test_policy_requires_explicit_non_negative_limits() -> None:
    try:
        _policy(max_shadow_candidates=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative limits must be rejected")
