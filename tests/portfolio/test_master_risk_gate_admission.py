from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.portfolio import (
    AllocationEnvelopeStatus,
    CrewAllocationEnvelope,
    CrewExposureSnapshot,
    MasterCapitalSnapshot,
    MasterReservationLedger,
    MasterRiskGateDecisionStatus,
    PortfolioMemberRef,
    ReservationAdmissionBridgeError,
    ReservationAdmissionReasonCode,
    ReservationAdmissionTransitionStatus,
    ReservationRecordStatus,
    ReservationRequest,
    SnapshotDataStatus,
    apply_master_risk_gate_decision_to_reservation,
    build_master_allocation_policy,
    build_master_portfolio_snapshot,
    build_master_risk_gate_candidate,
    build_master_risk_gate_policy,
    evaluate_master_risk_gate,
)
from app.trading.risk.models import RiskDecision, RiskDecisionStatus, RiskReasonCode

OPENED_AT = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)
RISK_AT = datetime(2026, 9, 9, 22, 10, tzinfo=UTC)
REQUESTED_AT = datetime(2026, 9, 9, 22, 20, tzinfo=UTC)
EVALUATED_AT = datetime(2026, 9, 9, 22, 30, tzinfo=UTC)
OBSERVED_AT = datetime(2026, 9, 9, 22, 25, tzinfo=UTC)


def member(system_id: str) -> PortfolioMemberRef:
    return PortfolioMemberRef(system_id=system_id, membership_ref=f"registry:{system_id}")


def members() -> tuple[PortfolioMemberRef, ...]:
    return (member("crew-a"), member("crew-b"))


def envelope(system_id: str) -> CrewAllocationEnvelope:
    return CrewAllocationEnvelope(
        system_id=system_id,
        status=AllocationEnvelopeStatus.CONFIGURED,
        capital_ceiling_amount=Decimal("80"),
        open_risk_ceiling_amount=Decimal("20"),
        gross_exposure_ceiling_amount=Decimal("400"),
    )


def allocation_policy():
    return build_master_allocation_policy(
        master_portfolio_id="master-main",
        policy_id="static-v1",
        members=members(),
        envelopes=(envelope("crew-a"), envelope("crew-b")),
        source_ref="operator-config:static-v1",
    )


def capital(observed_at: datetime):
    return MasterCapitalSnapshot(
        master_portfolio_id="master-main",
        observed_at=observed_at,
        status=SnapshotDataStatus.AVAILABLE,
        source="MASTER_ACCOUNT_FIXTURE",
        equity=Decimal("100"),
        cash_balance=Decimal("100"),
        day_start_equity=Decimal("100"),
        equity_peak=Decimal("100"),
        source_ref="fixture:capital",
    )


def exposure(system_id: str, observed_at: datetime):
    return CrewExposureSnapshot(
        system_id=system_id,
        observed_at=observed_at,
        status=SnapshotDataStatus.AVAILABLE,
        source="SYSTEM_EXPOSURE_FIXTURE",
        open_positions=0,
        gross_exposure_amount=Decimal("0"),
        open_risk_amount=Decimal("0"),
        source_ref=f"fixture:{system_id}",
    )


def snapshot(observed_at: datetime):
    return build_master_portfolio_snapshot(
        master_capital=capital(observed_at),
        members=members(),
        crew_exposures=(
            exposure("crew-a", observed_at),
            exposure("crew-b", observed_at),
        ),
    )


def opening_snapshot():
    return snapshot(OPENED_AT)


def current_snapshot():
    return snapshot(OBSERVED_AT)


def local_decision(
    *,
    proposal_id: str = "proposal-1",
    status: RiskDecisionStatus = RiskDecisionStatus.APPROVED,
    risk: str = "3",
    notional: str = "50",
):
    if status is RiskDecisionStatus.REJECTED:
        return RiskDecision(
            proposal_id=proposal_id,
            status=status,
            reason_codes=(RiskReasonCode.MAX_PORTFOLIO_RISK,),
            created_at=RISK_AT,
        )
    return RiskDecision(
        proposal_id=proposal_id,
        status=status,
        reason_codes=(RiskReasonCode.APPROVED,),
        approved_quantity=Decimal("2"),
        approved_risk_amount=Decimal(risk),
        approved_notional=Decimal(notional),
        created_at=RISK_AT,
    )


def reserve(
    ledger: MasterReservationLedger,
    *,
    request_id: str = "candidate-request",
    proposal_id: str = "proposal-1",
    system_id: str = "crew-a",
    risk: str = "3",
    gross: str = "50",
    capital_amount: str = "20",
    requested_at: datetime = REQUESTED_AT,
):
    result = ledger.reserve(
        ReservationRequest(
            request_id=request_id,
            system_id=system_id,
            requested_at=requested_at,
            capital_amount=Decimal(capital_amount),
            open_risk_amount=Decimal(risk),
            gross_exposure_amount=Decimal(gross),
            request_ref=proposal_id,
        )
    )
    assert result.reservation is not None
    return result.reservation


def gate_policy(policy, *, max_risk: str = "10", max_gross: str = "200"):
    return build_master_risk_gate_policy(
        master_portfolio_id="master-main",
        gate_policy_id="global-v1",
        allocation_policy_fingerprint_sha256=policy.fingerprint_sha256,
        max_total_open_risk_amount=Decimal(max_risk),
        max_total_gross_exposure_amount=Decimal(max_gross),
        source_ref="operator-config:global-v1",
    )


def context(*, reject: bool = False):
    policy = allocation_policy()
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening_snapshot())
    reservation = reserve(ledger)
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(),
        reservation_id=reservation.reservation_id,
    )
    gate = gate_policy(
        policy,
        max_risk="2" if reject else "10",
        max_gross="40" if reject else "200",
    )
    decision = evaluate_master_risk_gate(
        gate_policy=gate,
        allocation_policy=policy,
        candidate=candidate,
        portfolio_snapshot=current_snapshot(),
        ledger_snapshot=ledger.snapshot(),
        evaluated_at=EVALUATED_AT,
    )
    return policy, ledger, reservation, candidate, decision


def assert_bridge_error(
    exc_info: pytest.ExceptionInfo[ReservationAdmissionBridgeError],
    reason: ReservationAdmissionReasonCode,
) -> None:
    assert exc_info.value.reason_code is reason


def test_admit_commits_reserved_capacity() -> None:
    _, ledger, reservation, candidate, decision = context()

    receipt = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )

    updated = ledger.get(reservation.reservation_id)
    assert decision.status is MasterRiskGateDecisionStatus.ADMIT
    assert updated.status is ReservationRecordStatus.COMMITTED
    assert updated.committed_at == decision.created_at
    assert updated.commit_ref == decision.decision_id
    assert receipt.transition_status is ReservationAdmissionTransitionStatus.COMMITTED
    assert receipt.reason_code is ReservationAdmissionReasonCode.ADMITTED_COMMITTED


def test_reject_releases_reserved_capacity() -> None:
    _, ledger, reservation, candidate, decision = context(reject=True)

    receipt = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )

    updated = ledger.get(reservation.reservation_id)
    assert decision.status is MasterRiskGateDecisionStatus.REJECT
    assert updated.status is ReservationRecordStatus.RELEASED
    assert updated.committed_at is None
    assert updated.release_ref == decision.decision_id
    assert receipt.transition_status is ReservationAdmissionTransitionStatus.RELEASED
    assert receipt.reason_code is ReservationAdmissionReasonCode.REJECTED_RELEASED


def test_admit_retry_is_idempotent_and_returns_same_receipt() -> None:
    _, ledger, _, candidate, decision = context()

    first = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )
    second = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )

    assert first == second
    assert first.fingerprint_sha256 == second.fingerprint_sha256


def test_reject_retry_is_idempotent_and_returns_same_receipt() -> None:
    _, ledger, _, candidate, decision = context(reject=True)

    first = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )
    second = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )

    assert first == second


def test_exact_retry_remains_valid_after_unrelated_later_ledger_change() -> None:
    _, ledger, _, candidate, decision = context()
    first = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )
    reserve(
        ledger,
        request_id="other-request",
        proposal_id="proposal-2",
        system_id="crew-b",
        risk="1",
        gross="10",
        capital_amount="10",
        requested_at=datetime(2026, 9, 9, 22, 40, tzinfo=UTC),
    )

    retry = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )

    assert retry == first


def test_stale_ledger_blocks_first_admit_without_mutating_candidate_reservation() -> None:
    _, ledger, reservation, candidate, decision = context()
    reserve(
        ledger,
        request_id="concurrent-request",
        proposal_id="proposal-2",
        system_id="crew-b",
        risk="1",
        gross="10",
        capital_amount="10",
    )

    with pytest.raises(ReservationAdmissionBridgeError) as exc_info:
        apply_master_risk_gate_decision_to_reservation(
            ledger=ledger,
            candidate=candidate,
            decision=decision,
        )

    assert_bridge_error(exc_info, ReservationAdmissionReasonCode.STALE_LEDGER_SNAPSHOT)
    assert ledger.get(reservation.reservation_id).status is ReservationRecordStatus.RESERVED


def test_reject_can_release_after_unrelated_ledger_change() -> None:
    _, ledger, reservation, candidate, decision = context(reject=True)
    other = reserve(
        ledger,
        request_id="concurrent-request",
        proposal_id="proposal-2",
        system_id="crew-b",
        risk="1",
        gross="10",
        capital_amount="10",
    )

    receipt = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )

    assert receipt.transition_status is ReservationAdmissionTransitionStatus.RELEASED
    assert ledger.get(reservation.reservation_id).status is ReservationRecordStatus.RELEASED
    assert ledger.get(other.reservation_id).status is ReservationRecordStatus.RESERVED


def test_candidate_decision_mismatch_is_rejected_without_mutation() -> None:
    policy, ledger, reservation, candidate, decision = context()
    other_reservation = reserve(
        ledger,
        request_id="other-request",
        proposal_id="proposal-2",
        system_id="crew-b",
        risk="1",
        gross="10",
        capital_amount="10",
    )
    other_candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-b",
        local_risk_decision=local_decision(
            proposal_id="proposal-2",
            risk="1",
            notional="10",
        ),
        reservation_id=other_reservation.reservation_id,
    )

    with pytest.raises(ReservationAdmissionBridgeError) as exc_info:
        apply_master_risk_gate_decision_to_reservation(
            ledger=ledger,
            candidate=other_candidate,
            decision=decision,
        )

    assert policy.master_portfolio_id == "master-main"
    assert candidate.fingerprint_sha256 != other_candidate.fingerprint_sha256
    assert_bridge_error(exc_info, ReservationAdmissionReasonCode.CANDIDATE_DECISION_MISMATCH)
    assert ledger.get(reservation.reservation_id).status is ReservationRecordStatus.RESERVED
    assert ledger.get(other_reservation.reservation_id).status is ReservationRecordStatus.RESERVED


def test_master_portfolio_mismatch_is_rejected_without_mutation() -> None:
    policy, ledger, reservation, _, _ = context()
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-other",
        system_id="crew-a",
        local_risk_decision=local_decision(),
        reservation_id=reservation.reservation_id,
    )
    decision = evaluate_master_risk_gate(
        gate_policy=gate_policy(policy),
        allocation_policy=policy,
        candidate=candidate,
        portfolio_snapshot=current_snapshot(),
        ledger_snapshot=ledger.snapshot(),
        evaluated_at=EVALUATED_AT,
    )

    with pytest.raises(ReservationAdmissionBridgeError) as exc_info:
        apply_master_risk_gate_decision_to_reservation(
            ledger=ledger,
            candidate=candidate,
            decision=decision,
        )

    assert_bridge_error(exc_info, ReservationAdmissionReasonCode.MASTER_PORTFOLIO_ID_MISMATCH)
    assert ledger.get(reservation.reservation_id).status is ReservationRecordStatus.RESERVED


def test_reservation_bound_candidate_is_required() -> None:
    policy = allocation_policy()
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening_snapshot())
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(status=RiskDecisionStatus.REJECTED),
        reservation_id=None,
    )
    decision = evaluate_master_risk_gate(
        gate_policy=gate_policy(policy),
        allocation_policy=policy,
        candidate=candidate,
        portfolio_snapshot=current_snapshot(),
        ledger_snapshot=ledger.snapshot(),
        evaluated_at=EVALUATED_AT,
    )

    with pytest.raises(ReservationAdmissionBridgeError) as exc_info:
        apply_master_risk_gate_decision_to_reservation(
            ledger=ledger,
            candidate=candidate,
            decision=decision,
        )

    assert_bridge_error(exc_info, ReservationAdmissionReasonCode.RESERVATION_REQUIRED)
    assert ledger.records() == ()


def test_unknown_reservation_id_is_rejected() -> None:
    policy = allocation_policy()
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening_snapshot())
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(),
        reservation_id="reservation:missing",
    )
    decision = evaluate_master_risk_gate(
        gate_policy=gate_policy(policy),
        allocation_policy=policy,
        candidate=candidate,
        portfolio_snapshot=current_snapshot(),
        ledger_snapshot=ledger.snapshot(),
        evaluated_at=EVALUATED_AT,
    )

    with pytest.raises(ReservationAdmissionBridgeError) as exc_info:
        apply_master_risk_gate_decision_to_reservation(
            ledger=ledger,
            candidate=candidate,
            decision=decision,
        )

    assert_bridge_error(exc_info, ReservationAdmissionReasonCode.RESERVATION_NOT_FOUND)


def test_payload_mismatch_does_not_release_unrelated_reserved_capacity() -> None:
    policy = allocation_policy()
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening_snapshot())
    reservation = reserve(ledger, proposal_id="another-proposal")
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(),
        reservation_id=reservation.reservation_id,
    )
    decision = evaluate_master_risk_gate(
        gate_policy=gate_policy(policy),
        allocation_policy=policy,
        candidate=candidate,
        portfolio_snapshot=current_snapshot(),
        ledger_snapshot=ledger.snapshot(),
        evaluated_at=EVALUATED_AT,
    )
    assert decision.status is MasterRiskGateDecisionStatus.REJECT

    with pytest.raises(ReservationAdmissionBridgeError) as exc_info:
        apply_master_risk_gate_decision_to_reservation(
            ledger=ledger,
            candidate=candidate,
            decision=decision,
        )

    assert_bridge_error(exc_info, ReservationAdmissionReasonCode.RESERVATION_PAYLOAD_MISMATCH)
    assert ledger.get(reservation.reservation_id).status is ReservationRecordStatus.RESERVED


def test_decision_cannot_precede_reservation_request() -> None:
    policy = allocation_policy()
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening_snapshot())
    reservation = reserve(ledger)
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(),
        reservation_id=reservation.reservation_id,
    )
    decision = evaluate_master_risk_gate(
        gate_policy=gate_policy(policy),
        allocation_policy=policy,
        candidate=candidate,
        portfolio_snapshot=current_snapshot(),
        ledger_snapshot=ledger.snapshot(),
        evaluated_at=datetime(2026, 9, 9, 22, 15, tzinfo=UTC),
    )

    with pytest.raises(ReservationAdmissionBridgeError) as exc_info:
        apply_master_risk_gate_decision_to_reservation(
            ledger=ledger,
            candidate=candidate,
            decision=decision,
        )

    assert_bridge_error(exc_info, ReservationAdmissionReasonCode.DECISION_PRECEDES_RESERVATION)
    assert ledger.get(reservation.reservation_id).status is ReservationRecordStatus.RESERVED


def test_precommitted_reservation_cannot_be_claimed_by_admit_decision() -> None:
    _, ledger, reservation, candidate, decision = context()
    ledger.commit(
        reservation.reservation_id,
        committed_at=EVALUATED_AT,
        commit_ref="another-admission",
    )

    with pytest.raises(ReservationAdmissionBridgeError) as exc_info:
        apply_master_risk_gate_decision_to_reservation(
            ledger=ledger,
            candidate=candidate,
            decision=decision,
        )

    assert_bridge_error(exc_info, ReservationAdmissionReasonCode.RESERVATION_STATE_CONFLICT)
    assert ledger.get(reservation.reservation_id).commit_ref == "another-admission"


def test_committed_reservation_is_not_released_by_reject_bridge() -> None:
    _, ledger, reservation, candidate, decision = context(reject=True)
    ledger.commit(
        reservation.reservation_id,
        committed_at=EVALUATED_AT,
        commit_ref="execution-started",
    )

    with pytest.raises(ReservationAdmissionBridgeError) as exc_info:
        apply_master_risk_gate_decision_to_reservation(
            ledger=ledger,
            candidate=candidate,
            decision=decision,
        )

    assert_bridge_error(exc_info, ReservationAdmissionReasonCode.RESERVATION_STATE_CONFLICT)
    assert ledger.get(reservation.reservation_id).status is ReservationRecordStatus.COMMITTED


def test_released_reservation_cannot_be_committed_by_late_admit() -> None:
    _, ledger, reservation, candidate, decision = context()
    ledger.release(
        reservation.reservation_id,
        released_at=EVALUATED_AT,
        release_ref="cancelled-elsewhere",
    )

    with pytest.raises(ReservationAdmissionBridgeError) as exc_info:
        apply_master_risk_gate_decision_to_reservation(
            ledger=ledger,
            candidate=candidate,
            decision=decision,
        )

    assert_bridge_error(exc_info, ReservationAdmissionReasonCode.RESERVATION_STATE_CONFLICT)
    assert ledger.get(reservation.reservation_id).status is ReservationRecordStatus.RELEASED


def test_reject_release_restores_reserved_master_capital_capacity() -> None:
    _, ledger, _, candidate, decision = context(reject=True)
    before = ledger.snapshot()
    assert before.reserved_capital_amount == Decimal("20")
    assert before.available_capital_amount == Decimal("80")

    apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )

    after = ledger.snapshot()
    assert after.reserved_capital_amount == Decimal("0")
    assert after.committed_capital_amount == Decimal("0")
    assert after.available_capital_amount == Decimal("100")


def test_admit_moves_capacity_from_reserved_to_committed_without_changing_active_total() -> None:
    _, ledger, _, candidate, decision = context()
    before = ledger.snapshot()

    apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )

    after = ledger.snapshot()
    assert before.active_capital_amount == after.active_capital_amount == Decimal("20")
    assert after.reserved_capital_amount == Decimal("0")
    assert after.committed_capital_amount == Decimal("20")


def test_receipt_is_immutable_and_auditable() -> None:
    _, ledger, reservation, candidate, decision = context()
    receipt = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )

    assert receipt.reservation_id == reservation.reservation_id
    assert receipt.gate_decision_id == decision.decision_id
    assert receipt.gate_decision_fingerprint_sha256 == decision.fingerprint_sha256
    assert (
        receipt.evaluated_ledger_fingerprint_sha256
        == decision.reservation_ledger_fingerprint_sha256
    )
    assert receipt.transitioned_at == decision.created_at
    assert receipt.transition_ref == decision.decision_id
    with pytest.raises(FrozenInstanceError):
        receipt.transition_ref = "mutated"  # type: ignore[misc]


def test_receipt_exposes_no_risk_broker_registry_or_live_authority() -> None:
    _, ledger, _, candidate, decision = context()
    receipt = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )

    assert receipt.reservation_transition is True
    assert receipt.risk_authority is False
    assert receipt.admission_authority is False
    assert receipt.local_risk_override is False
    assert receipt.resize_authority is False
    assert receipt.broker_authority is False
    assert receipt.registry_mutation is False
    assert receipt.live_authority is False
    assert receipt.auto_execute is False


def test_receipt_fingerprint_rejects_tampering() -> None:
    _, ledger, _, candidate, decision = context()
    receipt = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )

    with pytest.raises(ValueError, match="fingerprint"):
        replace(receipt, transition_ref="another-ref")


def test_transition_metadata_is_derived_from_gate_decision_not_external_clock() -> None:
    _, ledger, reservation, candidate, decision = context()

    receipt = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )

    stored = ledger.get(reservation.reservation_id)
    assert stored.committed_at == decision.created_at
    assert stored.commit_ref == decision.decision_id
    assert receipt.transitioned_at == decision.created_at
    assert receipt.transition_ref == decision.decision_id
