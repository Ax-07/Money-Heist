from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .allocation import (
    AllocationEnvelopeStatus,
    CrewAllocationEnvelope,
    MasterAllocationPolicy,
    master_allocation_policy_fingerprint,
)
from .historical_replay_closure import (
    MasterHistoricalReplayAuditReport,
    MasterHistoricalReplayAuditStatus,
    MasterHistoricalReplayClosureSeal,
    MasterHistoricalReplayClosureStatus,
    master_historical_replay_audit_payload,
    master_historical_replay_closure_payload,
)
from .historical_replay_master_runner import (
    MasterHistoricalEvaluation,
    master_historical_evaluation_payload,
)


class MasterAllocationAdvisoryAction(StrEnum):
    KEEP_CURRENT = "KEEP_CURRENT"
    PROPOSE_CHANGE = "PROPOSE_CHANGE"
    ABSTAIN = "ABSTAIN"


class MasterAllocationAdvisoryStatus(StrEnum):
    READY_FOR_OPERATOR_REVIEW = "READY_FOR_OPERATOR_REVIEW"
    ABSTAINED = "ABSTAINED"


class MasterAllocationAdvisoryEvidenceSource(StrEnum):
    SEALED_MASTER_HISTORICAL_REPLAY = "SEALED_MASTER_HISTORICAL_REPLAY"


def _required_text(value: object, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank when provided")
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


def master_allocation_advisory_evidence_payload(
    evidence: MasterAllocationAdvisoryEvidence,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-advisory-evidence.v1",
        "schema_version": evidence.schema_version,
        "evidence_id": evidence.evidence_id,
        "source": evidence.source,
        "master_portfolio_id": evidence.master_portfolio_id,
        "audit_fingerprint_sha256": evidence.audit_report.fingerprint_sha256,
        "closure_fingerprint_sha256": (
            evidence.closure_seal.closure_fingerprint_sha256
        ),
        "evaluation_fingerprint_sha256": evidence.evaluation.fingerprint_sha256,
        "crew_system_ids": evidence.crew_system_ids,
        "sealed_at": evidence.sealed_at,
        "regime_label": evidence.regime_label,
        "regime_source_ref": evidence.regime_source_ref,
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationAdvisoryEvidence:
    evidence_id: str
    audit_report: MasterHistoricalReplayAuditReport
    closure_seal: MasterHistoricalReplayClosureSeal
    evaluation: MasterHistoricalEvaluation
    regime_label: str | None
    regime_source_ref: str | None
    fingerprint_sha256: str
    source: MasterAllocationAdvisoryEvidenceSource = field(
        default=MasterAllocationAdvisoryEvidenceSource.SEALED_MASTER_HISTORICAL_REPLAY,
        init=False,
    )
    advisory_only: bool = field(default=True, init=False)
    mutation_applied: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence_id",
            _required_text(self.evidence_id, field_name="evidence_id"),
        )
        object.__setattr__(
            self,
            "regime_label",
            _optional_text(self.regime_label, field_name="regime_label"),
        )
        object.__setattr__(
            self,
            "regime_source_ref",
            _optional_text(self.regime_source_ref, field_name="regime_source_ref"),
        )
        if (self.regime_label is None) != (self.regime_source_ref is None):
            raise ValueError("regime_label and regime_source_ref must be supplied together")
        self._validate_source_chain()
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master allocation advisory evidence schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_allocation_advisory_evidence_payload(self))
        if normalized != expected:
            raise ValueError("Master allocation advisory evidence fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    @property
    def master_portfolio_id(self) -> str:
        return self.closure_seal.master_portfolio_id

    @property
    def sealed_at(self) -> datetime:
        return self.closure_seal.sealed_at

    @property
    def crew_system_ids(self) -> tuple[str, ...]:
        return tuple(item.system_id for item in self.evaluation.crew_evaluations)

    def _validate_source_chain(self) -> None:
        audit = self.audit_report
        closure = self.closure_seal
        evaluation = self.evaluation
        if audit.status is not MasterHistoricalReplayAuditStatus.VERIFIED:
            raise ValueError("allocation advisory evidence requires VERIFIED historical audit")
        if closure.status is not MasterHistoricalReplayClosureStatus.SEALED:
            raise ValueError("allocation advisory evidence requires SEALED historical closure")
        if stable_digest(master_historical_replay_audit_payload(audit)) != audit.fingerprint_sha256:
            raise ValueError("allocation advisory audit fingerprint integrity failure")
        if stable_digest(master_historical_replay_closure_payload(closure)) != (
            closure.closure_fingerprint_sha256
        ):
            raise ValueError("allocation advisory closure fingerprint integrity failure")
        if stable_digest(master_historical_evaluation_payload(evaluation)) != (
            evaluation.fingerprint_sha256
        ):
            raise ValueError("allocation advisory evaluation fingerprint integrity failure")
        master_ids = {
            audit.master_portfolio_id,
            closure.master_portfolio_id,
            evaluation.master_portfolio_id,
        }
        if len(master_ids) != 1:
            raise ValueError("allocation advisory evidence spans multiple Master Portfolios")
        identity_pairs = (
            (audit.plan_id, closure.plan_id),
            (audit.timeline_id, closure.timeline_id),
            (audit.result_id, closure.result_id),
            (audit.result_fingerprint_sha256, closure.result_fingerprint_sha256),
            (audit.fingerprint_sha256, closure.audit_fingerprint_sha256),
            (audit.evaluation_fingerprint_sha256, evaluation.fingerprint_sha256),
            (closure.evaluation_fingerprint_sha256, evaluation.fingerprint_sha256),
        )
        if any(left != right for left, right in identity_pairs):
            raise ValueError("allocation advisory historical evidence provenance mismatch")
        crew_ids = self.crew_system_ids
        if not crew_ids:
            raise ValueError("allocation advisory evidence requires at least one crew")
        if crew_ids != tuple(sorted(crew_ids)) or len(set(crew_ids)) != len(crew_ids):
            raise ValueError("allocation advisory evidence crews must be sorted and unique")
        if evaluation.single_master_capital is not True or evaluation.branch_equities_summed:
            raise ValueError("allocation advisory evidence violates single Master capital")
        for authority_name in ("risk_authority", "admission_authority", "live_authority"):
            if getattr(evaluation, authority_name):
                raise ValueError("allocation advisory evidence carries forbidden authority")

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_advisory_evidence_payload(self)


def build_master_allocation_advisory_evidence(
    *,
    audit_report: MasterHistoricalReplayAuditReport,
    closure_seal: MasterHistoricalReplayClosureSeal,
    evaluation: MasterHistoricalEvaluation,
    regime_label: str | None = None,
    regime_source_ref: str | None = None,
) -> MasterAllocationAdvisoryEvidence:
    normalized_label = _optional_text(regime_label, field_name="regime_label")
    normalized_ref = _optional_text(regime_source_ref, field_name="regime_source_ref")
    if (normalized_label is None) != (normalized_ref is None):
        raise ValueError("regime_label and regime_source_ref must be supplied together")
    evidence_id = "master-allocation-evidence:" + stable_digest(
        {
            "schema": "money-heist.master-allocation-advisory-evidence-id.v1",
            "audit_fingerprint_sha256": audit_report.fingerprint_sha256,
            "closure_fingerprint_sha256": closure_seal.closure_fingerprint_sha256,
            "evaluation_fingerprint_sha256": evaluation.fingerprint_sha256,
            "regime_label": normalized_label,
            "regime_source_ref": normalized_ref,
        }
    )
    provisional = MasterAllocationAdvisoryEvidence.__new__(MasterAllocationAdvisoryEvidence)
    object.__setattr__(provisional, "evidence_id", evidence_id)
    object.__setattr__(provisional, "audit_report", audit_report)
    object.__setattr__(provisional, "closure_seal", closure_seal)
    object.__setattr__(provisional, "evaluation", evaluation)
    object.__setattr__(provisional, "regime_label", normalized_label)
    object.__setattr__(provisional, "regime_source_ref", normalized_ref)
    object.__setattr__(
        provisional,
        "source",
        MasterAllocationAdvisoryEvidenceSource.SEALED_MASTER_HISTORICAL_REPLAY,
    )
    object.__setattr__(provisional, "schema_version", "1.0")
    fingerprint = stable_digest(master_allocation_advisory_evidence_payload(provisional))
    return MasterAllocationAdvisoryEvidence(
        evidence_id=evidence_id,
        audit_report=audit_report,
        closure_seal=closure_seal,
        evaluation=evaluation,
        regime_label=normalized_label,
        regime_source_ref=normalized_ref,
        fingerprint_sha256=fingerprint,
    )


def master_allocation_advisory_recommendation_payload(
    recommendation: MasterAllocationAdvisoryRecommendation,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-advisory-recommendation.v1",
        "schema_version": recommendation.schema_version,
        "action": recommendation.action,
        "proposed_envelopes": [
            item.canonical_payload() for item in recommendation.proposed_envelopes
        ],
        "rationale_codes": recommendation.rationale_codes,
        "source_ref": recommendation.source_ref,
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationAdvisoryRecommendation:
    action: MasterAllocationAdvisoryAction
    proposed_envelopes: tuple[CrewAllocationEnvelope, ...]
    rationale_codes: tuple[str, ...]
    source_ref: str
    fingerprint_sha256: str
    advisor_role: str = field(default="MASTER_PROFESSOR", init=False)
    mode: str = field(default="SHADOW", init=False)
    advisory_only: bool = field(default=True, init=False)
    operator_review_required: bool = field(default=True, init=False)
    auto_apply: bool = field(default=False, init=False)
    policy_mutation: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_ref",
            _required_text(self.source_ref, field_name="source_ref"),
        )
        normalized_reasons = tuple(
            _required_text(value, field_name="rationale_codes") for value in self.rationale_codes
        )
        if normalized_reasons != tuple(sorted(normalized_reasons)):
            raise ValueError("allocation advisory rationale_codes must be sorted")
        if len(set(normalized_reasons)) != len(normalized_reasons):
            raise ValueError("allocation advisory rationale_codes must be unique")
        if not normalized_reasons:
            raise ValueError("allocation advisory recommendation requires rationale_codes")
        object.__setattr__(self, "rationale_codes", normalized_reasons)
        envelope_ids = tuple(item.system_id for item in self.proposed_envelopes)
        if envelope_ids != tuple(sorted(envelope_ids)):
            raise ValueError("allocation advisory envelopes must be sorted by system_id")
        if len(set(envelope_ids)) != len(envelope_ids):
            raise ValueError("allocation advisory envelopes must be unique by system_id")
        if self.action is MasterAllocationAdvisoryAction.ABSTAIN:
            if self.proposed_envelopes:
                raise ValueError("ABSTAIN allocation advisory cannot propose envelopes")
        else:
            if not self.proposed_envelopes:
                raise ValueError("non-abstaining allocation advisory requires proposed envelopes")
            if any(
                item.status is not AllocationEnvelopeStatus.CONFIGURED
                for item in self.proposed_envelopes
            ):
                raise ValueError("allocation advisory proposed envelopes must be CONFIGURED")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master allocation advisory recommendation schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_allocation_advisory_recommendation_payload(self))
        if normalized != expected:
            raise ValueError("Master allocation advisory recommendation fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_advisory_recommendation_payload(self)


def build_master_allocation_advisory_recommendation(
    *,
    action: MasterAllocationAdvisoryAction,
    proposed_envelopes: tuple[CrewAllocationEnvelope, ...] = (),
    rationale_codes: tuple[str, ...],
    source_ref: str,
) -> MasterAllocationAdvisoryRecommendation:
    ordered_envelopes = tuple(sorted(proposed_envelopes, key=lambda item: item.system_id))
    ordered_reasons = tuple(sorted(rationale_codes))
    normalized_source = _required_text(source_ref, field_name="source_ref")
    provisional = MasterAllocationAdvisoryRecommendation.__new__(
        MasterAllocationAdvisoryRecommendation
    )
    object.__setattr__(provisional, "action", action)
    object.__setattr__(provisional, "proposed_envelopes", ordered_envelopes)
    object.__setattr__(provisional, "rationale_codes", ordered_reasons)
    object.__setattr__(provisional, "source_ref", normalized_source)
    object.__setattr__(provisional, "schema_version", "1.0")
    fingerprint = stable_digest(master_allocation_advisory_recommendation_payload(provisional))
    return MasterAllocationAdvisoryRecommendation(
        action=action,
        proposed_envelopes=ordered_envelopes,
        rationale_codes=ordered_reasons,
        source_ref=normalized_source,
        fingerprint_sha256=fingerprint,
    )


def master_allocation_advisory_report_payload(
    report: MasterAllocationAdvisoryReport,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-advisory-report.v1",
        "schema_version": report.schema_version,
        "report_id": report.report_id,
        "status": report.status,
        "master_portfolio_id": report.master_portfolio_id,
        "current_policy_fingerprint_sha256": (
            report.current_allocation_policy.fingerprint_sha256
        ),
        "evidence_through": report.evidence_through,
        "evidence_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in report.evidence
        ),
        "recommendation_fingerprint_sha256": report.recommendation.fingerprint_sha256,
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationAdvisoryReport:
    report_id: str
    status: MasterAllocationAdvisoryStatus
    master_portfolio_id: str
    current_allocation_policy: MasterAllocationPolicy
    evidence_through: datetime | None
    evidence: tuple[MasterAllocationAdvisoryEvidence, ...]
    recommendation: MasterAllocationAdvisoryRecommendation
    fingerprint_sha256: str
    advisor_role: str = field(default="MASTER_PROFESSOR", init=False)
    mode: str = field(default="SHADOW", init=False)
    advisory_only: bool = field(default=True, init=False)
    operator_review_required: bool = field(default=True, init=False)
    auto_apply: bool = field(default=False, init=False)
    policy_mutation: bool = field(default=False, init=False)
    dynamic_allocation_authority: bool = field(default=False, init=False)
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
        object.__setattr__(
            self,
            "report_id",
            _required_text(self.report_id, field_name="report_id"),
        )
        object.__setattr__(
            self,
            "master_portfolio_id",
            _required_text(self.master_portfolio_id, field_name="master_portfolio_id"),
        )
        if self.evidence_through is not None:
            object.__setattr__(
                self,
                "evidence_through",
                _utc(self.evidence_through, field_name="evidence_through"),
            )
        self._validate_context()
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master allocation advisory report schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_allocation_advisory_report_payload(self))
        if normalized != expected:
            raise ValueError("Master allocation advisory report fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def _validate_context(self) -> None:
        policy = self.current_allocation_policy
        if policy.master_portfolio_id != self.master_portfolio_id:
            raise ValueError("allocation advisory current policy Master Portfolio mismatch")
        if _policy_fingerprint(policy) != policy.fingerprint_sha256:
            raise ValueError("allocation advisory current policy fingerprint integrity failure")
        evidence_keys = tuple(
            (item.sealed_at, item.evidence_id) for item in self.evidence
        )
        if evidence_keys != tuple(sorted(evidence_keys)):
            raise ValueError("allocation advisory evidence must be canonical")
        evidence_fingerprints = tuple(item.fingerprint_sha256 for item in self.evidence)
        if len(set(evidence_fingerprints)) != len(evidence_fingerprints):
            raise ValueError("allocation advisory evidence must be unique")
        policy_ids = tuple(member.system_id for member in policy.members)
        for item in self.evidence:
            if item.master_portfolio_id != self.master_portfolio_id:
                raise ValueError("allocation advisory evidence Master Portfolio mismatch")
            if item.crew_system_ids != policy_ids:
                raise ValueError("allocation advisory evidence membership mismatch")
        expected_through = max((item.sealed_at for item in self.evidence), default=None)
        if self.evidence_through != expected_through:
            raise ValueError("allocation advisory evidence_through mismatch")
        recommendation = self.recommendation
        expected_status = (
            MasterAllocationAdvisoryStatus.ABSTAINED
            if recommendation.action is MasterAllocationAdvisoryAction.ABSTAIN
            else MasterAllocationAdvisoryStatus.READY_FOR_OPERATOR_REVIEW
        )
        if self.status is not expected_status:
            raise ValueError("allocation advisory report status does not match recommendation")
        if (
            not self.evidence
            and recommendation.action is not MasterAllocationAdvisoryAction.ABSTAIN
        ):
            raise ValueError("allocation advisory cannot recommend changes without evidence")
        if (
            policy.status is not AllocationEnvelopeStatus.CONFIGURED
            and recommendation.action is not MasterAllocationAdvisoryAction.ABSTAIN
        ):
            raise ValueError("unconfigured allocation policy requires advisory abstention")
        if recommendation.action is MasterAllocationAdvisoryAction.ABSTAIN:
            return
        proposal_ids = tuple(item.system_id for item in recommendation.proposed_envelopes)
        if proposal_ids != policy_ids:
            raise ValueError("allocation advisory must preserve exact crew membership")
        current_payloads = tuple(item.canonical_payload() for item in policy.envelopes)
        proposed_payloads = tuple(
            item.canonical_payload() for item in recommendation.proposed_envelopes
        )
        if recommendation.action is MasterAllocationAdvisoryAction.KEEP_CURRENT:
            if proposed_payloads != current_payloads:
                raise ValueError("KEEP_CURRENT must reproduce current allocation envelopes")
        elif recommendation.action is MasterAllocationAdvisoryAction.PROPOSE_CHANGE:
            if proposed_payloads == current_payloads:
                raise ValueError("PROPOSE_CHANGE must actually change an allocation envelope")
        else:
            raise ValueError(f"unsupported allocation advisory action: {recommendation.action}")

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_advisory_report_payload(self)


def build_master_allocation_advisory_report(
    *,
    current_allocation_policy: MasterAllocationPolicy,
    evidence: tuple[MasterAllocationAdvisoryEvidence, ...],
    recommendation: MasterAllocationAdvisoryRecommendation,
) -> MasterAllocationAdvisoryReport:
    ordered_evidence = tuple(sorted(evidence, key=lambda item: (item.sealed_at, item.evidence_id)))
    evidence_through = max((item.sealed_at for item in ordered_evidence), default=None)
    status = (
        MasterAllocationAdvisoryStatus.ABSTAINED
        if recommendation.action is MasterAllocationAdvisoryAction.ABSTAIN
        else MasterAllocationAdvisoryStatus.READY_FOR_OPERATOR_REVIEW
    )
    master_portfolio_id = current_allocation_policy.master_portfolio_id
    report_id = "master-allocation-advisory:" + stable_digest(
        {
            "schema": "money-heist.master-allocation-advisory-report-id.v1",
            "master_portfolio_id": master_portfolio_id,
            "current_policy_fingerprint_sha256": (
                current_allocation_policy.fingerprint_sha256
            ),
            "evidence_fingerprints_sha256": tuple(
                item.fingerprint_sha256 for item in ordered_evidence
            ),
            "recommendation_fingerprint_sha256": recommendation.fingerprint_sha256,
        }
    )
    provisional = MasterAllocationAdvisoryReport.__new__(MasterAllocationAdvisoryReport)
    object.__setattr__(provisional, "report_id", report_id)
    object.__setattr__(provisional, "status", status)
    object.__setattr__(provisional, "master_portfolio_id", master_portfolio_id)
    object.__setattr__(provisional, "current_allocation_policy", current_allocation_policy)
    object.__setattr__(provisional, "evidence_through", evidence_through)
    object.__setattr__(provisional, "evidence", ordered_evidence)
    object.__setattr__(provisional, "recommendation", recommendation)
    object.__setattr__(provisional, "schema_version", "1.0")
    fingerprint = stable_digest(master_allocation_advisory_report_payload(provisional))
    return MasterAllocationAdvisoryReport(
        report_id=report_id,
        status=status,
        master_portfolio_id=master_portfolio_id,
        current_allocation_policy=current_allocation_policy,
        evidence_through=evidence_through,
        evidence=ordered_evidence,
        recommendation=recommendation,
        fingerprint_sha256=fingerprint,
    )


__all__ = [
    "MasterAllocationAdvisoryAction",
    "MasterAllocationAdvisoryEvidence",
    "MasterAllocationAdvisoryEvidenceSource",
    "MasterAllocationAdvisoryRecommendation",
    "MasterAllocationAdvisoryReport",
    "MasterAllocationAdvisoryStatus",
    "build_master_allocation_advisory_evidence",
    "build_master_allocation_advisory_recommendation",
    "build_master_allocation_advisory_report",
    "master_allocation_advisory_evidence_payload",
    "master_allocation_advisory_recommendation_payload",
    "master_allocation_advisory_report_payload",
]
