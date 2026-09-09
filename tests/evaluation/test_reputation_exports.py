from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from app.agents.models import AgentState
from app.evaluation.models import Metric
from app.evaluation.reputation import AgentReputationProfile, ReputationPolicy
from app.evaluation.reputation_advisory import (
    AgentReputationAdvisoryReport,
    ReputationEvidenceProvenance,
)
from app.evaluation.reputation_exports import (
    reputation_advisory_to_dict,
    reputation_advisory_to_json,
)
from app.evaluation.reputation_policy import (
    AgentStateEvidence,
    AgentStateRecommendation,
    EvidenceSufficiency,
    ReputationPolicyThresholds,
    StateRecommendationAction,
)


@dataclass(frozen=True)
class _Fixture:
    report: AgentReputationAdvisoryReport


def _report() -> AgentReputationAdvisoryReport:
    thresholds = ReputationPolicyThresholds(
        min_evaluation_samples=10,
        min_ablation_comparisons=3,
        promotion_beneficial_ratio=Decimal("0.75"),
        demotion_harmful_ratio=Decimal("0.75"),
        min_economic_net_contribution_eur=Decimal("1"),
        max_drawdown_increase_pct=Decimal("0.02"),
        max_ai_cost_share_pct=Decimal("0.40"),
    )
    profile = AgentReputationProfile(
        agent_id="denver",
        call_count=12,
        ablation_comparison_count=4,
        oos_ablation_comparison_count=4,
        participation_frequency=Metric.available(Decimal("0.50")),
        directional_agreement=Metric.available(Decimal("0.75")),
        average_confidence=Metric.available(Decimal("0.70")),
        average_cost_eur=Metric.available(Decimal("0.10")),
        average_latency_ms=Metric.available(Decimal("150")),
        marginal_trading_net=Metric.available(Decimal("2.0")),
        marginal_economic_net=Metric.available(Decimal("1.5")),
        drawdown_reduction_pct=Metric.available(Decimal("0.01")),
        suggested_state=AgentState.PROBATION,
        state_reasons=("POSITIVE_OOS_MARGINAL_ECONOMIC_NET",),
    )
    evidence = AgentStateEvidence(
        agent_id="denver",
        current_state=AgentState.ON_DEMAND,
        core=False,
        evaluation_sample_count=12,
        ablation_comparison_count=4,
        beneficial_ablation_count=3,
        harmful_ablation_count=1,
        inconclusive_ablation_count=0,
        economic_net_contribution_eur=Decimal("1.5"),
        drawdown_reduction_pct=Decimal("0.01"),
        ai_cost_share_pct=Decimal("0.20"),
    )
    recommendation = AgentStateRecommendation(
        policy_version="batch18.reputation-state-policy.v1",
        agent_id="denver",
        current_state=AgentState.ON_DEMAND,
        recommended_state=AgentState.ACTIVE,
        action=StateRecommendationAction.PROMOTE,
        evidence_sufficiency=EvidenceSufficiency.SUFFICIENT,
        reason_codes=("ABLATION_CONSISTENTLY_BENEFICIAL",),
    )
    provenance = ReputationEvidenceProvenance(
        evaluation_report_version="batch10.evaluation.v1",
        evaluation_sample_basis="AGENT_CALL_COUNT",
        economic_contribution_basis="MEAN_MARGINAL_ECONOMIC_NET_PER_OOS_COMPARISON",
        ai_cost_share_basis="AGENT_AI_COST_DIVIDED_BY_TOTAL_AI_COST_SAME_SCOPE",
        comparison_fingerprints=("fp-a", "fp-b"),
        baseline_run_ids=("base-a", "base-b"),
        ablated_run_ids=("abl-a", "abl-b"),
        dataset_ids=("dataset-1",),
        period_roles=("OOS",),
        comparison_count=4,
        oos_comparison_count=4,
    )
    return AgentReputationAdvisoryReport(
        report_version="batch18.reputation-advisory.v1",
        agent_id="denver",
        reputation_policy=ReputationPolicy(
            min_calls=10,
            min_oos_ablation_comparisons=3,
            max_allowed_drawdown_worsening_pct=Decimal("0.02"),
        ),
        state_policy_thresholds=thresholds,
        provenance=provenance,
        reputation=profile,
        evidence=evidence,
        recommendation=recommendation,
        audit_fingerprint_sha256="a" * 64,
    )


def test_advisory_to_dict_is_json_safe_and_preserves_decimal_precision() -> None:
    payload = reputation_advisory_to_dict(_report())

    assert payload["agent_id"] == "denver"
    assert payload["evidence"]["economic_net_contribution_eur"] == "1.5"
    assert payload["evidence"]["current_state"] == "ON_DEMAND"
    assert payload["recommendation"]["action"] == "PROMOTE"
    assert payload["recommendation"]["auto_apply"] is False
    json.dumps(payload)


def test_advisory_json_is_deterministic() -> None:
    report = _report()
    first = reputation_advisory_to_json(report, indent=None)
    second = reputation_advisory_to_json(report, indent=None)

    assert first == second
    assert json.loads(first)["audit_fingerprint_sha256"] == "a" * 64


def test_export_does_not_mutate_report() -> None:
    report = _report()
    before = report.audit_fingerprint_sha256

    reputation_advisory_to_dict(report)
    reputation_advisory_to_json(report)

    assert report.audit_fingerprint_sha256 == before
    assert report.auto_apply is False
