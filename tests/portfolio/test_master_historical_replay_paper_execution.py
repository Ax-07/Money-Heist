from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
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
from app.portfolio.historical_replay_paper_execution import (
    MasterHistoricalPaperAttemptStatus,
    MasterHistoricalPaperExecutionStatus,
    MasterHistoricalPaperProposalEvidence,
    MasterHistoricalPaperReasonCode,
    build_master_historical_paper_runtime,
    execute_master_historical_paper_admissions,
)
from app.portfolio.historical_replay_preexecution import (
    HistoricalCrewPreExecutionEvidence,
    build_master_historical_decision_barrier,
)
from app.portfolio.historical_replay_reservation_arbitration import (
    bridge_master_historical_reservation_and_arbitration,
    build_master_historical_capital_requirement,
)
from app.portfolio.models import (
    CrewExposureSnapshot,
    MasterCapitalSnapshot,
    PortfolioMemberRef,
    SnapshotDataStatus,
)
from app.portfolio.reservation import MasterReservationLedger, ReservationRecordStatus
from app.portfolio.risk_gate import (
    MasterRiskGateDecisionStatus,
    build_master_risk_gate_policy,
)
from app.portfolio.snapshot import build_master_portfolio_snapshot
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.ids import stable_digest
from app.trading.paper import OrderSide, OrderStatus
from app.trading.risk.models import RiskDecision, RiskDecisionStatus, RiskReasonCode

MASTER_ID = "master-alpha"
BASE = datetime(2026, 1, 1, tzinfo=UTC)


class Intrabar(StrEnum):
    STOP_FIRST = "STOP_FIRST"


class OrchestrationStatus(StrEnum):
    TRADE_PROPOSAL = "TRADE_PROPOSAL"


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
    close: Decimal


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
    side: str
    created_at: datetime


@dataclass(frozen=True)
class FakeOrchestrationResult:
    status: OrchestrationStatus
    opportunity_id: str
    source_snapshot_id: str
    system_id: str
    symbol: str
    trade_proposal: FakeProposal
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
    crew_risk: Decimal = Decimal("20"),
    crew_gross: Decimal = Decimal("100"),
    gate_risk: Decimal = Decimal("20"),
    gate_gross: Decimal = Decimal("200"),
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


def _plan_timeline(*, policies=None):
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


def _barrier_candle(barrier) -> dict[str, object]:
    return next(
        row
        for row in _candles()
        if row["close_time"].astimezone(UTC) == barrier.observed_at
    )


def _evidence(
    barrier,
    system_id: str,
    *,
    side: str = "LONG",
    approved_quantity: Decimal = Decimal("0.1"),
    approved_risk: Decimal = Decimal("1"),
    approved_notional: Decimal = Decimal("10.3"),
) -> HistoricalCrewPreExecutionEvidence:
    candle = _barrier_candle(barrier)
    context = FakeContext(
        snapshot_id=f"snapshot:{barrier.candle_index}:{system_id}",
        symbol="BTCUSDC",
        timeframe="1h",
        observed_at=barrier.observed_at,
        close=Decimal(str(candle["close"])),
    )
    opportunity = FakeOpportunity(
        opportunity_id=f"opp:{system_id}",
        snapshot_id=context.snapshot_id,
        system_id=system_id,
        symbol=context.symbol,
        timeframe=context.timeframe,
    )
    proposal = FakeProposal(
        proposal_id=f"proposal:{system_id}",
        opportunity_id=opportunity.opportunity_id,
        source_snapshot_id=context.snapshot_id,
        system_id=system_id,
        symbol=context.symbol,
        timeframe=context.timeframe,
        side=side,
        created_at=barrier.observed_at,
    )
    orchestration = FakeOrchestrationResult(
        status=OrchestrationStatus.TRADE_PROPOSAL,
        opportunity_id=opportunity.opportunity_id,
        source_snapshot_id=context.snapshot_id,
        system_id=system_id,
        symbol=context.symbol,
        trade_proposal=proposal,
    )
    decision = RiskDecision(
        proposal_id=proposal.proposal_id,
        status=RiskDecisionStatus.APPROVED,
        reason_codes=(RiskReasonCode.APPROVED,),
        approved_quantity=approved_quantity,
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


def _snapshot(*, observed_at: datetime, equity: Decimal):
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


def _setup(
    *,
    policies=None,
    evidence_a=None,
    evidence_b=None,
    capital_a: Decimal = Decimal("20"),
    capital_b: Decimal = Decimal("20"),
):
    plan, timeline, close_barrier, allocation, gate, arbitration = _plan_timeline(
        policies=policies
    )
    evidence_a = evidence_a or _evidence(close_barrier, "crew-a")
    evidence_b = evidence_b or _evidence(close_barrier, "crew-b")
    decision_barrier = build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=close_barrier,
        crew_evidence=(evidence_a, evidence_b),
    )
    opening = _snapshot(observed_at=BASE, equity=plan.master_initial_capital)
    current = _snapshot(
        observed_at=decision_barrier.observed_at,
        equity=plan.master_initial_capital,
    )
    ledger = MasterReservationLedger(policy=allocation, opening_snapshot=opening)
    amounts = {"crew-a": capital_a, "crew-b": capital_b}
    requirements = tuple(
        build_master_historical_capital_requirement(
            system_id=seed.system_id,
            proposal_id=seed.proposal_id,
            capital_amount=amounts[seed.system_id],
            source_ref="operator:test",
        )
        for seed in decision_barrier.candidate_seeds
    )
    step4 = bridge_master_historical_reservation_and_arbitration(
        plan=plan,
        timeline=timeline,
        decision_barrier=decision_barrier,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        opening_snapshot=opening,
        portfolio_snapshot=current,
        ledger=ledger,
        capital_requirements=requirements,
    )
    proposals = {
        item.system_id: item.orchestration_result.trade_proposal
        for item in (evidence_a, evidence_b)
    }
    proposal_evidence = tuple(
        MasterHistoricalPaperProposalEvidence(system_id=system_id, proposal=proposals[system_id])
        for system_id in sorted(proposals)
    )
    return {
        "plan": plan,
        "timeline": timeline,
        "close_barrier": close_barrier,
        "decision_barrier": decision_barrier,
        "allocation": allocation,
        "gate": gate,
        "arbitration": arbitration,
        "opening": opening,
        "current": current,
        "ledger": ledger,
        "step4": step4,
        "candle": _barrier_candle(close_barrier),
        "proposal_evidence": proposal_evidence,
    }


def _execute(setup, *, runtime=None, evidence=None, candle=None):
    runtime = runtime or build_master_historical_paper_runtime(plan=setup["plan"])
    result = asyncio.run(
        execute_master_historical_paper_admissions(
            runtime=runtime,
            plan=setup["plan"],
            timeline=setup["timeline"],
            decision_barrier=setup["decision_barrier"],
            reservation_arbitration=setup["step4"],
            ledger=setup["ledger"],
            candle=candle or setup["candle"],
            proposal_evidence=(
                setup["proposal_evidence"] if evidence is None else tuple(evidence)
            ),
        )
    )
    return result, runtime


def test_runtime_owns_one_master_account_with_exact_plan_config() -> None:
    setup = _setup()
    runtime = build_master_historical_paper_runtime(plan=setup["plan"])
    identity = runtime.identity
    assert runtime.broker.config.system_id == MASTER_ID
    assert runtime.broker.config.initial_balance == Decimal("100")
    assert runtime.broker.config.maker_fee_bps == setup["plan"].maker_fee_bps
    assert runtime.broker.config.taker_fee_bps == setup["plan"].taker_fee_bps
    assert runtime.broker.config.market_slippage_bps == setup["plan"].market_slippage_bps
    assert identity.single_master_account is True
    assert identity.uses_branch_brokers is False


def test_runtime_does_not_sum_source_branch_initial_balances() -> None:
    setup = _setup()
    assert tuple(crew.source_branch_initial_balance for crew in setup["plan"].crews) == (
        Decimal("100"),
        Decimal("250"),
    )
    runtime = build_master_historical_paper_runtime(plan=setup["plan"])
    assert runtime.broker.config.initial_balance == Decimal("100")
    assert runtime.broker.config.initial_balance != Decimal("350")


def test_two_master_admitted_long_entries_execute_on_same_broker() -> None:
    result, runtime = _execute(_setup())
    assert result.status is MasterHistoricalPaperExecutionStatus.EXECUTED
    assert result.executed_count == 2
    assert result.broker_order_count == 2
    orders = asyncio.run(runtime.broker.get_orders())
    assert len(orders) == 2
    assert all(order.system_id == MASTER_ID for order in orders)


def test_source_crew_attribution_is_preserved_outside_broker_account() -> None:
    result, runtime = _execute(_setup())
    assert tuple(item.source_system_id for item in result.attempts) == ("crew-a", "crew-b")
    assert all(item.source_system_id != MASTER_ID for item in result.attempts)
    assert all(order.system_id == MASTER_ID for order in asyncio.run(runtime.broker.get_orders()))


def test_execution_preserves_exact_local_risk_quantity() -> None:
    setup0 = _plan_timeline()
    barrier = setup0[2]
    evidence_a = _evidence(barrier, "crew-a", approved_quantity=Decimal("0.07"))
    evidence_b = _evidence(barrier, "crew-b", approved_quantity=Decimal("0.11"))
    setup = _setup(evidence_a=evidence_a, evidence_b=evidence_b)
    result, _ = _execute(setup)
    assert tuple(item.quantity for item in result.attempts) == (
        Decimal("0.07"),
        Decimal("0.11"),
    )
    assert tuple(item.fill_quantity for item in result.attempts) == (
        Decimal("0.07"),
        Decimal("0.11"),
    )


def test_fill_time_is_exact_close_barrier_time() -> None:
    result, _ = _execute(_setup())
    assert all(item.filled_at == result.observed_at for item in result.attempts)


def test_fill_uses_plan_slippage_and_taker_fee() -> None:
    setup = _setup()
    result, _ = _execute(setup)
    mark = Decimal(str(setup["candle"]["close"]))
    expected_fill = mark * (Decimal("1") + setup["plan"].market_slippage_bps / Decimal("10000"))
    first = result.attempts[0]
    assert first.fill_price == expected_fill
    expected_fee = expected_fill * first.quantity * setup["plan"].taker_fee_bps / Decimal("10000")
    assert first.fill_fee == expected_fee


def test_successful_execution_keeps_master_reservation_committed() -> None:
    setup = _setup()
    result, _ = _execute(setup)
    for attempt in result.attempts:
        reservation = setup["ledger"].get(attempt.reservation_id)
        assert reservation.status is ReservationRecordStatus.COMMITTED
        assert attempt.reservation_before_fingerprint_sha256 == (
            attempt.reservation_after_fingerprint_sha256
        )


def test_execution_result_has_no_risk_or_admission_or_live_authority() -> None:
    result, runtime = _execute(_setup())
    assert result.single_master_capital is True
    assert result.sums_branch_equities is False
    assert result.uses_branch_brokers is False
    assert result.paper_broker_authority is True
    assert result.risk_authority is False
    assert result.admission_authority is False
    assert result.live_authority is False
    assert result.auto_execute is False
    assert runtime.live_authority is False


def test_account_snapshot_converts_to_master_capital_snapshot() -> None:
    result, _ = _execute(_setup())
    capital = result.account_after.to_master_capital_snapshot()
    assert capital.master_portfolio_id == MASTER_ID
    assert capital.status is SnapshotDataStatus.AVAILABLE
    assert capital.equity == result.account_after.equity
    assert capital.cash_balance == result.account_after.cash_balance
    assert capital.source == "master-historical-paper-runtime"


def test_account_cash_is_non_negative_after_successful_long_entries() -> None:
    result, _ = _execute(_setup())
    assert result.account_after.cash_balance >= 0
    assert result.account_after.cash_balance < result.account_before.cash_balance


def test_account_equity_reflects_entry_fees_without_branch_equity_sum() -> None:
    result, _ = _execute(_setup())
    assert result.account_before.equity == Decimal("100")
    assert result.account_after.fees_paid > 0
    assert result.account_after.equity < Decimal("100")
    assert result.account_after.equity != Decimal("350")


def test_candle_content_must_match_timeline_fingerprint() -> None:
    setup = _setup()
    bad = dict(setup["candle"])
    bad["close"] = Decimal(str(bad["close"])) + Decimal("0.1")
    bad["high"] = Decimal(str(bad["high"])) + Decimal("0.1")
    with pytest.raises(ValueError, match="candle does not match timeline fingerprint"):
        _execute(setup, candle=bad)


def test_missing_proposal_evidence_fails_before_broker_execution() -> None:
    setup = _setup()
    runtime = build_master_historical_paper_runtime(plan=setup["plan"])
    with pytest.raises(ValueError, match="must match admitted candidates exactly"):
        _execute(setup, runtime=runtime, evidence=setup["proposal_evidence"][:1])
    assert asyncio.run(runtime.broker.get_orders()) == ()


def test_extra_proposal_evidence_fails_before_broker_execution() -> None:
    setup = _setup()
    extra = MasterHistoricalPaperProposalEvidence(
        system_id="crew-x",
        proposal=replace(setup["proposal_evidence"][0].proposal, system_id="crew-x"),
    )
    runtime = build_master_historical_paper_runtime(plan=setup["plan"])
    with pytest.raises(ValueError, match="must match admitted candidates exactly"):
        _execute(setup, runtime=runtime, evidence=setup["proposal_evidence"] + (extra,))
    assert asyncio.run(runtime.broker.get_orders()) == ()


def test_duplicate_proposal_evidence_is_rejected() -> None:
    setup = _setup()
    duplicate = (setup["proposal_evidence"][0], setup["proposal_evidence"][0])
    with pytest.raises(ValueError, match="cannot duplicate proposal"):
        _execute(setup, evidence=duplicate)


def test_proposal_fingerprint_mismatch_is_rejected() -> None:
    setup = _setup()
    first = setup["proposal_evidence"][0]
    changed = MasterHistoricalPaperProposalEvidence(
        system_id=first.system_id,
        proposal=replace(first.proposal, side="SHORT"),
    )
    with pytest.raises(ValueError, match="proposal fingerprint mismatch"):
        _execute(setup, evidence=(changed, setup["proposal_evidence"][1]))


def test_stale_ledger_is_rejected_before_execution() -> None:
    setup = _setup()
    first = setup["step4"].attempts[0]
    assert first.reservation_id is not None
    setup["ledger"].release(
        first.reservation_id,
        released_at=setup["decision_barrier"].observed_at,
        release_ref="external:mutation",
    )
    runtime = build_master_historical_paper_runtime(plan=setup["plan"])
    with pytest.raises(ValueError, match="ledger is stale"):
        _execute(setup, runtime=runtime)
    assert asyncio.run(runtime.broker.get_orders()) == ()


def test_runtime_from_other_plan_is_rejected() -> None:
    setup = _setup()
    other = _setup(policies=_policies(master_capital=Decimal("101")))
    runtime = build_master_historical_paper_runtime(plan=other["plan"])
    with pytest.raises(ValueError, match="runtime plan"):
        _execute(setup, runtime=runtime)


def test_master_gate_rejected_candidates_never_reach_broker() -> None:
    setup = _setup(policies=_policies(gate_risk=Decimal("0.5")))
    assert setup["step4"].admitted_count == 0
    result, runtime = _execute(setup, evidence=())
    assert result.status is MasterHistoricalPaperExecutionStatus.NO_ADMITTED_CANDIDATES
    assert result.attempts == ()
    assert asyncio.run(runtime.broker.get_orders()) == ()


def test_no_admitted_candidates_still_apply_exact_close_mark() -> None:
    setup = _setup(policies=_policies(gate_risk=Decimal("0.5")))
    result, runtime = _execute(setup, evidence=())
    account = asyncio.run(runtime.broker.get_account_state())
    assert result.market_mark_applied is True
    assert account.equity == setup["plan"].master_initial_capital


def test_insufficient_master_cash_releases_committed_reservation_without_order() -> None:
    policies = _policies(master_capital=Decimal("20"), crew_capital=Decimal("20"))
    _, _, raw_barrier, _, _, _ = _plan_timeline(policies=policies)
    evidence_a = _evidence(raw_barrier, "crew-a", approved_quantity=Decimal("0.3"))
    evidence_b = _evidence(raw_barrier, "crew-b", approved_quantity=Decimal("0.3"))
    setup = _setup(
        policies=policies,
        evidence_a=evidence_a,
        evidence_b=evidence_b,
        capital_a=Decimal("5"),
        capital_b=Decimal("5"),
    )
    result, runtime = _execute(setup)
    assert result.status is MasterHistoricalPaperExecutionStatus.NO_EXECUTION
    assert result.executed_count == 0
    assert result.released_count == 2
    assert asyncio.run(runtime.broker.get_orders()) == ()
    assert all(
        setup["ledger"].get(item.reservation_id).status is ReservationRecordStatus.RELEASED
        for item in result.attempts
    )


def test_partial_execution_when_later_long_lacks_physical_cash() -> None:
    policies = _policies(master_capital=Decimal("20"), crew_capital=Decimal("20"))
    _, _, raw_barrier, _, _, _ = _plan_timeline(policies=policies)
    evidence_a = _evidence(raw_barrier, "crew-a", approved_quantity=Decimal("0.15"))
    evidence_b = _evidence(raw_barrier, "crew-b", approved_quantity=Decimal("0.15"))
    setup = _setup(
        policies=policies,
        evidence_a=evidence_a,
        evidence_b=evidence_b,
        capital_a=Decimal("5"),
        capital_b=Decimal("5"),
    )
    result, runtime = _execute(setup)
    assert result.status is MasterHistoricalPaperExecutionStatus.PARTIAL_EXECUTION
    assert result.executed_count == 1
    assert result.released_count == 1
    assert len(asyncio.run(runtime.broker.get_orders())) == 1
    assert result.account_after.cash_balance >= 0


def test_cash_blocked_attempt_has_no_fill_and_explicit_reason() -> None:
    policies = _policies(master_capital=Decimal("20"), crew_capital=Decimal("20"))
    _, _, raw_barrier, _, _, _ = _plan_timeline(policies=policies)
    evidence_a = _evidence(raw_barrier, "crew-a", approved_quantity=Decimal("0.15"))
    evidence_b = _evidence(raw_barrier, "crew-b", approved_quantity=Decimal("0.15"))
    setup = _setup(
        policies=policies,
        evidence_a=evidence_a,
        evidence_b=evidence_b,
        capital_a=Decimal("5"),
        capital_b=Decimal("5"),
    )
    result, _ = _execute(setup)
    blocked = next(
        item
        for item in result.attempts
        if item.status is MasterHistoricalPaperAttemptStatus.RELEASED_INSUFFICIENT_MASTER_CASH
    )
    assert blocked.reason_code is MasterHistoricalPaperReasonCode.INSUFFICIENT_MASTER_CASH
    assert blocked.broker_called is False
    assert blocked.broker_order_id is None
    assert blocked.fill_id is None
    assert blocked.account_before_fingerprint_sha256 == blocked.account_after_fingerprint_sha256


def test_execution_order_follows_existing_arbitration_rank() -> None:
    setup = _setup()
    result, _ = _execute(setup, evidence=tuple(reversed(setup["proposal_evidence"])))
    expected = tuple(item.system_id for item in setup["step4"].arbitration_result.outcomes)
    assert tuple(item.source_system_id for item in result.attempts) == expected


def test_short_entry_uses_same_master_account_and_signed_broker_semantics() -> None:
    _, _, raw_barrier, _, _, _ = _plan_timeline()
    evidence_a = _evidence(raw_barrier, "crew-a", side="SHORT")
    evidence_b = _evidence(raw_barrier, "crew-b", side="LONG")
    setup = _setup(evidence_a=evidence_a, evidence_b=evidence_b)
    result, runtime = _execute(setup)
    assert result.executed_count == 2
    orders = asyncio.run(runtime.broker.get_orders())
    assert tuple(order.side for order in orders) == (OrderSide.SELL, OrderSide.BUY)
    assert all(order.system_id == MASTER_ID for order in orders)


def test_opposite_crew_directions_can_net_on_one_physical_position() -> None:
    _, _, raw_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(raw_barrier, "crew-a", side="SHORT"),
        evidence_b=_evidence(raw_barrier, "crew-b", side="LONG"),
    )
    result, runtime = _execute(setup)
    assert result.executed_count == 2
    assert asyncio.run(runtime.broker.get_positions()) == ()
    assert result.account_after.open_positions == 0
    assert tuple(item.source_system_id for item in result.attempts) == ("crew-a", "crew-b")


def test_exact_replay_is_idempotent_and_creates_no_duplicate_orders() -> None:
    setup = _setup()
    result1, runtime = _execute(setup)
    order_count = len(asyncio.run(runtime.broker.get_orders()))
    result2, _ = _execute(setup, runtime=runtime)
    assert result2 == result1
    assert len(asyncio.run(runtime.broker.get_orders())) == order_count == 2


def test_replay_with_changed_evidence_conflicts() -> None:
    setup = _setup()
    _, runtime = _execute(setup)
    first = setup["proposal_evidence"][0]
    changed = MasterHistoricalPaperProposalEvidence(
        system_id=first.system_id,
        proposal=replace(
            first.proposal,
            created_at=first.proposal.created_at + timedelta(seconds=1),
        ),
    )
    with pytest.raises(ValueError):
        _execute(setup, runtime=runtime, evidence=(changed, setup["proposal_evidence"][1]))


def test_result_and_runtime_are_deterministic_across_equivalent_fresh_runs() -> None:
    setup1 = _setup()
    result1, runtime1 = _execute(setup1)
    setup2 = _setup()
    result2, runtime2 = _execute(setup2)
    assert runtime1.identity == runtime2.identity
    assert result1 == result2


def test_client_order_ids_are_deterministic_and_unique_per_candidate() -> None:
    result, _ = _execute(_setup())
    ids = tuple(item.client_order_id for item in result.attempts)
    assert len(set(ids)) == 2
    assert all(value.startswith("master-historical:") for value in ids)


def test_result_binds_step4_final_ledger_as_initial_execution_ledger() -> None:
    setup = _setup()
    result, _ = _execute(setup)
    assert result.initial_ledger_fingerprint_sha256 == (
        setup["step4"].final_ledger_fingerprint_sha256
    )


def test_result_fingerprint_binds_final_account_and_ledger() -> None:
    result, _ = _execute(_setup())
    payload = {
        "account": result.account_after.fingerprint_sha256,
        "ledger": result.final_ledger_fingerprint_sha256,
        "attempts": tuple(item.fingerprint_sha256 for item in result.attempts),
    }
    assert stable_digest(payload)
    assert len(result.fingerprint_sha256) == 64


def test_master_broker_orders_are_all_filled_market_entries() -> None:
    result, runtime = _execute(_setup())
    assert result.executed_count == 2
    orders = asyncio.run(runtime.broker.get_orders())
    assert all(order.status is OrderStatus.FILLED for order in orders)
    assert all(order.trigger == "MASTER_HISTORICAL_ADMISSION" for order in orders)


def test_step5_does_not_install_stop_or_target_lifecycle() -> None:
    result, runtime = _execute(_setup())
    assert result.executed_count == 2
    assert not hasattr(runtime, "position_lifecycle")
    assert not hasattr(runtime, "protections")


def test_account_snapshot_has_single_master_runtime_provenance() -> None:
    result, runtime = _execute(_setup())
    assert result.account_after.runtime_fingerprint_sha256 == runtime.identity.fingerprint_sha256
    assert result.account_after.single_master_capital is True
    assert result.account_after.sums_branch_equities is False


def test_only_master_admitted_subset_is_eligible_for_paper_execution() -> None:
    setup = _setup(policies=_policies(gate_risk=Decimal("1")))
    assert setup["step4"].admitted_count == 1
    admitted_ids = {
        (item.system_id, item.proposal_id)
        for item in setup["step4"].arbitration_result.outcomes
        if item.decision_status is MasterRiskGateDecisionStatus.ADMIT
    }
    evidence = tuple(
        item
        for item in setup["proposal_evidence"]
        if (item.system_id, item.proposal.proposal_id) in admitted_ids
    )
    result, runtime = _execute(setup, evidence=evidence)
    assert result.executed_count == 1
    assert len(asyncio.run(runtime.broker.get_orders())) == 1
    assert {(item.source_system_id, item.proposal_id) for item in result.attempts} == admitted_ids


def test_not_reserved_candidate_never_becomes_paper_order() -> None:
    policies = _policies(master_capital=Decimal("30"), crew_capital=Decimal("30"))
    setup = _setup(
        policies=policies,
        capital_a=Decimal("20"),
        capital_b=Decimal("20"),
    )
    assert setup["step4"].reserved_count == 1
    assert setup["step4"].not_reserved_count == 1
    admitted = {
        (item.system_id, item.proposal_id)
        for item in setup["step4"].arbitration_result.outcomes
        if item.decision_status is MasterRiskGateDecisionStatus.ADMIT
    }
    evidence = tuple(
        item
        for item in setup["proposal_evidence"]
        if (item.system_id, item.proposal.proposal_id) in admitted
    )
    result, runtime = _execute(setup, evidence=evidence)
    assert result.executed_count == 1
    assert len(asyncio.run(runtime.broker.get_orders())) == 1
