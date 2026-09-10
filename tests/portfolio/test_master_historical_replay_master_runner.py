from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

import pytest

from app.evaluation.models import MetricStatus
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
from app.portfolio.historical_replay_master_runner import (
    MasterHistoricalCoordinatedReplayStatus,
    build_master_historical_barrier_input,
    run_master_historical_coordinated_replay,
)
from app.portfolio.historical_replay_preexecution import HistoricalCrewPreExecutionEvidence
from app.portfolio.historical_replay_reservation_arbitration import (
    build_master_historical_capital_requirement,
)
from app.portfolio.reservation import ReservationRecordStatus
from app.portfolio.risk_gate import build_master_risk_gate_policy
from app.services.backtest.dataset import DatasetRef
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
    entry_price: Decimal
    stop_price: Decimal
    targets: tuple[Decimal, ...]
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
    specs = (
        ("100", "101", "99", "100"),
        ("100", "102", "99", "100"),
        ("100", "105", "99", "104"),
        ("104", "105", "100", "101"),
        ("101", "103", "100", "102"),
    )
    rows = []
    for index, (open_, high, low, close) in enumerate(specs):
        open_at = BASE + timedelta(hours=index)
        rows.append(
            {
                "symbol": "BTCUSDC",
                "timeframe": "1h",
                "open_time": open_at,
                "close_time": open_at + timedelta(hours=1),
                "open": Decimal(open_),
                "high": Decimal(high),
                "low": Decimal(low),
                "close": Decimal(close),
                "volume": Decimal("10"),
                "is_closed": True,
            }
        )
    return tuple(rows)


def _dataset() -> DatasetRef:
    return DatasetRef.from_candles(
        _candles(),
        symbol="BTCUSDC",
        timeframe="1h",
        source="fixture",
    )


def _policies(
    *,
    master_capital: Decimal = Decimal("100"),
    crew_capital: Decimal = Decimal("70"),
    crew_risk: Decimal = Decimal("20"),
    crew_gross: Decimal = Decimal("200"),
    gate_risk: Decimal = Decimal("20"),
    gate_gross: Decimal = Decimal("400"),
):
    from app.portfolio.models import PortfolioMemberRef

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
    period_start = BASE + timedelta(hours=1)
    period_end = BASE + timedelta(hours=5)
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
    return plan, timeline, allocation, gate, arbitration


def _context(barrier, system_id: str) -> FakeContext:
    close = Decimal(str(_candles()[barrier.candle_index - 1]["close"]))
    return FakeContext(
        snapshot_id=f"snapshot:{barrier.sequence}:{system_id}",
        symbol="BTCUSDC",
        timeframe="1h",
        observed_at=barrier.observed_at,
        close=close,
    )


def _no_op(barrier, system_id: str) -> HistoricalCrewPreExecutionEvidence:
    return HistoricalCrewPreExecutionEvidence(
        system_id=system_id,
        market_context=_context(barrier, system_id),
    )


def _trade(
    barrier,
    system_id: str,
    *,
    side: str,
    stop: Decimal,
    target: Decimal,
    quantity: Decimal = Decimal("0.1"),
    approved_risk: Decimal = Decimal("1"),
    approved_notional: Decimal | None = None,
) -> HistoricalCrewPreExecutionEvidence:
    context = _context(barrier, system_id)
    opportunity = FakeOpportunity(
        opportunity_id=f"opp:{barrier.sequence}:{system_id}",
        snapshot_id=context.snapshot_id,
        system_id=system_id,
        symbol=context.symbol,
        timeframe=context.timeframe,
    )
    proposal = FakeProposal(
        proposal_id=f"proposal:{barrier.sequence}:{system_id}",
        opportunity_id=opportunity.opportunity_id,
        source_snapshot_id=context.snapshot_id,
        system_id=system_id,
        symbol=context.symbol,
        timeframe=context.timeframe,
        side=side,
        entry_price=context.close,
        stop_price=stop,
        targets=(target,),
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
    notional = approved_notional or context.close * quantity
    decision = RiskDecision(
        proposal_id=proposal.proposal_id,
        status=RiskDecisionStatus.APPROVED,
        reason_codes=(RiskReasonCode.APPROVED,),
        approved_quantity=quantity,
        approved_risk_amount=approved_risk,
        approved_notional=notional,
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


class ScriptedInputSource:
    def __init__(self, mode: str = "round_trip") -> None:
        self.mode = mode
        self.calls = []

    async def input_for_barrier(self, *, barrier, portfolio_snapshot):
        self.calls.append((barrier.sequence, portfolio_snapshot.fingerprint_sha256))
        evidence = self._evidence(barrier)
        requirements = []
        for item in evidence:
            decision = item.local_risk_decision
            proposal = getattr(item.orchestration_result, "trade_proposal", None)
            if decision is None or proposal is None or not decision.is_authorized:
                continue
            requirements.append(
                build_master_historical_capital_requirement(
                    system_id=item.system_id,
                    proposal_id=str(proposal.proposal_id),
                    capital_amount=Decimal("20"),
                    source_ref="operator:scripted-test",
                )
            )
        return build_master_historical_barrier_input(
            barrier=barrier,
            portfolio_snapshot=portfolio_snapshot,
            crew_evidence=tuple(evidence),
            capital_requirements=tuple(requirements),
            source_ref="scripted:test",
        )

    def _evidence(self, barrier):
        if self.mode == "round_trip":
            if barrier.candle_index == 2:
                return (
                    _trade(
                        barrier,
                        "crew-a",
                        side="LONG",
                        stop=Decimal("98"),
                        target=Decimal("104"),
                    ),
                    _no_op(barrier, "crew-b"),
                )
            if barrier.candle_index == 3:
                return (
                    _no_op(barrier, "crew-a"),
                    _trade(
                        barrier,
                        "crew-b",
                        side="SHORT",
                        stop=Decimal("108"),
                        target=Decimal("101"),
                    ),
                )
        if self.mode == "drift_reject":
            if barrier.candle_index == 2:
                return (
                    _trade(
                        barrier,
                        "crew-a",
                        side="LONG",
                        stop=Decimal("90"),
                        target=Decimal("120"),
                    ),
                    _no_op(barrier, "crew-b"),
                )
            if barrier.candle_index == 3:
                return (
                    _no_op(barrier, "crew-a"),
                    _trade(
                        barrier,
                        "crew-b",
                        side="LONG",
                        stop=Decimal("100"),
                        target=Decimal("120"),
                    ),
                )
        if self.mode == "opposing" and barrier.candle_index == 2:
            return (
                _trade(
                    barrier,
                    "crew-a",
                    side="LONG",
                    stop=Decimal("90"),
                    target=Decimal("120"),
                ),
                _trade(
                    barrier,
                    "crew-b",
                    side="SHORT",
                    stop=Decimal("110"),
                    target=Decimal("80"),
                ),
            )
        if self.mode == "cash_block" and barrier.candle_index == 2:
            return (
                _trade(
                    barrier,
                    "crew-a",
                    side="LONG",
                    stop=Decimal("98"),
                    target=Decimal("120"),
                    quantity=Decimal("2"),
                    approved_risk=Decimal("5"),
                    approved_notional=Decimal("200"),
                ),
                _no_op(barrier, "crew-b"),
            )
        if self.mode == "two_candidates" and barrier.candle_index == 2:
            return (
                _trade(
                    barrier,
                    "crew-a",
                    side="LONG",
                    stop=Decimal("98"),
                    target=Decimal("120"),
                ),
                _trade(
                    barrier,
                    "crew-b",
                    side="LONG",
                    stop=Decimal("98"),
                    target=Decimal("120"),
                ),
            )
        return (_no_op(barrier, "crew-a"), _no_op(barrier, "crew-b"))


class StaleInputSource(ScriptedInputSource):
    async def input_for_barrier(self, *, barrier, portfolio_snapshot):
        supplied = await super().input_for_barrier(
            barrier=barrier,
            portfolio_snapshot=portfolio_snapshot,
        )
        return replace(
            supplied,
            portfolio_snapshot_fingerprint_sha256="0" * 64,
            fingerprint_sha256=supplied.fingerprint_sha256,
        )


def _run(*, source=None, policies=None, candles=None):
    plan, timeline, allocation, gate, arbitration = _plan_timeline(policies=policies)
    result = asyncio.run(
        run_master_historical_coordinated_replay(
            plan=plan,
            timeline=timeline,
            allocation_policy=allocation,
            gate_policy=gate,
            arbitration_policy=arbitration,
            candles=candles or _candles(),
            input_source=source or ScriptedInputSource(),
        )
    )
    return result, plan, timeline


def test_full_replay_completes_every_barrier_and_decision_close() -> None:
    result, _, timeline = _run()
    assert result.status is MasterHistoricalCoordinatedReplayStatus.COMPLETED
    assert result.processed_barrier_count == len(timeline.barriers)
    assert len(result.lifecycle_results) == len(timeline.barriers)
    assert len(result.equity_curve) == len(timeline.barriers)
    assert len(result.decision_cycles) == timeline.evaluation_candle_count


def test_input_source_is_called_only_for_decision_eligible_closes() -> None:
    source = ScriptedInputSource()
    result, _, timeline = _run(source=source)
    expected = tuple(
        barrier.sequence
        for barrier in timeline.barriers
        if barrier.phase is MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE
        and barrier.decision_eligible
    )
    assert tuple(sequence for sequence, _ in source.calls) == expected
    assert len(source.calls) == result.evaluation.decision_cycle_count


def test_each_input_binds_exact_current_master_snapshot() -> None:
    source = ScriptedInputSource()
    result, _, _ = _run(source=source)
    assert tuple(fp for _, fp in source.calls) == tuple(
        cycle.portfolio_before.fingerprint_sha256 for cycle in result.decision_cycles
    )
    assert tuple(
        cycle.barrier_input.portfolio_snapshot_fingerprint_sha256
        for cycle in result.decision_cycles
    ) == tuple(
        cycle.portfolio_before.fingerprint_sha256 for cycle in result.decision_cycles
    )


def test_round_trip_entries_exit_through_virtual_lifecycle() -> None:
    result, _, _ = _run()
    evaluation = result.evaluation
    assert evaluation.paper_entry_count == 2
    assert evaluation.closed_lot_count == 2
    assert evaluation.open_lot_count == 0
    assert evaluation.master_admitted_count == 2
    assert evaluation.master_rejected_count == 0
    assert result.final_book.open_lots == ()
    assert len(result.final_book.closed_lots) == 2


def test_closed_virtual_lots_keep_crew_attribution() -> None:
    result, _, _ = _run()
    crews = {item.system_id: item for item in result.evaluation.crew_evaluations}
    assert crews["crew-a"].entry_count == 1
    assert crews["crew-a"].closed_lot_count == 1
    assert crews["crew-b"].entry_count == 1
    assert crews["crew-b"].closed_lot_count == 1


def test_final_committed_reservations_match_open_lots() -> None:
    result, _, _ = _run()
    committed = {
        item.reservation_id
        for item in result.final_ledger.reservations
        if item.status is ReservationRecordStatus.COMMITTED
    }
    assert committed == {lot.reservation_id for lot in result.final_book.open_lots}
    assert not any(
        item.status is ReservationRecordStatus.RESERVED
        for item in result.final_ledger.reservations
    )


def test_master_initial_capital_never_sums_source_branch_balances() -> None:
    result, plan, _ = _run()
    assert tuple(crew.source_branch_initial_balance for crew in plan.crews) == (
        Decimal("100"),
        Decimal("250"),
    )
    assert result.opening_snapshot.master_capital.equity == Decimal("100")
    assert result.evaluation.initial_capital == Decimal("100")
    assert result.single_master_capital is True
    assert result.sums_branch_equities is False
    assert result.uses_branch_brokers is False


def test_master_account_net_pnl_is_final_equity_minus_single_initial_capital() -> None:
    result, _, _ = _run()
    evaluation = result.evaluation
    assert evaluation.master_account_net_pnl == evaluation.final_equity - Decimal("100")
    assert evaluation.return_pct.status is MetricStatus.AVAILABLE
    assert evaluation.return_pct.value == evaluation.master_account_net_pnl / Decimal("100")


def test_drawdown_reuses_existing_evaluation_metric_contract() -> None:
    result, _, _ = _run()
    evaluation = result.evaluation
    assert evaluation.max_drawdown_abs.status is MetricStatus.AVAILABLE
    assert evaluation.max_drawdown_pct.status is MetricStatus.AVAILABLE
    assert evaluation.max_drawdown_abs.value is not None
    assert evaluation.max_drawdown_abs.value >= Decimal("0")


def test_trade_statistics_are_based_on_closed_virtual_lots() -> None:
    result, _, _ = _run()
    evaluation = result.evaluation
    assert evaluation.closed_lot_count == (
        evaluation.winning_lots
        + evaluation.losing_lots
        + evaluation.breakeven_lots
    )
    assert evaluation.win_rate.status is MetricStatus.AVAILABLE
    assert evaluation.expectancy.status is MetricStatus.AVAILABLE


def test_ai_economics_remain_explicitly_unavailable() -> None:
    result, _, _ = _run()
    assert result.evaluation.ai_cost_eur.status is MetricStatus.UNAVAILABLE
    assert result.evaluation.ai_cost_eur.reason == "AI_USAGE_NOT_SUPPLIED_BY_STEP7_INPUT_PORT"
    assert result.evaluation.economic_net.status is MetricStatus.UNAVAILABLE


def test_opposing_open_lots_preserve_gross_exposure_without_branch_brokers() -> None:
    result, _, _ = _run(source=ScriptedInputSource("opposing"))
    assert result.final_book.net_signed_quantity == Decimal("0")
    assert len(result.final_book.open_lots) == 2
    assert result.final_book.virtual_gross_exposure_amount > Decimal("0")
    assert result.evaluation.open_lot_count == 2
    assert result.evaluation.final_virtual_gross_exposure_amount == (
        result.final_book.virtual_gross_exposure_amount
    )


def test_opposing_open_lots_keep_two_committed_reservations() -> None:
    result, _, _ = _run(source=ScriptedInputSource("opposing"))
    committed = tuple(
        item
        for item in result.final_ledger.reservations
        if item.status is ReservationRecordStatus.COMMITTED
    )
    assert len(committed) == 2
    assert {item.request.system_id for item in committed} == {"crew-a", "crew-b"}


def test_master_gate_rejection_is_counted_and_never_executed() -> None:
    policies = _policies(gate_risk=Decimal("1.5"))
    result, _, _ = _run(
        source=ScriptedInputSource("two_candidates"),
        policies=policies,
    )
    evaluation = result.evaluation
    assert evaluation.local_authorized_candidate_count == 2
    assert evaluation.master_admitted_count == 1
    assert evaluation.master_rejected_count == 1
    assert evaluation.paper_entry_count == 1


def test_physical_cash_block_is_counted_and_releases_capacity() -> None:
    policies = _policies(
        crew_capital=Decimal("70"),
        crew_risk=Decimal("50"),
        crew_gross=Decimal("500"),
        gate_risk=Decimal("50"),
        gate_gross=Decimal("1000"),
    )
    result, _, _ = _run(
        source=ScriptedInputSource("cash_block"),
        policies=policies,
    )
    evaluation = result.evaluation
    assert evaluation.master_admitted_count == 1
    assert evaluation.paper_entry_count == 0
    assert evaluation.paper_cash_blocked_count == 1
    assert evaluation.open_lot_count == 0
    assert not any(
        item.status is ReservationRecordStatus.COMMITTED
        for item in result.final_ledger.reservations
    )


def test_no_trade_cycles_are_still_audited() -> None:
    result, _, timeline = _run(source=ScriptedInputSource("none"))
    assert len(result.decision_cycles) == timeline.evaluation_candle_count
    assert result.evaluation.local_authorized_candidate_count == 0
    assert result.evaluation.master_admitted_count == 0
    assert result.evaluation.paper_entry_count == 0
    assert result.evaluation.closed_lot_count == 0


def test_no_closed_lots_expose_unavailable_trade_statistics() -> None:
    result, _, _ = _run(source=ScriptedInputSource("none"))
    assert result.evaluation.win_rate.status is MetricStatus.UNAVAILABLE
    assert result.evaluation.profit_factor.status is MetricStatus.UNAVAILABLE
    assert result.evaluation.expectancy.status is MetricStatus.UNAVAILABLE


def test_replay_is_deterministic_across_fresh_runs() -> None:
    first, _, _ = _run(source=ScriptedInputSource())
    second, _, _ = _run(source=ScriptedInputSource())
    assert second.fingerprint_sha256 == first.fingerprint_sha256
    assert second.evaluation.fingerprint_sha256 == first.evaluation.fingerprint_sha256
    assert second.final_book.fingerprint_sha256 == first.final_book.fingerprint_sha256
    assert second.final_ledger.fingerprint_sha256 == first.final_ledger.fingerprint_sha256


def test_changed_candle_fails_before_input_source_is_called() -> None:
    source = ScriptedInputSource()
    changed = list(_candles())
    changed[2] = dict(changed[2], close=Decimal("103"))
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        _run(source=source, candles=tuple(changed))
    assert source.calls == []


def test_input_bound_to_stale_portfolio_fails_closed() -> None:
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        _run(source=StaleInputSource())


def test_policy_fingerprint_change_fails_before_replay() -> None:
    plan, timeline, allocation, _, arbitration = _plan_timeline()
    changed = build_master_risk_gate_policy(
        master_portfolio_id=MASTER_ID,
        gate_policy_id="gate-v1-changed",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        max_total_open_risk_amount=Decimal("19"),
        max_total_gross_exposure_amount=Decimal("400"),
    )
    with pytest.raises(ValueError, match="gate policy changed"):
        asyncio.run(
            run_master_historical_coordinated_replay(
                plan=plan,
                timeline=timeline,
                allocation_policy=allocation,
                gate_policy=changed,
                arbitration_policy=arbitration,
                candles=_candles(),
                input_source=ScriptedInputSource(),
            )
        )


def test_result_has_no_risk_admission_or_live_authority() -> None:
    result, _, _ = _run()
    assert result.risk_authority is False
    assert result.admission_authority is False
    assert result.live_authority is False
    assert result.auto_execute_live is False
    assert result.evaluation.risk_authority is False
    assert result.evaluation.admission_authority is False
    assert result.evaluation.live_authority is False


def test_barrier_input_has_no_execution_authority() -> None:
    result, _, _ = _run()
    item = result.decision_cycles[0].barrier_input
    assert item.risk_authority is False
    assert item.admission_authority is False
    assert item.broker_authority is False
    assert item.live_authority is False


def test_equity_curve_is_contiguous_and_fingerprint_stable() -> None:
    result, _, _ = _run()
    assert tuple(point.barrier_sequence for point in result.equity_curve) == tuple(
        range(1, result.processed_barrier_count + 1)
    )
    assert all(len(point.fingerprint_sha256) == 64 for point in result.equity_curve)


def test_decision_cycles_bind_all_existing_step_fingerprints() -> None:
    result, _, _ = _run()
    for cycle in result.decision_cycles:
        assert cycle.reservation_arbitration.decision_barrier_fingerprint_sha256 == (
            cycle.decision_barrier.fingerprint_sha256
        )
        assert cycle.paper_execution.decision_barrier_fingerprint_sha256 == (
            cycle.decision_barrier.fingerprint_sha256
        )
        assert cycle.lot_registration.execution_result_fingerprint_sha256 == (
            cycle.paper_execution.fingerprint_sha256
        )


def test_final_crew_metrics_sum_to_master_virtual_lot_counts() -> None:
    result, _, _ = _run()
    crews = result.evaluation.crew_evaluations
    assert sum(item.entry_count for item in crews) == (
        result.evaluation.closed_lot_count + result.evaluation.open_lot_count
    )
    assert sum(item.closed_lot_count for item in crews) == result.evaluation.closed_lot_count
    assert sum(item.open_lot_count for item in crews) == result.evaluation.open_lot_count


def test_lifecycle_exits_are_applied_before_same_close_new_admission() -> None:
    result, _, _ = _run()
    second = next(
        cycle for cycle in result.decision_cycles if cycle.decision_barrier.barrier_sequence == 6
    )
    assert second.portfolio_before.total_open_positions == 0
    assert second.portfolio_after.total_open_positions == 1
    assert second.paper_execution.executed_count == 1


def test_marked_exposure_above_committed_amount_fails_closed_for_new_candidate() -> None:
    result, _, _ = _run(source=ScriptedInputSource("drift_reject"))
    evaluation = result.evaluation
    assert evaluation.local_authorized_candidate_count == 2
    assert evaluation.master_admitted_count == 1
    assert evaluation.master_rejected_count == 1
    assert evaluation.paper_entry_count == 1
    assert evaluation.open_lot_count == 1
    second = next(
        cycle for cycle in result.decision_cycles if cycle.decision_barrier.barrier_sequence == 6
    )
    assert second.reservation_arbitration.master_rejected_count == 1
