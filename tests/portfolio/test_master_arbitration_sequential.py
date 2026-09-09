from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.portfolio import (
    AllocationEnvelopeStatus,
    CrewAllocationEnvelope,
    CrewExposureSnapshot,
    MasterArbitrationOrderStrategy,
    MasterCapitalSnapshot,
    MasterReservationLedger,
    MasterRiskGateDecisionStatus,
    MasterRiskGatePolicyStatus,
    MasterRiskGateReasonCode,
    MasterSequentialArbitrationStatus,
    PortfolioMemberRef,
    ReservationRecordStatus,
    ReservationRequest,
    SnapshotDataStatus,
    arbitrate_master_batch_sequentially,
    build_master_allocation_policy,
    build_master_arbitration_batch,
    build_master_arbitration_policy,
    build_master_portfolio_snapshot,
    build_master_risk_gate_candidate,
    build_master_risk_gate_policy,
)
from app.trading.risk.models import RiskDecision, RiskDecisionStatus, RiskReasonCode

OPENED_AT = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)
RISK_AT = datetime(2026, 9, 9, 22, 10, tzinfo=UTC)
REQUESTED_AT = datetime(2026, 9, 9, 22, 20, tzinfo=UTC)
BATCH_AT = datetime(2026, 9, 9, 22, 30, tzinfo=UTC)
EVALUATED_AT = datetime(2026, 9, 9, 22, 40, tzinfo=UTC)


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


def portfolio_snapshot(*, observed_at: datetime = EVALUATED_AT):
    capital = MasterCapitalSnapshot(
        master_portfolio_id="master-main",
        observed_at=observed_at,
        status=SnapshotDataStatus.AVAILABLE,
        source="MASTER_ACCOUNT_FIXTURE",
        equity=Decimal("200"),
        cash_balance=Decimal("200"),
        day_start_equity=Decimal("200"),
        equity_peak=Decimal("200"),
        source_ref="fixture:capital-current",
    )
    exposures = tuple(
        CrewExposureSnapshot(
            system_id=item.system_id,
            observed_at=observed_at,
            status=SnapshotDataStatus.AVAILABLE,
            source="SYSTEM_EXPOSURE_FIXTURE",
            open_positions=0,
            gross_exposure_amount=Decimal("0"),
            open_risk_amount=Decimal("0"),
            source_ref=f"fixture:current:{item.system_id}",
        )
        for item in members()
    )
    return build_master_portfolio_snapshot(
        master_capital=capital,
        members=members(),
        crew_exposures=exposures,
    )


def local_decision(*, proposal_id: str, risk: str = "3", gross: str = "50"):
    return RiskDecision(
        proposal_id=proposal_id,
        status=RiskDecisionStatus.APPROVED,
        reason_codes=(RiskReasonCode.APPROVED,),
        approved_quantity=Decimal("2"),
        approved_risk_amount=Decimal(risk),
        approved_notional=Decimal(gross),
        created_at=RISK_AT,
    )


def reserve_candidate(
    ledger: MasterReservationLedger,
    *,
    system_id: str,
    proposal_id: str,
    requested_at: datetime,
    risk: str = "3",
    gross: str = "50",
):
    decision = local_decision(proposal_id=proposal_id, risk=risk, gross=gross)
    result = ledger.reserve(
        ReservationRequest(
            request_id=f"request:{system_id}:{proposal_id}",
            system_id=system_id,
            requested_at=requested_at,
            capital_amount=Decimal("20"),
            open_risk_amount=Decimal(risk),
            gross_exposure_amount=Decimal(gross),
            request_ref=proposal_id,
        )
    )
    assert result.reservation is not None
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id=system_id,
        local_risk_decision=decision,
        reservation_id=result.reservation.reservation_id,
    )
    return candidate


def context(*, gate_risk: str = "100", gate_gross: str = "1000", configured=True):
    allocation = allocation_policy()
    opening = opening_snapshot()
    ledger = MasterReservationLedger(policy=allocation, opening_snapshot=opening)
    later = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id="proposal-a",
        requested_at=REQUESTED_AT + timedelta(seconds=2),
    )
    earlier = reserve_candidate(
        ledger,
        system_id="crew-b",
        proposal_id="proposal-b",
        requested_at=REQUESTED_AT,
    )
    arbitration_policy = build_master_arbitration_policy(
        master_portfolio_id="master-main",
        arbitration_policy_id="fifo-v1",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        order_strategy=MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST,
        source_ref="operator-config:fifo-v1",
    )
    batch = build_master_arbitration_batch(
        policy=arbitration_policy,
        candidates=(later, earlier),
        ledger_snapshot=ledger.snapshot(),
        created_at=BATCH_AT,
    )
    if configured:
        gate_policy = build_master_risk_gate_policy(
            master_portfolio_id="master-main",
            gate_policy_id="master-gate-v1",
            allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
            max_total_open_risk_amount=Decimal(gate_risk),
            max_total_gross_exposure_amount=Decimal(gate_gross),
            source_ref="operator-config:master-gate-v1",
        )
    else:
        gate_policy = build_master_risk_gate_policy(
            master_portfolio_id="master-main",
            gate_policy_id="master-gate-v1",
            allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
            reason_code="NOT_CONFIGURED_BY_OPERATOR",
            source_ref="operator-config:master-gate-v1",
        )
    return {
        "allocation": allocation,
        "opening": opening,
        "portfolio": portfolio_snapshot(),
        "ledger": ledger,
        "earlier": earlier,
        "later": later,
        "arbitration_policy": arbitration_policy,
        "batch": batch,
        "gate_policy": gate_policy,
    }


def run(ctx, *, candidates=None, evaluated_at=EVALUATED_AT):
    return arbitrate_master_batch_sequentially(
        arbitration_policy=ctx["arbitration_policy"],
        batch=ctx["batch"],
        allocation_policy=ctx["allocation"],
        gate_policy=ctx["gate_policy"],
        opening_snapshot=ctx["opening"],
        portfolio_snapshot=ctx["portfolio"],
        ledger=ctx["ledger"],
        candidates=candidates or (ctx["later"], ctx["earlier"]),
        evaluated_at=evaluated_at,
    )


def test_generous_gate_admits_and_commits_every_candidate() -> None:
    ctx = context()

    result = run(ctx)

    assert result.status is MasterSequentialArbitrationStatus.COMPLETED
    assert [item.decision_status for item in result.outcomes] == [
        MasterRiskGateDecisionStatus.ADMIT,
        MasterRiskGateDecisionStatus.ADMIT,
    ]
    assert all(
        ctx["ledger"].get(item.reservation_id).status is ReservationRecordStatus.COMMITTED
        for item in result.outcomes
    )


def test_fifo_batch_order_drives_sequential_outcome_order() -> None:
    ctx = context()

    result = run(ctx, candidates=(ctx["later"], ctx["earlier"]))

    assert [item.system_id for item in result.outcomes] == ["crew-b", "crew-a"]
    assert [item.rank for item in result.outcomes] == [1, 2]


def test_candidate_argument_order_does_not_change_batch_order() -> None:
    left = context()
    right = context()

    left_result = run(left, candidates=(left["later"], left["earlier"]))
    right_result = run(right, candidates=(right["earlier"], right["later"]))

    assert left_result.fingerprint_sha256 == right_result.fingerprint_sha256


def test_released_first_candidate_changes_state_seen_by_second_candidate() -> None:
    ctx = context(gate_risk="3")

    result = run(ctx)

    first, second = result.outcomes
    assert first.decision_status is MasterRiskGateDecisionStatus.REJECT
    assert MasterRiskGateReasonCode.MASTER_OPEN_RISK_LIMIT_EXCEEDED in first.decision_reason_codes
    assert second.decision_status is MasterRiskGateDecisionStatus.ADMIT
    assert first.ledger_after_fingerprint_sha256 == second.ledger_before_fingerprint_sha256
    assert ctx["ledger"].get(first.reservation_id).status is ReservationRecordStatus.RELEASED
    assert ctx["ledger"].get(second.reservation_id).status is ReservationRecordStatus.COMMITTED


def test_fifo_is_evaluation_order_not_hidden_priority_override() -> None:
    ctx = context(gate_risk="3")

    result = run(ctx)

    assert result.outcomes[0].system_id == "crew-b"
    assert result.outcomes[0].decision_status is MasterRiskGateDecisionStatus.REJECT
    assert result.outcomes[1].system_id == "crew-a"
    assert result.outcomes[1].decision_status is MasterRiskGateDecisionStatus.ADMIT


def test_not_configured_gate_rejects_and_releases_every_reservation() -> None:
    ctx = context(configured=False)
    assert ctx["gate_policy"].status is MasterRiskGatePolicyStatus.NOT_CONFIGURED

    result = run(ctx)

    assert all(
        item.decision_status is MasterRiskGateDecisionStatus.REJECT
        for item in result.outcomes
    )
    assert all(
        MasterRiskGateReasonCode.GATE_POLICY_NOT_CONFIGURED in item.decision_reason_codes
        for item in result.outcomes
    )
    assert all(
        ctx["ledger"].get(item.reservation_id).status is ReservationRecordStatus.RELEASED
        for item in result.outcomes
    )


def test_result_exposes_reservation_mutation_but_no_risk_or_execution_authority() -> None:
    ctx = context()

    result = run(ctx)

    assert result.mutation_applied is True
    assert result.reservation_mutation is True
    assert result.risk_authority is False
    assert result.admission_authority is False
    assert result.local_risk_override is False
    assert result.resize_authority is False
    assert result.broker_authority is False
    assert result.registry_mutation is False
    assert result.live_authority is False
    assert result.auto_execute is False


def test_outcomes_are_authority_free_evidence() -> None:
    ctx = context()

    outcome = run(ctx).outcomes[0]

    assert outcome.risk_authority is False
    assert outcome.admission_authority is False
    assert outcome.local_risk_override is False
    assert outcome.resize_authority is False
    assert outcome.broker_authority is False
    assert outcome.registry_mutation is False
    assert outcome.live_authority is False
    assert outcome.auto_execute is False


def test_each_outcome_carries_receipt_and_gate_closure_fingerprints() -> None:
    ctx = context()

    result = run(ctx)

    assert all(len(item.admission_receipt_fingerprint_sha256) == 64 for item in result.outcomes)
    assert all(len(item.gate_closure_fingerprint_sha256) == 64 for item in result.outcomes)


def test_result_ledger_chain_is_contiguous() -> None:
    ctx = context()

    result = run(ctx)

    assert (
        result.initial_ledger_fingerprint_sha256
        == result.outcomes[0].ledger_before_fingerprint_sha256
    )
    assert (
        result.outcomes[0].ledger_after_fingerprint_sha256
        == result.outcomes[1].ledger_before_fingerprint_sha256
    )
    assert (
        result.final_ledger_fingerprint_sha256
        == result.outcomes[-1].ledger_after_fingerprint_sha256
    )


def test_stale_batch_source_ledger_fails_before_mutation() -> None:
    ctx = context()
    extra = reserve_candidate(
        ctx["ledger"],
        system_id="crew-a",
        proposal_id="proposal-extra",
        requested_at=REQUESTED_AT + timedelta(seconds=5),
        risk="1",
        gross="10",
    )
    before = ctx["ledger"].snapshot()

    with pytest.raises(ValueError, match="source ledger is stale"):
        run(ctx, candidates=(ctx["later"], ctx["earlier"]))

    assert extra.reservation_id is not None
    assert ctx["ledger"].snapshot().fingerprint_sha256 == before.fingerprint_sha256


def test_missing_candidate_fails_before_mutation() -> None:
    ctx = context()
    before = ctx["ledger"].snapshot()

    with pytest.raises(ValueError, match="candidate set must match"):
        run(ctx, candidates=(ctx["earlier"],))

    assert ctx["ledger"].snapshot().fingerprint_sha256 == before.fingerprint_sha256


def test_duplicate_candidate_fails_before_mutation() -> None:
    ctx = context()
    before = ctx["ledger"].snapshot()

    with pytest.raises(ValueError, match="candidates must be unique"):
        run(ctx, candidates=(ctx["earlier"], ctx["earlier"]))

    assert ctx["ledger"].snapshot().fingerprint_sha256 == before.fingerprint_sha256


def test_arbitration_cannot_precede_batch_creation() -> None:
    ctx = context()
    before = ctx["ledger"].snapshot()

    with pytest.raises(ValueError, match="cannot precede batch creation"):
        run(ctx, evaluated_at=BATCH_AT - timedelta(microseconds=1))

    assert ctx["ledger"].snapshot().fingerprint_sha256 == before.fingerprint_sha256


def test_arbitration_cannot_postdate_portfolio_observation() -> None:
    ctx = context()
    before = ctx["ledger"].snapshot()

    with pytest.raises(ValueError, match="cannot postdate portfolio observation"):
        run(ctx, evaluated_at=EVALUATED_AT + timedelta(microseconds=1))

    assert ctx["ledger"].snapshot().fingerprint_sha256 == before.fingerprint_sha256


def test_opening_snapshot_mismatch_fails_before_mutation() -> None:
    ctx = context()
    before = ctx["ledger"].snapshot()
    ctx["opening"] = build_master_portfolio_snapshot(
        master_capital=MasterCapitalSnapshot(
            master_portfolio_id="master-main",
            observed_at=OPENED_AT,
            status=SnapshotDataStatus.AVAILABLE,
            source="MASTER_ACCOUNT_FIXTURE",
            equity=Decimal("201"),
            cash_balance=Decimal("201"),
            day_start_equity=Decimal("201"),
            equity_peak=Decimal("201"),
            source_ref="fixture:other-capital",
        ),
        members=members(),
        crew_exposures=tuple(
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
        ),
    )

    with pytest.raises(ValueError, match="opening snapshot does not match ledger"):
        run(ctx)

    assert ctx["ledger"].snapshot().fingerprint_sha256 == before.fingerprint_sha256


def test_arbitration_policy_fingerprint_mismatch_fails_before_mutation() -> None:
    ctx = context()
    before = ctx["ledger"].snapshot()
    ctx["arbitration_policy"] = build_master_arbitration_policy(
        master_portfolio_id="master-main",
        arbitration_policy_id="fifo-v2",
        allocation_policy_fingerprint_sha256=ctx["allocation"].fingerprint_sha256,
        order_strategy=MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST,
        source_ref="operator-config:fifo-v2",
    )

    with pytest.raises(ValueError, match="does not bind to supplied arbitration policy"):
        run(ctx)

    assert ctx["ledger"].snapshot().fingerprint_sha256 == before.fingerprint_sha256


def test_gate_policy_allocation_provenance_mismatch_fails_before_mutation() -> None:
    ctx = context()
    before = ctx["ledger"].snapshot()
    other_allocation = build_master_allocation_policy(
        master_portfolio_id="master-main",
        policy_id="static-v2",
        members=members(),
        envelopes=(envelope("crew-a"), envelope("crew-b")),
        source_ref="operator-config:static-v2",
    )
    ctx["gate_policy"] = build_master_risk_gate_policy(
        master_portfolio_id="master-main",
        gate_policy_id="master-gate-v1",
        allocation_policy_fingerprint_sha256=other_allocation.fingerprint_sha256,
        max_total_open_risk_amount=Decimal("100"),
        max_total_gross_exposure_amount=Decimal("1000"),
    )

    with pytest.raises(ValueError, match="allocation policy provenance mismatch"):
        run(ctx)

    assert ctx["ledger"].snapshot().fingerprint_sha256 == before.fingerprint_sha256


def test_cross_master_gate_policy_fails_before_mutation() -> None:
    ctx = context()
    before = ctx["ledger"].snapshot()
    ctx["gate_policy"] = build_master_risk_gate_policy(
        master_portfolio_id="master-other",
        gate_policy_id="master-gate-v1",
        allocation_policy_fingerprint_sha256=ctx["allocation"].fingerprint_sha256,
        max_total_open_risk_amount=Decimal("100"),
        max_total_gross_exposure_amount=Decimal("1000"),
    )

    with pytest.raises(ValueError, match="multiple Master Portfolios"):
        run(ctx)

    assert ctx["ledger"].snapshot().fingerprint_sha256 == before.fingerprint_sha256


def test_completed_batch_cannot_be_replayed_on_already_mutated_ledger() -> None:
    ctx = context()
    run(ctx)
    after = ctx["ledger"].snapshot()

    with pytest.raises(ValueError, match="source ledger is stale"):
        run(ctx)

    assert ctx["ledger"].snapshot().fingerprint_sha256 == after.fingerprint_sha256


def test_result_is_deterministic_for_equivalent_contexts() -> None:
    left = context(gate_risk="3")
    right = context(gate_risk="3")

    left_result = run(left)
    right_result = run(right)

    assert left_result.run_id == right_result.run_id
    assert left_result.fingerprint_sha256 == right_result.fingerprint_sha256


def test_result_is_immutable() -> None:
    result = run(context())

    with pytest.raises(FrozenInstanceError):
        result.status = MasterSequentialArbitrationStatus.COMPLETED  # type: ignore[misc]


def test_outcome_is_immutable() -> None:
    outcome = run(context()).outcomes[0]

    with pytest.raises(FrozenInstanceError):
        outcome.rank = 99  # type: ignore[misc]


def test_result_rejects_tampered_fingerprint() -> None:
    result = run(context())

    with pytest.raises(ValueError, match="fingerprint does not match payload"):
        replace(result, fingerprint_sha256="0" * 64)


def test_outcome_rejects_tampered_fingerprint() -> None:
    outcome = run(context()).outcomes[0]

    with pytest.raises(ValueError, match="fingerprint does not match payload"):
        replace(outcome, fingerprint_sha256="0" * 64)


def test_single_candidate_batch_is_supported() -> None:
    allocation = allocation_policy()
    opening = opening_snapshot()
    ledger = MasterReservationLedger(policy=allocation, opening_snapshot=opening)
    candidate = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id="proposal-only",
        requested_at=REQUESTED_AT,
    )
    arbitration_policy = build_master_arbitration_policy(
        master_portfolio_id="master-main",
        arbitration_policy_id="fifo-v1",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        order_strategy=MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST,
    )
    batch = build_master_arbitration_batch(
        policy=arbitration_policy,
        candidates=(candidate,),
        ledger_snapshot=ledger.snapshot(),
        created_at=BATCH_AT,
    )
    gate_policy = build_master_risk_gate_policy(
        master_portfolio_id="master-main",
        gate_policy_id="master-gate-v1",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        max_total_open_risk_amount=Decimal("100"),
        max_total_gross_exposure_amount=Decimal("1000"),
    )

    result = arbitrate_master_batch_sequentially(
        arbitration_policy=arbitration_policy,
        batch=batch,
        allocation_policy=allocation,
        gate_policy=gate_policy,
        opening_snapshot=opening,
        portfolio_snapshot=portfolio_snapshot(),
        ledger=ledger,
        candidates=(candidate,),
        evaluated_at=EVALUATED_AT,
    )

    assert len(result.outcomes) == 1
    assert result.outcomes[0].decision_status is MasterRiskGateDecisionStatus.ADMIT
