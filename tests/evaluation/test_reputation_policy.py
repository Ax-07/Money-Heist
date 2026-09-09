from decimal import Decimal

import pytest

from app.agents.models import AgentState
from app.evaluation.reputation_policy import (
    AgentStateEvidence,
    DeterministicAgentStateAdvisor,
    EvidenceSufficiency,
    ReputationPolicyThresholds,
    StateRecommendationAction,
)


D = Decimal


def thresholds() -> ReputationPolicyThresholds:
    return ReputationPolicyThresholds(
        min_evaluation_samples=30,
        min_ablation_comparisons=3,
        promotion_beneficial_ratio=D("0.67"),
        demotion_harmful_ratio=D("0.67"),
        min_economic_net_contribution_eur=D("1.00"),
        max_drawdown_increase_pct=D("0.50"),
        max_ai_cost_share_pct=D("0.25"),
    )


def evidence(
    *,
    agent_id: str = "berlin",
    state: AgentState = AgentState.ON_DEMAND,
    core: bool = False,
    evaluation_samples: int = 100,
    comparisons: int = 3,
    beneficial: int = 3,
    harmful: int = 0,
    inconclusive: int = 0,
    economic_net: str | None = "2.00",
    drawdown_reduction: str | None = "0.10",
    cost_share: str | None = "0.10",
) -> AgentStateEvidence:
    return AgentStateEvidence(
        agent_id=agent_id,
        current_state=state,
        core=core,
        evaluation_sample_count=evaluation_samples,
        ablation_comparison_count=comparisons,
        beneficial_ablation_count=beneficial,
        harmful_ablation_count=harmful,
        inconclusive_ablation_count=inconclusive,
        economic_net_contribution_eur=None if economic_net is None else D(economic_net),
        drawdown_reduction_pct=(
            None if drawdown_reduction is None else D(drawdown_reduction)
        ),
        ai_cost_share_pct=None if cost_share is None else D(cost_share),
    )


def test_thresholds_reject_implicit_or_invalid_policy_values() -> None:
    with pytest.raises(ValueError, match="promotion_beneficial_ratio"):
        ReputationPolicyThresholds(
            min_evaluation_samples=30,
            min_ablation_comparisons=3,
            promotion_beneficial_ratio=D("1.1"),
            demotion_harmful_ratio=D("0.67"),
            min_economic_net_contribution_eur=D("1"),
            max_drawdown_increase_pct=D("0.5"),
            max_ai_cost_share_pct=D("0.25"),
        )


def test_evidence_requires_complete_ablation_classification() -> None:
    with pytest.raises(ValueError, match="must equal"):
        evidence(comparisons=3, beneficial=1, harmful=1, inconclusive=0)


def test_core_agent_is_never_state_mutated_by_advisor() -> None:
    recommendation = DeterministicAgentStateAdvisor(thresholds()).recommend(
        evidence(agent_id="palermo", state=AgentState.ACTIVE, core=True)
    )

    assert recommendation.recommended_state is AgentState.ACTIVE
    assert recommendation.action is StateRecommendationAction.HOLD
    assert recommendation.reason_codes == ("CORE_FUNCTION_PROTECTED",)
    assert recommendation.auto_apply is False


def test_insufficient_evidence_holds_state_fail_closed() -> None:
    recommendation = DeterministicAgentStateAdvisor(thresholds()).recommend(
        evidence(
            evaluation_samples=12,
            comparisons=1,
            beneficial=1,
            harmful=0,
            inconclusive=0,
        )
    )

    assert recommendation.recommended_state is AgentState.ON_DEMAND
    assert recommendation.evidence_sufficiency is EvidenceSufficiency.INSUFFICIENT
    assert recommendation.reason_codes == (
        "INSUFFICIENT_EVALUATION_SAMPLES",
        "INSUFFICIENT_ABLATION_COMPARISONS",
    )


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (AgentState.SHADOW, AgentState.PROBATION),
        (AgentState.PROBATION, AgentState.ON_DEMAND),
        (AgentState.ON_DEMAND, AgentState.ACTIVE),
        (AgentState.ACTIVE, AgentState.ACTIVE),
    ],
)
def test_positive_multidimensional_evidence_promotes_at_most_one_step(
    current: AgentState,
    expected: AgentState,
) -> None:
    recommendation = DeterministicAgentStateAdvisor(thresholds()).recommend(
        evidence(state=current)
    )

    assert recommendation.recommended_state is expected
    assert recommendation.action is (
        StateRecommendationAction.HOLD
        if current is AgentState.ACTIVE
        else StateRecommendationAction.PROMOTE
    )


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (AgentState.ACTIVE, AgentState.ON_DEMAND),
        (AgentState.ON_DEMAND, AgentState.SHADOW),
        (AgentState.PROBATION, AgentState.SHADOW),
        (AgentState.SHADOW, AgentState.SHADOW),
    ],
)
def test_consistently_harmful_ablation_demotes_conservatively(
    current: AgentState,
    expected: AgentState,
) -> None:
    recommendation = DeterministicAgentStateAdvisor(thresholds()).recommend(
        evidence(
            state=current,
            beneficial=0,
            harmful=3,
            economic_net="-2.00",
            drawdown_reduction="-0.80",
        )
    )

    assert recommendation.recommended_state is expected
    assert "ABLATION_CONSISTENTLY_HARMFUL" in recommendation.reason_codes
    assert "NEGATIVE_ECONOMIC_NET_CONTRIBUTION" in recommendation.reason_codes
    assert "DRAWDOWN_WORSENING_ABOVE_POLICY" in recommendation.reason_codes


def test_high_cost_share_reduces_active_frequency_without_disabling_agent() -> None:
    recommendation = DeterministicAgentStateAdvisor(thresholds()).recommend(
        evidence(state=AgentState.ACTIVE, cost_share="0.40")
    )

    assert recommendation.recommended_state is AgentState.ON_DEMAND
    assert recommendation.action is StateRecommendationAction.REDUCE_FREQUENCY
    assert recommendation.reason_codes == ("AI_COST_SHARE_ABOVE_POLICY",)


def test_disabled_agent_requires_external_review_even_with_positive_evidence() -> None:
    recommendation = DeterministicAgentStateAdvisor(thresholds()).recommend(
        evidence(state=AgentState.DISABLED)
    )

    assert recommendation.recommended_state is AgentState.DISABLED
    assert recommendation.action is StateRecommendationAction.HOLD
    assert recommendation.reason_codes == ("DISABLED_REQUIRES_EXTERNAL_REVIEW",)


def test_missing_economic_contribution_prevents_promotion() -> None:
    recommendation = DeterministicAgentStateAdvisor(thresholds()).recommend(
        evidence(state=AgentState.SHADOW, economic_net=None)
    )

    assert recommendation.recommended_state is AgentState.SHADOW
    assert recommendation.action is StateRecommendationAction.HOLD
    assert recommendation.reason_codes == ("MIXED_OR_INCONCLUSIVE_EVIDENCE",)


def test_recommend_many_is_deterministic_and_rejects_duplicates() -> None:
    advisor = DeterministicAgentStateAdvisor(thresholds())
    recommendations = advisor.recommend_many(
        [
            evidence(agent_id="tokyo"),
            evidence(agent_id="berlin"),
        ]
    )
    assert tuple(item.agent_id for item in recommendations) == ("berlin", "tokyo")

    with pytest.raises(ValueError, match="duplicate agent evidence"):
        advisor.recommend_many(
            [
                evidence(agent_id="tokyo"),
                evidence(agent_id="tokyo"),
            ]
        )
