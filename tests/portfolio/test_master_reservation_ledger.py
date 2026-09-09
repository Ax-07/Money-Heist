from dataclasses import FrozenInstanceError
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
    ReservationIdempotencyConflict,
    ReservationLedgerInitializationError,
    ReservationOutcomeStatus,
    ReservationReasonCode,
    ReservationRecordStatus,
    ReservationRequest,
    ReservationStateTransitionError,
    SnapshotDataStatus,
    build_master_allocation_policy,
    build_master_portfolio_snapshot,
)

NOW = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)


def member(system_id: str, *, ref: str | None = None) -> PortfolioMemberRef:
    return PortfolioMemberRef(
        system_id=system_id,
        membership_ref=ref or f"member:{system_id}",
    )


def flat_exposure(system_id: str) -> CrewExposureSnapshot:
    return CrewExposureSnapshot(
        system_id=system_id,
        observed_at=NOW,
        status=SnapshotDataStatus.AVAILABLE,
        source="RESERVATION_FIXTURE",
        open_positions=0,
        gross_exposure_amount=Decimal("0"),
        open_risk_amount=Decimal("0"),
        source_ref=f"fixture:{system_id}",
    )


def snapshot(
    *,
    equity: str = "100",
    cash: str | None = None,
    members: tuple[PortfolioMemberRef, ...] | None = None,
    exposures: tuple[CrewExposureSnapshot, ...] | None = None,
):
    configured_members = members or (member("crew-a"), member("crew-b"))
    configured_exposures = exposures or tuple(
        flat_exposure(item.system_id) for item in configured_members
    )
    equity_value = Decimal(equity)
    cash_value = equity_value if cash is None else Decimal(cash)
    capital = MasterCapitalSnapshot(
        master_portfolio_id="master-main",
        observed_at=NOW,
        status=SnapshotDataStatus.AVAILABLE,
        source="MASTER_ACCOUNT_FIXTURE",
        equity=equity_value,
        cash_balance=cash_value,
        day_start_equity=equity_value,
        equity_peak=equity_value,
        source_ref="fixture:master-capital",
    )
    return build_master_portfolio_snapshot(
        master_capital=capital,
        members=configured_members,
        crew_exposures=configured_exposures,
    )


def envelope(
    system_id: str,
    *,
    capital: str = "60",
    risk: str = "5",
    gross: str = "120",
) -> CrewAllocationEnvelope:
    return CrewAllocationEnvelope(
        system_id=system_id,
        status=AllocationEnvelopeStatus.CONFIGURED,
        capital_ceiling_amount=Decimal(capital),
        open_risk_ceiling_amount=Decimal(risk),
        gross_exposure_ceiling_amount=Decimal(gross),
    )


def policy(
    *,
    master_portfolio_id: str = "master-main",
    members: tuple[PortfolioMemberRef, ...] | None = None,
    crew_a_capital: str = "60",
    crew_b_capital: str = "60",
):
    configured_members = members or (member("crew-a"), member("crew-b"))
    envelopes = []
    for item in configured_members:
        capital = crew_a_capital if item.system_id == "crew-a" else crew_b_capital
        envelopes.append(envelope(item.system_id, capital=capital))
    return build_master_allocation_policy(
        master_portfolio_id=master_portfolio_id,
        policy_id="static-v1",
        members=configured_members,
        envelopes=tuple(envelopes),
        source_ref="operator-config:static-v1",
    )


def request(
    request_id: str,
    system_id: str,
    *,
    capital: str = "20",
    risk: str = "2",
    gross: str = "40",
    requested_at: datetime = NOW,
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


def ledger() -> MasterReservationLedger:
    return MasterReservationLedger(policy=policy(), opening_snapshot=snapshot())


def test_ledger_opens_only_from_explicit_flat_master_state() -> None:
    result = ledger()
    state = result.snapshot()

    assert state.master_capital_capacity_amount == Decimal("100")
    assert state.active_capital_amount == Decimal("0")
    assert state.available_capital_amount == Decimal("100")
    assert result.risk_authority is False
    assert result.admission_authority is False
    assert result.broker_authority is False
    assert result.live_authority is False


def test_ledger_rejects_not_configured_policy() -> None:
    members = (member("crew-a"), member("crew-b"))
    incomplete = build_master_allocation_policy(
        master_portfolio_id="master-main",
        policy_id="static-v1",
        members=members,
        envelopes=(
            envelope("crew-a"),
            CrewAllocationEnvelope(
                system_id="crew-b",
                status=AllocationEnvelopeStatus.NOT_CONFIGURED,
                reason_code="OPERATOR_CONFIGURATION_REQUIRED",
            ),
        ),
    )

    with pytest.raises(ReservationLedgerInitializationError, match="fully CONFIGURED"):
        MasterReservationLedger(policy=incomplete, opening_snapshot=snapshot(members=members))


def test_ledger_rejects_unavailable_opening_snapshot() -> None:
    members = (member("crew-a"), member("crew-b"))
    missing = CrewExposureSnapshot(
        system_id="crew-b",
        observed_at=NOW,
        status=SnapshotDataStatus.UNAVAILABLE,
        source="RESERVATION_FIXTURE",
        reason_code="SOURCE_UNAVAILABLE",
    )
    unavailable = snapshot(
        members=members,
        exposures=(flat_exposure("crew-a"), missing),
    )

    with pytest.raises(ReservationLedgerInitializationError, match="must be AVAILABLE"):
        MasterReservationLedger(policy=policy(members=members), opening_snapshot=unavailable)


def test_ledger_rejects_master_or_membership_mismatch() -> None:
    other_master_policy = policy(master_portfolio_id="master-other")
    with pytest.raises(ReservationLedgerInitializationError, match="different Master Portfolios"):
        MasterReservationLedger(policy=other_master_policy, opening_snapshot=snapshot())

    changed_members = (member("crew-a", ref="member:crew-a:v2"), member("crew-b"))
    with pytest.raises(ReservationLedgerInitializationError, match="membership must match"):
        MasterReservationLedger(policy=policy(members=changed_members), opening_snapshot=snapshot())


def test_ledger_rejects_non_flat_opening_portfolio() -> None:
    exposed = CrewExposureSnapshot(
        system_id="crew-a",
        observed_at=NOW,
        status=SnapshotDataStatus.AVAILABLE,
        source="RESERVATION_FIXTURE",
        open_positions=1,
        gross_exposure_amount=Decimal("10"),
        open_risk_amount=Decimal("1"),
    )
    non_flat = snapshot(exposures=(exposed, flat_exposure("crew-b")))

    with pytest.raises(ReservationLedgerInitializationError, match="requires.*flat"):
        MasterReservationLedger(policy=policy(), opening_snapshot=non_flat)


def test_ledger_rejects_flat_snapshot_when_cash_and_equity_disagree() -> None:
    with pytest.raises(ReservationLedgerInitializationError, match="cash_balance to equal equity"):
        MasterReservationLedger(policy=policy(), opening_snapshot=snapshot(equity="100", cash="90"))


def test_request_is_explicit_finite_and_non_empty() -> None:
    with pytest.raises(ValueError, match="at least one non-zero"):
        request("req-0", "crew-a", capital="0", risk="0", gross="0")
    with pytest.raises(ValueError, match="finite and >= 0"):
        request("req-neg", "crew-a", capital="-1")
    with pytest.raises(ValueError, match="timezone-aware"):
        request(
            "req-naive",
            "crew-a",
            requested_at=datetime(2026, 9, 9, 22, 0),
        )


def test_successful_reservation_consumes_crew_and_master_capital_once() -> None:
    result = ledger()
    attempt = result.reserve(request("req-1", "crew-a", capital="40", risk="3", gross="80"))

    assert attempt.status is ReservationOutcomeStatus.RESERVED
    assert attempt.reason_codes == ()
    assert attempt.reservation is not None
    assert attempt.reservation.status is ReservationRecordStatus.RESERVED
    state = result.snapshot()
    assert state.reserved_capital_amount == Decimal("40")
    assert state.available_capital_amount == Decimal("60")


def test_per_crew_capital_ceiling_is_enforced_without_global_normalization() -> None:
    result = ledger()
    attempt = result.reserve(request("req-1", "crew-a", capital="61", risk="1", gross="10"))

    assert attempt.status is ReservationOutcomeStatus.NOT_RESERVED
    assert attempt.reason_codes == (ReservationReasonCode.CAPITAL_ENVELOPE_EXCEEDED,)
    assert result.snapshot().active_capital_amount == Decimal("0")


def test_per_crew_risk_and_gross_ceilings_are_enforced() -> None:
    result = ledger()
    risk_attempt = result.reserve(
        request("req-risk", "crew-a", capital="1", risk="6", gross="1")
    )
    gross_attempt = result.reserve(
        request("req-gross", "crew-b", capital="1", risk="1", gross="121")
    )

    assert risk_attempt.reason_codes == (ReservationReasonCode.OPEN_RISK_ENVELOPE_EXCEEDED,)
    assert gross_attempt.reason_codes == (
        ReservationReasonCode.GROSS_EXPOSURE_ENVELOPE_EXCEEDED,
    )


def test_per_crew_ceilings_apply_to_cumulative_active_usage() -> None:
    result = ledger()
    first = result.reserve(
        request("req-1", "crew-a", capital="20", risk="3", gross="70")
    )
    second = result.reserve(
        request("req-2", "crew-a", capital="20", risk="3", gross="60")
    )

    assert first.status is ReservationOutcomeStatus.RESERVED
    assert second.status is ReservationOutcomeStatus.NOT_RESERVED
    assert second.reason_codes == (
        ReservationReasonCode.OPEN_RISK_ENVELOPE_EXCEEDED,
        ReservationReasonCode.GROSS_EXPOSURE_ENVELOPE_EXCEEDED,
    )


def test_ledger_snapshot_exposes_per_crew_reserved_and_committed_usage() -> None:
    result = ledger()
    reserved = result.reserve(
        request("req-r", "crew-a", capital="10", risk="1", gross="20")
    )
    committed = result.reserve(
        request("req-c", "crew-a", capital="15", risk="2", gross="30")
    )
    assert reserved.reservation is not None
    assert committed.reservation is not None
    result.commit(
        committed.reservation.reservation_id,
        committed_at=NOW + timedelta(seconds=1),
        commit_ref="paper-order:crew-a",
    )

    usage = result.snapshot().crew_usage[0]
    assert usage.system_id == "crew-a"
    assert usage.reserved_capital_amount == Decimal("10")
    assert usage.committed_capital_amount == Decimal("15")
    assert usage.active_capital_amount == Decimal("25")
    assert usage.active_open_risk_amount == Decimal("3")
    assert usage.active_gross_exposure_amount == Decimal("50")


def test_global_master_capital_prevents_double_spend_across_overlapping_envelopes() -> None:
    result = ledger()
    first = result.reserve(request("req-a", "crew-a", capital="60", risk="1", gross="10"))
    second = result.reserve(request("req-b", "crew-b", capital="60", risk="1", gross="10"))

    assert first.status is ReservationOutcomeStatus.RESERVED
    assert second.status is ReservationOutcomeStatus.NOT_RESERVED
    assert second.reason_codes == (ReservationReasonCode.MASTER_CAPITAL_EXCEEDED,)
    assert result.snapshot().active_capital_amount == Decimal("60")


def test_unknown_crew_fails_closed_without_mutating_capacity() -> None:
    result = ledger()
    attempt = result.reserve(request("req-x", "crew-x", capital="10", risk="1", gross="10"))

    assert attempt.status is ReservationOutcomeStatus.NOT_RESERVED
    assert attempt.reason_codes == (ReservationReasonCode.UNKNOWN_CREW,)
    assert result.records() == ()


def test_same_request_is_idempotent_and_does_not_double_reserve() -> None:
    result = ledger()
    item = request("req-1", "crew-a", capital="20", risk="2", gross="40")

    first = result.reserve(item)
    second = result.reserve(item)

    assert first is second
    assert len(result.records()) == 1
    assert result.snapshot().active_capital_amount == Decimal("20")


def test_same_request_id_with_different_payload_is_rejected() -> None:
    result = ledger()
    result.reserve(request("req-1", "crew-a", capital="20"))

    with pytest.raises(ReservationIdempotencyConflict, match="another payload"):
        result.reserve(request("req-1", "crew-a", capital="21"))


def test_denied_request_is_idempotent_even_after_capacity_is_released() -> None:
    result = ledger()
    first = result.reserve(request("req-a", "crew-a", capital="60", risk="1", gross="10"))
    denied_request = request("req-b", "crew-b", capital="60", risk="1", gross="10")
    denied = result.reserve(denied_request)
    assert first.reservation is not None
    result.release(
        first.reservation.reservation_id,
        released_at=NOW + timedelta(minutes=1),
        release_ref="cancel:req-a",
    )

    repeated = result.reserve(denied_request)
    assert repeated is denied
    assert repeated.status is ReservationOutcomeStatus.NOT_RESERVED
    assert result.snapshot().active_capital_amount == Decimal("0")


def test_commit_is_idempotent_and_keeps_capacity_consumed() -> None:
    result = ledger()
    attempt = result.reserve(request("req-1", "crew-a", capital="20"))
    assert attempt.reservation is not None

    committed = result.commit(
        attempt.reservation.reservation_id,
        committed_at=NOW + timedelta(seconds=1),
        commit_ref="paper-order:1",
    )
    repeated = result.commit(
        attempt.reservation.reservation_id,
        committed_at=NOW + timedelta(seconds=1),
        commit_ref="paper-order:1",
    )

    assert committed is repeated
    assert committed.status is ReservationRecordStatus.COMMITTED
    state = result.snapshot()
    assert state.reserved_capital_amount == Decimal("0")
    assert state.committed_capital_amount == Decimal("20")
    assert state.active_capital_amount == Decimal("20")


def test_release_from_reserved_or_committed_frees_capacity_and_is_idempotent() -> None:
    result = ledger()
    reserved = result.reserve(request("req-r", "crew-a", capital="20"))
    committed = result.reserve(request("req-c", "crew-b", capital="30"))
    assert reserved.reservation is not None
    assert committed.reservation is not None
    result.commit(
        committed.reservation.reservation_id,
        committed_at=NOW + timedelta(seconds=1),
        commit_ref="paper-order:2",
    )

    released_reserved = result.release(
        reserved.reservation.reservation_id,
        released_at=NOW + timedelta(seconds=2),
        release_ref="cancel:req-r",
    )
    released_committed = result.release(
        committed.reservation.reservation_id,
        released_at=NOW + timedelta(seconds=3),
        release_ref="position-close:2",
    )
    repeated = result.release(
        committed.reservation.reservation_id,
        released_at=NOW + timedelta(seconds=3),
        release_ref="position-close:2",
    )

    assert released_reserved.status is ReservationRecordStatus.RELEASED
    assert released_committed is repeated
    assert result.snapshot().available_capital_amount == Decimal("100")


def test_transition_retries_with_different_metadata_fail_closed() -> None:
    result = ledger()
    attempt = result.reserve(request("req-1", "crew-a"))
    assert attempt.reservation is not None
    reservation_id = attempt.reservation.reservation_id
    result.commit(
        reservation_id,
        committed_at=NOW + timedelta(seconds=1),
        commit_ref="paper-order:1",
    )

    with pytest.raises(ReservationStateTransitionError, match="different metadata"):
        result.commit(
            reservation_id,
            committed_at=NOW + timedelta(seconds=2),
            commit_ref="paper-order:other",
        )

    result.release(
        reservation_id,
        released_at=NOW + timedelta(seconds=3),
        release_ref="position-close:1",
    )
    with pytest.raises(ReservationStateTransitionError, match="different metadata"):
        result.release(
            reservation_id,
            released_at=NOW + timedelta(seconds=4),
            release_ref="position-close:other",
        )


def test_released_reservation_cannot_be_committed_again() -> None:
    result = ledger()
    attempt = result.reserve(request("req-1", "crew-a"))
    assert attempt.reservation is not None
    result.release(
        attempt.reservation.reservation_id,
        released_at=NOW + timedelta(seconds=1),
        release_ref="cancel:req-1",
    )

    with pytest.raises(ReservationStateTransitionError, match="cannot be committed"):
        result.commit(
            attempt.reservation.reservation_id,
            committed_at=NOW + timedelta(seconds=2),
            commit_ref="paper-order:late",
        )


def test_reservation_ids_and_ledger_fingerprints_are_deterministic() -> None:
    first = ledger()
    second = ledger()
    request_value = request("req-1", "crew-a", capital="20", risk="2", gross="40")

    first_result = first.reserve(request_value)
    second_result = second.reserve(request_value)
    assert first_result.reservation is not None
    assert second_result.reservation is not None
    assert first_result.reservation.reservation_id == second_result.reservation.reservation_id
    assert first_result.fingerprint_sha256 == second_result.fingerprint_sha256
    assert first.snapshot().fingerprint_sha256 == second.snapshot().fingerprint_sha256


def test_reservation_records_are_immutable_and_have_no_execution_authority() -> None:
    result = ledger().reserve(request("req-1", "crew-a"))
    assert result.reservation is not None
    record = result.reservation

    assert record.risk_authority is False
    assert record.admission_authority is False
    assert record.live_authority is False
    with pytest.raises(FrozenInstanceError):
        record.status = ReservationRecordStatus.COMMITTED  # type: ignore[misc]
