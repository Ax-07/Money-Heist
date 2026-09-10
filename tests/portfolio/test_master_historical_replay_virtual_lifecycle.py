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
    MasterHistoricalPaperProposalEvidence,
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
from app.portfolio.historical_replay_virtual_lifecycle import (
    MasterHistoricalLifecycleStatus,
    MasterHistoricalVirtualLotRegistrationStatus,
    MasterHistoricalVirtualLotStatus,
    build_master_historical_virtual_lot_book,
    build_master_historical_virtual_portfolio_snapshot,
    process_master_historical_virtual_lot_barrier,
    register_master_historical_virtual_lots,
)
from app.portfolio.models import (
    CrewExposureSnapshot,
    MasterCapitalSnapshot,
    PortfolioMemberRef,
    SnapshotDataStatus,
)
from app.portfolio.reconciliation import (
    ReservationReconciliationStatus,
    build_reservation_reconciliation_report,
)
from app.portfolio.reservation import MasterReservationLedger, ReservationRecordStatus
from app.portfolio.risk_gate import build_master_risk_gate_policy
from app.portfolio.snapshot import build_master_portfolio_snapshot
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.intrabar import HistoricalExitReason
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
    entry_barrier = next(
        item
        for item in timeline.barriers
        if item.phase is MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE
        and item.decision_eligible
    )
    return plan, timeline, entry_barrier, allocation, gate, arbitration


def _barrier_candle(barrier) -> dict[str, object]:
    return next(
        row
        for row in _candles()
        if row["open_time"].astimezone(UTC) == barrier.candle_open_at
    )


def _evidence(
    barrier,
    system_id: str,
    *,
    side: str = "LONG",
    stop_price: Decimal | None = None,
    targets: tuple[Decimal, ...] | None = None,
    approved_quantity: Decimal = Decimal("0.1"),
    approved_risk: Decimal = Decimal("1"),
    approved_notional: Decimal = Decimal("10.2"),
) -> HistoricalCrewPreExecutionEvidence:
    candle = _barrier_candle(barrier)
    entry = Decimal(str(candle["close"]))
    if stop_price is None:
        stop_price = entry - Decimal("3") if side == "LONG" else entry + Decimal("3")
    if targets is None:
        targets = (
            entry + Decimal("3") if side == "LONG" else entry - Decimal("3"),
        )
    context = FakeContext(
        snapshot_id=f"snapshot:{barrier.candle_index}:{system_id}",
        symbol="BTCUSDC",
        timeframe="1h",
        observed_at=barrier.observed_at,
        close=entry,
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
        entry_price=entry,
        stop_price=stop_price,
        targets=targets,
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
    evidence_a=None,
    evidence_b=None,
    policies=None,
    capital_a: Decimal = Decimal("20"),
    capital_b: Decimal = Decimal("20"),
):
    plan, timeline, entry_barrier, allocation, gate, arbitration = _plan_timeline(
        policies=policies
    )
    evidence_a = evidence_a or _evidence(entry_barrier, "crew-a")
    evidence_b = evidence_b or _evidence(entry_barrier, "crew-b")
    decision_barrier = build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=entry_barrier,
        crew_evidence=(evidence_a, evidence_b),
    )
    opening = _snapshot(observed_at=BASE, equity=plan.master_initial_capital)
    current = _snapshot(observed_at=entry_barrier.observed_at, equity=plan.master_initial_capital)
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
    all_proposal_evidence = tuple(
        MasterHistoricalPaperProposalEvidence(
            system_id=system_id,
            proposal=proposals[system_id],
        )
        for system_id in sorted(proposals)
    )
    admitted_keys = set()
    if step4.arbitration_result is not None:
        admitted_keys = {
            (outcome.system_id, outcome.proposal_id)
            for outcome in step4.arbitration_result.outcomes
            if outcome.decision_status.value == "ADMIT"
        }
    proposal_evidence = tuple(
        item
        for item in all_proposal_evidence
        if (item.system_id, str(item.proposal.proposal_id)) in admitted_keys
    )
    runtime = build_master_historical_paper_runtime(plan=plan)
    step5 = asyncio.run(
        execute_master_historical_paper_admissions(
            runtime=runtime,
            plan=plan,
            timeline=timeline,
            decision_barrier=decision_barrier,
            reservation_arbitration=step4,
            ledger=ledger,
            candle=_barrier_candle(entry_barrier),
            proposal_evidence=proposal_evidence,
        )
    )
    book = build_master_historical_virtual_lot_book(plan=plan, runtime=runtime)
    executed_keys = {
        (attempt.source_system_id, attempt.proposal_id)
        for attempt in step5.attempts
        if attempt.broker_order_id is not None
    }
    registration_evidence = tuple(
        item
        for item in proposal_evidence
        if (item.system_id, str(item.proposal.proposal_id)) in executed_keys
    )
    registration = asyncio.run(
        register_master_historical_virtual_lots(
            book=book,
            plan=plan,
            timeline=timeline,
            decision_barrier=decision_barrier,
            execution_result=step5,
            ledger=ledger,
            candle=_barrier_candle(entry_barrier),
            proposal_evidence=registration_evidence,
        )
    )
    next_open = timeline.barriers[entry_barrier.sequence]
    next_close = timeline.barriers[entry_barrier.sequence + 1]
    return {
        "plan": plan,
        "timeline": timeline,
        "entry_barrier": entry_barrier,
        "decision_barrier": decision_barrier,
        "allocation": allocation,
        "ledger": ledger,
        "runtime": runtime,
        "step5": step5,
        "book": book,
        "registration": registration,
        "proposal_evidence": proposal_evidence,
        "registration_evidence": registration_evidence,
        "next_open": next_open,
        "next_close": next_close,
        "next_candle": _barrier_candle(next_open),
    }


def _process(setup, barrier, *, candle=None):
    return asyncio.run(
        process_master_historical_virtual_lot_barrier(
            book=setup["book"],
            plan=setup["plan"],
            timeline=setup["timeline"],
            barrier=barrier,
            ledger=setup["ledger"],
            candle=candle or _barrier_candle(barrier),
        )
    )


def test_book_uses_one_master_runtime_and_no_branch_capital() -> None:
    setup = _setup()
    book = setup["book"]
    assert book.runtime.broker.config.system_id == MASTER_ID
    assert book.runtime.broker.config.initial_balance == Decimal("100")
    assert book.risk_authority is False
    assert book.admission_authority is False
    assert book.live_authority is False


def test_registration_creates_one_open_virtual_lot_per_executed_entry() -> None:
    setup = _setup()
    assert setup["registration"].status is MasterHistoricalVirtualLotRegistrationStatus.REGISTERED
    assert len(setup["book"].open_lots) == 2
    assert tuple(lot.source_system_id for lot in setup["book"].open_lots) == (
        "crew-a",
        "crew-b",
    )


def test_virtual_lots_bind_exact_committed_reservations() -> None:
    setup = _setup()
    for lot in setup["book"].open_lots:
        record = setup["ledger"].get(lot.reservation_id)
        assert record.status is ReservationRecordStatus.COMMITTED
        assert record.request.system_id == lot.source_system_id
        assert record.request.request_ref == lot.proposal_id
        assert record.request.open_risk_amount == lot.reserved_open_risk_amount


def test_registration_is_idempotent_without_duplicate_lots() -> None:
    setup = _setup()
    before = setup["book"].lots
    again = asyncio.run(
        register_master_historical_virtual_lots(
            book=setup["book"],
            plan=setup["plan"],
            timeline=setup["timeline"],
            decision_barrier=setup["decision_barrier"],
            execution_result=setup["step5"],
            ledger=setup["ledger"],
            candle=_barrier_candle(setup["entry_barrier"]),
            proposal_evidence=setup["registration_evidence"],
        )
    )
    assert again == setup["registration"]
    assert setup["book"].lots == before


def test_registration_rejects_changed_proposal_evidence() -> None:
    setup = _setup()
    fresh_book = build_master_historical_virtual_lot_book(
        plan=setup["plan"], runtime=setup["runtime"]
    )
    first = setup["registration_evidence"][0]
    changed = MasterHistoricalPaperProposalEvidence(
        system_id=first.system_id,
        proposal=replace(first.proposal, stop_price=first.proposal.stop_price - Decimal("1")),
    )
    evidence = (changed, setup["registration_evidence"][1])
    with pytest.raises(ValueError, match="proposal fingerprint mismatch"):
        asyncio.run(
            register_master_historical_virtual_lots(
                book=fresh_book,
                plan=setup["plan"],
                timeline=setup["timeline"],
                decision_barrier=setup["decision_barrier"],
                execution_result=setup["step5"],
                ledger=setup["ledger"],
                candle=_barrier_candle(setup["entry_barrier"]),
                proposal_evidence=evidence,
            )
        )


def test_opposing_crews_can_net_physically_while_lots_remain_separate() -> None:
    _, _, entry_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(entry_barrier, "crew-a", side="LONG"),
        evidence_b=_evidence(entry_barrier, "crew-b", side="SHORT"),
    )
    physical = asyncio.run(setup["runtime"].broker.get_positions())
    assert physical == ()
    assert len(setup["book"].open_lots) == 2
    snapshot = setup["book"].snapshot(
        observed_at=setup["entry_barrier"].observed_at,
        mark_price=Decimal("102"),
    )
    assert snapshot.net_signed_quantity == Decimal("0")
    assert snapshot.virtual_gross_exposure_amount == Decimal("20.4")


def test_entry_candle_is_not_reprocessed_after_registration() -> None:
    setup = _setup()
    with pytest.raises(ValueError, match="processed contiguously"):
        _process(setup, setup["entry_barrier"])


def test_open_phase_does_not_apply_non_gap_intrabar_stop() -> None:
    _, _, entry_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(
            entry_barrier,
            "crew-a",
            stop_price=Decimal("101"),
            targets=(Decimal("105"),),
        ),
        evidence_b=_evidence(
            entry_barrier,
            "crew-b",
            stop_price=Decimal("99"),
            targets=(Decimal("106"),),
        ),
    )
    result = _process(setup, setup["next_open"])
    assert result.status is MasterHistoricalLifecycleStatus.PROCESSED_NO_EXIT
    assert len(setup["book"].open_lots) == 2


def test_long_stop_intrabar_exits_at_close_phase_and_releases_reservation() -> None:
    _, _, entry_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(
            entry_barrier,
            "crew-a",
            stop_price=Decimal("101"),
            targets=(Decimal("105"),),
        ),
        evidence_b=_evidence(
            entry_barrier,
            "crew-b",
            stop_price=Decimal("99"),
            targets=(Decimal("106"),),
        ),
    )
    _process(setup, setup["next_open"])
    result = _process(setup, setup["next_close"])
    assert result.status is MasterHistoricalLifecycleStatus.PROCESSED_WITH_EXITS
    assert len(result.exit_events) == 1
    event = result.exit_events[0]
    assert event.source_system_id == "crew-a"
    assert event.reason is HistoricalExitReason.STOP_INTRABAR
    assert event.reference_price == Decimal("101")
    assert setup["ledger"].get(event.reservation_id).status is ReservationRecordStatus.RELEASED


def test_long_target_intrabar_uses_exact_target_limit_fill() -> None:
    _, _, entry_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(
            entry_barrier,
            "crew-a",
            stop_price=Decimal("99"),
            targets=(Decimal("104"),),
        ),
        evidence_b=_evidence(
            entry_barrier,
            "crew-b",
            stop_price=Decimal("98"),
            targets=(Decimal("106"),),
        ),
    )
    _process(setup, setup["next_open"])
    result = _process(setup, setup["next_close"])
    event = result.exit_events[0]
    assert event.reason is HistoricalExitReason.TARGET_INTRABAR
    assert event.reference_price == Decimal("104")
    assert event.fill_price == Decimal("104")
    assert event.exit_fee > Decimal("0")


def test_long_gap_stop_is_resolved_at_open() -> None:
    _, _, entry_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(
            entry_barrier,
            "crew-a",
            stop_price=Decimal("102.003"),
            targets=(Decimal("105"),),
        ),
        evidence_b=_evidence(
            entry_barrier,
            "crew-b",
            stop_price=Decimal("99"),
            targets=(Decimal("106"),),
        ),
    )
    result = _process(setup, setup["next_open"])
    assert len(result.exit_events) == 1
    event = result.exit_events[0]
    assert event.reason is HistoricalExitReason.STOP_GAP
    assert event.reference_price == Decimal("102")


def test_short_stop_intrabar_exits_with_buy_and_releases_reservation() -> None:
    _, _, entry_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(
            entry_barrier,
            "crew-a",
            side="SHORT",
            stop_price=Decimal("103"),
            targets=(Decimal("99"),),
        ),
        evidence_b=_evidence(
            entry_barrier,
            "crew-b",
            stop_price=Decimal("98"),
            targets=(Decimal("106"),),
        ),
    )
    _process(setup, setup["next_open"])
    result = _process(setup, setup["next_close"])
    event = next(item for item in result.exit_events if item.source_system_id == "crew-a")
    assert event.reason is HistoricalExitReason.STOP_INTRABAR
    assert event.fill_price > event.reference_price
    assert setup["ledger"].get(event.reservation_id).status is ReservationRecordStatus.RELEASED


def test_opposing_lot_exit_recreates_physical_net_of_remaining_lot() -> None:
    _, _, entry_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(
            entry_barrier,
            "crew-a",
            side="LONG",
            stop_price=Decimal("101"),
            targets=(Decimal("105"),),
        ),
        evidence_b=_evidence(
            entry_barrier,
            "crew-b",
            side="SHORT",
            stop_price=Decimal("106"),
            targets=(Decimal("99"),),
        ),
    )
    assert asyncio.run(setup["runtime"].broker.get_positions()) == ()
    _process(setup, setup["next_open"])
    _process(setup, setup["next_close"])
    open_lots = setup["book"].open_lots
    assert len(open_lots) == 1
    assert open_lots[0].side == "SHORT"
    positions = asyncio.run(setup["runtime"].broker.get_positions())
    assert len(positions) == 1
    assert positions[0].signed_quantity == Decimal("-0.1")


def test_two_lots_exiting_same_barrier_use_canonical_crew_order() -> None:
    _, _, entry_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(
            entry_barrier,
            "crew-a",
            stop_price=Decimal("101"),
            targets=(Decimal("105"),),
        ),
        evidence_b=_evidence(
            entry_barrier,
            "crew-b",
            stop_price=Decimal("101"),
            targets=(Decimal("105"),),
        ),
    )
    _process(setup, setup["next_open"])
    result = _process(setup, setup["next_close"])
    assert tuple(event.source_system_id for event in result.exit_events) == (
        "crew-a",
        "crew-b",
    )
    assert tuple(event.rank for event in result.exit_events) == (1, 2)


def test_closed_lot_records_gross_and_net_realized_pnl() -> None:
    _, _, entry_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(
            entry_barrier,
            "crew-a",
            stop_price=Decimal("99"),
            targets=(Decimal("104"),),
        ),
        evidence_b=_evidence(
            entry_barrier,
            "crew-b",
            stop_price=Decimal("98"),
            targets=(Decimal("106"),),
        ),
    )
    _process(setup, setup["next_open"])
    result = _process(setup, setup["next_close"])
    event = result.exit_events[0]
    lot = next(lot for lot in setup["book"].closed_lots if lot.lot_id == event.lot_id)
    assert lot.status is MasterHistoricalVirtualLotStatus.CLOSED
    assert lot.gross_realized_pnl == event.gross_realized_pnl
    assert lot.net_realized_pnl == event.net_realized_pnl
    assert event.net_realized_pnl < event.gross_realized_pnl


def test_exit_release_uses_exact_barrier_timestamp() -> None:
    _, _, entry_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(
            entry_barrier,
            "crew-a",
            stop_price=Decimal("101"),
            targets=(Decimal("105"),),
        ),
        evidence_b=_evidence(
            entry_barrier,
            "crew-b",
            stop_price=Decimal("98"),
            targets=(Decimal("106"),),
        ),
    )
    _process(setup, setup["next_open"])
    result = _process(setup, setup["next_close"])
    event = result.exit_events[0]
    record = setup["ledger"].get(event.reservation_id)
    assert record.released_at == setup["next_close"].observed_at
    assert record.release_ref == event.reservation_release_ref


def test_no_exit_barrier_leaves_ledger_unchanged() -> None:
    setup = _setup()
    before = setup["ledger"].snapshot().fingerprint_sha256
    result = _process(setup, setup["next_open"])
    assert result.status is MasterHistoricalLifecycleStatus.PROCESSED_NO_EXIT
    assert result.ledger_before_fingerprint_sha256 == before
    assert result.ledger_after_fingerprint_sha256 == before


def test_lifecycle_barriers_must_be_contiguous() -> None:
    setup = _setup()
    with pytest.raises(ValueError, match="processed contiguously"):
        _process(setup, setup["next_close"])


def test_tampered_lifecycle_candle_is_rejected_before_execution() -> None:
    setup = _setup()
    bad = dict(setup["next_candle"])
    bad["high"] = Decimal(str(bad["high"])) + Decimal("1")
    with pytest.raises(ValueError, match="candle does not match timeline fingerprint"):
        _process(setup, setup["next_open"], candle=bad)


def test_immediate_barrier_replay_is_idempotent() -> None:
    setup = _setup()
    first = _process(setup, setup["next_open"])
    orders_before = asyncio.run(setup["runtime"].broker.get_orders())
    second = _process(setup, setup["next_open"])
    assert second == first
    assert asyncio.run(setup["runtime"].broker.get_orders()) == orders_before


def test_old_barrier_cannot_be_replayed_after_lifecycle_progresses() -> None:
    setup = _setup()
    _process(setup, setup["next_open"])
    _process(setup, setup["next_close"])
    with pytest.raises(ValueError, match="stale processed barrier"):
        _process(setup, setup["next_open"])


def test_open_virtual_lot_requires_committed_reservation() -> None:
    setup = _setup()
    lot = setup["book"].open_lots[0]
    setup["ledger"].release(
        lot.reservation_id,
        released_at=setup["entry_barrier"].observed_at,
        release_ref="external-release",
    )
    with pytest.raises(ValueError, match="lost its COMMITTED reservation"):
        _process(setup, setup["next_open"])


def test_virtual_portfolio_snapshot_preserves_per_crew_open_positions() -> None:
    setup = _setup()
    snapshot = asyncio.run(
        build_master_historical_virtual_portfolio_snapshot(
            book=setup["book"],
            allocation_policy=setup["allocation"],
            observed_at=setup["entry_barrier"].observed_at,
            mark_price=Decimal("102"),
        )
    )
    assert snapshot.master_capital.equity == setup["step5"].account_after.equity
    assert tuple(item.open_positions for item in snapshot.crew_exposures) == (1, 1)
    assert tuple(item.open_risk_amount for item in snapshot.crew_exposures) == (
        Decimal("1"),
        Decimal("1"),
    )


def test_virtual_portfolio_gross_does_not_net_opposing_crews() -> None:
    _, _, entry_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(entry_barrier, "crew-a", side="LONG"),
        evidence_b=_evidence(entry_barrier, "crew-b", side="SHORT"),
    )
    snapshot = asyncio.run(
        build_master_historical_virtual_portfolio_snapshot(
            book=setup["book"],
            allocation_policy=setup["allocation"],
            observed_at=setup["entry_barrier"].observed_at,
            mark_price=Decimal("102"),
        )
    )
    assert snapshot.total_gross_exposure_amount == Decimal("20.4")
    assert setup["step5"].account_after.gross_exposure_amount == Decimal("0")


def test_virtual_book_snapshot_marks_gross_at_current_price() -> None:
    setup = _setup()
    snapshot = setup["book"].snapshot(
        observed_at=setup["entry_barrier"].observed_at,
        mark_price=Decimal("110"),
    )
    assert snapshot.virtual_gross_exposure_amount == Decimal("22.0")
    assert snapshot.committed_open_risk_amount == Decimal("2")


def test_result_has_no_risk_admission_or_live_authority() -> None:
    setup = _setup()
    result = _process(setup, setup["next_open"])
    assert result.single_master_capital is True
    assert result.uses_branch_brokers is False
    assert result.paper_broker_authority is True
    assert result.risk_authority is False
    assert result.admission_authority is False
    assert result.live_authority is False


def test_cash_blocked_step5_entry_does_not_create_virtual_lot() -> None:
    _, _, entry_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(
            entry_barrier,
            "crew-a",
            approved_quantity=Decimal("1"),
            approved_notional=Decimal("90"),
        ),
        evidence_b=_evidence(
            entry_barrier,
            "crew-b",
            approved_quantity=Decimal("0.1"),
            approved_notional=Decimal("10.2"),
        ),
    )
    assert len(setup["book"].open_lots) == 1
    assert setup["book"].open_lots[0].source_system_id == "crew-b"


def test_master_rejected_entries_do_not_create_virtual_lots() -> None:
    policies = _policies(gate_gross=Decimal("1"))
    setup = _setup(policies=policies)
    assert setup["registration"].status is (
        MasterHistoricalVirtualLotRegistrationStatus.NO_EXECUTED_ENTRIES
    )
    assert setup["book"].lots == ()


def test_registration_rejects_wrong_candle_content() -> None:
    setup = _setup()
    fresh_book = build_master_historical_virtual_lot_book(
        plan=setup["plan"], runtime=setup["runtime"]
    )
    bad = dict(_barrier_candle(setup["entry_barrier"]))
    bad["close"] = Decimal(str(bad["close"])) + Decimal("0.01")
    bad["high"] = Decimal(str(bad["high"])) + Decimal("0.01")
    with pytest.raises(ValueError, match="candle does not match timeline fingerprint"):
        asyncio.run(
            register_master_historical_virtual_lots(
                book=fresh_book,
                plan=setup["plan"],
                timeline=setup["timeline"],
                decision_barrier=setup["decision_barrier"],
                execution_result=setup["step5"],
                ledger=setup["ledger"],
                candle=bad,
                proposal_evidence=setup["registration_evidence"],
            )
        )


def test_virtual_gross_above_committed_notional_fails_reconciliation_closed() -> None:
    setup = _setup()
    snapshot = asyncio.run(
        build_master_historical_virtual_portfolio_snapshot(
            book=setup["book"],
            allocation_policy=setup["allocation"],
            observed_at=setup["entry_barrier"].observed_at,
            mark_price=Decimal("110"),
        )
    )
    report = build_reservation_reconciliation_report(
        policy=setup["allocation"],
        ledger_snapshot=setup["ledger"].snapshot(),
        portfolio_snapshot=snapshot,
    )
    assert report.status is ReservationReconciliationStatus.INCONSISTENT


def test_target_exit_uses_exact_existing_maker_fee_model() -> None:
    _, _, entry_barrier, _, _, _ = _plan_timeline()
    setup = _setup(
        evidence_a=_evidence(
            entry_barrier,
            "crew-a",
            stop_price=Decimal("99"),
            targets=(Decimal("104"),),
        ),
        evidence_b=_evidence(
            entry_barrier,
            "crew-b",
            stop_price=Decimal("98"),
            targets=(Decimal("106"),),
        ),
    )
    _process(setup, setup["next_open"])
    result = _process(setup, setup["next_close"])
    event = result.exit_events[0]
    expected = Decimal("104") * Decimal("0.1") * Decimal("1") / Decimal("10000")
    assert event.exit_fee == expected
