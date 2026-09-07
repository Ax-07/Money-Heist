from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DashboardAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    UNBOUNDED = "UNBOUNDED"


class DashboardProvenance(StrEnum):
    SHADOW_PAPER = "SHADOW_PAPER"
    PAPER_EXECUTED = "PAPER_EXECUTED"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    UNAVAILABLE = "UNAVAILABLE"


class DashboardEventKind(StrEnum):
    AUDIT = "AUDIT"
    RISK = "RISK"
    SECURITY = "SECURITY"
    EVALUATION = "EVALUATION"


class DashboardEventSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DashboardMetric(FrozenModel):
    name: str
    value: Decimal | None = None
    availability: DashboardAvailability
    unit: str | None = None
    reason: str | None = None
    provenance: DashboardProvenance = DashboardProvenance.SHADOW_PAPER


class DashboardAccount(FrozenModel):
    availability: DashboardAvailability
    reason: str | None = None
    initial_balance: Decimal | None = None
    cash_balance: Decimal | None = None
    equity: Decimal | None = None
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    fees_paid: Decimal | None = None
    gross_exposure: Decimal | None = None
    open_positions: int | None = None


class DashboardPosition(FrozenModel):
    system_id: str
    symbol: str
    side: str | None
    quantity: Decimal
    average_entry: Decimal
    realized_pnl: Decimal
    provenance: DashboardProvenance = DashboardProvenance.SHADOW_PAPER


class DashboardOrder(FrozenModel):
    broker_order_id: str
    client_order_id: str
    system_id: str
    symbol: str
    side: str
    order_type: str
    requested_quantity: Decimal
    filled_quantity: Decimal
    status: str
    limit_price: Decimal | None = None
    average_fill_price: Decimal | None = None
    reject_reason: str | None = None
    trigger: str | None = None
    created_at: datetime
    updated_at: datetime
    provenance: DashboardProvenance = DashboardProvenance.SHADOW_PAPER


class DashboardFill(FrozenModel):
    fill_id: str
    broker_order_id: str
    price: Decimal
    quantity: Decimal
    fee: Decimal
    liquidity: str
    filled_at: datetime
    provenance: DashboardProvenance = DashboardProvenance.PAPER_EXECUTED


class DashboardOpportunity(FrozenModel):
    system_id: str
    opportunity_id: str
    root_opportunity_id: str | None = None
    source_snapshot_id: str
    symbol: str
    timeframe: str
    priority_score: int | None = None
    triggers: tuple[str, ...] = ()
    created_at: datetime | None = None
    expires_at: datetime | None = None
    provenance: DashboardProvenance = DashboardProvenance.SHADOW_PAPER


class DashboardProfessorDecision(FrozenModel):
    direction: str
    confidence: float
    thesis: tuple[str, ...] = ()
    counter_evidence: tuple[str, ...] = ()
    invalidation: tuple[str, ...] = ()


class DashboardTradeProposal(FrozenModel):
    proposal_id: str
    opportunity_id: str
    source_snapshot_id: str
    system_id: str
    symbol: str
    timeframe: str
    side: str
    confidence: float
    entry_price: Decimal
    stop_price: Decimal
    targets: tuple[Decimal, ...]
    expected_rr: Decimal
    market_regime: str
    expires_at: datetime
    provenance: DashboardProvenance = DashboardProvenance.SHADOW_PAPER


class DashboardRiskDecision(FrozenModel):
    risk_decision_id: str
    proposal_id: str
    status: str
    reason_codes: tuple[str, ...]
    approved_quantity: Decimal
    approved_risk_amount: Decimal
    approved_notional: Decimal
    created_at: datetime


class DashboardDecision(FrozenModel):
    system_id: str
    opportunity_id: str
    source_snapshot_id: str
    pipeline_status: str
    branch_status: str
    professor: DashboardProfessorDecision | None = None
    proposal: DashboardTradeProposal | None = None
    risk: DashboardRiskDecision | None = None
    failure_code: str | None = None
    failure_stage: str | None = None
    failure_message: str | None = None
    provenance: DashboardProvenance = DashboardProvenance.SHADOW_PAPER


class DashboardAIUsage(FrozenModel):
    availability: DashboardAvailability
    reason: str | None = None
    record_count: int
    total_cost_eur: Decimal | None = None
    by_agent_eur: dict[str, Decimal] = Field(default_factory=dict)
    by_model_eur: dict[str, Decimal] = Field(default_factory=dict)


class DashboardCounterfactual(FrozenModel):
    opportunity_id: str
    label: str
    hypothetical_pnl: Decimal | None = None
    notes: tuple[str, ...] = ()
    provenance: DashboardProvenance = DashboardProvenance.COUNTERFACTUAL


class DashboardAgentMetric(FrozenModel):
    agent_id: str
    call_count: int
    attempt_count: int
    total_cost_eur: Decimal
    average_cost_eur: DashboardMetric
    average_latency_ms: DashboardMetric
    participation_frequency: DashboardMetric
    disagreement_frequency: DashboardMetric
    average_confidence: DashboardMetric


class DashboardBatch10(FrozenModel):
    status: str
    metrics: dict[str, DashboardMetric] = Field(default_factory=dict)
    agents: tuple[DashboardAgentMetric, ...] = ()
    counterfactuals: tuple[DashboardCounterfactual, ...] = ()
    failure: str | None = None


class DashboardSystem(FrozenModel):
    system_id: str
    family: str
    display_name: str
    aliases: tuple[str, ...]
    mode: str = "SHADOW"
    execution_mode: str = "PAPER"
    live_execution: bool = False
    account: DashboardAccount
    positions_availability: DashboardAvailability
    positions_reason: str | None = None
    positions: tuple[DashboardPosition, ...] = ()
    orders_availability: DashboardAvailability
    orders_reason: str | None = None
    orders: tuple[DashboardOrder, ...] = ()
    fills_availability: DashboardAvailability
    fills_reason: str | None = None
    fills: tuple[DashboardFill, ...] = ()
    latest_decision: DashboardDecision | None = None
    ai_usage: DashboardAIUsage
    batch10: DashboardBatch10


class DashboardPairwiseDelta(FrozenModel):
    left_system_id: str
    right_system_id: str
    left_value: Decimal
    right_value: Decimal
    delta_right_minus_left: Decimal


class DashboardComparisonMetric(FrozenModel):
    metric: str
    availability: DashboardAvailability
    values: dict[str, Decimal | None]
    pairwise_deltas: tuple[DashboardPairwiseDelta, ...] = ()


class DashboardComparison(FrozenModel):
    metrics: dict[str, DashboardComparisonMetric]
    promotion_system_id: None = None
    risk_change: None = None
    authority: str = "OBSERVATION_ONLY"


class DashboardEvent(FrozenModel):
    event_id: str
    kind: DashboardEventKind
    severity: DashboardEventSeverity
    system_id: str | None = None
    opportunity_id: str | None = None
    source: str
    stage: str | None = None
    status: str | None = None
    code: str | None = None
    message: str | None = None
    created_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class DashboardSnapshot(FrozenModel):
    schema_version: str = "12.0"
    generated_at: datetime
    read_only: bool = True
    live_execution: bool = False
    execution_scope: str = "PAPER_SHADOW_ONLY"
    system_state: str
    root_correlation_id: str | None = None
    root_opportunity_id: str | None = None
    root_snapshot_id: str | None = None
    systems: tuple[DashboardSystem, ...]
    opportunities: tuple[DashboardOpportunity, ...] = ()
    decisions: tuple[DashboardDecision, ...] = ()
    comparison: DashboardComparison
    events: tuple[DashboardEvent, ...] = ()

    def by_system_id(self) -> dict[str, DashboardSystem]:
        return {system.system_id: system for system in self.systems}
