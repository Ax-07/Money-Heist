from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock

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
from .allocation_policy_store import (
    MasterAllocationPolicyAtomicStore,
    MasterAllocationPolicyAtomicSwapOutcome,
)


class MasterAllocationPolicyReplacementStatus(StrEnum):
    APPLIED = "APPLIED"
    CAS_CONFLICT = "CAS_CONFLICT"


class MasterAllocationPolicyReplacementReasonCode(StrEnum):
    APPLIED = "APPLIED"
    ATOMIC_BASE_POLICY_MISMATCH = "ATOMIC_BASE_POLICY_MISMATCH"


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


def _validate_policy_integrity(
    policy: MasterAllocationPolicy,
    *,
    context: str,
) -> None:
    if _policy_fingerprint(policy) != policy.fingerprint_sha256:
        raise ValueError(f"{context} policy fingerprint integrity failure")


class InMemoryMasterAllocationPolicyAtomicState:
    """One-process atomic holder for one Master allocation policy.

    This is intentionally not durable and is not a distributed lock. It exists to make the
    compare-and-swap mutation boundary executable and testable before any LIVE persistence adapter.
    """

    in_process_only = True
    durable = False
    multi_process_safe = False
    multi_host_safe = False
    live_ready = False

    def __init__(self, initial_policy: MasterAllocationPolicy) -> None:
        _validate_policy_integrity(initial_policy, context="atomic state initial")
        self._current_policy = initial_policy
        self._lock = RLock()

    def snapshot(self) -> MasterAllocationPolicy:
        with self._lock:
            _validate_policy_integrity(self._current_policy, context="atomic state current")
            return self._current_policy

    def compare_and_swap(
        self,
        *,
        expected_master_portfolio_id: str,
        expected_policy_id: str,
        expected_fingerprint_sha256: str,
        replacement_policy: MasterAllocationPolicy,
    ) -> MasterAllocationPolicyAtomicSwapOutcome:
        expected_master = _required_text(
            expected_master_portfolio_id,
            field_name="expected_master_portfolio_id",
        )
        expected_id = _required_text(expected_policy_id, field_name="expected_policy_id")
        expected_fingerprint = _sha256(
            expected_fingerprint_sha256,
            field_name="expected_fingerprint_sha256",
        )
        _validate_policy_integrity(replacement_policy, context="atomic replacement")
        if replacement_policy.master_portfolio_id != expected_master:
            raise ValueError("atomic replacement policy Master Portfolio mismatch")

        with self._lock:
            observed = self._current_policy
            _validate_policy_integrity(observed, context="atomic state current")
            matches = (
                observed.master_portfolio_id == expected_master
                and observed.policy_id == expected_id
                and observed.fingerprint_sha256 == expected_fingerprint
            )
            if not matches:
                return MasterAllocationPolicyAtomicSwapOutcome(
                    swapped=False,
                    observed_policy=observed,
                    active_policy=observed,
                )
            if tuple(member.system_id for member in observed.members) != tuple(
                member.system_id for member in replacement_policy.members
            ):
                raise ValueError("atomic replacement policy cannot change membership")
            self._current_policy = replacement_policy
            return MasterAllocationPolicyAtomicSwapOutcome(
                swapped=True,
                observed_policy=observed,
                active_policy=replacement_policy,
            )


def master_allocation_policy_replacement_receipt_payload(
    receipt: MasterAllocationPolicyReplacementReceipt,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-policy-replacement-receipt.v1",
        "schema_version": receipt.schema_version,
        "application_id": receipt.application_id,
        "status": receipt.status,
        "reason_code": receipt.reason_code,
        "master_portfolio_id": receipt.master_portfolio_id,
        "change_candidate_id": receipt.change_candidate_id,
        "change_candidate_fingerprint_sha256": receipt.change_candidate_fingerprint_sha256,
        "authorization_id": receipt.authorization_id,
        "authorization_fingerprint_sha256": receipt.authorization_fingerprint_sha256,
        "preflight_id": receipt.preflight_id,
        "preflight_fingerprint_sha256": receipt.preflight_fingerprint_sha256,
        "expected_base_policy_id": receipt.expected_base_policy_id,
        "expected_base_policy_fingerprint_sha256": (
            receipt.expected_base_policy_fingerprint_sha256
        ),
        "observed_policy_id_at_mutation": receipt.observed_policy_id_at_mutation,
        "observed_policy_fingerprint_sha256_at_mutation": (
            receipt.observed_policy_fingerprint_sha256_at_mutation
        ),
        "requested_new_policy_id": receipt.requested_new_policy_id,
        "requested_new_policy_fingerprint_sha256": (
            receipt.requested_new_policy_fingerprint_sha256
        ),
        "active_policy_id_after_attempt": receipt.active_policy_id_after_attempt,
        "active_policy_fingerprint_sha256_after_attempt": (
            receipt.active_policy_fingerprint_sha256_after_attempt
        ),
        "application_source_ref": receipt.application_source_ref,
        "operator_ref": receipt.operator_ref,
        "attempted_at": receipt.attempted_at,
        "atomic_compare_and_swap_performed": receipt.atomic_compare_and_swap_performed,
        "base_policy_revalidated_at_mutation": receipt.base_policy_revalidated_at_mutation,
        "policy_mutation_performed": receipt.policy_mutation_performed,
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationPolicyReplacementReceipt:
    """Immutable receipt for one atomic policy replacement attempt."""

    application_id: str
    status: MasterAllocationPolicyReplacementStatus
    reason_code: MasterAllocationPolicyReplacementReasonCode
    master_portfolio_id: str
    change_candidate_id: str
    change_candidate_fingerprint_sha256: str
    authorization_id: str
    authorization_fingerprint_sha256: str
    preflight_id: str
    preflight_fingerprint_sha256: str
    expected_base_policy_id: str
    expected_base_policy_fingerprint_sha256: str
    observed_policy_id_at_mutation: str
    observed_policy_fingerprint_sha256_at_mutation: str
    requested_new_policy_id: str
    requested_new_policy_fingerprint_sha256: str
    active_policy_id_after_attempt: str
    active_policy_fingerprint_sha256_after_attempt: str
    application_source_ref: str
    operator_ref: str
    attempted_at: datetime
    atomic_compare_and_swap_performed: bool
    base_policy_revalidated_at_mutation: bool
    policy_mutation_performed: bool
    fingerprint_sha256: str
    static_policy_replacement_only: bool = field(default=True, init=False)
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
            "application_id",
            "master_portfolio_id",
            "change_candidate_id",
            "authorization_id",
            "preflight_id",
            "expected_base_policy_id",
            "observed_policy_id_at_mutation",
            "requested_new_policy_id",
            "active_policy_id_after_attempt",
            "application_source_ref",
            "operator_ref",
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
            "expected_base_policy_fingerprint_sha256",
            "observed_policy_fingerprint_sha256_at_mutation",
            "requested_new_policy_fingerprint_sha256",
            "active_policy_fingerprint_sha256_after_attempt",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), field_name=name))
        object.__setattr__(self, "attempted_at", _utc(self.attempted_at, field_name="attempted_at"))
        if not self.atomic_compare_and_swap_performed:
            raise ValueError("policy replacement receipt requires atomic compare-and-swap")
        if not self.base_policy_revalidated_at_mutation:
            raise ValueError("policy replacement receipt requires mutation-time base revalidation")
        if self.status is MasterAllocationPolicyReplacementStatus.APPLIED:
            if self.reason_code is not MasterAllocationPolicyReplacementReasonCode.APPLIED:
                raise ValueError("applied policy replacement requires APPLIED reason")
            if not self.policy_mutation_performed:
                raise ValueError("applied policy replacement must record policy mutation")
            if self.observed_policy_id_at_mutation != self.expected_base_policy_id:
                raise ValueError("applied policy replacement observed unexpected base policy ID")
            if (
                self.observed_policy_fingerprint_sha256_at_mutation
                != self.expected_base_policy_fingerprint_sha256
            ):
                raise ValueError("applied policy replacement observed unexpected base fingerprint")
            if self.active_policy_id_after_attempt != self.requested_new_policy_id:
                raise ValueError("applied policy replacement active policy ID mismatch")
            if (
                self.active_policy_fingerprint_sha256_after_attempt
                != self.requested_new_policy_fingerprint_sha256
            ):
                raise ValueError("applied policy replacement active fingerprint mismatch")
        elif self.status is MasterAllocationPolicyReplacementStatus.CAS_CONFLICT:
            if self.reason_code is not (
                MasterAllocationPolicyReplacementReasonCode.ATOMIC_BASE_POLICY_MISMATCH
            ):
                raise ValueError("CAS conflict requires ATOMIC_BASE_POLICY_MISMATCH reason")
            if self.policy_mutation_performed:
                raise ValueError("CAS conflict cannot record policy mutation")
            if (
                self.active_policy_id_after_attempt != self.observed_policy_id_at_mutation
                or self.active_policy_fingerprint_sha256_after_attempt
                != self.observed_policy_fingerprint_sha256_at_mutation
            ):
                raise ValueError("CAS conflict must leave observed policy active")
        else:
            raise ValueError("unsupported policy replacement status")
        if self.schema_version != "1.0":
            raise ValueError("unsupported policy replacement receipt schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_allocation_policy_replacement_receipt_payload(self))
        if normalized != expected:
            raise ValueError("policy replacement receipt fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    @property
    def applied(self) -> bool:
        return self.status is MasterAllocationPolicyReplacementStatus.APPLIED

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_policy_replacement_receipt_payload(self)


def _validate_application_chain(
    *,
    candidate: MasterAllocationPolicyChangeCandidate,
    authorization: MasterAllocationPolicyApplicationAuthorization,
    preflight: MasterAllocationPolicyApplicationPreflight,
    base_allocation_policy: MasterAllocationPolicy,
) -> None:
    if stable_digest(master_allocation_policy_change_candidate_payload(candidate)) != (
        candidate.fingerprint_sha256
    ):
        raise ValueError("policy replacement change candidate fingerprint integrity failure")
    if candidate.status is not (
        MasterAllocationPolicyChangeCandidateStatus.READY_FOR_OPERATOR_AUTHORIZATION
    ):
        raise ValueError("policy replacement requires ready change candidate")
    if stable_digest(master_allocation_policy_application_authorization_payload(authorization)) != (
        authorization.fingerprint_sha256
    ):
        raise ValueError("policy replacement authorization fingerprint integrity failure")
    if authorization.action is not MasterAllocationPolicyApplicationAuthorizationAction.AUTHORIZE:
        raise ValueError("policy replacement requires AUTHORIZE operator action")
    if authorization.status is not MasterAllocationPolicyApplicationAuthorizationStatus.AUTHORIZED:
        raise ValueError("policy replacement requires AUTHORIZED operator decision")
    if stable_digest(master_allocation_policy_application_preflight_payload(preflight)) != (
        preflight.fingerprint_sha256
    ):
        raise ValueError("policy replacement preflight fingerprint integrity failure")
    if preflight.status is not (
        MasterAllocationPolicyApplicationPreflightStatus.READY_FOR_APPLICATION
    ):
        raise ValueError("policy replacement requires READY_FOR_APPLICATION preflight")
    if preflight.reason_codes != (MasterAllocationPolicyApplicationPreflightReasonCode.READY,):
        raise ValueError("policy replacement ready preflight must carry READY reason only")
    if not all(
        (
            preflight.operator_authorization_verified,
            preflight.base_policy_identity_verified,
            preflight.base_policy_fingerprint_verified,
            preflight.membership_verified,
            preflight.configuration_verified,
        )
    ):
        raise ValueError("policy replacement requires every preflight verification")
    _validate_policy_integrity(base_allocation_policy, context="policy replacement base")
    if base_allocation_policy.status is not AllocationEnvelopeStatus.CONFIGURED:
        raise ValueError("policy replacement requires CONFIGURED base policy")

    candidate_bindings = (
        (authorization.master_portfolio_id, candidate.master_portfolio_id),
        (authorization.change_candidate_id, candidate.change_candidate_id),
        (authorization.change_candidate_fingerprint_sha256, candidate.fingerprint_sha256),
        (authorization.base_policy_id, candidate.base_policy_id),
        (
            authorization.base_policy_fingerprint_sha256,
            candidate.base_policy_fingerprint_sha256,
        ),
        (preflight.master_portfolio_id, candidate.master_portfolio_id),
        (preflight.change_candidate_id, candidate.change_candidate_id),
        (preflight.change_candidate_fingerprint_sha256, candidate.fingerprint_sha256),
        (preflight.authorization_id, authorization.authorization_id),
        (preflight.authorization_fingerprint_sha256, authorization.fingerprint_sha256),
        (preflight.base_policy_id, candidate.base_policy_id),
        (preflight.base_policy_fingerprint_sha256, candidate.base_policy_fingerprint_sha256),
        (base_allocation_policy.master_portfolio_id, candidate.master_portfolio_id),
        (base_allocation_policy.policy_id, candidate.base_policy_id),
        (base_allocation_policy.fingerprint_sha256, candidate.base_policy_fingerprint_sha256),
        (preflight.current_policy_id, base_allocation_policy.policy_id),
        (
            preflight.current_policy_fingerprint_sha256,
            base_allocation_policy.fingerprint_sha256,
        ),
    )
    if any(left != right for left, right in candidate_bindings):
        raise ValueError("policy replacement candidate/authorization/preflight provenance mismatch")
    proposed_ids = tuple(envelope.system_id for envelope in candidate.proposed_envelopes)
    base_ids = tuple(member.system_id for member in base_allocation_policy.members)
    if preflight.proposed_system_ids != proposed_ids or proposed_ids != base_ids:
        raise ValueError("policy replacement membership provenance mismatch")


def _build_receipt(
    *,
    status: MasterAllocationPolicyReplacementStatus,
    reason_code: MasterAllocationPolicyReplacementReasonCode,
    candidate: MasterAllocationPolicyChangeCandidate,
    authorization: MasterAllocationPolicyApplicationAuthorization,
    preflight: MasterAllocationPolicyApplicationPreflight,
    observed_policy: MasterAllocationPolicy,
    replacement_policy: MasterAllocationPolicy,
    active_policy: MasterAllocationPolicy,
    application_source_ref: str,
    attempted_at: datetime,
) -> MasterAllocationPolicyReplacementReceipt:
    values = {
        "status": status,
        "reason_code": reason_code,
        "master_portfolio_id": candidate.master_portfolio_id,
        "change_candidate_id": candidate.change_candidate_id,
        "change_candidate_fingerprint_sha256": candidate.fingerprint_sha256,
        "authorization_id": authorization.authorization_id,
        "authorization_fingerprint_sha256": authorization.fingerprint_sha256,
        "preflight_id": preflight.preflight_id,
        "preflight_fingerprint_sha256": preflight.fingerprint_sha256,
        "expected_base_policy_id": candidate.base_policy_id,
        "expected_base_policy_fingerprint_sha256": candidate.base_policy_fingerprint_sha256,
        "observed_policy_id_at_mutation": observed_policy.policy_id,
        "observed_policy_fingerprint_sha256_at_mutation": observed_policy.fingerprint_sha256,
        "requested_new_policy_id": replacement_policy.policy_id,
        "requested_new_policy_fingerprint_sha256": replacement_policy.fingerprint_sha256,
        "active_policy_id_after_attempt": active_policy.policy_id,
        "active_policy_fingerprint_sha256_after_attempt": active_policy.fingerprint_sha256,
        "application_source_ref": application_source_ref,
        "operator_ref": authorization.operator_ref,
        "attempted_at": attempted_at,
        "atomic_compare_and_swap_performed": True,
        "base_policy_revalidated_at_mutation": True,
        "policy_mutation_performed": status is MasterAllocationPolicyReplacementStatus.APPLIED,
    }
    application_id = "master-allocation-policy-replacement:" + stable_digest(
        {
            "schema": "money-heist.master-allocation-policy-replacement-id.v1",
            **values,
        }
    )
    provisional = MasterAllocationPolicyReplacementReceipt.__new__(
        MasterAllocationPolicyReplacementReceipt
    )
    object.__setattr__(provisional, "application_id", application_id)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterAllocationPolicyReplacementReceipt(
        application_id=application_id,
        **values,
        fingerprint_sha256=stable_digest(
            master_allocation_policy_replacement_receipt_payload(provisional)
        ),
    )


def apply_master_allocation_policy_replacement(
    *,
    atomic_state: MasterAllocationPolicyAtomicStore,
    candidate: MasterAllocationPolicyChangeCandidate,
    authorization: MasterAllocationPolicyApplicationAuthorization,
    preflight: MasterAllocationPolicyApplicationPreflight,
    base_allocation_policy: MasterAllocationPolicy,
    new_policy_id: str,
    application_source_ref: str,
    attempted_at: datetime,
) -> MasterAllocationPolicyReplacementReceipt:
    """Apply one static policy replacement through mutation-time compare-and-swap."""

    _validate_application_chain(
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base_allocation_policy,
    )
    normalized_new_policy_id = _required_text(new_policy_id, field_name="new_policy_id")
    if normalized_new_policy_id == candidate.base_policy_id:
        raise ValueError("policy replacement new_policy_id must differ from base policy ID")
    normalized_source_ref = _required_text(
        application_source_ref,
        field_name="application_source_ref",
    )
    normalized_attempted_at = _utc(attempted_at, field_name="attempted_at")
    if normalized_attempted_at < preflight.checked_at:
        raise ValueError("policy replacement attempt cannot predate preflight")

    replacement_policy = build_master_allocation_policy(
        master_portfolio_id=candidate.master_portfolio_id,
        policy_id=normalized_new_policy_id,
        members=base_allocation_policy.members,
        envelopes=candidate.proposed_envelopes,
        source_ref=normalized_source_ref,
    )
    outcome = atomic_state.compare_and_swap(
        expected_master_portfolio_id=candidate.master_portfolio_id,
        expected_policy_id=candidate.base_policy_id,
        expected_fingerprint_sha256=candidate.base_policy_fingerprint_sha256,
        replacement_policy=replacement_policy,
    )
    if outcome.swapped:
        status = MasterAllocationPolicyReplacementStatus.APPLIED
        reason_code = MasterAllocationPolicyReplacementReasonCode.APPLIED
    else:
        status = MasterAllocationPolicyReplacementStatus.CAS_CONFLICT
        reason_code = MasterAllocationPolicyReplacementReasonCode.ATOMIC_BASE_POLICY_MISMATCH
    return _build_receipt(
        status=status,
        reason_code=reason_code,
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        observed_policy=outcome.observed_policy,
        replacement_policy=replacement_policy,
        active_policy=outcome.active_policy,
        application_source_ref=normalized_source_ref,
        attempted_at=normalized_attempted_at,
    )


__all__ = [
    "InMemoryMasterAllocationPolicyAtomicState",
    "MasterAllocationPolicyReplacementReasonCode",
    "MasterAllocationPolicyReplacementReceipt",
    "MasterAllocationPolicyReplacementStatus",
    "apply_master_allocation_policy_replacement",
    "master_allocation_policy_replacement_receipt_payload",
]
