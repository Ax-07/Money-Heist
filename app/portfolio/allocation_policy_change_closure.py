from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .allocation import (
    AllocationEnvelopeStatus,
    MasterAllocationPolicy,
    build_master_allocation_policy,
    master_allocation_policy_fingerprint,
)
from .allocation_policy_application import (
    MasterAllocationPolicyApplicationAuthorization,
    MasterAllocationPolicyApplicationAuthorizationAction,
    MasterAllocationPolicyApplicationAuthorizationStatus,
    MasterAllocationPolicyApplicationPreflight,
    MasterAllocationPolicyApplicationPreflightReasonCode,
    MasterAllocationPolicyApplicationPreflightStatus,
    master_allocation_policy_application_authorization_payload,
    master_allocation_policy_application_preflight_payload,
)
from .allocation_policy_change import (
    MasterAllocationPolicyChangeCandidate,
    MasterAllocationPolicyChangeCandidateStatus,
    master_allocation_policy_change_candidate_payload,
)
from .allocation_policy_replacement import (
    MasterAllocationPolicyReplacementReasonCode,
    MasterAllocationPolicyReplacementReceipt,
    MasterAllocationPolicyReplacementStatus,
    master_allocation_policy_replacement_receipt_payload,
)
from .allocation_policy_store import MasterAllocationPolicyAtomicStore


class MasterAllocationPolicyChangeAuditStatus(StrEnum):
    VERIFIED = "VERIFIED"


class MasterAllocationPolicyChangeClosureStatus(StrEnum):
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


def _validate_policy_integrity(policy: MasterAllocationPolicy, *, context: str) -> None:
    if _policy_fingerprint(policy) != policy.fingerprint_sha256:
        raise ValueError(f"{context} policy fingerprint integrity failure")


def master_allocation_policy_change_audit_payload(
    audit: MasterAllocationPolicyChangeAuditReport,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-policy-change-audit.v1",
        "schema_version": audit.schema_version,
        "audit_id": audit.audit_id,
        "status": audit.status,
        "master_portfolio_id": audit.master_portfolio_id,
        "change_candidate_id": audit.change_candidate_id,
        "change_candidate_fingerprint_sha256": audit.change_candidate_fingerprint_sha256,
        "authorization_id": audit.authorization_id,
        "authorization_fingerprint_sha256": audit.authorization_fingerprint_sha256,
        "preflight_id": audit.preflight_id,
        "preflight_fingerprint_sha256": audit.preflight_fingerprint_sha256,
        "application_id": audit.application_id,
        "replacement_receipt_fingerprint_sha256": audit.replacement_receipt_fingerprint_sha256,
        "application_status": audit.application_status,
        "application_reason_code": audit.application_reason_code,
        "base_policy_id": audit.base_policy_id,
        "base_policy_fingerprint_sha256": audit.base_policy_fingerprint_sha256,
        "requested_policy_id": audit.requested_policy_id,
        "requested_policy_fingerprint_sha256": audit.requested_policy_fingerprint_sha256,
        "active_policy_id": audit.active_policy_id,
        "active_policy_fingerprint_sha256": audit.active_policy_fingerprint_sha256,
        "store_ref": audit.store_ref,
        "store_durable": audit.store_durable,
        "store_multi_process_safe": audit.store_multi_process_safe,
        "store_multi_host_safe": audit.store_multi_host_safe,
        "store_live_ready": audit.store_live_ready,
        "audited_at": audit.audited_at,
        "candidate_verified": audit.candidate_verified,
        "authorization_verified": audit.authorization_verified,
        "preflight_verified": audit.preflight_verified,
        "base_policy_verified": audit.base_policy_verified,
        "replacement_receipt_verified": audit.replacement_receipt_verified,
        "persistent_store_verified": audit.persistent_store_verified,
        "active_policy_verified": audit.active_policy_verified,
        "outcome_consistency_verified": audit.outcome_consistency_verified,
        "no_trading_authority_verified": audit.no_trading_authority_verified,
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationPolicyChangeAuditReport:
    """Read-only integrity proof for one completed allocation-policy change attempt."""

    audit_id: str
    status: MasterAllocationPolicyChangeAuditStatus
    master_portfolio_id: str
    change_candidate_id: str
    change_candidate_fingerprint_sha256: str
    authorization_id: str
    authorization_fingerprint_sha256: str
    preflight_id: str
    preflight_fingerprint_sha256: str
    application_id: str
    replacement_receipt_fingerprint_sha256: str
    application_status: MasterAllocationPolicyReplacementStatus
    application_reason_code: MasterAllocationPolicyReplacementReasonCode
    base_policy_id: str
    base_policy_fingerprint_sha256: str
    requested_policy_id: str
    requested_policy_fingerprint_sha256: str
    active_policy_id: str
    active_policy_fingerprint_sha256: str
    store_ref: str
    store_durable: bool
    store_multi_process_safe: bool
    store_multi_host_safe: bool
    store_live_ready: bool
    audited_at: datetime
    candidate_verified: bool
    authorization_verified: bool
    preflight_verified: bool
    base_policy_verified: bool
    replacement_receipt_verified: bool
    persistent_store_verified: bool
    active_policy_verified: bool
    outcome_consistency_verified: bool
    no_trading_authority_verified: bool
    fingerprint_sha256: str
    audit_only: bool = field(default=True, init=False)
    read_only: bool = field(default=True, init=False)
    lifecycle_closed: bool = field(default=False, init=False)
    dynamic_allocation_enabled: bool = field(default=False, init=False)
    policy_mutation_authority: bool = field(default=False, init=False)
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
            "audit_id",
            "master_portfolio_id",
            "change_candidate_id",
            "authorization_id",
            "preflight_id",
            "application_id",
            "base_policy_id",
            "requested_policy_id",
            "active_policy_id",
            "store_ref",
        ):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), field_name=name),
            )
        for name in (
            "change_candidate_fingerprint_sha256",
            "authorization_fingerprint_sha256",
            "preflight_fingerprint_sha256",
            "replacement_receipt_fingerprint_sha256",
            "base_policy_fingerprint_sha256",
            "requested_policy_fingerprint_sha256",
            "active_policy_fingerprint_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), field_name=name))
        object.__setattr__(self, "audited_at", _utc(self.audited_at, field_name="audited_at"))
        if self.status is not MasterAllocationPolicyChangeAuditStatus.VERIFIED:
            raise ValueError("allocation policy change audit status must be VERIFIED")
        verification_flags = (
            self.candidate_verified,
            self.authorization_verified,
            self.preflight_verified,
            self.base_policy_verified,
            self.replacement_receipt_verified,
            self.persistent_store_verified,
            self.active_policy_verified,
            self.outcome_consistency_verified,
            self.no_trading_authority_verified,
        )
        if not all(verification_flags):
            raise ValueError("allocation policy change audit requires all verification flags")
        if not self.store_durable or not self.store_multi_process_safe:
            raise ValueError("allocation policy change audit requires durable multi-process store")
        if self.application_status is MasterAllocationPolicyReplacementStatus.APPLIED:
            if self.application_reason_code is not (
                MasterAllocationPolicyReplacementReasonCode.APPLIED
            ):
                raise ValueError("applied audit must preserve APPLIED reason")
            if self.active_policy_id != self.requested_policy_id:
                raise ValueError("applied audit active policy ID mismatch")
            if self.active_policy_fingerprint_sha256 != self.requested_policy_fingerprint_sha256:
                raise ValueError("applied audit active policy fingerprint mismatch")
        elif self.application_status is MasterAllocationPolicyReplacementStatus.CAS_CONFLICT:
            if self.application_reason_code is not (
                MasterAllocationPolicyReplacementReasonCode.ATOMIC_BASE_POLICY_MISMATCH
            ):
                raise ValueError("CAS conflict audit reason mismatch")
        else:
            raise ValueError("unsupported allocation policy change audit application status")
        if self.schema_version != "1.0":
            raise ValueError("unsupported allocation policy change audit schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        if normalized != stable_digest(master_allocation_policy_change_audit_payload(self)):
            raise ValueError("allocation policy change audit fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    @property
    def policy_change_applied(self) -> bool:
        return self.application_status is MasterAllocationPolicyReplacementStatus.APPLIED

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_policy_change_audit_payload(self)


def _validate_chain_integrity(
    *,
    candidate: MasterAllocationPolicyChangeCandidate,
    authorization: MasterAllocationPolicyApplicationAuthorization,
    preflight: MasterAllocationPolicyApplicationPreflight,
    base_allocation_policy: MasterAllocationPolicy,
    receipt: MasterAllocationPolicyReplacementReceipt,
) -> None:
    if stable_digest(master_allocation_policy_change_candidate_payload(candidate)) != (
        candidate.fingerprint_sha256
    ):
        raise ValueError("policy change audit candidate fingerprint integrity failure")
    if candidate.status is not (
        MasterAllocationPolicyChangeCandidateStatus.READY_FOR_OPERATOR_AUTHORIZATION
    ):
        raise ValueError("policy change audit requires ready change candidate")
    if stable_digest(master_allocation_policy_application_authorization_payload(authorization)) != (
        authorization.fingerprint_sha256
    ):
        raise ValueError("policy change audit authorization fingerprint integrity failure")
    if authorization.action is not MasterAllocationPolicyApplicationAuthorizationAction.AUTHORIZE:
        raise ValueError("policy change audit requires AUTHORIZE operator action")
    if authorization.status is not MasterAllocationPolicyApplicationAuthorizationStatus.AUTHORIZED:
        raise ValueError("policy change audit requires AUTHORIZED operator decision")
    if stable_digest(master_allocation_policy_application_preflight_payload(preflight)) != (
        preflight.fingerprint_sha256
    ):
        raise ValueError("policy change audit preflight fingerprint integrity failure")
    if preflight.status is not (
        MasterAllocationPolicyApplicationPreflightStatus.READY_FOR_APPLICATION
    ):
        raise ValueError("policy change audit requires READY_FOR_APPLICATION preflight")
    if preflight.reason_codes != (MasterAllocationPolicyApplicationPreflightReasonCode.READY,):
        raise ValueError("policy change audit ready preflight must carry READY reason only")
    if not all(
        (
            preflight.operator_authorization_verified,
            preflight.base_policy_identity_verified,
            preflight.base_policy_fingerprint_verified,
            preflight.membership_verified,
            preflight.configuration_verified,
        )
    ):
        raise ValueError("policy change audit requires every preflight verification")
    _validate_policy_integrity(base_allocation_policy, context="policy change audit base")
    if base_allocation_policy.status is not AllocationEnvelopeStatus.CONFIGURED:
        raise ValueError("policy change audit requires CONFIGURED base policy")
    if stable_digest(master_allocation_policy_replacement_receipt_payload(receipt)) != (
        receipt.fingerprint_sha256
    ):
        raise ValueError("policy change audit replacement receipt fingerprint integrity failure")

    bindings = (
        (candidate.master_portfolio_id, base_allocation_policy.master_portfolio_id),
        (candidate.base_policy_id, base_allocation_policy.policy_id),
        (candidate.base_policy_fingerprint_sha256, base_allocation_policy.fingerprint_sha256),
        (authorization.master_portfolio_id, candidate.master_portfolio_id),
        (authorization.change_candidate_id, candidate.change_candidate_id),
        (authorization.change_candidate_fingerprint_sha256, candidate.fingerprint_sha256),
        (authorization.base_policy_id, candidate.base_policy_id),
        (authorization.base_policy_fingerprint_sha256, candidate.base_policy_fingerprint_sha256),
        (preflight.master_portfolio_id, candidate.master_portfolio_id),
        (preflight.change_candidate_id, candidate.change_candidate_id),
        (preflight.change_candidate_fingerprint_sha256, candidate.fingerprint_sha256),
        (preflight.authorization_id, authorization.authorization_id),
        (preflight.authorization_fingerprint_sha256, authorization.fingerprint_sha256),
        (preflight.base_policy_id, candidate.base_policy_id),
        (preflight.base_policy_fingerprint_sha256, candidate.base_policy_fingerprint_sha256),
        (receipt.master_portfolio_id, candidate.master_portfolio_id),
        (receipt.change_candidate_id, candidate.change_candidate_id),
        (receipt.change_candidate_fingerprint_sha256, candidate.fingerprint_sha256),
        (receipt.authorization_id, authorization.authorization_id),
        (receipt.authorization_fingerprint_sha256, authorization.fingerprint_sha256),
        (receipt.preflight_id, preflight.preflight_id),
        (receipt.preflight_fingerprint_sha256, preflight.fingerprint_sha256),
        (receipt.expected_base_policy_id, base_allocation_policy.policy_id),
        (
            receipt.expected_base_policy_fingerprint_sha256,
            base_allocation_policy.fingerprint_sha256,
        ),
        (receipt.operator_ref, authorization.operator_ref),
    )
    if any(left != right for left, right in bindings):
        raise ValueError("policy change audit lifecycle provenance mismatch")
    proposed_ids = tuple(envelope.system_id for envelope in candidate.proposed_envelopes)
    base_ids = tuple(member.system_id for member in base_allocation_policy.members)
    if preflight.proposed_system_ids != proposed_ids or proposed_ids != base_ids:
        raise ValueError("policy change audit membership provenance mismatch")
    if receipt.attempted_at < preflight.checked_at:
        raise ValueError("policy change audit receipt predates preflight")
    if not receipt.atomic_compare_and_swap_performed:
        raise ValueError("policy change audit requires atomic compare-and-swap receipt")
    if not receipt.base_policy_revalidated_at_mutation:
        raise ValueError("policy change audit requires mutation-time base revalidation")


def _expected_requested_policy(
    *,
    candidate: MasterAllocationPolicyChangeCandidate,
    base_allocation_policy: MasterAllocationPolicy,
    receipt: MasterAllocationPolicyReplacementReceipt,
) -> MasterAllocationPolicy:
    expected = build_master_allocation_policy(
        master_portfolio_id=candidate.master_portfolio_id,
        policy_id=receipt.requested_new_policy_id,
        members=base_allocation_policy.members,
        envelopes=candidate.proposed_envelopes,
        source_ref=receipt.application_source_ref,
    )
    if expected.fingerprint_sha256 != receipt.requested_new_policy_fingerprint_sha256:
        raise ValueError("policy change audit requested replacement fingerprint mismatch")
    return expected


def _validate_persistent_outcome(
    *,
    store: MasterAllocationPolicyAtomicStore,
    candidate: MasterAllocationPolicyChangeCandidate,
    base_allocation_policy: MasterAllocationPolicy,
    receipt: MasterAllocationPolicyReplacementReceipt,
) -> MasterAllocationPolicy:
    if not bool(getattr(store, "durable", False)):
        raise ValueError("policy change audit requires durable policy store")
    if not bool(getattr(store, "multi_process_safe", False)):
        raise ValueError("policy change audit requires multi-process-safe policy store")
    active = store.snapshot()
    _validate_policy_integrity(active, context="policy change audit active")
    if active.master_portfolio_id != candidate.master_portfolio_id:
        raise ValueError("policy change audit active Master Portfolio mismatch")
    expected_requested = _expected_requested_policy(
        candidate=candidate,
        base_allocation_policy=base_allocation_policy,
        receipt=receipt,
    )
    if receipt.status is MasterAllocationPolicyReplacementStatus.APPLIED:
        if receipt.reason_code is not MasterAllocationPolicyReplacementReasonCode.APPLIED:
            raise ValueError("policy change audit applied receipt reason mismatch")
        if not receipt.policy_mutation_performed:
            raise ValueError("policy change audit applied receipt must record mutation")
        if active != expected_requested:
            raise ValueError("policy change audit persisted applied policy mismatch")
    elif receipt.status is MasterAllocationPolicyReplacementStatus.CAS_CONFLICT:
        if receipt.reason_code is not (
            MasterAllocationPolicyReplacementReasonCode.ATOMIC_BASE_POLICY_MISMATCH
        ):
            raise ValueError("policy change audit CAS conflict receipt reason mismatch")
        if receipt.policy_mutation_performed:
            raise ValueError("policy change audit CAS conflict cannot record mutation")
        if active.policy_id != receipt.active_policy_id_after_attempt:
            raise ValueError("policy change audit CAS conflict active policy ID changed")
        if active.fingerprint_sha256 != receipt.active_policy_fingerprint_sha256_after_attempt:
            raise ValueError("policy change audit CAS conflict active fingerprint changed")
        if receipt.active_policy_id_after_attempt != receipt.observed_policy_id_at_mutation:
            raise ValueError("policy change audit CAS conflict observed policy ID mismatch")
        if (
            receipt.active_policy_fingerprint_sha256_after_attempt
            != receipt.observed_policy_fingerprint_sha256_at_mutation
        ):
            raise ValueError("policy change audit CAS conflict observed fingerprint mismatch")
    else:
        raise ValueError("unsupported policy change audit receipt status")
    return active


def audit_master_allocation_policy_change(
    *,
    candidate: MasterAllocationPolicyChangeCandidate,
    authorization: MasterAllocationPolicyApplicationAuthorization,
    preflight: MasterAllocationPolicyApplicationPreflight,
    base_allocation_policy: MasterAllocationPolicy,
    receipt: MasterAllocationPolicyReplacementReceipt,
    store: MasterAllocationPolicyAtomicStore,
    store_ref: str,
    audited_at: datetime,
) -> MasterAllocationPolicyChangeAuditReport:
    """Verify one Step 1-4 lifecycle and persisted post-attempt policy without mutation."""

    _validate_chain_integrity(
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base_allocation_policy,
        receipt=receipt,
    )
    normalized_store_ref = _required_text(store_ref, field_name="store_ref")
    normalized_audited_at = _utc(audited_at, field_name="audited_at")
    if normalized_audited_at < receipt.attempted_at:
        raise ValueError("policy change audit cannot predate replacement attempt")
    active = _validate_persistent_outcome(
        store=store,
        candidate=candidate,
        base_allocation_policy=base_allocation_policy,
        receipt=receipt,
    )
    store_durable = bool(getattr(store, "durable", False))
    store_multi_process_safe = bool(getattr(store, "multi_process_safe", False))
    store_multi_host_safe = bool(getattr(store, "multi_host_safe", False))
    store_live_ready = bool(getattr(store, "live_ready", False))
    values = {
        "status": MasterAllocationPolicyChangeAuditStatus.VERIFIED,
        "master_portfolio_id": candidate.master_portfolio_id,
        "change_candidate_id": candidate.change_candidate_id,
        "change_candidate_fingerprint_sha256": candidate.fingerprint_sha256,
        "authorization_id": authorization.authorization_id,
        "authorization_fingerprint_sha256": authorization.fingerprint_sha256,
        "preflight_id": preflight.preflight_id,
        "preflight_fingerprint_sha256": preflight.fingerprint_sha256,
        "application_id": receipt.application_id,
        "replacement_receipt_fingerprint_sha256": receipt.fingerprint_sha256,
        "application_status": receipt.status,
        "application_reason_code": receipt.reason_code,
        "base_policy_id": base_allocation_policy.policy_id,
        "base_policy_fingerprint_sha256": base_allocation_policy.fingerprint_sha256,
        "requested_policy_id": receipt.requested_new_policy_id,
        "requested_policy_fingerprint_sha256": receipt.requested_new_policy_fingerprint_sha256,
        "active_policy_id": active.policy_id,
        "active_policy_fingerprint_sha256": active.fingerprint_sha256,
        "store_ref": normalized_store_ref,
        "store_durable": store_durable,
        "store_multi_process_safe": store_multi_process_safe,
        "store_multi_host_safe": store_multi_host_safe,
        "store_live_ready": store_live_ready,
        "audited_at": normalized_audited_at,
        "candidate_verified": True,
        "authorization_verified": True,
        "preflight_verified": True,
        "base_policy_verified": True,
        "replacement_receipt_verified": True,
        "persistent_store_verified": True,
        "active_policy_verified": True,
        "outcome_consistency_verified": True,
        "no_trading_authority_verified": True,
    }
    audit_id = "master-allocation-policy-change-audit:" + stable_digest(
        {"schema": "money-heist.master-allocation-policy-change-audit-id.v1", **values}
    )
    provisional = MasterAllocationPolicyChangeAuditReport.__new__(
        MasterAllocationPolicyChangeAuditReport
    )
    object.__setattr__(provisional, "audit_id", audit_id)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterAllocationPolicyChangeAuditReport(
        audit_id=audit_id,
        **values,
        fingerprint_sha256=stable_digest(
            master_allocation_policy_change_audit_payload(provisional)
        ),
    )


def master_allocation_policy_change_closure_payload(
    seal: MasterAllocationPolicyChangeClosureSeal,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-policy-change-closure.v1",
        "schema_version": seal.schema_version,
        "closure_id": seal.closure_id,
        "status": seal.status,
        "master_portfolio_id": seal.master_portfolio_id,
        "audit_fingerprint_sha256": seal.audit_fingerprint_sha256,
        "replacement_receipt_fingerprint_sha256": seal.replacement_receipt_fingerprint_sha256,
        "application_status": seal.application_status,
        "application_reason_code": seal.application_reason_code,
        "active_policy_id": seal.active_policy_id,
        "active_policy_fingerprint_sha256": seal.active_policy_fingerprint_sha256,
        "store_ref": seal.store_ref,
        "store_durable": seal.store_durable,
        "store_multi_process_safe": seal.store_multi_process_safe,
        "store_multi_host_safe": seal.store_multi_host_safe,
        "store_live_ready": seal.store_live_ready,
        "sealed_at": seal.sealed_at,
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationPolicyChangeClosureSeal:
    """Immutable closure proving the allocation-policy change lifecycle was audited."""

    closure_id: str
    status: MasterAllocationPolicyChangeClosureStatus
    master_portfolio_id: str
    audit_fingerprint_sha256: str
    replacement_receipt_fingerprint_sha256: str
    application_status: MasterAllocationPolicyReplacementStatus
    application_reason_code: MasterAllocationPolicyReplacementReasonCode
    active_policy_id: str
    active_policy_fingerprint_sha256: str
    store_ref: str
    store_durable: bool
    store_multi_process_safe: bool
    store_multi_host_safe: bool
    store_live_ready: bool
    sealed_at: datetime
    closure_fingerprint_sha256: str
    closure_only: bool = field(default=True, init=False)
    read_only: bool = field(default=True, init=False)
    lifecycle_closed: bool = field(default=True, init=False)
    dynamic_allocation_enabled: bool = field(default=False, init=False)
    policy_mutation_authority: bool = field(default=False, init=False)
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
        for name in ("closure_id", "master_portfolio_id", "active_policy_id", "store_ref"):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), field_name=name),
            )
        for name in (
            "audit_fingerprint_sha256",
            "replacement_receipt_fingerprint_sha256",
            "active_policy_fingerprint_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), field_name=name))
        object.__setattr__(self, "sealed_at", _utc(self.sealed_at, field_name="sealed_at"))
        if self.status is not MasterAllocationPolicyChangeClosureStatus.SEALED:
            raise ValueError("allocation policy change closure status must be SEALED")
        if not self.store_durable or not self.store_multi_process_safe:
            raise ValueError(
                "allocation policy change closure requires durable multi-process store"
            )
        if self.application_status is MasterAllocationPolicyReplacementStatus.APPLIED:
            if self.application_reason_code is not (
                MasterAllocationPolicyReplacementReasonCode.APPLIED
            ):
                raise ValueError("applied policy change closure reason mismatch")
        elif self.application_status is MasterAllocationPolicyReplacementStatus.CAS_CONFLICT:
            if self.application_reason_code is not (
                MasterAllocationPolicyReplacementReasonCode.ATOMIC_BASE_POLICY_MISMATCH
            ):
                raise ValueError("CAS conflict policy change closure reason mismatch")
        else:
            raise ValueError("unsupported policy change closure application status")
        if self.schema_version != "1.0":
            raise ValueError("unsupported allocation policy change closure schema_version")
        normalized = _sha256(
            self.closure_fingerprint_sha256,
            field_name="closure_fingerprint_sha256",
        )
        if normalized != stable_digest(master_allocation_policy_change_closure_payload(self)):
            raise ValueError("allocation policy change closure fingerprint mismatch")
        object.__setattr__(self, "closure_fingerprint_sha256", normalized)

    @property
    def policy_change_applied(self) -> bool:
        return self.application_status is MasterAllocationPolicyReplacementStatus.APPLIED

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_policy_change_closure_payload(self)


def seal_master_allocation_policy_change(
    *,
    audit: MasterAllocationPolicyChangeAuditReport,
) -> MasterAllocationPolicyChangeClosureSeal:
    """Seal one verified read-only allocation-policy change audit without further state access."""

    if stable_digest(master_allocation_policy_change_audit_payload(audit)) != (
        audit.fingerprint_sha256
    ):
        raise ValueError("policy change closure audit fingerprint integrity failure")
    if audit.status is not MasterAllocationPolicyChangeAuditStatus.VERIFIED:
        raise ValueError("policy change closure requires VERIFIED audit")
    values = {
        "status": MasterAllocationPolicyChangeClosureStatus.SEALED,
        "master_portfolio_id": audit.master_portfolio_id,
        "audit_fingerprint_sha256": audit.fingerprint_sha256,
        "replacement_receipt_fingerprint_sha256": audit.replacement_receipt_fingerprint_sha256,
        "application_status": audit.application_status,
        "application_reason_code": audit.application_reason_code,
        "active_policy_id": audit.active_policy_id,
        "active_policy_fingerprint_sha256": audit.active_policy_fingerprint_sha256,
        "store_ref": audit.store_ref,
        "store_durable": audit.store_durable,
        "store_multi_process_safe": audit.store_multi_process_safe,
        "store_multi_host_safe": audit.store_multi_host_safe,
        "store_live_ready": audit.store_live_ready,
        "sealed_at": audit.audited_at,
    }
    closure_id = "master-allocation-policy-change-closure:" + stable_digest(
        {"schema": "money-heist.master-allocation-policy-change-closure-id.v1", **values}
    )
    provisional = MasterAllocationPolicyChangeClosureSeal.__new__(
        MasterAllocationPolicyChangeClosureSeal
    )
    object.__setattr__(provisional, "closure_id", closure_id)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterAllocationPolicyChangeClosureSeal(
        closure_id=closure_id,
        **values,
        closure_fingerprint_sha256=stable_digest(
            master_allocation_policy_change_closure_payload(provisional)
        ),
    )


__all__ = [
    "MasterAllocationPolicyChangeAuditReport",
    "MasterAllocationPolicyChangeAuditStatus",
    "MasterAllocationPolicyChangeClosureSeal",
    "MasterAllocationPolicyChangeClosureStatus",
    "audit_master_allocation_policy_change",
    "master_allocation_policy_change_audit_payload",
    "master_allocation_policy_change_closure_payload",
    "seal_master_allocation_policy_change",
]
