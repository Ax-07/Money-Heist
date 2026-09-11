from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.registry import CORE_AGENT_REGISTRY, SPECIALIST_AGENT_REGISTRY
from app.intelligence.ai_gateway.budget import AIBudgetLedger
from app.intelligence.ai_gateway.gateway import AIGateway
from app.intelligence.ai_gateway.models import ProviderRequest, ProviderResponse, TokenUsage
from app.intelligence.ai_gateway.openai_client import OpenAIResponsesClient
from app.intelligence.ai_gateway.routing import ModelPricing, ModelRoute, ModelRouter
from app.intelligence.ai_gateway.usage import InMemoryAIUsageRecorder
from app.market.historical import HistoricalImportError, import_candles_csv
from app.services.backtest import (
    BacktestAIClient,
    BacktestAIMode,
    BacktestConfig,
    BacktestPeriodReport,
    BacktestPeriodRole,
    BacktestPortfolioStateProvider,
    BacktestResponseCache,
    BacktestRun,
    BacktestRunSet,
    BacktestSplitPlan,
    BacktestSplitReport,
    DatasetRef,
    HistoricalPositionLifecycle,
    HistoricalSetupAttributionError,
    HistoricalReplayRunner,
    ReplayClock,
    ReplayIdFactory,
    WalkForwardReport,
    build_run_manifest,
    build_walk_forward_plan,
    catalog_from_historical_runs,
    closed_trades_to_csv,
    equity_curve_to_csv,
    evaluate_historical_replay,
    execute_walk_forward,
    manifest_to_json,
    split_report_to_json,
    walk_forward_report_to_json,
)
from app.services.backtest.advanced_mock import DeterministicAdvancedSpecialistMockProvider
from app.services.backtest.runner import HistoricalReplayCancelledError
from app.services.backtest.historical_derivatives_analytics import (
    HistoricalDerivativesAnalyticsArchive,
)
from app.services.backtest.derivatives_runtime import (
    historical_derivatives_execution_assumptions,
    historical_derivatives_runner_kwargs,
)
from app.services.backtest.mtf_runtime import (
    mtf_execution_assumptions,
    mtf_runner_kwargs,
    supports_full_mtf_source,
)
from app.services.orchestration import OrchestrationPipeline
from app.services.paper_pipeline.journal import InMemoryPaperPipelineJournal
from app.services.paper_pipeline.pipeline import PaperTradingPipeline
from app.services.paper_pipeline.providers import (
    InMemoryKillSwitchStateProvider,
    InMemoryMarketConstraintsProvider,
    InMemoryRiskProfileProvider,
)
from app.trading.paper import PaperBroker, PaperBrokerConfig
from app.trading.risk import KillSwitchState, MarketConstraints, RiskEngine, RiskProfile

MAX_CSV_BYTES = 25_000_000

_TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetInput(FrozenModel):
    csv_text: str = Field(min_length=1)
    symbol: str = Field(min_length=1, default="BTC/EUR")
    timeframe: str = Field(min_length=1, default="5m")
    source: str = Field(min_length=1, default="dashboard_csv")
    candle_interval_seconds: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def normalize(self) -> DatasetInput:
        if len(self.csv_text.encode("utf-8")) > MAX_CSV_BYTES:
            raise ValueError("csv_text exceeds the 25 MB dashboard limit")
        for field_name in ("symbol", "timeframe", "source"):
            value = str(getattr(self, field_name)).strip()
            if not value:
                raise ValueError(f"{field_name} must not be blank")
            object.__setattr__(self, field_name, value)
        return self


class HistoricalDerivativesInput(FrozenModel):
    csv_text: str = Field(min_length=1)
    max_age_seconds: int = Field(default=7200, ge=1)

    @model_validator(mode="after")
    def validate_archive_input(self) -> HistoricalDerivativesInput:
        if len(self.csv_text.encode("utf-8")) > MAX_CSV_BYTES:
            raise ValueError(
                "historical derivatives csv_text exceeds the 25 MB dashboard limit"
            )
        if not self.csv_text.strip():
            raise ValueError("historical derivatives csv_text must not be blank")
        return self


class RiskInput(FrozenModel):
    risk_profile_id: str = "dashboard_balanced_dev"
    risk_version: str = "dashboard-balanced-dev-v1"
    max_risk_per_trade_pct: Decimal = Decimal("0.01")
    max_daily_loss_pct: Decimal = Decimal("0.03")
    max_drawdown_pct: Decimal = Decimal("0.10")
    max_portfolio_risk_pct: Decimal = Decimal("0.03")
    max_positions: int = Field(default=3, ge=1)
    max_leverage: Decimal = Decimal("1")
    max_correlated_exposure_pct: Decimal = Decimal("0.02")
    min_expected_rr: Decimal | None = Decimal("1.5")

    @model_validator(mode="after")
    def validate_limits(self) -> RiskInput:
        if not self.risk_profile_id.strip() or not self.risk_version.strip():
            raise ValueError("risk_profile_id and risk_version must not be blank")
        positive_or_zero = (
            "max_risk_per_trade_pct",
            "max_daily_loss_pct",
            "max_drawdown_pct",
            "max_portfolio_risk_pct",
            "max_correlated_exposure_pct",
        )
        for field_name in positive_or_zero:
            value = getattr(self, field_name)
            if not value.is_finite() or value < 0:
                raise ValueError(f"{field_name} must be finite and >= 0")
        if not self.max_leverage.is_finite() or self.max_leverage <= 0:
            raise ValueError("max_leverage must be finite and > 0")
        if self.min_expected_rr is not None and self.min_expected_rr <= 0:
            raise ValueError("min_expected_rr must be > 0 when configured")
        return self


class MarketConstraintsInput(FrozenModel):
    qty_step: Decimal = Field(gt=0)
    min_qty: Decimal = Field(gt=0)
    min_notional: Decimal = Field(gt=0)
    max_qty: Decimal | None = Field(default=None, gt=0)
    max_leverage: Decimal | None = Field(default=Decimal("1"), gt=0)


class AIInput(FrozenModel):
    mode: BacktestAIMode = BacktestAIMode.MOCK
    hard_budget_eur: Decimal = Decimal("1")
    model_id: str = "mock-backtest-v1"
    reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"
    input_per_million_eur: Decimal = Decimal("0")
    output_per_million_eur: Decimal = Decimal("0")
    cached_input_per_million_eur: Decimal | None = None
    mock_agent_coverage: bool = False

    @model_validator(mode="after")
    def validate_ai(self) -> AIInput:
        if not self.model_id.strip():
            raise ValueError("model_id must not be blank")
        if not self.hard_budget_eur.is_finite() or self.hard_budget_eur < 0:
            raise ValueError("hard_budget_eur must be finite and >= 0")
        for field_name in ("input_per_million_eur", "output_per_million_eur"):
            value = getattr(self, field_name)
            if not value.is_finite() or value < 0:
                raise ValueError(f"{field_name} must be finite and >= 0")
        cached = self.cached_input_per_million_eur
        if cached is not None and (not cached.is_finite() or cached < 0):
            raise ValueError("cached_input_per_million_eur must be finite and >= 0")
        if self.mode is BacktestAIMode.LIVE_EVAL:
            if self.input_per_million_eur == 0 and self.output_per_million_eur == 0:
                raise ValueError("LIVE_EVAL requires explicit non-zero model pricing")
            if self.model_id.startswith("mock-"):
                raise ValueError("LIVE_EVAL requires an explicit real model_id")
        if self.mock_agent_coverage and self.mode is not BacktestAIMode.MOCK:
            raise ValueError("mock_agent_coverage is available only in MOCK mode")
        return self


class SplitInput(FrozenModel):
    design_start: datetime
    design_end: datetime
    validation_start: datetime
    validation_end: datetime
    oos_start: datetime
    oos_end: datetime

    @model_validator(mode="after")
    def timezone_aware(self) -> SplitInput:
        for field_name in (
            "design_start",
            "design_end",
            "validation_start",
            "validation_end",
            "oos_start",
            "oos_end",
        ):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
            object.__setattr__(self, field_name, value.astimezone(UTC))
        return self


class WalkForwardInput(FrozenModel):
    enabled: bool = False
    design_bars: int = Field(default=300, ge=1)
    validation_bars: int = Field(default=100, ge=1)
    oos_bars: int = Field(default=100, ge=1)
    step_bars: int = Field(default=100, ge=1)


class ExecutionInput(FrozenModel):
    initial_balance: Decimal = Decimal("100")
    maker_fee_bps: Decimal = Decimal("10")
    taker_fee_bps: Decimal = Decimal("20")
    market_slippage_bps: Decimal = Decimal("5")
    code_version: str = "batch16.7-working-tree"
    execution_model_version: str = "historical-ohlc-v1"
    random_seed: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_execution(self) -> ExecutionInput:
        if not self.code_version.strip() or not self.execution_model_version.strip():
            raise ValueError("code_version and execution_model_version must not be blank")
        if not self.initial_balance.is_finite() or self.initial_balance <= 0:
            raise ValueError("initial_balance must be finite and > 0")
        for field_name in ("maker_fee_bps", "taker_fee_bps", "market_slippage_bps"):
            value = getattr(self, field_name)
            if not value.is_finite() or value < 0:
                raise ValueError(f"{field_name} must be finite and >= 0")
        return self


class CampaignRequest(FrozenModel):
    dataset: DatasetInput
    split: SplitInput
    risk: RiskInput
    market: MarketConstraintsInput
    ai: AIInput = Field(default_factory=AIInput)
    execution: ExecutionInput = Field(default_factory=ExecutionInput)
    walk_forward: WalkForwardInput = Field(default_factory=WalkForwardInput)
    derivatives: HistoricalDerivativesInput | None = None
    system_id: str = "balanced_v1"

    @model_validator(mode="after")
    def validate_system(self) -> CampaignRequest:
        if not self.system_id.strip():
            raise ValueError("system_id must not be blank")
        if (
            self.derivatives is not None
            and not supports_full_mtf_source(self.dataset.timeframe)
        ):
            raise ValueError(
                "historical derivatives activation requires source timeframe "
                "1m, 5m, or 15m"
            )
        if self.ai.mode is BacktestAIMode.LIVE_EVAL and self.execution.code_version in {
            "batch16.7-working-tree",
            "working-tree-unknown",
        }:
            raise ValueError("LIVE_EVAL requires an explicit immutable execution.code_version")
        return self


class SplitIndexView(FrozenModel):
    design_start: int = Field(ge=0)
    design_end: int = Field(ge=0)
    validation_start: int = Field(ge=0)
    validation_end: int = Field(ge=0)
    oos_start: int = Field(ge=0)
    oos_end: int = Field(ge=0)


class AgentDescriptorView(FrozenModel):
    agent: str
    role: str
    state: str
    core: bool


class DatasetPreview(FrozenModel):
    dataset_id: str
    version: str
    content_sha256: str
    symbol: str
    timeframe: str
    source: str
    candle_count: int
    start_at: datetime
    end_at: datetime
    is_valid: bool
    gap_count: int
    has_duplicates: bool
    missing_fields: tuple[str, ...]
    suggested_split: SplitInput | None = None
    candle_close_ms: tuple[int, ...] = ()
    suggested_split_indices: SplitIndexView | None = None


class BacktestMetricView(FrozenModel):
    value: str | None
    status: str
    reason: str | None = None

    @classmethod
    def from_metric(cls, metric: Any) -> BacktestMetricView:
        raw = getattr(metric, "value", None)
        status = getattr(getattr(metric, "status", None), "value", None) or "UNKNOWN"
        return cls(
            value=None if raw is None else str(raw),
            status=str(status),
            reason=getattr(metric, "reason", None),
        )


class PeriodSummary(FrozenModel):
    role: BacktestPeriodRole
    run_id: str
    processed_candles: int
    opportunities: int
    executed_orders: int
    closed_trades: int
    trading_net: BacktestMetricView
    economic_net: BacktestMetricView
    max_drawdown_pct: BacktestMetricView
    win_rate: BacktestMetricView
    profit_factor: BacktestMetricView
    expectancy: BacktestMetricView
    ai_cost_eur: str
    self_funding_ratio: str | None
    self_funding_status: str
    business_sha256: str


class EquityView(FrozenModel):
    observed_at: datetime
    equity: str


class AgentTraceView(FrozenModel):
    sequence: int
    observed_at: datetime
    role: BacktestPeriodRole
    opportunity_id: str
    agent: str
    phase: str
    title: str
    details: dict[str, Any] = Field(default_factory=dict)
    targets: tuple[str, ...] = ()


class CampaignProgressView(FrozenModel):
    campaign_id: str
    created_at: datetime
    status: str
    phase: str
    current_role: BacktestPeriodRole | None = None
    percent: float = Field(ge=0, le=100)
    work_done: int = Field(ge=0)
    total_work: int = Field(ge=0)
    current_observed_at: datetime | None = None
    opportunity_count: int = Field(ge=0)
    executed_order_count: int = Field(ge=0)
    agent_traces: tuple[AgentTraceView, ...] = ()
    active_agents: tuple[str, ...] = ()
    error: str | None = None
    message: str = ""
    can_cancel: bool = False
    result_available: bool = False


class WalkForwardOOSView(FrozenModel):
    window_index: int
    run_id: str
    trading_net: str | None
    max_drawdown_pct: str | None
    closed_trades: int
    business_sha256: str


class CampaignSummary(FrozenModel):
    campaign_id: str
    created_at: datetime
    status: str
    dataset: DatasetPreview
    ai_mode: BacktestAIMode
    design: PeriodSummary
    validation: PeriodSummary
    oos: PeriodSummary
    oos_equity: tuple[EquityView, ...]
    walk_forward_plan_id: str | None = None
    walk_forward_oos: tuple[WalkForwardOOSView, ...] = ()
    exports: tuple[str, ...] = ()


class BacktestCapabilities(FrozenModel):
    modes: tuple[BacktestAIMode, ...]
    live_eval_available: bool
    cache_entries: int
    supported_timeframes: tuple[str, ...]
    agents: tuple[AgentDescriptorView, ...] = ()
    paper_only: bool = True
    live_trading: bool = False
    campaign_cancel: bool = True
    campaign_progress: bool = True
    agent_traces: bool = True
    agent_activity: bool = True


@dataclass(slots=True)
class _ParsedDataset:
    preview: DatasetPreview
    dataset_ref: DatasetRef
    candles: tuple[Any, ...]


@dataclass(slots=True)
class _RunExecution:
    period: PeriodSummary
    period_report: BacktestPeriodReport
    replay: Any
    evaluation: Any


@dataclass(slots=True)
class _CampaignRecord:
    summary: CampaignSummary
    exports: dict[str, tuple[str, str]]


@dataclass(slots=True)
class _CampaignRuntime:
    campaign_id: str
    created_at: datetime
    status: str = "QUEUED"
    phase: str = "QUEUED"
    current_role: BacktestPeriodRole | None = None
    percent: float = 0.0
    work_done: int = 0
    total_work: int = 0
    current_observed_at: datetime | None = None
    opportunity_count: int = 0
    executed_order_count: int = 0
    traces: list[AgentTraceView] = field(default_factory=list)
    trace_sequence: int = 0
    active_agents: set[str] = field(default_factory=set)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    error: str | None = None
    message: str = ""
    result_available: bool = False


class BacktestDashboardError(RuntimeError):
    pass


# Batch 16.9 — Backtest Dashboard UX
_SCHEMA_AGENT = {
    "ProfessorPlan": "professor",
    "ProfessorFinalDecision": "professor",
    "PalermoReview": "palermo",
    "BerlinAnalysis": "berlin",
    "TokyoAnalysis": "tokyo",
    "NairobiAnalysis": "nairobi",
    "RioAnalysis": "rio",
    "DenverAnalysis": "denver",
}


class ObservableBacktestAIClient:
    def __init__(self, delegate: Any, runtime: _CampaignRuntime) -> None:
        self._delegate = delegate
        self._runtime = runtime

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        agent = _SCHEMA_AGENT.get(request.schema_name)
        if agent is not None:
            self._runtime.active_agents.add(agent)
        try:
            return await self._delegate.complete(request)
        finally:
            if agent is not None:
                self._runtime.active_agents.discard(agent)


class DeterministicBacktestMockProvider:
    """Schema-aware deterministic LLM substitute used only by MOCK backtests."""

    provider_name = "mock"

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        payload = self._payload_for(request)
        return ProviderResponse(
            provider_request_id=f"mock-{request.request_id}",
            model_id=request.model_id,
            output_text=json.dumps(payload, separators=(",", ":"), sort_keys=True),
            usage=TokenUsage(input_tokens=0, cached_input_tokens=0, output_tokens=0),
            latency_ms=0,
        )

    def _payload_for(self, request: ProviderRequest) -> dict[str, Any]:
        try:
            context = json.loads(request.input_text)
        except json.JSONDecodeError:
            context = {}
        schema = request.schema_name
        if schema == "ProfessorPlan":
            return {
                "decision": "MINI_CREW",
                "selected_agents": ["berlin"],
                "rationale": ["deterministic MOCK replay"],
                "request_more_analysis": False,
            }
        if schema == "BerlinAnalysis":
            return self._berlin(context)
        if schema == "TokyoAnalysis":
            return self._tokyo(context)
        if schema == "NairobiAnalysis":
            return self._nairobi(context)
        if schema == "PalermoReview":
            return {
                "verdict": "CAUTION",
                "severity": 0.35,
                "critical_objections": ["historical MOCK assumptions remain synthetic"],
                "missing_checks": [],
                "conditions_to_continue": ["respect deterministic Risk Engine"],
            }
        if schema == "ProfessorFinalDecision":
            return self._final_decision(context)
        raise ValueError(f"unsupported MOCK schema: {schema}")

    @staticmethod
    def _market(payload: dict[str, Any]) -> dict[str, Any]:
        raw = payload.get("market_context")
        return raw if isinstance(raw, dict) else {}

    @classmethod
    def _stance(cls, payload: dict[str, Any]) -> str:
        market = cls._market(payload)
        regime = str(market.get("regime") or "").lower()
        if "bearish" in regime:
            return "SHORT"
        if "bullish" in regime:
            return "LONG"
        close = Decimal(str(market.get("close") or "1"))
        ema = market.get("ema_slow")
        if ema is None:
            return "LONG"
        return "LONG" if close >= Decimal(str(ema)) else "SHORT"

    @classmethod
    def _base_analysis(cls, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "stance": cls._stance(payload),
            "confidence": 0.65,
            "evidence": [
                {
                    "source_key": "market_context.close",
                    "observation": "deterministic MOCK close reference",
                }
            ],
            "risks": ["MOCK analysis is synthetic"],
            "invalidation": ["deterministic stop condition"],
            "data_gaps": [],
        }

    @classmethod
    def _berlin(cls, payload: dict[str, Any]) -> dict[str, Any]:
        base = cls._base_analysis(payload)
        market = cls._market(payload)
        regime = str(market.get("regime") or "unknown").upper()
        allowed = {
            "BULLISH_TREND",
            "BEARISH_TREND",
            "RANGE",
            "TRANSITION",
            "HIGH_VOLATILITY",
            "LOW_VOLATILITY",
            "UNKNOWN",
        }
        base.update(
            {
                "agent": "berlin",
                "regime": regime if regime in allowed else "UNKNOWN",
                "trend_maturity": "UNCLEAR",
                "multi_timeframe_alignment": "UNKNOWN",
            }
        )
        return base

    @classmethod
    def _tokyo(cls, payload: dict[str, Any]) -> dict[str, Any]:
        base = cls._base_analysis(payload)
        base.update(
            {
                "agent": "tokyo",
                "momentum": "BULLISH" if base["stance"] == "LONG" else "BEARISH",
                "momentum_quality": "MODERATE",
                "breakout_quality": "UNCONFIRMED",
            }
        )
        return base

    @classmethod
    def _nairobi(cls, payload: dict[str, Any]) -> dict[str, Any]:
        base = cls._base_analysis(payload)
        base.update(
            {
                "agent": "nairobi",
                "market_structure": "TRANSITION",
                "liquidity_state": "UNKNOWN",
                "breakout_state": "NONE",
            }
        )
        return base

    @classmethod
    def _final_decision(cls, payload: dict[str, Any]) -> dict[str, Any]:
        market = cls._market(payload)
        close = Decimal(str(market.get("close") or "0"))
        analyses = payload.get("specialist_analyses") or []
        direction = analyses[0].get("stance") if analyses else cls._stance(payload)
        if direction not in {"LONG", "SHORT"} or close <= 0:
            return {
                "direction": "NO_TRADE",
                "confidence": 0.5,
                "thesis": ["MOCK could not form a directional trade"],
                "counter_evidence": [],
                "invalidation": [],
                "evidence": [],
                "trade": None,
            }
        if direction == "LONG":
            stop = close * Decimal("0.98")
            target = close * Decimal("1.04")
        else:
            stop = close * Decimal("1.02")
            target = close * Decimal("0.96")
        return {
            "direction": direction,
            "confidence": 0.65,
            "thesis": ["deterministic MOCK directional replay"],
            "counter_evidence": ["MOCK output is not a real model opinion"],
            "invalidation": [f"price reaches {stop}"],
            "evidence": [
                {
                    "source_key": "market_context.close",
                    "observation": "entry anchored to visible candle close",
                }
            ],
            "trade": {
                "entry_price": str(close),
                "stop_price": str(stop),
                "targets": [str(target)],
                "expected_rr": "2",
            },
        }


class DeterministicAgentCoverageMockProvider:
    # Dashboard-only deterministic MOCK coverage wrapper.

    provider_name = "mock"

    def __init__(self, fallback: Any) -> None:
        self._fallback = fallback
        self._plan_index = 0

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        response = await self._fallback.complete(request)
        if request.schema_name != "ProfessorPlan":
            return response

        try:
            context = json.loads(request.input_text)
        except json.JSONDecodeError:
            return response
        if not isinstance(context, dict):
            return response

        raw_available = context.get("available_agents")
        if not isinstance(raw_available, list):
            return response

        available = sorted(
            {
                str(agent_id)
                for agent_id in raw_available
                if isinstance(agent_id, str) and agent_id.strip()
            }
        )
        if not available:
            return response

        crews = [[agent_id] for agent_id in available]
        crews.extend(
            [available[left], available[right]]
            for left in range(len(available))
            for right in range(left + 1, len(available))
        )
        selected = crews[self._plan_index % len(crews)]
        self._plan_index += 1

        try:
            payload = json.loads(response.output_text)
        except json.JSONDecodeError:
            return response
        if not isinstance(payload, dict):
            return response

        payload.update(
            {
                "decision": "MINI_CREW",
                "selected_agents": selected,
                "rationale": [
                    "dashboard deterministic MOCK agent coverage smoke test",
                    "selection restricted to orchestration available_agents",
                ],
                "request_more_analysis": False,
            }
        )
        return ProviderResponse(
            provider_request_id=response.provider_request_id,
            model_id=response.model_id,
            output_text=json.dumps(payload, separators=(",", ":"), sort_keys=True),
            usage=response.usage,
            latency_ms=response.latency_ms,
        )


class BacktestDashboardService:
    """Operator-facing PAPER-only adapter around the completed Batch 16 engine."""

    def __init__(self, *, history_limit: int = 20) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be >= 1")
        self._history_limit = history_limit
        self._records: dict[str, _CampaignRecord] = {}
        self._order: list[str] = []
        self._cache = BacktestResponseCache()
        self._run_lock = asyncio.Lock()
        self._progress_records: dict[str, _CampaignRuntime] = {}
        self._progress_order: list[str] = []
        self._active_campaign_id: str | None = None
        self._active_task: asyncio.Task[None] | None = None

    async def start_campaign(self, request: CampaignRequest) -> CampaignProgressView:
        if self._active_campaign_id is not None:
            active = self._progress_records.get(self._active_campaign_id)
            if active is not None and active.status in {
                "QUEUED",
                "RUNNING",
                "CANCEL_REQUESTED",
            }:
                raise BacktestDashboardError("another backtest campaign is already running")
        if (
            request.ai.mode is BacktestAIMode.LIVE_EVAL
            and not self.capabilities().live_eval_available
        ):
            raise BacktestDashboardError(
                "LIVE_EVAL requires OPENAI_API_KEY in the backend environment"
            )

        campaign_id = str(uuid4())
        runtime = _CampaignRuntime(
            campaign_id=campaign_id,
            created_at=datetime.now(UTC),
        )
        self._store_progress(runtime)
        self._active_campaign_id = campaign_id
        self._active_task = asyncio.create_task(
            self._run_campaign_background(campaign_id, request),
            name=f"money-heist-backtest-{campaign_id}",
        )
        return self._progress_view(runtime)

    async def _run_campaign_background(
        self,
        campaign_id: str,
        request: CampaignRequest,
    ) -> None:
        runtime = self._progress_records[campaign_id]
        runtime.status = "RUNNING"
        runtime.phase = "PREPARING"
        runtime.message = "Validation du dataset et préparation des runs."
        try:
            await self.run_campaign(request, _campaign_id=campaign_id)
        except HistoricalReplayCancelledError:
            runtime.status = "CANCELLED"
            runtime.phase = "CANCELLED"
            runtime.message = "Campagne arrêtée proprement par l'opérateur."
        except Exception as exc:
            runtime.status = "FAILED"
            runtime.phase = "FAILED"
            runtime.error = str(exc)
            runtime.message = "La campagne a échoué."
        else:
            runtime.status = "COMPLETED"
            runtime.phase = "COMPLETED"
            runtime.percent = 100.0
            runtime.result_available = True
            runtime.message = "Campagne terminée."
        finally:
            runtime.current_role = None
            if self._active_campaign_id == campaign_id:
                self._active_campaign_id = None
                self._active_task = None

    def get_campaign_progress(self, campaign_id: str) -> CampaignProgressView | None:
        runtime = self._progress_records.get(campaign_id)
        return None if runtime is None else self._progress_view(runtime)

    def cancel_campaign(self, campaign_id: str) -> CampaignProgressView | None:
        runtime = self._progress_records.get(campaign_id)
        if runtime is None:
            return None
        if runtime.status in {"QUEUED", "RUNNING"}:
            runtime.cancel_event.set()
            runtime.status = "CANCEL_REQUESTED"
            runtime.phase = "CANCEL_REQUESTED"
            runtime.message = "Arrêt demandé; attente du prochain checkpoint de replay."
        return self._progress_view(runtime)

    def _progress_view(self, runtime: _CampaignRuntime) -> CampaignProgressView:
        return CampaignProgressView(
            campaign_id=runtime.campaign_id,
            created_at=runtime.created_at,
            status=runtime.status,
            phase=runtime.phase,
            current_role=runtime.current_role,
            percent=round(runtime.percent, 2),
            work_done=runtime.work_done,
            total_work=runtime.total_work,
            current_observed_at=runtime.current_observed_at,
            opportunity_count=runtime.opportunity_count,
            executed_order_count=runtime.executed_order_count,
            agent_traces=tuple(runtime.traces[-120:]),
            active_agents=tuple(sorted(runtime.active_agents)),
            error=runtime.error,
            message=runtime.message,
            can_cancel=runtime.status in {"QUEUED", "RUNNING"},
            result_available=runtime.result_available,
        )

    def capabilities(self) -> BacktestCapabilities:
        entries = (*CORE_AGENT_REGISTRY.list(), *SPECIALIST_AGENT_REGISTRY.list())
        agents = tuple(
            AgentDescriptorView(
                agent=entry.agent_id,
                role=entry.role.value,
                state=entry.state.value,
                core=entry.core,
            )
            for entry in entries
        )
        return BacktestCapabilities(
            modes=tuple(BacktestAIMode),
            live_eval_available=bool(os.getenv("OPENAI_API_KEY", "").strip()),
            cache_entries=len(self._cache),
            supported_timeframes=tuple(_TIMEFRAME_SECONDS),
            agents=agents,
        )

    def preview_dataset(self, request: DatasetInput) -> DatasetPreview:
        return self._parse_dataset(request).preview

    async def run_campaign(
        self,
        request: CampaignRequest,
        *,
        _campaign_id: str | None = None,
    ) -> CampaignSummary:
        async with self._run_lock:
            parsed = self._parse_dataset(request.dataset)
            if not parsed.preview.is_valid:
                raise BacktestDashboardError(
                    "dataset quality is invalid; resolve gaps/duplicates/missing fields first"
                )
            if (
                request.ai.mode is BacktestAIMode.LIVE_EVAL
                and not self.capabilities().live_eval_available
            ):
                raise BacktestDashboardError(
                    "LIVE_EVAL requires OPENAI_API_KEY in the backend environment"
                )

            risk_profile = self._risk_profile(request.risk)
            market_constraints = self._market_constraints(request.market)
            historical_derivatives_archive = (
                self._parse_historical_derivatives(request.derivatives)
                if request.derivatives is not None
                else None
            )
            if (
                historical_derivatives_archive is not None
                and historical_derivatives_archive.symbol
                != parsed.dataset_ref.symbol
            ):
                raise BacktestDashboardError(
                    "historical derivatives archive symbol does not match dataset"
                )
            config = self._backtest_config(
                request,
                historical_derivatives_archive=historical_derivatives_archive,
            )
            campaign_budget = AIBudgetLedger(request.ai.hard_budget_eur)
            split = BacktestSplitPlan.create(
                dataset=parsed.dataset_ref,
                design_start=request.split.design_start,
                design_end=request.split.design_end,
                validation_start=request.split.validation_start,
                validation_end=request.split.validation_end,
                oos_start=request.split.oos_start,
                oos_end=request.split.oos_end,
                label_prefix="dashboard",
            )
            run_set = split.runs(config)
            runtime = self._progress_records.get(_campaign_id) if _campaign_id is not None else None
            if runtime is not None:
                runtime.total_work = sum(
                    self._run_work_units(parsed.candles, run_set.by_role(role))
                    for role in BacktestPeriodRole
                )
                runtime.work_done = 0
                runtime.percent = 0.0
                runtime.phase = "DESIGN"
                runtime.message = "Replay DESIGN en cours."

            executions, split_report, exports = await self._execute_split(
                split=split,
                run_set=run_set,
                candles=parsed.candles,
                risk_profile=risk_profile,
                market_constraints=market_constraints,
                ai=request.ai,
                budget=campaign_budget,
                historical_derivatives_archive=(
                    historical_derivatives_archive
                ),
                runtime=runtime,
            )

            wf_report: WalkForwardReport | None = None
            wf_views: tuple[WalkForwardOOSView, ...] = ()
            if request.walk_forward.enabled:
                if runtime is not None:
                    runtime.phase = "WALK_FORWARD"
                    runtime.message = (
                        "Walk-forward en cours; progression principale déjà parcourue."
                    )
                plan = build_walk_forward_plan(
                    parsed.candles,
                    dataset=parsed.dataset_ref,
                    design_bars=request.walk_forward.design_bars,
                    validation_bars=request.walk_forward.validation_bars,
                    oos_bars=request.walk_forward.oos_bars,
                    step_bars=request.walk_forward.step_bars,
                )

                async def execute_window(window: Any, runs: BacktestRunSet) -> BacktestSplitReport:
                    _, report, _ = await self._execute_split(
                        split=window.split,
                        run_set=runs,
                        candles=parsed.candles,
                        risk_profile=risk_profile,
                        market_constraints=market_constraints,
                        ai=request.ai,
                        budget=campaign_budget,
                        historical_derivatives_archive=(
                            historical_derivatives_archive
                        ),
                        runtime=runtime,
                    )
                    return report

                wf_report = await execute_walk_forward(
                    plan,
                    config=config,
                    execute_split=execute_window,
                )
                exports["walk-forward-report.json"] = (
                    "application/json",
                    walk_forward_report_to_json(wf_report),
                )
                wf_views = tuple(
                    WalkForwardOOSView(
                        window_index=index,
                        run_id=report.oos.run_id,
                        trading_net=(
                            None
                            if report.oos.trading_net.value is None
                            else str(report.oos.trading_net.value)
                        ),
                        max_drawdown_pct=(
                            None
                            if report.oos.max_drawdown_pct.value is None
                            else str(report.oos.max_drawdown_pct.value)
                        ),
                        closed_trades=report.oos.closed_trade_count,
                        business_sha256=report.oos.business_sha256,
                    )
                    for index, report in enumerate(wf_report.windows, start=1)
                )

            exports["split-report.json"] = (
                "application/json",
                split_report_to_json(split_report),
            )
            exports["ai-cache.json"] = ("application/json", self._cache.export_json())

            if runtime is not None:
                runtime.phase = "FINALIZING"
                runtime.message = "Génération des rapports et exports."
                runtime.percent = max(runtime.percent, 99.0)

            campaign_id = _campaign_id or str(uuid4())
            oos_equity = tuple(
                EquityView(observed_at=point.observed_at, equity=str(point.equity))
                for point in executions[BacktestPeriodRole.OOS].evaluation.equity_points
            )
            summary = CampaignSummary(
                campaign_id=campaign_id,
                created_at=datetime.now(UTC),
                status="COMPLETED",
                dataset=parsed.preview,
                ai_mode=request.ai.mode,
                design=executions[BacktestPeriodRole.DESIGN].period,
                validation=executions[BacktestPeriodRole.VALIDATION].period,
                oos=executions[BacktestPeriodRole.OOS].period,
                oos_equity=oos_equity,
                walk_forward_plan_id=None if wf_report is None else wf_report.plan_id,
                walk_forward_oos=wf_views,
                exports=tuple(sorted(exports)),
            )
            self._store(_CampaignRecord(summary=summary, exports=exports))
            return summary

    def list_campaigns(self) -> tuple[CampaignSummary, ...]:
        return tuple(self._records[key].summary for key in reversed(self._order))

    def get_campaign(self, campaign_id: str) -> CampaignSummary | None:
        record = self._records.get(campaign_id)
        return None if record is None else record.summary

    def get_export(self, campaign_id: str, name: str) -> tuple[str, str] | None:
        record = self._records.get(campaign_id)
        if record is None:
            return None
        return record.exports.get(name)

    def export_cache(self) -> str:
        return self._cache.export_json()

    def import_cache(self, payload: str) -> int:
        if self._run_lock.locked() or self._active_campaign_id is not None:
            raise BacktestDashboardError("cannot replace AI cache while a campaign is running")
        self._cache = BacktestResponseCache.import_json(payload)
        return len(self._cache)

    def _store_progress(self, runtime: _CampaignRuntime) -> None:
        self._progress_records[runtime.campaign_id] = runtime
        self._progress_order.append(runtime.campaign_id)
        while len(self._progress_order) > self._history_limit:
            removed = self._progress_order.pop(0)
            if removed != self._active_campaign_id:
                self._progress_records.pop(removed, None)

    def _store(self, record: _CampaignRecord) -> None:
        campaign_id = record.summary.campaign_id
        self._records[campaign_id] = record
        self._order.append(campaign_id)
        while len(self._order) > self._history_limit:
            removed = self._order.pop(0)
            self._records.pop(removed, None)

    @staticmethod
    def _parse_historical_derivatives(
        request: HistoricalDerivativesInput,
    ) -> HistoricalDerivativesAnalyticsArchive:
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".csv",
                delete=False,
                encoding="utf-8-sig",
                newline="",
            ) as handle:
                handle.write(request.csv_text)
                temp_path = Path(handle.name)
            return HistoricalDerivativesAnalyticsArchive.from_canonical_csv(
                temp_path
            )
        except (OSError, ValueError) as exc:
            raise BacktestDashboardError(
                f"historical derivatives archive is invalid: {exc}"
            ) from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def _parse_dataset(self, request: DatasetInput) -> _ParsedDataset:
        interval_seconds = request.candle_interval_seconds or _TIMEFRAME_SECONDS.get(
            request.timeframe
        )
        if interval_seconds is None:
            raise BacktestDashboardError(
                "unknown timeframe; provide candle_interval_seconds explicitly"
            )
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".csv",
                delete=False,
                encoding="utf-8-sig",
                newline="",
            ) as handle:
                handle.write(request.csv_text)
                temp_path = Path(handle.name)
            imported = import_candles_csv(
                temp_path,
                symbol=request.symbol,
                timeframe=request.timeframe,
                source=request.source,
                candle_interval=timedelta(seconds=interval_seconds),
            )
        except HistoricalImportError as exc:
            raise BacktestDashboardError(str(exc)) from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

        dataset = DatasetRef.from_candles(
            imported.candles,
            symbol=request.symbol,
            timeframe=request.timeframe,
            source=request.source,
        )
        suggested_indices = self._suggest_split_indices(imported.candles)
        preview = DatasetPreview(
            dataset_id=dataset.dataset_id,
            version=dataset.version,
            content_sha256=dataset.content_sha256,
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            source=dataset.source,
            candle_count=dataset.candle_count,
            start_at=dataset.start_at,
            end_at=dataset.end_at,
            is_valid=bool(imported.quality.is_valid),
            gap_count=int(imported.quality.gap_count),
            has_duplicates=bool(imported.quality.has_duplicates),
            missing_fields=tuple(imported.quality.missing_fields),
            suggested_split=self._split_from_indices(imported.candles, suggested_indices),
            candle_close_ms=tuple(
                int(candle.close_time.timestamp() * 1000)
                for candle in imported.candles
            ),
            suggested_split_indices=suggested_indices,
        )
        return _ParsedDataset(preview=preview, dataset_ref=dataset, candles=imported.candles)

    @staticmethod
    def _suggest_split_indices(candles: tuple[Any, ...]) -> SplitIndexView | None:
        if len(candles) < 6:
            return None
        design_end_index = max(1, int(len(candles) * 0.60)) - 1
        validation_end_index = max(design_end_index + 1, int(len(candles) * 0.80)) - 1
        validation_start_index = design_end_index + 1
        oos_start_index = validation_end_index + 1
        if oos_start_index >= len(candles):
            return None
        return SplitIndexView(
            design_start=0,
            design_end=design_end_index,
            validation_start=validation_start_index,
            validation_end=validation_end_index,
            oos_start=oos_start_index,
            oos_end=len(candles) - 1,
        )

    @staticmethod
    def _split_from_indices(
        candles: tuple[Any, ...],
        indices: SplitIndexView | None,
    ) -> SplitInput | None:
        if indices is None:
            return None
        return SplitInput(
            design_start=candles[indices.design_start].close_time,
            design_end=candles[indices.design_end].close_time,
            validation_start=candles[indices.validation_start].close_time,
            validation_end=candles[indices.validation_end].close_time,
            oos_start=candles[indices.oos_start].close_time,
            oos_end=candles[indices.oos_end].close_time,
        )

    @classmethod
    def _suggest_split(cls, candles: tuple[Any, ...]) -> SplitInput | None:
        return cls._split_from_indices(candles, cls._suggest_split_indices(candles))

    @staticmethod
    def _risk_profile(request: RiskInput) -> RiskProfile:
        return RiskProfile(
            risk_profile_id=request.risk_profile_id,
            max_risk_per_trade_pct=request.max_risk_per_trade_pct,
            max_daily_loss_pct=request.max_daily_loss_pct,
            max_drawdown_pct=request.max_drawdown_pct,
            max_portfolio_risk_pct=request.max_portfolio_risk_pct,
            max_positions=request.max_positions,
            max_leverage=request.max_leverage,
            max_correlated_exposure_pct=request.max_correlated_exposure_pct,
            min_expected_rr=request.min_expected_rr,
        )

    @staticmethod
    def _market_constraints(request: MarketConstraintsInput) -> MarketConstraints:
        return MarketConstraints(
            qty_step=request.qty_step,
            min_qty=request.min_qty,
            min_notional=request.min_notional,
            max_qty=request.max_qty,
            max_leverage=request.max_leverage,
        )

    @staticmethod
    def _prompt_versions() -> dict[str, str]:
        entries = (*CORE_AGENT_REGISTRY.list(), *SPECIALIST_AGENT_REGISTRY.list())
        return {entry.agent_id: entry.prompt_version for entry in entries}

    def _backtest_config(
        self,
        request: CampaignRequest,
        *,
        historical_derivatives_archive: (
            HistoricalDerivativesAnalyticsArchive | None
        ) = None,
    ) -> BacktestConfig:
        model_versions = {
            entry.agent_id: request.ai.model_id
            for entry in (*CORE_AGENT_REGISTRY.list(), *SPECIALIST_AGENT_REGISTRY.list())
        }
        assumptions = {
            "dashboard": "batch16.7",
            "risk_profile_id": request.risk.risk_profile_id,
            "max_risk_per_trade_pct": str(request.risk.max_risk_per_trade_pct),
            "max_daily_loss_pct": str(request.risk.max_daily_loss_pct),
            "max_drawdown_pct": str(request.risk.max_drawdown_pct),
            "max_portfolio_risk_pct": str(request.risk.max_portfolio_risk_pct),
            "max_positions": str(request.risk.max_positions),
            "risk_max_leverage": str(request.risk.max_leverage),
            "max_correlated_exposure_pct": str(request.risk.max_correlated_exposure_pct),
            "min_expected_rr": str(request.risk.min_expected_rr),
            "market_qty_step": str(request.market.qty_step),
            "market_min_qty": str(request.market.min_qty),
            "market_min_notional": str(request.market.min_notional),
            "market_max_qty": str(request.market.max_qty),
            "market_max_leverage": str(request.market.max_leverage),
            "ai_hard_budget_eur": str(request.ai.hard_budget_eur),
            "ai_reasoning_effort": request.ai.reasoning_effort,
            "ai_input_per_million_eur": str(request.ai.input_per_million_eur),
            "ai_output_per_million_eur": str(request.ai.output_per_million_eur),
            "ai_cached_input_per_million_eur": str(request.ai.cached_input_per_million_eur),
        }
        assumptions.update(
            mtf_execution_assumptions(request.dataset.timeframe)
        )
        if request.derivatives is not None:
            archive = historical_derivatives_archive
            if archive is None:
                archive = self._parse_historical_derivatives(
                    request.derivatives
                )
            if archive.symbol != request.dataset.symbol.strip().upper():
                raise BacktestDashboardError(
                    "historical derivatives archive symbol does not match dataset"
                )
            assumptions.update(
                historical_derivatives_execution_assumptions(
                    archive,
                    max_age_seconds=request.derivatives.max_age_seconds,
                )
            )
        elif historical_derivatives_archive is not None:
            raise BacktestDashboardError(
                "derivatives archive supplied without explicit request.derivatives"
            )
        return BacktestConfig(
            system_id=request.system_id,
            risk_version=request.risk.risk_version,
            code_version=request.execution.code_version,
            execution_model_version=request.execution.execution_model_version,
            random_seed=request.execution.random_seed,
            ai_mode=request.ai.mode,
            initial_balance=request.execution.initial_balance,
            maker_fee_bps=request.execution.maker_fee_bps,
            taker_fee_bps=request.execution.taker_fee_bps,
            market_slippage_bps=request.execution.market_slippage_bps,
            prompt_versions=self._prompt_versions(),
            model_versions=model_versions,
            execution_assumptions=assumptions,
        )

    async def _execute_split(
        self,
        *,
        split: BacktestSplitPlan,
        run_set: BacktestRunSet,
        candles: tuple[Any, ...],
        risk_profile: RiskProfile,
        market_constraints: MarketConstraints,
        ai: AIInput,
        budget: AIBudgetLedger,
        historical_derivatives_archive: (
            HistoricalDerivativesAnalyticsArchive | None
        ) = None,
        runtime: _CampaignRuntime | None = None,
    ) -> tuple[
        dict[BacktestPeriodRole, _RunExecution],
        BacktestSplitReport,
        dict[str, tuple[str, str]],
    ]:
        executions: dict[BacktestPeriodRole, _RunExecution] = {}
        exports: dict[str, tuple[str, str]] = {}
        for role in BacktestPeriodRole:
            run = run_set.by_role(role)
            if runtime is not None:
                runtime.current_role = role
                runtime.phase = role.value
                runtime.message = f"Replay {role.value} en cours."
            execution = await self._execute_run(
                role=role,
                run=run,
                candles=candles,
                risk_profile=risk_profile,
                market_constraints=market_constraints,
                ai=ai,
                budget=budget,
                historical_derivatives_archive=(
                    historical_derivatives_archive
                ),
                runtime=runtime,
            )
            executions[role] = execution
            prefix = role.value.lower()
            manifest = build_run_manifest(execution.replay, execution.evaluation)
            exports[f"{prefix}-manifest.json"] = (
                "application/json",
                manifest_to_json(manifest),
            )
            exports[f"{prefix}-equity.csv"] = (
                "text/csv",
                equity_curve_to_csv(execution.evaluation.equity_points),
            )
            exports[f"{prefix}-closed-trades.csv"] = (
                "text/csv",
                closed_trades_to_csv(execution.evaluation.report),
            )

        denver_sources = tuple(
            (
                executions[role].replay,
                executions[role].evaluation,
                role,
            )
            for role in BacktestPeriodRole
        )
        try:
            denver_catalog = catalog_from_historical_runs(
                denver_sources
            )
        except HistoricalSetupAttributionError as exc:
            exports["denver-setup-stats-status.json"] = (
                "application/json",
                json.dumps(
                    {
                        "status": "UNAVAILABLE",
                        "reason": "AMBIGUOUS_TRADE_ATTRIBUTION",
                        "message": str(exc),
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        else:
            exports["denver-setup-stats-catalog.json"] = (
                "application/json",
                denver_catalog.to_json(),
            )
            exports["denver-setup-stats-status.json"] = (
                "application/json",
                json.dumps(
                    {
                        "status": "AVAILABLE",
                        "catalog_id": denver_catalog.catalog_id,
                        "observation_count": len(
                            denver_catalog.observations
                        ),
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )

        report = BacktestSplitReport.create(
            split,
            design=executions[BacktestPeriodRole.DESIGN].period_report,
            validation=executions[BacktestPeriodRole.VALIDATION].period_report,
            oos=executions[BacktestPeriodRole.OOS].period_report,
        )
        return executions, report, exports

    async def _execute_run(
        self,
        *,
        role: BacktestPeriodRole,
        run: BacktestRun,
        candles: tuple[Any, ...],
        risk_profile: RiskProfile,
        market_constraints: MarketConstraints,
        ai: AIInput,
        budget: AIBudgetLedger,
        historical_derivatives_archive: (
            HistoricalDerivativesAnalyticsArchive | None
        ) = None,
        runtime: _CampaignRuntime | None = None,
    ) -> _RunExecution:
        clock = ReplayClock.start(run.dataset.start_at)
        broker = PaperBroker(
            PaperBrokerConfig(
                system_id=run.config.system_id,
                initial_balance=run.config.initial_balance,
                maker_fee_bps=run.config.maker_fee_bps,
                taker_fee_bps=run.config.taker_fee_bps,
                market_slippage_bps=run.config.market_slippage_bps,
            ),
            id_factory=ReplayIdFactory(run.run_id),
            clock=clock,
        )
        portfolio = BacktestPortfolioStateProvider(
            system_id=run.config.system_id,
            initial_balance=run.config.initial_balance,
        )
        lifecycle = HistoricalPositionLifecycle(broker=broker, system_id=run.config.system_id)
        journal = InMemoryPaperPipelineJournal()
        usage = InMemoryAIUsageRecorder()
        pricing = ModelPricing(
            input_per_million_eur=ai.input_per_million_eur,
            output_per_million_eur=ai.output_per_million_eur,
            cached_input_per_million_eur=ai.cached_input_per_million_eur,
        )
        provider_name = "mock" if run.config.ai_mode is BacktestAIMode.MOCK else "openai"
        router = ModelRouter(
            [
                ModelRoute(
                    route_id="core_reasoning",
                    provider=provider_name,
                    model_id=ai.model_id,
                    pricing=pricing,
                    max_output_tokens=1200,
                    reasoning_effort=ai.reasoning_effort,
                ),
                ModelRoute(
                    route_id="economy",
                    provider=provider_name,
                    model_id=ai.model_id,
                    pricing=pricing,
                    max_output_tokens=800,
                    reasoning_effort=ai.reasoning_effort,
                ),
            ]
        )
        mock_client: Any = DeterministicBacktestMockProvider()
        if run.config.ai_mode is BacktestAIMode.MOCK and ai.mock_agent_coverage:
            mock_client = DeterministicAgentCoverageMockProvider(
                DeterministicAdvancedSpecialistMockProvider(mock_client)
            )
        live_client = None
        if run.config.ai_mode is BacktestAIMode.LIVE_EVAL:
            live_client = OpenAIResponsesClient(
                api_key=os.environ["OPENAI_API_KEY"],
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            )
        backtest_client = BacktestAIClient.from_run(
            run,
            cache=self._cache,
            mock_client=mock_client if run.config.ai_mode is BacktestAIMode.MOCK else None,
            live_client=live_client,
        )
        observable_client = (
            ObservableBacktestAIClient(backtest_client, runtime)
            if runtime is not None
            else backtest_client
        )
        gateway = AIGateway(
            router=router,
            clients={provider_name: observable_client},
            budget=budget,
            max_attempts=1,
            retry_backoff_seconds=0,
            usage_recorder=usage,
        )
        orchestration = OrchestrationPipeline(gateway=gateway, budget=budget)
        market_constraints_provider = InMemoryMarketConstraintsProvider(
            {run.dataset.symbol: market_constraints}
        )
        pipeline = PaperTradingPipeline(
            orchestration=orchestration,
            risk_engine=RiskEngine(),
            paper_broker=broker,
            portfolio_provider=portfolio,
            risk_profile_provider=InMemoryRiskProfileProvider({run.config.system_id: risk_profile}),
            market_constraints_provider=market_constraints_provider,
            kill_switch_provider=InMemoryKillSwitchStateProvider(
                {run.config.system_id: KillSwitchState()}
            ),
            journal=journal,
            clock=clock,
        )
        runner_kwargs = mtf_runner_kwargs(
            run.config.execution_assumptions
        )
        runner_kwargs.update(
            historical_derivatives_runner_kwargs(
                run.config.execution_assumptions,
                historical_derivatives_archive,
            )
        )
        runner = HistoricalReplayRunner(
            paper_pipeline=pipeline,
            clock=clock,
            portfolio_provider=portfolio,
            market_constraints_provider=market_constraints_provider,
            position_lifecycle=lifecycle,
            **runner_kwargs,
        )
        last_progress = 0

        def on_progress(done: int, total: int, observed_at: datetime) -> None:
            nonlocal last_progress
            if runtime is None:
                return
            delta = max(0, done - last_progress)
            last_progress = done
            runtime.work_done += delta
            runtime.current_observed_at = observed_at
            if runtime.total_work > 0:
                computed = runtime.work_done / runtime.total_work * 100.0
                runtime.percent = max(runtime.percent, min(99.0, computed))

        def on_point(point: Any) -> None:
            if runtime is None:
                return
            if point.opportunity is not None:
                runtime.opportunity_count += 1
            pipeline_result = point.pipeline_result
            if pipeline_result is not None and getattr(pipeline_result, "fill", None) is not None:
                runtime.executed_order_count += 1
            if pipeline_result is not None:
                self._append_agent_traces(runtime, role, point)

        replay = await runner.run(
            candles=candles,
            run=run,
            progress_callback=on_progress if runtime is not None else None,
            point_callback=on_point if runtime is not None else None,
            cancel_check=((lambda: runtime.cancel_event.is_set()) if runtime is not None else None),
        )
        self._raise_cached_miss(replay, run.config.ai_mode)
        evaluation = await evaluate_historical_replay(
            replay,
            broker=broker,
            ai_usage_records=tuple(usage.records),
            paper_events=journal.events(),
        )
        period_report = BacktestPeriodReport.from_evaluation(role, replay, evaluation)
        period = self._period_summary(role, replay, evaluation, period_report)
        return _RunExecution(
            period=period,
            period_report=period_report,
            replay=replay,
            evaluation=evaluation,
        )

    @staticmethod
    def _run_work_units(candles: tuple[Any, ...], run: BacktestRun) -> int:
        return sum(1 for candle in candles if candle.close_time <= run.period_end)

    def _append_agent_traces(
        self,
        runtime: _CampaignRuntime,
        role: BacktestPeriodRole,
        point: Any,
    ) -> None:
        pipeline_result = point.pipeline_result
        orchestration = getattr(pipeline_result, "orchestration_result", None)
        if orchestration is None:
            return

        opportunity_id = str(getattr(orchestration, "opportunity_id", ""))
        observed_at = point.observed_at

        def add(
            agent: str,
            phase: str,
            title: str,
            value: Any,
            *,
            targets: tuple[str, ...] = (),
        ) -> None:
            if value is None:
                return
            if hasattr(value, "model_dump"):
                details = value.model_dump(mode="json")
            elif isinstance(value, dict):
                details = value
            else:
                details = {"value": str(value)}
            runtime.trace_sequence += 1
            runtime.traces.append(
                AgentTraceView(
                    sequence=runtime.trace_sequence,
                    observed_at=observed_at,
                    role=role,
                    opportunity_id=opportunity_id,
                    agent=agent,
                    phase=phase,
                    title=title,
                    details=details,
                    targets=targets,
                )
            )
            if len(runtime.traces) > 160:
                del runtime.traces[:-160]

        plan = getattr(orchestration, "professor_plan", None)
        if plan is not None:
            selected = ", ".join(getattr(plan, "selected_agents", ())) or "aucun"
            add(
                "professor",
                "PLAN",
                f"{getattr(plan, 'decision', 'PLAN')} · {selected}",
                plan,
                targets=tuple(getattr(plan, "selected_agents", ())),
            )

        for specialist in getattr(orchestration, "specialist_runs", ()):
            analysis = specialist.analysis
            stance = getattr(analysis, "stance", "")
            confidence = getattr(analysis, "confidence", None)
            suffix = f" · confiance {float(confidence):.2f}" if confidence is not None else ""
            add(
                specialist.agent_id,
                "ANALYSIS",
                f"{stance}{suffix}".strip(" ·"),
                analysis,
                targets=("professor",),
            )

        palermo = getattr(orchestration, "palermo_run", None)
        if palermo is not None:
            review = palermo.review
            add(
                "palermo",
                "RED_TEAM",
                f"{getattr(review, 'verdict', 'REVIEW')} · sévérité "
                f"{getattr(review, 'severity', '—')}",
                review,
                targets=("professor",),
            )

        risk_record = getattr(pipeline_result, "risk_record", None)
        decision = getattr(orchestration, "professor_decision", None)
        if decision is not None:
            add(
                "professor",
                "FINAL",
                f"{decision.direction} · confiance {decision.confidence:.2f}",
                decision,
                targets=("risk_engine",) if risk_record is not None else (),
            )

        if risk_record is not None:
            add("risk_engine", "RISK", "Décision Risk Engine", risk_record)

        failure = getattr(orchestration, "failure", None)
        if failure is not None:
            add("orchestration", "FAILED", str(failure.code), failure)

    @staticmethod
    def _raise_cached_miss(replay: Any, mode: BacktestAIMode) -> None:
        if mode is not BacktestAIMode.CACHED:
            return
        for result in replay.pipeline_results:
            failure = getattr(result, "failure", None)
            message = str(getattr(failure, "message", ""))
            if "cache miss" in message.lower():
                raise BacktestDashboardError(message)

    @staticmethod
    def _period_summary(
        role: BacktestPeriodRole,
        replay: Any,
        evaluation: Any,
        period_report: BacktestPeriodReport,
    ) -> PeriodSummary:
        report = evaluation.report
        ratio = report.self_funding_ratio
        ratio_value = getattr(ratio, "value", None)
        ratio_status = getattr(getattr(ratio, "status", None), "value", "UNKNOWN")
        return PeriodSummary(
            role=role,
            run_id=replay.backtest_result.run.run_id,
            processed_candles=replay.backtest_result.processed_candles,
            opportunities=replay.backtest_result.opportunity_count,
            executed_orders=replay.backtest_result.executed_order_count,
            closed_trades=report.trading.closed_trade_count,
            trading_net=BacktestMetricView.from_metric(report.trading.trading_net),
            economic_net=BacktestMetricView.from_metric(report.economic_net),
            max_drawdown_pct=BacktestMetricView.from_metric(report.trading.max_drawdown_pct),
            win_rate=BacktestMetricView.from_metric(report.trading.win_rate),
            profit_factor=BacktestMetricView.from_metric(report.trading.profit_factor),
            expectancy=BacktestMetricView.from_metric(report.trading.expectancy),
            ai_cost_eur=str(report.ai_costs.total_cost_eur),
            self_funding_ratio=None if ratio_value is None else str(ratio_value),
            self_funding_status=str(ratio_status),
            business_sha256=period_report.business_sha256,
        )


def get_backtest_dashboard_service(request: Request) -> BacktestDashboardService:
    service = getattr(request.app.state, "backtest_dashboard_service", None)
    if service is None:
        service = BacktestDashboardService()
        request.app.state.backtest_dashboard_service = service
    if not isinstance(service, BacktestDashboardService):
        raise RuntimeError(
            "app.state.backtest_dashboard_service must be a BacktestDashboardService"
        )
    return service


__all__ = [
    "AIInput",
    "AgentDescriptorView",
    "BacktestCapabilities",
    "BacktestDashboardError",
    "BacktestDashboardService",
    "CampaignProgressView",
    "CampaignRequest",
    "CampaignSummary",
    "DatasetInput",
    "DatasetPreview",
    "DeterministicBacktestMockProvider",
    "DeterministicAgentCoverageMockProvider",
    "ObservableBacktestAIClient",
    "ExecutionInput",
    "MarketConstraintsInput",
    "RiskInput",
    "SplitIndexView",
    "SplitInput",
    "WalkForwardInput",
    "get_backtest_dashboard_service",
]
