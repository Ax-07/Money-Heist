from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.portfolio import (
    AllocationEnvelopeStatus,
    CrewAllocationEnvelope,
    CrewExposureSnapshot,
    MasterAllocationPolicy,
    MasterCapitalSnapshot,
    MasterReservationLedger,
    PortfolioMemberRef,
    ReservationReconciliationReasonCode,
    ReservationReconciliationStatus,
    ReservationRequest,
    SnapshotDataStatus,
    build_master_allocation_policy,
    build_master_portfolio_snapshot,
    build_reservation_reconciliation_report,
)

OPENED_AT = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)
OBSERVED_AT = OPENED_AT + timedelta(minutes=5)


def member(system_id: str, *, ref: str | None = None) -> PortfolioMemberRef:
    return PortfolioMemberRef(
        system_id=system_id,
        membership_ref=ref or f"member:{system_id}",
    )


def envelope(system_id: str) -> CrewAllocationEnvelope:
    return CrewAllocationEnvelope(
        system_id=system_id,
        status=AllocationEnvelopeStatus.CONFIGURED,
        capital_ceiling_amount=Decimal("60"),
        open_risk_ceiling_amount=Decimal("10"),
        gross_exposure_ceiling_amount=Decimal("150"),
    )


def policy(
    *,
    master_portfolio_id: str = "master-main",
    members: tuple[PortfolioMemberRef, ...] | None = None,
    source_ref: str = "operator:static-v1",
) -> MasterAllocationPolicy:
    configured_members = members or (member("crew-a"), member("crew-b"))
    return build_master_allocation_policy(
        master_portfolio_id=master_portfolio_id,
        policy_id="static-v1",
        members=configured_members,
        envelopes=tuple(envelope(item.system_id) for item in configured_members),
        source_ref=source_ref,
    )


def exposure(
    system_id: str,
    *,
    observed_at: datetime,
    risk: str = "0",
    gross: str = "0",
    positions: int = 0,
) -> CrewExposureSnapshot:
    return CrewExposureSnapshot(
        system_id=system_id,
        observed_at=observed_at,
        status=SnapshotDataStatus.AVAILABLE,
        source="RECONCILIATION_FIXTURE",
        open_positions=positions,
        gross_exposure_amount=Decimal(gross),
        open_risk_amount=Decimal(risk),
        source_ref=f"fixture:{system_id}:{observed_at.isoformat()}",
    )


def unavailable_exposure(
    system_id: str,
    *,
    observed_at: datetime,
) -> CrewExposureSnapshot:
    return CrewExposureSnapshot(
        system_id=system_id,
        observed_at=observed_at,
        status=SnapshotDataStatus.UNAVAILABLE,
        source="RECONCILIATION_FIXTURE",
        reason_code="SOURCE_UNAVAILABLE",
    )


def portfolio_snapshot(
    *,
    observed_at: datetime,
    master_portfolio_id: str = "master-main",
    members: tuple[PortfolioMemberRef, ...] | None = None,
    exposures: tuple[CrewExposureSnapshot, ...] | None = None,
    equity: str = "100",
    cash: str = "100",
    capital_available: bool = True,
):
    configured_members = members or (member("crew-a"), member("crew-b"))
    configured_exposures = exposures or tuple(
        exposure(item.system_id, observed_at=observed_at) for item in configured_members
    )
    if capital_available:
        capital = MasterCapitalSnapshot(
            master_portfolio_id=master_portfolio_id,
            observed_at=observed_at,
            status=SnapshotDataStatus.AVAILABLE,
            source="MASTER_ACCOUNT_FIXTURE",
            equity=Decimal(equity),
            cash_balance=Decimal(cash),
            day_start_equity=Decimal(equity),
            equity_peak=Decimal(equity),
            source_ref=f"fixture:master:{observed_at.isoformat()}",
        )
    else:
        capital = MasterCapitalSnapshot(
            master_portfolio_id=master_portfolio_id,
            observed_at=observed_at,
            status=SnapshotDataStatus.UNAVAILABLE,
            source="MASTER_ACCOUNT_FIXTURE",
            reason_code="MASTER_ACCOUNT_UNAVAILABLE",
        )
    return build_master_portfolio_snapshot(
        master_capital=capital,
        members=configured_members,
        crew_exposures=configured_exposures,
    )


def opening_snapshot():
    return portfolio_snapshot(observed_at=OPENED_AT)


def request(
    request_id: str,
    system_id: str,
    *,
    capital: str = "20",
    risk: str = "2",
    gross: str = "40",
    requested_at: datetime = OPENED_AT,
) -> ReservationRequest:
    return ReservationRequest(
        request_id=request_id,
        system_id=system_id,
        requested_at=requested_at,
        capital_amount=Decimal(capital),
        open_risk_amount=Decimal(risk),
        gross_exposure_amount=Decimal(gross),
        request_ref=f"proposal:{request_id}",
    )


def ledger_and_policy() -> tuple[MasterReservationLedger, MasterAllocationPolicy]:
    configured_policy = policy()
    return (
        MasterReservationLedger(
            policy=configured_policy,
            opening_snapshot=opening_snapshot(),
        ),
        configured_policy,
    )


def reserve_and_commit(
    ledger: MasterReservationLedger,
    *,
    request_id: str,
    system_id: str,
    risk: str = "2",
    gross: str = "40",
    committed_at: datetime | None = None,
) -> str:
    result = ledger.reserve(
        request(
            request_id,
            system_id,
            risk=risk,
            gross=gross,
        )
    )
    assert result.reservation is not None
    reservation_id = result.reservation.reservation_id
    ledger.commit(
        reservation_id,
        committed_at=committed_at or OPENED_AT + timedelta(minutes=1),
        commit_ref=f"fill:{request_id}",
    )
    return reservation_id


def reconcile(
    ledger: MasterReservationLedger,
    configured_policy: MasterAllocationPolicy,
    current_snapshot,
):
    return build_reservation_reconciliation_report(
        policy=configured_policy,
        ledger_snapshot=ledger.snapshot(),
        portfolio_snapshot=current_snapshot,
    )


def test_exact_committed_exposure_is_consistent() -> None:
    ledger, configured_policy = ledger_and_policy()
    reserve_and_commit(ledger, request_id="req-1", system_id="crew-a", risk="2", gross="40")
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        exposures=(
            exposure("crew-a", observed_at=OBSERVED_AT, risk="2", gross="40", positions=1),
            exposure("crew-b", observed_at=OBSERVED_AT),
        ),
    )

    report = reconcile(ledger, configured_policy, current)

    assert report.status is ReservationReconciliationStatus.CONSISTENT
    assert report.reason_codes == ()
    crew_a = report.crews[0]
    assert crew_a.open_risk_delta_amount == Decimal("0")
    assert crew_a.gross_exposure_delta_amount == Decimal("0")


def test_reserved_capacity_is_not_expected_in_observed_market_exposure() -> None:
    ledger, configured_policy = ledger_and_policy()
    result = ledger.reserve(request("req-1", "crew-a", risk="3", gross="50"))
    assert result.reservation is not None

    report = reconcile(
        ledger,
        configured_policy,
        portfolio_snapshot(observed_at=OBSERVED_AT),
    )

    assert report.status is ReservationReconciliationStatus.CONSISTENT
    crew_a = report.crews[0]
    assert crew_a.reserved_open_risk_amount == Decimal("3")
    assert crew_a.committed_open_risk_amount == Decimal("0")
    assert crew_a.reason_codes == ()


def test_observed_exposure_against_only_reserved_capacity_is_inconsistent() -> None:
    ledger, configured_policy = ledger_and_policy()
    ledger.reserve(request("req-1", "crew-a", risk="3", gross="50"))
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        exposures=(
            exposure("crew-a", observed_at=OBSERVED_AT, risk="1", gross="20", positions=1),
            exposure("crew-b", observed_at=OBSERVED_AT),
        ),
    )

    report = reconcile(ledger, configured_policy, current)

    assert report.status is ReservationReconciliationStatus.INCONSISTENT
    assert (
        ReservationReconciliationReasonCode.OBSERVED_OPEN_RISK_EXCEEDS_COMMITTED
        in report.crews[0].reason_codes
    )


def test_committed_capacity_not_yet_observed_is_pending() -> None:
    ledger, configured_policy = ledger_and_policy()
    reserve_and_commit(ledger, request_id="req-1", system_id="crew-a", risk="2", gross="40")

    report = reconcile(
        ledger,
        configured_policy,
        portfolio_snapshot(observed_at=OBSERVED_AT),
    )

    assert report.status is ReservationReconciliationStatus.PENDING
    assert report.crews[0].reason_codes == (
        ReservationReconciliationReasonCode.COMMITTED_OPEN_RISK_NOT_YET_OBSERVED,
        ReservationReconciliationReasonCode.COMMITTED_GROSS_EXPOSURE_NOT_YET_OBSERVED,
    )


def test_partial_observation_remains_pending_without_inventing_a_failure() -> None:
    ledger, configured_policy = ledger_and_policy()
    reserve_and_commit(ledger, request_id="req-1", system_id="crew-a", risk="2", gross="40")
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        exposures=(
            exposure("crew-a", observed_at=OBSERVED_AT, risk="2", gross="25", positions=1),
            exposure("crew-b", observed_at=OBSERVED_AT),
        ),
    )

    report = reconcile(ledger, configured_policy, current)

    assert report.status is ReservationReconciliationStatus.PENDING
    assert report.crews[0].reason_codes == (
        ReservationReconciliationReasonCode.COMMITTED_GROSS_EXPOSURE_NOT_YET_OBSERVED,
    )


def test_observed_open_risk_above_committed_is_inconsistent() -> None:
    ledger, configured_policy = ledger_and_policy()
    reserve_and_commit(ledger, request_id="req-1", system_id="crew-a", risk="2", gross="40")
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        exposures=(
            exposure("crew-a", observed_at=OBSERVED_AT, risk="3", gross="40", positions=1),
            exposure("crew-b", observed_at=OBSERVED_AT),
        ),
    )

    report = reconcile(ledger, configured_policy, current)

    assert report.status is ReservationReconciliationStatus.INCONSISTENT
    assert report.crews[0].open_risk_delta_amount == Decimal("1")
    assert report.crews[0].reason_codes == (
        ReservationReconciliationReasonCode.OBSERVED_OPEN_RISK_EXCEEDS_COMMITTED,
    )


def test_observed_gross_above_committed_is_inconsistent() -> None:
    ledger, configured_policy = ledger_and_policy()
    reserve_and_commit(ledger, request_id="req-1", system_id="crew-a", risk="2", gross="40")
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        exposures=(
            exposure("crew-a", observed_at=OBSERVED_AT, risk="2", gross="45", positions=1),
            exposure("crew-b", observed_at=OBSERVED_AT),
        ),
    )

    report = reconcile(ledger, configured_policy, current)

    assert report.status is ReservationReconciliationStatus.INCONSISTENT
    assert report.crews[0].gross_exposure_delta_amount == Decimal("5")
    assert report.crews[0].reason_codes == (
        ReservationReconciliationReasonCode.OBSERVED_GROSS_EXPOSURE_EXCEEDS_COMMITTED,
    )


def test_released_commitment_with_lingering_observed_exposure_is_inconsistent() -> None:
    ledger, configured_policy = ledger_and_policy()
    reservation_id = reserve_and_commit(
        ledger,
        request_id="req-1",
        system_id="crew-a",
        risk="2",
        gross="40",
    )
    ledger.release(
        reservation_id,
        released_at=OPENED_AT + timedelta(minutes=2),
        release_ref="close:req-1",
    )
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        exposures=(
            exposure("crew-a", observed_at=OBSERVED_AT, risk="2", gross="40", positions=1),
            exposure("crew-b", observed_at=OBSERVED_AT),
        ),
    )

    report = reconcile(ledger, configured_policy, current)

    assert report.status is ReservationReconciliationStatus.INCONSISTENT
    assert report.crews[0].committed_gross_exposure_amount == Decimal("0")


def test_unavailable_crew_exposure_is_preserved_without_invented_deltas() -> None:
    ledger, configured_policy = ledger_and_policy()
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        exposures=(
            unavailable_exposure("crew-a", observed_at=OBSERVED_AT),
            exposure("crew-b", observed_at=OBSERVED_AT),
        ),
    )

    report = reconcile(ledger, configured_policy, current)

    assert report.status is ReservationReconciliationStatus.UNAVAILABLE
    crew_a = report.crews[0]
    assert crew_a.status is ReservationReconciliationStatus.UNAVAILABLE
    assert crew_a.open_risk_delta_amount is None
    assert crew_a.gross_exposure_delta_amount is None
    assert crew_a.reason_codes == (
        ReservationReconciliationReasonCode.CREW_EXPOSURE_UNAVAILABLE,
    )


def test_unavailable_master_capital_makes_report_unavailable_but_keeps_crew_comparison() -> None:
    ledger, configured_policy = ledger_and_policy()
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        capital_available=False,
    )

    report = reconcile(ledger, configured_policy, current)

    assert report.status is ReservationReconciliationStatus.UNAVAILABLE
    assert report.crews[0].status is ReservationReconciliationStatus.CONSISTENT
    assert (
        ReservationReconciliationReasonCode.PORTFOLIO_SNAPSHOT_UNAVAILABLE.value
        in report.reason_codes
    )


def test_policy_fingerprint_mismatch_fails_closed_before_crew_comparison() -> None:
    ledger, _ = ledger_and_policy()
    changed_policy = policy(source_ref="operator:static-v2")

    report = build_reservation_reconciliation_report(
        policy=changed_policy,
        ledger_snapshot=ledger.snapshot(),
        portfolio_snapshot=portfolio_snapshot(observed_at=OBSERVED_AT),
    )

    assert report.status is ReservationReconciliationStatus.UNAVAILABLE
    assert report.crews == ()
    assert report.reason_codes == (
        ReservationReconciliationReasonCode.POLICY_FINGERPRINT_MISMATCH.value,
    )


def test_membership_ref_change_fails_closed_even_when_system_ids_are_unchanged() -> None:
    ledger, configured_policy = ledger_and_policy()
    changed_members = (member("crew-a", ref="member:crew-a:v2"), member("crew-b"))
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        members=changed_members,
    )

    report = reconcile(ledger, configured_policy, current)

    assert report.status is ReservationReconciliationStatus.UNAVAILABLE
    assert report.crews == ()
    assert report.reason_codes == (
        ReservationReconciliationReasonCode.MEMBERSHIP_MISMATCH.value,
    )


def test_master_portfolio_id_mismatch_fails_closed() -> None:
    ledger, configured_policy = ledger_and_policy()
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        master_portfolio_id="master-other",
    )

    report = reconcile(ledger, configured_policy, current)

    assert report.status is ReservationReconciliationStatus.UNAVAILABLE
    assert report.crews == ()
    assert report.reason_codes == (
        ReservationReconciliationReasonCode.MASTER_PORTFOLIO_ID_MISMATCH.value,
    )


def test_ledger_event_after_observation_fails_closed_instead_of_replaying_history() -> None:
    ledger, configured_policy = ledger_and_policy()
    reserve_and_commit(
        ledger,
        request_id="req-1",
        system_id="crew-a",
        committed_at=OBSERVED_AT + timedelta(minutes=1),
    )

    report = reconcile(
        ledger,
        configured_policy,
        portfolio_snapshot(observed_at=OBSERVED_AT),
    )

    assert report.status is ReservationReconciliationStatus.UNAVAILABLE
    assert report.crews == ()
    assert report.reason_codes == (
        ReservationReconciliationReasonCode.LEDGER_STATE_AFTER_OBSERVATION.value,
    )


def test_future_reserved_request_also_blocks_historical_reconciliation() -> None:
    ledger, configured_policy = ledger_and_policy()
    ledger.reserve(
        request(
            "req-future",
            "crew-a",
            requested_at=OBSERVED_AT + timedelta(seconds=1),
        )
    )

    report = reconcile(
        ledger,
        configured_policy,
        portfolio_snapshot(observed_at=OBSERVED_AT),
    )

    assert report.status is ReservationReconciliationStatus.UNAVAILABLE
    assert ReservationReconciliationReasonCode.LEDGER_STATE_AFTER_OBSERVATION.value in (
        report.reason_codes
    )


def test_mixed_pending_and_inconsistent_crews_surfaces_confirmed_inconsistency() -> None:
    ledger, configured_policy = ledger_and_policy()
    reserve_and_commit(ledger, request_id="req-a", system_id="crew-a", risk="2", gross="40")
    reserve_and_commit(ledger, request_id="req-b", system_id="crew-b", risk="2", gross="40")
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        exposures=(
            exposure("crew-a", observed_at=OBSERVED_AT, risk="1", gross="20", positions=1),
            exposure("crew-b", observed_at=OBSERVED_AT, risk="3", gross="40", positions=1),
        ),
    )

    report = reconcile(ledger, configured_policy, current)

    assert report.status is ReservationReconciliationStatus.INCONSISTENT
    assert report.crews[0].status is ReservationReconciliationStatus.PENDING
    assert report.crews[1].status is ReservationReconciliationStatus.INCONSISTENT


def test_master_equity_and_cash_are_not_treated_as_crew_committed_capital() -> None:
    ledger, configured_policy = ledger_and_policy()
    reserve_and_commit(ledger, request_id="req-1", system_id="crew-a", risk="2", gross="40")
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        equity="70",
        cash="30",
        exposures=(
            exposure("crew-a", observed_at=OBSERVED_AT, risk="2", gross="40", positions=1),
            exposure("crew-b", observed_at=OBSERVED_AT),
        ),
    )

    report = reconcile(ledger, configured_policy, current)

    assert report.status is ReservationReconciliationStatus.CONSISTENT
    assert report.crews[0].committed_capital_amount == Decimal("20")


def test_open_position_count_is_observed_but_not_invented_as_a_reservation_dimension() -> None:
    ledger, configured_policy = ledger_and_policy()
    reserve_and_commit(ledger, request_id="req-1", system_id="crew-a", risk="2", gross="40")
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        exposures=(
            exposure("crew-a", observed_at=OBSERVED_AT, risk="2", gross="40", positions=3),
            exposure("crew-b", observed_at=OBSERVED_AT),
        ),
    )

    report = reconcile(ledger, configured_policy, current)

    assert report.status is ReservationReconciliationStatus.CONSISTENT
    assert report.crews[0].observed_open_positions == 3


def test_report_fingerprint_is_deterministic_for_identical_evidence() -> None:
    ledger, configured_policy = ledger_and_policy()
    reserve_and_commit(ledger, request_id="req-1", system_id="crew-a", risk="2", gross="40")
    current = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        exposures=(
            exposure("crew-a", observed_at=OBSERVED_AT, risk="2", gross="40", positions=1),
            exposure("crew-b", observed_at=OBSERVED_AT),
        ),
    )

    first = reconcile(ledger, configured_policy, current)
    second = reconcile(ledger, configured_policy, current)

    assert first == second
    assert first.fingerprint_sha256 == second.fingerprint_sha256


def test_material_observed_exposure_change_changes_report_fingerprint() -> None:
    ledger, configured_policy = ledger_and_policy()
    reserve_and_commit(ledger, request_id="req-1", system_id="crew-a", risk="2", gross="40")
    exact = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        exposures=(
            exposure("crew-a", observed_at=OBSERVED_AT, risk="2", gross="40", positions=1),
            exposure("crew-b", observed_at=OBSERVED_AT),
        ),
    )
    changed = portfolio_snapshot(
        observed_at=OBSERVED_AT,
        exposures=(
            exposure("crew-a", observed_at=OBSERVED_AT, risk="3", gross="40", positions=1),
            exposure("crew-b", observed_at=OBSERVED_AT),
        ),
    )

    first = reconcile(ledger, configured_policy, exact)
    second = reconcile(ledger, configured_policy, changed)

    assert first.fingerprint_sha256 != second.fingerprint_sha256


def test_report_is_immutable_and_has_no_mutation_or_execution_authority() -> None:
    ledger, configured_policy = ledger_and_policy()
    report = reconcile(
        ledger,
        configured_policy,
        portfolio_snapshot(observed_at=OBSERVED_AT),
    )

    with pytest.raises(FrozenInstanceError):
        report.status = ReservationReconciliationStatus.INCONSISTENT  # type: ignore[misc]
    assert report.mutation_applied is False
    assert report.reservation_mutation is False
    assert report.risk_authority is False
    assert report.admission_authority is False
    assert report.broker_authority is False
    assert report.live_authority is False
