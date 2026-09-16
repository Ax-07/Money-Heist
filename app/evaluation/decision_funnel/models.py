from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DecisionFunnelObservationCounts(FrozenModel):
    pre_scanner_warmup_skipped: int = Field(default=0, ge=0)
    pre_scanner_not_decision_close_skipped: int = Field(default=0, ge=0)

    @property
    def total_pre_scanner_skipped(self) -> int:
        return (
            self.pre_scanner_warmup_skipped
            + self.pre_scanner_not_decision_close_skipped
        )


class DecisionFunnelCounts(FrozenModel):
    candles_evaluated: int = Field(ge=0)
    scanner_evaluations: int = Field(ge=0)
    scanner_no_trigger: int = Field(ge=0)
    scanner_triggered: int = Field(ge=0)
    candidate_opportunities: int = Field(ge=0)
    compute_gate_allowed: int = Field(ge=0)
    compute_gate_blocked: int = Field(ge=0)
    ai_orchestrations_triggered: int = Field(ge=0)
    professor_plan_no_analysis: int = Field(ge=0)
    orchestration_failed: int = Field(ge=0)
    professor_no_trade: int = Field(ge=0)
    trade_proposals_created: int = Field(ge=0)
    risk_rejected: int = Field(ge=0)
    risk_resized: int = Field(ge=0)
    risk_approved: int = Field(ge=0)
    paper_pipeline_failed: int = Field(ge=0)
    duplicate_execution_blocked: int = Field(ge=0)
    orders_submitted: int = Field(ge=0)
    fills: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_internal_conservation(self) -> DecisionFunnelCounts:
        if self.scanner_evaluations != self.scanner_no_trigger + self.scanner_triggered:
            raise ValueError(
                "scanner_evaluations must equal scanner_no_trigger + scanner_triggered"
            )
        if self.candidate_opportunities > self.scanner_triggered:
            raise ValueError("candidate_opportunities cannot exceed scanner_triggered")
        if self.compute_gate_allowed + self.compute_gate_blocked > self.candidate_opportunities:
            raise ValueError("Compute Gate decisions cannot exceed candidate opportunities")
        if self.trade_proposals_created > self.candidate_opportunities:
            raise ValueError("trade proposals cannot exceed candidate opportunities")
        if self.orders_submitted > self.risk_approved + self.risk_resized:
            raise ValueError("orders_submitted cannot exceed authorized Risk decisions")
        if self.fills > self.orders_submitted:
            raise ValueError("fills cannot exceed orders_submitted")
        return self


class DecisionFunnelReasonCount(FrozenModel):
    stage: str = Field(min_length=1)
    code: str = Field(min_length=1)
    count: int = Field(ge=1)


class DecisionFunnelPostHoc(FrozenModel):
    closed_trades: int = Field(ge=0)
    broker_orders_total: int = Field(ge=0)
    broker_fills_total: int = Field(ge=0)


class DecisionFunnelReport(FrozenModel):
    schema_version: str = "money-heist.decision-funnel.v1"
    run_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    period_start: datetime
    period_end: datetime
    observation_counts: DecisionFunnelObservationCounts
    counts: DecisionFunnelCounts
    reason_counts: tuple[DecisionFunnelReasonCount, ...] = ()
    post_hoc: DecisionFunnelPostHoc

    @model_validator(mode="after")
    def validate_candle_conservation(self) -> DecisionFunnelReport:
        expected = (
            self.observation_counts.total_pre_scanner_skipped
            + self.counts.scanner_evaluations
        )
        if self.counts.candles_evaluated != expected:
            raise ValueError(
                "candles_evaluated must equal pre-Scanner skips + scanner_evaluations"
            )
        ordered = tuple(sorted(self.reason_counts, key=lambda item: (item.stage, item.code)))
        if self.reason_counts != ordered:
            raise ValueError("reason_counts must be sorted deterministically")
        return self
