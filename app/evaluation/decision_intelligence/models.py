from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.canonical import stable_digest, stable_uuid

DECISION_INTELLIGENCE_RECORD_SCHEMA_VERSION = "money-heist.decision-intelligence-record.v1"
DECISION_INTELLIGENCE_RECORD_SET_SCHEMA_VERSION = (
    "money-heist.decision-intelligence-record-set.v1"
)
DECISION_INTELLIGENCE_RECORD_POLICY_VERSION = "decision-intelligence-projection-v1"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _normalize_sha256(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a 64-character hexadecimal digest")
    return normalized


class StageTrace(FrozenModel):
    sequence: int = Field(ge=1)
    stage: str = Field(min_length=1)
    status: str = Field(min_length=1)


class FailureProjection(FrozenModel):
    code: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    message: str = Field(min_length=1)
    agent_id: str | None = None

    @field_validator("message")
    @classmethod
    def reject_obvious_secret_material(cls, value: str) -> str:
        lowered = value.lower()
        forbidden_fragments = (
            "authorization:",
            "bearer ",
            "openai_api_key",
            "api_key=",
            "api-key=",
            "sk-proj-",
            "sk-live-",
        )
        if any(fragment in lowered for fragment in forbidden_fragments):
            raise ValueError("failure message appears to contain secret material")
        return value


class EvidenceProjection(FrozenModel):
    source_key: str = Field(min_length=1)
    observation: str = Field(min_length=1)


class AgentCallProjection(FrozenModel):
    request_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    route_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    estimated_cost_eur: Decimal = Field(ge=0)
    attempts: int = Field(ge=1)


class ScannerProjection(FrozenModel):
    snapshot_id: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    scanner_version: str = Field(min_length=1)
    market_regime: str | None = None
    score: int = Field(ge=0, le=100)
    priority_score: int = Field(ge=0, le=100)
    triggers: tuple[str, ...]
    observed_at: datetime
    expires_at: datetime

    @field_validator("observed_at", "expires_at")
    @classmethod
    def normalize_datetimes(cls, value: datetime, info) -> datetime:
        return _as_utc(value, field_name=info.field_name)


class ComputeGateProjection(FrozenModel):
    reached: bool
    level: str | None = None
    reason: str | None = None
    priority_score: int | None = Field(default=None, ge=0, le=100)
    remaining_budget_eur: Decimal | None = Field(default=None, ge=0)
    minimum_required_budget_eur: Decimal | None = Field(default=None, ge=0)
    allows_ai: bool | None = None

    @model_validator(mode="after")
    def validate_reachability(self) -> ComputeGateProjection:
        values = (
            self.level,
            self.reason,
            self.priority_score,
            self.remaining_budget_eur,
            self.minimum_required_budget_eur,
            self.allows_ai,
        )
        if self.reached and any(value is None for value in values):
            raise ValueError("reached Compute Gate requires the canonical decision fields")
        if not self.reached and any(value is not None for value in values):
            raise ValueError("not-reached Compute Gate cannot carry decision fields")
        return self


class DecisionContextRef(FrozenModel):
    present: bool
    context_id: str | None = None
    context_fingerprint: str | None = None
    schema_version: str | None = None
    context_version: str | None = None
    system_id: str | None = None
    symbol: str | None = None
    as_of: datetime | None = None
    primary_timeframe: str | None = None
    timeframe_policy_version: str | None = None
    source_cursor_fingerprint: str | None = None

    @field_validator("as_of")
    @classmethod
    def normalize_as_of(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _as_utc(value, field_name="as_of")

    @field_validator("context_fingerprint", "source_cursor_fingerprint")
    @classmethod
    def normalize_fingerprints(cls, value: str | None, info) -> str | None:
        return _normalize_sha256(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_presence(self) -> DecisionContextRef:
        material = (
            self.context_id,
            self.context_fingerprint,
            self.schema_version,
            self.context_version,
            self.system_id,
            self.symbol,
            self.as_of,
            self.primary_timeframe,
            self.timeframe_policy_version,
            self.source_cursor_fingerprint,
        )
        if self.present and any(value is None for value in material):
            raise ValueError("present DecisionContext reference is incomplete")
        if not self.present and any(value is not None for value in material):
            raise ValueError("absent DecisionContext reference cannot carry fields")
        return self


class ProfessorPlanProjection(FrozenModel):
    reached: bool
    stage_status: str | None = None
    decision: str | None = None
    selected_agents: tuple[str, ...] = ()
    rationale: tuple[str, ...] = ()
    request_more_analysis: bool | None = None
    call: AgentCallProjection | None = None

    @model_validator(mode="after")
    def validate_reachability(self) -> ProfessorPlanProjection:
        if self.reached:
            has_artifact = self.decision is not None
            if has_artifact != (self.request_more_analysis is not None):
                raise ValueError("Professor PLAN decision fields must be present together")
            if not has_artifact and self.stage_status != "FAILED":
                raise ValueError(
                    "reached Professor PLAN without artifact requires FAILED status"
                )
        elif any(
            (
                self.decision is not None,
                bool(self.selected_agents),
                bool(self.rationale),
                self.request_more_analysis is not None,
                self.call is not None,
            )
        ):
            raise ValueError("not-reached Professor PLAN cannot carry plan fields")
        return self


class SpecialistAnalysisBase(FrozenModel):
    agent: str = Field(min_length=1)
    stance: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence: tuple[EvidenceProjection, ...]
    risks: tuple[str, ...]
    invalidation: tuple[str, ...]
    data_gaps: tuple[str, ...]


class BerlinAnalysisProjection(SpecialistAnalysisBase):
    agent: Literal["berlin"]
    regime: str = Field(min_length=1)
    trend_maturity: str = Field(min_length=1)
    multi_timeframe_alignment: str = Field(min_length=1)


class TokyoAnalysisProjection(SpecialistAnalysisBase):
    agent: Literal["tokyo"]
    momentum: str = Field(min_length=1)
    momentum_quality: str = Field(min_length=1)
    breakout_quality: str = Field(min_length=1)


class NairobiAnalysisProjection(SpecialistAnalysisBase):
    agent: Literal["nairobi"]
    market_structure: str = Field(min_length=1)
    liquidity_state: str = Field(min_length=1)
    breakout_state: str = Field(min_length=1)


class RioAnalysisProjection(SpecialistAnalysisBase):
    agent: Literal["rio"]
    positioning_regime: str = Field(min_length=1)
    funding_state: str = Field(min_length=1)
    open_interest_state: str = Field(min_length=1)
    liquidation_state: str = Field(min_length=1)
    squeeze_risk: str = Field(min_length=1)
    data_quality: str = Field(min_length=1)


class DenverAnalysisProjection(SpecialistAnalysisBase):
    agent: Literal["denver"]
    source_stats_id: str = Field(min_length=1)
    historical_edge: str = Field(min_length=1)
    sample_size_band: str = Field(min_length=1)
    robustness: str = Field(min_length=1)
    oos_consistency: str = Field(min_length=1)


SpecialistAnalysisProjection = Annotated[
    BerlinAnalysisProjection
    | TokyoAnalysisProjection
    | NairobiAnalysisProjection
    | RioAnalysisProjection
    | DenverAnalysisProjection,
    Field(discriminator="agent"),
]


class SpecialistRunProjection(FrozenModel):
    agent_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    route_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    analysis: SpecialistAnalysisProjection
    call: AgentCallProjection | None = None

    @model_validator(mode="after")
    def validate_agent_identity(self) -> SpecialistRunProjection:
        if self.analysis.agent != self.agent_id:
            raise ValueError("specialist projection agent mismatch")
        if self.call is not None and self.call.request_id != self.request_id:
            raise ValueError("specialist call request_id mismatch")
        return self


class SpecialistsProjection(FrozenModel):
    reached: bool
    stage_status: str | None = None
    selected_agents: tuple[str, ...] = ()
    runs: tuple[SpecialistRunProjection, ...] = ()
    failure: FailureProjection | None = None

    @model_validator(mode="after")
    def validate_selected_runs(self) -> SpecialistsProjection:
        if not self.reached:
            if any((self.selected_agents, self.runs, self.failure)):
                raise ValueError("not-reached specialists cannot carry specialist artifacts")
            return self
        if len(set(self.selected_agents)) != len(self.selected_agents):
            raise ValueError("selected_agents cannot contain duplicates")
        run_ids = tuple(run.agent_id for run in self.runs)
        if len(set(run_ids)) != len(run_ids):
            raise ValueError("specialist runs cannot contain duplicate agents")
        selected_positions = {
            agent_id: index for index, agent_id in enumerate(self.selected_agents)
        }
        if any(agent_id not in selected_positions for agent_id in run_ids):
            raise ValueError("specialist run was not selected by Professor PLAN")
        if tuple(sorted(run_ids, key=selected_positions.__getitem__)) != run_ids:
            raise ValueError("specialist runs must preserve Professor orchestration order")
        return self


class PalermoProjection(FrozenModel):
    reached: bool
    stage_status: str | None = None
    request_id: str | None = None
    prompt_version: str | None = None
    route_id: str | None = None
    model_id: str | None = None
    verdict: str | None = None
    severity: float | None = Field(default=None, ge=0, le=1)
    critical_objections: tuple[str, ...] = ()
    missing_checks: tuple[str, ...] = ()
    conditions_to_continue: tuple[str, ...] = ()
    call: AgentCallProjection | None = None

    @model_validator(mode="after")
    def validate_reachability(self) -> PalermoProjection:
        required = (
            self.request_id,
            self.prompt_version,
            self.route_id,
            self.model_id,
            self.verdict,
            self.severity,
        )
        has_artifact = self.request_id is not None
        if self.reached:
            if has_artifact and any(value is None for value in required):
                raise ValueError("Palermo run fields must be present together")
            if not has_artifact and self.stage_status != "FAILED":
                raise ValueError("reached Palermo without artifact requires FAILED status")
        elif any(
            (
                any(value is not None for value in required),
                self.critical_objections,
                self.missing_checks,
                self.conditions_to_continue,
                self.call is not None,
            )
        ):
            raise ValueError("not-reached Palermo stage cannot carry review fields")
        return self


class ProfessorTradeProjection(FrozenModel):
    entry_price: Decimal = Field(gt=0)
    stop_price: Decimal = Field(gt=0)
    targets: tuple[Decimal, ...] = Field(min_length=1)
    expected_rr: Decimal = Field(gt=0)


class ProfessorFinalProjection(FrozenModel):
    reached: bool
    stage_status: str | None = None
    direction: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    thesis: tuple[str, ...] = ()
    counter_evidence: tuple[str, ...] = ()
    invalidation: tuple[str, ...] = ()
    evidence: tuple[EvidenceProjection, ...] = ()
    trade: ProfessorTradeProjection | None = None
    call: AgentCallProjection | None = None

    @model_validator(mode="after")
    def validate_reachability(self) -> ProfessorFinalProjection:
        has_artifact = self.direction is not None
        if self.reached:
            if has_artifact != (self.confidence is not None):
                raise ValueError("Professor FINAL decision fields must be present together")
            if not has_artifact:
                if self.stage_status != "FAILED":
                    raise ValueError(
                        "reached Professor FINAL without artifact requires FAILED status"
                    )
            elif self.direction == "NO_TRADE" and self.trade is not None:
                raise ValueError("NO_TRADE FINAL cannot contain trade parameters")
            elif self.direction != "NO_TRADE" and self.trade is None:
                raise ValueError("trading FINAL requires trade parameters")
        elif any(
            (
                self.direction is not None,
                self.confidence is not None,
                self.thesis,
                self.counter_evidence,
                self.invalidation,
                self.evidence,
                self.trade is not None,
                self.call is not None,
            )
        ):
            raise ValueError("not-reached Professor FINAL cannot carry decision fields")
        return self


class TradeProposalProjection(FrozenModel):
    reached: bool
    stage_status: str | None = None
    proposal_id: str | None = None
    side: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    entry_price: Decimal | None = None
    stop_price: Decimal | None = None
    targets: tuple[Decimal, ...] = ()
    expected_rr: Decimal | None = None
    market_regime: str | None = None
    feature_version: str | None = None
    professor_prompt_version: str | None = None
    professor_request_id: str | None = None
    specialist_request_ids: tuple[str, ...] = ()
    palermo_request_id: str | None = None
    thesis: tuple[str, ...] = ()
    counter_evidence: tuple[str, ...] = ()
    invalidation: tuple[str, ...] = ()
    evidence: tuple[EvidenceProjection, ...] = ()
    created_at: datetime | None = None
    expires_at: datetime | None = None

    @field_validator("created_at", "expires_at")
    @classmethod
    def normalize_datetimes(cls, value: datetime | None, info) -> datetime | None:
        if value is None:
            return None
        return _as_utc(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_reachability(self) -> TradeProposalProjection:
        required = (
            self.proposal_id,
            self.side,
            self.confidence,
            self.entry_price,
            self.stop_price,
            self.expected_rr,
            self.market_regime,
            self.feature_version,
            self.professor_prompt_version,
            self.professor_request_id,
            self.palermo_request_id,
            self.created_at,
            self.expires_at,
        )
        if self.reached:
            if any(value is None for value in required) or not self.targets:
                raise ValueError("reached TradeProposal requires canonical proposal fields")
        elif any(
            (
                any(value is not None for value in required),
                self.targets,
                self.specialist_request_ids,
                self.thesis,
                self.counter_evidence,
                self.invalidation,
                self.evidence,
            )
        ):
            raise ValueError("not-reached TradeProposal cannot carry proposal fields")
        return self


class RiskInputProjection(FrozenModel):
    proposal_id: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: str = Field(min_length=1)
    entry_price: Decimal = Field(gt=0)
    stop_price: Decimal | None = None
    expected_rr: Decimal | None = None
    expires_at: datetime
    requested_leverage: Decimal = Field(gt=0)

    @field_validator("expires_at")
    @classmethod
    def normalize_expires_at(cls, value: datetime) -> datetime:
        return _as_utc(value, field_name="expires_at")


class RiskDetail(FrozenModel):
    key: str = Field(min_length=1)
    value: str


class RiskProjection(FrozenModel):
    reached: bool
    stage_status: str | None = None
    risk_input: RiskInputProjection | None = None
    risk_decision_id: str | None = None
    status: str | None = None
    reason_codes: tuple[str, ...] = ()
    approved_quantity: Decimal | None = None
    approved_risk_amount: Decimal | None = None
    approved_notional: Decimal | None = None
    created_at: datetime | None = None
    details: tuple[RiskDetail, ...] = ()

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _as_utc(value, field_name="created_at")

    @model_validator(mode="after")
    def validate_reachability(self) -> RiskProjection:
        required = (
            self.risk_input,
            self.risk_decision_id,
            self.status,
            self.approved_quantity,
            self.approved_risk_amount,
            self.approved_notional,
            self.created_at,
        )
        if self.reached and any(value is None for value in required):
            raise ValueError("reached Risk stage requires canonical decision fields")
        if not self.reached and any(
            (
                any(value is not None for value in required),
                self.reason_codes,
                self.details,
            )
        ):
            raise ValueError("not-reached Risk stage cannot carry decision fields")
        return self


class OrderIntentProjection(FrozenModel):
    risk_decision_id: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    client_order_id: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    order_type: str = Field(min_length=1)


class BrokerOrderProjection(FrozenModel):
    broker_order_id: str = Field(min_length=1)
    client_order_id: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: str = Field(min_length=1)
    order_type: str = Field(min_length=1)
    requested_quantity: Decimal = Field(gt=0)
    filled_quantity: Decimal = Field(ge=0)
    status: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    limit_price: Decimal | None = None
    average_fill_price: Decimal | None = None
    reject_reason: str | None = None
    trigger: str | None = None

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_datetimes(cls, value: datetime, info) -> datetime:
        return _as_utc(value, field_name=info.field_name)


class FillProjection(FrozenModel):
    fill_id: str = Field(min_length=1)
    broker_order_id: str = Field(min_length=1)
    price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    fee: Decimal = Field(ge=0)
    fee_rate_bps: Decimal = Field(ge=0)
    liquidity: str = Field(min_length=1)
    filled_at: datetime

    @field_validator("filled_at")
    @classmethod
    def normalize_filled_at(cls, value: datetime) -> datetime:
        return _as_utc(value, field_name="filled_at")


class PositionProjection(FrozenModel):
    system_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: str | None = None
    signed_quantity: Decimal
    quantity: Decimal = Field(ge=0)
    average_entry: Decimal = Field(ge=0)


class ExecutionProjection(FrozenModel):
    reached: bool
    stage_status: str | None = None
    order_intent: OrderIntentProjection | None = None
    order: BrokerOrderProjection | None = None
    fill: FillProjection | None = None
    position_before: PositionProjection | None = None
    position_after: PositionProjection | None = None
    failure: FailureProjection | None = None

    @model_validator(mode="after")
    def validate_chain(self) -> ExecutionProjection:
        if not self.reached:
            if any(
                (
                    self.order_intent is not None,
                    self.order is not None,
                    self.fill is not None,
                    self.position_before is not None,
                    self.position_after is not None,
                    self.failure is not None,
                )
            ):
                raise ValueError("not-reached execution cannot carry execution artifacts")
            return self
        if self.order_intent is None:
            raise ValueError("reached execution requires order_intent")
        if (
            self.order is not None
            and self.order.client_order_id != self.order_intent.client_order_id
        ):
            raise ValueError("BrokerOrder client_order_id does not match OrderIntent")
        if self.fill is not None:
            if self.order is None:
                raise ValueError("Fill requires BrokerOrder")
            if self.fill.broker_order_id != self.order.broker_order_id:
                raise ValueError("Fill broker_order_id does not match BrokerOrder")
        return self


class DecisionProjection(FrozenModel):
    pipeline_result_present: bool
    paper_pipeline_status: str | None = None
    orchestration_status: str | None = None
    orchestration_failure: FailureProjection | None = None
    paper_pipeline_failure: FailureProjection | None = None
    orchestration_stages: tuple[StageTrace, ...] = ()
    paper_pipeline_stages: tuple[StageTrace, ...] = ()
    compute_gate: ComputeGateProjection
    professor_plan: ProfessorPlanProjection
    specialists: SpecialistsProjection
    palermo: PalermoProjection
    professor_final: ProfessorFinalProjection
    trade_proposal: TradeProposalProjection
    risk: RiskProjection
    execution: ExecutionProjection

    @model_validator(mode="after")
    def validate_pipeline_presence(self) -> DecisionProjection:
        has_pipeline_material = any(
            (
                self.paper_pipeline_status is not None,
                self.orchestration_status is not None,
                self.orchestration_failure is not None,
                self.paper_pipeline_failure is not None,
                self.orchestration_stages,
                self.paper_pipeline_stages,
                self.compute_gate.reached,
                self.professor_plan.reached,
                self.specialists.reached,
                self.palermo.reached,
                self.professor_final.reached,
                self.trade_proposal.reached,
                self.risk.reached,
                self.execution.reached,
            )
        )
        if not self.pipeline_result_present and has_pipeline_material:
            raise ValueError("missing pipeline result cannot carry decision stages")
        return self


class AnalyticsRefProjection(FrozenModel):
    link_id: str = Field(min_length=1)
    link_fingerprint: str = Field(min_length=64, max_length=64)
    link_policy_version: str = Field(min_length=1)
    status: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    analytics_snapshot_id: str | None = None
    analytics_snapshot_fingerprint: str | None = None
    analytics_as_of: datetime | None = None
    source_cursor_fingerprint: str | None = None
    analytics_snapshot_source_cursor_fingerprint: str | None = None
    diagnostics: tuple[str, ...] = ()

    @field_validator(
        "link_fingerprint",
        "analytics_snapshot_fingerprint",
        "source_cursor_fingerprint",
        "analytics_snapshot_source_cursor_fingerprint",
    )
    @classmethod
    def normalize_fingerprints(cls, value: str | None, info) -> str | None:
        return _normalize_sha256(value, field_name=info.field_name)

    @field_validator("analytics_as_of")
    @classmethod
    def normalize_as_of(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _as_utc(value, field_name="analytics_as_of")

    @model_validator(mode="after")
    def validate_snapshot_pair(self) -> AnalyticsRefProjection:
        snapshot_values = (
            self.analytics_snapshot_id,
            self.analytics_snapshot_fingerprint,
            self.analytics_as_of,
            self.analytics_snapshot_source_cursor_fingerprint,
        )
        if any(value is None for value in snapshot_values) and any(
            value is not None for value in snapshot_values
        ):
            raise ValueError("Analytics snapshot reference must be complete or absent")
        return self


class DecisionIntelligenceRecord(FrozenModel):
    schema_version: str = DECISION_INTELLIGENCE_RECORD_SCHEMA_VERSION
    policy_version: str = DECISION_INTELLIGENCE_RECORD_POLICY_VERSION
    record_id: str = Field(min_length=1)
    record_fingerprint: str = Field(min_length=64, max_length=64)
    source_backtest_run_id: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    opportunity_id: str = Field(min_length=1)
    opportunity_fingerprint: str = Field(min_length=64, max_length=64)
    system_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    decision_timeframe: str = Field(min_length=1)
    observed_at: datetime
    scanner: ScannerProjection
    decision_context: DecisionContextRef
    decision: DecisionProjection
    analytics: AnalyticsRefProjection

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _as_utc(value, field_name="observed_at")

    @field_validator("record_fingerprint", "opportunity_fingerprint")
    @classmethod
    def normalize_sha_fields(cls, value: str, info) -> str:
        normalized = _normalize_sha256(value, field_name=info.field_name)
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_contract(self) -> DecisionIntelligenceRecord:
        if self.schema_version != DECISION_INTELLIGENCE_RECORD_SCHEMA_VERSION:
            raise ValueError("unsupported Decision Intelligence record schema")
        if self.policy_version != DECISION_INTELLIGENCE_RECORD_POLICY_VERSION:
            raise ValueError("unsupported Decision Intelligence record policy")
        if self.analytics.analytics_run_id != self.analytics_run_id:
            raise ValueError("record analytics_run_id mismatch")
        if self.scanner.observed_at != self.observed_at:
            raise ValueError("Scanner observed_at must equal record observed_at")
        if self.decision_context.present and self.decision_context.as_of != self.observed_at:
            raise ValueError("DecisionContext as_of must equal record observed_at")
        if (
            self.analytics.analytics_as_of is not None
            and self.analytics.analytics_as_of != self.observed_at
        ):
            raise ValueError("matched Analytics as_of must equal record observed_at")
        return self

    @classmethod
    def create(
        cls,
        *,
        source_backtest_run_id: str,
        analytics_run_id: str,
        opportunity_id: str,
        opportunity_fingerprint: str,
        system_id: str,
        symbol: str,
        decision_timeframe: str,
        observed_at: datetime,
        scanner: ScannerProjection,
        decision_context: DecisionContextRef,
        decision: DecisionProjection,
        analytics: AnalyticsRefProjection,
    ) -> DecisionIntelligenceRecord:
        identity_payload = {
            "schema": DECISION_INTELLIGENCE_RECORD_SCHEMA_VERSION,
            "policy_version": DECISION_INTELLIGENCE_RECORD_POLICY_VERSION,
            "source_backtest_run_id": source_backtest_run_id,
            "analytics_run_id": analytics_run_id,
            "opportunity_id": opportunity_id,
            "opportunity_analytics_link_id": analytics.link_id,
        }
        fingerprint_payload = {
            **identity_payload,
            "opportunity_fingerprint": opportunity_fingerprint,
            "system_id": system_id,
            "symbol": symbol,
            "decision_timeframe": decision_timeframe,
            "observed_at": observed_at,
            "scanner": scanner.model_dump(mode="python"),
            "decision_context": decision_context.model_dump(mode="python"),
            "decision": decision.model_dump(mode="python"),
            "analytics": analytics.model_dump(mode="python"),
        }
        return cls(
            record_id=stable_uuid("decision-intelligence-record", identity_payload),
            record_fingerprint=stable_digest(fingerprint_payload),
            source_backtest_run_id=source_backtest_run_id,
            analytics_run_id=analytics_run_id,
            opportunity_id=opportunity_id,
            opportunity_fingerprint=opportunity_fingerprint,
            system_id=system_id,
            symbol=symbol,
            decision_timeframe=decision_timeframe,
            observed_at=observed_at,
            scanner=scanner,
            decision_context=decision_context,
            decision=decision,
            analytics=analytics,
        )


class DecisionIntelligenceRecordSet(FrozenModel):
    schema_version: str = DECISION_INTELLIGENCE_RECORD_SET_SCHEMA_VERSION
    policy_version: str = DECISION_INTELLIGENCE_RECORD_POLICY_VERSION
    source_backtest_run_id: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    record_count: int = Field(ge=0)
    matched_analytics_count: int = Field(ge=0)
    unmatched_analytics_count: int = Field(ge=0)
    records: tuple[DecisionIntelligenceRecord, ...]
    set_fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("set_fingerprint")
    @classmethod
    def normalize_set_fingerprint(cls, value: str) -> str:
        normalized = _normalize_sha256(value, field_name="set_fingerprint")
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_counts_and_order(self) -> DecisionIntelligenceRecordSet:
        if self.schema_version != DECISION_INTELLIGENCE_RECORD_SET_SCHEMA_VERSION:
            raise ValueError("unsupported Decision Intelligence record-set schema")
        if self.policy_version != DECISION_INTELLIGENCE_RECORD_POLICY_VERSION:
            raise ValueError("unsupported Decision Intelligence record-set policy")
        if self.record_count != len(self.records):
            raise ValueError("record_count must equal records length")
        if self.matched_analytics_count + self.unmatched_analytics_count != self.record_count:
            raise ValueError("Analytics counts must conserve record_count")
        opportunity_ids = tuple(item.opportunity_id for item in self.records)
        record_ids = tuple(item.record_id for item in self.records)
        if len(set(opportunity_ids)) != len(opportunity_ids):
            raise ValueError("record set cannot contain duplicate opportunity_id")
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("record set cannot contain duplicate record_id")
        for item in self.records:
            if item.source_backtest_run_id != self.source_backtest_run_id:
                raise ValueError("record source_backtest_run_id does not match record set")
            if item.analytics_run_id != self.analytics_run_id:
                raise ValueError("record analytics_run_id does not match record set")
        ordered = tuple(
            sorted(
                self.records,
                key=lambda item: (item.observed_at, item.opportunity_id, item.record_id),
            )
        )
        if ordered != self.records:
            raise ValueError("records must be sorted deterministically")
        return self

    @classmethod
    def create(
        cls,
        *,
        source_backtest_run_id: str,
        analytics_run_id: str,
        records: tuple[DecisionIntelligenceRecord, ...],
    ) -> DecisionIntelligenceRecordSet:
        ordered = tuple(
            sorted(
                records,
                key=lambda item: (item.observed_at, item.opportunity_id, item.record_id),
            )
        )
        matched = sum(1 for item in ordered if item.analytics.status == "MATCHED")
        payload = {
            "schema": DECISION_INTELLIGENCE_RECORD_SET_SCHEMA_VERSION,
            "policy_version": DECISION_INTELLIGENCE_RECORD_POLICY_VERSION,
            "source_backtest_run_id": source_backtest_run_id,
            "analytics_run_id": analytics_run_id,
            "records": tuple(item.record_fingerprint for item in ordered),
        }
        return cls(
            source_backtest_run_id=source_backtest_run_id,
            analytics_run_id=analytics_run_id,
            record_count=len(ordered),
            matched_analytics_count=matched,
            unmatched_analytics_count=len(ordered) - matched,
            records=ordered,
            set_fingerprint=stable_digest(payload),
        )


__all__ = [
    "AgentCallProjection",
    "AnalyticsRefProjection",
    "BerlinAnalysisProjection",
    "BrokerOrderProjection",
    "ComputeGateProjection",
    "DECISION_INTELLIGENCE_RECORD_POLICY_VERSION",
    "DECISION_INTELLIGENCE_RECORD_SCHEMA_VERSION",
    "DECISION_INTELLIGENCE_RECORD_SET_SCHEMA_VERSION",
    "DecisionContextRef",
    "DecisionIntelligenceRecord",
    "DecisionIntelligenceRecordSet",
    "DecisionProjection",
    "DenverAnalysisProjection",
    "EvidenceProjection",
    "ExecutionProjection",
    "FailureProjection",
    "FillProjection",
    "NairobiAnalysisProjection",
    "OrderIntentProjection",
    "PalermoProjection",
    "PositionProjection",
    "ProfessorFinalProjection",
    "ProfessorPlanProjection",
    "ProfessorTradeProjection",
    "RioAnalysisProjection",
    "RiskDetail",
    "RiskInputProjection",
    "RiskProjection",
    "ScannerProjection",
    "SpecialistAnalysisProjection",
    "SpecialistRunProjection",
    "SpecialistsProjection",
    "StageTrace",
    "TokyoAnalysisProjection",
    "TradeProposalProjection",
]
