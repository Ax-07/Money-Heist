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
    MasterRiskGatePolicyStatus,
    MasterRiskGateReasonCode,
    PortfolioMemberRef,
    ReservationRecordStatus,
    ReservationRequest,
    SnapshotDataStatus,
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
COMMITTED_AT = datetime(2026, 9, 9, 22, 30, tzinfo=UTC)
OBSERVED_AT = datetime(2026, 9, 9, 23, 0, tzinfo=UTC)
EVALUATED_AT = datetime(2026, 9, 9, 23, 1, tzinfo=UTC)


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


def capital(observed_at: datetime, *, master_portfolio_id: str = "master-main"):
    return MasterCapitalSnapshot(
        master_portfolio_id=master_portfolio_id,
        observed_at=observed_at,
        status=SnapshotDataStatus.AVAILABLE,
        source="MASTER_ACCOUNT_FIXTURE",
        equity=Decimal("100"),
        cash_balance=Decimal("100"),
        day_start_equity=Decimal("100"),
        equity_peak=Decimal("100"),
        source_ref="fixture:capital",
    )


def exposure(
    system_id: str,
    observed_at: datetime,
    *,
    risk: str = "0",
    gross: str = "0",
    positions: int = 0,
):
    return CrewExposureSnapshot(
        system_id=system_id,
        observed_at=observed_at,
        status=SnapshotDataStatus.AVAILABLE,
        source="SYSTEM_EXPOSURE_FIXTURE",
        open_positions=positions,
        gross_exposure_amount=Decimal(gross),
        open_risk_amount=Decimal(risk),
        source_ref=f"fixture:{system_id}",
    )


def opening_snapshot():
    return build_master_portfolio_snapshot(
        master_capital=capital(OPENED_AT),
        members=members(),
        crew_exposures=(
            exposure("crew-a", OPENED_AT),
            exposure("crew-b", OPENED_AT),
        ),
    )


def current_snapshot(
    *,
    crew_a_risk: str = "0",
    crew_a_gross: str = "0",
    crew_b_risk: str = "0",
    crew_b_gross: str = "0",
):
    return build_master_portfolio_snapshot(
        master_capital=capital(OBSERVED_AT),
        members=members(),
        crew_exposures=(
            exposure(
                "crew-a",
                OBSERVED_AT,
                risk=crew_a_risk,
                gross=crew_a_gross,
                positions=int(Decimal(crew_a_gross) > 0),
            ),
            exposure(
                "crew-b",
                OBSERVED_AT,
                risk=crew_b_risk,
                gross=crew_b_gross,
                positions=int(Decimal(crew_b_gross) > 0),
            ),
        ),
    )


def unavailable_snapshot():
    unavailable = CrewExposureSnapshot(
        system_id="crew-b",
        observed_at=OBSERVED_AT,
        status=SnapshotDataStatus.UNAVAILABLE,
        source="SYSTEM_EXPOSURE_FIXTURE",
        reason_code="SOURCE_NOT_CONFIGURED",
    )
    return build_master_portfolio_snapshot(
        master_capital=capital(OBSERVED_AT),
        members=members(),
        crew_exposures=(exposure("crew-a", OBSERVED_AT), unavailable),
    )


def gate_policy(
    policy,
    *,
    max_risk: str = "10",
    max_gross: str = "200",
):
    return build_master_risk_gate_policy(
        master_portfolio_id="master-main",
        gate_policy_id="global-v1",
        allocation_policy_fingerprint_sha256=policy.fingerprint_sha256,
        max_total_open_risk_amount=Decimal(max_risk),
        max_total_gross_exposure_amount=Decimal(max_gross),
        source_ref="operator-config:global-v1",
    )


def local_decision(
    *,
    proposal_id: str = "proposal-1",
    status: RiskDecisionStatus = RiskDecisionStatus.APPROVED,
    quantity: str = "2",
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
    reason = (
        RiskReasonCode.APPROVED
        if status is RiskDecisionStatus.APPROVED
        else RiskReasonCode.RESIZED_PORTFOLIO_RISK
    )
    return RiskDecision(
        proposal_id=proposal_id,
        status=status,
        reason_codes=(reason,),
        approved_quantity=Decimal(quantity),
        approved_risk_amount=Decimal(risk),
        approved_notional=Decimal(notional),
        created_at=RISK_AT,
        details={"source": "local-risk"},
    )


def reserve(
    ledger: MasterReservationLedger,
    *,
    request_id: str,
    proposal_id: str,
    system_id: str,
    risk: str,
    gross: str,
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


def base_context(
    *,
    candidate_status: RiskDecisionStatus = RiskDecisionStatus.APPROVED,
    candidate_risk: str = "3",
    candidate_gross: str = "50",
    candidate_request_ref: str = "proposal-1",
    gate_max_risk: str = "10",
    gate_max_gross: str = "200",
):
    policy = allocation_policy()
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening_snapshot())
    reservation = reserve(
        ledger,
        request_id="candidate-request",
        proposal_id=candidate_request_ref,
        system_id="crew-a",
        risk=candidate_risk,
        gross=candidate_gross,
    )
    decision = local_decision(
        status=candidate_status,
        risk=candidate_risk,
        notional=candidate_gross,
    )
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=decision,
        reservation_id=reservation.reservation_id,
    )
    return policy, ledger, candidate, gate_policy(
        policy,
        max_risk=gate_max_risk,
        max_gross=gate_max_gross,
    )


def evaluate(policy, ledger, candidate, gate, snapshot=None):
    return evaluate_master_risk_gate(
        gate_policy=gate,
        allocation_policy=policy,
        candidate=candidate,
        portfolio_snapshot=snapshot or current_snapshot(),
        ledger_snapshot=ledger.snapshot(),
        evaluated_at=EVALUATED_AT,
    )


def test_evaluator_admits_clean_authorized_candidate_without_resize() -> None:
    policy, ledger, candidate, gate = base_context()

    decision = evaluate(policy, ledger, candidate, gate)

    assert decision.status is MasterRiskGateDecisionStatus.ADMIT
    assert decision.reason_codes == (MasterRiskGateReasonCode.ADMITTED,)
    assert decision.admitted_quantity == candidate.local_approved_quantity
    assert decision.admitted_risk_amount == candidate.local_approved_risk_amount
    assert decision.admitted_notional == candidate.local_approved_notional
    assert decision.resize_applied is False
    assert decision.local_risk_override is False


def test_resized_local_decision_can_only_be_admitted_at_exact_local_amounts() -> None:
    policy, ledger, candidate, gate = base_context(
        candidate_status=RiskDecisionStatus.RESIZED,
    )

    decision = evaluate(policy, ledger, candidate, gate)

    assert decision.status is MasterRiskGateDecisionStatus.ADMIT
    assert decision.local_risk_status is RiskDecisionStatus.RESIZED
    assert decision.admitted_quantity == Decimal("2")
    assert decision.admitted_risk_amount == Decimal("3")
    assert decision.admitted_notional == Decimal("50")


def test_local_rejection_is_terminal_for_master_gate() -> None:
    policy = allocation_policy()
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening_snapshot())
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(status=RiskDecisionStatus.REJECTED),
        reservation_id=None,
    )

    decision = evaluate(policy, ledger, candidate, gate_policy(policy))

    assert decision.status is MasterRiskGateDecisionStatus.REJECT
    assert MasterRiskGateReasonCode.LOCAL_RISK_NOT_AUTHORIZED in decision.reason_codes
    assert decision.admitted_quantity == 0
    assert decision.admitted_risk_amount == 0
    assert decision.admitted_notional == 0


def test_not_configured_gate_policy_rejects_fail_closed() -> None:
    policy, ledger, candidate, _ = base_context()
    gate = build_master_risk_gate_policy(
        master_portfolio_id="master-main",
        gate_policy_id="global-v1",
        allocation_policy_fingerprint_sha256=policy.fingerprint_sha256,
        reason_code="OPERATOR_CONFIGURATION_REQUIRED",
    )

    decision = evaluate(policy, ledger, candidate, gate)

    assert gate.status is MasterRiskGatePolicyStatus.NOT_CONFIGURED
    assert decision.status is MasterRiskGateDecisionStatus.REJECT
    assert MasterRiskGateReasonCode.GATE_POLICY_NOT_CONFIGURED in decision.reason_codes


def test_master_portfolio_identity_mismatch_rejects() -> None:
    policy, ledger, _, gate = base_context()
    reservation = ledger.snapshot().reservations[0]
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-other",
        system_id="crew-a",
        local_risk_decision=local_decision(),
        reservation_id=reservation.reservation_id,
    )

    decision = evaluate(policy, ledger, candidate, gate)

    assert decision.status is MasterRiskGateDecisionStatus.REJECT
    assert MasterRiskGateReasonCode.MASTER_PORTFOLIO_ID_MISMATCH in decision.reason_codes


def test_gate_policy_must_bind_exact_allocation_policy() -> None:
    policy, ledger, candidate, _ = base_context()
    other_policy = allocation_policy(policy_id="static-v2")
    gate = gate_policy(other_policy)

    decision = evaluate(policy, ledger, candidate, gate)

    assert MasterRiskGateReasonCode.ALLOCATION_POLICY_MISMATCH in decision.reason_codes
    assert decision.status is MasterRiskGateDecisionStatus.REJECT


def test_ledger_must_bind_exact_allocation_policy() -> None:
    policy = allocation_policy()
    other_policy = allocation_policy(policy_id="static-v2")
    ledger = MasterReservationLedger(
        policy=other_policy,
        opening_snapshot=opening_snapshot(),
    )
    reservation = reserve(
        ledger,
        request_id="candidate-request",
        proposal_id="proposal-1",
        system_id="crew-a",
        risk="3",
        gross="50",
    )
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(),
        reservation_id=reservation.reservation_id,
    )

    decision = evaluate(policy, ledger, candidate, gate_policy(policy))

    assert MasterRiskGateReasonCode.LEDGER_POLICY_MISMATCH in decision.reason_codes
    assert decision.status is MasterRiskGateDecisionStatus.REJECT


def test_candidate_system_must_be_known_to_master_context() -> None:
    policy = allocation_policy()
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening_snapshot())
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-c",
        local_risk_decision=local_decision(status=RiskDecisionStatus.REJECTED),
        reservation_id=None,
    )

    decision = evaluate(policy, ledger, candidate, gate_policy(policy))

    assert MasterRiskGateReasonCode.SYSTEM_NOT_MEMBER in decision.reason_codes
    assert decision.status is MasterRiskGateDecisionStatus.REJECT


def test_unavailable_portfolio_snapshot_rejects() -> None:
    policy, ledger, candidate, gate = base_context()

    decision = evaluate(policy, ledger, candidate, gate, unavailable_snapshot())

    assert MasterRiskGateReasonCode.PORTFOLIO_SNAPSHOT_UNAVAILABLE in decision.reason_codes
    assert (
        MasterRiskGateReasonCode.RESERVATION_RECONCILIATION_UNAVAILABLE
        in decision.reason_codes
    )
    assert decision.status is MasterRiskGateDecisionStatus.REJECT


def test_missing_reservation_rejects_authorized_candidate() -> None:
    policy = allocation_policy()
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening_snapshot())
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(),
        reservation_id="reservation:missing",
    )

    decision = evaluate(policy, ledger, candidate, gate_policy(policy))

    assert MasterRiskGateReasonCode.RESERVATION_NOT_FOUND in decision.reason_codes
    assert decision.status is MasterRiskGateDecisionStatus.REJECT


def test_committed_candidate_reservation_is_not_reusable_for_admission() -> None:
    policy, ledger, candidate, gate = base_context()
    assert candidate.reservation_id is not None
    ledger.commit(
        candidate.reservation_id,
        committed_at=COMMITTED_AT,
        commit_ref="execution:proposal-1",
    )

    decision = evaluate(
        policy,
        ledger,
        candidate,
        gate,
        current_snapshot(crew_a_risk="3", crew_a_gross="50"),
    )

    assert MasterRiskGateReasonCode.RESERVATION_NOT_RESERVED in decision.reason_codes
    assert decision.status is MasterRiskGateDecisionStatus.REJECT


def test_released_candidate_reservation_is_not_reusable_for_admission() -> None:
    policy, ledger, candidate, gate = base_context()
    assert candidate.reservation_id is not None
    ledger.release(
        candidate.reservation_id,
        released_at=COMMITTED_AT,
        release_ref="cancelled:proposal-1",
    )

    decision = evaluate(policy, ledger, candidate, gate)

    assert MasterRiskGateReasonCode.RESERVATION_NOT_RESERVED in decision.reason_codes
    assert decision.status is MasterRiskGateDecisionStatus.REJECT


def test_reservation_request_ref_must_bind_the_exact_proposal() -> None:
    policy, ledger, candidate, gate = base_context(
        candidate_request_ref="proposal-other",
    )

    decision = evaluate(policy, ledger, candidate, gate)

    assert MasterRiskGateReasonCode.RESERVATION_PAYLOAD_MISMATCH in decision.reason_codes
    assert decision.status is MasterRiskGateDecisionStatus.REJECT



def test_reservation_cannot_predate_the_local_risk_authorization() -> None:
    policy = allocation_policy()
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening_snapshot())
    reservation = reserve(
        ledger,
        request_id="candidate-request",
        proposal_id="proposal-1",
        system_id="crew-a",
        risk="3",
        gross="50",
        requested_at=datetime(2026, 9, 9, 22, 5, tzinfo=UTC),
    )
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(),
        reservation_id=reservation.reservation_id,
    )

    decision = evaluate(policy, ledger, candidate, gate_policy(policy))

    assert MasterRiskGateReasonCode.RESERVATION_PAYLOAD_MISMATCH in decision.reason_codes
    assert decision.status is MasterRiskGateDecisionStatus.REJECT

def test_reservation_amounts_must_match_local_risk_authorization() -> None:
    policy = allocation_policy()
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening_snapshot())
    reservation = reserve(
        ledger,
        request_id="candidate-request",
        proposal_id="proposal-1",
        system_id="crew-a",
        risk="4",
        gross="60",
    )
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(risk="3", notional="50"),
        reservation_id=reservation.reservation_id,
    )

    decision = evaluate(policy, ledger, candidate, gate_policy(policy))

    assert MasterRiskGateReasonCode.RESERVATION_PAYLOAD_MISMATCH in decision.reason_codes
    assert decision.status is MasterRiskGateDecisionStatus.REJECT


def test_concurrent_reserved_risk_is_counted_globally() -> None:
    policy, ledger, candidate, gate = base_context(gate_max_risk="6")
    reserve(
        ledger,
        request_id="other-request",
        proposal_id="proposal-2",
        system_id="crew-b",
        risk="4",
        gross="20",
    )

    decision = evaluate(policy, ledger, candidate, gate)

    assert MasterRiskGateReasonCode.MASTER_OPEN_RISK_LIMIT_EXCEEDED in decision.reason_codes
    assert decision.status is MasterRiskGateDecisionStatus.REJECT


def test_concurrent_reserved_gross_exposure_is_counted_globally() -> None:
    policy, ledger, candidate, gate = base_context(gate_max_gross="69")
    reserve(
        ledger,
        request_id="other-request",
        proposal_id="proposal-2",
        system_id="crew-b",
        risk="1",
        gross="20",
    )

    decision = evaluate(policy, ledger, candidate, gate)

    assert (
        MasterRiskGateReasonCode.MASTER_GROSS_EXPOSURE_LIMIT_EXCEEDED
        in decision.reason_codes
    )
    assert decision.status is MasterRiskGateDecisionStatus.REJECT


def test_exact_global_limits_are_admissible() -> None:
    policy, ledger, candidate, gate = base_context(
        gate_max_risk="7",
        gate_max_gross="70",
    )
    reserve(
        ledger,
        request_id="other-request",
        proposal_id="proposal-2",
        system_id="crew-b",
        risk="4",
        gross="20",
    )

    decision = evaluate(policy, ledger, candidate, gate)

    assert decision.status is MasterRiskGateDecisionStatus.ADMIT
    assert decision.reason_codes == (MasterRiskGateReasonCode.ADMITTED,)


def test_pending_committed_capacity_is_counted_without_double_spending() -> None:
    policy, ledger, candidate, gate = base_context(
        gate_max_risk="6",
        gate_max_gross="200",
    )
    existing = reserve(
        ledger,
        request_id="existing-request",
        proposal_id="proposal-existing",
        system_id="crew-b",
        risk="4",
        gross="80",
    )
    ledger.commit(
        existing.reservation_id,
        committed_at=COMMITTED_AT,
        commit_ref="execution:proposal-existing",
    )

    decision = evaluate(
        policy,
        ledger,
        candidate,
        gate,
        current_snapshot(crew_b_risk="2", crew_b_gross="40"),
    )

    assert MasterRiskGateReasonCode.MASTER_OPEN_RISK_LIMIT_EXCEEDED in decision.reason_codes
    assert (
        MasterRiskGateReasonCode.RESERVATION_RECONCILIATION_INCONSISTENT
        not in decision.reason_codes
    )
    assert decision.status is MasterRiskGateDecisionStatus.REJECT


def test_inconsistent_observed_exposure_is_fail_closed() -> None:
    policy, ledger, candidate, gate = base_context(
        gate_max_risk="100",
        gate_max_gross="1000",
    )
    existing = reserve(
        ledger,
        request_id="existing-request",
        proposal_id="proposal-existing",
        system_id="crew-b",
        risk="2",
        gross="40",
    )
    ledger.commit(
        existing.reservation_id,
        committed_at=COMMITTED_AT,
        commit_ref="execution:proposal-existing",
    )

    decision = evaluate(
        policy,
        ledger,
        candidate,
        gate,
        current_snapshot(crew_b_risk="3", crew_b_gross="50"),
    )

    assert (
        MasterRiskGateReasonCode.RESERVATION_RECONCILIATION_INCONSISTENT
        in decision.reason_codes
    )
    assert decision.status is MasterRiskGateDecisionStatus.REJECT


def test_observed_committed_exposure_is_not_double_counted() -> None:
    policy, ledger, candidate, gate = base_context(
        gate_max_risk="7",
        gate_max_gross="130",
    )
    existing = reserve(
        ledger,
        request_id="existing-request",
        proposal_id="proposal-existing",
        system_id="crew-b",
        risk="4",
        gross="80",
    )
    ledger.commit(
        existing.reservation_id,
        committed_at=COMMITTED_AT,
        commit_ref="execution:proposal-existing",
    )

    decision = evaluate(
        policy,
        ledger,
        candidate,
        gate,
        current_snapshot(crew_b_risk="4", crew_b_gross="80"),
    )

    assert decision.status is MasterRiskGateDecisionStatus.ADMIT
    assert decision.reason_codes == (MasterRiskGateReasonCode.ADMITTED,)


def test_evaluation_is_deterministic_for_identical_inputs() -> None:
    policy, ledger, candidate, gate = base_context()
    snapshot = current_snapshot()
    ledger_snapshot = ledger.snapshot()

    first = evaluate_master_risk_gate(
        gate_policy=gate,
        allocation_policy=policy,
        candidate=candidate,
        portfolio_snapshot=snapshot,
        ledger_snapshot=ledger_snapshot,
        evaluated_at=EVALUATED_AT,
    )
    second = evaluate_master_risk_gate(
        gate_policy=gate,
        allocation_policy=policy,
        candidate=candidate,
        portfolio_snapshot=snapshot,
        ledger_snapshot=ledger_snapshot,
        evaluated_at=EVALUATED_AT,
    )

    assert first == second
    assert first.decision_id == second.decision_id
    assert first.fingerprint_sha256 == second.fingerprint_sha256


def test_decision_fingerprint_changes_when_source_ledger_changes() -> None:
    policy, ledger, candidate, gate = base_context()
    first = evaluate(policy, ledger, candidate, gate)
    reserve(
        ledger,
        request_id="other-request",
        proposal_id="proposal-2",
        system_id="crew-b",
        risk="1",
        gross="10",
    )
    second = evaluate(policy, ledger, candidate, gate)

    assert first.reservation_ledger_fingerprint_sha256 != (
        second.reservation_ledger_fingerprint_sha256
    )
    assert first.fingerprint_sha256 != second.fingerprint_sha256


def test_evaluator_does_not_mutate_ledger_or_snapshot() -> None:
    policy, ledger, candidate, gate = base_context()
    snapshot = current_snapshot()
    before_ledger = ledger.snapshot()
    before_snapshot_fingerprint = snapshot.fingerprint_sha256

    decision = evaluate_master_risk_gate(
        gate_policy=gate,
        allocation_policy=policy,
        candidate=candidate,
        portfolio_snapshot=snapshot,
        ledger_snapshot=before_ledger,
        evaluated_at=EVALUATED_AT,
    )

    after_ledger = ledger.snapshot()
    assert decision.status is MasterRiskGateDecisionStatus.ADMIT
    assert after_ledger == before_ledger
    assert snapshot.fingerprint_sha256 == before_snapshot_fingerprint
    assert ledger.get(candidate.reservation_id).status is ReservationRecordStatus.RESERVED


def test_evaluated_at_must_be_timezone_aware() -> None:
    policy, ledger, candidate, gate = base_context()

    with pytest.raises(ValueError, match="evaluated_at must be timezone-aware"):
        evaluate_master_risk_gate(
            gate_policy=gate,
            allocation_policy=policy,
            candidate=candidate,
            portfolio_snapshot=current_snapshot(),
            ledger_snapshot=ledger.snapshot(),
            evaluated_at=datetime(2026, 9, 9, 23, 1),
        )


def test_reason_code_order_is_stable_for_multi_failure_reject() -> None:
    policy, ledger, candidate, _ = base_context(
        gate_max_risk="1",
        gate_max_gross="1",
    )
    gate = build_master_risk_gate_policy(
        master_portfolio_id="master-main",
        gate_policy_id="global-v1",
        allocation_policy_fingerprint_sha256=policy.fingerprint_sha256,
        reason_code="OPERATOR_CONFIGURATION_REQUIRED",
    )

    decision = evaluate(policy, ledger, candidate, gate)

    assert decision.reason_codes == tuple(
        code for code in MasterRiskGateReasonCode if code in set(decision.reason_codes)
    )
