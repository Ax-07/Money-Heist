from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

import pytest

from app.portfolio.allocation import (
    AllocationEnvelopeStatus,
    CrewAllocationEnvelope,
    build_master_allocation_policy,
)
from app.portfolio.arbitration import (
    MasterArbitrationOrderStrategy,
    build_master_arbitration_policy,
)
from app.portfolio.historical_replay import build_master_historical_replay_plan
from app.portfolio.historical_replay_coordinator import (
    MasterHistoricalReplayBarrierPhase,
    build_master_historical_replay_timeline,
)
from app.portfolio.historical_replay_preexecution import (
    HistoricalCrewPreExecutionEvidence,
    build_master_historical_decision_barrier,
)
from app.portfolio.historical_replay_reservation_arbitration import (
    MasterHistoricalCapitalRequirementSource,
    MasterHistoricalReservationArbitrationStatus,
    MasterHistoricalReservationAttemptStatus,
    bridge_master_historical_reservation_and_arbitration,
    build_master_historical_capital_requirement,
)
from app.portfolio.models import (
    CrewExposureSnapshot,
    MasterCapitalSnapshot,
    PortfolioMemberRef,
    SnapshotDataStatus,
)
from app.portfolio.reservation import (
    MasterReservationLedger,
    ReservationOutcomeStatus,
    ReservationReasonCode,
    ReservationRecordStatus,
    ReservationRequest,
)
from app.portfolio.risk_gate import (
    MasterRiskGateDecisionStatus,
    build_master_risk_gate_policy,
)
from app.portfolio.snapshot import build_master_portfolio_snapshot
from app.services.backtest.dataset import DatasetRef
from app.trading.risk.models import RiskDecision, RiskDecisionStatus, RiskReasonCode

MASTER_ID = "master-alpha"
BASE = datetime(2026, 1, 1, tzinfo=UTC)


class Intrabar(StrEnum):
    STOP_FIRST = "STOP_FIRST"


class OrchestrationStatus(StrEnum):
    NO_ANALYSIS = "NO_ANALYSIS"
    NO_TRADE = "NO_TRADE"
    TRADE_PROPOSAL = "TRADE_PROPOSAL"
    FAILED = "FAILED"


@dataclass(frozen=True)
class FakeConfig:
    system_id: str
    initial_balance: Decimal
    execution_model_version: str = "historical-ohlc-v1"
    maker_fee_bps: Decimal = Decimal("1")
    taker_fee_bps: Decimal = Decimal("2")
    market_slippage_bps: Decimal = Decimal("0.5")
    intrabar_policy: Intrabar = Intrabar.STOP_FIRST

    def canonical_payload(self) -> dict[str, object]:
        return {
            "system_id": self.system_id,
            "initial_balance": self.initial_balance,
            "execution_model_version": self.execution_model_version,
            "maker_fee_bps": self.maker_fee_bps,
            "taker_fee_bps": self.taker_fee_bps,
            "market_slippage_bps": self.market_slippage_bps,
            "intrabar_policy": self.intrabar_policy,
        }


@dataclass(frozen=True)
class FakeRun:
    run_id: str
    dataset: object
    config: object
    period_start: datetime
    period_end: datetime


@dataclass(frozen=True)
class FakeContext:
    snapshot_id: str
    symbol: str
    timeframe: str
    observed_at: datetime


@dataclass(frozen=True)
class FakeOpportunity:
    opportunity_id: str
    snapshot_id: str
    system_id: str
    symbol: str
    timeframe: str


@dataclass(frozen=True)
class FakeProposal:
    proposal_id: str
    opportunity_id: str
    source_snapshot_id: str
    system_id: str
    symbol: str
    timeframe: str
    created_at: datetime


@dataclass(frozen=True)
class FakeOrchestrationResult:
    status: OrchestrationStatus
    opportunity_id: str
    source_snapshot_id: str
    system_id: str
    symbol: str
    trade_proposal: FakeProposal | None = None
    failure: object | None = None


def _candles() -> tuple[dict[str, object], ...]:
    rows = []
    for index in range(4):
        open_at = BASE + timedelta(hours=index)
        price = Decimal("100") + Decimal(index)
        rows.append(
            {
                "symbol": "BTCUSDC",
                "timeframe": "1h",
                "open_time": open_at,
                "close_time": open_at + timedelta(hours=1),
                "open": price,
                "high": price + Decimal("2"),
                "low": price - Decimal("2"),
                "close": price + Decimal("1"),
                "volume": Decimal("10"),
                "is_closed": True,
            }
        )
    return tuple(rows)


def _dataset() -> DatasetRef:
    return DatasetRef.from_candles(
        _candles(), symbol="BTCUSDC", timeframe="1h", source="fixture"
    )


def _policies(
    *,
    master_capital: Decimal = Decimal("100"),
    crew_capital: Decimal = Decimal("70"),
    crew_risk: Decimal = Decimal("10"),
    crew_gross: Decimal = Decimal("100"),
    gate_risk: Decimal = Decimal("10"),
    gate_gross: Decimal = Decimal("100"),
):
    members = (
        PortfolioMemberRef(system_id="crew-a"),
        PortfolioMemberRef(system_id="crew-b"),
    )
    allocation = build_master_allocation_policy(
        master_portfolio_id=MASTER_ID,
        policy_id="allocation-v1",
        members=members,
        envelopes=tuple(
            CrewAllocationEnvelope(
                system_id=member.system_id,
                status=AllocationEnvelopeStatus.CONFIGURED,
                capital_ceiling_amount=crew_capital,
                open_risk_ceiling_amount=crew_risk,
                gross_exposure_ceiling_amount=crew_gross,
            )
            for member in members
        ),
    )
    gate = build_master_risk_gate_policy(
        master_portfolio_id=MASTER_ID,
        gate_policy_id="gate-v1",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        max_total_open_risk_amount=gate_risk,
        max_total_gross_exposure_amount=gate_gross,
    )
    arbitration = build_master_arbitration_policy(
        master_portfolio_id=MASTER_ID,
        arbitration_policy_id="arb-v1",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        order_strategy=MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST,
    )
    return master_capital, allocation, gate, arbitration


def _plan_timeline_barrier(*, policies=None):
    capital, allocation, gate, arbitration = policies or _policies()
    dataset = _dataset()
    period_start = BASE + timedelta(hours=2)
    period_end = BASE + timedelta(hours=4)
    runs = tuple(
        FakeRun(
            run_id=f"run-{suffix}",
            dataset=dataset,
            config=FakeConfig(system_id=f"crew-{suffix}", initial_balance=balance),
            period_start=period_start,
            period_end=period_end,
        )
        for suffix, balance in (("a", Decimal("100")), ("b", Decimal("250")))
    )
    plan = build_master_historical_replay_plan(
        master_portfolio_id=MASTER_ID,
        master_initial_capital=capital,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        backtest_runs=runs,
        created_at=BASE + timedelta(days=10),
    )
    timeline = build_master_historical_replay_timeline(
        plan=plan,
        dataset=dataset,
        candles=_candles(),
    )
    barrier = next(
        item
        for item in timeline.barriers
        if item.phase is MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE
        and item.decision_eligible
    )
    return plan, timeline, barrier, allocation, gate, arbitration


def _evidence(
    barrier,
    system_id: str,
    *,
    risk_status: RiskDecisionStatus = RiskDecisionStatus.APPROVED,
    orchestration_status: OrchestrationStatus = OrchestrationStatus.TRADE_PROPOSAL,
    approved_risk: Decimal = Decimal("2"),
    approved_notional: Decimal = Decimal("20"),
) -> HistoricalCrewPreExecutionEvidence:
    context = FakeContext(
        snapshot_id=f"snapshot:{barrier.candle_index}:{system_id}",
        symbol="BTCUSDC",
        timeframe="1h",
        observed_at=barrier.observed_at,
    )
    opportunity = FakeOpportunity(
        opportunity_id=f"opp:{system_id}",
        snapshot_id=context.snapshot_id,
        system_id=system_id,
        symbol=context.symbol,
        timeframe=context.timeframe,
    )
    if orchestration_status is not OrchestrationStatus.TRADE_PROPOSAL:
        orchestration = FakeOrchestrationResult(
            status=orchestration_status,
            opportunity_id=opportunity.opportunity_id,
            source_snapshot_id=context.snapshot_id,
            system_id=system_id,
            symbol=context.symbol,
        )
        return HistoricalCrewPreExecutionEvidence(
            system_id=system_id,
            market_context=context,
            opportunity=opportunity,
            orchestration_result=orchestration,
        )
    proposal = FakeProposal(
        proposal_id=f"proposal:{system_id}",
        opportunity_id=opportunity.opportunity_id,
        source_snapshot_id=context.snapshot_id,
        system_id=system_id,
        symbol=context.symbol,
        timeframe=context.timeframe,
        created_at=barrier.observed_at,
    )
    orchestration = FakeOrchestrationResult(
        status=orchestration_status,
        opportunity_id=opportunity.opportunity_id,
        source_snapshot_id=context.snapshot_id,
        system_id=system_id,
        symbol=context.symbol,
        trade_proposal=proposal,
    )
    if risk_status is RiskDecisionStatus.REJECTED:
        decision = RiskDecision(
            proposal_id=proposal.proposal_id,
            status=risk_status,
            reason_codes=(RiskReasonCode.MAX_PORTFOLIO_RISK,),
            created_at=barrier.observed_at,
        )
    else:
        reason = (
            RiskReasonCode.APPROVED
            if risk_status is RiskDecisionStatus.APPROVED
            else RiskReasonCode.RESIZED_PORTFOLIO_RISK
        )
        decision = RiskDecision(
            proposal_id=proposal.proposal_id,
            status=risk_status,
            reason_codes=(reason,),
            approved_quantity=Decimal("2"),
            approved_risk_amount=approved_risk,
            approved_notional=approved_notional,
            created_at=barrier.observed_at,
            details={"risk_profile_id": "risk-v1"},
        )
    return HistoricalCrewPreExecutionEvidence(
        system_id=system_id,
        market_context=context,
        opportunity=opportunity,
        orchestration_result=orchestration,
        local_risk_decision=decision,
    )


def _decision_barrier(*, policies=None, evidence=None):
    plan, timeline, barrier, allocation, gate, arbitration = _plan_timeline_barrier(
        policies=policies
    )
    crew_evidence = evidence or (
        _evidence(barrier, "crew-a"),
        _evidence(barrier, "crew-b"),
    )
    result = build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=barrier,
        crew_evidence=tuple(crew_evidence),
    )
    return plan, timeline, result, allocation, gate, arbitration


def _snapshot(*, observed_at: datetime, equity: Decimal = Decimal("100")):
    members = (
        PortfolioMemberRef(system_id="crew-a"),
        PortfolioMemberRef(system_id="crew-b"),
    )
    capital = MasterCapitalSnapshot(
        master_portfolio_id=MASTER_ID,
        observed_at=observed_at,
        status=SnapshotDataStatus.AVAILABLE,
        source="historical-master-fixture",
        equity=equity,
        cash_balance=equity,
        day_start_equity=equity,
        equity_peak=equity,
    )
    exposures = tuple(
        CrewExposureSnapshot(
            system_id=member.system_id,
            observed_at=observed_at,
            status=SnapshotDataStatus.AVAILABLE,
            source="historical-master-fixture",
            open_positions=0,
            gross_exposure_amount=Decimal("0"),
            open_risk_amount=Decimal("0"),
        )
        for member in members
    )
    return build_master_portfolio_snapshot(
        master_capital=capital,
        members=members,
        crew_exposures=exposures,
    )


def _runtime(*, policies=None, evidence=None):
    plan, timeline, barrier, allocation, gate, arbitration = _decision_barrier(
        policies=policies,
        evidence=evidence,
    )
    opening = _snapshot(observed_at=BASE, equity=plan.master_initial_capital)
    current = _snapshot(observed_at=barrier.observed_at, equity=plan.master_initial_capital)
    ledger = MasterReservationLedger(policy=allocation, opening_snapshot=opening)
    return plan, timeline, barrier, allocation, gate, arbitration, opening, current, ledger


def _requirements(barrier, *, a=Decimal("30"), b=Decimal("30")):
    by_system = {seed.system_id: seed for seed in barrier.candidate_seeds}
    amounts = {"crew-a": a, "crew-b": b}
    return tuple(
        build_master_historical_capital_requirement(
            system_id=system_id,
            proposal_id=seed.proposal_id,
            capital_amount=amounts[system_id],
            source_ref="operator:test",
        )
        for system_id, seed in sorted(by_system.items())
    )


def _bridge(*, policies=None, evidence=None, requirements=None):
    runtime = _runtime(policies=policies, evidence=evidence)
    plan, timeline, barrier, allocation, gate, arbitration, opening, current, ledger = runtime
    if requirements is None:
        requirements = _requirements(barrier)
    result = bridge_master_historical_reservation_and_arbitration(
        plan=plan,
        timeline=timeline,
        decision_barrier=barrier,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger=ledger,
        capital_requirements=tuple(requirements),
    )
    return result, runtime


def test_capital_requirement_is_explicit_operator_input() -> None:
    requirement = build_master_historical_capital_requirement(
        system_id="crew-a",
        proposal_id="proposal:crew-a",
        capital_amount=Decimal("7"),
        source_ref="operator:test",
    )
    assert requirement.capital_amount == Decimal("7")
    assert requirement.source is MasterHistoricalCapitalRequirementSource.OPERATOR_CONFIGURATION
    assert requirement.inferred_from_notional is False


def test_capital_requirement_rejects_zero() -> None:
    with pytest.raises(ValueError, match="capital_amount"):
        build_master_historical_capital_requirement(
            system_id="crew-a",
            proposal_id="proposal:crew-a",
            capital_amount=Decimal("0"),
        )


def test_capital_requirement_rejects_non_finite() -> None:
    with pytest.raises(ValueError, match="capital_amount"):
        build_master_historical_capital_requirement(
            system_id="crew-a",
            proposal_id="proposal:crew-a",
            capital_amount=Decimal("NaN"),
        )


def test_capital_requirement_is_deterministic() -> None:
    kwargs = dict(
        system_id="crew-a",
        proposal_id="proposal:crew-a",
        capital_amount=Decimal("7"),
        source_ref="operator:test",
    )
    assert build_master_historical_capital_requirement(**kwargs) == (
        build_master_historical_capital_requirement(**kwargs)
    )


def test_two_authorized_seeds_are_reserved_and_arbitrated() -> None:
    result, _ = _bridge()
    assert result.status is MasterHistoricalReservationArbitrationStatus.ARBITRATED
    assert result.reserved_count == 2
    assert result.not_reserved_count == 0
    assert result.admitted_count == 2
    assert result.master_rejected_count == 0


def test_bridge_uses_exact_close_barrier_time_everywhere() -> None:
    result, _ = _bridge()
    assert all(item.request.requested_at == result.observed_at for item in result.attempts)
    assert result.arbitration_batch is not None
    assert result.arbitration_result is not None
    assert result.arbitration_batch.created_at == result.observed_at
    assert result.arbitration_result.evaluated_at == result.observed_at


def test_request_uses_seed_risk_and_notional_without_inference() -> None:
    result, _ = _bridge()
    for attempt in result.attempts:
        seed_risk = attempt.candidate.local_approved_risk_amount
        seed_notional = attempt.candidate.local_approved_notional
        assert attempt.request.open_risk_amount == seed_risk
        assert attempt.request.gross_exposure_amount == seed_notional
        assert attempt.request.capital_amount == Decimal("30")
        assert attempt.request.capital_amount != seed_notional


def test_request_ref_is_exact_proposal_id() -> None:
    result, _ = _bridge()
    assert all(item.request.request_ref == item.proposal_id for item in result.attempts)


def test_candidate_preserves_exact_local_risk_fingerprint() -> None:
    result, runtime = _bridge()
    seeds = {seed.system_id: seed for seed in runtime[2].candidate_seeds}
    for attempt in result.attempts:
        assert attempt.candidate is not None
        assert attempt.candidate.local_risk_decision_fingerprint_sha256 == (
            seeds[attempt.system_id].local_risk_decision_fingerprint_sha256
        )


def test_admitted_reservations_end_committed() -> None:
    result, runtime = _bridge()
    ledger = runtime[-1]
    assert result.admitted_count == 2
    assert all(
        ledger.get(attempt.reservation_id).status is ReservationRecordStatus.COMMITTED
        for attempt in result.attempts
        if attempt.reservation_id is not None
    )


def test_master_gate_rejection_releases_reservation() -> None:
    policies = _policies(gate_risk=Decimal("1"))
    plan, timeline, barrier, allocation, gate, arbitration = _decision_barrier(
        policies=policies,
        evidence=None,
    )
    opening = _snapshot(observed_at=BASE, equity=plan.master_initial_capital)
    current = _snapshot(observed_at=barrier.observed_at, equity=plan.master_initial_capital)
    ledger = MasterReservationLedger(policy=allocation, opening_snapshot=opening)
    requirements = _requirements(barrier)
    result = bridge_master_historical_reservation_and_arbitration(
        plan=plan,
        timeline=timeline,
        decision_barrier=barrier,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger=ledger,
        capital_requirements=requirements,
    )
    assert result.master_rejected_count == 2
    assert result.admitted_count == 0
    assert all(
        ledger.get(attempt.reservation_id).status is ReservationRecordStatus.RELEASED
        for attempt in result.attempts
        if attempt.reservation_id is not None
    )


def test_reservation_capacity_can_reject_one_before_arbitration() -> None:
    result, _ = _bridge(requirements=None, policies=_policies(master_capital=Decimal("100")))
    assert result.reserved_count == 2
    assert result.not_reserved_count == 0


def test_global_capital_reservation_rejection_is_explicit() -> None:
    runtime = _runtime()
    plan, timeline, barrier, allocation, gate, arbitration, opening, current, ledger = runtime
    requirements = _requirements(barrier, a=Decimal("60"), b=Decimal("60"))
    result = bridge_master_historical_reservation_and_arbitration(
        plan=plan,
        timeline=timeline,
        decision_barrier=barrier,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger=ledger,
        capital_requirements=requirements,
    )
    assert result.reserved_count == 1
    assert result.not_reserved_count == 1
    failed = next(
        item
        for item in result.attempts
        if item.status is MasterHistoricalReservationAttemptStatus.NOT_RESERVED
    )
    assert ReservationReasonCode.MASTER_CAPITAL_EXCEEDED in failed.reason_codes


def test_per_crew_capital_reservation_rejection_is_explicit() -> None:
    runtime = _runtime()
    plan, timeline, barrier, allocation, gate, arbitration, opening, current, ledger = runtime
    requirements = _requirements(barrier, a=Decimal("71"), b=Decimal("30"))
    result = bridge_master_historical_reservation_and_arbitration(
        plan=plan,
        timeline=timeline,
        decision_barrier=barrier,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger=ledger,
        capital_requirements=requirements,
    )
    failed = next(item for item in result.attempts if item.system_id == "crew-a")
    assert failed.reservation_result.status is ReservationOutcomeStatus.NOT_RESERVED
    assert ReservationReasonCode.CAPITAL_ENVELOPE_EXCEEDED in failed.reason_codes


def test_all_reservations_failed_skips_arbitration() -> None:
    policies = _policies(crew_capital=Decimal("10"))
    runtime = _runtime(policies=policies)
    plan, timeline, barrier, allocation, gate, arbitration, opening, current, ledger = runtime
    requirements = _requirements(barrier, a=Decimal("30"), b=Decimal("30"))
    result = bridge_master_historical_reservation_and_arbitration(
        plan=plan,
        timeline=timeline,
        decision_barrier=barrier,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger=ledger,
        capital_requirements=requirements,
    )
    assert result.status is MasterHistoricalReservationArbitrationStatus.NO_RESERVATIONS
    assert result.arbitration_batch is None
    assert result.arbitration_result is None
    assert result.reservation_mutation_applied is True
    assert result.mutation_applied is True


def test_no_authorized_seeds_is_noop() -> None:
    plan, timeline, source_barrier, allocation, gate, arbitration = _plan_timeline_barrier()
    evidence = (
        _evidence(source_barrier, "crew-a", risk_status=RiskDecisionStatus.REJECTED),
        _evidence(source_barrier, "crew-b", risk_status=RiskDecisionStatus.REJECTED),
    )
    barrier = build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=source_barrier,
        crew_evidence=evidence,
    )
    opening = _snapshot(observed_at=BASE, equity=plan.master_initial_capital)
    current = _snapshot(observed_at=barrier.observed_at, equity=plan.master_initial_capital)
    ledger = MasterReservationLedger(policy=allocation, opening_snapshot=opening)
    before = ledger.snapshot()
    result = bridge_master_historical_reservation_and_arbitration(
        plan=plan,
        timeline=timeline,
        decision_barrier=barrier,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger=ledger,
        capital_requirements=(),
    )
    assert result.status is MasterHistoricalReservationArbitrationStatus.NO_AUTHORIZED_CANDIDATES
    assert result.attempts == ()
    assert result.final_ledger_fingerprint_sha256 == before.fingerprint_sha256


def test_missing_capital_requirement_is_rejected_before_mutation() -> None:
    runtime = _runtime()
    barrier = runtime[2]
    before = runtime[-1].snapshot()
    requirements = _requirements(barrier)[:1]
    with pytest.raises(ValueError, match="match authorized seeds exactly"):
        bridge_master_historical_reservation_and_arbitration(
            plan=runtime[0],
            timeline=runtime[1],
            decision_barrier=barrier,
            allocation_policy=runtime[3],
            gate_policy=runtime[4],
            arbitration_policy=runtime[5],
            opening_snapshot=runtime[6],
            portfolio_snapshot=runtime[7],
            ledger=runtime[8],
            capital_requirements=requirements,
        )
    assert runtime[-1].snapshot() == before


def test_extra_capital_requirement_is_rejected_before_mutation() -> None:
    runtime = _runtime()
    barrier = runtime[2]
    requirements = _requirements(barrier) + (
        build_master_historical_capital_requirement(
            system_id="crew-x",
            proposal_id="proposal:x",
            capital_amount=Decimal("1"),
        ),
    )
    with pytest.raises(ValueError, match="match authorized seeds exactly"):
        bridge_master_historical_reservation_and_arbitration(
            plan=runtime[0],
            timeline=runtime[1],
            decision_barrier=barrier,
            allocation_policy=runtime[3],
            gate_policy=runtime[4],
            arbitration_policy=runtime[5],
            opening_snapshot=runtime[6],
            portfolio_snapshot=runtime[7],
            ledger=runtime[8],
            capital_requirements=requirements,
        )


def test_duplicate_capital_requirement_is_rejected() -> None:
    runtime = _runtime()
    barrier = runtime[2]
    requirements = _requirements(barrier)
    with pytest.raises(ValueError, match="cannot duplicate"):
        bridge_master_historical_reservation_and_arbitration(
            plan=runtime[0],
            timeline=runtime[1],
            decision_barrier=barrier,
            allocation_policy=runtime[3],
            gate_policy=runtime[4],
            arbitration_policy=runtime[5],
            opening_snapshot=runtime[6],
            portfolio_snapshot=runtime[7],
            ledger=runtime[8],
            capital_requirements=(requirements[0], requirements[0], requirements[1]),
        )


def test_requirement_input_order_does_not_change_result() -> None:
    first_runtime = _runtime()
    first_requirements = _requirements(first_runtime[2])
    first = bridge_master_historical_reservation_and_arbitration(
        plan=first_runtime[0], timeline=first_runtime[1], decision_barrier=first_runtime[2],
        allocation_policy=first_runtime[3], gate_policy=first_runtime[4],
        arbitration_policy=first_runtime[5], opening_snapshot=first_runtime[6],
        portfolio_snapshot=first_runtime[7], ledger=first_runtime[8],
        capital_requirements=first_requirements,
    )
    second_runtime = _runtime()
    second_requirements = tuple(reversed(_requirements(second_runtime[2])))
    second = bridge_master_historical_reservation_and_arbitration(
        plan=second_runtime[0], timeline=second_runtime[1], decision_barrier=second_runtime[2],
        allocation_policy=second_runtime[3], gate_policy=second_runtime[4],
        arbitration_policy=second_runtime[5], opening_snapshot=second_runtime[6],
        portfolio_snapshot=second_runtime[7], ledger=second_runtime[8],
        capital_requirements=second_requirements,
    )
    assert first.fingerprint_sha256 == second.fingerprint_sha256
    assert first.result_id == second.result_id


def test_resized_local_risk_remains_resized() -> None:
    plan, timeline, source_barrier, allocation, gate, arbitration = _plan_timeline_barrier()
    evidence = (
        _evidence(source_barrier, "crew-a", risk_status=RiskDecisionStatus.RESIZED),
        _evidence(source_barrier, "crew-b", risk_status=RiskDecisionStatus.REJECTED),
    )
    barrier = build_master_historical_decision_barrier(
        plan=plan, timeline=timeline, barrier=source_barrier, crew_evidence=evidence
    )
    opening = _snapshot(observed_at=BASE, equity=plan.master_initial_capital)
    current = _snapshot(observed_at=barrier.observed_at, equity=plan.master_initial_capital)
    ledger = MasterReservationLedger(policy=allocation, opening_snapshot=opening)
    requirement = build_master_historical_capital_requirement(
        system_id="crew-a",
        proposal_id=barrier.candidate_seeds[0].proposal_id,
        capital_amount=Decimal("30"),
    )
    result = bridge_master_historical_reservation_and_arbitration(
        plan=plan, timeline=timeline, decision_barrier=barrier,
        allocation_policy=allocation, gate_policy=gate, arbitration_policy=arbitration,
        opening_snapshot=opening, portfolio_snapshot=current, ledger=ledger,
        capital_requirements=(requirement,),
    )
    assert result.candidates[0].local_risk_status is RiskDecisionStatus.RESIZED
    assert result.candidates[0].local_approved_risk_amount == Decimal("2")
    assert result.candidates[0].local_approved_notional == Decimal("20")


def test_policy_fingerprints_are_bound_in_result() -> None:
    result, runtime = _bridge()
    assert result.allocation_policy_fingerprint_sha256 == runtime[3].fingerprint_sha256
    assert result.gate_policy_fingerprint_sha256 == runtime[4].fingerprint_sha256
    assert result.arbitration_policy_fingerprint_sha256 == runtime[5].fingerprint_sha256


def test_wrong_gate_policy_rejected_before_reservation() -> None:
    runtime = _runtime()
    wrong_gate = build_master_risk_gate_policy(
        master_portfolio_id=MASTER_ID,
        gate_policy_id="gate-other",
        allocation_policy_fingerprint_sha256=runtime[3].fingerprint_sha256,
        max_total_open_risk_amount=Decimal("10"),
        max_total_gross_exposure_amount=Decimal("100"),
    )
    with pytest.raises(ValueError, match="does not match replay plan"):
        bridge_master_historical_reservation_and_arbitration(
            plan=runtime[0], timeline=runtime[1], decision_barrier=runtime[2],
            allocation_policy=runtime[3], gate_policy=wrong_gate,
            arbitration_policy=runtime[5], opening_snapshot=runtime[6],
            portfolio_snapshot=runtime[7], ledger=runtime[8],
            capital_requirements=_requirements(runtime[2]),
        )


def test_wrong_arbitration_policy_rejected_before_reservation() -> None:
    runtime = _runtime()
    wrong = build_master_arbitration_policy(
        master_portfolio_id=MASTER_ID,
        arbitration_policy_id="arb-other",
        allocation_policy_fingerprint_sha256=runtime[3].fingerprint_sha256,
        order_strategy=MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST,
    )
    with pytest.raises(ValueError, match="does not match replay plan"):
        bridge_master_historical_reservation_and_arbitration(
            plan=runtime[0], timeline=runtime[1], decision_barrier=runtime[2],
            allocation_policy=runtime[3], gate_policy=runtime[4], arbitration_policy=wrong,
            opening_snapshot=runtime[6], portfolio_snapshot=runtime[7], ledger=runtime[8],
            capital_requirements=_requirements(runtime[2]),
        )


def test_opening_equity_must_equal_plan_master_initial_capital() -> None:
    runtime = _runtime()
    wrong_opening = _snapshot(observed_at=BASE, equity=Decimal("99"))
    wrong_ledger = MasterReservationLedger(policy=runtime[3], opening_snapshot=wrong_opening)
    with pytest.raises(ValueError, match="opening equity"):
        bridge_master_historical_reservation_and_arbitration(
            plan=runtime[0], timeline=runtime[1], decision_barrier=runtime[2],
            allocation_policy=runtime[3], gate_policy=runtime[4], arbitration_policy=runtime[5],
            opening_snapshot=wrong_opening, portfolio_snapshot=runtime[7], ledger=wrong_ledger,
            capital_requirements=_requirements(runtime[2]),
        )


def test_portfolio_snapshot_must_use_exact_barrier_time() -> None:
    runtime = _runtime()
    wrong_current = _snapshot(
        observed_at=runtime[2].observed_at + timedelta(seconds=1),
        equity=runtime[0].master_initial_capital,
    )
    with pytest.raises(ValueError, match="exact decision barrier time"):
        bridge_master_historical_reservation_and_arbitration(
            plan=runtime[0], timeline=runtime[1], decision_barrier=runtime[2],
            allocation_policy=runtime[3], gate_policy=runtime[4], arbitration_policy=runtime[5],
            opening_snapshot=runtime[6], portfolio_snapshot=wrong_current, ledger=runtime[8],
            capital_requirements=_requirements(runtime[2]),
        )


def test_future_reservation_in_ledger_is_rejected_as_lookahead() -> None:
    runtime = _runtime()
    future = ReservationRequest(
        request_id="future-request",
        system_id="crew-a",
        requested_at=runtime[2].observed_at + timedelta(minutes=1),
        capital_amount=Decimal("1"),
        open_risk_amount=Decimal("1"),
        gross_exposure_amount=Decimal("1"),
        request_ref="future-proposal",
    )
    assert runtime[8].reserve(future).status is ReservationOutcomeStatus.RESERVED
    with pytest.raises(ValueError, match="future reservation request"):
        bridge_master_historical_reservation_and_arbitration(
            plan=runtime[0], timeline=runtime[1], decision_barrier=runtime[2],
            allocation_policy=runtime[3], gate_policy=runtime[4], arbitration_policy=runtime[5],
            opening_snapshot=runtime[6], portfolio_snapshot=runtime[7], ledger=runtime[8],
            capital_requirements=_requirements(runtime[2]),
        )


def test_future_commit_in_ledger_is_rejected_as_lookahead() -> None:
    runtime = _runtime()
    request = ReservationRequest(
        request_id="existing-request",
        system_id="crew-a",
        requested_at=runtime[2].observed_at,
        capital_amount=Decimal("1"),
        open_risk_amount=Decimal("1"),
        gross_exposure_amount=Decimal("1"),
        request_ref="existing-proposal",
    )
    reservation = runtime[8].reserve(request).reservation
    assert reservation is not None
    runtime[8].commit(
        reservation.reservation_id,
        committed_at=runtime[2].observed_at + timedelta(minutes=1),
        commit_ref="future-commit",
    )
    with pytest.raises(ValueError, match="future reservation commit"):
        bridge_master_historical_reservation_and_arbitration(
            plan=runtime[0], timeline=runtime[1], decision_barrier=runtime[2],
            allocation_policy=runtime[3], gate_policy=runtime[4], arbitration_policy=runtime[5],
            opening_snapshot=runtime[6], portfolio_snapshot=runtime[7], ledger=runtime[8],
            capital_requirements=_requirements(runtime[2]),
        )


def test_bridge_has_no_broker_or_live_authority() -> None:
    result, _ = _bridge()
    assert result.broker_called is False
    assert result.broker_authority is False
    assert result.live_authority is False
    assert result.auto_execute is False
    assert result.risk_authority is False
    assert result.admission_authority is False


def test_bridge_never_sums_branch_equities() -> None:
    result, _ = _bridge()
    assert result.single_master_capital is True
    assert result.sums_branch_equities is False
    assert not hasattr(result, "branch_equity")


def test_arbitration_batch_contains_only_successfully_reserved_candidates() -> None:
    runtime = _runtime()
    plan, timeline, barrier, allocation, gate, arbitration, opening, current, ledger = runtime
    requirements = _requirements(barrier, a=Decimal("71"), b=Decimal("30"))
    result = bridge_master_historical_reservation_and_arbitration(
        plan=plan, timeline=timeline, decision_barrier=barrier,
        allocation_policy=allocation, gate_policy=gate, arbitration_policy=arbitration,
        opening_snapshot=opening, portfolio_snapshot=current, ledger=ledger,
        capital_requirements=requirements,
    )
    assert result.arbitration_batch is not None
    assert len(result.arbitration_batch.entries) == 1
    assert result.arbitration_batch.entries[0].system_id == "crew-b"


def test_final_ledger_matches_sequential_arbitration_result() -> None:
    result, _ = _bridge()
    assert result.arbitration_result is not None
    assert result.final_ledger_fingerprint_sha256 == (
        result.arbitration_result.final_ledger_fingerprint_sha256
    )


def test_post_reservation_ledger_matches_arbitration_initial_ledger() -> None:
    result, _ = _bridge()
    assert result.arbitration_result is not None
    assert result.post_reservation_ledger_fingerprint_sha256 == (
        result.arbitration_result.initial_ledger_fingerprint_sha256
    )


def test_arbitrated_result_binds_existing_arbitration_closure() -> None:
    result, _ = _bridge()
    assert result.arbitration_result is not None
    assert result.arbitration_closure is not None
    assert (
        result.arbitration_closure.result_fingerprint_sha256
        == result.arbitration_result.fingerprint_sha256
    )
    assert (
        result.arbitration_closure.initial_ledger_fingerprint_sha256
        == result.post_reservation_ledger_fingerprint_sha256
    )
    assert (
        result.arbitration_closure.final_ledger_fingerprint_sha256
        == result.final_ledger_fingerprint_sha256
    )


def test_successful_bridge_is_deterministic_on_fresh_ledgers() -> None:
    first, _ = _bridge()
    second, _ = _bridge()
    assert first.result_id == second.result_id
    assert first.fingerprint_sha256 == second.fingerprint_sha256


def test_capital_amount_changes_reservation_and_bridge_identity() -> None:
    first_runtime = _runtime()
    first = bridge_master_historical_reservation_and_arbitration(
        plan=first_runtime[0], timeline=first_runtime[1], decision_barrier=first_runtime[2],
        allocation_policy=first_runtime[3], gate_policy=first_runtime[4],
        arbitration_policy=first_runtime[5], opening_snapshot=first_runtime[6],
        portfolio_snapshot=first_runtime[7], ledger=first_runtime[8],
        capital_requirements=_requirements(first_runtime[2], a=Decimal("20"), b=Decimal("20")),
    )
    second_runtime = _runtime()
    second = bridge_master_historical_reservation_and_arbitration(
        plan=second_runtime[0], timeline=second_runtime[1], decision_barrier=second_runtime[2],
        allocation_policy=second_runtime[3], gate_policy=second_runtime[4],
        arbitration_policy=second_runtime[5], opening_snapshot=second_runtime[6],
        portfolio_snapshot=second_runtime[7], ledger=second_runtime[8],
        capital_requirements=_requirements(second_runtime[2], a=Decimal("21"), b=Decimal("20")),
    )
    assert first.result_id != second.result_id
    assert first.fingerprint_sha256 != second.fingerprint_sha256


def test_attempt_status_matches_reservation_result() -> None:
    result, _ = _bridge()
    assert all(
        item.status is MasterHistoricalReservationAttemptStatus.RESERVED_FOR_ARBITRATION
        and item.reservation_result.status is ReservationOutcomeStatus.RESERVED
        for item in result.attempts
    )


def test_master_gate_decisions_preserve_local_amounts() -> None:
    result, _ = _bridge()
    assert result.arbitration_result is not None
    candidates = {item.proposal_id: item for item in result.candidates}
    for outcome in result.arbitration_result.outcomes:
        candidate = candidates[outcome.proposal_id]
        assert candidate.local_approved_risk_amount == Decimal("2")
        assert candidate.local_approved_notional == Decimal("20")
        assert outcome.decision_status is MasterRiskGateDecisionStatus.ADMIT
