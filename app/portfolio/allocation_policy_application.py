from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .allocation import (
    AllocationEnvelopeStatus,
    MasterAllocationPolicy,
    master_allocation_policy_fingerprint,
)
from .allocation_policy_change import (
    MasterAllocationPolicyChangeCandidate,
    MasterAllocationPolicyChangeCandidateStatus,
    master_allocation_policy_change_candidate_payload,
)


class MasterAllocationPolicyApplicationAuthorizationAction(StrEnum):
    AUTHORIZE = "AUTHORIZE"
    REJECT = "REJECT"
    DEFER = "DEFER"


class MasterAllocationPolicyApplicationAuthorizationStatus(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


class MasterAllocationPolicyApplicationPreflightStatus(StrEnum):
    READY_FOR_APPLICATION = "READY_FOR_APPLICATION"
    BLOCKED = "BLOCKED"


class MasterAllocationPolicyApplicationPreflightReasonCode(StrEnum):
    READY = "READY"
    OPERATOR_REJECTED = "OPERATOR_REJECTED"
    OPERATOR_DEFERRED = "OPERATOR_DEFERRED"
    MASTER_PORTFOLIO_MISMATCH = "MASTER_PORTFOLIO_MISMATCH"
    BASE_POLICY_ID_MISMATCH = "BASE_POLICY_ID_MISMATCH"
    BASE_POLICY_FINGERPRINT_MISMATCH = "BASE_POLICY_FINGERPRINT_MISMATCH"
    BASE_POLICY_NOT_CONFIGURED = "BASE_POLICY_NOT_CONFIGURED"
    MEMBERSHIP_MISMATCH = "MEMBERSHIP_MISMATCH"


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


def _authorization_status(
    action: MasterAllocationPolicyApplicationAuthorizationAction,
) -> MasterAllocationPolicyApplicationAuthorizationStatus:
    mapping = {
        MasterAllocationPolicyApplicationAuthorizationAction.AUTHORIZE: (
            MasterAllocationPolicyApplicationAuthorizationStatus.AUTHORIZED
        ),
        MasterAllocationPolicyApplicationAuthorizationAction.REJECT: (
            MasterAllocationPolicyApplicationAuthorizationStatus.REJECTED
        ),
        MasterAllocationPolicyApplicationAuthorizationAction.DEFER: (
            MasterAllocationPolicyApplicationAuthorizationStatus.DEFERRED
        ),
    }
    return mapping[action]


def master_allocation_policy_application_authorization_payload(
    authorization: MasterAllocationPolicyApplicationAuthorization,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-policy-application-authorization.v1",
        "schema_version": authorization.schema_version,
        "authorization_id": authorization.authorization_id,
        "status": authorization.status,
        "action": authorization.action,
        "master_portfolio_id": authorization.master_portfolio_id,
        "change_candidate_id": authorization.change_candidate_id,
        "change_candidate_fingerprint_sha256": (
            authorization.change_candidate_fingerprint_sha256
        ),
        "base_policy_id": authorization.base_policy_id,
        "base_policy_fingerprint_sha256": authorization.base_policy_fingerprint_sha256,
        "operator_ref": authorization.operator_ref,
        "rationale_codes": authorization.rationale_codes,
        "decided_at": authorization.decided_at,
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationPolicyApplicationAuthorization:
    """Explicit human decision about one exact policy-change candidate."""

    authorization_id: str
    status: MasterAllocationPolicyApplicationAuthorizationStatus
    action: MasterAllocationPolicyApplicationAuthorizationAction
    master_portfolio_id: str
    change_candidate_id: str
    change_candidate_fingerprint_sha256: str
    base_policy_id: str
    base_policy_fingerprint_sha256: str
    operator_ref: str
    rationale_codes: tuple[str, ...]
    decided_at: datetime
    fingerprint_sha256: str
    human_operator_required: bool = field(default=True, init=False)
    single_candidate_scope: bool = field(default=True, init=False)
    deterministic_preflight_required: bool = field(default=True, init=False)
    atomic_compare_and_swap_required: bool = field(default=True, init=False)
    policy_application_performed: bool = field(default=False, init=False)
    runtime_policy_application_authority: bool = field(default=False, init=False)
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
            "authorization_id",
            "master_portfolio_id",
            "change_candidate_id",
            "base_policy_id",
            "operator_ref",
        ):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), field_name=name),
            )
        for name in (
            "change_candidate_fingerprint_sha256",
            "base_policy_fingerprint_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), field_name=name))
        object.__setattr__(
            self,
            "rationale_codes",
            _canonical_text_values(self.rationale_codes, field_name="rationale_codes"),
        )
        object.__setattr__(self, "decided_at", _utc(self.decided_at, field_name="decided_at"))
        if self.status is not _authorization_status(self.action):
            raise ValueError("policy application authorization status does not match action")
        if self.schema_version != "1.0":
            raise ValueError("unsupported policy application authorization schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_allocation_policy_application_authorization_payload(self))
        if normalized != expected:
            raise ValueError("policy application authorization fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_policy_application_authorization_payload(self)


def _validate_change_candidate_integrity(
    candidate: MasterAllocationPolicyChangeCandidate,
) -> None:
    if stable_digest(master_allocation_policy_change_candidate_payload(candidate)) != (
        candidate.fingerprint_sha256
    ):
        raise ValueError("policy application change candidate fingerprint integrity failure")
    expected_status = MasterAllocationPolicyChangeCandidateStatus.READY_FOR_OPERATOR_AUTHORIZATION
    if candidate.status is not expected_status:
        raise ValueError("policy application requires candidate ready for operator authorization")
    if not candidate.candidate_only:
        raise ValueError("policy application candidate must remain candidate-only")
    if not candidate.explicit_policy_application_authorization_required:
        raise ValueError("policy application candidate lost explicit authorization boundary")
    if candidate.policy_application_performed:
        raise ValueError("policy application candidate already claims application")
    if candidate.policy_application_authority:
        raise ValueError("policy application candidate cannot hold application authority")


def build_master_allocation_policy_application_authorization(
    *,
    candidate: MasterAllocationPolicyChangeCandidate,
    action: MasterAllocationPolicyApplicationAuthorizationAction,
    operator_ref: str,
    rationale_codes: tuple[str, ...],
    decided_at: datetime,
) -> MasterAllocationPolicyApplicationAuthorization:
    """Record a new human decision for one exact policy-change candidate."""

    _validate_change_candidate_integrity(candidate)
    normalized_operator_ref = _required_text(operator_ref, field_name="operator_ref")
    ordered_reasons = tuple(sorted(rationale_codes))
    _canonical_text_values(ordered_reasons, field_name="rationale_codes")
    normalized_decided_at = _utc(decided_at, field_name="decided_at")
    if normalized_decided_at < candidate.reviewed_at:
        raise ValueError("policy application authorization cannot predate advisory review")
    values = {
        "status": _authorization_status(action),
        "action": action,
        "master_portfolio_id": candidate.master_portfolio_id,
        "change_candidate_id": candidate.change_candidate_id,
        "change_candidate_fingerprint_sha256": candidate.fingerprint_sha256,
        "base_policy_id": candidate.base_policy_id,
        "base_policy_fingerprint_sha256": candidate.base_policy_fingerprint_sha256,
        "operator_ref": normalized_operator_ref,
        "rationale_codes": ordered_reasons,
        "decided_at": normalized_decided_at,
    }
    authorization_id = "master-allocation-policy-application-authorization:" + stable_digest(
        {
            "schema": "money-heist.master-allocation-policy-application-authorization-id.v1",
            **values,
        }
    )
    provisional = MasterAllocationPolicyApplicationAuthorization.__new__(
        MasterAllocationPolicyApplicationAuthorization
    )
    object.__setattr__(provisional, "authorization_id", authorization_id)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterAllocationPolicyApplicationAuthorization(
        authorization_id=authorization_id,
        **values,
        fingerprint_sha256=stable_digest(
            master_allocation_policy_application_authorization_payload(provisional)
        ),
    )


def master_allocation_policy_application_preflight_payload(
    preflight: MasterAllocationPolicyApplicationPreflight,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-policy-application-preflight.v1",
        "schema_version": preflight.schema_version,
        "preflight_id": preflight.preflight_id,
        "status": preflight.status,
        "reason_codes": preflight.reason_codes,
        "master_portfolio_id": preflight.master_portfolio_id,
        "change_candidate_id": preflight.change_candidate_id,
        "change_candidate_fingerprint_sha256": preflight.change_candidate_fingerprint_sha256,
        "authorization_id": preflight.authorization_id,
        "authorization_fingerprint_sha256": preflight.authorization_fingerprint_sha256,
        "base_policy_id": preflight.base_policy_id,
        "base_policy_fingerprint_sha256": preflight.base_policy_fingerprint_sha256,
        "current_policy_id": preflight.current_policy_id,
        "current_policy_fingerprint_sha256": preflight.current_policy_fingerprint_sha256,
        "proposed_system_ids": preflight.proposed_system_ids,
        "operator_authorization_verified": preflight.operator_authorization_verified,
        "base_policy_identity_verified": preflight.base_policy_identity_verified,
        "base_policy_fingerprint_verified": preflight.base_policy_fingerprint_verified,
        "membership_verified": preflight.membership_verified,
        "configuration_verified": preflight.configuration_verified,
        "checked_at": preflight.checked_at,
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationPolicyApplicationPreflight:
    """Read-only deterministic preflight. It does not mutate allocation policy state."""

    preflight_id: str
    status: MasterAllocationPolicyApplicationPreflightStatus
    reason_codes: tuple[MasterAllocationPolicyApplicationPreflightReasonCode, ...]
    master_portfolio_id: str
    change_candidate_id: str
    change_candidate_fingerprint_sha256: str
    authorization_id: str
    authorization_fingerprint_sha256: str
    base_policy_id: str
    base_policy_fingerprint_sha256: str
    current_policy_id: str
    current_policy_fingerprint_sha256: str
    proposed_system_ids: tuple[str, ...]
    operator_authorization_verified: bool
    base_policy_identity_verified: bool
    base_policy_fingerprint_verified: bool
    membership_verified: bool
    configuration_verified: bool
    checked_at: datetime
    fingerprint_sha256: str
    preflight_only: bool = field(default=True, init=False)
    atomic_compare_and_swap_still_required: bool = field(default=True, init=False)
    policy_application_performed: bool = field(default=False, init=False)
    policy_mutation: bool = field(default=False, init=False)
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
            "preflight_id",
            "master_portfolio_id",
            "change_candidate_id",
            "authorization_id",
            "base_policy_id",
            "current_policy_id",
        ):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), field_name=name),
            )
        for name in (
            "change_candidate_fingerprint_sha256",
            "authorization_fingerprint_sha256",
            "base_policy_fingerprint_sha256",
            "current_policy_fingerprint_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), field_name=name))
        if not self.reason_codes:
            raise ValueError("policy application preflight reason_codes must not be empty")
        expected_reasons = tuple(sorted(set(self.reason_codes), key=lambda item: item.value))
        if self.reason_codes != expected_reasons:
            raise ValueError("policy application preflight reason_codes must be sorted and unique")
        normalized_system_ids = tuple(
            _required_text(value, field_name="proposed_system_ids")
            for value in self.proposed_system_ids
        )
        if not normalized_system_ids:
            raise ValueError("policy application preflight requires proposed_system_ids")
        if normalized_system_ids != tuple(sorted(normalized_system_ids)):
            raise ValueError("policy application preflight proposed_system_ids must be sorted")
        if len(set(normalized_system_ids)) != len(normalized_system_ids):
            raise ValueError("policy application preflight proposed_system_ids must be unique")
        object.__setattr__(self, "proposed_system_ids", normalized_system_ids)
        object.__setattr__(self, "checked_at", _utc(self.checked_at, field_name="checked_at"))
        ready = (
            self.status
            is MasterAllocationPolicyApplicationPreflightStatus.READY_FOR_APPLICATION
        )
        if ready:
            if self.reason_codes != (MasterAllocationPolicyApplicationPreflightReasonCode.READY,):
                raise ValueError("ready policy application preflight requires READY reason only")
            if not all(
                (
                    self.operator_authorization_verified,
                    self.base_policy_identity_verified,
                    self.base_policy_fingerprint_verified,
                    self.membership_verified,
                    self.configuration_verified,
                )
            ):
                raise ValueError("ready policy application preflight requires every verification")
        else:
            if self.status is not MasterAllocationPolicyApplicationPreflightStatus.BLOCKED:
                raise ValueError("unsupported policy application preflight status")
            if MasterAllocationPolicyApplicationPreflightReasonCode.READY in self.reason_codes:
                raise ValueError("blocked policy application preflight cannot carry READY reason")
        expected_authorization_verified = not any(
            reason
            in {
                MasterAllocationPolicyApplicationPreflightReasonCode.OPERATOR_REJECTED,
                MasterAllocationPolicyApplicationPreflightReasonCode.OPERATOR_DEFERRED,
            }
            for reason in self.reason_codes
        )
        expected_identity_verified = not any(
            reason
            in {
                MasterAllocationPolicyApplicationPreflightReasonCode.MASTER_PORTFOLIO_MISMATCH,
                MasterAllocationPolicyApplicationPreflightReasonCode.BASE_POLICY_ID_MISMATCH,
            }
            for reason in self.reason_codes
        )
        expected_fingerprint_verified = (
            MasterAllocationPolicyApplicationPreflightReasonCode.BASE_POLICY_FINGERPRINT_MISMATCH
            not in self.reason_codes
        )
        expected_membership_verified = (
            MasterAllocationPolicyApplicationPreflightReasonCode.MEMBERSHIP_MISMATCH
            not in self.reason_codes
        )
        expected_configuration_verified = (
            MasterAllocationPolicyApplicationPreflightReasonCode.BASE_POLICY_NOT_CONFIGURED
            not in self.reason_codes
        )
        expected_flags = (
            expected_authorization_verified,
            expected_identity_verified,
            expected_fingerprint_verified,
            expected_membership_verified,
            expected_configuration_verified,
        )
        actual_flags = (
            self.operator_authorization_verified,
            self.base_policy_identity_verified,
            self.base_policy_fingerprint_verified,
            self.membership_verified,
            self.configuration_verified,
        )
        if actual_flags != expected_flags:
            raise ValueError("policy application preflight verification flags do not match reasons")
        if self.schema_version != "1.0":
            raise ValueError("unsupported policy application preflight schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_allocation_policy_application_preflight_payload(self))
        if normalized != expected:
            raise ValueError("policy application preflight fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    @property
    def ready_for_application(self) -> bool:
        return self.status is MasterAllocationPolicyApplicationPreflightStatus.READY_FOR_APPLICATION

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_policy_application_preflight_payload(self)


def _validate_authorization_integrity(
    *,
    candidate: MasterAllocationPolicyChangeCandidate,
    authorization: MasterAllocationPolicyApplicationAuthorization,
) -> None:
    _validate_change_candidate_integrity(candidate)
    if stable_digest(master_allocation_policy_application_authorization_payload(authorization)) != (
        authorization.fingerprint_sha256
    ):
        raise ValueError("policy application authorization fingerprint integrity failure")
    expected_status = _authorization_status(authorization.action)
    if authorization.status is not expected_status:
        raise ValueError("policy application authorization status/action mismatch")
    bindings = (
        (authorization.master_portfolio_id, candidate.master_portfolio_id),
        (authorization.change_candidate_id, candidate.change_candidate_id),
        (authorization.change_candidate_fingerprint_sha256, candidate.fingerprint_sha256),
        (authorization.base_policy_id, candidate.base_policy_id),
        (
            authorization.base_policy_fingerprint_sha256,
            candidate.base_policy_fingerprint_sha256,
        ),
    )
    if any(left != right for left, right in bindings):
        raise ValueError("policy application authorization candidate provenance mismatch")
    if authorization.decided_at < candidate.reviewed_at:
        raise ValueError("policy application authorization predates advisory review")


def _preflight_reasons(
    *,
    candidate: MasterAllocationPolicyChangeCandidate,
    authorization: MasterAllocationPolicyApplicationAuthorization,
    current_allocation_policy: MasterAllocationPolicy,
) -> tuple[MasterAllocationPolicyApplicationPreflightReasonCode, ...]:
    reasons: list[MasterAllocationPolicyApplicationPreflightReasonCode] = []
    if authorization.action is MasterAllocationPolicyApplicationAuthorizationAction.REJECT:
        reasons.append(MasterAllocationPolicyApplicationPreflightReasonCode.OPERATOR_REJECTED)
    elif authorization.action is MasterAllocationPolicyApplicationAuthorizationAction.DEFER:
        reasons.append(MasterAllocationPolicyApplicationPreflightReasonCode.OPERATOR_DEFERRED)
    if current_allocation_policy.master_portfolio_id != candidate.master_portfolio_id:
        reasons.append(
            MasterAllocationPolicyApplicationPreflightReasonCode.MASTER_PORTFOLIO_MISMATCH
        )
    if current_allocation_policy.policy_id != candidate.base_policy_id:
        reasons.append(MasterAllocationPolicyApplicationPreflightReasonCode.BASE_POLICY_ID_MISMATCH)
    if current_allocation_policy.fingerprint_sha256 != candidate.base_policy_fingerprint_sha256:
        reasons.append(
            MasterAllocationPolicyApplicationPreflightReasonCode.BASE_POLICY_FINGERPRINT_MISMATCH
        )
    if current_allocation_policy.status is not AllocationEnvelopeStatus.CONFIGURED:
        reasons.append(
            MasterAllocationPolicyApplicationPreflightReasonCode.BASE_POLICY_NOT_CONFIGURED
        )
    current_ids = tuple(member.system_id for member in current_allocation_policy.members)
    proposed_ids = tuple(envelope.system_id for envelope in candidate.proposed_envelopes)
    if current_ids != proposed_ids:
        reasons.append(MasterAllocationPolicyApplicationPreflightReasonCode.MEMBERSHIP_MISMATCH)
    if not reasons:
        return (MasterAllocationPolicyApplicationPreflightReasonCode.READY,)
    return tuple(sorted(set(reasons), key=lambda item: item.value))


def evaluate_master_allocation_policy_application_preflight(
    *,
    candidate: MasterAllocationPolicyChangeCandidate,
    authorization: MasterAllocationPolicyApplicationAuthorization,
    current_allocation_policy: MasterAllocationPolicy,
    checked_at: datetime,
) -> MasterAllocationPolicyApplicationPreflight:
    """Check operator authorization and current base-policy freshness without applying anything."""

    _validate_authorization_integrity(candidate=candidate, authorization=authorization)
    if _policy_fingerprint(current_allocation_policy) != (
        current_allocation_policy.fingerprint_sha256
    ):
        raise ValueError("policy application current policy fingerprint integrity failure")
    normalized_checked_at = _utc(checked_at, field_name="checked_at")
    if normalized_checked_at < authorization.decided_at:
        raise ValueError("policy application preflight cannot predate operator authorization")
    reasons = _preflight_reasons(
        candidate=candidate,
        authorization=authorization,
        current_allocation_policy=current_allocation_policy,
    )
    status = (
        MasterAllocationPolicyApplicationPreflightStatus.READY_FOR_APPLICATION
        if reasons == (MasterAllocationPolicyApplicationPreflightReasonCode.READY,)
        else MasterAllocationPolicyApplicationPreflightStatus.BLOCKED
    )
    current_ids = tuple(member.system_id for member in current_allocation_policy.members)
    proposed_ids = tuple(envelope.system_id for envelope in candidate.proposed_envelopes)
    values = {
        "status": status,
        "reason_codes": reasons,
        "master_portfolio_id": candidate.master_portfolio_id,
        "change_candidate_id": candidate.change_candidate_id,
        "change_candidate_fingerprint_sha256": candidate.fingerprint_sha256,
        "authorization_id": authorization.authorization_id,
        "authorization_fingerprint_sha256": authorization.fingerprint_sha256,
        "base_policy_id": candidate.base_policy_id,
        "base_policy_fingerprint_sha256": candidate.base_policy_fingerprint_sha256,
        "current_policy_id": current_allocation_policy.policy_id,
        "current_policy_fingerprint_sha256": current_allocation_policy.fingerprint_sha256,
        "proposed_system_ids": proposed_ids,
        "operator_authorization_verified": (
            authorization.status
            is MasterAllocationPolicyApplicationAuthorizationStatus.AUTHORIZED
        ),
        "base_policy_identity_verified": (
            current_allocation_policy.master_portfolio_id == candidate.master_portfolio_id
            and current_allocation_policy.policy_id == candidate.base_policy_id
        ),
        "base_policy_fingerprint_verified": (
            current_allocation_policy.fingerprint_sha256
            == candidate.base_policy_fingerprint_sha256
        ),
        "membership_verified": current_ids == proposed_ids,
        "configuration_verified": (
            current_allocation_policy.status is AllocationEnvelopeStatus.CONFIGURED
        ),
        "checked_at": normalized_checked_at,
    }
    preflight_id = "master-allocation-policy-application-preflight:" + stable_digest(
        {
            "schema": "money-heist.master-allocation-policy-application-preflight-id.v1",
            **values,
        }
    )
    provisional = MasterAllocationPolicyApplicationPreflight.__new__(
        MasterAllocationPolicyApplicationPreflight
    )
    object.__setattr__(provisional, "preflight_id", preflight_id)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterAllocationPolicyApplicationPreflight(
        preflight_id=preflight_id,
        **values,
        fingerprint_sha256=stable_digest(
            master_allocation_policy_application_preflight_payload(provisional)
        ),
    )


__all__ = [
    "MasterAllocationPolicyApplicationAuthorization",
    "MasterAllocationPolicyApplicationAuthorizationAction",
    "MasterAllocationPolicyApplicationAuthorizationStatus",
    "MasterAllocationPolicyApplicationPreflight",
    "MasterAllocationPolicyApplicationPreflightReasonCode",
    "MasterAllocationPolicyApplicationPreflightStatus",
    "build_master_allocation_policy_application_authorization",
    "evaluate_master_allocation_policy_application_preflight",
    "master_allocation_policy_application_authorization_payload",
    "master_allocation_policy_application_preflight_payload",
]
