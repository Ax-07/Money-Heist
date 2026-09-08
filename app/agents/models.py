from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AgentState(StrEnum):
    ACTIVE = "ACTIVE"
    ON_DEMAND = "ON_DEMAND"
    SHADOW = "SHADOW"
    PROBATION = "PROBATION"
    DISABLED = "DISABLED"


class AgentRole(StrEnum):
    ORCHESTRATION = "orchestration"
    RED_TEAM = "red_team"
    AI_ECONOMICS = "ai_economics"
    TREND_REGIME = "trend_regime"
    MOMENTUM = "momentum"
    MARKET_STRUCTURE = "market_structure"
    DERIVATIVES_POSITIONING = "derivatives_positioning"
    HISTORICAL_STATISTICS = "historical_statistics"


class Stance(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
    NO_TRADE = "NO_TRADE"


class SpecialistStance(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class AgentRegistryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_id: str = Field(min_length=1, max_length=100)
    role: AgentRole
    state: AgentState
    prompt_version: str = Field(min_length=1, max_length=100)
    model_route: str = Field(min_length=1, max_length=100)
    allowed_tools: tuple[str, ...] = ()
    budget_policy_id: str = "default"
    core: bool = True

    @model_validator(mode="after")
    def secure_tools(self) -> AgentRegistryEntry:
        forbidden_fragments = (
            "broker",
            "exchange",
            "secret",
            "risk_engine",
            "shell",
            "filesystem",
            "withdraw",
            "live_order",
        )
        for tool in self.allowed_tools:
            normalized = tool.lower()
            if any(fragment in normalized for fragment in forbidden_fragments):
                raise ValueError(f"unsafe agent tool: {tool}")
        return self


class ProfessorPlan(BaseModel):
    decision: Literal["NO_ANALYSIS", "MINI_CREW", "FULL_CREW"]
    selected_agents: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    request_more_analysis: bool = False


class ProfessorDecision(BaseModel):
    direction: Stance
    confidence: float = Field(ge=0, le=1)
    thesis: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    invalidation: list[str] = Field(default_factory=list)
    request_more_analysis: bool = False


class PalermoReview(BaseModel):
    verdict: Literal["CLEAR", "CAUTION", "REJECT"]
    severity: float = Field(ge=0, le=1)
    critical_objections: list[str] = Field(default_factory=list)
    missing_checks: list[str] = Field(default_factory=list)
    conditions_to_continue: list[str] = Field(default_factory=list)


class LisbonRecommendation(BaseModel):
    agent_id: str
    recommended_state: AgentState
    reasons: list[str] = Field(default_factory=list)


class LisbonReport(BaseModel):
    total_ai_cost_eur: float = Field(ge=0)
    cost_per_decision_eur: float = Field(ge=0)
    self_funding_ratio: float | None = Field(default=None, ge=0)
    additional_analysis_justified: bool
    recommendations: list[LisbonRecommendation] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)


class EvidenceReference(BaseModel):
    """Evidence tied to an exact field present in the specialist input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_key: str = Field(min_length=1, max_length=300)
    observation: str = Field(min_length=1, max_length=1000)


class SpecialistAnalysis(BaseModel):
    """Strict common contract for independent first-round specialists."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stance: SpecialistStance
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceReference]
    risks: list[str]
    invalidation: list[str]
    data_gaps: list[str]


class BerlinAnalysis(SpecialistAnalysis):
    agent: Literal["berlin"]
    regime: Literal[
        "BULLISH_TREND",
        "BEARISH_TREND",
        "RANGE",
        "TRANSITION",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
        "UNKNOWN",
    ]
    trend_maturity: Literal["EARLY", "MATURE", "EXHAUSTED", "UNCLEAR"]
    multi_timeframe_alignment: Literal["BULLISH", "BEARISH", "MIXED", "UNKNOWN"]


class TokyoAnalysis(SpecialistAnalysis):
    agent: Literal["tokyo"]
    momentum: Literal["BULLISH", "BEARISH", "NEUTRAL", "MIXED", "UNKNOWN"]
    momentum_quality: Literal["STRONG", "MODERATE", "WEAK", "UNKNOWN"]
    breakout_quality: Literal[
        "CONFIRMED",
        "UNCONFIRMED",
        "FAILED",
        "NOT_APPLICABLE",
        "UNKNOWN",
    ]


class NairobiAnalysis(SpecialistAnalysis):
    agent: Literal["nairobi"]
    market_structure: Literal["HH_HL", "LH_LL", "RANGE", "TRANSITION", "UNKNOWN"]
    liquidity_state: Literal["CLEAN", "AT_RISK", "SWEEP_SUSPECTED", "UNKNOWN"]
    breakout_state: Literal["BREAKOUT", "RETEST", "FALSE_BREAKOUT", "NONE", "UNKNOWN"]


class RioContext(BaseModel):
    """Read-only derivatives context supplied to Rio by trusted market-data code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    source: str = Field(min_length=1, max_length=100)
    instrument: str = Field(min_length=1, max_length=100)
    observed_at: datetime
    is_stale: bool = False
    data_quality: Literal["RELIABLE", "DEGRADED", "INSUFFICIENT"]
    funding_rate: float | None = Field(default=None, allow_inf_nan=False)
    open_interest: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    open_interest_change_pct: float | None = Field(default=None, allow_inf_nan=False)
    long_liquidations_notional: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    short_liquidations_notional: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    long_short_ratio: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    missing_fields: tuple[str, ...] = ()

    @field_validator("observed_at")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value.astimezone(UTC)

    @property
    def usable(self) -> bool:
        metrics = (
            self.funding_rate,
            self.open_interest,
            self.open_interest_change_pct,
            self.long_liquidations_notional,
            self.short_liquidations_notional,
            self.long_short_ratio,
        )
        return (
            not self.is_stale
            and self.data_quality in {"RELIABLE", "DEGRADED"}
            and any(value is not None for value in metrics)
        )

    @model_validator(mode="after")
    def coherent_quality(self) -> RioContext:
        if self.data_quality == "RELIABLE" and self.is_stale:
            raise ValueError("RELIABLE RioContext cannot be stale")
        return self


class DenverContext(BaseModel):
    """Deterministic historical statistics supplied to Denver; the LLM never computes them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    stats_id: str = Field(min_length=1, max_length=200)
    setup_definition_version: str = Field(min_length=1, max_length=100)
    as_of: datetime
    source_run_ids: tuple[str, ...] = Field(min_length=1)
    source_dataset_ids: tuple[str, ...] = Field(min_length=1)
    sample_count: int = Field(ge=0)
    oos_sample_count: int = Field(default=0, ge=0)
    win_rate: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    expectancy: float | None = Field(default=None, allow_inf_nan=False)
    profit_factor: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_drawdown_pct: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    regime: str | None = Field(default=None, max_length=100)
    notes: tuple[str, ...] = ()

    @field_validator("as_of")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def coherent_samples(self) -> DenverContext:
        if self.oos_sample_count > self.sample_count:
            raise ValueError("oos_sample_count cannot exceed sample_count")
        return self

    @property
    def sample_size_band(self) -> Literal["NONE", "SMALL", "MEDIUM", "LARGE"]:
        if self.sample_count == 0:
            return "NONE"
        if self.sample_count < 30:
            return "SMALL"
        if self.sample_count < 100:
            return "MEDIUM"
        return "LARGE"

    @property
    def usable(self) -> bool:
        metrics = (self.win_rate, self.expectancy, self.profit_factor, self.max_drawdown_pct)
        return self.sample_count > 0 and any(value is not None for value in metrics)


class RioAnalysis(SpecialistAnalysis):
    agent: Literal["rio"]
    positioning_regime: Literal[
        "LONG_CROWDED",
        "SHORT_CROWDED",
        "BALANCED",
        "MIXED",
        "UNKNOWN",
    ]
    funding_state: Literal[
        "POSITIVE",
        "NEGATIVE",
        "NEUTRAL",
        "EXTREME_POSITIVE",
        "EXTREME_NEGATIVE",
        "UNKNOWN",
    ]
    open_interest_state: Literal["RISING", "FALLING", "STABLE", "UNKNOWN"]
    liquidation_state: Literal[
        "LONG_DOMINATED",
        "SHORT_DOMINATED",
        "BALANCED",
        "QUIET",
        "UNKNOWN",
    ]
    squeeze_risk: Literal[
        "LONG_SQUEEZE",
        "SHORT_SQUEEZE",
        "TWO_SIDED",
        "LOW",
        "UNKNOWN",
    ]
    data_quality: Literal["RELIABLE", "DEGRADED", "INSUFFICIENT"]


class DenverAnalysis(SpecialistAnalysis):
    agent: Literal["denver"]
    source_stats_id: str = Field(min_length=1, max_length=200)
    historical_edge: Literal["POSITIVE", "NEGATIVE", "MIXED", "INCONCLUSIVE", "UNKNOWN"]
    sample_size_band: Literal["NONE", "SMALL", "MEDIUM", "LARGE"]
    robustness: Literal["ROBUST", "MIXED", "FRAGILE", "UNKNOWN"]
    oos_consistency: Literal["CONSISTENT", "DIVERGENT", "UNAVAILABLE", "UNKNOWN"]
