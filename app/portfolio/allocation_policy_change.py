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
from .allocation_advisory import (
    MasterAllocationAdvisoryAction,
    master_allocation_advisory_recommendation_payload,
    master_allocation_advisory_report_payload,
)
from .allocation_advisory_review_closure import (
    MasterProfessorAdvisoryAuditReport,
    MasterProfessorAdvisoryAuditStatus,
    MasterProfessorAdvisoryClosureSeal,
    MasterProfessorAdvisoryClosureStatus,
    MasterProfessorOperatorReviewAction,
    MasterProfessorOperatorReviewDecision,
    MasterProfessorOperatorReviewStatus,
    master_professor_advisory_closure_payload,
    master_professor_operator_review_payload,
    seal_master_professor_advisory_review,
)
from .allocation_master_professor_shadow import (
    MasterProfessorAllocationCandidate,
    MasterProfessorShadowAdvisoryResult,
    MasterProfessorShadowStatus,
    master_professor_allocation_candidate_payload,
    master_professor_shadow_result_payload,
)


class MasterAllocationPolicyChangeCandidateStatus(StrEnum):
    READY_FOR_OPERATOR_AUTHORIZATION = "READY_FOR_OPERATOR_AUTHORIZATION"


class MasterAllocationPolicyChangeCandidateSource(StrEnum):
    ACCEPTED_SEALED_MASTER_PROFESSOR_ADVISORY = (
        "ACCEPTED_SEALED_MASTER_PROFESSOR_ADVISORY"
    )


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


def master_allocation_policy_change_candidate_payload(
    candidate: MasterAllocationPolicyChangeCandidate,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-policy-change-candidate.v1",
        "schema_version": candidate.schema_version,
        "change_candidate_id": candidate.change_candidate_id,
        "status": candidate.status,
        "source": candidate.source,
        "master_portfolio_id": candidate.master_portfolio_id,
        "base_policy_id": candidate.base_policy_id,
        "base_policy_fingerprint_sha256": candidate.base_policy_fingerprint_sha256,
        "selected_operator_candidate_id": candidate.selected_operator_candidate_id,
        "selected_operator_candidate_fingerprint_sha256": (
            candidate.selected_operator_candidate_fingerprint_sha256
        ),
        "selected_operator_candidate_source_ref": (
            candidate.selected_operator_candidate_source_ref
        ),
        "proposed_envelopes": [
            envelope.canonical_payload() for envelope in candidate.proposed_envelopes
        ],
        "shadow_result_fingerprint_sha256": candidate.shadow_result_fingerprint_sha256,
        "recommendation_fingerprint_sha256": candidate.recommendation_fingerprint_sha256,
        "operator_decision_fingerprint_sha256": candidate.operator_decision_fingerprint_sha256,
        "advisory_audit_fingerprint_sha256": candidate.advisory_audit_fingerprint_sha256,
        "advisory_closure_fingerprint_sha256": candidate.advisory_closure_fingerprint_sha256,
        "operator_ref": candidate.operator_ref,
        "reviewed_at": candidate.reviewed_at,
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationPolicyChangeCandidate:
    """Immutable, non-applying candidate derived from one accepted sealed SHADOW advisory."""

    change_candidate_id: str
    status: MasterAllocationPolicyChangeCandidateStatus
    master_portfolio_id: str
    base_policy_id: str
    base_policy_fingerprint_sha256: str
    selected_operator_candidate_id: str
    selected_operator_candidate_fingerprint_sha256: str
    selected_operator_candidate_source_ref: str
    proposed_envelopes: tuple[CrewAllocationEnvelope, ...]
    shadow_result_fingerprint_sha256: str
    recommendation_fingerprint_sha256: str
    operator_decision_fingerprint_sha256: str
    advisory_audit_fingerprint_sha256: str
    advisory_closure_fingerprint_sha256: str
    operator_ref: str
    reviewed_at: datetime
    fingerprint_sha256: str
    source: MasterAllocationPolicyChangeCandidateSource = field(
        default=(
            MasterAllocationPolicyChangeCandidateSource.ACCEPTED_SEALED_MASTER_PROFESSOR_ADVISORY
        ),
        init=False,
    )
    candidate_only: bool = field(default=True, init=False)
    explicit_policy_application_authorization_required: bool = field(default=True, init=False)
    policy_application_performed: bool = field(default=False, init=False)
    policy_application_authority: bool = field(default=False, init=False)
    auto_apply: bool = field(default=False, init=False)
    dynamic_allocation_enabled: bool = field(default=False, init=False)
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
        for name in (
            "change_candidate_id",
            "master_portfolio_id",
            "base_policy_id",
            "selected_operator_candidate_id",
            "selected_operator_candidate_source_ref",
            "operator_ref",
        ):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), field_name=name),
            )
        for name in (
            "base_policy_fingerprint_sha256",
            "selected_operator_candidate_fingerprint_sha256",
            "shadow_result_fingerprint_sha256",
            "recommendation_fingerprint_sha256",
            "operator_decision_fingerprint_sha256",
            "advisory_audit_fingerprint_sha256",
            "advisory_closure_fingerprint_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), field_name=name))
        object.__setattr__(self, "reviewed_at", _utc(self.reviewed_at, field_name="reviewed_at"))
        expected_status = (
            MasterAllocationPolicyChangeCandidateStatus.READY_FOR_OPERATOR_AUTHORIZATION
        )
        if self.status is not expected_status:
            raise ValueError(
                "allocation policy change candidate status must be ready for authorization"
            )
        if not self.proposed_envelopes:
            raise ValueError("allocation policy change candidate requires proposed envelopes")
        system_ids = tuple(item.system_id for item in self.proposed_envelopes)
        if system_ids != tuple(sorted(system_ids)):
            raise ValueError("allocation policy change candidate envelopes must be sorted")
        if len(set(system_ids)) != len(system_ids):
            raise ValueError("allocation policy change candidate envelopes must be unique")
        if any(
            item.status is not AllocationEnvelopeStatus.CONFIGURED
            for item in self.proposed_envelopes
        ):
            raise ValueError("allocation policy change candidate envelopes must be CONFIGURED")
        if self.schema_version != "1.0":
            raise ValueError("unsupported allocation policy change candidate schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        if normalized != stable_digest(master_allocation_policy_change_candidate_payload(self)):
            raise ValueError("allocation policy change candidate fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_policy_change_candidate_payload(self)


def _validate_selected_candidate(
    *,
    current_allocation_policy: MasterAllocationPolicy,
    selected_operator_candidate: MasterProfessorAllocationCandidate,
    shadow_result: MasterProfessorShadowAdvisoryResult,
) -> tuple[CrewAllocationEnvelope, ...]:
    selected_payload = master_professor_allocation_candidate_payload(
        selected_operator_candidate
    )
    if stable_digest(selected_payload) != selected_operator_candidate.fingerprint_sha256:
        raise ValueError("selected operator allocation candidate fingerprint integrity failure")
    output = shadow_result.output
    recommendation = shadow_result.advisory_report.recommendation
    if output.selected_candidate_id != selected_operator_candidate.candidate_id:
        raise ValueError("selected operator allocation candidate identity mismatch")
    if selected_operator_candidate.fingerprint_sha256 not in (
        shadow_result.candidate_fingerprints_sha256
    ):
        raise ValueError("selected operator allocation candidate is outside Step 3 candidate set")
    if recommendation.proposed_envelopes != selected_operator_candidate.proposed_envelopes:
        raise ValueError("selected operator allocation candidate envelopes mismatch recommendation")
    member_ids = tuple(member.system_id for member in current_allocation_policy.members)
    proposed_ids = tuple(item.system_id for item in selected_operator_candidate.proposed_envelopes)
    if proposed_ids != member_ids:
        raise ValueError("allocation policy change candidate must preserve exact crew membership")
    current_payloads = tuple(
        item.canonical_payload() for item in current_allocation_policy.envelopes
    )
    proposed_payloads = tuple(
        item.canonical_payload() for item in selected_operator_candidate.proposed_envelopes
    )
    if proposed_payloads == current_payloads:
        raise ValueError("allocation policy change candidate must differ from current policy")
    return selected_operator_candidate.proposed_envelopes


def _validate_review_chain(
    *,
    current_allocation_policy: MasterAllocationPolicy,
    shadow_result: MasterProfessorShadowAdvisoryResult,
    operator_decision: MasterProfessorOperatorReviewDecision,
    advisory_audit: MasterProfessorAdvisoryAuditReport,
    advisory_closure: MasterProfessorAdvisoryClosureSeal,
) -> None:
    if _policy_fingerprint(current_allocation_policy) != (
        current_allocation_policy.fingerprint_sha256
    ):
        raise ValueError("allocation policy change base policy fingerprint integrity failure")
    if current_allocation_policy.status is not AllocationEnvelopeStatus.CONFIGURED:
        raise ValueError("allocation policy change requires CONFIGURED current policy")
    if stable_digest(master_professor_shadow_result_payload(shadow_result)) != (
        shadow_result.fingerprint_sha256
    ):
        raise ValueError("allocation policy change SHADOW result fingerprint integrity failure")
    if shadow_result.status is not MasterProfessorShadowStatus.COMPLETED:
        raise ValueError("allocation policy change requires completed SHADOW result")
    report = shadow_result.advisory_report
    if stable_digest(master_allocation_advisory_report_payload(report)) != (
        report.fingerprint_sha256
    ):
        raise ValueError("allocation policy change advisory report fingerprint integrity failure")
    recommendation = report.recommendation
    if stable_digest(master_allocation_advisory_recommendation_payload(recommendation)) != (
        recommendation.fingerprint_sha256
    ):
        raise ValueError("allocation policy change recommendation fingerprint integrity failure")
    if recommendation.action is not MasterAllocationAdvisoryAction.PROPOSE_CHANGE:
        raise ValueError("allocation policy change requires PROPOSE_CHANGE recommendation")
    if report.current_allocation_policy.fingerprint_sha256 != (
        current_allocation_policy.fingerprint_sha256
    ):
        raise ValueError("allocation policy change current policy provenance mismatch")
    if shadow_result.current_policy_fingerprint_sha256 != (
        current_allocation_policy.fingerprint_sha256
    ):
        raise ValueError("allocation policy change Step 3 base policy mismatch")
    if stable_digest(master_professor_operator_review_payload(operator_decision)) != (
        operator_decision.fingerprint_sha256
    ):
        raise ValueError("allocation policy change operator decision fingerprint integrity failure")
    if operator_decision.action is not MasterProfessorOperatorReviewAction.ACCEPT:
        raise ValueError("allocation policy change requires operator ACCEPT")
    if operator_decision.status is not MasterProfessorOperatorReviewStatus.ACCEPTED:
        raise ValueError("allocation policy change requires ACCEPTED operator review")
    if operator_decision.recommendation_action is not MasterAllocationAdvisoryAction.PROPOSE_CHANGE:
        raise ValueError("allocation policy change operator review must bind PROPOSE_CHANGE")
    if advisory_audit.status is not MasterProfessorAdvisoryAuditStatus.VERIFIED:
        raise ValueError("allocation policy change requires VERIFIED advisory audit")
    rebuilt_closure = seal_master_professor_advisory_review(
        audit=advisory_audit,
        operator_decision=operator_decision,
    )
    if advisory_closure.status is not MasterProfessorAdvisoryClosureStatus.SEALED:
        raise ValueError("allocation policy change requires SEALED advisory closure")
    if stable_digest(master_professor_advisory_closure_payload(advisory_closure)) != (
        advisory_closure.closure_fingerprint_sha256
    ):
        raise ValueError("allocation policy change advisory closure fingerprint integrity failure")
    if rebuilt_closure != advisory_closure:
        raise ValueError("allocation policy change advisory closure provenance mismatch")
    bindings = (
        (operator_decision.shadow_result_fingerprint_sha256, shadow_result.fingerprint_sha256),
        (
            operator_decision.current_policy_fingerprint_sha256,
            current_allocation_policy.fingerprint_sha256,
        ),
        (
            operator_decision.recommendation_fingerprint_sha256,
            recommendation.fingerprint_sha256,
        ),
        (advisory_closure.shadow_result_fingerprint_sha256, shadow_result.fingerprint_sha256),
        (
            advisory_closure.current_policy_fingerprint_sha256,
            current_allocation_policy.fingerprint_sha256,
        ),
        (
            advisory_closure.recommendation_fingerprint_sha256,
            recommendation.fingerprint_sha256,
        ),
    )
    if any(left != right for left, right in bindings):
        raise ValueError("allocation policy change accepted advisory provenance mismatch")


def build_master_allocation_policy_change_candidate(
    *,
    current_allocation_policy: MasterAllocationPolicy,
    selected_operator_candidate: MasterProfessorAllocationCandidate,
    shadow_result: MasterProfessorShadowAdvisoryResult,
    operator_decision: MasterProfessorOperatorReviewDecision,
    advisory_audit: MasterProfessorAdvisoryAuditReport,
    advisory_closure: MasterProfessorAdvisoryClosureSeal,
) -> MasterAllocationPolicyChangeCandidate:
    """Prepare one immutable policy-change candidate without applying a policy mutation."""

    _validate_review_chain(
        current_allocation_policy=current_allocation_policy,
        shadow_result=shadow_result,
        operator_decision=operator_decision,
        advisory_audit=advisory_audit,
        advisory_closure=advisory_closure,
    )
    proposed_envelopes = _validate_selected_candidate(
        current_allocation_policy=current_allocation_policy,
        selected_operator_candidate=selected_operator_candidate,
        shadow_result=shadow_result,
    )
    if operator_decision.selected_candidate_id != selected_operator_candidate.candidate_id:
        raise ValueError("allocation policy change operator review candidate identity mismatch")
    if advisory_closure.selected_candidate_id != selected_operator_candidate.candidate_id:
        raise ValueError("allocation policy change closure candidate identity mismatch")
    values = {
        "status": MasterAllocationPolicyChangeCandidateStatus.READY_FOR_OPERATOR_AUTHORIZATION,
        "master_portfolio_id": current_allocation_policy.master_portfolio_id,
        "base_policy_id": current_allocation_policy.policy_id,
        "base_policy_fingerprint_sha256": current_allocation_policy.fingerprint_sha256,
        "selected_operator_candidate_id": selected_operator_candidate.candidate_id,
        "selected_operator_candidate_fingerprint_sha256": (
            selected_operator_candidate.fingerprint_sha256
        ),
        "selected_operator_candidate_source_ref": selected_operator_candidate.source_ref,
        "proposed_envelopes": proposed_envelopes,
        "shadow_result_fingerprint_sha256": shadow_result.fingerprint_sha256,
        "recommendation_fingerprint_sha256": shadow_result.recommendation_fingerprint_sha256,
        "operator_decision_fingerprint_sha256": operator_decision.fingerprint_sha256,
        "advisory_audit_fingerprint_sha256": advisory_audit.fingerprint_sha256,
        "advisory_closure_fingerprint_sha256": advisory_closure.closure_fingerprint_sha256,
        "operator_ref": operator_decision.operator_ref,
        "reviewed_at": advisory_closure.sealed_at,
    }
    change_candidate_id = "master-allocation-policy-change:" + stable_digest(
        {
            "schema": "money-heist.master-allocation-policy-change-candidate-id.v1",
            **values,
        }
    )
    provisional = MasterAllocationPolicyChangeCandidate.__new__(
        MasterAllocationPolicyChangeCandidate
    )
    object.__setattr__(provisional, "change_candidate_id", change_candidate_id)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(
        provisional,
        "source",
        MasterAllocationPolicyChangeCandidateSource.ACCEPTED_SEALED_MASTER_PROFESSOR_ADVISORY,
    )
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterAllocationPolicyChangeCandidate(
        change_candidate_id=change_candidate_id,
        **values,
        fingerprint_sha256=stable_digest(
            master_allocation_policy_change_candidate_payload(provisional)
        ),
    )


__all__ = [
    "MasterAllocationPolicyChangeCandidate",
    "MasterAllocationPolicyChangeCandidateSource",
    "MasterAllocationPolicyChangeCandidateStatus",
    "build_master_allocation_policy_change_candidate",
    "master_allocation_policy_change_candidate_payload",
]
