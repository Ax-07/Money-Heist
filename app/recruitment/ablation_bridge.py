from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.evaluation.ablation import AblationComparison, AblationRunDescriptor, compare_ablation
from app.services.backtest.ids import stable_digest

from .campaign import RecruitmentCampaignPlan, candidate_runtime_agent_id
from .campaign_execution import RecruitmentCampaignExecutionReport
from .evidence_gate import (
    RecruitmentEvidenceGateDecision,
    RecruitmentEvidencePurpose,
    evaluate_recruitment_evidence,
)
from .gates import RecruitmentGateStatus
from .models import RecruitmentCandidateSpec


class RecruitmentAblationSemantics(StrEnum):
    """How recruitment twins map onto the pre-existing Batch 18 ablation contract."""

    FULL_WITH_CANDIDATE_VS_WITHOUT_CANDIDATE_BASELINE = (
        "FULL_WITH_CANDIDATE_VS_WITHOUT_CANDIDATE_BASELINE"
    )


@dataclass(frozen=True, slots=True)
class RecruitmentAblationBridgeResult:
    """Audited adapter result; it carries evidence but no lifecycle authority."""

    recruitment_id: str
    candidate_agent_id: str
    purpose: RecruitmentEvidencePurpose
    evidence_gate_fingerprint_sha256: str
    comparison: AblationComparison
    audit_fingerprint_sha256: str
    semantics: RecruitmentAblationSemantics = (
        RecruitmentAblationSemantics.FULL_WITH_CANDIDATE_VS_WITHOUT_CANDIDATE_BASELINE
    )
    auto_apply: bool = False
    registry_mutation: bool = False
    promotion_action: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        if not self.recruitment_id.strip():
            raise ValueError("recruitment_id must not be blank")
        if not self.candidate_agent_id.strip():
            raise ValueError("candidate_agent_id must not be blank")
        if len(self.evidence_gate_fingerprint_sha256) != 64:
            raise ValueError("evidence_gate_fingerprint_sha256 must be a SHA-256 hex digest")
        if len(self.audit_fingerprint_sha256) != 64:
            raise ValueError("audit_fingerprint_sha256 must be a SHA-256 hex digest")
        if self.comparison.agent_id != self.candidate_agent_id:
            raise ValueError("ablation comparison must target candidate_agent_id")
        if self.auto_apply or self.registry_mutation or self.promotion_action or self.live_authority:
            raise ValueError("recruitment ablation bridge cannot apply operational changes")

    @property
    def is_out_of_sample(self) -> bool:
        return self.comparison.is_out_of_sample


def bridge_recruitment_to_ablation(
    plan: RecruitmentCampaignPlan,
    candidate: RecruitmentCandidateSpec,
    execution: RecruitmentCampaignExecutionReport,
    evidence_gate: RecruitmentEvidenceGateDecision,
) -> RecruitmentAblationBridgeResult:
    """Adapt one approved recruitment twin comparison to Batch 18 AblationComparison.

    Batch 18 names the run containing the evaluated agent ``baseline`` and the run
    without that agent ``ablated``. Recruitment terminology is the inverse: the
    incumbent-only run is called BASELINE. Therefore WITH_CANDIDATE is intentionally
    passed as the full Batch 18 baseline, and recruitment BASELINE as the ablated twin.

    The evidence gate is recomputed before adaptation. A stale, tampered or blocked gate
    cannot be bridged. The function calculates no recruitment success decision and does
    not mutate lifecycle, registry, Risk Engine or execution authority.
    """

    expected_gate = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=evidence_gate.purpose,
    )
    if expected_gate.audit_fingerprint_sha256 != evidence_gate.audit_fingerprint_sha256:
        raise ValueError("recruitment evidence gate is stale or does not match execution")
    if expected_gate != evidence_gate:
        raise ValueError("recruitment evidence gate payload does not match recomputed gate")
    if evidence_gate.status is not RecruitmentGateStatus.ALLOW:
        raise ValueError("blocked recruitment evidence cannot be bridged to ablation")

    candidate_id = candidate_runtime_agent_id(candidate)
    if candidate_id != plan.candidate_agent_id:
        raise ValueError("candidate runtime identity does not match campaign plan")

    full_with_candidate = AblationRunDescriptor(
        report=execution.with_candidate.period_report,
        comparison_fingerprint=plan.comparison_fingerprint,
        included_agents=execution.with_candidate.variant.included_agents,
    )
    without_candidate = AblationRunDescriptor(
        report=execution.baseline.period_report,
        comparison_fingerprint=plan.comparison_fingerprint,
        included_agents=execution.baseline.variant.included_agents,
    )
    comparison = compare_ablation(
        full_with_candidate,
        without_candidate,
        agent_id=candidate_id,
    )

    audit_fingerprint = stable_digest(
        {
            "schema": "money-heist.recruitment-ablation-bridge.v1",
            "recruitment_id": plan.recruitment_id,
            "candidate_agent_id": candidate_id,
            "purpose": evidence_gate.purpose,
            "evidence_gate_fingerprint_sha256": evidence_gate.audit_fingerprint_sha256,
            "semantics": RecruitmentAblationSemantics.FULL_WITH_CANDIDATE_VS_WITHOUT_CANDIDATE_BASELINE,
            "comparison": comparison,
            "auto_apply": False,
            "registry_mutation": False,
            "promotion_action": False,
            "live_authority": False,
        }
    )
    return RecruitmentAblationBridgeResult(
        recruitment_id=plan.recruitment_id,
        candidate_agent_id=candidate_id,
        purpose=evidence_gate.purpose,
        evidence_gate_fingerprint_sha256=evidence_gate.audit_fingerprint_sha256,
        comparison=comparison,
        audit_fingerprint_sha256=audit_fingerprint,
    )


__all__ = [
    "RecruitmentAblationBridgeResult",
    "RecruitmentAblationSemantics",
    "bridge_recruitment_to_ablation",
]
