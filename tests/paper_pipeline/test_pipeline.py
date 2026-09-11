from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from app.agents.models import EvidenceReference
from app.market.features.models import FeatureQuality, FeatureSnapshot, MarketRegime
from app.market.scanner.models import CandidateOpportunity, ScannerTrigger
from app.services.orchestration.models import (
    OrchestrationResult,
    PipelineFailure,
    PipelineFailureCode,
    PipelineStatus,
    ProfessorFinalDecision,
    ProfessorTradeParameters,
    TradeProposal,
)
from app.services.paper_pipeline import (
    InMemoryKillSwitchStateProvider,
    InMemoryMarketConstraintsProvider,
    InMemoryPaperPipelineJournal,
    InMemoryPortfolioRiskStateProvider,
    InMemoryRiskProfileProvider,
    PaperOrderIntent,
    PaperPipelineFailureCode,
    PaperPipelineStatus,
    PaperTradingPipeline,
    trade_proposal_to_risk_input,
)
from app.trading.paper.broker import PaperBroker, ValidationError
from app.trading.paper.config import PaperBrokerConfig
from app.trading.paper.models import OrderSide, PositionSide
from app.trading.risk.engine import RiskEngine
from app.trading.risk.models import (
    KillSwitchState,
    MarketConstraints,
    PortfolioRiskState,
    RiskDecisionStatus,
    RiskReasonCode,
    TradeSide,
)
from app.trading.risk.profiles import demo_profile


NOW = datetime(2026, 9, 7, 16, 0, tzinfo=timezone.utc)
PROPOSAL_ID = UUID("10000000-0000-0000-0000-000000000001")
PROFESSOR_REQUEST_ID = UUID("20000000-0000-0000-0000-000000000001")
PALERMO_REQUEST_ID = UUID("30000000-0000-0000-0000-000000000001")


def sync_test(func):
    def wrapper():
        return asyncio.run(func())

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


class StubOrchestration:
    def __init__(self, result: OrchestrationResult):
        self.result = result
        self.calls = 0
        self.last_decision_context = None
        self.last_specialist_contexts = None

    async def run(
        self,
        *,
        opportunity,
        market_context,
        now=None,
        decision_context=None,
        specialist_contexts=None,
    ):
        del opportunity, market_context, now
        self.calls += 1
        self.last_decision_context = decision_context
        self.last_specialist_contexts = specialist_contexts
        return self.result


class CountingRiskEngine(RiskEngine):
    def __init__(self):
        self.calls = 0
        self.last_proposal = None

    def evaluate(self, **kwargs):
        self.calls += 1
        self.last_proposal = kwargs["proposal"]
        return super().evaluate(**kwargs)


class CountingPaperBroker(PaperBroker):
    def __init__(self, config=None):
        super().__init__(config)
        self.submit_calls = 0
        self.price_calls = 0

    async def submit_order(self, request, *, trigger=None):
        self.submit_calls += 1
        return await super().submit_order(request, trigger=trigger)

    async def process_price(self, symbol, price, *, observed_at=None):
        self.price_calls += 1
        return await super().process_price(symbol, price, observed_at=observed_at)


class FailingSubmitBroker(CountingPaperBroker):
    async def submit_order(self, request, *, trigger=None):
        self.submit_calls += 1
        raise ValidationError("injected PAPER broker failure")


def make_context(*, close: float = 100.0) -> FeatureSnapshot:
    return FeatureSnapshot(
        feature_version="features-v1",
        snapshot_id="snapshot-1",
        source_snapshot_id="raw-1",
        symbol="BTCUSDT",
        timeframe="1m",
        observed_at=NOW,
        candle_count=100,
        close=close,
        ema_fast=101.0,
        ema_slow=99.0,
        ema_spread_pct=2.0,
        rsi_14=62.0,
        adx_14=30.0,
        prior_range_high_20=99.0,
        prior_range_low_20=90.0,
        regime=MarketRegime.BULLISH_TREND,
        quality=FeatureQuality(
            warmup_complete=True,
            closed_candle_count=100,
            missing_features=(),
        ),
    )


def make_opportunity() -> CandidateOpportunity:
    return CandidateOpportunity(
        scanner_version="scanner-v1",
        opportunity_id="40000000-0000-0000-0000-000000000001",
        snapshot_id="snapshot-1",
        system_id="balanced_v1",
        symbol="BTCUSDT",
        timeframe="1m",
        priority_score=80,
        triggers=(ScannerTrigger.RANGE_BREAK,),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )


def make_final(side: str = "LONG") -> ProfessorFinalDecision:
    if side == "NO_TRADE":
        return ProfessorFinalDecision(
            direction="NO_TRADE",
            confidence=0.8,
            thesis=["red-team evidence dominates"],
            counter_evidence=["false breakout"],
            invalidation=[],
            evidence=[],
            trade=None,
        )
    stop = Decimal("98") if side == "LONG" else Decimal("102")
    target = Decimal("110") if side == "LONG" else Decimal("90")
    return ProfessorFinalDecision(
        direction=side,
        confidence=0.72,
        thesis=["conditional trade"],
        counter_evidence=["red-team caution"],
        invalidation=["stop invalidates thesis"],
        evidence=[EvidenceReference(source_key="market_context.close", observation="close=100")],
        trade=ProfessorTradeParameters(
            entry_price=Decimal("100"),
            stop_price=stop,
            targets=(target,),
            expected_rr=Decimal("2"),
        ),
    )


def make_proposal(
    *,
    side: str = "LONG",
    stop_price: Decimal | None = None,
    expires_at: datetime | None = None,
    proposal_id: UUID = PROPOSAL_ID,
    opportunity_id: str | None = None,
    source_snapshot_id: str = "snapshot-1",
) -> TradeProposal:
    stop = stop_price or (Decimal("98") if side == "LONG" else Decimal("102"))
    target = Decimal("110") if side == "LONG" else Decimal("90")
    return TradeProposal(
        proposal_id=proposal_id,
        opportunity_id=opportunity_id or make_opportunity().opportunity_id,
        source_snapshot_id=source_snapshot_id,
        system_id="balanced_v1",
        symbol="BTCUSDT",
        timeframe="1m",
        side=side,
        confidence=0.72,
        entry_price=Decimal("100"),
        stop_price=stop,
        targets=(target,),
        expected_rr=Decimal("2"),
        thesis=("conditional trade",),
        counter_evidence=("red-team caution",),
        invalidation=("stop invalidates thesis",),
        evidence=(
            EvidenceReference(source_key="market_context.close", observation="close=100"),
        ),
        market_regime="bullish_trend",
        feature_version="features-v1",
        professor_prompt_version="v1",
        professor_request_id=PROFESSOR_REQUEST_ID,
        specialist_request_ids=(),
        palermo_request_id=PALERMO_REQUEST_ID,
        created_at=NOW,
        expires_at=expires_at or NOW + timedelta(minutes=5),
    )


def orchestration_trade(*, proposal: TradeProposal | None = None, side: str = "LONG"):
    proposal = proposal or make_proposal(side=side)
    return OrchestrationResult(
        status=PipelineStatus.TRADE_PROPOSAL,
        opportunity_id=proposal.opportunity_id,
        source_snapshot_id=proposal.source_snapshot_id,
        system_id=proposal.system_id,
        symbol=proposal.symbol,
        professor_decision=make_final(side),
        trade_proposal=proposal,
    )


def orchestration_no_analysis():
    opportunity = make_opportunity()
    return OrchestrationResult(
        status=PipelineStatus.NO_ANALYSIS,
        opportunity_id=opportunity.opportunity_id,
        source_snapshot_id=opportunity.snapshot_id,
        system_id=opportunity.system_id,
        symbol=opportunity.symbol,
    )


def orchestration_no_trade():
    opportunity = make_opportunity()
    return OrchestrationResult(
        status=PipelineStatus.NO_TRADE,
        opportunity_id=opportunity.opportunity_id,
        source_snapshot_id=opportunity.snapshot_id,
        system_id=opportunity.system_id,
        symbol=opportunity.symbol,
        professor_decision=make_final("NO_TRADE"),
    )


def orchestration_failed(code: PipelineFailureCode):
    opportunity = make_opportunity()
    return OrchestrationResult(
        status=PipelineStatus.FAILED,
        opportunity_id=opportunity.opportunity_id,
        source_snapshot_id=opportunity.snapshot_id,
        system_id=opportunity.system_id,
        symbol=opportunity.symbol,
        failure=PipelineFailure(code=code, stage="upstream", message=code.value),
    )


def base_portfolio(**changes) -> PortfolioRiskState:
    state = PortfolioRiskState(
        equity=Decimal("100"),
        day_start_equity=Decimal("100"),
        equity_peak=Decimal("100"),
        daily_pnl=Decimal("0"),
        open_positions=0,
        open_risk_amount=Decimal("0"),
        correlated_risk_amount=Decimal("0"),
        gross_exposure_amount=Decimal("0"),
    )
    return replace(state, **changes)


def base_market(**changes) -> MarketConstraints:
    state = MarketConstraints(
        qty_step=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("1"),
        max_qty=Decimal("100"),
        max_leverage=Decimal("1"),
    )
    return replace(state, **changes)


def make_service(
    orchestration_result: OrchestrationResult,
    *,
    portfolio: PortfolioRiskState | None = None,
    profile=None,
    market: MarketConstraints | None = None,
    kill_switch: KillSwitchState | None = None,
    broker: CountingPaperBroker | None = None,
    journal: InMemoryPaperPipelineJournal | None = None,
    omit_portfolio: bool = False,
    omit_market: bool = False,
):
    risk = CountingRiskEngine()
    paper = broker or CountingPaperBroker(PaperBrokerConfig(system_id="balanced_v1"))
    orchestration = StubOrchestration(orchestration_result)
    portfolio_map = {} if omit_portfolio else {"balanced_v1": portfolio or base_portfolio()}
    market_map = {} if omit_market else {"BTCUSDT": market or base_market()}
    service = PaperTradingPipeline(
        orchestration=orchestration,
        risk_engine=risk,
        paper_broker=paper,
        portfolio_provider=InMemoryPortfolioRiskStateProvider(portfolio_map),
        risk_profile_provider=InMemoryRiskProfileProvider(
            {"balanced_v1": profile or demo_profile()}
        ),
        market_constraints_provider=InMemoryMarketConstraintsProvider(market_map),
        kill_switch_provider=InMemoryKillSwitchStateProvider(
            {"balanced_v1": kill_switch or KillSwitchState()}
        ),
        journal=journal or InMemoryPaperPipelineJournal(),
        clock=lambda: NOW,
    )
    return service, orchestration, risk, paper


@sync_test
async def test_nominal_long_runs_ai_risk_paper_fill_and_position():
    service, _, risk, broker = make_service(orchestration_trade(side="LONG"))
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )

    assert result.status is PaperPipelineStatus.EXECUTED
    assert risk.calls == 1
    assert result.risk_record.decision.status is RiskDecisionStatus.APPROVED
    assert result.order_intent.mode == "PAPER"
    assert result.order_intent.side is OrderSide.BUY
    assert result.order.requested_quantity == result.risk_record.decision.approved_quantity
    assert result.fill.quantity == result.risk_record.decision.approved_quantity
    assert result.position_after.side is PositionSide.LONG
    assert broker.submit_calls == 1
    assert result.fill.price == Decimal("100.0500")


@sync_test
async def test_nominal_short_is_supported_by_current_paper_contracts():
    service, _, _, broker = make_service(orchestration_trade(side="SHORT"))
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )

    assert result.status is PaperPipelineStatus.EXECUTED
    assert result.order_intent.side is OrderSide.SELL
    assert result.position_after.side is PositionSide.SHORT
    assert result.position_after.quantity == result.risk_record.decision.approved_quantity
    assert result.fill.price == Decimal("99.9500")
    assert broker.config.allow_short is True


@sync_test
async def test_no_analysis_never_calls_risk_or_broker():
    service, _, risk, broker = make_service(orchestration_no_analysis())
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.status is PaperPipelineStatus.NO_ANALYSIS
    assert risk.calls == 0
    assert broker.submit_calls == 0
    assert broker.price_calls == 0


@sync_test
async def test_no_trade_never_calls_risk_or_broker():
    service, _, risk, broker = make_service(orchestration_no_trade())
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.status is PaperPipelineStatus.NO_TRADE
    assert risk.calls == 0
    assert broker.submit_calls == 0
    assert broker.price_calls == 0


@sync_test
async def test_risk_rejected_never_creates_order():
    service, _, _, broker = make_service(
        orchestration_trade(),
        portfolio=base_portfolio(open_positions=3),
    )
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.status is PaperPipelineStatus.RISK_REJECTED
    assert result.risk_record.decision.reason_codes == (RiskReasonCode.MAX_POSITIONS_LIMIT,)
    assert broker.submit_calls == 0
    assert broker.price_calls == 0


@sync_test
async def test_approved_decision_creates_exact_paper_order():
    service, _, _, _ = make_service(orchestration_trade())
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    decision = result.risk_record.decision
    assert decision.status is RiskDecisionStatus.APPROVED
    assert result.order.requested_quantity == decision.approved_quantity == Decimal("0.500")


@sync_test
async def test_resized_decision_strictly_uses_authorized_quantity():
    service, _, _, _ = make_service(
        orchestration_trade(),
        portfolio=base_portfolio(open_risk_amount=Decimal("2.5")),
    )
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    decision = result.risk_record.decision
    assert decision.status is RiskDecisionStatus.RESIZED
    assert decision.approved_quantity == Decimal("0.250")
    assert result.order_intent.quantity == Decimal("0.250")
    assert result.order.requested_quantity == Decimal("0.250")
    assert result.fill.quantity == Decimal("0.250")


@sync_test
async def test_expired_proposal_is_terminal_risk_rejection():
    proposal = make_proposal(expires_at=NOW)
    service, _, _, broker = make_service(orchestration_trade(proposal=proposal))
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.status is PaperPipelineStatus.RISK_REJECTED
    assert result.risk_record.decision.reason_codes == (RiskReasonCode.SIGNAL_EXPIRED,)
    assert broker.submit_calls == 0


@sync_test
async def test_invalid_stop_reaches_risk_authority_and_is_rejected():
    proposal = make_proposal(stop_price=Decimal("101"))
    service, _, risk, broker = make_service(orchestration_trade(proposal=proposal))
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert risk.calls == 1
    assert result.status is PaperPipelineStatus.RISK_REJECTED
    assert result.risk_record.decision.reason_codes == (RiskReasonCode.STOP_ON_WRONG_SIDE,)
    assert broker.submit_calls == 0


@sync_test
async def test_daily_loss_limit_stops_before_broker():
    service, _, _, broker = make_service(
        orchestration_trade(),
        portfolio=base_portfolio(daily_pnl=Decimal("-3")),
    )
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.risk_record.decision.reason_codes == (RiskReasonCode.DAILY_LOSS_LIMIT,)
    assert broker.submit_calls == 0


@sync_test
async def test_drawdown_limit_stops_before_broker():
    service, _, _, broker = make_service(
        orchestration_trade(),
        portfolio=base_portfolio(equity=Decimal("90"), equity_peak=Decimal("100")),
    )
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.risk_record.decision.reason_codes == (RiskReasonCode.MAX_DRAWDOWN_LIMIT,)
    assert broker.submit_calls == 0


@sync_test
async def test_kill_switch_stops_before_broker():
    service, _, _, broker = make_service(
        orchestration_trade(),
        kill_switch=KillSwitchState(stop_new_trades=True),
    )
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.risk_record.decision.reason_codes == (RiskReasonCode.KILL_SWITCH_ACTIVE,)
    assert broker.submit_calls == 0


@sync_test
async def test_min_quantity_constraint_is_respected():
    service, _, _, broker = make_service(
        orchestration_trade(),
        market=base_market(min_qty=Decimal("0.600")),
    )
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.risk_record.decision.reason_codes == (RiskReasonCode.MIN_QUANTITY,)
    assert broker.submit_calls == 0


@sync_test
async def test_min_notional_constraint_is_respected():
    service, _, _, broker = make_service(
        orchestration_trade(),
        market=base_market(min_notional=Decimal("60")),
    )
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.risk_record.decision.reason_codes == (RiskReasonCode.MIN_NOTIONAL,)
    assert broker.submit_calls == 0


@sync_test
async def test_missing_portfolio_state_fails_before_risk_and_broker():
    service, _, risk, broker = make_service(orchestration_trade(), omit_portfolio=True)
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.status is PaperPipelineStatus.FAILED
    assert result.failure.code is PaperPipelineFailureCode.PORTFOLIO_STATE_UNAVAILABLE
    assert risk.calls == 0
    assert broker.submit_calls == 0


@sync_test
async def test_missing_market_constraints_fails_before_risk_and_broker():
    service, _, risk, broker = make_service(orchestration_trade(), omit_market=True)
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.failure.code is PaperPipelineFailureCode.MARKET_CONSTRAINTS_UNAVAILABLE
    assert risk.calls == 0
    assert broker.submit_calls == 0


def test_trade_proposal_adapter_preserves_risk_owned_fields():
    proposal = make_proposal(side="SHORT")
    adapted = trade_proposal_to_risk_input(proposal)
    assert adapted.proposal_id == str(proposal.proposal_id)
    assert adapted.system_id == proposal.system_id
    assert adapted.symbol == proposal.symbol
    assert adapted.side is TradeSide.SHORT
    assert adapted.entry_price == proposal.entry_price
    assert adapted.stop_price == proposal.stop_price
    assert adapted.expected_rr == proposal.expected_rr
    assert adapted.expires_at == proposal.expires_at
    assert adapted.requested_leverage == Decimal("1")


@sync_test
async def test_full_lineage_links_opportunity_proposal_risk_order_fill_position():
    service, _, _, _ = make_service(orchestration_trade())
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    proposal = result.orchestration_result.trade_proposal

    assert result.opportunity_id == proposal.opportunity_id
    assert result.risk_input.proposal_id == str(proposal.proposal_id)
    assert result.risk_record.decision.proposal_id == str(proposal.proposal_id)
    assert result.order_intent.risk_decision_id == result.risk_record.risk_decision_id
    assert result.order.client_order_id == f"paper:opportunity:{proposal.opportunity_id}"
    assert result.fill.broker_order_id == result.order.broker_order_id
    assert result.position_after.symbol == proposal.symbol
    assert result.source_snapshot_id == proposal.source_snapshot_id

    assert [event.stage for event in result.audit_events] == [
        "orchestration",
        "trade_proposal",
        "risk_engine",
        "order_intent",
        "paper_execution",
    ]
    proposal_event = result.audit_events[1]
    assert proposal_event.details["professor_request_id"] == str(proposal.professor_request_id)
    assert proposal_event.details["palermo_request_id"] == str(proposal.palermo_request_id)

    final_event = result.audit_events[-1]
    assert final_event.stage == "paper_execution"
    assert final_event.details["broker_order_id"] == result.order.broker_order_id
    assert final_event.details["fill_id"] == result.fill.fill_id


@sync_test
async def test_idempotence_blocks_second_execution_of_same_opportunity_and_proposal():
    journal = InMemoryPaperPipelineJournal()
    service, _, risk, broker = make_service(orchestration_trade(), journal=journal)
    first = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    second = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )

    assert first.status is PaperPipelineStatus.EXECUTED
    assert second.status is PaperPipelineStatus.DUPLICATE_BLOCKED
    assert second.failure.code is PaperPipelineFailureCode.DUPLICATE_EXECUTION
    assert broker.submit_calls == 1
    assert len(await broker.get_fills()) == 1
    assert risk.calls == 2  # re-evaluation is harmless; execution remains exactly-once.


@sync_test
async def test_broker_error_never_creates_order_fill_or_position():
    broker = FailingSubmitBroker(PaperBrokerConfig(system_id="balanced_v1"))
    service, _, _, _ = make_service(orchestration_trade(), broker=broker)
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )

    assert result.status is PaperPipelineStatus.FAILED
    assert result.failure.code is PaperPipelineFailureCode.BROKER_EXECUTION_FAILED
    assert await broker.get_orders() == ()
    assert await broker.get_fills() == ()
    assert await broker.get_positions() == ()


@pytest.mark.parametrize(
    "upstream_code",
    [PipelineFailureCode.INVALID_PROFESSOR_OUTPUT, PipelineFailureCode.BUDGET_EXHAUSTED],
)
def test_upstream_ai_failure_never_reaches_risk_or_broker(upstream_code):
    async def scenario():
        service, _, risk, broker = make_service(orchestration_failed(upstream_code))
        result = await service.run(
            opportunity=make_opportunity(), market_context=make_context(), now=NOW
        )
        assert result.status is PaperPipelineStatus.FAILED
        assert result.failure.code is PaperPipelineFailureCode.ORCHESTRATION_FAILED
        assert risk.calls == 0
        assert broker.submit_calls == 0
        assert broker.price_calls == 0

    asyncio.run(scenario())


@sync_test
async def test_unavailable_audit_blocks_before_ai_risk_and_broker():
    journal = InMemoryPaperPipelineJournal(available=False)
    service, orchestration, risk, broker = make_service(orchestration_trade(), journal=journal)
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.failure.code is PaperPipelineFailureCode.AUDIT_UNAVAILABLE
    assert orchestration.calls == 0
    assert risk.calls == 0
    assert broker.submit_calls == 0


def test_paper_order_intent_cannot_be_constructed_as_live():
    with pytest.raises(TypeError):
        PaperOrderIntent(
            risk_decision_id=UUID("50000000-0000-0000-0000-000000000001"),
            system_id="balanced_v1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            client_order_id="paper:test",
            mode="LIVE",
        )

@sync_test
async def test_portfolio_risk_exposure_limit_stops_before_broker():
    service, _, _, broker = make_service(
        orchestration_trade(),
        portfolio=base_portfolio(open_risk_amount=Decimal("3")),
    )
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.status is PaperPipelineStatus.RISK_REJECTED
    assert result.risk_record.decision.reason_codes == (RiskReasonCode.MAX_PORTFOLIO_RISK,)
    assert broker.submit_calls == 0


@sync_test
async def test_gross_exposure_leverage_limit_stops_before_broker():
    service, _, _, broker = make_service(
        orchestration_trade(),
        portfolio=base_portfolio(gross_exposure_amount=Decimal("100")),
    )
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.status is PaperPipelineStatus.RISK_REJECTED
    assert result.risk_record.decision.reason_codes == (RiskReasonCode.MAX_LEVERAGE,)
    assert broker.submit_calls == 0


@sync_test
async def test_missing_risk_profile_fails_before_risk_and_broker():
    orchestration = StubOrchestration(orchestration_trade())
    risk = CountingRiskEngine()
    broker = CountingPaperBroker(PaperBrokerConfig(system_id="balanced_v1"))
    service = PaperTradingPipeline(
        orchestration=orchestration,
        risk_engine=risk,
        paper_broker=broker,
        portfolio_provider=InMemoryPortfolioRiskStateProvider(
            {"balanced_v1": base_portfolio()}
        ),
        risk_profile_provider=InMemoryRiskProfileProvider({}),
        market_constraints_provider=InMemoryMarketConstraintsProvider(
            {"BTCUSDT": base_market()}
        ),
        kill_switch_provider=InMemoryKillSwitchStateProvider(
            {"balanced_v1": KillSwitchState()}
        ),
        journal=InMemoryPaperPipelineJournal(),
        clock=lambda: NOW,
    )
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.failure.code is PaperPipelineFailureCode.RISK_PROFILE_UNAVAILABLE
    assert risk.calls == 0
    assert broker.submit_calls == 0


@sync_test
async def test_missing_kill_switch_state_fails_closed_before_risk_and_broker():
    orchestration = StubOrchestration(orchestration_trade())
    risk = CountingRiskEngine()
    broker = CountingPaperBroker(PaperBrokerConfig(system_id="balanced_v1"))
    service = PaperTradingPipeline(
        orchestration=orchestration,
        risk_engine=risk,
        paper_broker=broker,
        portfolio_provider=InMemoryPortfolioRiskStateProvider(
            {"balanced_v1": base_portfolio()}
        ),
        risk_profile_provider=InMemoryRiskProfileProvider(
            {"balanced_v1": demo_profile()}
        ),
        market_constraints_provider=InMemoryMarketConstraintsProvider(
            {"BTCUSDT": base_market()}
        ),
        kill_switch_provider=InMemoryKillSwitchStateProvider({}),
        journal=InMemoryPaperPipelineJournal(),
        clock=lambda: NOW,
    )
    result = await service.run(
        opportunity=make_opportunity(), market_context=make_context(), now=NOW
    )
    assert result.failure.code is PaperPipelineFailureCode.KILL_SWITCH_UNAVAILABLE
    assert risk.calls == 0
    assert broker.submit_calls == 0


@sync_test
async def test_decision_context_is_forwarded_to_orchestration_without_rebuild():
    service, orchestration, _, _ = make_service(orchestration_no_analysis())
    sentinel = object()

    result = await service.run(
        opportunity=make_opportunity(),
        market_context=make_context(),
        now=NOW,
        decision_context=sentinel,
    )

    assert result.status is PaperPipelineStatus.NO_ANALYSIS
    assert orchestration.last_decision_context is sentinel


@sync_test
async def test_explicit_specialist_contexts_are_relayed_unchanged_to_orchestration():
    service, orchestration, risk, broker = make_service(
        orchestration_no_analysis()
    )
    rio_context = object()
    specialist_contexts = {"rio": rio_context}

    result = await service.run(
        opportunity=make_opportunity(),
        market_context=make_context(),
        now=NOW,
        specialist_contexts=specialist_contexts,
    )

    assert result.status is PaperPipelineStatus.NO_ANALYSIS
    assert orchestration.last_specialist_contexts is specialist_contexts
    assert orchestration.last_specialist_contexts["rio"] is rio_context
    assert risk.calls == 0
    assert broker.submit_calls == 0
