from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.portfolio import (
    AllocationEnvelopeStatus,
    CrewAllocationEnvelope,
    CrewExposureSnapshot,
    MasterArbitrationBatchStatus,
    MasterArbitrationOrderStrategy,
    MasterArbitrationPolicySource,
    MasterArbitrationPolicyStatus,
    MasterCapitalSnapshot,
    MasterReservationLedger,
    PortfolioMemberRef,
    ReservationRequest,
    SnapshotDataStatus,
    build_master_allocation_policy,
    build_master_arbitration_batch,
    build_master_arbitration_policy,
    build_master_portfolio_snapshot,
    build_master_risk_gate_candidate,
)
from app.trading.risk.models import RiskDecision, RiskDecisionStatus, RiskReasonCode

OPENED_AT = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)
RISK_AT = datetime(2026, 9, 9, 22, 10, tzinfo=UTC)
REQUESTED_AT = datetime(2026, 9, 9, 22, 20, tzinfo=UTC)
BATCH_AT = datetime(2026, 9, 9, 22, 30, tzinfo=UTC)


def member(system_id: str) -> PortfolioMemberRef:
    return PortfolioMemberRef(system_id=system_id, membership_ref=f"registry:{system_id}")


def members() -> tuple[PortfolioMemberRef, ...]:
    return (member("crew-a"), member("crew-b"))


def envelope(system_id: str) -> CrewAllocationEnvelope:
    return CrewAllocationEnvelope(
        system_id=system_id,
        status=AllocationEnvelopeStatus.CONFIGURED,
        capital_ceiling_amount=Decimal("100"),
        open_risk_ceiling_amount=Decimal("50"),
        gross_exposure_ceiling_amount=Decimal("500"),
    )


def allocation_policy(*, master_portfolio_id: str = "master-main"):
    return build_master_allocation_policy(
        master_portfolio_id=master_portfolio_id,
        policy_id="static-v1",
        members=members(),
        envelopes=(envelope("crew-a"), envelope("crew-b")),
        source_ref="operator-config:static-v1",
    )


def opening_snapshot(*, master_portfolio_id: str = "master-main"):
    capital = MasterCapitalSnapshot(
        master_portfolio_id=master_portfolio_id,
        observed_at=OPENED_AT,
        status=SnapshotDataStatus.AVAILABLE,
        source="MASTER_ACCOUNT_FIXTURE",
        equity=Decimal("200"),
        cash_balance=Decimal("200"),
        day_start_equity=Decimal("200"),
        equity_peak=Decimal("200"),
        source_ref="fixture:capital",
    )
    exposures = tuple(
        CrewExposureSnapshot(
            system_id=item.system_id,
            observed_at=OPENED_AT,
            status=SnapshotDataStatus.AVAILABLE,
            source="SYSTEM_EXPOSURE_FIXTURE",
            open_positions=0,
            gross_exposure_amount=Decimal("0"),
            open_risk_amount=Decimal("0"),
            source_ref=f"fixture:{item.system_id}",
        )
        for item in members()
    )
    return build_master_portfolio_snapshot(
        master_capital=capital,
        members=members(),
        crew_exposures=exposures,
    )


def ledger_and_policy():
    policy = allocation_policy()
    ledger = MasterReservationLedger(policy=policy, opening_snapshot=opening_snapshot())
    return ledger, policy


def arbitration_policy(policy, *, configured: bool = True):
    if configured:
        return build_master_arbitration_policy(
            master_portfolio_id="master-main",
            arbitration_policy_id="fifo-v1",
            allocation_policy_fingerprint_sha256=policy.fingerprint_sha256,
            order_strategy=MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST,
            source_ref="operator-config:fifo-v1",
        )
    return build_master_arbitration_policy(
        master_portfolio_id="master-main",
        arbitration_policy_id="fifo-v1",
        allocation_policy_fingerprint_sha256=policy.fingerprint_sha256,
        reason_code="NOT_CONFIGURED_BY_OPERATOR",
        source_ref="operator-config:fifo-v1",
    )


def local_decision(
    *,
    proposal_id: str,
    risk: str = "3",
    gross: str = "50",
    created_at: datetime = RISK_AT,
    status: RiskDecisionStatus = RiskDecisionStatus.APPROVED,
):
    if status is RiskDecisionStatus.REJECTED:
        return RiskDecision(
            proposal_id=proposal_id,
            status=status,
            reason_codes=(RiskReasonCode.MAX_PORTFOLIO_RISK,),
            created_at=created_at,
        )
    return RiskDecision(
        proposal_id=proposal_id,
        status=status,
        reason_codes=(RiskReasonCode.APPROVED,),
        approved_quantity=Decimal("2"),
        approved_risk_amount=Decimal(risk),
        approved_notional=Decimal(gross),
        created_at=created_at,
    )


def reserve_candidate(
    ledger: MasterReservationLedger,
    *,
    system_id: str,
    proposal_id: str,
    requested_at: datetime,
    request_id: str | None = None,
    risk: str = "3",
    gross: str = "50",
    request_ref: str | None = None,
):
    decision = local_decision(proposal_id=proposal_id, risk=risk, gross=gross)
    result = ledger.reserve(
        ReservationRequest(
            request_id=request_id or f"request:{system_id}:{proposal_id}",
            system_id=system_id,
            requested_at=requested_at,
            capital_amount=Decimal("20"),
            open_risk_amount=Decimal(risk),
            gross_exposure_amount=Decimal(gross),
            request_ref=proposal_id if request_ref is None else request_ref,
        )
    )
    assert result.reservation is not None
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id=system_id,
        local_risk_decision=decision,
        reservation_id=result.reservation.reservation_id,
    )
    return candidate, result.reservation


def two_candidate_context():
    ledger, allocation = ledger_and_policy()
    later, _ = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id="proposal-a",
        requested_at=REQUESTED_AT + timedelta(seconds=2),
    )
    earlier, _ = reserve_candidate(
        ledger,
        system_id="crew-b",
        proposal_id="proposal-b",
        requested_at=REQUESTED_AT,
    )
    return ledger, arbitration_policy(allocation), earlier, later


def test_configured_policy_requires_explicit_fifo_strategy() -> None:
    _, allocation = ledger_and_policy()
    policy = arbitration_policy(allocation)

    assert policy.status is MasterArbitrationPolicyStatus.CONFIGURED
    assert policy.order_strategy is MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST
    assert policy.source is MasterArbitrationPolicySource.OPERATOR_CONFIGURATION
    assert policy.reason_code is None


def test_policy_has_no_implicit_default_strategy() -> None:
    _, allocation = ledger_and_policy()

    with pytest.raises(ValueError, match="requires reason_code"):
        build_master_arbitration_policy(
            master_portfolio_id="master-main",
            arbitration_policy_id="fifo-v1",
            allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        )


def test_not_configured_policy_carries_no_strategy() -> None:
    _, allocation = ledger_and_policy()
    policy = arbitration_policy(allocation, configured=False)

    assert policy.status is MasterArbitrationPolicyStatus.NOT_CONFIGURED
    assert policy.order_strategy is None
    assert policy.reason_code == "NOT_CONFIGURED_BY_OPERATOR"


def test_configured_policy_rejects_reason_code() -> None:
    _, allocation = ledger_and_policy()

    with pytest.raises(ValueError, match="cannot carry reason_code"):
        build_master_arbitration_policy(
            master_portfolio_id="master-main",
            arbitration_policy_id="fifo-v1",
            allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
            order_strategy=MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST,
            reason_code="SHOULD_NOT_EXIST",
        )


def test_policy_is_immutable_and_authority_free() -> None:
    _, allocation = ledger_and_policy()
    policy = arbitration_policy(allocation)

    with pytest.raises(FrozenInstanceError):
        policy.status = MasterArbitrationPolicyStatus.NOT_CONFIGURED  # type: ignore[misc]

    assert policy.adaptive_ranking is False
    assert policy.agent_influence is False
    assert policy.risk_authority is False
    assert policy.admission_authority is False
    assert policy.reservation_mutation is False
    assert policy.broker_authority is False
    assert policy.registry_mutation is False
    assert policy.live_authority is False
    assert policy.auto_execute is False


def test_policy_fingerprint_is_stable() -> None:
    _, allocation = ledger_and_policy()

    assert arbitration_policy(allocation) == arbitration_policy(allocation)


def test_batch_orders_by_reservation_request_time_not_input_order() -> None:
    ledger, policy, earlier, later = two_candidate_context()

    batch = build_master_arbitration_batch(
        policy=policy,
        candidates=(later, earlier),
        ledger_snapshot=ledger.snapshot(),
        created_at=BATCH_AT,
    )

    assert tuple(entry.proposal_id for entry in batch.entries) == (
        "proposal-b",
        "proposal-a",
    )
    assert tuple(entry.rank for entry in batch.entries) == (1, 2)


def test_fifo_tie_breaker_uses_system_id() -> None:
    ledger, allocation = ledger_and_policy()
    candidate_b, _ = reserve_candidate(
        ledger,
        system_id="crew-b",
        proposal_id="proposal-b",
        requested_at=REQUESTED_AT,
    )
    candidate_a, _ = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id="proposal-a",
        requested_at=REQUESTED_AT,
    )

    batch = build_master_arbitration_batch(
        policy=arbitration_policy(allocation),
        candidates=(candidate_b, candidate_a),
        ledger_snapshot=ledger.snapshot(),
        created_at=BATCH_AT,
    )

    assert tuple(entry.system_id for entry in batch.entries) == ("crew-a", "crew-b")


def test_fifo_tie_breaker_uses_proposal_id_within_same_system() -> None:
    ledger, allocation = ledger_and_policy()
    candidate_z, _ = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id="proposal-z",
        requested_at=REQUESTED_AT,
    )
    candidate_a, _ = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id="proposal-a",
        requested_at=REQUESTED_AT,
    )

    batch = build_master_arbitration_batch(
        policy=arbitration_policy(allocation),
        candidates=(candidate_z, candidate_a),
        ledger_snapshot=ledger.snapshot(),
        created_at=BATCH_AT,
    )

    assert tuple(entry.proposal_id for entry in batch.entries) == (
        "proposal-a",
        "proposal-z",
    )


def test_batch_is_stable_regardless_of_candidate_input_order() -> None:
    ledger, policy, earlier, later = two_candidate_context()
    snapshot = ledger.snapshot()

    first = build_master_arbitration_batch(
        policy=policy,
        candidates=(earlier, later),
        ledger_snapshot=snapshot,
        created_at=BATCH_AT,
    )
    second = build_master_arbitration_batch(
        policy=policy,
        candidates=(later, earlier),
        ledger_snapshot=snapshot,
        created_at=BATCH_AT,
    )

    assert first == second
    assert first.fingerprint_sha256 == second.fingerprint_sha256
    assert first.batch_id == second.batch_id


def test_batch_binds_policy_and_source_ledger() -> None:
    ledger, policy, earlier, later = two_candidate_context()
    snapshot = ledger.snapshot()

    batch = build_master_arbitration_batch(
        policy=policy,
        candidates=(earlier, later),
        ledger_snapshot=snapshot,
        created_at=BATCH_AT,
    )

    assert batch.status is MasterArbitrationBatchStatus.READY
    assert batch.arbitration_policy_fingerprint_sha256 == policy.fingerprint_sha256
    assert (
        batch.allocation_policy_fingerprint_sha256
        == snapshot.policy_fingerprint_sha256
    )
    assert batch.source_ledger_fingerprint_sha256 == snapshot.fingerprint_sha256


def test_batch_requires_configured_policy() -> None:
    ledger, allocation = ledger_and_policy()
    candidate, _ = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id="proposal-a",
        requested_at=REQUESTED_AT,
    )

    with pytest.raises(ValueError, match="must be CONFIGURED"):
        build_master_arbitration_batch(
            policy=arbitration_policy(allocation, configured=False),
            candidates=(candidate,),
            ledger_snapshot=ledger.snapshot(),
            created_at=BATCH_AT,
        )


def test_batch_requires_at_least_one_candidate() -> None:
    ledger, allocation = ledger_and_policy()

    with pytest.raises(ValueError, match="at least one candidate"):
        build_master_arbitration_batch(
            policy=arbitration_policy(allocation),
            candidates=(),
            ledger_snapshot=ledger.snapshot(),
            created_at=BATCH_AT,
        )


def test_single_candidate_batch_is_allowed_without_invented_minimum() -> None:
    ledger, allocation = ledger_and_policy()
    candidate, _ = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id="proposal-a",
        requested_at=REQUESTED_AT,
    )

    batch = build_master_arbitration_batch(
        policy=arbitration_policy(allocation),
        candidates=(candidate,),
        ledger_snapshot=ledger.snapshot(),
        created_at=BATCH_AT,
    )

    assert len(batch.entries) == 1
    assert batch.entries[0].rank == 1


def test_batch_rejects_candidate_from_another_master_portfolio() -> None:
    ledger, allocation = ledger_and_policy()
    decision = local_decision(proposal_id="proposal-a")
    reserved = ledger.reserve(
        ReservationRequest(
            request_id="request-a",
            system_id="crew-a",
            requested_at=REQUESTED_AT,
            capital_amount=Decimal("20"),
            open_risk_amount=Decimal("3"),
            gross_exposure_amount=Decimal("50"),
            request_ref="proposal-a",
        )
    )
    assert reserved.reservation is not None
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-other",
        system_id="crew-a",
        local_risk_decision=decision,
        reservation_id=reserved.reservation.reservation_id,
    )

    with pytest.raises(ValueError, match="policy Master Portfolio"):
        build_master_arbitration_batch(
            policy=arbitration_policy(allocation),
            candidates=(candidate,),
            ledger_snapshot=ledger.snapshot(),
            created_at=BATCH_AT,
        )


def test_batch_rejects_ledger_from_different_allocation_policy() -> None:
    ledger, allocation = ledger_and_policy()
    candidate, _ = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id="proposal-a",
        requested_at=REQUESTED_AT,
    )
    other_allocation = build_master_allocation_policy(
        master_portfolio_id="master-main",
        policy_id="static-v2",
        members=members(),
        envelopes=(envelope("crew-a"), envelope("crew-b")),
        source_ref="operator-config:static-v2",
    )

    with pytest.raises(ValueError, match="different allocation policies"):
        build_master_arbitration_batch(
            policy=arbitration_policy(other_allocation),
            candidates=(candidate,),
            ledger_snapshot=ledger.snapshot(),
            created_at=BATCH_AT,
        )


def test_batch_rejects_locally_rejected_candidate() -> None:
    ledger, allocation = ledger_and_policy()
    rejected = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(
            proposal_id="proposal-rejected",
            status=RiskDecisionStatus.REJECTED,
        ),
        reservation_id=None,
    )

    with pytest.raises(ValueError, match="locally authorized"):
        build_master_arbitration_batch(
            policy=arbitration_policy(allocation),
            candidates=(rejected,),
            ledger_snapshot=ledger.snapshot(),
            created_at=BATCH_AT,
        )


def test_batch_rejects_missing_reservation() -> None:
    ledger, allocation = ledger_and_policy()
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=local_decision(proposal_id="proposal-a"),
        reservation_id="reservation:missing",
    )

    with pytest.raises(ValueError, match="missing from ledger"):
        build_master_arbitration_batch(
            policy=arbitration_policy(allocation),
            candidates=(candidate,),
            ledger_snapshot=ledger.snapshot(),
            created_at=BATCH_AT,
        )


def test_batch_rejects_reservation_that_is_not_reserved() -> None:
    ledger, allocation = ledger_and_policy()
    candidate, reservation = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id="proposal-a",
        requested_at=REQUESTED_AT,
    )
    ledger.commit(
        reservation.reservation_id,
        committed_at=BATCH_AT,
        commit_ref="decision:already-committed",
    )

    with pytest.raises(ValueError, match="must still be RESERVED"):
        build_master_arbitration_batch(
            policy=arbitration_policy(allocation),
            candidates=(candidate,),
            ledger_snapshot=ledger.snapshot(),
            created_at=BATCH_AT + timedelta(seconds=1),
        )


def test_batch_rejects_candidate_reservation_payload_mismatch() -> None:
    ledger, allocation = ledger_and_policy()
    candidate, _ = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id="proposal-a",
        requested_at=REQUESTED_AT,
        request_ref="proposal-other",
    )

    with pytest.raises(ValueError, match="does not match"):
        build_master_arbitration_batch(
            policy=arbitration_policy(allocation),
            candidates=(candidate,),
            ledger_snapshot=ledger.snapshot(),
            created_at=BATCH_AT,
        )


def test_batch_rejects_duplicate_candidate() -> None:
    ledger, allocation = ledger_and_policy()
    candidate, _ = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id="proposal-a",
        requested_at=REQUESTED_AT,
    )

    with pytest.raises(ValueError, match="fingerprints must be unique"):
        build_master_arbitration_batch(
            policy=arbitration_policy(allocation),
            candidates=(candidate, candidate),
            ledger_snapshot=ledger.snapshot(),
            created_at=BATCH_AT,
        )


def test_batch_cannot_precede_latest_reservation_request() -> None:
    ledger, allocation = ledger_and_policy()
    candidate, _ = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id="proposal-a",
        requested_at=REQUESTED_AT,
    )

    with pytest.raises(ValueError, match="cannot precede"):
        build_master_arbitration_batch(
            policy=arbitration_policy(allocation),
            candidates=(candidate,),
            ledger_snapshot=ledger.snapshot(),
            created_at=REQUESTED_AT - timedelta(seconds=1),
        )


def test_batch_is_immutable_and_has_no_operational_authority() -> None:
    ledger, policy, earlier, later = two_candidate_context()
    batch = build_master_arbitration_batch(
        policy=policy,
        candidates=(earlier, later),
        ledger_snapshot=ledger.snapshot(),
        created_at=BATCH_AT,
    )

    with pytest.raises(FrozenInstanceError):
        batch.batch_id = "changed"  # type: ignore[misc]

    assert batch.mutation_applied is False
    assert batch.adaptive_ranking is False
    assert batch.agent_influence is False
    assert batch.risk_authority is False
    assert batch.admission_authority is False
    assert batch.reservation_mutation is False
    assert batch.broker_authority is False
    assert batch.registry_mutation is False
    assert batch.live_authority is False
    assert batch.auto_execute is False


def test_batch_has_no_concurrency_window_or_score_fields() -> None:
    ledger, policy, earlier, later = two_candidate_context()
    batch = build_master_arbitration_batch(
        policy=policy,
        candidates=(earlier, later),
        ledger_snapshot=ledger.snapshot(),
        created_at=BATCH_AT,
    )

    assert not hasattr(policy, "concurrency_window")
    assert not hasattr(policy, "score_weights")
    assert not hasattr(batch, "concurrency_window")
    assert not hasattr(batch.entries[0], "score")
    assert not hasattr(batch.entries[0], "reputation")


def test_batch_constructor_rejects_reordered_entries() -> None:
    ledger, policy, earlier, later = two_candidate_context()
    batch = build_master_arbitration_batch(
        policy=policy,
        candidates=(earlier, later),
        ledger_snapshot=ledger.snapshot(),
        created_at=BATCH_AT,
    )
    reordered = tuple(reversed(batch.entries))

    with pytest.raises(ValueError, match="ranks"):
        replace(batch, entries=reordered)


def test_batch_fingerprint_detects_source_ledger_tampering() -> None:
    ledger, policy, earlier, later = two_candidate_context()
    batch = build_master_arbitration_batch(
        policy=policy,
        candidates=(earlier, later),
        ledger_snapshot=ledger.snapshot(),
        created_at=BATCH_AT,
    )

    with pytest.raises(ValueError, match="fingerprint does not match"):
        replace(
            batch,
            source_ledger_fingerprint_sha256="f" * 64,
        )
