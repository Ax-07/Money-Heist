from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from app.agents.models import EvidenceReference
from app.market.features.models import FeatureQuality, FeatureSnapshot, MarketRegime
from app.market.scanner.models import CandidateOpportunity, ScannerTrigger
from app.services.orchestration.models import (
    OrchestrationResult,
    PipelineStatus,
    ProfessorFinalDecision,
    ProfessorTradeParameters,
    TradeProposal,
)
from app.services.shadow import DEFAULT_SHADOW_SYSTEMS, build_shadow_runtime
from app.trading.paper import PaperBrokerConfig
from app.trading.risk import (
    MarketConstraints,
    PortfolioRiskState,
    RiskProfile,
)


NOW = datetime(2026, 9, 7, 16, 30, tzinfo=timezone.utc)
ROOT_OPPORTUNITY_ID = "70000000-0000-0000-0000-000000000011"
SNAPSHOT_ID = "snapshot-shadow-root-11"
SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"


def run(coro):
    return asyncio.run(coro)


def market_context(*, close: float = 100.0) -> FeatureSnapshot:
    return FeatureSnapshot(
        feature_version="features-v1",
        snapshot_id=SNAPSHOT_ID,
        source_snapshot_id="raw-shadow-root-11",
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
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


def root_opportunity() -> CandidateOpportunity:
    # The scanner's original system_id is deliberately neutral. Batch 11 derives
    # one immutable opportunity clone per SHADOW system.
    return CandidateOpportunity(
        scanner_version="scanner-v1",
        opportunity_id=ROOT_OPPORTUNITY_ID,
        snapshot_id=SNAPSHOT_ID,
        system_id="shadow_root",
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        priority_score=80,
        triggers=(ScannerTrigger.RANGE_BREAK,),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )


def portfolio_state(
    *,
    equity: str = "100",
    day_start_equity: str = "100",
    equity_peak: str = "100",
    daily_pnl: str = "0",
    open_positions: int = 0,
    open_risk_amount: str = "0",
    correlated_risk_amount: str = "0",
    gross_exposure_amount: str = "0",
) -> PortfolioRiskState:
    return PortfolioRiskState(
        equity=Decimal(equity),
        day_start_equity=Decimal(day_start_equity),
        equity_peak=Decimal(equity_peak),
        daily_pnl=Decimal(daily_pnl),
        open_positions=open_positions,
        open_risk_amount=Decimal(open_risk_amount),
        correlated_risk_amount=Decimal(correlated_risk_amount),
        gross_exposure_amount=Decimal(gross_exposure_amount),
    )


def explicit_test_profile(
    system_id: str,
    *,
    max_positions: int = 3,
    max_risk_per_trade_pct: str = "0.01",
    max_daily_loss_pct: str = "0.05",
    max_drawdown_pct: str = "0.20",
    max_portfolio_risk_pct: str = "0.03",
    max_leverage: str = "1",
    max_correlated_exposure_pct: str = "0.03",
    min_expected_rr: str | None = None,
) -> RiskProfile:
    """Explicit test-only profile; never a Conservative/Balanced/Aggressive preset."""

    return RiskProfile(
        risk_profile_id=f"test:{system_id}",
        max_risk_per_trade_pct=Decimal(max_risk_per_trade_pct),
        max_daily_loss_pct=Decimal(max_daily_loss_pct),
        max_drawdown_pct=Decimal(max_drawdown_pct),
        max_portfolio_risk_pct=Decimal(max_portfolio_risk_pct),
        max_positions=max_positions,
        max_leverage=Decimal(max_leverage),
        max_correlated_exposure_pct=Decimal(max_correlated_exposure_pct),
        min_expected_rr=(Decimal(min_expected_rr) if min_expected_rr is not None else None),
    )


def market_constraints() -> dict[str, MarketConstraints]:
    return {
        SYMBOL: MarketConstraints(
            qty_step=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            min_notional=Decimal("1"),
            max_qty=None,
            max_leverage=Decimal("1"),
        )
    }


def paper_config(
    system_id: str,
    *,
    initial_balance: str = "100",
    taker_fee_bps: str = "10",
    market_slippage_bps: str = "0",
) -> PaperBrokerConfig:
    return PaperBrokerConfig(
        system_id=system_id,
        initial_balance=Decimal(initial_balance),
        maker_fee_bps=Decimal("10"),
        taker_fee_bps=Decimal(taker_fee_bps),
        market_slippage_bps=Decimal(market_slippage_bps),
        allow_short=True,
    )


class ScenarioOrchestration:
    """Strict Batch 08-compatible deterministic test orchestration."""

    def __init__(
        self,
        *,
        outcome: str = "TRADE",
        side: str = "LONG",
        fail_with: Exception | None = None,
        expected_rr: str = "2",
    ) -> None:
        self.outcome = outcome
        self.side = side
        self.fail_with = fail_with
        self.expected_rr = Decimal(expected_rr)
        self.calls = 0
        self.received_opportunities = []
        self.received_market_contexts = []

    async def run(self, *, opportunity, market_context, now=None):
        del now
        self.calls += 1
        self.received_opportunities.append(opportunity)
        self.received_market_contexts.append(market_context)
        if self.fail_with is not None:
            raise self.fail_with

        if self.outcome == "NO_ANALYSIS":
            return OrchestrationResult(
                status=PipelineStatus.NO_ANALYSIS,
                opportunity_id=opportunity.opportunity_id,
                source_snapshot_id=market_context.snapshot_id,
                system_id=opportunity.system_id,
                symbol=opportunity.symbol,
            )

        if self.outcome == "NO_TRADE":
            final = ProfessorFinalDecision(
                direction="NO_TRADE",
                confidence=0.5,
                thesis=["test no-trade"],
                counter_evidence=["test counter-evidence"],
                invalidation=[],
                evidence=[],
                trade=None,
            )
            return OrchestrationResult(
                status=PipelineStatus.NO_TRADE,
                opportunity_id=opportunity.opportunity_id,
                source_snapshot_id=market_context.snapshot_id,
                system_id=opportunity.system_id,
                symbol=opportunity.symbol,
                professor_decision=final,
            )

        stop = Decimal("98") if self.side == "LONG" else Decimal("102")
        target = Decimal("104") if self.side == "LONG" else Decimal("96")
        trade = ProfessorTradeParameters(
            entry_price=Decimal("100"),
            stop_price=stop,
            targets=(target,),
            expected_rr=self.expected_rr,
        )
        final = ProfessorFinalDecision(
            direction=self.side,
            confidence=0.7,
            thesis=["deterministic Batch 11 test trade"],
            counter_evidence=["deterministic caution"],
            invalidation=["stop invalidates thesis"],
            evidence=[
                EvidenceReference(
                    source_key="market_context.close",
                    observation="close=100",
                )
            ],
            trade=trade,
        )
        proposal_id = uuid5(
            NAMESPACE_URL,
            f"money-heist:shadow:test:proposal:{opportunity.opportunity_id}:{self.side}",
        )
        professor_request_id = uuid5(
            NAMESPACE_URL,
            f"money-heist:shadow:test:professor:{opportunity.opportunity_id}:{self.side}",
        )
        palermo_request_id = uuid5(
            NAMESPACE_URL,
            f"money-heist:shadow:test:palermo:{opportunity.opportunity_id}:{self.side}",
        )
        proposal = TradeProposal(
            proposal_id=proposal_id,
            opportunity_id=opportunity.opportunity_id,
            source_snapshot_id=market_context.snapshot_id,
            system_id=opportunity.system_id,
            symbol=opportunity.symbol,
            timeframe=opportunity.timeframe,
            side=self.side,
            confidence=0.7,
            entry_price=trade.entry_price,
            stop_price=trade.stop_price,
            targets=trade.targets,
            expected_rr=trade.expected_rr,
            thesis=("deterministic Batch 11 test trade",),
            counter_evidence=("deterministic caution",),
            invalidation=("stop invalidates thesis",),
            evidence=tuple(final.evidence),
            market_regime=market_context.regime.value,
            feature_version=market_context.feature_version,
            professor_prompt_version="test-v1",
            professor_request_id=professor_request_id,
            specialist_request_ids=(),
            palermo_request_id=palermo_request_id,
            created_at=NOW,
            expires_at=opportunity.expires_at,
        )
        return OrchestrationResult(
            status=PipelineStatus.TRADE_PROPOSAL,
            opportunity_id=opportunity.opportunity_id,
            source_snapshot_id=market_context.snapshot_id,
            system_id=opportunity.system_id,
            symbol=opportunity.symbol,
            professor_decision=final,
            trade_proposal=proposal,
        )


@dataclass(frozen=True)
class FakeAIUsage:
    system_id: str
    estimated_cost: Decimal
    agent_id: str = "professor"
    model_id: str = "test-model"
    route_id: str = "test-route"


def make_runtime(
    identity,
    *,
    orchestration: ScenarioOrchestration | None = None,
    risk_profile: RiskProfile | None | object = ...,
    portfolio: PortfolioRiskState | None = None,
    initial_balance: str = "100",
    fee_bps: str = "10",
    market_constraints_override=None,
    risk_engine=None,
):
    orchestration = orchestration or ScenarioOrchestration()
    if risk_profile is ...:
        risk_profile = explicit_test_profile(identity.system_id)
    return build_shadow_runtime(
        identity=identity,
        orchestration=orchestration,
        paper_broker_config=paper_config(
            identity.system_id,
            initial_balance=initial_balance,
            taker_fee_bps=fee_bps,
        ),
        portfolio_state=portfolio or portfolio_state(),
        market_constraints=(
            market_constraints_override
            if market_constraints_override is not None
            else market_constraints()
        ),
        risk_profile=risk_profile,
        risk_engine=risk_engine,
        clock=lambda: NOW,
    )


def three_runtimes(
    *,
    outcomes: tuple[str, str, str] = ("TRADE", "TRADE", "TRADE"),
    sides: tuple[str, str, str] = ("LONG", "LONG", "LONG"),
):
    result = []
    for identity, outcome, side in zip(DEFAULT_SHADOW_SYSTEMS, outcomes, sides, strict=True):
        result.append(
            make_runtime(
                identity,
                orchestration=ScenarioOrchestration(outcome=outcome, side=side),
            )
        )
    return tuple(result)
