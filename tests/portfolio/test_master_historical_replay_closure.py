from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.portfolio.historical_replay_closure import (
    MasterHistoricalReplayAuditStatus,
    MasterHistoricalReplayClosureStatus,
    audit_master_historical_coordinated_replay,
    seal_master_historical_coordinated_replay,
)
from app.portfolio.reservation import ReservationRecordStatus
from tests.portfolio.test_master_historical_replay_master_runner import (
    ScriptedInputSource,
    _policies,
    _run,
)


def _context(*, mode: str = "round_trip", policies=None):
    selected = policies or _policies()
    result, plan, timeline = _run(
        source=ScriptedInputSource(mode),
        policies=selected,
    )
    _, allocation, gate, arbitration = selected
    return result, plan, timeline, allocation, gate, arbitration


def _audit(*, mode: str = "round_trip", policies=None):
    result, plan, timeline, allocation, gate, arbitration = _context(
        mode=mode,
        policies=policies,
    )
    report = audit_master_historical_coordinated_replay(
        plan=plan,
        timeline=timeline,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        result=result,
    )
    return report, result, plan, timeline, allocation, gate, arbitration


def test_audit_verifies_complete_replay() -> None:
    report, result, _, timeline, *_ = _audit()
    assert report.status is MasterHistoricalReplayAuditStatus.VERIFIED
    assert report.processed_barrier_count == len(timeline.barriers)
    assert report.decision_cycle_count == len(result.decision_cycles)
    assert report.equity_point_count == len(result.equity_curve)


def test_closure_seals_verified_replay() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    seal = seal_master_historical_coordinated_replay(
        plan=plan,
        timeline=timeline,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        result=result,
    )
    assert seal.status is MasterHistoricalReplayClosureStatus.SEALED
    assert seal.result_fingerprint_sha256 == result.fingerprint_sha256
    assert seal.final_ledger_fingerprint_sha256 == result.final_ledger.fingerprint_sha256


def test_audit_and_closure_are_deterministic_across_fresh_runs() -> None:
    first = _audit()
    second = _audit()
    (
        first_report,
        first_result,
        first_plan,
        first_timeline,
        first_allocation,
        first_gate,
        first_arb,
    ) = first
    second_report = second[0]
    assert first_report.fingerprint_sha256 == second_report.fingerprint_sha256
    first_seal = seal_master_historical_coordinated_replay(
        plan=first_plan,
        timeline=first_timeline,
        allocation_policy=first_allocation,
        gate_policy=first_gate,
        arbitration_policy=first_arb,
        result=first_result,
    )
    second_seal = seal_master_historical_coordinated_replay(
        plan=second[2],
        timeline=second[3],
        allocation_policy=second[4],
        gate_policy=second[5],
        arbitration_policy=second[6],
        result=second[1],
    )
    assert first_seal.closure_fingerprint_sha256 == second_seal.closure_fingerprint_sha256


def test_audit_is_read_only() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    before = (
        result.fingerprint_sha256,
        result.final_ledger.fingerprint_sha256,
        result.final_book.fingerprint_sha256,
    )
    audit_master_historical_coordinated_replay(
        plan=plan,
        timeline=timeline,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        result=result,
    )
    after = (
        result.fingerprint_sha256,
        result.final_ledger.fingerprint_sha256,
        result.final_book.fingerprint_sha256,
    )
    assert before == after


def test_sealed_at_is_exact_final_timeline_barrier_time() -> None:
    report, _, _, timeline, *_ = _audit()
    assert report.sealed_at == timeline.barriers[-1].observed_at


def test_final_reservation_counts_are_sealed() -> None:
    report, result, *_ = _audit()
    assert report.reserved_reservation_count == 0
    assert report.committed_reservation_count == 0
    assert report.released_reservation_count == len(result.final_ledger.reservations)


def test_open_virtual_lots_match_committed_reservations() -> None:
    report, result, *_ = _audit(mode="opposing")
    assert report.open_lot_count == 2
    assert report.committed_reservation_count == 2
    assert {
        lot.reservation_id for lot in result.final_book.open_lots
    } == {
        item.reservation_id
        for item in result.final_ledger.reservations
        if item.status is ReservationRecordStatus.COMMITTED
    }


def test_single_master_capital_is_verified_with_different_branch_balances() -> None:
    report, result, plan, *_ = _audit()
    assert tuple(crew.source_branch_initial_balance for crew in plan.crews) == (
        Decimal("100"),
        Decimal("250"),
    )
    assert report.single_master_capital_verified is True
    assert result.evaluation.initial_capital == plan.master_initial_capital == Decimal("100")


def test_final_account_fingerprint_binds_last_equity_point() -> None:
    report, result, *_ = _audit()
    assert report.final_account_fingerprint_sha256 == (
        result.equity_curve[-1].account_fingerprint_sha256
    )


def test_audit_flags_are_all_verified_and_authority_free() -> None:
    report, *_ = _audit()
    assert report.full_barrier_chain_verified
    assert report.reservation_lifecycle_verified
    assert report.virtual_lot_accounting_verified
    assert report.evaluation_accounting_verified
    assert report.audit_only
    assert not report.mutation_applied
    assert not report.reservation_mutation
    assert not report.broker_called
    assert not report.risk_authority
    assert not report.admission_authority
    assert not report.registry_mutation
    assert not report.live_authority
    assert not report.auto_execute


def test_closure_flags_are_audit_only_and_authority_free() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    seal = seal_master_historical_coordinated_replay(
        plan=plan,
        timeline=timeline,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        result=result,
    )
    assert seal.audit_only
    assert not seal.mutation_applied
    assert not seal.reservation_mutation
    assert not seal.broker_called
    assert not seal.risk_authority
    assert not seal.admission_authority
    assert not seal.local_risk_override
    assert not seal.resize_authority
    assert not seal.registry_mutation
    assert not seal.live_authority
    assert not seal.auto_execute


def test_wrong_allocation_policy_is_rejected() -> None:
    result, plan, timeline, _, gate, arbitration = _context()
    _, changed_allocation, _, _ = _policies(crew_capital=Decimal("60"))
    with pytest.raises(ValueError, match="static fingerprint provenance"):
        audit_master_historical_coordinated_replay(
            plan=plan,
            timeline=timeline,
            allocation_policy=changed_allocation,
            gate_policy=gate,
            arbitration_policy=arbitration,
            result=result,
        )


def test_tampered_result_fingerprint_is_rejected() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    object.__setattr__(result, "fingerprint_sha256", "0" * 64)
    with pytest.raises(ValueError, match="replay result fingerprint integrity"):
        audit_master_historical_coordinated_replay(
            plan=plan,
            timeline=timeline,
            allocation_policy=allocation,
            gate_policy=gate,
            arbitration_policy=arbitration,
            result=result,
        )


def test_tampered_lifecycle_barrier_provenance_is_rejected() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    object.__setattr__(result.lifecycle_results[0], "barrier_fingerprint_sha256", "0" * 64)
    with pytest.raises(ValueError, match="lifecycle result fingerprint integrity"):
        audit_master_historical_coordinated_replay(
            plan=plan,
            timeline=timeline,
            allocation_policy=allocation,
            gate_policy=gate,
            arbitration_policy=arbitration,
            result=result,
        )


def test_tampered_step4_ledger_provenance_is_rejected() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    cycle = next(item for item in result.decision_cycles if item.paper_execution.executed_count)
    object.__setattr__(cycle.reservation_arbitration, "initial_ledger_fingerprint_sha256", "0" * 64)
    with pytest.raises(ValueError, match="reservation/arbitration fingerprint integrity"):
        audit_master_historical_coordinated_replay(
            plan=plan,
            timeline=timeline,
            allocation_policy=allocation,
            gate_policy=gate,
            arbitration_policy=arbitration,
            result=result,
        )


def test_tampered_step5_arbitration_provenance_is_rejected() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    cycle = next(item for item in result.decision_cycles if item.paper_execution.executed_count)
    object.__setattr__(
        cycle.paper_execution,
        "reservation_arbitration_fingerprint_sha256",
        "0" * 64,
    )
    with pytest.raises(ValueError, match="PAPER execution fingerprint integrity"):
        audit_master_historical_coordinated_replay(
            plan=plan,
            timeline=timeline,
            allocation_policy=allocation,
            gate_policy=gate,
            arbitration_policy=arbitration,
            result=result,
        )


def test_tampered_step6_registration_ledger_is_rejected() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    cycle = next(item for item in result.decision_cycles if item.paper_execution.executed_count)
    object.__setattr__(cycle.lot_registration, "ledger_fingerprint_sha256", "0" * 64)
    with pytest.raises(ValueError, match="virtual lot registration fingerprint integrity"):
        audit_master_historical_coordinated_replay(
            plan=plan,
            timeline=timeline,
            allocation_policy=allocation,
            gate_policy=gate,
            arbitration_policy=arbitration,
            result=result,
        )


def test_tampered_equity_account_provenance_is_rejected() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    object.__setattr__(result.equity_curve[-1], "account_fingerprint_sha256", "0" * 64)
    with pytest.raises(ValueError, match="equity point fingerprint integrity"):
        audit_master_historical_coordinated_replay(
            plan=plan,
            timeline=timeline,
            allocation_policy=allocation,
            gate_policy=gate,
            arbitration_policy=arbitration,
            result=result,
        )


def test_tampered_final_ledger_is_rejected() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    object.__setattr__(
        result.final_ledger.reservations[0],
        "status",
        ReservationRecordStatus.RESERVED,
    )
    with pytest.raises(ValueError, match="reservation ledger fingerprint integrity"):
        audit_master_historical_coordinated_replay(
            plan=plan,
            timeline=timeline,
            allocation_policy=allocation,
            gate_policy=gate,
            arbitration_policy=arbitration,
            result=result,
        )


def test_tampered_final_book_is_rejected() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context(mode="opposing")
    object.__setattr__(result.final_book, "virtual_gross_exposure_amount", Decimal("999"))
    with pytest.raises(ValueError, match="final virtual lot book fingerprint integrity"):
        audit_master_historical_coordinated_replay(
            plan=plan,
            timeline=timeline,
            allocation_policy=allocation,
            gate_policy=gate,
            arbitration_policy=arbitration,
            result=result,
        )


def test_tampered_evaluation_is_rejected() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    object.__setattr__(result.evaluation, "final_equity", Decimal("999"))
    with pytest.raises(ValueError, match="evaluation fingerprint integrity"):
        audit_master_historical_coordinated_replay(
            plan=plan,
            timeline=timeline,
            allocation_policy=allocation,
            gate_policy=gate,
            arbitration_policy=arbitration,
            result=result,
        )


def test_forbidden_result_live_authority_is_rejected() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    object.__setattr__(result, "live_authority", True)
    with pytest.raises(ValueError, match="forbidden replay authority"):
        audit_master_historical_coordinated_replay(
            plan=plan,
            timeline=timeline,
            allocation_policy=allocation,
            gate_policy=gate,
            arbitration_policy=arbitration,
            result=result,
        )


def test_forbidden_decision_barrier_broker_authority_is_rejected() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    object.__setattr__(result.decision_cycles[0].decision_barrier, "broker_authority", True)
    with pytest.raises(ValueError, match="forbidden decision-cycle authority"):
        audit_master_historical_coordinated_replay(
            plan=plan,
            timeline=timeline,
            allocation_policy=allocation,
            gate_policy=gate,
            arbitration_policy=arbitration,
            result=result,
        )


def test_audit_report_rejects_fingerprint_preserving_payload_change() -> None:
    report, *_ = _audit()
    with pytest.raises(ValueError, match="audit fingerprint integrity"):
        replace(
            report,
            final_equity=report.final_equity + Decimal("1"),
            fingerprint_sha256=report.fingerprint_sha256,
        )


def test_closure_rejects_fingerprint_preserving_payload_change() -> None:
    result, plan, timeline, allocation, gate, arbitration = _context()
    seal = seal_master_historical_coordinated_replay(
        plan=plan,
        timeline=timeline,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        result=result,
    )
    with pytest.raises(ValueError, match="closure fingerprint integrity"):
        replace(
            seal,
            result_id="other-result",
            closure_fingerprint_sha256=seal.closure_fingerprint_sha256,
        )
