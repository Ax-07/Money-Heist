from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.agents.models import AgentState


ZERO = Decimal("0")
ONE = Decimal("1")


class EvidenceSufficiency(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class StateRecommendationAction(StrEnum):
    HOLD = "HOLD"
    PROMOTE = "PROMOTE"
    DEMOTE = "DEMOTE"
    REDUCE_FREQUENCY = "REDUCE_FREQUENCY"


@dataclass(frozen=True, slots=True)
class ReputationPolicyThresholds:
    """Explicit operator-owned thresholds for advisory state recommendations.

    Batch 18 must not invent LIVE/promotion thresholds. The caller supplies every
    material threshold before evaluating an agent.
    """

    min_evaluation_samples: int
    min_ablation_comparisons: int
    promotion_beneficial_ratio: Decimal
    demotion_harmful_ratio: Decimal
    min_economic_net_contribution_eur: Decimal
    max_drawdown_increase_pct: Decimal
    max_ai_cost_share_pct: Decimal

    def __post_init__(self) -> None:
        if self.min_evaluation_samples < 1:
            raise ValueError("min_evaluation_samples must be >= 1")
        if self.min_ablation_comparisons < 1:
            raise ValueError("min_ablation_comparisons must be >= 1")
        _require_ratio("promotion_beneficial_ratio", self.promotion_beneficial_ratio)
        _require_ratio("demotion_harmful_ratio", self.demotion_harmful_ratio)
        _require_ratio("max_ai_cost_share_pct", self.max_ai_cost_share_pct)
        if self.min_economic_net_contribution_eur < ZERO:
            raise ValueError("min_economic_net_contribution_eur must be >= 0")
        if self.max_drawdown_increase_pct < ZERO:
            raise ValueError("max_drawdown_increase_pct must be >= 0")


@dataclass(frozen=True, slots=True)
class AgentStateEvidence:
    """Multidimensional evidence consumed by the deterministic advisory policy.

    Sign conventions are intentionally explicit:
    - economic_net_contribution_eur > 0 means the agent improved Economic Net.
    - drawdown_reduction_pct > 0 means the agent reduced max drawdown.
    - ai_cost_share_pct is the agent share of measured AI cost, in [0, 1].

    beneficial/harmful/inconclusive counts are expected to come from comparable
    deterministic ablation comparisons created by Batch 18 foundations.
    """

    agent_id: str
    current_state: AgentState
    core: bool
    evaluation_sample_count: int
    ablation_comparison_count: int
    beneficial_ablation_count: int
    harmful_ablation_count: int
    inconclusive_ablation_count: int
    economic_net_contribution_eur: Decimal | None
    drawdown_reduction_pct: Decimal | None
    ai_cost_share_pct: Decimal | None

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise ValueError("agent_id must not be empty")
        counts = (
            self.evaluation_sample_count,
            self.ablation_comparison_count,
            self.beneficial_ablation_count,
            self.harmful_ablation_count,
            self.inconclusive_ablation_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("evidence counts must be >= 0")
        classified = (
            self.beneficial_ablation_count
            + self.harmful_ablation_count
            + self.inconclusive_ablation_count
        )
        if classified != self.ablation_comparison_count:
            raise ValueError(
                "beneficial + harmful + inconclusive must equal ablation_comparison_count"
            )
        if self.ai_cost_share_pct is not None:
            _require_ratio("ai_cost_share_pct", self.ai_cost_share_pct)

    @property
    def beneficial_ratio(self) -> Decimal | None:
        if self.ablation_comparison_count == 0:
            return None
        return Decimal(self.beneficial_ablation_count) / Decimal(self.ablation_comparison_count)

    @property
    def harmful_ratio(self) -> Decimal | None:
        if self.ablation_comparison_count == 0:
            return None
        return Decimal(self.harmful_ablation_count) / Decimal(self.ablation_comparison_count)


@dataclass(frozen=True, slots=True)
class AgentStateRecommendation:
    policy_version: str
    agent_id: str
    current_state: AgentState
    recommended_state: AgentState
    action: StateRecommendationAction
    evidence_sufficiency: EvidenceSufficiency
    reason_codes: tuple[str, ...]
    auto_apply: bool = False

    def __post_init__(self) -> None:
        if self.auto_apply:
            raise ValueError("Batch 18 state recommendations are advisory only")
        if not self.reason_codes:
            raise ValueError("reason_codes must not be empty")


class DeterministicAgentStateAdvisor:
    """Advisory-only state policy; never mutates AgentRegistry or trading state."""

    policy_version = "batch18.reputation-state-policy.v1"

    def __init__(self, thresholds: ReputationPolicyThresholds) -> None:
        self._thresholds = thresholds

    def recommend(self, evidence: AgentStateEvidence) -> AgentStateRecommendation:
        if evidence.core:
            return self._hold(
                evidence,
                EvidenceSufficiency.SUFFICIENT,
                "CORE_FUNCTION_PROTECTED",
            )

        if evidence.current_state is AgentState.DISABLED:
            return self._hold(
                evidence,
                EvidenceSufficiency.SUFFICIENT,
                "DISABLED_REQUIRES_EXTERNAL_REVIEW",
            )

        if not self._has_minimum_evidence(evidence):
            reasons = []
            if evidence.evaluation_sample_count < self._thresholds.min_evaluation_samples:
                reasons.append("INSUFFICIENT_EVALUATION_SAMPLES")
            if evidence.ablation_comparison_count < self._thresholds.min_ablation_comparisons:
                reasons.append("INSUFFICIENT_ABLATION_COMPARISONS")
            return self._hold(
                evidence,
                EvidenceSufficiency.INSUFFICIENT,
                *reasons,
            )

        demotion_reasons = self._demotion_reasons(evidence)
        if demotion_reasons:
            recommended = _demote_one_step(evidence.current_state)
            action = (
                StateRecommendationAction.HOLD
                if recommended is evidence.current_state
                else StateRecommendationAction.DEMOTE
            )
            return self._build(
                evidence,
                recommended,
                action,
                EvidenceSufficiency.SUFFICIENT,
                demotion_reasons,
            )

        if self._cost_pressure(evidence):
            recommended = _reduce_frequency(evidence.current_state)
            action = (
                StateRecommendationAction.HOLD
                if recommended is evidence.current_state
                else StateRecommendationAction.REDUCE_FREQUENCY
            )
            return self._build(
                evidence,
                recommended,
                action,
                EvidenceSufficiency.SUFFICIENT,
                ("AI_COST_SHARE_ABOVE_POLICY",),
            )

        promotion_reasons = self._promotion_reasons(evidence)
        if promotion_reasons:
            recommended = _promote_one_step(evidence.current_state)
            action = (
                StateRecommendationAction.HOLD
                if recommended is evidence.current_state
                else StateRecommendationAction.PROMOTE
            )
            return self._build(
                evidence,
                recommended,
                action,
                EvidenceSufficiency.SUFFICIENT,
                promotion_reasons,
            )

        return self._hold(
            evidence,
            EvidenceSufficiency.SUFFICIENT,
            "MIXED_OR_INCONCLUSIVE_EVIDENCE",
        )

    def recommend_many(
        self,
        evidence_items: tuple[AgentStateEvidence, ...] | list[AgentStateEvidence],
    ) -> tuple[AgentStateRecommendation, ...]:
        by_agent: dict[str, AgentStateEvidence] = {}
        for evidence in evidence_items:
            if evidence.agent_id in by_agent:
                raise ValueError(f"duplicate agent evidence: {evidence.agent_id}")
            by_agent[evidence.agent_id] = evidence
        return tuple(self.recommend(by_agent[agent_id]) for agent_id in sorted(by_agent))

    def _has_minimum_evidence(self, evidence: AgentStateEvidence) -> bool:
        return (
            evidence.evaluation_sample_count >= self._thresholds.min_evaluation_samples
            and evidence.ablation_comparison_count >= self._thresholds.min_ablation_comparisons
        )

    def _demotion_reasons(self, evidence: AgentStateEvidence) -> tuple[str, ...]:
        reasons: list[str] = []
        harmful_ratio = evidence.harmful_ratio
        if (
            harmful_ratio is not None
            and harmful_ratio >= self._thresholds.demotion_harmful_ratio
        ):
            reasons.append("ABLATION_CONSISTENTLY_HARMFUL")
        contribution = evidence.economic_net_contribution_eur
        if (
            contribution is not None
            and contribution < -self._thresholds.min_economic_net_contribution_eur
        ):
            reasons.append("NEGATIVE_ECONOMIC_NET_CONTRIBUTION")
        drawdown_reduction = evidence.drawdown_reduction_pct
        if (
            drawdown_reduction is not None
            and drawdown_reduction < -self._thresholds.max_drawdown_increase_pct
        ):
            reasons.append("DRAWDOWN_WORSENING_ABOVE_POLICY")
        return tuple(reasons)

    def _cost_pressure(self, evidence: AgentStateEvidence) -> bool:
        return (
            evidence.ai_cost_share_pct is not None
            and evidence.ai_cost_share_pct > self._thresholds.max_ai_cost_share_pct
        )

    def _promotion_reasons(self, evidence: AgentStateEvidence) -> tuple[str, ...]:
        beneficial_ratio = evidence.beneficial_ratio
        if beneficial_ratio is None:
            return ()
        if beneficial_ratio < self._thresholds.promotion_beneficial_ratio:
            return ()

        contribution = evidence.economic_net_contribution_eur
        if contribution is None:
            return ()
        if contribution < self._thresholds.min_economic_net_contribution_eur:
            return ()

        drawdown_reduction = evidence.drawdown_reduction_pct
        if (
            drawdown_reduction is not None
            and drawdown_reduction < -self._thresholds.max_drawdown_increase_pct
        ):
            return ()

        return ("ABLATION_CONSISTENTLY_BENEFICIAL", "ECONOMIC_NET_CONTRIBUTION_ACCEPTABLE")

    def _hold(
        self,
        evidence: AgentStateEvidence,
        sufficiency: EvidenceSufficiency,
        *reason_codes: str,
    ) -> AgentStateRecommendation:
        return self._build(
            evidence,
            evidence.current_state,
            StateRecommendationAction.HOLD,
            sufficiency,
            tuple(reason_codes),
        )

    def _build(
        self,
        evidence: AgentStateEvidence,
        recommended_state: AgentState,
        action: StateRecommendationAction,
        sufficiency: EvidenceSufficiency,
        reason_codes: tuple[str, ...],
    ) -> AgentStateRecommendation:
        return AgentStateRecommendation(
            policy_version=self.policy_version,
            agent_id=evidence.agent_id,
            current_state=evidence.current_state,
            recommended_state=recommended_state,
            action=action,
            evidence_sufficiency=sufficiency,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
        )


def _promote_one_step(state: AgentState) -> AgentState:
    transitions = {
        AgentState.SHADOW: AgentState.PROBATION,
        AgentState.PROBATION: AgentState.ON_DEMAND,
        AgentState.ON_DEMAND: AgentState.ACTIVE,
        AgentState.ACTIVE: AgentState.ACTIVE,
        AgentState.DISABLED: AgentState.DISABLED,
    }
    return transitions[state]


def _demote_one_step(state: AgentState) -> AgentState:
    transitions = {
        AgentState.ACTIVE: AgentState.ON_DEMAND,
        AgentState.ON_DEMAND: AgentState.SHADOW,
        AgentState.PROBATION: AgentState.SHADOW,
        AgentState.SHADOW: AgentState.SHADOW,
        AgentState.DISABLED: AgentState.DISABLED,
    }
    return transitions[state]


def _reduce_frequency(state: AgentState) -> AgentState:
    if state is AgentState.ACTIVE:
        return AgentState.ON_DEMAND
    return state


def _require_ratio(name: str, value: Decimal) -> None:
    if not (ZERO <= value <= ONE):
        raise ValueError(f"{name} must be between 0 and 1")
