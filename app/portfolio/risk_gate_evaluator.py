from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from .allocation import MasterAllocationPolicy
from .models import MasterPortfolioSnapshot, SnapshotDataStatus
from .reconciliation import (
    ReservationReconciliationStatus,
    build_reservation_reconciliation_report,
)
from .reservation import ReservationLedgerSnapshot, ReservationRecordStatus
from .risk_gate import (
    MasterRiskGateCandidate,
    MasterRiskGateDecision,
    MasterRiskGateDecisionStatus,
    MasterRiskGatePolicy,
    MasterRiskGatePolicyStatus,
    MasterRiskGateReasonCode,
    _build_master_risk_gate_decision,
)

ZERO = Decimal("0")


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _ordered_reasons(
    values: set[MasterRiskGateReasonCode],
) -> tuple[MasterRiskGateReasonCode, ...]:
    return tuple(code for code in MasterRiskGateReasonCode if code in values)


def _master_ids_match(
    *,
    gate_policy: MasterRiskGatePolicy,
    allocation_policy: MasterAllocationPolicy,
    candidate: MasterRiskGateCandidate,
    portfolio_snapshot: MasterPortfolioSnapshot,
    ledger_snapshot: ReservationLedgerSnapshot,
) -> bool:
    expected = gate_policy.master_portfolio_id
    return all(
        item == expected
        for item in (
            allocation_policy.master_portfolio_id,
            candidate.master_portfolio_id,
            portfolio_snapshot.master_portfolio_id,
            ledger_snapshot.master_portfolio_id,
        )
    )


def _system_is_member_everywhere(
    *,
    system_id: str,
    allocation_policy: MasterAllocationPolicy,
    portfolio_snapshot: MasterPortfolioSnapshot,
    ledger_snapshot: ReservationLedgerSnapshot,
) -> bool:
    allocation_ids = {member.system_id for member in allocation_policy.members}
    portfolio_ids = {member.system_id for member in portfolio_snapshot.members}
    ledger_ids = {usage.system_id for usage in ledger_snapshot.crew_usage}
    return all(system_id in values for values in (allocation_ids, portfolio_ids, ledger_ids))


def _reservation_matches_candidate(
    *,
    candidate: MasterRiskGateCandidate,
    reservation,
    allocation_policy: MasterAllocationPolicy,
) -> bool:
    request = reservation.request
    return (
        reservation.master_portfolio_id == candidate.master_portfolio_id
        and reservation.policy_fingerprint_sha256 == allocation_policy.fingerprint_sha256
        and request.system_id == candidate.system_id
        and request.request_ref == candidate.proposal_id
        and request.requested_at >= candidate.local_risk_created_at
        and request.open_risk_amount == candidate.local_approved_risk_amount
        and request.gross_exposure_amount == candidate.local_approved_notional
    )


def _active_projected_amounts(
    *,
    portfolio_snapshot: MasterPortfolioSnapshot,
    ledger_snapshot: ReservationLedgerSnapshot,
) -> tuple[Decimal, Decimal]:
    assert portfolio_snapshot.total_open_risk_amount is not None
    assert portfolio_snapshot.total_gross_exposure_amount is not None

    committed_risk = sum(
        (usage.committed_open_risk_amount for usage in ledger_snapshot.crew_usage),
        ZERO,
    )
    reserved_risk = sum(
        (usage.reserved_open_risk_amount for usage in ledger_snapshot.crew_usage),
        ZERO,
    )
    committed_gross = sum(
        (usage.committed_gross_exposure_amount for usage in ledger_snapshot.crew_usage),
        ZERO,
    )
    reserved_gross = sum(
        (usage.reserved_gross_exposure_amount for usage in ledger_snapshot.crew_usage),
        ZERO,
    )

    projected_risk = max(portfolio_snapshot.total_open_risk_amount, committed_risk) + reserved_risk
    projected_gross = (
        max(portfolio_snapshot.total_gross_exposure_amount, committed_gross) + reserved_gross
    )
    return projected_risk, projected_gross


def evaluate_master_risk_gate(
    *,
    gate_policy: MasterRiskGatePolicy,
    allocation_policy: MasterAllocationPolicy,
    candidate: MasterRiskGateCandidate,
    portfolio_snapshot: MasterPortfolioSnapshot,
    ledger_snapshot: ReservationLedgerSnapshot,
    evaluated_at: datetime,
) -> MasterRiskGateDecision:
    """Evaluate one candidate with veto-only Master Portfolio authority.

    The evaluator never mutates reservations and never resizes local Risk-approved amounts.
    RESERVED capacity is counted as concurrent future exposure. COMMITTED capacity is compared
    with observed exposure through the existing reservation reconciliation layer before global
    limits are evaluated.
    """

    normalized_time = _utc(evaluated_at, field_name="evaluated_at")
    reasons: set[MasterRiskGateReasonCode] = set()

    if not candidate.local_risk_authorized:
        reasons.add(MasterRiskGateReasonCode.LOCAL_RISK_NOT_AUTHORIZED)

    if gate_policy.status is not MasterRiskGatePolicyStatus.CONFIGURED:
        reasons.add(MasterRiskGateReasonCode.GATE_POLICY_NOT_CONFIGURED)

    ids_match = _master_ids_match(
        gate_policy=gate_policy,
        allocation_policy=allocation_policy,
        candidate=candidate,
        portfolio_snapshot=portfolio_snapshot,
        ledger_snapshot=ledger_snapshot,
    )
    if not ids_match:
        reasons.add(MasterRiskGateReasonCode.MASTER_PORTFOLIO_ID_MISMATCH)

    if gate_policy.allocation_policy_fingerprint_sha256 != allocation_policy.fingerprint_sha256:
        reasons.add(MasterRiskGateReasonCode.ALLOCATION_POLICY_MISMATCH)

    if ledger_snapshot.policy_fingerprint_sha256 != allocation_policy.fingerprint_sha256:
        reasons.add(MasterRiskGateReasonCode.LEDGER_POLICY_MISMATCH)

    if not _system_is_member_everywhere(
        system_id=candidate.system_id,
        allocation_policy=allocation_policy,
        portfolio_snapshot=portfolio_snapshot,
        ledger_snapshot=ledger_snapshot,
    ):
        reasons.add(MasterRiskGateReasonCode.SYSTEM_NOT_MEMBER)

    snapshot_available = (
        portfolio_snapshot.status is SnapshotDataStatus.AVAILABLE
        and portfolio_snapshot.aggregate_exposure_status is SnapshotDataStatus.AVAILABLE
        and portfolio_snapshot.total_open_risk_amount is not None
        and portfolio_snapshot.total_gross_exposure_amount is not None
    )
    if not snapshot_available:
        reasons.add(MasterRiskGateReasonCode.PORTFOLIO_SNAPSHOT_UNAVAILABLE)

    reservation = None
    if candidate.local_risk_authorized:
        reservation = next(
            (
                item
                for item in ledger_snapshot.reservations
                if item.reservation_id == candidate.reservation_id
            ),
            None,
        )
        if reservation is None:
            reasons.add(MasterRiskGateReasonCode.RESERVATION_NOT_FOUND)
        else:
            if reservation.status is not ReservationRecordStatus.RESERVED:
                reasons.add(MasterRiskGateReasonCode.RESERVATION_NOT_RESERVED)
            if not _reservation_matches_candidate(
                candidate=candidate,
                reservation=reservation,
                allocation_policy=allocation_policy,
            ):
                reasons.add(MasterRiskGateReasonCode.RESERVATION_PAYLOAD_MISMATCH)

    structural_context_valid = (
        ids_match
        and gate_policy.allocation_policy_fingerprint_sha256
        == allocation_policy.fingerprint_sha256
        and ledger_snapshot.policy_fingerprint_sha256 == allocation_policy.fingerprint_sha256
    )

    reconciliation_status: ReservationReconciliationStatus | None = None
    if structural_context_valid:
        reconciliation = build_reservation_reconciliation_report(
            policy=allocation_policy,
            ledger_snapshot=ledger_snapshot,
            portfolio_snapshot=portfolio_snapshot,
        )
        reconciliation_status = reconciliation.status
        if reconciliation_status is ReservationReconciliationStatus.UNAVAILABLE:
            reasons.add(MasterRiskGateReasonCode.RESERVATION_RECONCILIATION_UNAVAILABLE)
        elif reconciliation_status is ReservationReconciliationStatus.INCONSISTENT:
            reasons.add(MasterRiskGateReasonCode.RESERVATION_RECONCILIATION_INCONSISTENT)

    can_evaluate_limits = (
        gate_policy.status is MasterRiskGatePolicyStatus.CONFIGURED
        and snapshot_available
        and reconciliation_status
        in {
            ReservationReconciliationStatus.CONSISTENT,
            ReservationReconciliationStatus.PENDING,
        }
    )
    if can_evaluate_limits:
        assert gate_policy.max_total_open_risk_amount is not None
        assert gate_policy.max_total_gross_exposure_amount is not None
        projected_risk, projected_gross = _active_projected_amounts(
            portfolio_snapshot=portfolio_snapshot,
            ledger_snapshot=ledger_snapshot,
        )
        if projected_risk > gate_policy.max_total_open_risk_amount:
            reasons.add(MasterRiskGateReasonCode.MASTER_OPEN_RISK_LIMIT_EXCEEDED)
        if projected_gross > gate_policy.max_total_gross_exposure_amount:
            reasons.add(MasterRiskGateReasonCode.MASTER_GROSS_EXPOSURE_LIMIT_EXCEEDED)

    if reasons:
        status = MasterRiskGateDecisionStatus.REJECT
        reason_codes = _ordered_reasons(reasons)
    else:
        status = MasterRiskGateDecisionStatus.ADMIT
        reason_codes = (MasterRiskGateReasonCode.ADMITTED,)

    return _build_master_risk_gate_decision(
        candidate=candidate,
        status=status,
        reason_codes=reason_codes,
        gate_policy_fingerprint_sha256=gate_policy.fingerprint_sha256,
        portfolio_snapshot_fingerprint_sha256=portfolio_snapshot.fingerprint_sha256,
        reservation_ledger_fingerprint_sha256=ledger_snapshot.fingerprint_sha256,
        created_at=normalized_time,
    )


__all__ = ["evaluate_master_risk_gate"]
