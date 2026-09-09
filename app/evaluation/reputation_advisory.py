from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from app.agents.models import AgentRegistryEntry

from .ablation import AblationAggregate, AblationComparison, aggregate_ablation
from .models import AgentMetrics, Metric, MetricStatus
from .reputation import (
    AgentReputationProfile,
    ReputationPolicy,
    build_agent_reputation,
)
from .reputation_policy import (
    AgentStateEvidence,
    AgentStateRecommendation,
    DeterministicAgentStateAdvisor,
    ReputationPolicyThresholds,
)

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class ReputationEvidenceProvenance:
    evaluation_report_version: str
    evaluation_sample_basis: str
    economic_contribution_basis: str
    ai_cost_share_basis: str
    comparison_fingerprints: tuple[str, ...]
    baseline_run_ids: tuple[str, ...]
    ablated_run_ids: tuple[str, ...]
    dataset_ids: tuple[str, ...]
    period_roles: tuple[str, ...]
    comparison_count: int
    oos_comparison_count: int

    def __post_init__(self) -> None:
        if not self.evaluation_report_version.strip():
            raise ValueError("evaluation_report_version must not be blank")
        if self.comparison_count < 0 or self.oos_comparison_count < 0:
            raise ValueError("comparison counts must be >= 0")
        if self.oos_comparison_count > self.comparison_count:
            raise ValueError("oos_comparison_count cannot exceed comparison_count")


@dataclass(frozen=True, slots=True)
class AgentReputationAdvisoryReport:
    report_version: str
    agent_id: str
    reputation_policy: ReputationPolicy
    state_policy_thresholds: ReputationPolicyThresholds
    provenance: ReputationEvidenceProvenance
    reputation: AgentReputationProfile
    evidence: AgentStateEvidence
    recommendation: AgentStateRecommendation
    audit_fingerprint_sha256: str
    auto_apply: bool = False

    def __post_init__(self) -> None:
        if self.auto_apply:
            raise ValueError("Batch 18 advisory reports can never auto-apply state changes")
        if not self.audit_fingerprint_sha256 or len(self.audit_fingerprint_sha256) != 64:
            raise ValueError("audit_fingerprint_sha256 must be a SHA-256 hex digest")
        ids = {
            self.agent_id,
            self.reputation.agent_id,
            self.evidence.agent_id,
            self.recommendation.agent_id,
        }
        if len(ids) != 1:
            raise ValueError("advisory report contains mismatched agent ids")


def build_agent_state_evidence(
    profile: AgentReputationProfile,
    *,
    metrics: AgentMetrics,
    registry_entry: AgentRegistryEntry,
    ablation: AblationAggregate | None,
    total_ai_cost_eur: Decimal,
) -> AgentStateEvidence:
    """Adapt Step 1 outputs into the Step 2 policy contract without inventing evidence."""

    _validate_agent_identity(profile, metrics, registry_entry, ablation)
    if total_ai_cost_eur < ZERO:
        raise ValueError("total_ai_cost_eur must be >= 0")
    if metrics.total_cost_eur > total_ai_cost_eur:
        raise ValueError("agent AI cost cannot exceed total AI cost for the same scope")

    if ablation is not None and ablation.oos_comparison_count != ablation.comparison_count:
        raise ValueError(
            "state evidence requires an OOS-only ablation aggregate; "
            "mixed DESIGN/VALIDATION/OOS evidence is not promotable"
        )

    if ablation is None:
        beneficial = 0
        harmful = 0
        inconclusive = 0
        comparison_count = 0
    else:
        beneficial = ablation.positive_economic_count
        harmful = ablation.negative_economic_count
        comparison_count = ablation.comparison_count
        inconclusive = comparison_count - beneficial - harmful
        if inconclusive < 0:
            raise ValueError("ablation classification counts are inconsistent")

    return AgentStateEvidence(
        agent_id=profile.agent_id,
        current_state=registry_entry.state,
        core=registry_entry.core,
        evaluation_sample_count=profile.call_count,
        ablation_comparison_count=comparison_count,
        beneficial_ablation_count=beneficial,
        harmful_ablation_count=harmful,
        inconclusive_ablation_count=inconclusive,
        economic_net_contribution_eur=_metric_value(profile.marginal_economic_net),
        drawdown_reduction_pct=_metric_value(profile.drawdown_reduction_pct),
        ai_cost_share_pct=_ai_cost_share(metrics.total_cost_eur, total_ai_cost_eur),
    )


class ReputationAdvisoryService:
    """Bridge Step 1 reputation/ablation evidence to Step 2 advisory recommendations."""

    report_version = "batch18.reputation-advisory.v1"

    def __init__(
        self,
        *,
        reputation_policy: ReputationPolicy,
        state_policy_thresholds: ReputationPolicyThresholds,
    ) -> None:
        self._reputation_policy = reputation_policy
        self._state_policy_thresholds = state_policy_thresholds
        self._advisor = DeterministicAgentStateAdvisor(state_policy_thresholds)

    def build(
        self,
        *,
        metrics: AgentMetrics,
        registry_entry: AgentRegistryEntry,
        comparisons: tuple[AblationComparison, ...] = (),
        total_ai_cost_eur: Decimal,
        evaluation_report_version: str,
    ) -> AgentReputationAdvisoryReport:
        ordered = _normalize_comparisons(comparisons, agent_id=metrics.agent_id)
        ablation = aggregate_ablation(ordered) if ordered else None
        profile = build_agent_reputation(
            metrics,
            ablation=ablation,
            policy=self._reputation_policy,
        )
        evidence = build_agent_state_evidence(
            profile,
            metrics=metrics,
            registry_entry=registry_entry,
            ablation=ablation,
            total_ai_cost_eur=total_ai_cost_eur,
        )
        recommendation = self._advisor.recommend(evidence)
        provenance = _build_provenance(
            ordered,
            evaluation_report_version=evaluation_report_version,
        )
        fingerprint = _fingerprint(
            profile=profile,
            evidence=evidence,
            recommendation=recommendation,
            provenance=provenance,
            reputation_policy=self._reputation_policy,
            state_policy_thresholds=self._state_policy_thresholds,
        )
        return AgentReputationAdvisoryReport(
            report_version=self.report_version,
            agent_id=metrics.agent_id,
            reputation_policy=self._reputation_policy,
            state_policy_thresholds=self._state_policy_thresholds,
            provenance=provenance,
            reputation=profile,
            evidence=evidence,
            recommendation=recommendation,
            audit_fingerprint_sha256=fingerprint,
        )


def _validate_agent_identity(
    profile: AgentReputationProfile,
    metrics: AgentMetrics,
    registry_entry: AgentRegistryEntry,
    ablation: AblationAggregate | None,
) -> None:
    ids = {profile.agent_id, metrics.agent_id, registry_entry.agent_id}
    if ablation is not None:
        ids.add(ablation.agent_id)
    if len(ids) != 1:
        raise ValueError("reputation, metrics, registry and ablation must target one agent")
    if profile.call_count != metrics.call_count:
        raise ValueError("reputation call_count must match AgentMetrics.call_count")
    expected_comparisons = 0 if ablation is None else ablation.comparison_count
    expected_oos = 0 if ablation is None else ablation.oos_comparison_count
    if profile.ablation_comparison_count != expected_comparisons:
        raise ValueError("reputation ablation count does not match aggregate")
    if profile.oos_ablation_comparison_count != expected_oos:
        raise ValueError("reputation OOS ablation count does not match aggregate")


def _metric_value(metric: Metric) -> Decimal | None:
    if metric.status is not MetricStatus.AVAILABLE:
        return None
    return metric.value


def _ai_cost_share(agent_cost: Decimal, total_cost: Decimal) -> Decimal | None:
    if total_cost == ZERO:
        if agent_cost != ZERO:
            raise ValueError("non-zero agent cost with zero total AI cost is inconsistent")
        return ZERO
    return agent_cost / total_cost


def _normalize_comparisons(
    comparisons: tuple[AblationComparison, ...],
    *,
    agent_id: str,
) -> tuple[AblationComparison, ...]:
    seen: set[tuple[str, str]] = set()
    for comparison in comparisons:
        if comparison.agent_id != agent_id:
            raise ValueError("all ablation comparisons must target metrics.agent_id")
        key = (comparison.baseline_run_id, comparison.ablated_run_id)
        if key in seen:
            raise ValueError("duplicate ablation run pair")
        seen.add(key)
    return tuple(
        sorted(
            comparisons,
            key=lambda item: (
                item.dataset_id,
                item.role,
                str(item.period_start),
                item.baseline_run_id,
                item.ablated_run_id,
            ),
        )
    )


def _build_provenance(
    comparisons: tuple[AblationComparison, ...],
    *,
    evaluation_report_version: str,
) -> ReputationEvidenceProvenance:
    return ReputationEvidenceProvenance(
        evaluation_report_version=evaluation_report_version,
        evaluation_sample_basis="AGENT_CALL_COUNT",
        economic_contribution_basis="MEAN_MARGINAL_ECONOMIC_NET_PER_OOS_COMPARISON",
        ai_cost_share_basis="AGENT_AI_COST_DIVIDED_BY_TOTAL_AI_COST_SAME_SCOPE",
        comparison_fingerprints=tuple(
            sorted({item.comparison_fingerprint for item in comparisons})
        ),
        baseline_run_ids=tuple(item.baseline_run_id for item in comparisons),
        ablated_run_ids=tuple(item.ablated_run_id for item in comparisons),
        dataset_ids=tuple(sorted({item.dataset_id for item in comparisons})),
        period_roles=tuple(sorted({item.role for item in comparisons})),
        comparison_count=len(comparisons),
        oos_comparison_count=sum(item.is_out_of_sample for item in comparisons),
    )


def _fingerprint(
    *,
    profile: AgentReputationProfile,
    evidence: AgentStateEvidence,
    recommendation: AgentStateRecommendation,
    provenance: ReputationEvidenceProvenance,
    reputation_policy: ReputationPolicy,
    state_policy_thresholds: ReputationPolicyThresholds,
) -> str:
    payload = {
        "agent_id": profile.agent_id,
        "reputation_policy": {
            "min_calls": reputation_policy.min_calls,
            "min_oos_ablation_comparisons": reputation_policy.min_oos_ablation_comparisons,
            "max_allowed_drawdown_worsening_pct": str(
                reputation_policy.max_allowed_drawdown_worsening_pct
            ),
        },
        "state_policy_thresholds": {
            "min_evaluation_samples": state_policy_thresholds.min_evaluation_samples,
            "min_ablation_comparisons": state_policy_thresholds.min_ablation_comparisons,
            "promotion_beneficial_ratio": str(
                state_policy_thresholds.promotion_beneficial_ratio
            ),
            "demotion_harmful_ratio": str(state_policy_thresholds.demotion_harmful_ratio),
            "min_economic_net_contribution_eur": str(
                state_policy_thresholds.min_economic_net_contribution_eur
            ),
            "max_drawdown_increase_pct": str(
                state_policy_thresholds.max_drawdown_increase_pct
            ),
            "max_ai_cost_share_pct": str(state_policy_thresholds.max_ai_cost_share_pct),
        },
        "provenance": {
            "evaluation_report_version": provenance.evaluation_report_version,
            "comparison_fingerprints": provenance.comparison_fingerprints,
            "baseline_run_ids": provenance.baseline_run_ids,
            "ablated_run_ids": provenance.ablated_run_ids,
            "dataset_ids": provenance.dataset_ids,
            "period_roles": provenance.period_roles,
            "comparison_count": provenance.comparison_count,
            "oos_comparison_count": provenance.oos_comparison_count,
        },
        "evidence": {
            "current_state": evidence.current_state.value,
            "core": evidence.core,
            "evaluation_sample_count": evidence.evaluation_sample_count,
            "ablation_comparison_count": evidence.ablation_comparison_count,
            "beneficial_ablation_count": evidence.beneficial_ablation_count,
            "harmful_ablation_count": evidence.harmful_ablation_count,
            "inconclusive_ablation_count": evidence.inconclusive_ablation_count,
            "economic_net_contribution_eur": _decimal_or_none(
                evidence.economic_net_contribution_eur
            ),
            "drawdown_reduction_pct": _decimal_or_none(evidence.drawdown_reduction_pct),
            "ai_cost_share_pct": _decimal_or_none(evidence.ai_cost_share_pct),
        },
        "recommendation": {
            "policy_version": recommendation.policy_version,
            "recommended_state": recommendation.recommended_state.value,
            "action": recommendation.action.value,
            "evidence_sufficiency": recommendation.evidence_sufficiency.value,
            "reason_codes": recommendation.reason_codes,
            "auto_apply": recommendation.auto_apply,
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _decimal_or_none(value: Decimal | None) -> str | None:
    return None if value is None else str(value)
