from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.services.backtest.ids import stable_digest
from app.trading.risk.models import RiskDecisionStatus

from .allocation import MasterAllocationPolicy
from .closure import build_reservation_closure_seal
from .models import MasterPortfolioSnapshot
from .reconciliation import build_reservation_reconciliation_report
from .reservation import (
    CrewReservationUsage,
    PortfolioReservation,
    ReservationLedgerSnapshot,
    ReservationRecordStatus,
)
from .risk_gate import (
    MasterRiskGateCandidate,
    MasterRiskGateDecision,
    MasterRiskGateDecisionStatus,
    MasterRiskGatePolicy,
    MasterRiskGateReasonCode,
)
from .risk_gate_admission import (
    ReservationAdmissionReasonCode,
    ReservationAdmissionReceipt,
    ReservationAdmissionTransitionStatus,
)


class MasterRiskGateClosureStatus(StrEnum):
    SEALED = "SEALED"


def _required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
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


def _sha256(value: str, *, field_name: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return normalized


def _optional_sha256(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _sha256(value, field_name=field_name)


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def master_risk_gate_closure_payload(
    seal: MasterRiskGateClosureSeal,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-risk-gate-closure.v1",
        "schema_version": seal.schema_version,
        "master_portfolio_id": seal.master_portfolio_id,
        "system_id": seal.system_id,
        "proposal_id": seal.proposal_id,
        "reservation_id": seal.reservation_id,
        "sealed_at": seal.sealed_at,
        "status": seal.status,
        "gate_policy_id": seal.gate_policy_id,
        "gate_policy_source_ref": seal.gate_policy_source_ref,
        "gate_policy_fingerprint_sha256": seal.gate_policy_fingerprint_sha256,
        "allocation_policy_fingerprint_sha256": seal.allocation_policy_fingerprint_sha256,
        "candidate_fingerprint_sha256": seal.candidate_fingerprint_sha256,
        "local_risk_decision_fingerprint_sha256": (
            seal.local_risk_decision_fingerprint_sha256
        ),
        "decision_id": seal.decision_id,
        "decision_status": seal.decision_status,
        "decision_reason_codes": seal.decision_reason_codes,
        "decision_fingerprint_sha256": seal.decision_fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": (
            seal.portfolio_snapshot_fingerprint_sha256
        ),
        "ledger_before_fingerprint_sha256": seal.ledger_before_fingerprint_sha256,
        "ledger_after_fingerprint_sha256": seal.ledger_after_fingerprint_sha256,
        "reservation_before_fingerprint_sha256": (
            seal.reservation_before_fingerprint_sha256
        ),
        "reservation_after_fingerprint_sha256": seal.reservation_after_fingerprint_sha256,
        "reservation_transition_status": seal.reservation_transition_status,
        "reservation_transition_reason_code": seal.reservation_transition_reason_code,
        "admission_receipt_fingerprint_sha256": seal.admission_receipt_fingerprint_sha256,
        "reservation_closure_before_fingerprint_sha256": (
            seal.reservation_closure_before_fingerprint_sha256
        ),
        "reservation_closure_after_fingerprint_sha256": (
            seal.reservation_closure_after_fingerprint_sha256
        ),
    }


def master_risk_gate_closure_fingerprint(seal: MasterRiskGateClosureSeal) -> str:
    return stable_digest(master_risk_gate_closure_payload(seal))


@dataclass(frozen=True, slots=True)
class MasterRiskGateClosureSeal:
    """Immutable provenance seal for one Master Risk Gate decision and ledger outcome."""

    master_portfolio_id: str
    system_id: str
    proposal_id: str
    reservation_id: str | None
    sealed_at: datetime
    status: MasterRiskGateClosureStatus
    gate_policy_id: str
    gate_policy_source_ref: str | None
    gate_policy_fingerprint_sha256: str
    allocation_policy_fingerprint_sha256: str
    candidate_fingerprint_sha256: str
    local_risk_decision_fingerprint_sha256: str
    decision_id: str
    decision_status: MasterRiskGateDecisionStatus
    decision_reason_codes: tuple[MasterRiskGateReasonCode, ...]
    decision_fingerprint_sha256: str
    portfolio_snapshot_fingerprint_sha256: str
    ledger_before_fingerprint_sha256: str
    ledger_after_fingerprint_sha256: str
    reservation_before_fingerprint_sha256: str | None
    reservation_after_fingerprint_sha256: str | None
    reservation_transition_status: ReservationAdmissionTransitionStatus | None
    reservation_transition_reason_code: ReservationAdmissionReasonCode | None
    admission_receipt_fingerprint_sha256: str | None
    reservation_closure_before_fingerprint_sha256: str
    reservation_closure_after_fingerprint_sha256: str
    closure_fingerprint_sha256: str
    mutation_applied: bool = field(default=False, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in (
            "master_portfolio_id",
            "system_id",
            "proposal_id",
            "gate_policy_id",
            "decision_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "reservation_id",
            _optional_text(self.reservation_id, field_name="reservation_id"),
        )
        object.__setattr__(
            self,
            "gate_policy_source_ref",
            _optional_text(self.gate_policy_source_ref, field_name="gate_policy_source_ref"),
        )
        object.__setattr__(self, "sealed_at", _utc(self.sealed_at, field_name="sealed_at"))
        if self.status is not MasterRiskGateClosureStatus.SEALED:
            raise ValueError("Master Risk Gate closure status must be SEALED")
        if not self.decision_reason_codes:
            raise ValueError("Master Risk Gate closure requires decision reason codes")
        if len(set(self.decision_reason_codes)) != len(self.decision_reason_codes):
            raise ValueError("Master Risk Gate closure decision reason codes must be unique")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master Risk Gate closure schema_version")

        for field_name in (
            "gate_policy_fingerprint_sha256",
            "allocation_policy_fingerprint_sha256",
            "candidate_fingerprint_sha256",
            "local_risk_decision_fingerprint_sha256",
            "decision_fingerprint_sha256",
            "portfolio_snapshot_fingerprint_sha256",
            "ledger_before_fingerprint_sha256",
            "ledger_after_fingerprint_sha256",
            "reservation_closure_before_fingerprint_sha256",
            "reservation_closure_after_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "reservation_before_fingerprint_sha256",
            "reservation_after_fingerprint_sha256",
            "admission_receipt_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_sha256(getattr(self, field_name), field_name=field_name),
            )

        optional_evidence = (
            self.reservation_id,
            self.reservation_before_fingerprint_sha256,
            self.reservation_after_fingerprint_sha256,
            self.reservation_transition_status,
            self.reservation_transition_reason_code,
            self.admission_receipt_fingerprint_sha256,
        )
        if self.reservation_id is None:
            if any(value is not None for value in optional_evidence[1:]):
                raise ValueError("no-reservation closure cannot carry transition evidence")
            if self.decision_status is not MasterRiskGateDecisionStatus.REJECT:
                raise ValueError("no-reservation closure requires a REJECT decision")
            if self.ledger_before_fingerprint_sha256 != self.ledger_after_fingerprint_sha256:
                raise ValueError("no-reservation closure requires an unchanged ledger")
        elif any(value is None for value in optional_evidence[1:]):
            raise ValueError("reservation-bound closure requires complete transition evidence")

        normalized = _sha256(
            self.closure_fingerprint_sha256,
            field_name="closure_fingerprint_sha256",
        )
        expected = master_risk_gate_closure_fingerprint(self)
        if normalized != expected:
            raise ValueError("Master Risk Gate closure fingerprint does not match payload")
        object.__setattr__(self, "closure_fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_risk_gate_closure_payload(self)


def _reservation_map(
    snapshot: ReservationLedgerSnapshot,
) -> dict[str, PortfolioReservation]:
    return {record.reservation_id: record for record in snapshot.reservations}


def _usage_map(snapshot: ReservationLedgerSnapshot) -> dict[str, CrewReservationUsage]:
    return {usage.system_id: usage for usage in snapshot.crew_usage}


def _validate_common_bindings(
    *,
    gate_policy: MasterRiskGatePolicy,
    allocation_policy: MasterAllocationPolicy,
    opening_snapshot: MasterPortfolioSnapshot,
    portfolio_snapshot: MasterPortfolioSnapshot,
    ledger_before: ReservationLedgerSnapshot,
    ledger_after: ReservationLedgerSnapshot,
    candidate: MasterRiskGateCandidate,
    decision: MasterRiskGateDecision,
) -> None:
    master_id = gate_policy.master_portfolio_id
    if any(
        item != master_id
        for item in (
            allocation_policy.master_portfolio_id,
            opening_snapshot.master_portfolio_id,
            portfolio_snapshot.master_portfolio_id,
            ledger_before.master_portfolio_id,
            ledger_after.master_portfolio_id,
            candidate.master_portfolio_id,
        )
    ):
        raise ValueError("Master Risk Gate closure inputs belong to different portfolios")
    if gate_policy.allocation_policy_fingerprint_sha256 != allocation_policy.fingerprint_sha256:
        raise ValueError("gate policy does not bind to supplied allocation policy")
    if ledger_before.policy_fingerprint_sha256 != allocation_policy.fingerprint_sha256:
        raise ValueError("ledger_before does not bind to supplied allocation policy")
    if ledger_after.policy_fingerprint_sha256 != allocation_policy.fingerprint_sha256:
        raise ValueError("ledger_after does not bind to supplied allocation policy")
    if any(
        snapshot.opening_snapshot_fingerprint_sha256 != opening_snapshot.fingerprint_sha256
        for snapshot in (ledger_before, ledger_after)
    ):
        raise ValueError("ledger snapshots do not bind to supplied opening snapshot")
    if decision.candidate_fingerprint_sha256 != candidate.fingerprint_sha256:
        raise ValueError("gate decision does not bind to supplied candidate")
    if (
        decision.local_risk_decision_fingerprint_sha256
        != candidate.local_risk_decision_fingerprint_sha256
    ):
        raise ValueError("gate decision local Risk binding differs from candidate")
    if decision.gate_policy_fingerprint_sha256 != gate_policy.fingerprint_sha256:
        raise ValueError("gate decision does not bind to supplied gate policy")
    if decision.portfolio_snapshot_fingerprint_sha256 != portfolio_snapshot.fingerprint_sha256:
        raise ValueError("gate decision does not bind to supplied portfolio snapshot")
    if decision.reservation_ledger_fingerprint_sha256 != ledger_before.fingerprint_sha256:
        raise ValueError("gate decision does not bind to supplied pre-transition ledger")


def _validate_unchanged_reservations(
    *,
    ledger_before: ReservationLedgerSnapshot,
    ledger_after: ReservationLedgerSnapshot,
    target_reservation_id: str,
) -> None:
    before = _reservation_map(ledger_before)
    after = _reservation_map(ledger_after)
    if set(before) != set(after):
        raise ValueError("reservation set changed during admission transition")
    for reservation_id in before:
        if reservation_id == target_reservation_id:
            continue
        if before[reservation_id].fingerprint_sha256 != after[reservation_id].fingerprint_sha256:
            raise ValueError("non-target reservation changed during admission transition")


def _validate_crew_usage_delta(
    *,
    ledger_before: ReservationLedgerSnapshot,
    ledger_after: ReservationLedgerSnapshot,
    reservation_before: PortfolioReservation,
    decision_status: MasterRiskGateDecisionStatus,
) -> None:
    request = reservation_before.request
    before_usage = _usage_map(ledger_before)
    after_usage = _usage_map(ledger_after)
    if set(before_usage) != set(after_usage):
        raise ValueError("crew usage membership changed during admission transition")
    for system_id in before_usage:
        before = before_usage[system_id]
        after = after_usage[system_id]
        if system_id != request.system_id:
            if before != after:
                raise ValueError("non-target crew usage changed during admission transition")
            continue

        if decision_status is MasterRiskGateDecisionStatus.ADMIT:
            expected = CrewReservationUsage(
                system_id=system_id,
                reserved_capital_amount=before.reserved_capital_amount - request.capital_amount,
                committed_capital_amount=before.committed_capital_amount + request.capital_amount,
                active_capital_amount=before.active_capital_amount,
                reserved_open_risk_amount=(
                    before.reserved_open_risk_amount - request.open_risk_amount
                ),
                committed_open_risk_amount=(
                    before.committed_open_risk_amount + request.open_risk_amount
                ),
                active_open_risk_amount=before.active_open_risk_amount,
                reserved_gross_exposure_amount=(
                    before.reserved_gross_exposure_amount - request.gross_exposure_amount
                ),
                committed_gross_exposure_amount=(
                    before.committed_gross_exposure_amount + request.gross_exposure_amount
                ),
                active_gross_exposure_amount=before.active_gross_exposure_amount,
            )
        else:
            expected = CrewReservationUsage(
                system_id=system_id,
                reserved_capital_amount=before.reserved_capital_amount - request.capital_amount,
                committed_capital_amount=before.committed_capital_amount,
                active_capital_amount=before.active_capital_amount - request.capital_amount,
                reserved_open_risk_amount=(
                    before.reserved_open_risk_amount - request.open_risk_amount
                ),
                committed_open_risk_amount=before.committed_open_risk_amount,
                active_open_risk_amount=before.active_open_risk_amount - request.open_risk_amount,
                reserved_gross_exposure_amount=(
                    before.reserved_gross_exposure_amount - request.gross_exposure_amount
                ),
                committed_gross_exposure_amount=before.committed_gross_exposure_amount,
                active_gross_exposure_amount=(
                    before.active_gross_exposure_amount - request.gross_exposure_amount
                ),
            )
        if after != expected:
            raise ValueError("target crew usage delta does not match admission transition")


def _validate_ledger_totals_delta(
    *,
    ledger_before: ReservationLedgerSnapshot,
    ledger_after: ReservationLedgerSnapshot,
    reservation_before: PortfolioReservation,
    decision_status: MasterRiskGateDecisionStatus,
) -> None:
    request = reservation_before.request
    if ledger_after.master_capital_capacity_amount != ledger_before.master_capital_capacity_amount:
        raise ValueError("Master capital capacity changed during admission transition")
    if decision_status is MasterRiskGateDecisionStatus.ADMIT:
        checks = (
            (
                ledger_after.reserved_capital_amount,
                ledger_before.reserved_capital_amount - request.capital_amount,
            ),
            (
                ledger_after.committed_capital_amount,
                ledger_before.committed_capital_amount + request.capital_amount,
            ),
            (ledger_after.active_capital_amount, ledger_before.active_capital_amount),
            (ledger_after.available_capital_amount, ledger_before.available_capital_amount),
        )
    else:
        checks = (
            (
                ledger_after.reserved_capital_amount,
                ledger_before.reserved_capital_amount - request.capital_amount,
            ),
            (ledger_after.committed_capital_amount, ledger_before.committed_capital_amount),
            (
                ledger_after.active_capital_amount,
                ledger_before.active_capital_amount - request.capital_amount,
            ),
            (
                ledger_after.available_capital_amount,
                ledger_before.available_capital_amount + request.capital_amount,
            ),
        )
    if any(actual != expected for actual, expected in checks):
        raise ValueError("ledger capital totals do not match admission transition")


def _validate_transition_evidence(
    *,
    ledger_before: ReservationLedgerSnapshot,
    ledger_after: ReservationLedgerSnapshot,
    candidate: MasterRiskGateCandidate,
    decision: MasterRiskGateDecision,
    receipt: ReservationAdmissionReceipt | None,
) -> tuple[PortfolioReservation | None, PortfolioReservation | None]:
    if candidate.reservation_id is None:
        if candidate.local_risk_status is not RiskDecisionStatus.REJECTED:
            raise ValueError("reservation-free candidate must originate from local Risk rejection")
        if decision.status is not MasterRiskGateDecisionStatus.REJECT:
            raise ValueError("reservation-free candidate cannot be admitted")
        if MasterRiskGateReasonCode.LOCAL_RISK_NOT_AUTHORIZED not in decision.reason_codes:
            raise ValueError("reservation-free rejection must preserve local Risk rejection reason")
        if receipt is not None:
            raise ValueError("reservation-free closure cannot carry admission receipt")
        if ledger_before.fingerprint_sha256 != ledger_after.fingerprint_sha256:
            raise ValueError("reservation-free rejection must leave ledger unchanged")
        return None, None

    if receipt is None:
        raise ValueError("reservation-bound closure requires admission receipt")
    before_map = _reservation_map(ledger_before)
    after_map = _reservation_map(ledger_after)
    if candidate.reservation_id not in before_map or candidate.reservation_id not in after_map:
        raise ValueError("candidate reservation must exist in both ledger snapshots")
    before = before_map[candidate.reservation_id]
    after = after_map[candidate.reservation_id]
    if before.status is not ReservationRecordStatus.RESERVED:
        raise ValueError("pre-transition candidate reservation must be RESERVED")
    if before.request.system_id != candidate.system_id:
        raise ValueError("candidate reservation system_id mismatch")
    if before.request.request_ref != candidate.proposal_id:
        raise ValueError("candidate reservation proposal reference mismatch")
    if before.request.open_risk_amount != candidate.local_approved_risk_amount:
        raise ValueError("candidate reservation open-risk amount mismatch")
    if before.request.gross_exposure_amount != candidate.local_approved_notional:
        raise ValueError("candidate reservation gross-exposure amount mismatch")
    if before.request != after.request:
        raise ValueError("reservation request payload changed during admission transition")
    if before.master_portfolio_id != after.master_portfolio_id:
        raise ValueError("reservation Master Portfolio changed during admission transition")
    if before.policy_fingerprint_sha256 != after.policy_fingerprint_sha256:
        raise ValueError("reservation policy provenance changed during admission transition")
    if before.opening_snapshot_fingerprint_sha256 != after.opening_snapshot_fingerprint_sha256:
        raise ValueError("reservation opening provenance changed during admission transition")

    expected_status = (
        ReservationRecordStatus.COMMITTED
        if decision.status is MasterRiskGateDecisionStatus.ADMIT
        else ReservationRecordStatus.RELEASED
    )
    if after.status is not expected_status:
        raise ValueError("post-transition reservation status does not match gate decision")
    if decision.status is MasterRiskGateDecisionStatus.ADMIT:
        if (
            after.committed_at != decision.created_at
            or after.commit_ref != decision.decision_id
            or after.released_at is not None
            or after.release_ref is not None
        ):
            raise ValueError("COMMITTED reservation metadata does not match gate decision")
        expected_transition = ReservationAdmissionTransitionStatus.COMMITTED
        expected_reason = ReservationAdmissionReasonCode.ADMITTED_COMMITTED
    else:
        if (
            after.committed_at is not None
            or after.commit_ref is not None
            or after.released_at != decision.created_at
            or after.release_ref != decision.decision_id
        ):
            raise ValueError("RELEASED reservation metadata does not match gate decision")
        expected_transition = ReservationAdmissionTransitionStatus.RELEASED
        expected_reason = ReservationAdmissionReasonCode.REJECTED_RELEASED

    if (
        receipt.master_portfolio_id != candidate.master_portfolio_id
        or receipt.system_id != candidate.system_id
        or receipt.proposal_id != candidate.proposal_id
        or receipt.reservation_id != candidate.reservation_id
        or receipt.gate_decision_id != decision.decision_id
        or receipt.gate_decision_status is not decision.status
        or receipt.transition_status is not expected_transition
        or receipt.reason_code is not expected_reason
        or receipt.candidate_fingerprint_sha256 != candidate.fingerprint_sha256
        or receipt.gate_decision_fingerprint_sha256 != decision.fingerprint_sha256
        or receipt.evaluated_ledger_fingerprint_sha256 != ledger_before.fingerprint_sha256
        or receipt.resulting_reservation_fingerprint_sha256 != after.fingerprint_sha256
        or receipt.transitioned_at != decision.created_at
        or receipt.transition_ref != decision.decision_id
    ):
        raise ValueError("admission receipt does not bind to supplied transition evidence")

    _validate_unchanged_reservations(
        ledger_before=ledger_before,
        ledger_after=ledger_after,
        target_reservation_id=candidate.reservation_id,
    )
    _validate_crew_usage_delta(
        ledger_before=ledger_before,
        ledger_after=ledger_after,
        reservation_before=before,
        decision_status=decision.status,
    )
    _validate_ledger_totals_delta(
        ledger_before=ledger_before,
        ledger_after=ledger_after,
        reservation_before=before,
        decision_status=decision.status,
    )
    return before, after


def build_master_risk_gate_closure_seal(
    *,
    gate_policy: MasterRiskGatePolicy,
    allocation_policy: MasterAllocationPolicy,
    opening_snapshot: MasterPortfolioSnapshot,
    portfolio_snapshot: MasterPortfolioSnapshot,
    ledger_before: ReservationLedgerSnapshot,
    ledger_after: ReservationLedgerSnapshot,
    candidate: MasterRiskGateCandidate,
    decision: MasterRiskGateDecision,
    receipt: ReservationAdmissionReceipt | None,
) -> MasterRiskGateClosureSeal:
    """Seal one gate decision and its ledger effect without mutation or source re-reads."""

    _validate_common_bindings(
        gate_policy=gate_policy,
        allocation_policy=allocation_policy,
        opening_snapshot=opening_snapshot,
        portfolio_snapshot=portfolio_snapshot,
        ledger_before=ledger_before,
        ledger_after=ledger_after,
        candidate=candidate,
        decision=decision,
    )
    reservation_before, reservation_after = _validate_transition_evidence(
        ledger_before=ledger_before,
        ledger_after=ledger_after,
        candidate=candidate,
        decision=decision,
        receipt=receipt,
    )

    reconciliation_before = build_reservation_reconciliation_report(
        policy=allocation_policy,
        ledger_snapshot=ledger_before,
        portfolio_snapshot=portfolio_snapshot,
    )
    reconciliation_after = build_reservation_reconciliation_report(
        policy=allocation_policy,
        ledger_snapshot=ledger_after,
        portfolio_snapshot=portfolio_snapshot,
    )
    reservation_closure_before = build_reservation_closure_seal(
        policy=allocation_policy,
        opening_snapshot=opening_snapshot,
        portfolio_snapshot=portfolio_snapshot,
        ledger_snapshot=ledger_before,
        reconciliation_report=reconciliation_before,
    )
    reservation_closure_after = build_reservation_closure_seal(
        policy=allocation_policy,
        opening_snapshot=opening_snapshot,
        portfolio_snapshot=portfolio_snapshot,
        ledger_snapshot=ledger_after,
        reconciliation_report=reconciliation_after,
    )

    transition_status = receipt.transition_status if receipt is not None else None
    transition_reason = receipt.reason_code if receipt is not None else None
    receipt_fingerprint = receipt.fingerprint_sha256 if receipt is not None else None
    before_reservation_fingerprint = (
        reservation_before.fingerprint_sha256 if reservation_before is not None else None
    )
    after_reservation_fingerprint = (
        reservation_after.fingerprint_sha256 if reservation_after is not None else None
    )
    payload = {
        "schema": "money-heist.master-risk-gate-closure.v1",
        "schema_version": "1.0",
        "master_portfolio_id": candidate.master_portfolio_id,
        "system_id": candidate.system_id,
        "proposal_id": candidate.proposal_id,
        "reservation_id": candidate.reservation_id,
        "sealed_at": decision.created_at,
        "status": MasterRiskGateClosureStatus.SEALED,
        "gate_policy_id": gate_policy.gate_policy_id,
        "gate_policy_source_ref": gate_policy.source_ref,
        "gate_policy_fingerprint_sha256": gate_policy.fingerprint_sha256,
        "allocation_policy_fingerprint_sha256": allocation_policy.fingerprint_sha256,
        "candidate_fingerprint_sha256": candidate.fingerprint_sha256,
        "local_risk_decision_fingerprint_sha256": (
            candidate.local_risk_decision_fingerprint_sha256
        ),
        "decision_id": decision.decision_id,
        "decision_status": decision.status,
        "decision_reason_codes": decision.reason_codes,
        "decision_fingerprint_sha256": decision.fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": portfolio_snapshot.fingerprint_sha256,
        "ledger_before_fingerprint_sha256": ledger_before.fingerprint_sha256,
        "ledger_after_fingerprint_sha256": ledger_after.fingerprint_sha256,
        "reservation_before_fingerprint_sha256": before_reservation_fingerprint,
        "reservation_after_fingerprint_sha256": after_reservation_fingerprint,
        "reservation_transition_status": transition_status,
        "reservation_transition_reason_code": transition_reason,
        "admission_receipt_fingerprint_sha256": receipt_fingerprint,
        "reservation_closure_before_fingerprint_sha256": (
            reservation_closure_before.closure_fingerprint_sha256
        ),
        "reservation_closure_after_fingerprint_sha256": (
            reservation_closure_after.closure_fingerprint_sha256
        ),
    }
    return MasterRiskGateClosureSeal(
        master_portfolio_id=candidate.master_portfolio_id,
        system_id=candidate.system_id,
        proposal_id=candidate.proposal_id,
        reservation_id=candidate.reservation_id,
        sealed_at=decision.created_at,
        status=MasterRiskGateClosureStatus.SEALED,
        gate_policy_id=gate_policy.gate_policy_id,
        gate_policy_source_ref=gate_policy.source_ref,
        gate_policy_fingerprint_sha256=gate_policy.fingerprint_sha256,
        allocation_policy_fingerprint_sha256=allocation_policy.fingerprint_sha256,
        candidate_fingerprint_sha256=candidate.fingerprint_sha256,
        local_risk_decision_fingerprint_sha256=(
            candidate.local_risk_decision_fingerprint_sha256
        ),
        decision_id=decision.decision_id,
        decision_status=decision.status,
        decision_reason_codes=decision.reason_codes,
        decision_fingerprint_sha256=decision.fingerprint_sha256,
        portfolio_snapshot_fingerprint_sha256=portfolio_snapshot.fingerprint_sha256,
        ledger_before_fingerprint_sha256=ledger_before.fingerprint_sha256,
        ledger_after_fingerprint_sha256=ledger_after.fingerprint_sha256,
        reservation_before_fingerprint_sha256=before_reservation_fingerprint,
        reservation_after_fingerprint_sha256=after_reservation_fingerprint,
        reservation_transition_status=transition_status,
        reservation_transition_reason_code=transition_reason,
        admission_receipt_fingerprint_sha256=receipt_fingerprint,
        reservation_closure_before_fingerprint_sha256=(
            reservation_closure_before.closure_fingerprint_sha256
        ),
        reservation_closure_after_fingerprint_sha256=(
            reservation_closure_after.closure_fingerprint_sha256
        ),
        closure_fingerprint_sha256=stable_digest(payload),
    )


__all__ = [
    "MasterRiskGateClosureSeal",
    "MasterRiskGateClosureStatus",
    "build_master_risk_gate_closure_seal",
    "master_risk_gate_closure_fingerprint",
]
