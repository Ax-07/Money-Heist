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
    PortfolioMemberRef,
    ReservationClosureSeal,
    ReservationClosureSealStatus,
    ReservationReconciliationStatus,
    ReservationRecordStatus,
    ReservationRequest,
    SnapshotDataStatus,
    build_master_allocation_policy,
    build_master_portfolio_audit_seal,
    build_master_portfolio_snapshot,
    build_reservation_closure_seal,
    build_reservation_reconciliation_report,
)

OPENED_AT = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)
OBSERVED_AT = OPENED_AT + timedelta(minutes=10)


def member(system_id: str) -> PortfolioMemberRef:
    return PortfolioMemberRef(
        system_id=system_id,
        membership_ref=f"member:{system_id}",
    )


def envelope(system_id: str) -> CrewAllocationEnvelope:
    return CrewAllocationEnvelope(
        system_id=system_id,
        status=AllocationEnvelopeStatus.CONFIGURED,
        capital_ceiling_amount=Decimal("60"),
        open_risk_ceiling_amount=Decimal("10"),
        gross_exposure_ceiling_amount=Decimal("150"),
    )


def policy():
    members = (member("crew-a"), member("crew-b"))
    return build_master_allocation_policy(
        master_portfolio_id="master-main",
        policy_id="static-v1",
        members=members,
        envelopes=tuple(envelope(item.system_id) for item in members),
        source_ref="operator:static-v1",
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
        source="CLOSURE_FIXTURE",
        open_positions=positions,
        gross_exposure_amount=Decimal(gross),
        open_risk_amount=Decimal(risk),
        source_ref=f"fixture:{system_id}:{observed_at.isoformat()}",
    )


def snapshot(
    *,
    observed_at: datetime,
    crew_a_risk: str = "0",
    crew_a_gross: str = "0",
    crew_a_positions: int = 0,
):
    members = (member("crew-a"), member("crew-b"))
    capital = MasterCapitalSnapshot(
        master_portfolio_id="master-main",
        observed_at=observed_at,
        status=SnapshotDataStatus.AVAILABLE,
        source="MASTER_ACCOUNT_FIXTURE",
        equity=Decimal("100"),
        cash_balance=Decimal("100"),
        day_start_equity=Decimal("100"),
        equity_peak=Decimal("100"),
        source_ref=f"fixture:master:{observed_at.isoformat()}",
    )
    return build_master_portfolio_snapshot(
        master_capital=capital,
        members=members,
        crew_exposures=(
            exposure(
                "crew-a",
                observed_at=observed_at,
                risk=crew_a_risk,
                gross=crew_a_gross,
                positions=crew_a_positions,
            ),
            exposure("crew-b", observed_at=observed_at),
        ),
    )


def request(request_id: str, *, risk: str = "2", gross: str = "40") -> ReservationRequest:
    return ReservationRequest(
        request_id=request_id,
        system_id="crew-a",
        requested_at=OPENED_AT,
        capital_amount=Decimal("20"),
        open_risk_amount=Decimal(risk),
        gross_exposure_amount=Decimal(gross),
        request_ref=f"proposal:{request_id}",
    )


def evidence(*, state: str = "reserved"):
    configured_policy = policy()
    opening = snapshot(observed_at=OPENED_AT)
    ledger = MasterReservationLedger(
        policy=configured_policy,
        opening_snapshot=opening,
    )
    reserved = ledger.reserve(request("req-1"))
    assert reserved.reservation is not None
    reservation_id = reserved.reservation.reservation_id
    if state in {"committed", "released_after_commit"}:
        ledger.commit(
            reservation_id,
            committed_at=OPENED_AT + timedelta(minutes=1),
            commit_ref="fill:req-1",
        )
    if state == "released_after_commit":
        ledger.release(
            reservation_id,
            released_at=OPENED_AT + timedelta(minutes=5),
            release_ref="close:req-1",
        )
    if state == "released_direct":
        ledger.release(
            reservation_id,
            released_at=OPENED_AT + timedelta(minutes=2),
            release_ref="cancel:req-1",
        )

    if state == "committed":
        current = snapshot(
            observed_at=OBSERVED_AT,
            crew_a_risk="2",
            crew_a_gross="40",
            crew_a_positions=1,
        )
    else:
        current = snapshot(observed_at=OBSERVED_AT)
    ledger_snapshot = ledger.snapshot()
    report = build_reservation_reconciliation_report(
        policy=configured_policy,
        ledger_snapshot=ledger_snapshot,
        portfolio_snapshot=current,
    )
    return configured_policy, opening, current, ledger_snapshot, report


def seal(*, state: str = "reserved") -> ReservationClosureSeal:
    configured_policy, opening, current, ledger_snapshot, report = evidence(state=state)
    return build_reservation_closure_seal(
        policy=configured_policy,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger_snapshot=ledger_snapshot,
        reconciliation_report=report,
    )


def test_closure_seals_consistent_reserved_state_without_mutation_authority() -> None:
    result = seal(state="reserved")

    assert result.status is ReservationClosureSealStatus.SEALED
    assert result.reconciliation_status is ReservationReconciliationStatus.CONSISTENT
    assert result.reserved_count == 1
    assert result.committed_count == 0
    assert result.released_count == 0
    assert result.mutation_applied is False
    assert result.reservation_mutation is False
    assert result.allocation_mutation is False
    assert result.risk_authority is False
    assert result.admission_authority is False
    assert result.broker_authority is False
    assert result.registry_mutation is False
    assert result.live_authority is False


def test_closure_binds_policy_ledger_snapshots_and_reconciliation() -> None:
    configured_policy, opening, current, ledger_snapshot, report = evidence()
    result = build_reservation_closure_seal(
        policy=configured_policy,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger_snapshot=ledger_snapshot,
        reconciliation_report=report,
    )

    assert result.master_portfolio_id == configured_policy.master_portfolio_id
    assert result.ledger_master_portfolio_id == ledger_snapshot.master_portfolio_id
    assert result.opening_master_portfolio_id == opening.master_portfolio_id
    assert result.portfolio_master_portfolio_id == current.master_portfolio_id
    assert result.policy_id == configured_policy.policy_id
    assert result.policy_source_ref == configured_policy.source_ref
    assert result.policy_fingerprint_sha256 == configured_policy.fingerprint_sha256
    assert result.ledger_policy_fingerprint_sha256 == ledger_snapshot.policy_fingerprint_sha256
    assert result.ledger_snapshot_fingerprint_sha256 == ledger_snapshot.fingerprint_sha256
    assert result.opening_snapshot_fingerprint_sha256 == opening.fingerprint_sha256
    assert result.portfolio_snapshot_fingerprint_sha256 == current.fingerprint_sha256
    assert result.reconciliation_fingerprint_sha256 == report.fingerprint_sha256


def test_closure_binds_opening_and_current_master_provenance_audits() -> None:
    configured_policy, opening, current, ledger_snapshot, report = evidence()
    result = build_reservation_closure_seal(
        policy=configured_policy,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger_snapshot=ledger_snapshot,
        reconciliation_report=report,
    )

    assert result.opening_snapshot_audit_fingerprint_sha256 == (
        build_master_portfolio_audit_seal(opening).audit_fingerprint_sha256
    )
    assert result.portfolio_snapshot_audit_fingerprint_sha256 == (
        build_master_portfolio_audit_seal(current).audit_fingerprint_sha256
    )


def test_reserved_lifecycle_path_is_sealed() -> None:
    record = seal(state="reserved").reservation_records[0]

    assert record.status is ReservationRecordStatus.RESERVED
    assert record.transition_path == (ReservationRecordStatus.RESERVED,)
    assert record.committed_at is None
    assert record.released_at is None


def test_committed_lifecycle_path_is_sealed() -> None:
    record = seal(state="committed").reservation_records[0]

    assert record.status is ReservationRecordStatus.COMMITTED
    assert record.transition_path == (
        ReservationRecordStatus.RESERVED,
        ReservationRecordStatus.COMMITTED,
    )
    assert record.commit_ref == "fill:req-1"


def test_direct_release_lifecycle_path_is_sealed() -> None:
    record = seal(state="released_direct").reservation_records[0]

    assert record.status is ReservationRecordStatus.RELEASED
    assert record.transition_path == (
        ReservationRecordStatus.RESERVED,
        ReservationRecordStatus.RELEASED,
    )
    assert record.commit_ref is None
    assert record.release_ref == "cancel:req-1"


def test_committed_then_released_lifecycle_path_is_sealed() -> None:
    record = seal(state="released_after_commit").reservation_records[0]

    assert record.status is ReservationRecordStatus.RELEASED
    assert record.transition_path == (
        ReservationRecordStatus.RESERVED,
        ReservationRecordStatus.COMMITTED,
        ReservationRecordStatus.RELEASED,
    )
    assert record.commit_ref == "fill:req-1"
    assert record.release_ref == "close:req-1"


def test_released_capacity_is_reflected_in_closure_count() -> None:
    result = seal(state="released_after_commit")

    assert result.reserved_count == 0
    assert result.committed_count == 0
    assert result.released_count == 1


def test_closure_fingerprint_is_deterministic() -> None:
    first = seal(state="committed")
    second = seal(state="committed")

    assert first.closure_fingerprint_sha256 == second.closure_fingerprint_sha256
    assert first == second


def test_lifecycle_change_changes_closure_fingerprint() -> None:
    reserved = seal(state="reserved")
    committed = seal(state="committed")

    assert reserved.closure_fingerprint_sha256 != committed.closure_fingerprint_sha256


def test_closure_seals_pending_reconciliation_without_turning_it_into_consistent() -> None:
    configured_policy, opening, _, ledger_snapshot, _ = evidence(state="committed")
    current = snapshot(observed_at=OBSERVED_AT)
    report = build_reservation_reconciliation_report(
        policy=configured_policy,
        ledger_snapshot=ledger_snapshot,
        portfolio_snapshot=current,
    )

    result = build_reservation_closure_seal(
        policy=configured_policy,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger_snapshot=ledger_snapshot,
        reconciliation_report=report,
    )

    assert report.status is ReservationReconciliationStatus.PENDING
    assert result.reconciliation_status is ReservationReconciliationStatus.PENDING
    assert result.reason_codes == report.reason_codes


def test_closure_can_seal_policy_mismatch_as_unavailable_evidence() -> None:
    current_policy = policy()
    opening = snapshot(observed_at=OPENED_AT)
    ledger_policy = build_master_allocation_policy(
        master_portfolio_id="master-main",
        policy_id="static-ledger-v2",
        members=(member("crew-a"), member("crew-b")),
        envelopes=(envelope("crew-a"), envelope("crew-b")),
        source_ref="operator:static-ledger-v2",
    )
    ledger = MasterReservationLedger(
        policy=ledger_policy,
        opening_snapshot=opening,
    )
    ledger_snapshot = ledger.snapshot()
    current = snapshot(observed_at=OBSERVED_AT)
    report = build_reservation_reconciliation_report(
        policy=current_policy,
        ledger_snapshot=ledger_snapshot,
        portfolio_snapshot=current,
    )

    result = build_reservation_closure_seal(
        policy=current_policy,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger_snapshot=ledger_snapshot,
        reconciliation_report=report,
    )

    assert result.reconciliation_status is ReservationReconciliationStatus.UNAVAILABLE
    assert result.policy_fingerprint_sha256 == current_policy.fingerprint_sha256
    assert result.ledger_policy_fingerprint_sha256 == ledger_policy.fingerprint_sha256
    assert result.reason_codes == report.reason_codes


def test_closure_seals_inconsistent_reconciliation_without_authority() -> None:
    configured_policy, opening, _, ledger_snapshot, _ = evidence(state="committed")
    current = snapshot(
        observed_at=OBSERVED_AT,
        crew_a_risk="3",
        crew_a_gross="50",
        crew_a_positions=1,
    )
    report = build_reservation_reconciliation_report(
        policy=configured_policy,
        ledger_snapshot=ledger_snapshot,
        portfolio_snapshot=current,
    )

    result = build_reservation_closure_seal(
        policy=configured_policy,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger_snapshot=ledger_snapshot,
        reconciliation_report=report,
    )

    assert result.reconciliation_status is ReservationReconciliationStatus.INCONSISTENT
    assert result.reason_codes == report.reason_codes
    assert result.reservation_mutation is False
    assert result.risk_authority is False


def test_sealed_at_is_observation_time_not_wall_clock_time() -> None:
    result = seal()

    assert result.sealed_at == OBSERVED_AT


def test_records_are_sorted_by_reservation_id() -> None:
    configured_policy = policy()
    opening = snapshot(observed_at=OPENED_AT)
    ledger = MasterReservationLedger(
        policy=configured_policy,
        opening_snapshot=opening,
    )
    ledger.reserve(request("req-z"))
    ledger.reserve(
        ReservationRequest(
            request_id="req-a",
            system_id="crew-b",
            requested_at=OPENED_AT,
            capital_amount=Decimal("10"),
            open_risk_amount=Decimal("1"),
            gross_exposure_amount=Decimal("20"),
            request_ref="proposal:req-a",
        )
    )
    ledger_snapshot = ledger.snapshot()
    current = snapshot(observed_at=OBSERVED_AT)
    report = build_reservation_reconciliation_report(
        policy=configured_policy,
        ledger_snapshot=ledger_snapshot,
        portfolio_snapshot=current,
    )

    result = build_reservation_closure_seal(
        policy=configured_policy,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger_snapshot=ledger_snapshot,
        reconciliation_report=report,
    )

    ids = tuple(item.reservation_id for item in result.reservation_records)
    assert ids == tuple(sorted(ids))


def test_closure_rejects_wrong_opening_snapshot() -> None:
    configured_policy, _, current, ledger_snapshot, report = evidence()
    wrong_opening = snapshot(observed_at=OPENED_AT + timedelta(seconds=1))

    with pytest.raises(ValueError, match="opening snapshot does not match"):
        build_reservation_closure_seal(
            policy=configured_policy,
            opening_snapshot=wrong_opening,
            portfolio_snapshot=current,
            ledger_snapshot=ledger_snapshot,
            reconciliation_report=report,
        )


def test_closure_rejects_report_for_different_ledger_snapshot() -> None:
    configured_policy, opening, current, _, report = evidence()
    changed_ledger = MasterReservationLedger(
        policy=configured_policy,
        opening_snapshot=opening,
    )
    changed_ledger.reserve(request("req-other"))

    with pytest.raises(ValueError, match="supplied ledger snapshot"):
        build_reservation_closure_seal(
            policy=configured_policy,
            opening_snapshot=opening,
            portfolio_snapshot=current,
            ledger_snapshot=changed_ledger.snapshot(),
            reconciliation_report=report,
        )


def test_closure_rejects_report_for_different_current_snapshot() -> None:
    configured_policy, opening, _, ledger_snapshot, report = evidence()
    changed_current = snapshot(observed_at=OBSERVED_AT + timedelta(minutes=1))

    with pytest.raises(ValueError, match="portfolio snapshot"):
        build_reservation_closure_seal(
            policy=configured_policy,
            opening_snapshot=opening,
            portfolio_snapshot=changed_current,
            ledger_snapshot=ledger_snapshot,
            reconciliation_report=report,
        )


def test_closure_rejects_report_for_different_policy() -> None:
    _, opening, current, ledger_snapshot, report = evidence()
    changed_policy = build_master_allocation_policy(
        master_portfolio_id="master-main",
        policy_id="static-v2",
        members=(member("crew-a"), member("crew-b")),
        envelopes=(envelope("crew-a"), envelope("crew-b")),
        source_ref="operator:static-v2",
    )

    with pytest.raises(ValueError, match="supplied policy fingerprint"):
        build_reservation_closure_seal(
            policy=changed_policy,
            opening_snapshot=opening,
            portfolio_snapshot=current,
            ledger_snapshot=ledger_snapshot,
            reconciliation_report=report,
        )


def test_closure_is_immutable() -> None:
    result = seal()

    with pytest.raises(FrozenInstanceError):
        result.policy_id = "changed"  # type: ignore[misc]


def test_closure_rejects_tampered_counts() -> None:
    result = seal()

    with pytest.raises(ValueError, match="reserved_count"):
        replace(result, reserved_count=2)


def test_closure_rejects_tampered_fingerprint() -> None:
    result = seal()

    with pytest.raises(ValueError, match="closure fingerprint"):
        replace(result, closure_fingerprint_sha256="0" * 64)


def test_lifecycle_audit_record_rejects_invalid_transition_path() -> None:
    record = seal(state="committed").reservation_records[0]

    with pytest.raises(ValueError, match="transition_path"):
        replace(record, transition_path=(ReservationRecordStatus.RESERVED,))


def test_failed_reservation_attempts_are_not_invented_as_lifecycle_records() -> None:
    configured_policy = policy()
    opening = snapshot(observed_at=OPENED_AT)
    ledger = MasterReservationLedger(
        policy=configured_policy,
        opening_snapshot=opening,
    )
    failed = ledger.reserve(
        request("too-large", risk="99", gross="999")
    )
    assert failed.reservation is None
    ledger_snapshot = ledger.snapshot()
    current = snapshot(observed_at=OBSERVED_AT)
    report = build_reservation_reconciliation_report(
        policy=configured_policy,
        ledger_snapshot=ledger_snapshot,
        portfolio_snapshot=current,
    )

    result = build_reservation_closure_seal(
        policy=configured_policy,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger_snapshot=ledger_snapshot,
        reconciliation_report=report,
    )

    assert result.reservation_records == ()
    assert result.reserved_count == 0
    assert result.committed_count == 0
    assert result.released_count == 0
