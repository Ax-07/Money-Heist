from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.evaluation.ablation import AblationAggregate, aggregate_ablation
from app.evaluation.models import AgentMetrics, Metric
from app.evaluation.reputation import build_agent_reputation
from app.services.backtest.ids import stable_digest

from .ablation_bridge import RecruitmentAblationBridgeResult, bridge_recruitment_to_ablation
from .campaign import RecruitmentCampaignPlan, candidate_runtime_agent_id
from .campaign_execution import RecruitmentCampaignExecutionReport
from .evidence_gate import RecruitmentEvidenceGateDecision, RecruitmentEvidencePurpose
from .models import RecruitmentCandidateSpec

ZERO = Decimal("0")


class RecruitmentReputationBasis(StrEnum):
    BATCH18_REPUTATION_DIMENSIONS = "BATCH18_REPUTATION_DIMENSIONS"


class RecruitmentCostEvidenceBasis(StrEnum):
    ESTIMATED_AI_USAGE_EUR_IN_SIMULATED_HISTORICAL_REPLAY_PAPER = (
        "ESTIMATED_AI_USAGE_EUR_IN_SIMULATED_HISTORICAL_REPLAY_PAPER"
    )


@dataclass(frozen=True, slots=True)
class RecruitmentCandidateReputationDimensions:
    """Batch 18 reputation dimensions with operational state advice deliberately omitted."""

    candidate_agent_id: str
    call_count: int
    ablation_comparison_count: int
    oos_ablation_comparison_count: int
    participation_frequency: Metric
    directional_agreement: Metric
    average_confidence: Metric
    average_cost_eur: Metric
    average_latency_ms: Metric
    marginal_trading_net: Metric
    marginal_economic_net: Metric
    drawdown_reduction_pct: Metric
    basis: RecruitmentReputationBasis = RecruitmentReputationBasis.BATCH18_REPUTATION_DIMENSIONS
    operational_state_advisory_used: bool = False

    def __post_init__(self) -> None:
        if not self.candidate_agent_id.strip():
            raise ValueError("candidate_agent_id must not be blank")
        if self.call_count < 0:
            raise ValueError("call_count must be >= 0")
        if self.ablation_comparison_count < 0 or self.oos_ablation_comparison_count < 0:
            raise ValueError("ablation comparison counts must be >= 0")
        if self.oos_ablation_comparison_count > self.ablation_comparison_count:
            raise ValueError("OOS ablation count cannot exceed total ablation count")
        if self.operational_state_advisory_used:
            raise ValueError("candidate evidence cannot use Batch 18 operational state advice")


@dataclass(frozen=True, slots=True)
class RecruitmentCandidateCostEvidence:
    """Keep direct candidate cost distinct from system-level marginal AI cost."""

    candidate_direct_ai_cost_eur: Decimal
    with_candidate_total_ai_cost_eur: Decimal
    baseline_total_ai_cost_eur: Decimal
    marginal_total_ai_cost_eur: Decimal
    candidate_direct_cost_share_ratio: Decimal
    candidate_budget_limit_eur: Decimal
    candidate_budget_utilization_ratio: Decimal
    candidate_direct_cost_within_budget: bool
    basis: RecruitmentCostEvidenceBasis = (
        RecruitmentCostEvidenceBasis.ESTIMATED_AI_USAGE_EUR_IN_SIMULATED_HISTORICAL_REPLAY_PAPER
    )

    def __post_init__(self) -> None:
        for field_name in (
            "candidate_direct_ai_cost_eur",
            "with_candidate_total_ai_cost_eur",
            "baseline_total_ai_cost_eur",
            "candidate_direct_cost_share_ratio",
            "candidate_budget_limit_eur",
            "candidate_budget_utilization_ratio",
        ):
            value = getattr(self, field_name)
            if not value.is_finite():
                raise ValueError(f"{field_name} must be finite")
        if not self.marginal_total_ai_cost_eur.is_finite():
            raise ValueError("marginal_total_ai_cost_eur must be finite")
        if self.candidate_direct_ai_cost_eur < ZERO:
            raise ValueError("candidate_direct_ai_cost_eur must be >= 0")
        if self.with_candidate_total_ai_cost_eur < ZERO or self.baseline_total_ai_cost_eur < ZERO:
            raise ValueError("total AI costs must be >= 0")
        if self.candidate_budget_limit_eur <= ZERO:
            raise ValueError("candidate_budget_limit_eur must be > 0")
        if self.candidate_direct_cost_share_ratio < ZERO:
            raise ValueError("candidate_direct_cost_share_ratio must be >= 0")
        if self.candidate_budget_utilization_ratio < ZERO:
            raise ValueError("candidate_budget_utilization_ratio must be >= 0")


@dataclass(frozen=True, slots=True)
class RecruitmentCandidateReputationEvidenceReport:
    """Audited candidate evidence only; this report has no promotion or registry authority."""

    recruitment_id: str
    candidate_agent_id: str
    purpose: RecruitmentEvidencePurpose
    evaluation_report_version: str
    evidence_gate_fingerprint_sha256: str
    ablation_bridge_fingerprint_sha256: str
    candidate_metrics: AgentMetrics
    ablation_aggregate: AblationAggregate
    reputation: RecruitmentCandidateReputationDimensions
    costs: RecruitmentCandidateCostEvidence
    audit_fingerprint_sha256: str
    report_version: str = "batch19.candidate-reputation-evidence.v1"
    auto_apply: bool = False
    registry_mutation: bool = False
    promotion_action: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "recruitment_id",
            "candidate_agent_id",
            "evaluation_report_version",
            "evidence_gate_fingerprint_sha256",
            "ablation_bridge_fingerprint_sha256",
            "audit_fingerprint_sha256",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be blank")
        for field_name in (
            "evidence_gate_fingerprint_sha256",
            "ablation_bridge_fingerprint_sha256",
            "audit_fingerprint_sha256",
        ):
            if len(getattr(self, field_name)) != 64:
                raise ValueError(f"{field_name} must be a SHA-256 hex digest")
        ids = {
            self.candidate_agent_id,
            self.candidate_metrics.agent_id,
            self.ablation_aggregate.agent_id,
            self.reputation.candidate_agent_id,
        }
        if len(ids) != 1:
            raise ValueError("candidate metrics, reputation and ablation must target one candidate")
        if self.auto_apply or self.registry_mutation or self.promotion_action or self.live_authority:
            raise ValueError("candidate reputation evidence cannot apply operational changes")


def _evaluation_report(execution_variant: Any) -> Any:
    bundle = getattr(execution_variant, "evaluation_bundle", None)
    report = getattr(bundle, "report", None)
    if report is None:
        raise ValueError("recruitment execution is missing Batch 10 evaluation report")
    return report


def _candidate_metrics(report: Any, *, candidate_agent_id: str) -> AgentMetrics:
    agents = tuple(getattr(report, "agents", ()) or ())
    matches = tuple(item for item in agents if getattr(item, "agent_id", None) == candidate_agent_id)
    if len(matches) != 1:
        raise ValueError("WITH_CANDIDATE evaluation must contain exactly one candidate AgentMetrics")
    metrics = matches[0]
    if not isinstance(metrics, AgentMetrics):
        raise TypeError("candidate evaluation metric must be AgentMetrics")
    return metrics


def _assert_candidate_absent_from_baseline(report: Any, *, candidate_agent_id: str) -> None:
    agents = tuple(getattr(report, "agents", ()) or ())
    if any(getattr(item, "agent_id", None) == candidate_agent_id for item in agents):
        raise ValueError("recruitment BASELINE evaluation must not contain candidate AgentMetrics")
    by_agent = getattr(getattr(report, "ai_costs", None), "by_agent", {}) or {}
    baseline_candidate_cost = Decimal(str(by_agent.get(candidate_agent_id, ZERO)))
    if baseline_candidate_cost != ZERO:
        raise ValueError("recruitment BASELINE must not attribute AI cost to candidate")


def _ai_costs(report: Any) -> tuple[Decimal, Any]:
    ai_costs = getattr(report, "ai_costs", None)
    if ai_costs is None:
        raise ValueError("evaluation report is missing ai_costs")
    total = Decimal(str(getattr(ai_costs, "total_cost_eur", ZERO)))
    if not total.is_finite() or total < ZERO:
        raise ValueError("evaluation total AI cost must be finite and >= 0")
    return total, ai_costs


def _reputation_dimensions(
    metrics: AgentMetrics,
    aggregate: AblationAggregate,
) -> RecruitmentCandidateReputationDimensions:
    # Reuse Batch 18's dimension normalization, but deliberately do not expose its
    # AgentState-oriented advice because recruitment has a separate lifecycle.
    profile = build_agent_reputation(metrics, ablation=aggregate)
    return RecruitmentCandidateReputationDimensions(
        candidate_agent_id=profile.agent_id,
        call_count=profile.call_count,
        ablation_comparison_count=profile.ablation_comparison_count,
        oos_ablation_comparison_count=profile.oos_ablation_comparison_count,
        participation_frequency=profile.participation_frequency,
        directional_agreement=profile.directional_agreement,
        average_confidence=profile.average_confidence,
        average_cost_eur=profile.average_cost_eur,
        average_latency_ms=profile.average_latency_ms,
        marginal_trading_net=profile.marginal_trading_net,
        marginal_economic_net=profile.marginal_economic_net,
        drawdown_reduction_pct=profile.drawdown_reduction_pct,
    )


def build_candidate_reputation_evidence(
    plan: RecruitmentCampaignPlan,
    candidate: RecruitmentCandidateSpec,
    execution: RecruitmentCampaignExecutionReport,
    evidence_gate: RecruitmentEvidenceGateDecision,
    ablation_bridge: RecruitmentAblationBridgeResult,
) -> RecruitmentCandidateReputationEvidenceReport:
    """Combine one verified recruitment comparison with Batch 18 reputation dimensions.

    This is evidence construction only. It does not evaluate the frozen recruitment
    success criteria, does not recommend a lifecycle transition, and never creates or
    mutates an AgentRegistryEntry.
    """

    expected_bridge = bridge_recruitment_to_ablation(
        plan,
        candidate,
        execution,
        evidence_gate,
    )
    if expected_bridge.audit_fingerprint_sha256 != ablation_bridge.audit_fingerprint_sha256:
        raise ValueError("recruitment ablation bridge is stale or does not match execution")
    if expected_bridge != ablation_bridge:
        raise ValueError("recruitment ablation bridge payload does not match recomputed bridge")

    candidate_id = candidate_runtime_agent_id(candidate)
    if candidate_id != plan.candidate_agent_id or candidate_id != ablation_bridge.candidate_agent_id:
        raise ValueError("candidate runtime identity mismatch")

    baseline_report = _evaluation_report(execution.baseline)
    with_candidate_report = _evaluation_report(execution.with_candidate)
    baseline_version = str(getattr(baseline_report, "report_version", "")).strip()
    candidate_version = str(getattr(with_candidate_report, "report_version", "")).strip()
    if not baseline_version or not candidate_version:
        raise ValueError("evaluation report_version must not be blank")
    if baseline_version != candidate_version:
        raise ValueError("recruitment twins must use the same evaluation report version")

    _assert_candidate_absent_from_baseline(
        baseline_report,
        candidate_agent_id=candidate_id,
    )
    metrics = _candidate_metrics(with_candidate_report, candidate_agent_id=candidate_id)

    baseline_total, _ = _ai_costs(baseline_report)
    with_total, with_ai_costs = _ai_costs(with_candidate_report)
    if baseline_total != execution.baseline.period_report.ai_cost_eur:
        raise ValueError("BASELINE evaluation AI cost does not match period report")
    if with_total != execution.with_candidate.period_report.ai_cost_eur:
        raise ValueError("WITH_CANDIDATE evaluation AI cost does not match period report")

    by_agent = getattr(with_ai_costs, "by_agent", {}) or {}
    direct_cost = Decimal(str(by_agent.get(candidate_id, ZERO)))
    if direct_cost != metrics.total_cost_eur:
        raise ValueError("candidate AgentMetrics cost does not match ai_costs.by_agent")
    if direct_cost > with_total:
        raise ValueError("candidate direct AI cost cannot exceed WITH_CANDIDATE total AI cost")

    marginal_total = with_total - baseline_total
    if marginal_total != ablation_bridge.comparison.additional_ai_cost_eur:
        raise ValueError("marginal AI cost does not match Batch 18 ablation comparison")

    aggregate = aggregate_ablation((ablation_bridge.comparison,))
    reputation = _reputation_dimensions(metrics, aggregate)

    direct_share = ZERO if with_total == ZERO else direct_cost / with_total
    budget_limit = candidate.budget_limit_eur
    budget_utilization = direct_cost / budget_limit
    costs = RecruitmentCandidateCostEvidence(
        candidate_direct_ai_cost_eur=direct_cost,
        with_candidate_total_ai_cost_eur=with_total,
        baseline_total_ai_cost_eur=baseline_total,
        marginal_total_ai_cost_eur=marginal_total,
        candidate_direct_cost_share_ratio=direct_share,
        candidate_budget_limit_eur=budget_limit,
        candidate_budget_utilization_ratio=budget_utilization,
        candidate_direct_cost_within_budget=direct_cost <= budget_limit,
    )

    fingerprint = stable_digest(
        {
            "schema": "money-heist.candidate-reputation-evidence.v1",
            "recruitment_id": plan.recruitment_id,
            "candidate_agent_id": candidate_id,
            "purpose": evidence_gate.purpose,
            "evaluation_report_version": candidate_version,
            "evidence_gate_fingerprint_sha256": evidence_gate.audit_fingerprint_sha256,
            "ablation_bridge_fingerprint_sha256": ablation_bridge.audit_fingerprint_sha256,
            "candidate_metrics": metrics,
            "ablation_aggregate": aggregate,
            "reputation": reputation,
            "costs": costs,
            "auto_apply": False,
            "registry_mutation": False,
            "promotion_action": False,
            "live_authority": False,
        }
    )
    return RecruitmentCandidateReputationEvidenceReport(
        recruitment_id=plan.recruitment_id,
        candidate_agent_id=candidate_id,
        purpose=evidence_gate.purpose,
        evaluation_report_version=candidate_version,
        evidence_gate_fingerprint_sha256=evidence_gate.audit_fingerprint_sha256,
        ablation_bridge_fingerprint_sha256=ablation_bridge.audit_fingerprint_sha256,
        candidate_metrics=metrics,
        ablation_aggregate=aggregate,
        reputation=reputation,
        costs=costs,
        audit_fingerprint_sha256=fingerprint,
    )


__all__ = [
    "RecruitmentCandidateCostEvidence",
    "RecruitmentCandidateReputationDimensions",
    "RecruitmentCandidateReputationEvidenceReport",
    "RecruitmentCostEvidenceBasis",
    "RecruitmentReputationBasis",
    "build_candidate_reputation_evidence",
]
