from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
