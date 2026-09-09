from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.portfolio import (
    AllocationEnvelopeStatus,
    CrewAllocationEnvelope,
    CrewExposureSnapshot,
    MasterArbitrationClosureStatus,
    MasterArbitrationOrderStrategy,
    MasterCapitalSnapshot,
    MasterReservationLedger,
    MasterRiskGateDecisionStatus,
    MasterRiskGateReasonCode,
    MasterSequentialArbitrationOutcome,
    MasterSequentialArbitrationResult,
    PortfolioMemberRef,
    ReservationRecordStatus,
    ReservationRequest,
    SnapshotDataStatus,
    arbitrate_master_batch_sequentially,
    build_master_allocation_policy,
    build_master_arbitration_batch,
    build_master_arbitration_closure_seal,
    build_master_arbitration_policy,
    build_master_portfolio_snapshot,
    build_master_risk_gate_candidate,
    build_master_risk_gate_policy,
)
from app.services.backtest.ids import stable_digest
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


def allocation_policy(*, policy_id: str = "static-v1"):
    return build_master_allocation_policy(
        master_portfolio_id="master-main",
        policy_id=policy_id,
        members=members(),
        envelopes=(envelope("crew-a"), envelope("crew-b")),
        source_ref=f"operator-config:{policy_id}",
    )


def opening_snapshot():
    capital = MasterCapitalSnapshot(
        master_portfolio_id="master-main",
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


def portfolio_snapshot(*, source_suffix: str = "current"):
    capital = MasterCapitalSnapshot(
        master_portfolio_id="master-main",
        observed_at=EVALUATED_AT,
        status=SnapshotDataStatus.AVAILABLE,
        source="MASTER_ACCOUNT_FIXTURE",
        equity=Decimal("200"),
        cash_balance=Decimal("200"),
        day_start_equity=Decimal("200"),
        equity_peak=Decimal("200"),
        source_ref=f"fixture:capital:{source_suffix}",
    )
    exposures = tuple(
        CrewExposureSnapshot(
            system_id=item.system_id,
            observed_at=EVALUATED_AT,
            status=SnapshotDataStatus.AVAILABLE,
            source="SYSTEM_EXPOSURE_FIXTURE",
            open_positions=0,
            gross_exposure_amount=Decimal("0"),
            open_risk_amount=Decimal("0"),
            source_ref=f"fixture:{source_suffix}:{item.system_id}",
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
    return build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id=system_id,
        local_risk_decision=decision,
        reservation_id=result.reservation.reservation_id,
    )


def context(
    *,
    gate_risk: str = "100",
    gate_gross: str = "1000",
    suffix: str = "",
    unrelated: bool = False,
    allocation_id: str = "static-v1",
):
    allocation = allocation_policy(policy_id=allocation_id)
    opening = opening_snapshot()
    ledger = MasterReservationLedger(policy=allocation, opening_snapshot=opening)
    later = reserve_candidate(
        ledger,
        system_id="crew-a",
        proposal_id=f"proposal-a{suffix}",
        requested_at=REQUESTED_AT + timedelta(seconds=2),
    )
    earlier = reserve_candidate(
        ledger,
        system_id="crew-b",
        proposal_id=f"proposal-b{suffix}",
        requested_at=REQUESTED_AT,
    )
    unrelated_id = None
    if unrelated:
        extra = ledger.reserve(
            ReservationRequest(
                request_id=f"request:extra{suffix}",
                system_id="crew-a",
                requested_at=REQUESTED_AT + timedelta(seconds=4),
                capital_amount=Decimal("5"),
                open_risk_amount=Decimal("1"),
                gross_exposure_amount=Decimal("10"),
                request_ref=f"proposal-extra{suffix}",
            )
        )
        assert extra.reservation is not None
        unrelated_id = extra.reservation.reservation_id

    arbitration_policy = build_master_arbitration_policy(
        master_portfolio_id="master-main",
        arbitration_policy_id=f"fifo-v1{suffix}",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        order_strategy=MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST,
        source_ref=f"operator-config:fifo-v1{suffix}",
    )
    batch = build_master_arbitration_batch(
        policy=arbitration_policy,
        candidates=(later, earlier),
        ledger_snapshot=ledger.snapshot(),
        created_at=BATCH_AT,
    )
    gate_policy = build_master_risk_gate_policy(
        master_portfolio_id="master-main",
        gate_policy_id=f"master-gate-v1{suffix}",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        max_total_open_risk_amount=Decimal(gate_risk),
        max_total_gross_exposure_amount=Decimal(gate_gross),
        source_ref=f"operator-config:master-gate-v1{suffix}",
    )
    return {
        "allocation": allocation,
        "opening": opening,
        "portfolio": portfolio_snapshot(source_suffix=f"current{suffix}"),
        "ledger": ledger,
        "earlier": earlier,
        "later": later,
        "arbitration_policy": arbitration_policy,
        "batch": batch,
        "gate_policy": gate_policy,
        "unrelated_id": unrelated_id,
    }


def execute(ctx):
    initial = ctx["ledger"].snapshot()
    result = arbitrate_master_batch_sequentially(
        arbitration_policy=ctx["arbitration_policy"],
        batch=ctx["batch"],
        allocation_policy=ctx["allocation"],
        gate_policy=ctx["gate_policy"],
        opening_snapshot=ctx["opening"],
        portfolio_snapshot=ctx["portfolio"],
        ledger=ctx["ledger"],
        candidates=(ctx["later"], ctx["earlier"]),
        evaluated_at=EVALUATED_AT,
    )
    return initial, result, ctx["ledger"].snapshot()


def seal(ctx, initial, result, final):
    return build_master_arbitration_closure_seal(
        arbitration_policy=ctx["arbitration_policy"],
        batch=ctx["batch"],
        allocation_policy=ctx["allocation"],
        gate_policy=ctx["gate_policy"],
        opening_snapshot=ctx["opening"],
        portfolio_snapshot=ctx["portfolio"],
        initial_ledger=initial,
        final_ledger=final,
        result=result,
    )


def forge_outcome(source: MasterSequentialArbitrationOutcome, **changes):
    values = {
        "rank": source.rank,
        "system_id": source.system_id,
        "proposal_id": source.proposal_id,
        "reservation_id": source.reservation_id,
        "candidate_fingerprint_sha256": source.candidate_fingerprint_sha256,
        "ledger_before_fingerprint_sha256": source.ledger_before_fingerprint_sha256,
        "decision_id": source.decision_id,
        "decision_status": source.decision_status,
        "decision_reason_codes": source.decision_reason_codes,
        "decision_fingerprint_sha256": source.decision_fingerprint_sha256,
        "admission_receipt_fingerprint_sha256": (
            source.admission_receipt_fingerprint_sha256
        ),
        "gate_closure_fingerprint_sha256": source.gate_closure_fingerprint_sha256,
        "ledger_after_fingerprint_sha256": source.ledger_after_fingerprint_sha256,
    }
    values.update(changes)
    payload = {
        "schema": "money-heist.master-sequential-arbitration-outcome.v1",
        "schema_version": "1.0",
        **values,
    }
    return MasterSequentialArbitrationOutcome(
        **values,
        fingerprint_sha256=stable_digest(payload),
    )


def forge_result(source: MasterSequentialArbitrationResult, **changes):
    values = {
        "master_portfolio_id": source.master_portfolio_id,
        "run_id": source.run_id,
        "batch_id": source.batch_id,
        "evaluated_at": source.evaluated_at,
        "status": source.status,
        "order_strategy": source.order_strategy,
        "arbitration_policy_fingerprint_sha256": (
            source.arbitration_policy_fingerprint_sha256
        ),
        "allocation_policy_fingerprint_sha256": (
            source.allocation_policy_fingerprint_sha256
        ),
        "gate_policy_fingerprint_sha256": source.gate_policy_fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": source.opening_snapshot_fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": (
            source.portfolio_snapshot_fingerprint_sha256
        ),
        "initial_ledger_fingerprint_sha256": source.initial_ledger_fingerprint_sha256,
        "final_ledger_fingerprint_sha256": source.final_ledger_fingerprint_sha256,
        "outcomes": source.outcomes,
    }
    values.update(changes)
    payload = {
        "schema": "money-heist.master-sequential-arbitration-result.v1",
        "schema_version": "1.0",
        **values,
        "outcomes": [
            {
                "schema": "money-heist.master-sequential-arbitration-outcome.v1",
                "schema_version": item.schema_version,
                "rank": item.rank,
                "system_id": item.system_id,
                "proposal_id": item.proposal_id,
                "reservation_id": item.reservation_id,
                "candidate_fingerprint_sha256": item.candidate_fingerprint_sha256,
                "ledger_before_fingerprint_sha256": item.ledger_before_fingerprint_sha256,
                "decision_id": item.decision_id,
                "decision_status": item.decision_status,
                "decision_reason_codes": item.decision_reason_codes,
                "decision_fingerprint_sha256": item.decision_fingerprint_sha256,
                "admission_receipt_fingerprint_sha256": (
                    item.admission_receipt_fingerprint_sha256
                ),
                "gate_closure_fingerprint_sha256": item.gate_closure_fingerprint_sha256,
                "ledger_after_fingerprint_sha256": item.ledger_after_fingerprint_sha256,
            }
            for item in values["outcomes"]
        ],
    }
    return MasterSequentialArbitrationResult(
        **values,
        fingerprint_sha256=stable_digest(payload),
    )


def test_seals_generous_two_admit_run() -> None:
    ctx = context()
    initial, result, final = execute(ctx)

    closed = seal(ctx, initial, result, final)

    assert closed.status is MasterArbitrationClosureStatus.SEALED
    assert closed.admitted_count == 2
    assert closed.rejected_count == 0
    assert closed.result_fingerprint_sha256 == result.fingerprint_sha256


def test_seals_mixed_reject_then_admit_run() -> None:
    ctx = context(gate_risk="3")
    initial, result, final = execute(ctx)

    closed = seal(ctx, initial, result, final)

    assert closed.admitted_count == 1
    assert closed.rejected_count == 1


def test_seal_is_deterministic() -> None:
    ctx = context()
    initial, result, final = execute(ctx)

    first = seal(ctx, initial, result, final)
    second = seal(ctx, initial, result, final)

    assert first == second
    assert first.closure_id == second.closure_id
    assert first.closure_fingerprint_sha256 == second.closure_fingerprint_sha256


def test_seal_carries_outcome_and_gate_closure_fingerprints() -> None:
    ctx = context()
    initial, result, final = execute(ctx)

    closed = seal(ctx, initial, result, final)

    assert closed.outcome_fingerprints_sha256 == tuple(
        item.fingerprint_sha256 for item in result.outcomes
    )
    assert closed.gate_closure_fingerprints_sha256 == tuple(
        item.gate_closure_fingerprint_sha256 for item in result.outcomes
    )


def test_seal_is_audit_only_without_authority() -> None:
    ctx = context()
    initial, result, final = execute(ctx)

    closed = seal(ctx, initial, result, final)

    assert closed.audit_only is True
    assert closed.mutation_applied is False
    assert closed.reservation_mutation is False
    assert closed.risk_authority is False
    assert closed.admission_authority is False
    assert closed.local_risk_override is False
    assert closed.resize_authority is False
    assert closed.broker_authority is False
    assert closed.registry_mutation is False
    assert closed.live_authority is False
    assert closed.auto_execute is False


def test_seal_is_frozen() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    closed = seal(ctx, initial, result, final)

    with pytest.raises(FrozenInstanceError):
        closed.run_id = "changed"


def test_constructor_rejects_bad_closure_fingerprint() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    closed = seal(ctx, initial, result, final)

    with pytest.raises(ValueError, match="fingerprint"):
        replace(closed, closure_fingerprint_sha256="0" * 64)


def test_rejects_wrong_arbitration_policy() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    other = context(suffix="-other")

    with pytest.raises(ValueError, match="policy provenance"):
        build_master_arbitration_closure_seal(
            arbitration_policy=other["arbitration_policy"],
            batch=ctx["batch"],
            allocation_policy=ctx["allocation"],
            gate_policy=ctx["gate_policy"],
            opening_snapshot=ctx["opening"],
            portfolio_snapshot=ctx["portfolio"],
            initial_ledger=initial,
            final_ledger=final,
            result=result,
        )


def test_rejects_wrong_allocation_policy() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    other = allocation_policy(policy_id="static-v2")

    with pytest.raises(ValueError, match="allocation provenance"):
        build_master_arbitration_closure_seal(
            arbitration_policy=ctx["arbitration_policy"],
            batch=ctx["batch"],
            allocation_policy=other,
            gate_policy=ctx["gate_policy"],
            opening_snapshot=ctx["opening"],
            portfolio_snapshot=ctx["portfolio"],
            initial_ledger=initial,
            final_ledger=final,
            result=result,
        )


def test_rejects_wrong_gate_policy() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    other = context(gate_risk="99", suffix="-gate")

    with pytest.raises(ValueError, match="gate policy provenance"):
        build_master_arbitration_closure_seal(
            arbitration_policy=ctx["arbitration_policy"],
            batch=ctx["batch"],
            allocation_policy=ctx["allocation"],
            gate_policy=other["gate_policy"],
            opening_snapshot=ctx["opening"],
            portfolio_snapshot=ctx["portfolio"],
            initial_ledger=initial,
            final_ledger=final,
            result=result,
        )


def test_rejects_wrong_portfolio_snapshot() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    other = portfolio_snapshot(source_suffix="other")

    with pytest.raises(ValueError, match="portfolio snapshot mismatch"):
        build_master_arbitration_closure_seal(
            arbitration_policy=ctx["arbitration_policy"],
            batch=ctx["batch"],
            allocation_policy=ctx["allocation"],
            gate_policy=ctx["gate_policy"],
            opening_snapshot=ctx["opening"],
            portfolio_snapshot=other,
            initial_ledger=initial,
            final_ledger=final,
            result=result,
        )


def test_rejects_wrong_initial_ledger() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    other_ctx = context(suffix="-ledger")
    other_initial = other_ctx["ledger"].snapshot()

    with pytest.raises(ValueError, match="source ledger"):
        seal(ctx, other_initial, result, final)


def test_rejects_wrong_final_ledger() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    other_ctx = context(suffix="-final")
    _, _, other_final = execute(other_ctx)

    with pytest.raises(ValueError, match="final ledger mismatch"):
        seal(ctx, initial, result, other_final)


def test_rejects_result_bound_to_another_batch() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    forged = forge_result(result, batch_id="other-batch")

    with pytest.raises(ValueError, match="supplied batch"):
        seal(ctx, initial, forged, final)


def test_rejects_result_policy_fingerprint_mismatch() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    forged = forge_result(result, arbitration_policy_fingerprint_sha256="0" * 64)

    with pytest.raises(ValueError, match="result policy provenance"):
        seal(ctx, initial, forged, final)


def test_rejects_result_gate_fingerprint_mismatch() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    forged = forge_result(result, gate_policy_fingerprint_sha256="0" * 64)

    with pytest.raises(ValueError, match="gate policy provenance"):
        seal(ctx, initial, forged, final)


def test_rejects_result_opening_snapshot_mismatch() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    forged = forge_result(result, opening_snapshot_fingerprint_sha256="0" * 64)

    with pytest.raises(ValueError, match="opening snapshot mismatch"):
        seal(ctx, initial, forged, final)


def test_rejects_result_that_postdates_portfolio_observation() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    forged = forge_result(result, evaluated_at=EVALUATED_AT + timedelta(seconds=1))

    with pytest.raises(ValueError, match="postdates portfolio observation"):
        seal(ctx, initial, forged, final)


def test_rejects_outcome_count_that_does_not_match_batch() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    only = forge_outcome(
        result.outcomes[0],
        ledger_after_fingerprint_sha256=final.fingerprint_sha256,
    )
    forged = forge_result(result, outcomes=(only,))

    with pytest.raises(ValueError, match="outcome count"):
        seal(ctx, initial, forged, final)


def test_rejects_outcome_identity_mismatch() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    wrong = forge_outcome(result.outcomes[0], system_id="crew-x")
    forged = forge_result(result, outcomes=(wrong, result.outcomes[1]))

    with pytest.raises(ValueError, match="ordered batch entry"):
        seal(ctx, initial, forged, final)


def test_rejects_admit_with_non_admitted_reason() -> None:
    ctx = context()
    initial, result, final = execute(ctx)
    wrong = forge_outcome(
        result.outcomes[0],
        decision_reason_codes=(MasterRiskGateReasonCode.MASTER_OPEN_RISK_LIMIT_EXCEEDED,),
    )
    forged = forge_result(result, outcomes=(wrong, result.outcomes[1]))

    with pytest.raises(ValueError, match="ADMIT arbitration outcome"):
        seal(ctx, initial, forged, final)


def test_rejects_reject_with_admitted_reason() -> None:
    ctx = context(gate_risk="3")
    initial, result, final = execute(ctx)
    rejected = next(
        item
        for item in result.outcomes
        if item.decision_status is MasterRiskGateDecisionStatus.REJECT
    )
    admitted = next(
        item
        for item in result.outcomes
        if item.decision_status is MasterRiskGateDecisionStatus.ADMIT
    )
    wrong = forge_outcome(
        rejected,
        decision_reason_codes=(MasterRiskGateReasonCode.ADMITTED,),
    )
    outcomes = (wrong, admitted) if wrong.rank == 1 else (admitted, wrong)
    forged = forge_result(result, outcomes=outcomes)

    with pytest.raises(ValueError, match="REJECT arbitration outcome"):
        seal(ctx, initial, forged, final)


def test_rejects_late_mutation_of_admitted_batch_reservation() -> None:
    ctx = context()
    initial, result, _ = execute(ctx)
    target = result.outcomes[-1]
    ctx["ledger"].release(
        target.reservation_id,
        released_at=EVALUATED_AT + timedelta(seconds=1),
        release_ref="late-release",
    )
    mutated_final = ctx["ledger"].snapshot()
    wrong_last = forge_outcome(
        target,
        ledger_after_fingerprint_sha256=mutated_final.fingerprint_sha256,
    )
    forged = forge_result(
        result,
        final_ledger_fingerprint_sha256=mutated_final.fingerprint_sha256,
        outcomes=(result.outcomes[0], wrong_last),
    )

    with pytest.raises(ValueError, match="ADMIT arbitration outcome"):
        seal(ctx, initial, forged, mutated_final)


def test_rejects_mutation_outside_batch() -> None:
    ctx = context(unrelated=True)
    initial, result, _ = execute(ctx)
    unrelated_id = ctx["unrelated_id"]
    assert unrelated_id is not None
    ctx["ledger"].release(
        unrelated_id,
        released_at=EVALUATED_AT + timedelta(seconds=1),
        release_ref="outside-batch",
    )
    mutated_final = ctx["ledger"].snapshot()
    wrong_last = forge_outcome(
        result.outcomes[-1],
        ledger_after_fingerprint_sha256=mutated_final.fingerprint_sha256,
    )
    forged = forge_result(
        result,
        final_ledger_fingerprint_sha256=mutated_final.fingerprint_sha256,
        outcomes=(result.outcomes[0], wrong_last),
    )

    with pytest.raises(ValueError, match="outside the batch"):
        seal(ctx, initial, forged, mutated_final)


def test_final_reservations_reference_their_decision_ids() -> None:
    ctx = context(gate_risk="3")
    initial, result, final = execute(ctx)

    seal(ctx, initial, result, final)
    final_map = {item.reservation_id: item for item in final.reservations}
    for outcome in result.outcomes:
        record = final_map[outcome.reservation_id]
        if outcome.decision_status is MasterRiskGateDecisionStatus.ADMIT:
            assert record.status is ReservationRecordStatus.COMMITTED
            assert record.commit_ref == outcome.decision_id
        else:
            assert record.status is ReservationRecordStatus.RELEASED
            assert record.release_ref == outcome.decision_id
