from decimal import Decimal

import pytest

from app.recruitment import (
    RecruitmentBaselineSpec,
    RecruitmentCandidateState,
    RecruitmentLifecycleAction,
    RecruitmentMetricDirection,
    RecruitmentProposal,
    RecruitmentSuccessCriterion,
    plan_recruitment_transition,
    record_recruitment_transition,
    specify_recruitment_candidate,
    start_recruitment_lifecycle,
)


def _candidate():
    proposal = RecruitmentProposal(
        recruitment_id="recruitment-001",
        proposed_name="Marseille",
        role="liquidation_specialist",
        problem="Repeated liquidation-context errors.",
        hypothesis="A specialist may improve OOS decisions net of cost.",
        trigger_evidence_refs=("evaluation:oos:campaign-17",),
    )
    return specify_recruitment_candidate(
        proposal,
        required_data=("liquidation_feed",),
        allowed_tools=("get_liquidation_context",),
        model_class="specialist-small",
        budget_limit_eur=Decimal("3.50"),
        evaluation_window="Frozen DESIGN/VALIDATION/OOS plan",
        baseline=RecruitmentBaselineSpec(
            baseline_id="balanced-v1-incumbent",
            system_id="balanced_v1",
            description="Frozen incumbent baseline.",
        ),
        success_criteria=(
            RecruitmentSuccessCriterion(
                metric_key="marginal_economic_net_eur",
                direction=RecruitmentMetricDirection.AT_LEAST,
                threshold=Decimal("0"),
                primary=True,
                rationale="Primary OOS criterion.",
            ),
        ),
    )


def _plan(record, action):
    return plan_recruitment_transition(
        record,
        action=action,
        reason_codes=("OPERATOR_REVIEW_COMPLETE",),
        evidence_refs=("recruitment:evidence:001",),
    )


def test_lifecycle_starts_as_candidate_without_operational_authority() -> None:
    record = start_recruitment_lifecycle(_candidate())

    assert record.current_state is RecruitmentCandidateState.CANDIDATE
    assert record.revision == 0
    assert record.auto_apply is False
    assert record.registry_mutation is False
    assert record.live_authority is False


def test_planning_shadow_transition_is_deterministic_and_non_mutating() -> None:
    record = start_recruitment_lifecycle(_candidate())

    first = _plan(record, RecruitmentLifecycleAction.ENTER_SHADOW)
    second = _plan(record, RecruitmentLifecycleAction.ENTER_SHADOW)

    assert first == second
    assert first.transition_id == second.transition_id
    assert first.from_state is RecruitmentCandidateState.CANDIDATE
    assert first.to_state is RecruitmentCandidateState.SHADOW
    assert first.auto_apply is False
    assert first.registry_mutation is False
    assert record.current_state is RecruitmentCandidateState.CANDIDATE


def test_recording_transition_requires_explicit_operator_authorization() -> None:
    record = start_recruitment_lifecycle(_candidate())
    plan = _plan(record, RecruitmentLifecycleAction.ENTER_SHADOW)

    with pytest.raises(PermissionError, match="operator authorization"):
        record_recruitment_transition(record, plan, operator_authorized=False)

    advanced = record_recruitment_transition(record, plan, operator_authorized=True)
    assert advanced.current_state is RecruitmentCandidateState.SHADOW
    assert advanced.revision == 1
    assert advanced.transition_ids == (plan.transition_id,)


def test_candidate_cannot_jump_directly_to_probation_or_promotion() -> None:
    record = start_recruitment_lifecycle(_candidate())

    with pytest.raises(ValueError, match="not allowed"):
        _plan(record, RecruitmentLifecycleAction.ENTER_PROBATION)
    with pytest.raises(ValueError, match="not allowed"):
        _plan(record, RecruitmentLifecycleAction.RECOMMEND_PROMOTION)


def test_promotion_is_only_recommended_after_probation_and_remains_reversible() -> None:
    record = start_recruitment_lifecycle(_candidate())
    record = record_recruitment_transition(
        record,
        _plan(record, RecruitmentLifecycleAction.ENTER_SHADOW),
        operator_authorized=True,
    )
    record = record_recruitment_transition(
        record,
        _plan(record, RecruitmentLifecycleAction.ENTER_PROBATION),
        operator_authorized=True,
    )
    recommended = record_recruitment_transition(
        record,
        _plan(record, RecruitmentLifecycleAction.RECOMMEND_PROMOTION),
        operator_authorized=True,
    )

    assert recommended.current_state is RecruitmentCandidateState.PROMOTION_RECOMMENDED
    assert recommended.registry_mutation is False
    assert recommended.live_authority is False

    withdrawn = record_recruitment_transition(
        recommended,
        _plan(
            recommended,
            RecruitmentLifecycleAction.WITHDRAW_PROMOTION_RECOMMENDATION,
        ),
        operator_authorized=True,
    )
    assert withdrawn.current_state is RecruitmentCandidateState.PROBATION


def test_rejection_is_auditable_and_can_be_reopened_only_explicitly() -> None:
    record = start_recruitment_lifecycle(_candidate())
    rejected = record_recruitment_transition(
        record,
        _plan(record, RecruitmentLifecycleAction.REJECT),
        operator_authorized=True,
    )
    assert rejected.current_state is RecruitmentCandidateState.REJECTED

    with pytest.raises(ValueError, match="not allowed"):
        _plan(rejected, RecruitmentLifecycleAction.ENTER_SHADOW)

    reopened = record_recruitment_transition(
        rejected,
        _plan(rejected, RecruitmentLifecycleAction.REOPEN_CANDIDATE),
        operator_authorized=True,
    )
    assert reopened.current_state is RecruitmentCandidateState.CANDIDATE


def test_stale_transition_plan_is_rejected() -> None:
    record = start_recruitment_lifecycle(_candidate())
    first_plan = _plan(record, RecruitmentLifecycleAction.ENTER_SHADOW)
    advanced = record_recruitment_transition(record, first_plan, operator_authorized=True)

    with pytest.raises(ValueError, match="stale recruitment transition plan revision"):
        record_recruitment_transition(advanced, first_plan, operator_authorized=True)
