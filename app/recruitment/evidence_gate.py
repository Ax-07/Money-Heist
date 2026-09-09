from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.services.backtest.ids import stable_digest
from app.services.backtest.splits import BacktestPeriodRole

from .campaign import RecruitmentCampaignPlan, candidate_runtime_agent_id
from .campaign_execution import RecruitmentCampaignExecutionReport
from .gates import RecruitmentGateStatus
from .models import RecruitmentCandidateSpec

_RECRUITMENT_EXECUTION_KEYS = frozenset(
    {
        "recruitment_campaign_id",
        "recruitment_comparison_fingerprint",
        "recruitment_variant",
        "recruitment_candidate_agent_id",
        "recruitment_included_agents",
        "recruitment_period_role",
        "recruitment_baseline_id",
    }
)


class RecruitmentEvidencePurpose(StrEnum):
    DIAGNOSTIC = "DIAGNOSTIC"
    PROMOTION = "PROMOTION"


class RecruitmentEvidenceBasis(StrEnum):
    SIMULATED_HISTORICAL_REPLAY_PAPER = "SIMULATED_HISTORICAL_REPLAY_PAPER"


@dataclass(frozen=True, slots=True)
class RecruitmentEvidenceProvenance:
    """Exact provenance for one executed baseline-vs-candidate twin comparison."""

    campaign_id: str
    recruitment_id: str
    baseline_id: str
    source_run_id: str
    comparison_fingerprint: str
    execution_fingerprint: str
    success_criteria_fingerprint: str
    candidate_agent_id: str
    baseline_run_id: str
    candidate_run_id: str
    baseline_dataset_id: str
    candidate_dataset_id: str
    baseline_role: BacktestPeriodRole
    candidate_role: BacktestPeriodRole
    baseline_period_start: object
    candidate_period_start: object
    baseline_period_end: object
    candidate_period_end: object
    baseline_processed_candles: int
    candidate_processed_candles: int
    baseline_opportunity_count: int
    candidate_opportunity_count: int
    baseline_business_sha256: str
    candidate_business_sha256: str
    baseline_agents: tuple[str, ...]
    candidate_agents: tuple[str, ...]
    evidence_basis: RecruitmentEvidenceBasis = (
        RecruitmentEvidenceBasis.SIMULATED_HISTORICAL_REPLAY_PAPER
    )

    def __post_init__(self) -> None:
        for field_name in (
            "campaign_id",
            "recruitment_id",
            "baseline_id",
            "source_run_id",
            "comparison_fingerprint",
            "execution_fingerprint",
            "success_criteria_fingerprint",
            "candidate_agent_id",
            "baseline_run_id",
            "candidate_run_id",
            "baseline_dataset_id",
            "candidate_dataset_id",
            "baseline_business_sha256",
            "candidate_business_sha256",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be blank")
        if self.baseline_processed_candles < 0 or self.candidate_processed_candles < 0:
            raise ValueError("processed candle counts must be >= 0")
        if self.baseline_opportunity_count < 0 or self.candidate_opportunity_count < 0:
            raise ValueError("opportunity counts must be >= 0")


@dataclass(frozen=True, slots=True)
class RecruitmentEvidenceGateDecision:
    """Audit-only comparability/OOS decision; never promotes or mutates a candidate."""

    recruitment_id: str
    purpose: RecruitmentEvidencePurpose
    status: RecruitmentGateStatus
    comparable: bool
    is_out_of_sample: bool
    reason_codes: tuple[str, ...]
    provenance: RecruitmentEvidenceProvenance
    audit_fingerprint_sha256: str
    gate_version: str = "batch19.recruitment-evidence-gate.v1"
    auto_apply: bool = False
    registry_mutation: bool = False
    promotion_action: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        if not self.recruitment_id.strip():
            raise ValueError("recruitment_id must not be blank")
        if not self.reason_codes:
            raise ValueError("reason_codes must not be empty")
        normalized = tuple(sorted(code.strip() for code in self.reason_codes))
        if any(not code for code in normalized):
            raise ValueError("reason_codes must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("reason_codes must not contain duplicates")
        object.__setattr__(self, "reason_codes", normalized)
        if len(self.audit_fingerprint_sha256) != 64:
            raise ValueError("audit_fingerprint_sha256 must be a SHA-256 hex digest")
        if self.auto_apply or self.registry_mutation or self.promotion_action or self.live_authority:
            raise ValueError("recruitment evidence gates cannot apply operational changes")
        if self.status is RecruitmentGateStatus.ALLOW and not self.comparable:
            raise ValueError("non-comparable evidence cannot be allowed")
        if self.purpose is RecruitmentEvidencePurpose.PROMOTION:
            if self.status is RecruitmentGateStatus.ALLOW and not self.is_out_of_sample:
                raise ValueError("promotion evidence can only be allowed when OOS")


def _success_criteria_fingerprint(candidate: RecruitmentCandidateSpec) -> str:
    return stable_digest(
        {
            "schema": "money-heist.recruitment-success-criteria.v1",
            "recruitment_id": candidate.recruitment_id,
            "criteria": [
                criterion.model_dump(mode="json") for criterion in candidate.success_criteria
            ],
        }
    )


def _material_config_payload(config: Any) -> dict[str, Any]:
    payload = dict(config.canonical_payload())
    assumptions = dict(payload.get("execution_assumptions", {}))
    payload["execution_assumptions"] = {
        key: value
        for key, value in assumptions.items()
        if key not in _RECRUITMENT_EXECUTION_KEYS
    }
    return payload


def _build_provenance(
    plan: RecruitmentCampaignPlan,
    execution: RecruitmentCampaignExecutionReport,
) -> RecruitmentEvidenceProvenance:
    baseline = execution.baseline
    candidate = execution.with_candidate
    return RecruitmentEvidenceProvenance(
        campaign_id=execution.campaign_id,
        recruitment_id=execution.recruitment_id,
        baseline_id=plan.baseline_id,
        source_run_id=plan.source_run_id,
        comparison_fingerprint=execution.comparison_fingerprint,
        execution_fingerprint=execution.execution_fingerprint,
        success_criteria_fingerprint=plan.success_criteria_fingerprint,
        candidate_agent_id=plan.candidate_agent_id,
        baseline_run_id=baseline.run_id,
        candidate_run_id=candidate.run_id,
        baseline_dataset_id=baseline.period_report.dataset_id,
        candidate_dataset_id=candidate.period_report.dataset_id,
        baseline_role=baseline.period_report.role,
        candidate_role=candidate.period_report.role,
        baseline_period_start=baseline.period_report.period_start,
        candidate_period_start=candidate.period_report.period_start,
        baseline_period_end=baseline.period_report.period_end,
        candidate_period_end=candidate.period_report.period_end,
        baseline_processed_candles=baseline.period_report.processed_candles,
        candidate_processed_candles=candidate.period_report.processed_candles,
        baseline_opportunity_count=baseline.period_report.opportunity_count,
        candidate_opportunity_count=candidate.period_report.opportunity_count,
        baseline_business_sha256=baseline.period_report.business_sha256,
        candidate_business_sha256=candidate.period_report.business_sha256,
        baseline_agents=baseline.variant.included_agents,
        candidate_agents=candidate.variant.included_agents,
    )


def _comparability_reasons(
    plan: RecruitmentCampaignPlan,
    candidate: RecruitmentCandidateSpec,
    execution: RecruitmentCampaignExecutionReport,
) -> list[str]:
    reasons: list[str] = []
    baseline = execution.baseline
    with_candidate = execution.with_candidate

    if execution.campaign_id != plan.campaign_id:
        reasons.append("CAMPAIGN_ID_MISMATCH")
    if execution.recruitment_id != plan.recruitment_id:
        reasons.append("RECRUITMENT_ID_MISMATCH")
    if execution.comparison_fingerprint != plan.comparison_fingerprint:
        reasons.append("COMPARISON_FINGERPRINT_MISMATCH")
    if execution.role is not plan.role:
        reasons.append("PLAN_EXECUTION_ROLE_MISMATCH")

    if candidate.recruitment_id != plan.recruitment_id:
        reasons.append("CANDIDATE_ID_MISMATCH")
    if candidate.baseline.baseline_id != plan.baseline_id:
        reasons.append("BASELINE_SPEC_DRIFT")
    if candidate_runtime_agent_id(candidate) != plan.candidate_agent_id:
        reasons.append("CANDIDATE_RUNTIME_ID_MISMATCH")
    if _success_criteria_fingerprint(candidate) != plan.success_criteria_fingerprint:
        reasons.append("SUCCESS_CRITERIA_DRIFT")

    if baseline.variant.variant_id != plan.baseline.variant_id:
        reasons.append("BASELINE_VARIANT_ID_MISMATCH")
    if with_candidate.variant.variant_id != plan.with_candidate.variant_id:
        reasons.append("CANDIDATE_VARIANT_ID_MISMATCH")
    if baseline.run_id != plan.baseline.run.run_id:
        reasons.append("BASELINE_RUN_ID_MISMATCH")
    if with_candidate.run_id != plan.with_candidate.run.run_id:
        reasons.append("CANDIDATE_RUN_ID_MISMATCH")
    if baseline.run_id == with_candidate.run_id:
        reasons.append("TWIN_RUN_IDS_MUST_DIFFER")

    comparable_fields = (
        ("DATASET_MISMATCH", baseline.period_report.dataset_id, with_candidate.period_report.dataset_id),
        ("PERIOD_ROLE_MISMATCH", baseline.period_report.role, with_candidate.period_report.role),
        ("PERIOD_START_MISMATCH", baseline.period_report.period_start, with_candidate.period_report.period_start),
        ("PERIOD_END_MISMATCH", baseline.period_report.period_end, with_candidate.period_report.period_end),
        (
            "PROCESSED_CANDLES_MISMATCH",
            baseline.period_report.processed_candles,
            with_candidate.period_report.processed_candles,
        ),
        (
            "OPPORTUNITY_COUNT_MISMATCH",
            baseline.period_report.opportunity_count,
            with_candidate.period_report.opportunity_count,
        ),
    )
    for reason, left, right in comparable_fields:
        if left != right:
            reasons.append(reason)

    if baseline.period_report.role is not plan.role:
        reasons.append("BASELINE_ROLE_MISMATCH")
    if with_candidate.period_report.role is not plan.role:
        reasons.append("CANDIDATE_ROLE_MISMATCH")

    if baseline.variant.included_agents != plan.baseline.included_agents:
        reasons.append("BASELINE_ROSTER_MISMATCH")
    if with_candidate.variant.included_agents != plan.with_candidate.included_agents:
        reasons.append("CANDIDATE_ROSTER_MISMATCH")
    baseline_agents = set(baseline.variant.included_agents)
    candidate_agents = set(with_candidate.variant.included_agents)
    if candidate_agents - baseline_agents != {plan.candidate_agent_id}:
        reasons.append("CANDIDATE_TWIN_MUST_ADD_EXACTLY_CANDIDATE")
    if baseline_agents - candidate_agents:
        reasons.append("CANDIDATE_TWIN_MUST_NOT_REMOVE_INCUMBENTS")

    if _material_config_payload(baseline.variant.run.config) != _material_config_payload(
        with_candidate.variant.run.config
    ):
        reasons.append("MATERIAL_BACKTEST_CONFIG_MISMATCH")

    return reasons


def evaluate_recruitment_evidence(
    plan: RecruitmentCampaignPlan,
    candidate: RecruitmentCandidateSpec,
    execution: RecruitmentCampaignExecutionReport,
    *,
    purpose: RecruitmentEvidencePurpose,
) -> RecruitmentEvidenceGateDecision:
    """Evaluate whether one twin execution is usable evidence for a declared purpose.

    DESIGN/VALIDATION may be ALLOWed for DIAGNOSTIC use when comparable. PROMOTION
    evidence is fail-closed unless the campaign is strictly OOS. ALLOW never means
    the success criteria passed and never changes lifecycle/registry state.
    """

    reasons = _comparability_reasons(plan, candidate, execution)
    comparable = not reasons
    is_oos = (
        execution.role is BacktestPeriodRole.OOS
        and execution.baseline.period_report.role is BacktestPeriodRole.OOS
        and execution.with_candidate.period_report.role is BacktestPeriodRole.OOS
    )

    if comparable and purpose is RecruitmentEvidencePurpose.PROMOTION and not is_oos:
        reasons.append("OOS_REQUIRED_FOR_PROMOTION_EVIDENCE")

    if reasons:
        status = RecruitmentGateStatus.BLOCK
    else:
        status = RecruitmentGateStatus.ALLOW
        if purpose is RecruitmentEvidencePurpose.PROMOTION:
            reasons.append("COMPARABLE_OOS_PROMOTION_EVIDENCE")
        else:
            reasons.append("COMPARABLE_DIAGNOSTIC_EVIDENCE")

    provenance = _build_provenance(plan, execution)
    canonical_reasons = tuple(sorted(reasons))
    fingerprint = stable_digest(
        {
            "schema": "money-heist.recruitment-evidence-gate.v1",
            "purpose": purpose,
            "status": status,
            "comparable": comparable,
            "is_out_of_sample": is_oos,
            "reason_codes": canonical_reasons,
            "provenance": provenance,
            "auto_apply": False,
            "registry_mutation": False,
            "promotion_action": False,
            "live_authority": False,
        }
    )
    return RecruitmentEvidenceGateDecision(
        recruitment_id=plan.recruitment_id,
        purpose=purpose,
        status=status,
        comparable=comparable,
        is_out_of_sample=is_oos,
        reason_codes=canonical_reasons,
        provenance=provenance,
        audit_fingerprint_sha256=fingerprint,
    )


__all__ = [
    "RecruitmentEvidenceBasis",
    "RecruitmentEvidenceGateDecision",
    "RecruitmentEvidenceProvenance",
    "RecruitmentEvidencePurpose",
    "evaluate_recruitment_evidence",
]
