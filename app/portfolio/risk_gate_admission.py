from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Never

from app.services.backtest.ids import stable_digest

from .reservation import (
    MasterReservationLedger,
    PortfolioReservation,
    ReservationRecordStatus,
    ReservationStateTransitionError,
)
from .risk_gate import (
    MasterRiskGateCandidate,
    MasterRiskGateDecision,
    MasterRiskGateDecisionStatus,
)


class ReservationAdmissionTransitionStatus(StrEnum):
    COMMITTED = "COMMITTED"
    RELEASED = "RELEASED"


class ReservationAdmissionReasonCode(StrEnum):
    ADMITTED_COMMITTED = "ADMITTED_COMMITTED"
    REJECTED_RELEASED = "REJECTED_RELEASED"
    CANDIDATE_DECISION_MISMATCH = "CANDIDATE_DECISION_MISMATCH"
    MASTER_PORTFOLIO_ID_MISMATCH = "MASTER_PORTFOLIO_ID_MISMATCH"
    RESERVATION_REQUIRED = "RESERVATION_REQUIRED"
    RESERVATION_NOT_FOUND = "RESERVATION_NOT_FOUND"
    RESERVATION_PAYLOAD_MISMATCH = "RESERVATION_PAYLOAD_MISMATCH"
    DECISION_PRECEDES_RESERVATION = "DECISION_PRECEDES_RESERVATION"
    STALE_LEDGER_SNAPSHOT = "STALE_LEDGER_SNAPSHOT"
    RESERVATION_STATE_CONFLICT = "RESERVATION_STATE_CONFLICT"


class ReservationAdmissionBridgeError(ValueError):
    def __init__(self, reason_code: ReservationAdmissionReasonCode, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


def _required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _sha256(value: str, *, field_name: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return normalized


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def reservation_admission_receipt_payload(
    receipt: ReservationAdmissionReceipt,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-reservation-admission-receipt.v1",
        "schema_version": receipt.schema_version,
        "master_portfolio_id": receipt.master_portfolio_id,
        "system_id": receipt.system_id,
        "proposal_id": receipt.proposal_id,
        "reservation_id": receipt.reservation_id,
        "gate_decision_id": receipt.gate_decision_id,
        "gate_decision_status": receipt.gate_decision_status,
        "transition_status": receipt.transition_status,
        "reason_code": receipt.reason_code,
        "candidate_fingerprint_sha256": receipt.candidate_fingerprint_sha256,
        "gate_decision_fingerprint_sha256": receipt.gate_decision_fingerprint_sha256,
        "evaluated_ledger_fingerprint_sha256": (
            receipt.evaluated_ledger_fingerprint_sha256
        ),
        "resulting_reservation_fingerprint_sha256": (
            receipt.resulting_reservation_fingerprint_sha256
        ),
        "transitioned_at": receipt.transitioned_at,
        "transition_ref": receipt.transition_ref,
    }


def reservation_admission_receipt_fingerprint(
    receipt: ReservationAdmissionReceipt,
) -> str:
    return stable_digest(reservation_admission_receipt_payload(receipt))


@dataclass(frozen=True, slots=True)
class ReservationAdmissionReceipt:
    """Immutable receipt for one gate-driven reservation state transition."""

    master_portfolio_id: str
    system_id: str
    proposal_id: str
    reservation_id: str
    gate_decision_id: str
    gate_decision_status: MasterRiskGateDecisionStatus
    transition_status: ReservationAdmissionTransitionStatus
    reason_code: ReservationAdmissionReasonCode
    candidate_fingerprint_sha256: str
    gate_decision_fingerprint_sha256: str
    evaluated_ledger_fingerprint_sha256: str
    resulting_reservation_fingerprint_sha256: str
    transitioned_at: datetime
    transition_ref: str
    fingerprint_sha256: str
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    reservation_transition: bool = field(default=True, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in (
            "master_portfolio_id",
            "system_id",
            "proposal_id",
            "reservation_id",
            "gate_decision_id",
            "transition_ref",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "candidate_fingerprint_sha256",
            "gate_decision_fingerprint_sha256",
            "evaluated_ledger_fingerprint_sha256",
            "resulting_reservation_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "transitioned_at",
            _utc(self.transitioned_at, field_name="transitioned_at"),
        )
        if self.schema_version != "1.0":
            raise ValueError("unsupported reservation admission receipt schema_version")
        if self.gate_decision_status is MasterRiskGateDecisionStatus.ADMIT:
            if self.transition_status is not ReservationAdmissionTransitionStatus.COMMITTED:
                raise ValueError("ADMIT receipt must transition reservation to COMMITTED")
            if self.reason_code is not ReservationAdmissionReasonCode.ADMITTED_COMMITTED:
                raise ValueError("ADMIT receipt requires ADMITTED_COMMITTED reason code")
        elif self.gate_decision_status is MasterRiskGateDecisionStatus.REJECT:
            if self.transition_status is not ReservationAdmissionTransitionStatus.RELEASED:
                raise ValueError("REJECT receipt must transition reservation to RELEASED")
            if self.reason_code is not ReservationAdmissionReasonCode.REJECTED_RELEASED:
                raise ValueError("REJECT receipt requires REJECTED_RELEASED reason code")
        else:
            raise ValueError(f"unsupported gate decision status: {self.gate_decision_status}")

        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = reservation_admission_receipt_fingerprint(self)
        if normalized != expected:
            raise ValueError("reservation admission receipt fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def _error(reason_code: ReservationAdmissionReasonCode, message: str) -> Never:
    raise ReservationAdmissionBridgeError(reason_code, message)


def _validate_candidate_decision(
    *,
    candidate: MasterRiskGateCandidate,
    decision: MasterRiskGateDecision,
) -> None:
    if (
        decision.candidate_fingerprint_sha256 != candidate.fingerprint_sha256
        or decision.local_risk_decision_fingerprint_sha256
        != candidate.local_risk_decision_fingerprint_sha256
        or decision.local_risk_status is not candidate.local_risk_status
        or decision.local_approved_quantity != candidate.local_approved_quantity
        or decision.local_approved_risk_amount != candidate.local_approved_risk_amount
        or decision.local_approved_notional != candidate.local_approved_notional
    ):
        _error(
            ReservationAdmissionReasonCode.CANDIDATE_DECISION_MISMATCH,
            "Master Risk Gate decision does not bind to the supplied candidate",
        )


def _validate_reservation_binding(
    *,
    ledger: MasterReservationLedger,
    candidate: MasterRiskGateCandidate,
    reservation: PortfolioReservation,
) -> None:
    request = reservation.request
    if (
        reservation.reservation_id != candidate.reservation_id
        or reservation.master_portfolio_id != candidate.master_portfolio_id
        or reservation.policy_fingerprint_sha256 != ledger.policy.fingerprint_sha256
        or reservation.opening_snapshot_fingerprint_sha256
        != ledger.opening_snapshot.fingerprint_sha256
        or request.system_id != candidate.system_id
        or request.request_ref != candidate.proposal_id
        or request.requested_at < candidate.local_risk_created_at
        or request.open_risk_amount != candidate.local_approved_risk_amount
        or request.gross_exposure_amount != candidate.local_approved_notional
    ):
        _error(
            ReservationAdmissionReasonCode.RESERVATION_PAYLOAD_MISMATCH,
            "reservation payload does not match the Master Risk Gate candidate",
        )


def _is_exact_retry(
    *,
    reservation: PortfolioReservation,
    decision: MasterRiskGateDecision,
) -> bool:
    if decision.status is MasterRiskGateDecisionStatus.ADMIT:
        return (
            reservation.status is ReservationRecordStatus.COMMITTED
            and reservation.committed_at == decision.created_at
            and reservation.commit_ref == decision.decision_id
            and reservation.released_at is None
            and reservation.release_ref is None
        )
    return (
        reservation.status is ReservationRecordStatus.RELEASED
        and reservation.committed_at is None
        and reservation.commit_ref is None
        and reservation.released_at == decision.created_at
        and reservation.release_ref == decision.decision_id
    )


def _build_receipt(
    *,
    candidate: MasterRiskGateCandidate,
    decision: MasterRiskGateDecision,
    reservation: PortfolioReservation,
) -> ReservationAdmissionReceipt:
    if decision.status is MasterRiskGateDecisionStatus.ADMIT:
        transition_status = ReservationAdmissionTransitionStatus.COMMITTED
        reason_code = ReservationAdmissionReasonCode.ADMITTED_COMMITTED
    else:
        transition_status = ReservationAdmissionTransitionStatus.RELEASED
        reason_code = ReservationAdmissionReasonCode.REJECTED_RELEASED

    payload = {
        "schema": "money-heist.master-reservation-admission-receipt.v1",
        "schema_version": "1.0",
        "master_portfolio_id": candidate.master_portfolio_id,
        "system_id": candidate.system_id,
        "proposal_id": candidate.proposal_id,
        "reservation_id": reservation.reservation_id,
        "gate_decision_id": decision.decision_id,
        "gate_decision_status": decision.status,
        "transition_status": transition_status,
        "reason_code": reason_code,
        "candidate_fingerprint_sha256": candidate.fingerprint_sha256,
        "gate_decision_fingerprint_sha256": decision.fingerprint_sha256,
        "evaluated_ledger_fingerprint_sha256": decision.reservation_ledger_fingerprint_sha256,
        "resulting_reservation_fingerprint_sha256": reservation.fingerprint_sha256,
        "transitioned_at": decision.created_at,
        "transition_ref": decision.decision_id,
    }
    return ReservationAdmissionReceipt(
        master_portfolio_id=candidate.master_portfolio_id,
        system_id=candidate.system_id,
        proposal_id=candidate.proposal_id,
        reservation_id=reservation.reservation_id,
        gate_decision_id=decision.decision_id,
        gate_decision_status=decision.status,
        transition_status=transition_status,
        reason_code=reason_code,
        candidate_fingerprint_sha256=candidate.fingerprint_sha256,
        gate_decision_fingerprint_sha256=decision.fingerprint_sha256,
        evaluated_ledger_fingerprint_sha256=decision.reservation_ledger_fingerprint_sha256,
        resulting_reservation_fingerprint_sha256=reservation.fingerprint_sha256,
        transitioned_at=decision.created_at,
        transition_ref=decision.decision_id,
        fingerprint_sha256=stable_digest(payload),
    )


def apply_master_risk_gate_decision_to_reservation(
    *,
    ledger: MasterReservationLedger,
    candidate: MasterRiskGateCandidate,
    decision: MasterRiskGateDecision,
) -> ReservationAdmissionReceipt:
    """Apply one already-made Master admission decision to its reserved capacity.

    The bridge has no Risk, broker, or LIVE authority. A first ADMIT application requires the
    current ledger fingerprint to equal the exact snapshot evaluated by the Master gate. REJECT
    may still release its bound RESERVED capacity after unrelated ledger changes because release
    can only reduce active commitments. Exact retries produce the same immutable receipt.
    """

    _validate_candidate_decision(candidate=candidate, decision=decision)

    if candidate.master_portfolio_id != ledger.policy.master_portfolio_id:
        _error(
            ReservationAdmissionReasonCode.MASTER_PORTFOLIO_ID_MISMATCH,
            "candidate and reservation ledger belong to different Master Portfolios",
        )
    if candidate.reservation_id is None:
        _error(
            ReservationAdmissionReasonCode.RESERVATION_REQUIRED,
            "reservation admission bridge requires a reservation-bound candidate",
        )

    try:
        reservation = ledger.get(candidate.reservation_id)
    except KeyError:
        _error(
            ReservationAdmissionReasonCode.RESERVATION_NOT_FOUND,
            f"reservation {candidate.reservation_id!r} is not present in the ledger",
        )

    _validate_reservation_binding(
        ledger=ledger,
        candidate=candidate,
        reservation=reservation,
    )

    if decision.created_at < reservation.request.requested_at:
        _error(
            ReservationAdmissionReasonCode.DECISION_PRECEDES_RESERVATION,
            "Master Risk Gate decision cannot precede the reservation request",
        )

    if _is_exact_retry(reservation=reservation, decision=decision):
        return _build_receipt(
            candidate=candidate,
            decision=decision,
            reservation=reservation,
        )

    if reservation.status is not ReservationRecordStatus.RESERVED:
        _error(
            ReservationAdmissionReasonCode.RESERVATION_STATE_CONFLICT,
            "only RESERVED capacity may be transitioned by a new admission decision",
        )

    if decision.status is MasterRiskGateDecisionStatus.ADMIT:
        current_ledger = ledger.snapshot()
        if current_ledger.fingerprint_sha256 != decision.reservation_ledger_fingerprint_sha256:
            _error(
                ReservationAdmissionReasonCode.STALE_LEDGER_SNAPSHOT,
                "reservation ledger changed after the Master Risk Gate decision was evaluated",
            )

    try:
        if decision.status is MasterRiskGateDecisionStatus.ADMIT:
            transitioned = ledger.commit(
                reservation.reservation_id,
                committed_at=decision.created_at,
                commit_ref=decision.decision_id,
            )
        else:
            transitioned = ledger.release(
                reservation.reservation_id,
                released_at=decision.created_at,
                release_ref=decision.decision_id,
            )
    except ReservationStateTransitionError as exc:
        raise ReservationAdmissionBridgeError(
            ReservationAdmissionReasonCode.RESERVATION_STATE_CONFLICT,
            str(exc),
        ) from exc

    return _build_receipt(
        candidate=candidate,
        decision=decision,
        reservation=transitioned,
    )


__all__ = [
    "ReservationAdmissionBridgeError",
    "ReservationAdmissionReasonCode",
    "ReservationAdmissionReceipt",
    "ReservationAdmissionTransitionStatus",
    "apply_master_risk_gate_decision_to_reservation",
    "reservation_admission_receipt_fingerprint",
]
