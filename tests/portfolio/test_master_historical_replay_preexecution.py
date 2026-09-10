from __future__ import annotations

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
    MasterHistoricalReplayBarrier,
    MasterHistoricalReplayBarrierPhase,
    build_master_historical_replay_timeline,
)
from app.portfolio.historical_replay_preexecution import (
    HistoricalCrewDecisionStatus,
    HistoricalCrewPreExecutionEvidence,
    MasterHistoricalDecisionBarrierStatus,
    build_master_historical_decision_barrier,
)
from app.portfolio.models import PortfolioMemberRef
from app.portfolio.risk_gate import (
    build_master_risk_gate_policy,
    local_risk_decision_fingerprint,
)
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.ids import stable_digest
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


class FailureCode(StrEnum):
    AI_PROVIDER_ERROR = "AI_PROVIDER_ERROR"


@dataclass(frozen=True)
class FakeConfig:
    system_id: str
    initial_balance: Decimal
    risk_version: str = "risk-v1"
    feature_version: str = "feature-v1"
    execution_model_version: str = "historical-ohlc-v1"
    maker_fee_bps: Decimal = Decimal("1")
    taker_fee_bps: Decimal = Decimal("2")
    market_slippage_bps: Decimal = Decimal("0.5")
    intrabar_policy: Intrabar = Intrabar.STOP_FIRST

    def canonical_payload(self) -> dict[str, object]:
        return {
            "system_id": self.system_id,
            "initial_balance": self.initial_balance,
            "risk_version": self.risk_version,
            "feature_version": self.feature_version,
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
    close: Decimal = Decimal("101")


@dataclass(frozen=True)
class FakeOpportunity:
    opportunity_id: str
    snapshot_id: str
    system_id: str
    symbol: str
    timeframe: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class FakeProposal:
    proposal_id: str
    opportunity_id: str
    source_snapshot_id: str
    system_id: str
    symbol: str
    timeframe: str
    created_at: datetime
    expires_at: datetime
    side: str = "LONG"
    entry_price: Decimal = Decimal("100")
    stop_price: Decimal = Decimal("99")
    expected_rr: Decimal = Decimal("2")


@dataclass(frozen=True)
class FakeFailure:
    code: FailureCode


@dataclass(frozen=True)
class FakeOrchestrationResult:
    status: OrchestrationStatus
    opportunity_id: str
    source_snapshot_id: str
    system_id: str
    symbol: str
    trade_proposal: FakeProposal | None = None
    failure: FakeFailure | None = None


def _candle(index: int) -> dict[str, object]:
    open_at = BASE + timedelta(hours=index)
    close_at = open_at + timedelta(hours=1)
    price = Decimal("100") + Decimal(index)
    return {
        "symbol": "BTCUSDC",
        "timeframe": "1h",
        "open_time": open_at,
        "close_time": close_at,
        "open": price,
        "high": price + Decimal("2"),
        "low": price - Decimal("2"),
        "close": price + Decimal("1"),
        "volume": Decimal("10"),
        "is_closed": True,
    }


def _candles() -> tuple[dict[str, object], ...]:
    return tuple(_candle(index) for index in range(4))


def _dataset() -> DatasetRef:
    return DatasetRef.from_candles(
        _candles(),
        symbol="BTCUSDC",
        timeframe="1h",
        source="fixture",
    )


def _allocation():
    members = (
        PortfolioMemberRef(system_id="crew-a"),
        PortfolioMemberRef(system_id="crew-b"),
    )
    envelopes = tuple(
        CrewAllocationEnvelope(
            system_id=member.system_id,
            status=AllocationEnvelopeStatus.CONFIGURED,
            capital_ceiling_amount=Decimal("70"),
            open_risk_ceiling_amount=Decimal("10"),
            gross_exposure_ceiling_amount=Decimal("100"),
        )
        for member in members
    )
    return build_master_allocation_policy(
        master_portfolio_id=MASTER_ID,
        policy_id="allocation-v1",
        members=members,
        envelopes=envelopes,
    )


def _plan_and_timeline():
    dataset = _dataset()
    allocation = _allocation()
    gate = build_master_risk_gate_policy(
        master_portfolio_id=MASTER_ID,
        gate_policy_id="gate-v1",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        max_total_open_risk_amount=Decimal("20"),
        max_total_gross_exposure_amount=Decimal("150"),
    )
    arbitration = build_master_arbitration_policy(
        master_portfolio_id=MASTER_ID,
        arbitration_policy_id="arb-v1",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        order_strategy=MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST,
    )
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
        master_initial_capital=Decimal("80"),
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
    return plan, timeline


def _barrier():
    plan, timeline = _plan_and_timeline()
    barrier = next(
        item
        for item in timeline.barriers
        if item.phase is MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE
        and item.decision_eligible
    )
    return plan, timeline, barrier


def _context(barrier, system_id: str) -> FakeContext:
    return FakeContext(
        snapshot_id=f"snapshot:{barrier.candle_index}:{system_id}",
        symbol="BTCUSDC",
        timeframe="1h",
        observed_at=barrier.observed_at,
    )


def _opportunity(context: FakeContext, system_id: str) -> FakeOpportunity:
    return FakeOpportunity(
        opportunity_id=f"opp:{system_id}",
        snapshot_id=context.snapshot_id,
        system_id=system_id,
        symbol=context.symbol,
        timeframe=context.timeframe,
        created_at=context.observed_at,
        expires_at=context.observed_at + timedelta(minutes=10),
    )


def _proposal(
    context: FakeContext,
    opportunity: FakeOpportunity,
    system_id: str,
) -> FakeProposal:
    return FakeProposal(
        proposal_id=f"proposal:{system_id}",
        opportunity_id=opportunity.opportunity_id,
        source_snapshot_id=context.snapshot_id,
        system_id=system_id,
        symbol=context.symbol,
        timeframe=context.timeframe,
        created_at=context.observed_at,
        expires_at=context.observed_at + timedelta(minutes=10),
    )


def _evidence(
    barrier,
    system_id: str,
    *,
    orchestration_status: OrchestrationStatus = OrchestrationStatus.TRADE_PROPOSAL,
    risk_status: RiskDecisionStatus = RiskDecisionStatus.APPROVED,
) -> HistoricalCrewPreExecutionEvidence:
    context = _context(barrier, system_id)
    opportunity = _opportunity(context, system_id)
    if orchestration_status is not OrchestrationStatus.TRADE_PROPOSAL:
        failure = (
            FakeFailure(FailureCode.AI_PROVIDER_ERROR)
            if orchestration_status is OrchestrationStatus.FAILED
            else None
        )
        orchestration = FakeOrchestrationResult(
            status=orchestration_status,
            opportunity_id=opportunity.opportunity_id,
            source_snapshot_id=context.snapshot_id,
            system_id=system_id,
            symbol=context.symbol,
            failure=failure,
        )
        return HistoricalCrewPreExecutionEvidence(
            system_id=system_id,
            market_context=context,
            opportunity=opportunity,
            orchestration_result=orchestration,
        )

    proposal = _proposal(context, opportunity, system_id)
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
            details={"risk_profile_id": "risk-v1"},
        )
    else:
        reasons = (
            (RiskReasonCode.APPROVED,)
            if risk_status is RiskDecisionStatus.APPROVED
            else (RiskReasonCode.RESIZED_PORTFOLIO_RISK,)
        )
        decision = RiskDecision(
            proposal_id=proposal.proposal_id,
            status=risk_status,
            reason_codes=reasons,
            approved_quantity=Decimal("2"),
            approved_risk_amount=Decimal("2"),
            approved_notional=Decimal("200"),
            created_at=barrier.observed_at,
            details={"risk_profile_id": "risk-v1", "budget": "2"},
        )
    return HistoricalCrewPreExecutionEvidence(
        system_id=system_id,
        market_context=context,
        opportunity=opportunity,
        orchestration_result=orchestration,
        local_risk_decision=decision,
    )


def _result(*evidence):
    plan, timeline, barrier = _barrier()
    items = evidence or (_evidence(barrier, "crew-a"), _evidence(barrier, "crew-b"))
    return build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=barrier,
        crew_evidence=tuple(items),
    )


def test_builds_ready_for_reservation_barrier() -> None:
    result = _result()
    assert result.status is MasterHistoricalDecisionBarrierStatus.READY_FOR_RESERVATION
    assert result.local_risk_completed is True
    assert result.reservation_required_before_master_gate is True


def test_authorized_decisions_become_candidate_seeds() -> None:
    result = _result()
    assert result.authorized_count == 2
    assert tuple(item.system_id for item in result.candidate_seeds) == ("crew-a", "crew-b")
    assert all(item.reservation_required for item in result.candidate_seeds)
    assert all(not item.reservation_id_present for item in result.candidate_seeds)


def test_candidate_seed_never_infers_capital_requirement() -> None:
    seed = _result().candidate_seeds[0]
    assert seed.capital_requirement_inferred is False
    assert seed.local_approved_notional == Decimal("200")


def test_candidate_seed_reconstructs_exact_local_risk_decision() -> None:
    seed = _result().candidate_seeds[0]
    decision = seed.to_local_risk_decision()
    assert decision.proposal_id == seed.proposal_id
    assert decision.status is seed.local_risk_status
    assert local_risk_decision_fingerprint(system_id=seed.system_id, decision=decision) == (
        seed.local_risk_decision_fingerprint_sha256
    )


def test_resized_local_risk_is_authorized_without_changing_amounts() -> None:
    plan, timeline, barrier = _barrier()
    evidence = (
        _evidence(barrier, "crew-a", risk_status=RiskDecisionStatus.RESIZED),
        _evidence(barrier, "crew-b", risk_status=RiskDecisionStatus.REJECTED),
    )
    result = build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=barrier,
        crew_evidence=evidence,
    )
    seed = result.candidate_seeds[0]
    assert seed.local_risk_status is RiskDecisionStatus.RESIZED
    assert seed.local_approved_quantity == Decimal("2")
    assert seed.local_approved_risk_amount == Decimal("2")
    assert seed.local_approved_notional == Decimal("200")


def test_local_risk_rejected_is_terminal_and_has_no_seed() -> None:
    plan, timeline, barrier = _barrier()
    result = build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=barrier,
        crew_evidence=(
            _evidence(barrier, "crew-a", risk_status=RiskDecisionStatus.REJECTED),
            _evidence(barrier, "crew-b"),
        ),
    )
    rejected = result.outcomes[0]
    assert rejected.status is HistoricalCrewDecisionStatus.LOCAL_RISK_REJECTED
    assert rejected.candidate_seed_fingerprint_sha256 is None
    assert result.authorized_count == 1
    assert result.rejected_count == 1


@pytest.mark.parametrize(
    ("orchestration_status", "expected"),
    (
        (OrchestrationStatus.NO_ANALYSIS, HistoricalCrewDecisionStatus.NO_ANALYSIS),
        (OrchestrationStatus.NO_TRADE, HistoricalCrewDecisionStatus.NO_TRADE),
        (OrchestrationStatus.FAILED, HistoricalCrewDecisionStatus.ORCHESTRATION_FAILED),
    ),
)
def test_terminal_orchestration_never_reaches_local_risk(
    orchestration_status: OrchestrationStatus,
    expected: HistoricalCrewDecisionStatus,
) -> None:
    plan, timeline, barrier = _barrier()
    result = build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=barrier,
        crew_evidence=(
            _evidence(barrier, "crew-a", orchestration_status=orchestration_status),
            _evidence(barrier, "crew-b"),
        ),
    )
    assert result.outcomes[0].status is expected
    assert result.outcomes[0].local_risk_status is None


def test_failed_orchestration_seals_failure_code() -> None:
    plan, timeline, barrier = _barrier()
    result = build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=barrier,
        crew_evidence=(
            _evidence(barrier, "crew-a", orchestration_status=OrchestrationStatus.FAILED),
            _evidence(barrier, "crew-b"),
        ),
    )
    assert result.outcomes[0].failure_code == "AI_PROVIDER_ERROR"


def test_no_opportunity_is_explicit_and_terminal() -> None:
    plan, timeline, barrier = _barrier()
    evidence = HistoricalCrewPreExecutionEvidence(
        system_id="crew-a",
        market_context=_context(barrier, "crew-a"),
    )
    result = build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=barrier,
        crew_evidence=(evidence, _evidence(barrier, "crew-b")),
    )
    assert result.outcomes[0].status is HistoricalCrewDecisionStatus.NO_OPPORTUNITY
    assert result.outcomes[0].opportunity_id is None


def test_input_evidence_order_does_not_change_barrier_identity() -> None:
    plan, timeline, barrier = _barrier()
    a = _evidence(barrier, "crew-a")
    b = _evidence(barrier, "crew-b")
    first = build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=barrier,
        crew_evidence=(a, b),
    )
    second = build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=barrier,
        crew_evidence=(b, a),
    )
    assert first == second


def test_barrier_has_no_execution_or_admission_authority() -> None:
    result = _result()
    assert result.single_master_capital is True
    assert result.sums_branch_equities is False
    assert result.mutation_applied is False
    assert result.reservation_mutation is False
    assert result.broker_called is False
    assert result.broker_authority is False
    assert result.risk_authority is False
    assert result.admission_authority is False
    assert result.live_authority is False
    assert result.auto_execute is False


def test_outcomes_have_no_broker_authority() -> None:
    for outcome in _result().outcomes:
        assert outcome.broker_called is False
        assert outcome.reservation_created is False
        assert outcome.broker_authority is False
        assert outcome.live_authority is False


def test_candidate_seeds_have_no_admission_authority() -> None:
    for seed in _result().candidate_seeds:
        assert seed.risk_authority is False
        assert seed.admission_authority is False
        assert seed.reservation_mutation is False
        assert seed.broker_authority is False
        assert seed.live_authority is False
        assert seed.auto_execute is False


def test_open_barrier_is_rejected() -> None:
    plan, timeline, _ = _barrier()
    open_barrier = next(
        item
        for item in timeline.barriers
        if item.phase is MasterHistoricalReplayBarrierPhase.CANDLE_OPEN
    )
    with pytest.raises(ValueError, match="CANDLE_CLOSE"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=open_barrier,
            crew_evidence=(),
        )


def test_non_decision_eligible_close_is_rejected() -> None:
    plan, timeline, _ = _barrier()
    warmup_close = next(
        item
        for item in timeline.barriers
        if item.phase is MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE
        and not item.decision_eligible
    )
    with pytest.raises(ValueError, match="decision-eligible"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=warmup_close,
            crew_evidence=(),
        )


def test_foreign_barrier_is_rejected() -> None:
    plan, timeline, barrier = _barrier()
    shifted_close = barrier.candle_close_at + timedelta(minutes=1)
    payload = {
        "schema": "money-heist.master-historical-replay-barrier.v1",
        "schema_version": "1.0",
        "sequence": barrier.sequence,
        "candle_index": barrier.candle_index,
        "phase": barrier.phase,
        "observed_at": shifted_close,
        "candle_open_at": barrier.candle_open_at,
        "candle_close_at": shifted_close,
        "visible_candle_count": barrier.visible_candle_count,
        "decision_eligible": True,
        "candle_fingerprint_sha256": stable_digest({"foreign": True}),
        "crew_system_ids": barrier.crew_system_ids,
    }
    forged = MasterHistoricalReplayBarrier(
        sequence=barrier.sequence,
        candle_index=barrier.candle_index,
        phase=barrier.phase,
        observed_at=shifted_close,
        candle_open_at=barrier.candle_open_at,
        candle_close_at=shifted_close,
        visible_candle_count=barrier.visible_candle_count,
        decision_eligible=True,
        candle_fingerprint_sha256=payload["candle_fingerprint_sha256"],
        crew_system_ids=barrier.crew_system_ids,
        fingerprint_sha256=stable_digest(payload),
    )
    with pytest.raises(ValueError, match="exact timeline barrier"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=forged,
            crew_evidence=(),
        )


def test_missing_crew_evidence_is_rejected() -> None:
    plan, timeline, barrier = _barrier()
    with pytest.raises(ValueError, match="exactly one evidence per crew"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(_evidence(barrier, "crew-a"),),
        )


def test_duplicate_crew_evidence_is_rejected() -> None:
    plan, timeline, barrier = _barrier()
    a = _evidence(barrier, "crew-a")
    with pytest.raises(ValueError, match="must be unique"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(a, a),
        )


def test_market_context_must_use_exact_barrier_time() -> None:
    plan, timeline, barrier = _barrier()
    evidence = _evidence(barrier, "crew-a")
    wrong_context = replace(
        evidence.market_context,
        observed_at=barrier.observed_at + timedelta(seconds=1),
    )
    wrong = replace(evidence, market_context=wrong_context)
    with pytest.raises(ValueError, match="exact CLOSE barrier time"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(wrong, _evidence(barrier, "crew-b")),
        )


def test_market_context_symbol_mismatch_is_rejected() -> None:
    plan, timeline, barrier = _barrier()
    evidence = _evidence(barrier, "crew-a")
    wrong = replace(evidence, market_context=replace(evidence.market_context, symbol="ETHUSDC"))
    with pytest.raises(ValueError, match="symbol/timeframe"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(wrong, _evidence(barrier, "crew-b")),
        )


def test_opportunity_system_mismatch_is_rejected() -> None:
    plan, timeline, barrier = _barrier()
    evidence = _evidence(barrier, "crew-a")
    wrong = replace(evidence, opportunity=replace(evidence.opportunity, system_id="crew-b"))
    with pytest.raises(ValueError, match="opportunity system_id"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(wrong, _evidence(barrier, "crew-b")),
        )


def test_opportunity_snapshot_mismatch_is_rejected() -> None:
    plan, timeline, barrier = _barrier()
    evidence = _evidence(barrier, "crew-a")
    wrong = replace(evidence, opportunity=replace(evidence.opportunity, snapshot_id="other"))
    with pytest.raises(ValueError, match="snapshot"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(wrong, _evidence(barrier, "crew-b")),
        )


def test_orchestration_system_mismatch_is_rejected() -> None:
    plan, timeline, barrier = _barrier()
    evidence = _evidence(barrier, "crew-a")
    wrong_result = replace(evidence.orchestration_result, system_id="crew-b")
    wrong = replace(evidence, orchestration_result=wrong_result)
    with pytest.raises(ValueError, match="orchestration system_id"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(wrong, _evidence(barrier, "crew-b")),
        )


def test_trade_proposal_requires_local_risk_decision() -> None:
    plan, timeline, barrier = _barrier()
    evidence = replace(_evidence(barrier, "crew-a"), local_risk_decision=None)
    with pytest.raises(ValueError, match="requires local Risk decision"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(evidence, _evidence(barrier, "crew-b")),
        )


def test_local_risk_decision_must_match_proposal() -> None:
    plan, timeline, barrier = _barrier()
    evidence = _evidence(barrier, "crew-a")
    decision = replace(evidence.local_risk_decision, proposal_id="other")
    wrong = replace(evidence, local_risk_decision=decision)
    with pytest.raises(ValueError, match="proposal_id"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(wrong, _evidence(barrier, "crew-b")),
        )


def test_local_risk_decision_must_use_exact_barrier_time() -> None:
    plan, timeline, barrier = _barrier()
    evidence = _evidence(barrier, "crew-a")
    decision = replace(
        evidence.local_risk_decision,
        created_at=barrier.observed_at + timedelta(microseconds=1),
    )
    wrong = replace(evidence, local_risk_decision=decision)
    with pytest.raises(ValueError, match="exact CLOSE barrier time"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(wrong, _evidence(barrier, "crew-b")),
        )


def test_rejected_risk_cannot_carry_approved_amounts() -> None:
    plan, timeline, barrier = _barrier()
    evidence = _evidence(barrier, "crew-a", risk_status=RiskDecisionStatus.REJECTED)
    decision = replace(evidence.local_risk_decision, approved_quantity=Decimal("1"))
    wrong = replace(evidence, local_risk_decision=decision)
    with pytest.raises(ValueError, match="cannot carry approved amounts"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(wrong, _evidence(barrier, "crew-b")),
        )


def test_authorized_risk_requires_positive_amounts() -> None:
    plan, timeline, barrier = _barrier()
    evidence = _evidence(barrier, "crew-a")
    decision = replace(evidence.local_risk_decision, approved_risk_amount=Decimal("0"))
    wrong = replace(evidence, local_risk_decision=decision)
    with pytest.raises(ValueError, match="must be > 0"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(wrong, _evidence(barrier, "crew-b")),
        )


def test_proposal_created_after_barrier_is_rejected() -> None:
    plan, timeline, barrier = _barrier()
    evidence = _evidence(barrier, "crew-a")
    orchestration = evidence.orchestration_result
    proposal = replace(
        orchestration.trade_proposal,
        created_at=barrier.observed_at + timedelta(seconds=1),
    )
    wrong = replace(evidence, orchestration_result=replace(orchestration, trade_proposal=proposal))
    with pytest.raises(ValueError, match="cannot be created after"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(wrong, _evidence(barrier, "crew-b")),
        )


def test_no_opportunity_cannot_carry_orchestration() -> None:
    plan, timeline, barrier = _barrier()
    full = _evidence(barrier, "crew-a")
    wrong = replace(full, opportunity=None, local_risk_decision=None)
    with pytest.raises(ValueError, match="no-opportunity"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(wrong, _evidence(barrier, "crew-b")),
        )


def test_terminal_orchestration_cannot_carry_local_risk() -> None:
    plan, timeline, barrier = _barrier()
    terminal = _evidence(barrier, "crew-a", orchestration_status=OrchestrationStatus.NO_TRADE)
    decision = RiskDecision(
        proposal_id="forbidden",
        status=RiskDecisionStatus.REJECTED,
        reason_codes=(RiskReasonCode.NO_RISK_BUDGET,),
        created_at=barrier.observed_at,
    )
    wrong = replace(terminal, local_risk_decision=decision)
    with pytest.raises(ValueError, match="terminal orchestration"):
        build_master_historical_decision_barrier(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            crew_evidence=(wrong, _evidence(barrier, "crew-b")),
        )


def test_barrier_fingerprint_changes_when_local_risk_changes() -> None:
    plan, timeline, barrier = _barrier()
    a = _evidence(barrier, "crew-a")
    b = _evidence(barrier, "crew-b")
    baseline = build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=barrier,
        crew_evidence=(a, b),
    )
    changed_decision = replace(a.local_risk_decision, approved_quantity=Decimal("1"))
    changed = build_master_historical_decision_barrier(
        plan=plan,
        timeline=timeline,
        barrier=barrier,
        crew_evidence=(replace(a, local_risk_decision=changed_decision), b),
    )
    assert baseline.fingerprint_sha256 != changed.fingerprint_sha256


def test_candidate_seed_binds_plan_timeline_and_barrier() -> None:
    result = _result()
    seed = result.candidate_seeds[0]
    assert seed.master_portfolio_id == result.master_portfolio_id
    assert seed.plan_id == result.plan_id
    assert seed.timeline_id == result.timeline_id
    assert seed.barrier_sequence == result.barrier_sequence
    assert seed.barrier_fingerprint_sha256 == result.barrier_fingerprint_sha256


def test_all_outcomes_are_sorted_by_system_id() -> None:
    result = _result()
    assert tuple(item.system_id for item in result.outcomes) == ("crew-a", "crew-b")


def test_every_crew_has_exactly_one_outcome() -> None:
    result = _result()
    assert len(result.outcomes) == 2
    assert {item.system_id for item in result.outcomes} == {"crew-a", "crew-b"}
