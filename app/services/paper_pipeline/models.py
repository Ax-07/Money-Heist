from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Mapping
from uuid import UUID

from app.services.orchestration.models import OrchestrationResult
from app.trading.paper.models import BrokerOrder, Fill, OrderSide, OrderType, Position
from app.trading.risk.models import (
    KillSwitchState,
    MarketConstraints,
    PortfolioRiskState,
    RiskDecision,
    RiskProfile,
    TradeProposalRiskInput,
)


class PaperPipelineStatus(StrEnum):
    NO_ANALYSIS = "NO_ANALYSIS"
    NO_TRADE = "NO_TRADE"
    RISK_REJECTED = "RISK_REJECTED"
    EXECUTED = "EXECUTED"
    DUPLICATE_BLOCKED = "DUPLICATE_BLOCKED"
    FAILED = "FAILED"


class PaperPipelineFailureCode(StrEnum):
    AUDIT_UNAVAILABLE = "AUDIT_UNAVAILABLE"
    ORCHESTRATION_UNAVAILABLE = "ORCHESTRATION_UNAVAILABLE"
    ORCHESTRATION_FAILED = "ORCHESTRATION_FAILED"
    INCOHERENT_ORCHESTRATION_RESULT = "INCOHERENT_ORCHESTRATION_RESULT"
    PROPOSAL_ADAPTATION_FAILED = "PROPOSAL_ADAPTATION_FAILED"
    PORTFOLIO_STATE_UNAVAILABLE = "PORTFOLIO_STATE_UNAVAILABLE"
    RISK_PROFILE_UNAVAILABLE = "RISK_PROFILE_UNAVAILABLE"
    MARKET_CONSTRAINTS_UNAVAILABLE = "MARKET_CONSTRAINTS_UNAVAILABLE"
    KILL_SWITCH_UNAVAILABLE = "KILL_SWITCH_UNAVAILABLE"
    INVALID_EXECUTION_MARK = "INVALID_EXECUTION_MARK"
    DUPLICATE_EXECUTION = "DUPLICATE_EXECUTION"
    BROKER_EXECUTION_FAILED = "BROKER_EXECUTION_FAILED"
    INCOMPLETE_BROKER_EXECUTION = "INCOMPLETE_BROKER_EXECUTION"
    AUDIT_RECORDING_FAILED = "AUDIT_RECORDING_FAILED"


@dataclass(frozen=True, slots=True)
class PaperPipelineFailure:
    code: PaperPipelineFailureCode
    stage: str
    message: str


@dataclass(frozen=True, slots=True)
class RiskDecisionRecord:
    risk_decision_id: UUID
    decision: RiskDecision


@dataclass(frozen=True, slots=True)
class PaperOrderIntent:
    risk_decision_id: UUID
    system_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    client_order_id: str
    mode: str = field(default="PAPER", init=False)
    order_type: OrderType = field(default=OrderType.MARKET, init=False)

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("paper order intent quantity must be > 0")
        if not self.client_order_id.strip():
            raise ValueError("client_order_id must not be empty")


@dataclass(frozen=True, slots=True)
class PaperPipelineEvent:
    sequence: int
    stage: str
    status: str
    opportunity_id: str
    proposal_id: str | None
    source_snapshot_id: str
    created_at: datetime
    details: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PaperPipelineResult:
    status: PaperPipelineStatus
    opportunity_id: str
    source_snapshot_id: str
    orchestration_result: OrchestrationResult | None = None
    risk_input: TradeProposalRiskInput | None = None
    portfolio_state: PortfolioRiskState | None = None
    risk_profile: RiskProfile | None = None
    market_constraints: MarketConstraints | None = None
    kill_switch_state: KillSwitchState | None = None
    risk_record: RiskDecisionRecord | None = None
    order_intent: PaperOrderIntent | None = None
    order: BrokerOrder | None = None
    fill: Fill | None = None
    position_before: Position | None = None
    position_after: Position | None = None
    failure: PaperPipelineFailure | None = None
    audit_events: tuple[PaperPipelineEvent, ...] = ()
