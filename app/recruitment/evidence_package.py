from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .ablation_bridge import RecruitmentAblationBridgeResult, bridge_recruitment_to_ablation
from .campaign import (
    RecruitmentCampaignPlan,
    build_recruitment_campaign,
    candidate_runtime_agent_id,
)
from .campaign_execution import RecruitmentCampaignExecutionReport
from .candidate_reputation import (
    RecruitmentCandidateReputationEvidenceReport,
    build_candidate_reputation_evidence,
)
from .evidence_gate import (
    RecruitmentEvidenceBasis,
    RecruitmentEvidenceGateDecision,
    RecruitmentEvidencePurpose,
    evaluate_recruitment_evidence,
)
from .gates import RecruitmentGateStatus
from .models import RecruitmentCandidateSpec, RecruitmentSuccessCriterion


class RecruitmentEvidencePackageBasis(StrEnum):
    AUDITABLE_CANDIDATE_EVIDENCE = "AUDITABLE_CANDIDATE_EVIDENCE"


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


def _require_sha256(value: str, *, field_name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")


def _candidate_spec_fingerprint(candidate: RecruitmentCandidateSpec) -> str:
    return stable_digest(
        {
            "schema": "money-heist.recruitment-candidate-spec.v1",
            "candidate": candidate.model_dump(mode="json"),
        }
    )


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


def _assert_candidate_spec_matches_plan(
    plan: RecruitmentCampaignPlan,
    candidate: RecruitmentCandidateSpec,
) -> None:
    assumptions = dict(plan.baseline.run.config.execution_assumptions)
    source_assumptions = {
        key: value
        for key, value in assumptions.items()
        if key not in _RECRUITMENT_EXECUTION_KEYS
    }
    source_config = replace(
        plan.baseline.run.config,
        execution_assumptions=source_assumptions,
    )
    source_run = plan.baseline.run.__class__.create(
        dataset=plan.baseline.run.dataset,
        config=source_config,
        period_start=plan.baseline.run.period_start,
        period_end=plan.baseline.run.period_end,
    )
    if source_run.run_id != plan.source_run_id:
        raise ValueError("campaign plan cannot reconstruct its frozen source run")
    rebuilt = build_recruitment_campaign(
        source_run,
        candidate,
        role=plan.role,
        baseline_agents=plan.baseline_agents,
    )
    comparable = (
        rebuilt.campaign_id == plan.campaign_id
        and rebuilt.comparison_fingerprint == plan.comparison_fingerprint
        and rebuilt.success_criteria_fingerprint == plan.success_criteria_fingerprint
        and rebuilt.candidate_agent_id == plan.candidate_agent_id
        and tuple(item.variant_id for item in rebuilt.variants)
        == tuple(item.variant_id for item in plan.variants)
        and tuple(item.run.run_id for item in rebuilt.variants)
        == tuple(item.run.run_id for item in plan.variants)
    )
    if not comparable:
        raise ValueError("candidate spec changed after campaign planning")


@dataclass(frozen=True, slots=True)
class RecruitmentEvidencePackageLineage:
    """Compact immutable lineage linking every prerequisite evidence artifact."""

    recruitment_id: str
    candidate_agent_id: str
    purpose: RecruitmentEvidencePurpose
    campaign_id: str
    baseline_id: str
    source_run_id: str
    comparison_fingerprint: str
    execution_fingerprint: str
    success_criteria_fingerprint: str
    candidate_spec_fingerprint_sha256: str
    evidence_gate_fingerprint_sha256: str
    ablation_bridge_fingerprint_sha256: str
    reputation_evidence_fingerprint_sha256: str
    baseline_run_id: str
    candidate_run_id: str
    baseline_business_sha256: str
    candidate_business_sha256: str
    evaluation_report_version: str
    evidence_basis: RecruitmentEvidenceBasis

    def __post_init__(self) -> None:
        for field_name in (
            "recruitment_id",
            "candidate_agent_id",
            "campaign_id",
            "baseline_id",
            "source_run_id",
            "comparison_fingerprint",
            "execution_fingerprint",
            "success_criteria_fingerprint",
            "baseline_run_id",
            "candidate_run_id",
            "evaluation_report_version",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be blank")
        for field_name in (
            "candidate_spec_fingerprint_sha256",
            "evidence_gate_fingerprint_sha256",
            "ablation_bridge_fingerprint_sha256",
            "reputation_evidence_fingerprint_sha256",
            "baseline_business_sha256",
            "candidate_business_sha256",
        ):
            _require_sha256(str(getattr(self, field_name)), field_name=field_name)
        if self.baseline_run_id == self.candidate_run_id:
            raise ValueError("baseline_run_id and candidate_run_id must differ")


def _package_fingerprint(
    *,
    recruitment_id: str,
    candidate_agent_id: str,
    purpose: RecruitmentEvidencePurpose,
    lineage: RecruitmentEvidencePackageLineage,
    success_criteria_snapshot: tuple[RecruitmentSuccessCriterion, ...],
    evidence_gate: RecruitmentEvidenceGateDecision,
    ablation_bridge: RecruitmentAblationBridgeResult,
    reputation_evidence: RecruitmentCandidateReputationEvidenceReport,
) -> str:
    return stable_digest(
        {
            "schema": "money-heist.candidate-evidence-package.v1",
            "recruitment_id": recruitment_id,
            "candidate_agent_id": candidate_agent_id,
            "purpose": purpose,
            "lineage": lineage,
            "success_criteria_snapshot": [
                criterion.model_dump(mode="json")
                for criterion in success_criteria_snapshot
            ],
            "evidence_gate": evidence_gate,
            "ablation_bridge": ablation_bridge,
            "reputation_evidence": reputation_evidence,
            "basis": RecruitmentEvidencePackageBasis.AUDITABLE_CANDIDATE_EVIDENCE,
            "criteria_evaluation_performed": False,
            "recommendation_generated": False,
            "auto_apply": False,
            "registry_mutation": False,
            "promotion_action": False,
            "live_authority": False,
        }
    )


@dataclass(frozen=True, slots=True)
class RecruitmentCandidateEvidencePackage:
    """Reproducible evidence bundle consumed later by recruitment advisory policy.

    The package freezes evidence and lineage only. It deliberately does not evaluate
    success criteria, recommend a lifecycle transition, mutate AgentRegistry, or grant
    trading authority.
    """

    recruitment_id: str
    candidate_agent_id: str
    purpose: RecruitmentEvidencePurpose
    lineage: RecruitmentEvidencePackageLineage
    success_criteria_snapshot: tuple[RecruitmentSuccessCriterion, ...]
    evidence_gate: RecruitmentEvidenceGateDecision
    ablation_bridge: RecruitmentAblationBridgeResult
    reputation_evidence: RecruitmentCandidateReputationEvidenceReport
    audit_fingerprint_sha256: str
    package_version: str = "batch19.candidate-evidence-package.v1"
    basis: RecruitmentEvidencePackageBasis = RecruitmentEvidencePackageBasis.AUDITABLE_CANDIDATE_EVIDENCE
    criteria_evaluation_performed: bool = False
    recommendation_generated: bool = False
    auto_apply: bool = False
    registry_mutation: bool = False
    promotion_action: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        if not self.recruitment_id.strip():
            raise ValueError("recruitment_id must not be blank")
        if not self.candidate_agent_id.strip():
            raise ValueError("candidate_agent_id must not be blank")
        if not self.success_criteria_snapshot:
            raise ValueError("success_criteria_snapshot must not be empty")
        _require_sha256(self.audit_fingerprint_sha256, field_name="audit_fingerprint_sha256")

        ids = {
            self.recruitment_id,
            self.lineage.recruitment_id,
            self.evidence_gate.recruitment_id,
            self.ablation_bridge.recruitment_id,
            self.reputation_evidence.recruitment_id,
        }
        if len(ids) != 1:
            raise ValueError("evidence package contains mismatched recruitment ids")
        candidate_ids = {
            self.candidate_agent_id,
            self.lineage.candidate_agent_id,
            self.ablation_bridge.candidate_agent_id,
            self.reputation_evidence.candidate_agent_id,
        }
        if len(candidate_ids) != 1:
            raise ValueError("evidence package contains mismatched candidate agent ids")
        purposes = {
            self.purpose,
            self.lineage.purpose,
            self.evidence_gate.purpose,
            self.ablation_bridge.purpose,
            self.reputation_evidence.purpose,
        }
        if len(purposes) != 1:
            raise ValueError("evidence package contains mismatched evidence purposes")
        if self.evidence_gate.status is not RecruitmentGateStatus.ALLOW:
            raise ValueError("evidence package requires an ALLOW evidence gate")
        if self.lineage.evidence_gate_fingerprint_sha256 != self.evidence_gate.audit_fingerprint_sha256:
            raise ValueError("lineage evidence gate fingerprint does not match embedded gate")
        if self.lineage.ablation_bridge_fingerprint_sha256 != self.ablation_bridge.audit_fingerprint_sha256:
            raise ValueError("lineage ablation bridge fingerprint does not match embedded bridge")
        if self.lineage.reputation_evidence_fingerprint_sha256 != self.reputation_evidence.audit_fingerprint_sha256:
            raise ValueError("lineage reputation fingerprint does not match embedded evidence")
        if self.lineage.evidence_basis is not self.evidence_gate.provenance.evidence_basis:
            raise ValueError("lineage evidence basis does not match gate provenance")
        snapshot_fingerprint = stable_digest(
            {
                "schema": "money-heist.recruitment-success-criteria.v1",
                "recruitment_id": self.recruitment_id,
                "criteria": [
                    criterion.model_dump(mode="json")
                    for criterion in self.success_criteria_snapshot
                ],
            }
        )
        if snapshot_fingerprint != self.lineage.success_criteria_fingerprint:
            raise ValueError("success criteria snapshot does not match lineage fingerprint")
        if self.criteria_evaluation_performed or self.recommendation_generated:
            raise ValueError("Batch 19c evidence packages cannot evaluate criteria or recommend")
        if self.auto_apply or self.registry_mutation or self.promotion_action or self.live_authority:
            raise ValueError("candidate evidence packages cannot apply operational changes")
        expected_fingerprint = _package_fingerprint(
            recruitment_id=self.recruitment_id,
            candidate_agent_id=self.candidate_agent_id,
            purpose=self.purpose,
            lineage=self.lineage,
            success_criteria_snapshot=self.success_criteria_snapshot,
            evidence_gate=self.evidence_gate,
            ablation_bridge=self.ablation_bridge,
            reputation_evidence=self.reputation_evidence,
        )
        if expected_fingerprint != self.audit_fingerprint_sha256:
            raise ValueError("candidate evidence package fingerprint does not match payload")


def build_candidate_evidence_package(
    plan: RecruitmentCampaignPlan,
    candidate: RecruitmentCandidateSpec,
    execution: RecruitmentCampaignExecutionReport,
    evidence_gate: RecruitmentEvidenceGateDecision,
    ablation_bridge: RecruitmentAblationBridgeResult,
    reputation_evidence: RecruitmentCandidateReputationEvidenceReport,
) -> RecruitmentCandidateEvidencePackage:
    """Verify and package the complete Batch 19c evidence chain.

    Every prerequisite artifact is recomputed from the frozen plan/candidate/execution.
    Stale or tampered gate, bridge, or reputation evidence is rejected before packaging.
    """

    _assert_candidate_spec_matches_plan(plan, candidate)

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
    if expected_gate.status is not RecruitmentGateStatus.ALLOW:
        raise ValueError("blocked recruitment evidence cannot be packaged")

    expected_bridge = bridge_recruitment_to_ablation(
        plan,
        candidate,
        execution,
        expected_gate,
    )
    if expected_bridge.audit_fingerprint_sha256 != ablation_bridge.audit_fingerprint_sha256:
        raise ValueError("recruitment ablation bridge is stale or does not match execution")
    if expected_bridge != ablation_bridge:
        raise ValueError("recruitment ablation bridge payload does not match recomputed bridge")

    expected_reputation = build_candidate_reputation_evidence(
        plan,
        candidate,
        execution,
        expected_gate,
        expected_bridge,
    )
    if expected_reputation.audit_fingerprint_sha256 != reputation_evidence.audit_fingerprint_sha256:
        raise ValueError("candidate reputation evidence is stale or does not match execution")
    if expected_reputation != reputation_evidence:
        raise ValueError("candidate reputation evidence payload does not match recomputed evidence")

    candidate_id = candidate_runtime_agent_id(candidate)
    if candidate_id != plan.candidate_agent_id:
        raise ValueError("candidate runtime identity does not match campaign plan")

    candidate_spec_fingerprint = _candidate_spec_fingerprint(candidate)
    criteria_fingerprint = _success_criteria_fingerprint(candidate)
    if criteria_fingerprint != plan.success_criteria_fingerprint:
        raise ValueError("success criteria changed after campaign planning")

    provenance = expected_gate.provenance
    lineage = RecruitmentEvidencePackageLineage(
        recruitment_id=plan.recruitment_id,
        candidate_agent_id=candidate_id,
        purpose=expected_gate.purpose,
        campaign_id=plan.campaign_id,
        baseline_id=plan.baseline_id,
        source_run_id=plan.source_run_id,
        comparison_fingerprint=plan.comparison_fingerprint,
        execution_fingerprint=execution.execution_fingerprint,
        success_criteria_fingerprint=plan.success_criteria_fingerprint,
        candidate_spec_fingerprint_sha256=candidate_spec_fingerprint,
        evidence_gate_fingerprint_sha256=expected_gate.audit_fingerprint_sha256,
        ablation_bridge_fingerprint_sha256=expected_bridge.audit_fingerprint_sha256,
        reputation_evidence_fingerprint_sha256=expected_reputation.audit_fingerprint_sha256,
        baseline_run_id=provenance.baseline_run_id,
        candidate_run_id=provenance.candidate_run_id,
        baseline_business_sha256=provenance.baseline_business_sha256,
        candidate_business_sha256=provenance.candidate_business_sha256,
        evaluation_report_version=expected_reputation.evaluation_report_version,
        evidence_basis=provenance.evidence_basis,
    )
    criteria_snapshot = tuple(candidate.success_criteria)
    fingerprint = _package_fingerprint(
        recruitment_id=plan.recruitment_id,
        candidate_agent_id=candidate_id,
        purpose=expected_gate.purpose,
        lineage=lineage,
        success_criteria_snapshot=criteria_snapshot,
        evidence_gate=expected_gate,
        ablation_bridge=expected_bridge,
        reputation_evidence=expected_reputation,
    )
    return RecruitmentCandidateEvidencePackage(
        recruitment_id=plan.recruitment_id,
        candidate_agent_id=candidate_id,
        purpose=expected_gate.purpose,
        lineage=lineage,
        success_criteria_snapshot=criteria_snapshot,
        evidence_gate=expected_gate,
        ablation_bridge=expected_bridge,
        reputation_evidence=expected_reputation,
        audit_fingerprint_sha256=fingerprint,
    )


__all__ = [
    "RecruitmentCandidateEvidencePackage",
    "RecruitmentEvidencePackageBasis",
    "RecruitmentEvidencePackageLineage",
    "build_candidate_evidence_package",
]
