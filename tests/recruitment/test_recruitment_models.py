from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agents.models import AgentState
from app.recruitment import (
    RecruitmentBaselineSpec,
    RecruitmentCandidateState,
    RecruitmentMetricDirection,
    RecruitmentProposal,
    RecruitmentSuccessCriterion,
    specify_recruitment_candidate,
)


def _proposal() -> RecruitmentProposal:
    return RecruitmentProposal(
        recruitment_id="recruitment-001",
        proposed_name="Marseille",
        role="liquidation_specialist",
        problem="Repeated liquidation-context errors are not covered by the current specialists.",
        hypothesis="A dedicated liquidation specialist can improve OOS decisions net of AI cost.",
        trigger_evidence_refs=("evaluation:oos:campaign-17",),
    )


def _baseline() -> RecruitmentBaselineSpec:
    return RecruitmentBaselineSpec(
        baseline_id="balanced-v1-without-marseille",
        system_id="balanced_v1",
        description="Frozen incumbent crew used as the recruitment baseline.",
    )


def _criteria() -> tuple[RecruitmentSuccessCriterion, ...]:
    return (
        RecruitmentSuccessCriterion(
            metric_key="marginal_economic_net_eur",
            direction=RecruitmentMetricDirection.AT_LEAST,
            threshold=Decimal("0"),
            primary=True,
            rationale="Candidate must not destroy Economic Net OOS.",
        ),
        RecruitmentSuccessCriterion(
            metric_key="drawdown_increase_pct",
            direction=RecruitmentMetricDirection.AT_MOST,
            threshold=Decimal("0"),
            rationale="Candidate must not worsen drawdown under this test policy.",
        ),
    )


def test_candidate_lifecycle_is_separate_from_agent_registry_state() -> None:
    assert RecruitmentCandidateState.CANDIDATE.value == "CANDIDATE"
    assert RecruitmentCandidateState.SHADOW.value == "SHADOW"
    assert "CANDIDATE" not in {state.value for state in AgentState}


def test_proposal_is_advisory_only_and_immutable() -> None:
    proposal = _proposal()

    assert proposal.state is RecruitmentCandidateState.PROPOSED
    assert proposal.auto_apply is False
    with pytest.raises(ValidationError):
        proposal.proposed_name = "Changed"


def test_specification_requires_one_primary_predeclared_oos_criterion() -> None:
    candidate = specify_recruitment_candidate(
        _proposal(),
        required_data=("liquidation_feed",),
        allowed_tools=("get_liquidation_context",),
        model_class="specialist-small",
        budget_limit_eur=Decimal("3.50"),
        evaluation_window="One frozen DESIGN/VALIDATION/OOS campaign plan.",
        baseline=_baseline(),
        success_criteria=_criteria(),
    )

    assert candidate.state is RecruitmentCandidateState.CANDIDATE
    assert candidate.live_authority is False
    assert candidate.auto_register is False
    assert candidate.auto_promote is False
    assert candidate.core_function is False
    assert all(item.evidence_role == "OOS" for item in candidate.success_criteria)


def test_candidate_rejects_tools_crossing_security_boundaries() -> None:
    with pytest.raises(ValidationError, match="unsafe candidate tool"):
        specify_recruitment_candidate(
            _proposal(),
            required_data=("liquidation_feed",),
            allowed_tools=("execute_live_order",),
            model_class="specialist-small",
            budget_limit_eur=Decimal("1"),
            evaluation_window="Frozen OOS window",
            baseline=_baseline(),
            success_criteria=_criteria(),
        )


def test_candidate_rejects_ambiguous_primary_metric() -> None:
    criteria = tuple(item.model_copy(update={"primary": False}) for item in _criteria())

    with pytest.raises(ValidationError, match="exactly one success criterion must be primary"):
        specify_recruitment_candidate(
            _proposal(),
            required_data=("liquidation_feed",),
            allowed_tools=(),
            model_class="specialist-small",
            budget_limit_eur=Decimal("1"),
            evaluation_window="Frozen OOS window",
            baseline=_baseline(),
            success_criteria=criteria,
        )
