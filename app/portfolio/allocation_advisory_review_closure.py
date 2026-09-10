from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .allocation import MasterAllocationPolicy, master_allocation_policy_fingerprint
from .allocation_advisory import (
    MasterAllocationAdvisoryAction,
    build_master_allocation_advisory_evidence,
    master_allocation_advisory_recommendation_payload,
    master_allocation_advisory_report_payload,
)
from .allocation_evidence_analysis import (
    MasterAllocationEvidenceAnalysisReport,
    master_allocation_evidence_analysis_payload,
)
from .allocation_master_professor_shadow import (
    MASTER_PROFESSOR_AGENT_ID,
    MasterProfessorShadowAdvisoryResult,
    MasterProfessorShadowStatus,
    master_professor_shadow_result_payload,
    master_professor_shadow_usage_payload,
)


class MasterProfessorOperatorReviewAction(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    DEFER = "DEFER"


class MasterProfessorOperatorReviewStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


class MasterProfessorAdvisoryAuditStatus(StrEnum):
    VERIFIED = "VERIFIED"


class MasterProfessorAdvisoryClosureStatus(StrEnum):
    SEALED = "SEALED"


def _required_text(value: object, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _sha256(value: str, *, field_name: str) -> str:
    normalized = str(value).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return normalized


def _canonical_text_values(
    values: tuple[str, ...],
    *,
    field_name: str,
) -> tuple[str, ...]:
    normalized = tuple(_required_text(value, field_name=field_name) for value in values)
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if normalized != tuple(sorted(normalized)):
        raise ValueError(f"{field_name} must be sorted")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must be unique")
    return normalized


def _policy_fingerprint(policy: MasterAllocationPolicy) -> str:
    return master_allocation_policy_fingerprint(
        master_portfolio_id=policy.master_portfolio_id,
        policy_id=policy.policy_id,
        members=policy.members,
        envelopes=policy.envelopes,
        status=policy.status,
        reason_codes=policy.reason_codes,
        source=policy.source,
        source_ref=policy.source_ref,
        schema_version=policy.schema_version,
    )


def _review_status(
    action: MasterProfessorOperatorReviewAction,
) -> MasterProfessorOperatorReviewStatus:
    mapping = {
        MasterProfessorOperatorReviewAction.ACCEPT: MasterProfessorOperatorReviewStatus.ACCEPTED,
        MasterProfessorOperatorReviewAction.REJECT: MasterProfessorOperatorReviewStatus.REJECTED,
        MasterProfessorOperatorReviewAction.DEFER: MasterProfessorOperatorReviewStatus.DEFERRED,
    }
    return mapping[action]


def master_professor_operator_review_payload(
    decision: MasterProfessorOperatorReviewDecision,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-professor-operator-review.v1",
        "schema_version": decision.schema_version,
        "decision_id": decision.decision_id,
        "status": decision.status,
        "action": decision.action,
        "master_portfolio_id": decision.master_portfolio_id,
        "analysis_fingerprint_sha256": decision.analysis_fingerprint_sha256,
        "shadow_result_fingerprint_sha256": decision.shadow_result_fingerprint_sha256,
        "advisory_report_fingerprint_sha256": decision.advisory_report_fingerprint_sha256,
        "recommendation_fingerprint_sha256": decision.recommendation_fingerprint_sha256,
        "current_policy_fingerprint_sha256": decision.current_policy_fingerprint_sha256,
        "recommendation_action": decision.recommendation_action,
        "selected_candidate_id": decision.selected_candidate_id,
        "operator_ref": decision.operator_ref,
        "rationale_codes": decision.rationale_codes,
        "decided_at": decision.decided_at,
    }


@dataclass(frozen=True, slots=True)
class MasterProfessorOperatorReviewDecision:
    decision_id: str
    status: MasterProfessorOperatorReviewStatus
    action: MasterProfessorOperatorReviewAction
    master_portfolio_id: str
    analysis_fingerprint_sha256: str
    shadow_result_fingerprint_sha256: str
    advisory_report_fingerprint_sha256: str
    recommendation_fingerprint_sha256: str
    current_policy_fingerprint_sha256: str
    recommendation_action: MasterAllocationAdvisoryAction
    selected_candidate_id: str | None
    operator_ref: str
    rationale_codes: tuple[str, ...]
    decided_at: datetime
    fingerprint_sha256: str
    human_operator_required: bool = field(default=True, init=False)
    operator_decision_recorded: bool = field(default=True, init=False)
    advisory_acceptance_only: bool = field(default=True, init=False)
    allocation_application_performed: bool = field(default=False, init=False)
    allocation_application_authority: bool = field(default=False, init=False)
    policy_mutation: bool = field(default=False, init=False)
    reservation_authority: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("decision_id", "master_portfolio_id", "operator_ref"):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), field_name=name),
            )
        for name in (
            "analysis_fingerprint_sha256",
            "shadow_result_fingerprint_sha256",
            "advisory_report_fingerprint_sha256",
            "recommendation_fingerprint_sha256",
            "current_policy_fingerprint_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), field_name=name))
        if self.selected_candidate_id is not None:
            object.__setattr__(
                self,
                "selected_candidate_id",
                _required_text(self.selected_candidate_id, field_name="selected_candidate_id"),
            )
        object.__setattr__(
            self,
            "rationale_codes",
            _canonical_text_values(self.rationale_codes, field_name="rationale_codes"),
        )
        object.__setattr__(self, "decided_at", _utc(self.decided_at, field_name="decided_at"))
        if self.status is not _review_status(self.action):
            raise ValueError("operator review status does not match action")
        if self.recommendation_action is MasterAllocationAdvisoryAction.PROPOSE_CHANGE:
            if self.selected_candidate_id is None:
                raise ValueError("PROPOSE_CHANGE review must preserve selected candidate identity")
        elif self.selected_candidate_id is not None:
            raise ValueError("non-change recommendation review cannot carry selected candidate")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master Professor operator review schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        if normalized != stable_digest(master_professor_operator_review_payload(self)):
            raise ValueError("Master Professor operator review fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_professor_operator_review_payload(self)


def _validate_shadow_result_integrity(
    *,
    analysis: MasterAllocationEvidenceAnalysisReport,
    shadow_result: MasterProfessorShadowAdvisoryResult,
) -> None:
    if stable_digest(master_allocation_evidence_analysis_payload(analysis)) != (
        analysis.fingerprint_sha256
    ):
        raise ValueError("operator review analysis fingerprint integrity failure")
    if stable_digest(master_professor_shadow_result_payload(shadow_result)) != (
        shadow_result.fingerprint_sha256
    ):
        raise ValueError("operator review SHADOW result fingerprint integrity failure")
    if shadow_result.status is not MasterProfessorShadowStatus.COMPLETED:
        raise ValueError("operator review requires completed Master Professor SHADOW result")
    if shadow_result.analysis_id != analysis.analysis_id:
        raise ValueError("operator review analysis identity mismatch")
    if shadow_result.analysis_fingerprint_sha256 != analysis.fingerprint_sha256:
        raise ValueError("operator review analysis fingerprint mismatch")
    if shadow_result.master_portfolio_id != analysis.master_portfolio_id:
        raise ValueError("operator review Master Portfolio mismatch")
    report = shadow_result.advisory_report
    report_fingerprint = stable_digest(master_allocation_advisory_report_payload(report))
    if report_fingerprint != report.fingerprint_sha256:
        raise ValueError("operator review advisory report fingerprint integrity failure")
    recommendation = report.recommendation
    if stable_digest(master_allocation_advisory_recommendation_payload(recommendation)) != (
        recommendation.fingerprint_sha256
    ):
        raise ValueError("operator review recommendation fingerprint integrity failure")
    policy = report.current_allocation_policy
    if _policy_fingerprint(policy) != policy.fingerprint_sha256:
        raise ValueError("operator review allocation policy fingerprint integrity failure")
    if analysis.current_policy_fingerprint_sha256 != policy.fingerprint_sha256:
        raise ValueError("operator review Step 2 current policy mismatch")
    if shadow_result.current_policy_fingerprint_sha256 != policy.fingerprint_sha256:
        raise ValueError("operator review Step 3 current policy mismatch")
    evidence_fingerprints: list[str] = []
    for evidence in report.evidence:
        rebuilt = build_master_allocation_advisory_evidence(
            audit_report=evidence.audit_report,
            closure_seal=evidence.closure_seal,
            evaluation=evidence.evaluation,
            regime_label=evidence.regime_label,
            regime_source_ref=evidence.regime_source_ref,
        )
        if rebuilt.fingerprint_sha256 != evidence.fingerprint_sha256:
            raise ValueError("operator review Step 1 evidence fingerprint integrity failure")
        evidence_fingerprints.append(evidence.fingerprint_sha256)
    if tuple(evidence_fingerprints) != analysis.evidence_fingerprints_sha256:
        raise ValueError("operator review Step 1/Step 2 evidence provenance mismatch")
    if report.fingerprint_sha256 != shadow_result.advisory_report.fingerprint_sha256:
        raise ValueError("operator review advisory report provenance mismatch")
    if recommendation.fingerprint_sha256 != shadow_result.recommendation_fingerprint_sha256:
        raise ValueError("operator review recommendation provenance mismatch")
    for usage in shadow_result.usage_records:
        if stable_digest(master_professor_shadow_usage_payload(usage)) != usage.fingerprint_sha256:
            raise ValueError("operator review AI usage fingerprint integrity failure")
        if usage.agent_id != MASTER_PROFESSOR_AGENT_ID:
            raise ValueError("operator review AI usage agent identity mismatch")


def build_master_professor_operator_review_decision(
    *,
    analysis: MasterAllocationEvidenceAnalysisReport,
    shadow_result: MasterProfessorShadowAdvisoryResult,
    action: MasterProfessorOperatorReviewAction,
    operator_ref: str,
    rationale_codes: tuple[str, ...],
    decided_at: datetime,
) -> MasterProfessorOperatorReviewDecision:
    _validate_shadow_result_integrity(analysis=analysis, shadow_result=shadow_result)
    normalized_operator_ref = _required_text(operator_ref, field_name="operator_ref")
    ordered_reasons = tuple(sorted(rationale_codes))
    _canonical_text_values(ordered_reasons, field_name="rationale_codes")
    normalized_decided_at = _utc(decided_at, field_name="decided_at")
    latest_usage_at = max(item.created_at for item in shadow_result.usage_records)
    if normalized_decided_at < latest_usage_at:
        raise ValueError("operator review cannot predate Master Professor AI usage")
    output = shadow_result.output
    values = {
        "status": _review_status(action),
        "action": action,
        "master_portfolio_id": shadow_result.master_portfolio_id,
        "analysis_fingerprint_sha256": analysis.fingerprint_sha256,
        "shadow_result_fingerprint_sha256": shadow_result.fingerprint_sha256,
        "advisory_report_fingerprint_sha256": shadow_result.advisory_report.fingerprint_sha256,
        "recommendation_fingerprint_sha256": shadow_result.recommendation_fingerprint_sha256,
        "current_policy_fingerprint_sha256": shadow_result.current_policy_fingerprint_sha256,
        "recommendation_action": shadow_result.advisory_report.recommendation.action,
        "selected_candidate_id": output.selected_candidate_id,
        "operator_ref": normalized_operator_ref,
        "rationale_codes": ordered_reasons,
        "decided_at": normalized_decided_at,
    }
    decision_id = "master-professor-operator-review:" + stable_digest(
        {
            "schema": "money-heist.master-professor-operator-review-id.v1",
            **values,
        }
    )
    provisional = MasterProfessorOperatorReviewDecision.__new__(
        MasterProfessorOperatorReviewDecision
    )
    object.__setattr__(provisional, "decision_id", decision_id)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterProfessorOperatorReviewDecision(
        decision_id=decision_id,
        **values,
        fingerprint_sha256=stable_digest(master_professor_operator_review_payload(provisional)),
    )


def master_professor_advisory_audit_payload(
    audit: MasterProfessorAdvisoryAuditReport,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-professor-advisory-audit.v1",
        "schema_version": audit.schema_version,
        "audit_id": audit.audit_id,
        "status": audit.status,
        "master_portfolio_id": audit.master_portfolio_id,
        "analysis_id": audit.analysis_id,
        "analysis_fingerprint_sha256": audit.analysis_fingerprint_sha256,
        "shadow_result_fingerprint_sha256": audit.shadow_result_fingerprint_sha256,
        "advisory_report_fingerprint_sha256": audit.advisory_report_fingerprint_sha256,
        "recommendation_fingerprint_sha256": audit.recommendation_fingerprint_sha256,
        "current_policy_fingerprint_sha256": audit.current_policy_fingerprint_sha256,
        "operator_decision_fingerprint_sha256": audit.operator_decision_fingerprint_sha256,
        "operator_review_action": audit.operator_review_action,
        "operator_review_status": audit.operator_review_status,
        "recommendation_action": audit.recommendation_action,
        "selected_candidate_id": audit.selected_candidate_id,
        "reviewed_at": audit.reviewed_at,
        "step1_evidence_chain_verified": audit.step1_evidence_chain_verified,
        "step2_analysis_verified": audit.step2_analysis_verified,
        "step3_shadow_gateway_verified": audit.step3_shadow_gateway_verified,
        "operator_review_verified": audit.operator_review_verified,
        "no_policy_application_verified": audit.no_policy_application_verified,
        "no_trading_authority_verified": audit.no_trading_authority_verified,
    }


@dataclass(frozen=True, slots=True)
class MasterProfessorAdvisoryAuditReport:
    audit_id: str
    status: MasterProfessorAdvisoryAuditStatus
    master_portfolio_id: str
    analysis_id: str
    analysis_fingerprint_sha256: str
    shadow_result_fingerprint_sha256: str
    advisory_report_fingerprint_sha256: str
    recommendation_fingerprint_sha256: str
    current_policy_fingerprint_sha256: str
    operator_decision_fingerprint_sha256: str
    operator_review_action: MasterProfessorOperatorReviewAction
    operator_review_status: MasterProfessorOperatorReviewStatus
    recommendation_action: MasterAllocationAdvisoryAction
    selected_candidate_id: str | None
    reviewed_at: datetime
    step1_evidence_chain_verified: bool
    step2_analysis_verified: bool
    step3_shadow_gateway_verified: bool
    operator_review_verified: bool
    no_policy_application_verified: bool
    no_trading_authority_verified: bool
    fingerprint_sha256: str
    advisory_only: bool = field(default=True, init=False)
    audit_only: bool = field(default=True, init=False)
    policy_mutation: bool = field(default=False, init=False)
    allocation_application_performed: bool = field(default=False, init=False)
    allocation_application_authority: bool = field(default=False, init=False)
    reservation_authority: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("audit_id", "master_portfolio_id", "analysis_id"):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), field_name=name),
            )
        for name in (
            "analysis_fingerprint_sha256",
            "shadow_result_fingerprint_sha256",
            "advisory_report_fingerprint_sha256",
            "recommendation_fingerprint_sha256",
            "current_policy_fingerprint_sha256",
            "operator_decision_fingerprint_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), field_name=name))
        if self.selected_candidate_id is not None:
            object.__setattr__(
                self,
                "selected_candidate_id",
                _required_text(self.selected_candidate_id, field_name="selected_candidate_id"),
            )
        object.__setattr__(self, "reviewed_at", _utc(self.reviewed_at, field_name="reviewed_at"))
        if self.status is not MasterProfessorAdvisoryAuditStatus.VERIFIED:
            raise ValueError("Master Professor advisory audit status must be VERIFIED")
        if self.operator_review_status is not _review_status(self.operator_review_action):
            raise ValueError("Master Professor advisory audit review status mismatch")
        verification_flags = (
            self.step1_evidence_chain_verified,
            self.step2_analysis_verified,
            self.step3_shadow_gateway_verified,
            self.operator_review_verified,
            self.no_policy_application_verified,
            self.no_trading_authority_verified,
        )
        if not all(verification_flags):
            raise ValueError("Master Professor advisory audit requires all verification flags")
        if self.recommendation_action is MasterAllocationAdvisoryAction.PROPOSE_CHANGE:
            if self.selected_candidate_id is None:
                raise ValueError("PROPOSE_CHANGE audit must preserve selected candidate identity")
        elif self.selected_candidate_id is not None:
            raise ValueError("non-change advisory audit cannot carry selected candidate")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master Professor advisory audit schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        if normalized != stable_digest(master_professor_advisory_audit_payload(self)):
            raise ValueError("Master Professor advisory audit fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_professor_advisory_audit_payload(self)


def audit_master_professor_advisory_review(
    *,
    analysis: MasterAllocationEvidenceAnalysisReport,
    shadow_result: MasterProfessorShadowAdvisoryResult,
    operator_decision: MasterProfessorOperatorReviewDecision,
) -> MasterProfessorAdvisoryAuditReport:
    _validate_shadow_result_integrity(analysis=analysis, shadow_result=shadow_result)
    if stable_digest(master_professor_operator_review_payload(operator_decision)) != (
        operator_decision.fingerprint_sha256
    ):
        raise ValueError("advisory audit operator decision fingerprint integrity failure")
    expected_bindings = (
        (operator_decision.master_portfolio_id, shadow_result.master_portfolio_id),
        (operator_decision.analysis_fingerprint_sha256, analysis.fingerprint_sha256),
        (operator_decision.shadow_result_fingerprint_sha256, shadow_result.fingerprint_sha256),
        (
            operator_decision.advisory_report_fingerprint_sha256,
            shadow_result.advisory_report.fingerprint_sha256,
        ),
        (
            operator_decision.recommendation_fingerprint_sha256,
            shadow_result.recommendation_fingerprint_sha256,
        ),
        (
            operator_decision.current_policy_fingerprint_sha256,
            shadow_result.current_policy_fingerprint_sha256,
        ),
        (
            operator_decision.recommendation_action,
            shadow_result.advisory_report.recommendation.action,
        ),
        (operator_decision.selected_candidate_id, shadow_result.output.selected_candidate_id),
    )
    if any(left != right for left, right in expected_bindings):
        raise ValueError("advisory audit operator decision provenance mismatch")
    latest_usage_at = max(item.created_at for item in shadow_result.usage_records)
    if operator_decision.decided_at < latest_usage_at:
        raise ValueError("advisory audit operator decision predates AI usage")
    values = {
        "status": MasterProfessorAdvisoryAuditStatus.VERIFIED,
        "master_portfolio_id": shadow_result.master_portfolio_id,
        "analysis_id": analysis.analysis_id,
        "analysis_fingerprint_sha256": analysis.fingerprint_sha256,
        "shadow_result_fingerprint_sha256": shadow_result.fingerprint_sha256,
        "advisory_report_fingerprint_sha256": shadow_result.advisory_report.fingerprint_sha256,
        "recommendation_fingerprint_sha256": shadow_result.recommendation_fingerprint_sha256,
        "current_policy_fingerprint_sha256": shadow_result.current_policy_fingerprint_sha256,
        "operator_decision_fingerprint_sha256": operator_decision.fingerprint_sha256,
        "operator_review_action": operator_decision.action,
        "operator_review_status": operator_decision.status,
        "recommendation_action": operator_decision.recommendation_action,
        "selected_candidate_id": operator_decision.selected_candidate_id,
        "reviewed_at": operator_decision.decided_at,
        "step1_evidence_chain_verified": True,
        "step2_analysis_verified": True,
        "step3_shadow_gateway_verified": True,
        "operator_review_verified": True,
        "no_policy_application_verified": True,
        "no_trading_authority_verified": True,
    }
    audit_id = "master-professor-advisory-audit:" + stable_digest(
        {
            "schema": "money-heist.master-professor-advisory-audit-id.v1",
            **values,
        }
    )
    provisional = MasterProfessorAdvisoryAuditReport.__new__(
        MasterProfessorAdvisoryAuditReport
    )
    object.__setattr__(provisional, "audit_id", audit_id)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterProfessorAdvisoryAuditReport(
        audit_id=audit_id,
        **values,
        fingerprint_sha256=stable_digest(master_professor_advisory_audit_payload(provisional)),
    )


def master_professor_advisory_closure_payload(
    seal: MasterProfessorAdvisoryClosureSeal,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-professor-advisory-closure.v1",
        "schema_version": seal.schema_version,
        "closure_id": seal.closure_id,
        "status": seal.status,
        "master_portfolio_id": seal.master_portfolio_id,
        "analysis_fingerprint_sha256": seal.analysis_fingerprint_sha256,
        "shadow_result_fingerprint_sha256": seal.shadow_result_fingerprint_sha256,
        "advisory_report_fingerprint_sha256": seal.advisory_report_fingerprint_sha256,
        "recommendation_fingerprint_sha256": seal.recommendation_fingerprint_sha256,
        "current_policy_fingerprint_sha256": seal.current_policy_fingerprint_sha256,
        "operator_decision_fingerprint_sha256": seal.operator_decision_fingerprint_sha256,
        "audit_fingerprint_sha256": seal.audit_fingerprint_sha256,
        "operator_review_action": seal.operator_review_action,
        "operator_review_status": seal.operator_review_status,
        "recommendation_action": seal.recommendation_action,
        "selected_candidate_id": seal.selected_candidate_id,
        "sealed_at": seal.sealed_at,
    }


@dataclass(frozen=True, slots=True)
class MasterProfessorAdvisoryClosureSeal:
    closure_id: str
    status: MasterProfessorAdvisoryClosureStatus
    master_portfolio_id: str
    analysis_fingerprint_sha256: str
    shadow_result_fingerprint_sha256: str
    advisory_report_fingerprint_sha256: str
    recommendation_fingerprint_sha256: str
    current_policy_fingerprint_sha256: str
    operator_decision_fingerprint_sha256: str
    audit_fingerprint_sha256: str
    operator_review_action: MasterProfessorOperatorReviewAction
    operator_review_status: MasterProfessorOperatorReviewStatus
    recommendation_action: MasterAllocationAdvisoryAction
    selected_candidate_id: str | None
    sealed_at: datetime
    closure_fingerprint_sha256: str
    advisory_only: bool = field(default=True, init=False)
    closure_only: bool = field(default=True, init=False)
    operator_review_completed: bool = field(default=True, init=False)
    allocation_application_performed: bool = field(default=False, init=False)
    allocation_application_authority: bool = field(default=False, init=False)
    policy_mutation: bool = field(default=False, init=False)
    reservation_authority: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("closure_id", "master_portfolio_id"):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), field_name=name),
            )
        for name in (
            "analysis_fingerprint_sha256",
            "shadow_result_fingerprint_sha256",
            "advisory_report_fingerprint_sha256",
            "recommendation_fingerprint_sha256",
            "current_policy_fingerprint_sha256",
            "operator_decision_fingerprint_sha256",
            "audit_fingerprint_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), field_name=name))
        if self.selected_candidate_id is not None:
            object.__setattr__(
                self,
                "selected_candidate_id",
                _required_text(self.selected_candidate_id, field_name="selected_candidate_id"),
            )
        object.__setattr__(self, "sealed_at", _utc(self.sealed_at, field_name="sealed_at"))
        if self.status is not MasterProfessorAdvisoryClosureStatus.SEALED:
            raise ValueError("Master Professor advisory closure status must be SEALED")
        if self.operator_review_status is not _review_status(self.operator_review_action):
            raise ValueError("Master Professor advisory closure review status mismatch")
        if self.recommendation_action is MasterAllocationAdvisoryAction.PROPOSE_CHANGE:
            if self.selected_candidate_id is None:
                raise ValueError("PROPOSE_CHANGE closure must preserve selected candidate identity")
        elif self.selected_candidate_id is not None:
            raise ValueError("non-change advisory closure cannot carry selected candidate")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master Professor advisory closure schema_version")
        normalized = _sha256(
            self.closure_fingerprint_sha256,
            field_name="closure_fingerprint_sha256",
        )
        if normalized != stable_digest(master_professor_advisory_closure_payload(self)):
            raise ValueError("Master Professor advisory closure fingerprint mismatch")
        object.__setattr__(self, "closure_fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_professor_advisory_closure_payload(self)


def seal_master_professor_advisory_review(
    *,
    audit: MasterProfessorAdvisoryAuditReport,
    operator_decision: MasterProfessorOperatorReviewDecision,
) -> MasterProfessorAdvisoryClosureSeal:
    if stable_digest(master_professor_advisory_audit_payload(audit)) != audit.fingerprint_sha256:
        raise ValueError("advisory closure audit fingerprint integrity failure")
    if stable_digest(master_professor_operator_review_payload(operator_decision)) != (
        operator_decision.fingerprint_sha256
    ):
        raise ValueError("advisory closure operator decision fingerprint integrity failure")
    if audit.status is not MasterProfessorAdvisoryAuditStatus.VERIFIED:
        raise ValueError("advisory closure requires VERIFIED audit")
    bindings = (
        (audit.master_portfolio_id, operator_decision.master_portfolio_id),
        (audit.analysis_fingerprint_sha256, operator_decision.analysis_fingerprint_sha256),
        (
            audit.shadow_result_fingerprint_sha256,
            operator_decision.shadow_result_fingerprint_sha256,
        ),
        (
            audit.advisory_report_fingerprint_sha256,
            operator_decision.advisory_report_fingerprint_sha256,
        ),
        (
            audit.recommendation_fingerprint_sha256,
            operator_decision.recommendation_fingerprint_sha256,
        ),
        (
            audit.current_policy_fingerprint_sha256,
            operator_decision.current_policy_fingerprint_sha256,
        ),
        (audit.operator_decision_fingerprint_sha256, operator_decision.fingerprint_sha256),
        (audit.operator_review_action, operator_decision.action),
        (audit.operator_review_status, operator_decision.status),
        (audit.recommendation_action, operator_decision.recommendation_action),
        (audit.selected_candidate_id, operator_decision.selected_candidate_id),
        (audit.reviewed_at, operator_decision.decided_at),
    )
    if any(left != right for left, right in bindings):
        raise ValueError("advisory closure audit/operator review provenance mismatch")
    values = {
        "status": MasterProfessorAdvisoryClosureStatus.SEALED,
        "master_portfolio_id": audit.master_portfolio_id,
        "analysis_fingerprint_sha256": audit.analysis_fingerprint_sha256,
        "shadow_result_fingerprint_sha256": audit.shadow_result_fingerprint_sha256,
        "advisory_report_fingerprint_sha256": audit.advisory_report_fingerprint_sha256,
        "recommendation_fingerprint_sha256": audit.recommendation_fingerprint_sha256,
        "current_policy_fingerprint_sha256": audit.current_policy_fingerprint_sha256,
        "operator_decision_fingerprint_sha256": operator_decision.fingerprint_sha256,
        "audit_fingerprint_sha256": audit.fingerprint_sha256,
        "operator_review_action": operator_decision.action,
        "operator_review_status": operator_decision.status,
        "recommendation_action": operator_decision.recommendation_action,
        "selected_candidate_id": operator_decision.selected_candidate_id,
        "sealed_at": operator_decision.decided_at,
    }
    closure_id = "master-professor-advisory-closure:" + stable_digest(
        {
            "schema": "money-heist.master-professor-advisory-closure-id.v1",
            **values,
        }
    )
    provisional = MasterProfessorAdvisoryClosureSeal.__new__(
        MasterProfessorAdvisoryClosureSeal
    )
    object.__setattr__(provisional, "closure_id", closure_id)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterProfessorAdvisoryClosureSeal(
        closure_id=closure_id,
        **values,
        closure_fingerprint_sha256=stable_digest(
            master_professor_advisory_closure_payload(provisional)
        ),
    )


__all__ = [
    "MasterProfessorAdvisoryAuditReport",
    "MasterProfessorAdvisoryAuditStatus",
    "MasterProfessorAdvisoryClosureSeal",
    "MasterProfessorAdvisoryClosureStatus",
    "MasterProfessorOperatorReviewAction",
    "MasterProfessorOperatorReviewDecision",
    "MasterProfessorOperatorReviewStatus",
    "audit_master_professor_advisory_review",
    "build_master_professor_operator_review_decision",
    "master_professor_advisory_audit_payload",
    "master_professor_advisory_closure_payload",
    "master_professor_operator_review_payload",
    "seal_master_professor_advisory_review",
]
