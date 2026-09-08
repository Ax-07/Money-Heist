from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
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
    HistoricalReplayRunner,
    ReplayClock,
    ReplayIdFactory,
    WalkForwardReport,
    build_run_manifest,
    build_walk_forward_plan,
    closed_trades_to_csv,
    equity_curve_to_csv,
    evaluate_historical_replay,
    execute_walk_forward,
    manifest_to_json,
    split_report_to_json,
    walk_forward_report_to_json,
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
    input_per_million_eur: Decimal = Decimal("0")
    output_per_million_eur: Decimal = Decimal("0")
    cached_input_per_million_eur: Decimal | None = None

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
    system_id: str = "balanced_v1"

    @model_validator(mode="after")
    def validate_system(self) -> CampaignRequest:
        if not self.system_id.strip():
            raise ValueError("system_id must not be blank")
        return self


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
    paper_only: bool = True
    live_trading: bool = False


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


class BacktestDashboardError(RuntimeError):
    pass


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

    def capabilities(self) -> BacktestCapabilities:
        return BacktestCapabilities(
            modes=tuple(BacktestAIMode),
            live_eval_available=bool(os.getenv("OPENAI_API_KEY", "").strip()),
            cache_entries=len(self._cache),
            supported_timeframes=tuple(_TIMEFRAME_SECONDS),
        )

    def preview_dataset(self, request: DatasetInput) -> DatasetPreview:
        return self._parse_dataset(request).preview

    async def run_campaign(self, request: CampaignRequest) -> CampaignSummary:
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
            config = self._backtest_config(request)
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
            executions, split_report, exports = await self._execute_split(
                split=split,
                run_set=run_set,
                candles=parsed.candles,
                risk_profile=risk_profile,
                market_constraints=market_constraints,
                ai=request.ai,
            )

            wf_report: WalkForwardReport | None = None
            wf_views: tuple[WalkForwardOOSView, ...] = ()
            if request.walk_forward.enabled:
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

            campaign_id = str(uuid4())
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
        if self._run_lock.locked():
            raise BacktestDashboardError("cannot replace AI cache while a campaign is running")
        self._cache = BacktestResponseCache.import_json(payload)
        return len(self._cache)

    def _store(self, record: _CampaignRecord) -> None:
        campaign_id = record.summary.campaign_id
        self._records[campaign_id] = record
        self._order.append(campaign_id)
        while len(self._order) > self._history_limit:
            removed = self._order.pop(0)
            self._records.pop(removed, None)

    def _parse_dataset(self, request: DatasetInput) -> _ParsedDataset:
        interval_seconds = (
            request.candle_interval_seconds or _TIMEFRAME_SECONDS.get(request.timeframe)
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
            suggested_split=self._suggest_split(imported.candles),
        )
        return _ParsedDataset(preview=preview, dataset_ref=dataset, candles=imported.candles)

    @staticmethod
    def _suggest_split(candles: tuple[Any, ...]) -> SplitInput | None:
        if len(candles) < 6:
            return None
        design_end_index = max(1, int(len(candles) * 0.60)) - 1
        validation_end_index = max(design_end_index + 1, int(len(candles) * 0.80)) - 1
        validation_start_index = design_end_index + 1
        oos_start_index = validation_end_index + 1
        if oos_start_index >= len(candles):
            return None
        return SplitInput(
            design_start=candles[0].close_time,
            design_end=candles[design_end_index].close_time,
            validation_start=candles[validation_start_index].close_time,
            validation_end=candles[validation_end_index].close_time,
            oos_start=candles[oos_start_index].close_time,
            oos_end=candles[-1].close_time,
        )

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

    def _backtest_config(self, request: CampaignRequest) -> BacktestConfig:
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
            "max_correlated_exposure_pct": str(
                request.risk.max_correlated_exposure_pct
            ),
            "min_expected_rr": str(request.risk.min_expected_rr),
            "market_qty_step": str(request.market.qty_step),
            "market_min_qty": str(request.market.min_qty),
            "market_min_notional": str(request.market.min_notional),
            "market_max_qty": str(request.market.max_qty),
            "market_max_leverage": str(request.market.max_leverage),
            "ai_hard_budget_eur": str(request.ai.hard_budget_eur),
            "ai_input_per_million_eur": str(request.ai.input_per_million_eur),
            "ai_output_per_million_eur": str(request.ai.output_per_million_eur),
            "ai_cached_input_per_million_eur": str(
                request.ai.cached_input_per_million_eur
            ),
        }
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
    ) -> tuple[
        dict[BacktestPeriodRole, _RunExecution],
        BacktestSplitReport,
        dict[str, tuple[str, str]],
    ]:
        executions: dict[BacktestPeriodRole, _RunExecution] = {}
        exports: dict[str, tuple[str, str]] = {}
        for role in BacktestPeriodRole:
            run = run_set.by_role(role)
            execution = await self._execute_run(
                role=role,
                run=run,
                candles=candles,
                risk_profile=risk_profile,
                market_constraints=market_constraints,
                ai=ai,
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
        budget = AIBudgetLedger(ai.hard_budget_eur)
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
                ),
                ModelRoute(
                    route_id="economy",
                    provider=provider_name,
                    model_id=ai.model_id,
                    pricing=pricing,
                    max_output_tokens=800,
                ),
            ]
        )
        mock_client = DeterministicBacktestMockProvider()
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
        gateway = AIGateway(
            router=router,
            clients={provider_name: backtest_client},
            budget=budget,
            max_attempts=1,
            retry_backoff_seconds=0,
            usage_recorder=usage,
        )
        orchestration = OrchestrationPipeline(gateway=gateway, budget=budget)
        pipeline = PaperTradingPipeline(
            orchestration=orchestration,
            risk_engine=RiskEngine(),
            paper_broker=broker,
            portfolio_provider=portfolio,
            risk_profile_provider=InMemoryRiskProfileProvider(
                {run.config.system_id: risk_profile}
            ),
            market_constraints_provider=InMemoryMarketConstraintsProvider(
                {run.dataset.symbol: market_constraints}
            ),
            kill_switch_provider=InMemoryKillSwitchStateProvider(
                {run.config.system_id: KillSwitchState()}
            ),
            journal=journal,
            clock=clock,
        )
        runner = HistoricalReplayRunner(
            paper_pipeline=pipeline,
            clock=clock,
            portfolio_provider=portfolio,
            position_lifecycle=lifecycle,
        )
        replay = await runner.run(candles=candles, run=run)
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
    "BacktestCapabilities",
    "BacktestDashboardError",
    "BacktestDashboardService",
    "CampaignRequest",
    "CampaignSummary",
    "DatasetInput",
    "DatasetPreview",
    "DeterministicBacktestMockProvider",
    "ExecutionInput",
    "MarketConstraintsInput",
    "RiskInput",
    "SplitInput",
    "WalkForwardInput",
    "get_backtest_dashboard_service",
]
