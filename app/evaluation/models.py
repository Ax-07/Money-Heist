from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


ZERO = Decimal("0")


class MetricStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNBOUNDED = "UNBOUNDED"


class DataKind(StrEnum):
    PAPER_EXECUTED = "PAPER_EXECUTED"
    COUNTERFACTUAL = "COUNTERFACTUAL"


class SelfFundingStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    ZERO_AI_COST = "ZERO_AI_COST"
    TRADING_NET_UNAVAILABLE = "TRADING_NET_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class Metric:
    value: Decimal | None
    status: MetricStatus
    reason: str | None = None

    @classmethod
    def available(cls, value: Decimal) -> Metric:
        return cls(value=value, status=MetricStatus.AVAILABLE)

    @classmethod
    def unavailable(cls, reason: str) -> Metric:
        return cls(value=None, status=MetricStatus.UNAVAILABLE, reason=reason)

    @classmethod
    def unbounded(cls, reason: str) -> Metric:
        return cls(value=None, status=MetricStatus.UNBOUNDED, reason=reason)


@dataclass(frozen=True, slots=True)
class SelfFundingRatio:
    value: Decimal | None
    status: SelfFundingStatus
    basis: str


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    fill_id: str
    broker_order_id: str
    system_id: str
    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    filled_at: datetime
    slippage_cost: Decimal | None
    data_kind: DataKind = DataKind.PAPER_EXECUTED

    def __post_init__(self) -> None:
        if self.data_kind is not DataKind.PAPER_EXECUTED:
            raise ValueError("ExecutionRecord accepts only PAPER_EXECUTED data")
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if self.order_type not in {"MARKET", "LIMIT"}:
            raise ValueError("order_type must be MARKET or LIMIT")
        if self.quantity <= ZERO or self.price <= ZERO:
            raise ValueError("execution quantity and price must be > 0")
        if self.fee < ZERO:
            raise ValueError("fee must be >= 0")
        if self.slippage_cost is not None and self.slippage_cost < ZERO:
            raise ValueError("slippage_cost must be >= 0 when available")


@dataclass(frozen=True, slots=True)
class EquityPoint:
    observed_at: datetime
    equity: Decimal
    data_kind: DataKind = DataKind.PAPER_EXECUTED

    def __post_init__(self) -> None:
        if self.data_kind is not DataKind.PAPER_EXECUTED:
            raise ValueError("realized equity series must be PAPER_EXECUTED")


@dataclass(frozen=True, slots=True)
class AIUsageEntry:
    request_id: str
    agent_id: str
    route_id: str
    model_id: str
    estimated_cost_eur: Decimal
    latency_ms: int | None
    attempt: int
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.estimated_cost_eur < ZERO:
            raise ValueError("estimated_cost_eur must be >= 0")
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError("latency_ms must be >= 0")
        if self.attempt < 1:
            raise ValueError("attempt must be >= 1")


@dataclass(frozen=True, slots=True)
class AgentCallEntry:
    request_id: str
    agent_id: str
    opportunity_id: str
    phase: str
    prompt_version: str | None
    route_id: str | None
    model_id: str | None


@dataclass(frozen=True, slots=True)
class AgentObservation:
    request_id: str
    agent_id: str
    opportunity_id: str
    phase: str
    stance: str | None
    confidence: Decimal | None
    final_decision: str | None

    def __post_init__(self) -> None:
        if self.confidence is not None and not (ZERO <= self.confidence <= Decimal("1")):
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class OpportunityTrace:
    opportunity_id: str
    source_snapshot_id: str
    system_id: str | None
    final_decision: str | None
    proposal_id: str | None
    risk_decision_id: str | None
    risk_status: str | None
    broker_order_id: str | None
    fill_id: str | None
    prompt_versions: tuple[str, ...] = ()
    agent_calls: tuple[AgentCallEntry, ...] = ()
    observations: tuple[AgentObservation, ...] = ()
    agent_request_ids: tuple[str, ...] = ()
    data_kind: DataKind = DataKind.PAPER_EXECUTED

    def __post_init__(self) -> None:
        if self.data_kind is not DataKind.PAPER_EXECUTED:
            raise ValueError("OpportunityTrace accepts only PAPER_EXECUTED data")


@dataclass(frozen=True, slots=True)
class CounterfactualOutcome:
    opportunity_id: str
    label: str
    hypothetical_pnl: Decimal | None = None
    notes: tuple[str, ...] = ()
    data_kind: DataKind = field(default=DataKind.COUNTERFACTUAL, init=False)


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    trade_id: str
    system_id: str
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    opened_at: datetime
    closed_at: datetime
    execution_gross_pnl: Decimal
    fees: Decimal
    slippage_cost: Decimal | None
    gross_pnl_before_costs: Decimal | None
    net_pnl: Decimal
    exit_fill_id: str


@dataclass(frozen=True, slots=True)
class ReconstructedPosition:
    system_id: str
    symbol: str
    signed_quantity: Decimal
    average_entry: Decimal
    entry_fees: Decimal
    entry_slippage_cost: Decimal | None

    @property
    def side(self) -> str | None:
        if self.signed_quantity > ZERO:
            return "LONG"
        if self.signed_quantity < ZERO:
            return "SHORT"
        return None


@dataclass(frozen=True, slots=True)
class TradingMetrics:
    executed_fill_count: int
    executed_order_count: int
    closed_trade_count: int
    open_position_count: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    execution_realized_pnl: Decimal
    fees_paid: Decimal
    slippage_cost: Metric
    gross_pnl_before_costs: Metric
    realized_trading_net: Decimal
    unrealized_pnl: Metric
    trading_net: Metric
    gross_exposure: Metric
    win_rate: Metric
    profit_factor: Metric
    expectancy: Metric
    max_drawdown_abs: Metric
    max_drawdown_pct: Metric
    positions: tuple[ReconstructedPosition, ...]
    closed_trades: tuple[ClosedTrade, ...]


@dataclass(frozen=True, slots=True)
class AICostMetrics:
    total_cost_eur: Decimal
    by_agent: Mapping[str, Decimal]
    by_model: Mapping[str, Decimal]
    by_route: Mapping[str, Decimal]
    by_opportunity: Mapping[str, Decimal]
    by_risk_decision: Mapping[str, Decimal]
    by_trade: Mapping[str, Decimal]
    unattributed_to_opportunity_eur: Decimal
    average_cost_per_opportunity: Metric
    average_cost_per_risk_decision: Metric
    average_cost_per_executed_trade: Metric

    @staticmethod
    def freeze(mapping: Mapping[str, Decimal]) -> Mapping[str, Decimal]:
        return MappingProxyType(dict(sorted(mapping.items())))


@dataclass(frozen=True, slots=True)
class AgentMetrics:
    agent_id: str
    call_count: int
    attempt_count: int
    total_cost_eur: Decimal
    average_cost_eur: Metric
    average_latency_ms: Metric
    participation_frequency: Metric
    disagreement_frequency: Metric
    average_confidence: Metric
    stance_counts: Mapping[str, int]
    final_decision_counts: Mapping[str, int]
    prompt_versions: tuple[str, ...]
    route_ids: tuple[str, ...]
    model_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LisbonRecommendation:
    code: str
    message: str
    agent_id: str | None = None


@dataclass(frozen=True, slots=True)
class LisbonEvaluationReport:
    report_version: str
    data_scope: str
    trading_net: Metric
    ai_cost_eur: Decimal
    economic_net: Metric
    self_funding_ratio: SelfFundingRatio
    observations: tuple[str, ...]
    recommendations: tuple[LisbonRecommendation, ...]


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    report_version: str
    trading: TradingMetrics
    ai_costs: AICostMetrics
    agents: tuple[AgentMetrics, ...]
    opportunity_traces: tuple[OpportunityTrace, ...]
    counterfactual_outcomes: tuple[CounterfactualOutcome, ...]
    economic_net: Metric
    self_funding_ratio: SelfFundingRatio
    lisbon: LisbonEvaluationReport


@dataclass(frozen=True, slots=True)
class EvaluationSource:
    executions: tuple[ExecutionRecord, ...] = ()
    marks: Mapping[str, Decimal] = field(default_factory=dict)
    equity_points: tuple[EquityPoint, ...] = ()
    ai_usage: tuple[AIUsageEntry, ...] = ()
    opportunity_traces: tuple[OpportunityTrace, ...] = ()
    counterfactual_outcomes: tuple[CounterfactualOutcome, ...] = ()
