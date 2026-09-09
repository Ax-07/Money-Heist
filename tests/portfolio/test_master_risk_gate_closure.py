from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.portfolio import (
    AllocationEnvelopeStatus,
    CrewAllocationEnvelope,
    CrewExposureSnapshot,
    MasterCapitalSnapshot,
    MasterReservationLedger,
    MasterRiskGateClosureStatus,
    MasterRiskGateDecisionStatus,
    MasterRiskGateReasonCode,
    PortfolioMemberRef,
    ReservationAdmissionTransitionStatus,
    ReservationRecordStatus,
    ReservationRequest,
    SnapshotDataStatus,
    apply_master_risk_gate_decision_to_reservation,
    build_master_allocation_policy,
    build_master_portfolio_snapshot,
    build_master_risk_gate_candidate,
    build_master_risk_gate_closure_seal,
    build_master_risk_gate_policy,
    evaluate_master_risk_gate,
)
from app.trading.risk.models import RiskDecision, RiskDecisionStatus, RiskReasonCode

OPENED_AT = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)
RISK_AT = datetime(2026, 9, 9, 22, 10, tzinfo=UTC)
REQUESTED_AT = datetime(2026, 9, 9, 22, 20, tzinfo=UTC)
OBSERVED_AT = datetime(2026, 9, 9, 22, 25, tzinfo=UTC)
EVALUATED_AT = datetime(2026, 9, 9, 22, 30, tzinfo=UTC)


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


def allocation_policy(*, policy_id: str = "static-v1"):
    return build_master_allocation_policy(
        master_portfolio_id="master-main",
        policy_id=policy_id,
        members=members(),
        envelopes=(envelope("crew-a"), envelope("crew-b")),
        source_ref=f"operator-config:{policy_id}",
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


def local_decision(
    *,
    proposal_id: str = "proposal-1",
    status: RiskDecisionStatus = RiskDecisionStatus.APPROVED,
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
        approved_risk_amount=Decimal("3"),
        approved_notional=Decimal("50"),
        created_at=RISK_AT,
    )


def reserve(
    ledger: MasterReservationLedger,
    *,
    request_id: str = "candidate-request",
    proposal_id: str = "proposal-1",
    system_id: str = "crew-a",
    capital_amount: str = "20",
    risk: str = "3",
    gross: str = "50",
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


def gate_policy(policy, *, reject: bool = False):
    return build_master_risk_gate_policy(
        master_portfolio_id="master-main",
        gate_policy_id="global-v1",
        allocation_policy_fingerprint_sha256=policy.fingerprint_sha256,
        max_total_open_risk_amount=Decimal("2" if reject else "10"),
        max_total_gross_exposure_amount=Decimal("40" if reject else "200"),
        source_ref="operator-config:global-v1",
    )


def transitioned_context(*, reject: bool = False, with_second: bool = False):
    policy = allocation_policy()
    opening = snapshot(OPENED_AT)
    current = snapshot(OBSERVED_AT)
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening)
    reservation = reserve(ledger)
    second = None
    if with_second:
        second = reserve(
            ledger,
            request_id="second-request",
            proposal_id="proposal-2",
            system_id="crew-b",
            capital_amount="10",
            risk="1",
            gross="20",
        )
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(),
        reservation_id=reservation.reservation_id,
    )
    gate = gate_policy(policy, reject=reject)
    before = ledger.snapshot()
    decision = evaluate_master_risk_gate(
        gate_policy=gate,
        allocation_policy=policy,
        candidate=candidate,
        portfolio_snapshot=current,
        ledger_snapshot=before,
        evaluated_at=EVALUATED_AT,
    )
    receipt = apply_master_risk_gate_decision_to_reservation(
        ledger=ledger,
        candidate=candidate,
        decision=decision,
    )
    after = ledger.snapshot()
    return (
        policy,
        opening,
        current,
        ledger,
        reservation,
        second,
        candidate,
        gate,
        before,
        decision,
        receipt,
        after,
    )


def build_transitioned_seal(*, reject: bool = False):
    context = transitioned_context(reject=reject)
    policy, opening, current, _, _, _, candidate, gate, before, decision, receipt, after = context
    seal = build_master_risk_gate_closure_seal(
        gate_policy=gate,
        allocation_policy=policy,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger_before=before,
        ledger_after=after,
        candidate=candidate,
        decision=decision,
        receipt=receipt,
    )
    return context, seal


def local_reject_context():
    policy = allocation_policy()
    opening = snapshot(OPENED_AT)
    current = snapshot(OBSERVED_AT)
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening)
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(status=RiskDecisionStatus.REJECTED),
        reservation_id=None,
    )
    gate = gate_policy(policy)
    before = ledger.snapshot()
    decision = evaluate_master_risk_gate(
        gate_policy=gate,
        allocation_policy=policy,
        candidate=candidate,
        portfolio_snapshot=current,
        ledger_snapshot=before,
        evaluated_at=EVALUATED_AT,
    )
    return policy, opening, current, ledger, candidate, gate, before, decision


def test_admit_closure_seals_full_provenance() -> None:
    context, seal = build_transitioned_seal()
    (
        policy,
        _,
        current,
        _,
        reservation,
        _,
        candidate,
        gate,
        before,
        decision,
        receipt,
        after,
    ) = context

    assert seal.status is MasterRiskGateClosureStatus.SEALED
    assert seal.decision_status is MasterRiskGateDecisionStatus.ADMIT
    assert seal.master_portfolio_id == "master-main"
    assert seal.system_id == "crew-a"
    assert seal.proposal_id == "proposal-1"
    assert seal.reservation_id == reservation.reservation_id
    assert seal.gate_policy_id == "global-v1"
    assert seal.gate_policy_source_ref == "operator-config:global-v1"
    assert seal.gate_policy_fingerprint_sha256 == gate.fingerprint_sha256
    assert seal.allocation_policy_fingerprint_sha256 == policy.fingerprint_sha256
    assert seal.candidate_fingerprint_sha256 == candidate.fingerprint_sha256
    assert seal.decision_fingerprint_sha256 == decision.fingerprint_sha256
    assert seal.portfolio_snapshot_fingerprint_sha256 == current.fingerprint_sha256
    assert seal.ledger_before_fingerprint_sha256 == before.fingerprint_sha256
    assert seal.ledger_after_fingerprint_sha256 == after.fingerprint_sha256
    assert seal.admission_receipt_fingerprint_sha256 == receipt.fingerprint_sha256


def test_admit_closure_seals_commit_transition() -> None:
    context, seal = build_transitioned_seal()
    before = context[8]
    decision = context[9]
    receipt = context[10]
    after = context[11]
    before_record = before.reservations[0]
    after_record = after.reservations[0]

    assert decision.status is MasterRiskGateDecisionStatus.ADMIT
    assert after_record.status is ReservationRecordStatus.COMMITTED
    assert seal.reservation_before_fingerprint_sha256 == before_record.fingerprint_sha256
    assert seal.reservation_after_fingerprint_sha256 == after_record.fingerprint_sha256
    assert seal.reservation_transition_status is ReservationAdmissionTransitionStatus.COMMITTED
    assert seal.reservation_transition_reason_code is receipt.reason_code


def test_reject_closure_seals_release_transition() -> None:
    context, seal = build_transitioned_seal(reject=True)
    before = context[8]
    decision = context[9]
    receipt = context[10]
    after = context[11]

    assert decision.status is MasterRiskGateDecisionStatus.REJECT
    assert after.reservations[0].status is ReservationRecordStatus.RELEASED
    assert seal.reservation_before_fingerprint_sha256 == before.reservations[0].fingerprint_sha256
    assert seal.reservation_after_fingerprint_sha256 == after.reservations[0].fingerprint_sha256
    assert seal.reservation_transition_status is ReservationAdmissionTransitionStatus.RELEASED
    assert seal.reservation_transition_reason_code is receipt.reason_code


def test_local_risk_rejection_seals_without_fake_transition() -> None:
    policy, opening, current, _, candidate, gate, before, decision = local_reject_context()

    seal = build_master_risk_gate_closure_seal(
        gate_policy=gate,
        allocation_policy=policy,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger_before=before,
        ledger_after=before,
        candidate=candidate,
        decision=decision,
        receipt=None,
    )

    assert decision.status is MasterRiskGateDecisionStatus.REJECT
    assert MasterRiskGateReasonCode.LOCAL_RISK_NOT_AUTHORIZED in decision.reason_codes
    assert seal.reservation_id is None
    assert seal.reservation_before_fingerprint_sha256 is None
    assert seal.reservation_after_fingerprint_sha256 is None
    assert seal.reservation_transition_status is None
    assert seal.reservation_transition_reason_code is None
    assert seal.admission_receipt_fingerprint_sha256 is None
    assert seal.ledger_before_fingerprint_sha256 == seal.ledger_after_fingerprint_sha256


def test_closure_is_deterministic() -> None:
    context = transitioned_context()
    policy, opening, current, _, _, _, candidate, gate, before, decision, receipt, after = context
    kwargs = dict(
        gate_policy=gate,
        allocation_policy=policy,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger_before=before,
        ledger_after=after,
        candidate=candidate,
        decision=decision,
        receipt=receipt,
    )

    first = build_master_risk_gate_closure_seal(**kwargs)
    second = build_master_risk_gate_closure_seal(**kwargs)

    assert first == second
    assert first.closure_fingerprint_sha256 == second.closure_fingerprint_sha256
    assert first.canonical_payload() == second.canonical_payload()


def test_closure_is_immutable() -> None:
    _, seal = build_transitioned_seal()

    with pytest.raises((FrozenInstanceError, AttributeError)):
        seal.decision_id = "other"  # type: ignore[misc]


def test_closure_has_no_execution_or_risk_authority() -> None:
    _, seal = build_transitioned_seal()

    assert seal.mutation_applied is False
    assert seal.reservation_mutation is False
    assert seal.risk_authority is False
    assert seal.admission_authority is False
    assert seal.local_risk_override is False
    assert seal.resize_authority is False
    assert seal.broker_authority is False
    assert seal.registry_mutation is False
    assert seal.live_authority is False
    assert seal.auto_execute is False


def test_gate_policy_mismatch_fails_closed() -> None:
    context = transitioned_context()
    policy, opening, current, _, _, _, candidate, _, before, decision, receipt, after = context
    other_gate = build_master_risk_gate_policy(
        master_portfolio_id="master-main",
        gate_policy_id="global-v2",
        allocation_policy_fingerprint_sha256=policy.fingerprint_sha256,
        max_total_open_risk_amount=Decimal("9"),
        max_total_gross_exposure_amount=Decimal("190"),
        source_ref="operator-config:global-v2",
    )

    with pytest.raises(ValueError, match="gate decision does not bind"):
        build_master_risk_gate_closure_seal(
            gate_policy=other_gate,
            allocation_policy=policy,
            opening_snapshot=opening,
            portfolio_snapshot=current,
            ledger_before=before,
            ledger_after=after,
            candidate=candidate,
            decision=decision,
            receipt=receipt,
        )


def test_allocation_policy_mismatch_fails_closed() -> None:
    context = transitioned_context()
    _, opening, current, _, _, _, candidate, gate, before, decision, receipt, after = context

    with pytest.raises(ValueError, match="gate policy does not bind"):
        build_master_risk_gate_closure_seal(
            gate_policy=gate,
            allocation_policy=allocation_policy(policy_id="static-v2"),
            opening_snapshot=opening,
            portfolio_snapshot=current,
            ledger_before=before,
            ledger_after=after,
            candidate=candidate,
            decision=decision,
            receipt=receipt,
        )


def test_opening_snapshot_mismatch_fails_closed() -> None:
    context = transitioned_context()
    policy, _, current, _, _, _, candidate, gate, before, decision, receipt, after = context

    with pytest.raises(ValueError, match="opening snapshot"):
        build_master_risk_gate_closure_seal(
            gate_policy=gate,
            allocation_policy=policy,
            opening_snapshot=snapshot(OPENED_AT + timedelta(minutes=1)),
            portfolio_snapshot=current,
            ledger_before=before,
            ledger_after=after,
            candidate=candidate,
            decision=decision,
            receipt=receipt,
        )


def test_portfolio_snapshot_mismatch_fails_closed() -> None:
    context = transitioned_context()
    policy, opening, _, _, _, _, candidate, gate, before, decision, receipt, after = context

    with pytest.raises(ValueError, match="portfolio snapshot"):
        build_master_risk_gate_closure_seal(
            gate_policy=gate,
            allocation_policy=policy,
            opening_snapshot=opening,
            portfolio_snapshot=snapshot(OBSERVED_AT + timedelta(minutes=1)),
            ledger_before=before,
            ledger_after=after,
            candidate=candidate,
            decision=decision,
            receipt=receipt,
        )


def test_wrong_pre_transition_ledger_fails_closed() -> None:
    context = transitioned_context()
    policy, opening, current, _, _, _, candidate, gate, _, decision, receipt, after = context

    with pytest.raises(ValueError, match="pre-transition ledger"):
        build_master_risk_gate_closure_seal(
            gate_policy=gate,
            allocation_policy=policy,
            opening_snapshot=opening,
            portfolio_snapshot=current,
            ledger_before=after,
            ledger_after=after,
            candidate=candidate,
            decision=decision,
            receipt=receipt,
        )


def test_admit_requires_committed_post_transition_state() -> None:
    context = transitioned_context()
    policy, opening, current, _, _, _, candidate, gate, before, decision, receipt, _ = context

    with pytest.raises(ValueError, match="post-transition reservation status"):
        build_master_risk_gate_closure_seal(
            gate_policy=gate,
            allocation_policy=policy,
            opening_snapshot=opening,
            portfolio_snapshot=current,
            ledger_before=before,
            ledger_after=before,
            candidate=candidate,
            decision=decision,
            receipt=receipt,
        )


def test_reservation_bound_closure_requires_receipt() -> None:
    context = transitioned_context()
    policy, opening, current, _, _, _, candidate, gate, before, decision, _, after = context

    with pytest.raises(ValueError, match="requires admission receipt"):
        build_master_risk_gate_closure_seal(
            gate_policy=gate,
            allocation_policy=policy,
            opening_snapshot=opening,
            portfolio_snapshot=current,
            ledger_before=before,
            ledger_after=after,
            candidate=candidate,
            decision=decision,
            receipt=None,
        )


def test_local_reject_forbids_fake_receipt() -> None:
    policy, opening, current, _, candidate, gate, before, decision = local_reject_context()
    other = transitioned_context()
    other_receipt = other[10]

    with pytest.raises(ValueError, match="cannot carry admission receipt"):
        build_master_risk_gate_closure_seal(
            gate_policy=gate,
            allocation_policy=policy,
            opening_snapshot=opening,
            portfolio_snapshot=current,
            ledger_before=before,
            ledger_after=before,
            candidate=candidate,
            decision=decision,
            receipt=other_receipt,
        )


def test_local_reject_requires_unchanged_ledger() -> None:
    policy, opening, current, ledger, candidate, gate, before, decision = local_reject_context()
    reserve(ledger, request_id="late", proposal_id="proposal-late")
    changed = ledger.snapshot()

    with pytest.raises(ValueError, match="must leave ledger unchanged"):
        build_master_risk_gate_closure_seal(
            gate_policy=gate,
            allocation_policy=policy,
            opening_snapshot=opening,
            portfolio_snapshot=current,
            ledger_before=before,
            ledger_after=changed,
            candidate=candidate,
            decision=decision,
            receipt=None,
        )


def test_non_target_reservation_mutation_is_rejected() -> None:
    context = transitioned_context(with_second=True)
    (
        policy,
        opening,
        current,
        ledger,
        _,
        second,
        candidate,
        gate,
        before,
        decision,
        receipt,
        _,
    ) = context
    assert second is not None
    ledger.release(
        second.reservation_id,
        released_at=EVALUATED_AT + timedelta(minutes=1),
        release_ref="unrelated-release",
    )
    changed_after = ledger.snapshot()

    with pytest.raises(ValueError, match="non-target reservation changed"):
        build_master_risk_gate_closure_seal(
            gate_policy=gate,
            allocation_policy=policy,
            opening_snapshot=opening,
            portfolio_snapshot=current,
            ledger_before=before,
            ledger_after=changed_after,
            candidate=candidate,
            decision=decision,
            receipt=receipt,
        )


def test_new_reservation_after_transition_is_rejected() -> None:
    context = transitioned_context()
    policy, opening, current, ledger, _, _, candidate, gate, before, decision, receipt, _ = context
    reserve(
        ledger,
        request_id="late-request",
        proposal_id="proposal-late",
        system_id="crew-b",
        capital_amount="5",
        risk="1",
        gross="10",
        requested_at=EVALUATED_AT + timedelta(minutes=1),
    )
    changed_after = ledger.snapshot()

    with pytest.raises(ValueError, match="reservation set changed"):
        build_master_risk_gate_closure_seal(
            gate_policy=gate,
            allocation_policy=policy,
            opening_snapshot=opening,
            portfolio_snapshot=current,
            ledger_before=before,
            ledger_after=changed_after,
            candidate=candidate,
            decision=decision,
            receipt=receipt,
        )


def test_receipt_from_other_decision_is_rejected() -> None:
    context = transitioned_context()
    policy, opening, current, _, _, _, candidate, gate, before, decision, _, after = context
    other = transitioned_context(reject=True)
    other_receipt = other[10]

    with pytest.raises(ValueError, match="admission receipt does not bind"):
        build_master_risk_gate_closure_seal(
            gate_policy=gate,
            allocation_policy=policy,
            opening_snapshot=opening,
            portfolio_snapshot=current,
            ledger_before=before,
            ledger_after=after,
            candidate=candidate,
            decision=decision,
            receipt=other_receipt,
        )


def test_closure_seals_existing_reservation_closures() -> None:
    _, seal = build_transitioned_seal()

    assert len(seal.reservation_closure_before_fingerprint_sha256) == 64
    assert len(seal.reservation_closure_after_fingerprint_sha256) == 64
    assert (
        seal.reservation_closure_before_fingerprint_sha256
        != seal.reservation_closure_after_fingerprint_sha256
    )


def test_decision_reason_codes_are_preserved() -> None:
    context, seal = build_transitioned_seal(reject=True)
    decision = context[9]

    assert seal.decision_reason_codes == decision.reason_codes
    assert MasterRiskGateReasonCode.MASTER_OPEN_RISK_LIMIT_EXCEEDED in seal.decision_reason_codes
    assert (
        MasterRiskGateReasonCode.MASTER_GROSS_EXPOSURE_LIMIT_EXCEEDED
        in seal.decision_reason_codes
    )


def test_sealed_at_is_gate_decision_time() -> None:
    context, seal = build_transitioned_seal()

    assert seal.sealed_at == context[9].created_at == EVALUATED_AT


def test_tampered_closure_payload_is_rejected() -> None:
    _, seal = build_transitioned_seal()

    with pytest.raises(ValueError, match="fingerprint does not match"):
        replace(seal, decision_id="master-risk-gate:tampered")


def test_no_transition_closure_rejects_admit_shape() -> None:
    _, seal = build_transitioned_seal()

    with pytest.raises(ValueError, match="requires complete transition evidence"):
        replace(
            seal,
            reservation_before_fingerprint_sha256=None,
            reservation_after_fingerprint_sha256=None,
            reservation_transition_status=None,
            reservation_transition_reason_code=None,
            admission_receipt_fingerprint_sha256=None,
        )
