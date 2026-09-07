from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.models import (
    BerlinAnalysis,
    EvidenceReference,
    NairobiAnalysis,
    PalermoReview,
    ProfessorPlan,
    TokyoAnalysis,
)


class ComputeLevel(StrEnum):
    SKIP_AI = "SKIP_AI"
    LEVEL_2_MINI_CREW = "LEVEL_2_MINI_CREW"
    LEVEL_3_FULL_CREW = "LEVEL_3_FULL_CREW"


class ComputeGateReason(StrEnum):
    ALLOWED_MINI_CREW = "ALLOWED_MINI_CREW"
    ALLOWED_FULL_CREW = "ALLOWED_FULL_CREW"
    PRIORITY_TOO_LOW = "PRIORITY_TOO_LOW"
    BUDGET_INSUFFICIENT = "BUDGET_INSUFFICIENT"
    OPPORTUNITY_EXPIRED = "OPPORTUNITY_EXPIRED"


class ComputeGateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    level: ComputeLevel
    reason: ComputeGateReason
    priority_score: int = Field(ge=0, le=100)
    remaining_budget_eur: Decimal = Field(ge=0)
    minimum_required_budget_eur: Decimal = Field(ge=0)

    @property
    def allows_ai(self) -> bool:
        return self.level is not ComputeLevel.SKIP_AI


class ProfessorTradeParameters(BaseModel):
    """Parameters proposed by the Professor; they are not risk authorization or sizing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_price: Decimal = Field(gt=0)
    stop_price: Decimal = Field(gt=0)
    targets: tuple[Decimal, ...] = Field(min_length=1)
    expected_rr: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def positive_targets(self) -> ProfessorTradeParameters:
        if any(target <= 0 for target in self.targets):
            raise ValueError("all targets must be positive")
        return self


class ProfessorFinalDecision(BaseModel):
    """Strict Batch 08 final decision used only by the orchestration pipeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction: Literal["LONG", "SHORT", "NO_TRADE"]
    confidence: float = Field(ge=0, le=1)
    thesis: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    invalidation: list[str] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    trade: ProfessorTradeParameters | None = None

    @model_validator(mode="after")
    def validate_trade_shape(self) -> ProfessorFinalDecision:
        if self.direction == "NO_TRADE":
            if self.trade is not None:
                raise ValueError("NO_TRADE cannot contain trade parameters")
            return self

        if self.trade is None:
            raise ValueError("LONG/SHORT requires a complete trade object")
        if not self.evidence:
            raise ValueError("LONG/SHORT requires at least one grounded evidence reference")
        if not self.invalidation:
            raise ValueError("LONG/SHORT requires an explicit invalidation")

        if self.direction == "LONG":
            if self.trade.stop_price >= self.trade.entry_price:
                raise ValueError("LONG stop_price must be below entry_price")
            if any(target <= self.trade.entry_price for target in self.trade.targets):
                raise ValueError("LONG targets must be above entry_price")
        else:
            if self.trade.stop_price <= self.trade.entry_price:
                raise ValueError("SHORT stop_price must be above entry_price")
            if any(target >= self.trade.entry_price for target in self.trade.targets):
                raise ValueError("SHORT targets must be below entry_price")
        return self


class TradeProposal(BaseModel):
    """Strict Batch 08 proposal. It is not an order and carries no position size."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    proposal_id: UUID
    opportunity_id: str
    source_snapshot_id: str
    system_id: str
    symbol: str
    timeframe: str
    side: Literal["LONG", "SHORT"]
    confidence: float = Field(ge=0, le=1)
    entry_price: Decimal = Field(gt=0)
    stop_price: Decimal = Field(gt=0)
    targets: tuple[Decimal, ...] = Field(min_length=1)
    expected_rr: Decimal = Field(gt=0)
    thesis: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    invalidation: tuple[str, ...] = Field(min_length=1)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1)
    market_regime: str
    feature_version: str
    professor_prompt_version: str
    professor_request_id: UUID
    specialist_request_ids: tuple[UUID, ...]
    palermo_request_id: UUID
    created_at: datetime
    expires_at: datetime


class SpecialistRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: Literal["berlin", "tokyo", "nairobi"]
    request_id: UUID
    prompt_version: str
    route_id: str
    model_id: str
    analysis: BerlinAnalysis | TokyoAnalysis | NairobiAnalysis

    @model_validator(mode="after")
    def matching_agent(self) -> SpecialistRunRecord:
        if self.analysis.agent != self.agent_id:
            raise ValueError("specialist analysis agent does not match run agent_id")
        return self


class PalermoRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID
    prompt_version: str
    route_id: str
    model_id: str
    review: PalermoReview


class AgentCallAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID
    agent_id: str
    phase: str
    prompt_version: str
    route_id: str
    model_id: str
    estimated_cost_eur: Decimal = Field(ge=0)
    attempts: int = Field(ge=1)


class PipelineAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    stage: str
    status: Literal["STARTED", "COMPLETED", "SKIPPED", "FAILED"]
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PipelineFailureCode(StrEnum):
    INVALID_CONTEXT = "INVALID_CONTEXT"
    INVALID_PROFESSOR_PLAN = "INVALID_PROFESSOR_PLAN"
    INVALID_SPECIALIST_OUTPUT = "INVALID_SPECIALIST_OUTPUT"
    UNGROUNDED_EVIDENCE = "UNGROUNDED_EVIDENCE"
    INVALID_PALERMO_OUTPUT = "INVALID_PALERMO_OUTPUT"
    INVALID_PROFESSOR_OUTPUT = "INVALID_PROFESSOR_OUTPUT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    AI_PROVIDER_ERROR = "AI_PROVIDER_ERROR"


class PipelineFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: PipelineFailureCode
    stage: str
    message: str
    agent_id: str | None = None


class PipelineStatus(StrEnum):
    NO_ANALYSIS = "NO_ANALYSIS"
    NO_TRADE = "NO_TRADE"
    TRADE_PROPOSAL = "TRADE_PROPOSAL"
    FAILED = "FAILED"


class OrchestrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: PipelineStatus
    opportunity_id: str
    source_snapshot_id: str
    system_id: str
    symbol: str
    compute_gate: ComputeGateDecision | None = None
    professor_plan: ProfessorPlan | None = None
    specialist_runs: tuple[SpecialistRunRecord, ...] = ()
    palermo_run: PalermoRunRecord | None = None
    professor_decision: ProfessorFinalDecision | None = None
    trade_proposal: TradeProposal | None = None
    failure: PipelineFailure | None = None
    agent_calls: tuple[AgentCallAudit, ...] = ()
    audit_events: tuple[PipelineAuditEvent, ...] = ()

    @model_validator(mode="after")
    def coherent_result(self) -> OrchestrationResult:
        if self.status is PipelineStatus.TRADE_PROPOSAL:
            if self.trade_proposal is None or self.professor_decision is None:
                raise ValueError("TRADE_PROPOSAL status requires proposal and final decision")
            if self.professor_decision.direction == "NO_TRADE":
                raise ValueError("TRADE_PROPOSAL cannot come from NO_TRADE")
            if self.failure is not None:
                raise ValueError("successful proposal cannot include a failure")
        elif self.status is PipelineStatus.NO_TRADE:
            if self.professor_decision is None or self.professor_decision.direction != "NO_TRADE":
                raise ValueError("NO_TRADE status requires a NO_TRADE final decision")
            if self.trade_proposal is not None or self.failure is not None:
                raise ValueError("NO_TRADE cannot include proposal/failure")
        elif self.status is PipelineStatus.FAILED:
            if self.failure is None or self.trade_proposal is not None:
                raise ValueError("FAILED status requires failure and forbids proposal")
        elif self.trade_proposal is not None or self.failure is not None:
            raise ValueError("NO_ANALYSIS cannot include proposal/failure")
        return self
