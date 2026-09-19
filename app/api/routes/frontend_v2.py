from __future__ import annotations

import asyncio
import contextlib
import csv
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.dashboard.backtest import (
    AgentTraceView,
    AIInput,
    BacktestDashboardError,
    BacktestDashboardService,
    BacktestPeriodRole,
    CampaignProgressView,
    CampaignRequest,
    CampaignSummary,
    DatasetInput,
    DatasetPreview,
    ExecutionInput,
    FrozenDenverPriorInput,
    HistoricalDerivativesInput,
    MarketConstraintsInput,
    RiskInput,
    SplitInput,
    WalkForwardInput,
    get_backtest_dashboard_service,
)
from app.market.exchange.kraken import (
    KRAKEN_INITIAL_SYMBOLS,
    KRAKEN_INTERVAL_MINUTES,
    KrakenAdapterConfig,
    KrakenPublicMarketDataProvider,
)
from app.market.exchange.transport import (
    ResilientPublicHttpClient,
    RetryPolicy,
    StdlibJsonTransport,
)
from app.market.historical import HistoricalImportError, import_candles_csv
from app.market.quality import FreshnessPolicy

BacktestService = Annotated[
    BacktestDashboardService,
    Depends(get_backtest_dashboard_service),
]

router = APIRouter(prefix="/api/frontend/v2", tags=["frontend-v2"])

_TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}
_TERMINAL_CAMPAIGN_STATES = {"COMPLETED", "FAILED", "CANCELLED"}
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

_DATASET_UPLOAD_DEFAULT_MAX_MB = 256
_CAMPAIGN_DATASET_MANIFEST_SCHEMA = "money-heist.campaign-prefix-datasets.v1"
_CAMPAIGN_DATASET_MANIFEST_ENV = "MONEY_HEIST_CAMPAIGN_DATASETS_MANIFEST"
_DEFAULT_CAMPAIGN_DATASET_MANIFEST = (
    _PROJECT_ROOT
    / "data"
    / "historical"
    / "binance_spot"
    / "campaign_datasets"
    / "campaign_datasets_manifest.json"
)
_DEFAULT_LOCAL_CAMPAIGN_SYMBOL = "BTC/USDC"


def _dataset_upload_max_bytes() -> int | None:
    raw = os.getenv(
        "MONEY_HEIST_DATASET_UPLOAD_MAX_MB",
        str(_DATASET_UPLOAD_DEFAULT_MAX_MB),
    ).strip()
    try:
        value = int(raw)
    except ValueError:
        value = _DATASET_UPLOAD_DEFAULT_MAX_MB
    if value <= 0:
        return None
    return value * 1024 * 1024


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]


class OpenAIModelCatalogEntry(FrozenModel):
    model_id: str
    display_name: str
    input_per_million_usd: str
    cached_input_per_million_usd: str
    output_per_million_usd: str
    reasoning_efforts: tuple[ReasoningEffort, ...]
    default_reasoning_effort: ReasoningEffort
    recommended: bool = False
    pricing_currency: Literal["USD"] = "USD"
    pricing_tier: Literal["STANDARD"] = "STANDARD"
    pricing_source: Literal["OPENAI_OFFICIAL"] = "OPENAI_OFFICIAL"
    pricing_snapshot_at: str = "2026-09-13"
    pricing_valid_until: str | None = None
    standard_context_max_tokens: int = 272_000
    source_url: str = "https://openai.com/api/pricing/"
    notes: tuple[str, ...] = ()


_OPENAI_MODEL_CATALOG = (
    OpenAIModelCatalogEntry(
        model_id="gpt-6-astra",
        display_name="GPT-6 Astra",
        input_per_million_usd="10.00",
        cached_input_per_million_usd="1.00",
        output_per_million_usd="50.00",
        reasoning_efforts=("low", "medium", "high", "xhigh", "max"),
        default_reasoning_effort="medium",
        notes=("Tarification Standard pour contexte inférieur à 272K tokens.",),
    ),
    OpenAIModelCatalogEntry(
        model_id="gpt-5.6-sol",
        display_name="GPT-5.6 Sol",
        input_per_million_usd="4.00",
        cached_input_per_million_usd="0.40",
        output_per_million_usd="20.00",
        reasoning_efforts=("none", "low", "medium", "high", "xhigh", "max"),
        default_reasoning_effort="medium",
        pricing_valid_until="2026-11-21",
        notes=(
            "Tarification promotionnelle OpenAI disponible au moins jusqu'au 21 novembre 2026.",
            "Tarification Standard pour contexte inférieur à 272K tokens.",
        ),
    ),
    OpenAIModelCatalogEntry(
        model_id="gpt-5.6-terra",
        display_name="GPT-5.6 Terra",
        input_per_million_usd="2.00",
        cached_input_per_million_usd="0.20",
        output_per_million_usd="12.00",
        reasoning_efforts=("none", "low", "medium", "high", "xhigh", "max"),
        default_reasoning_effort="medium",
        recommended=True,
        notes=("Tarification Standard pour contexte inférieur à 272K tokens.",),
    ),
    OpenAIModelCatalogEntry(
        model_id="gpt-5.6-luna",
        display_name="GPT-5.6 Luna",
        input_per_million_usd="0.20",
        cached_input_per_million_usd="0.02",
        output_per_million_usd="1.20",
        reasoning_efforts=("none", "low", "medium", "high", "xhigh", "max"),
        default_reasoning_effort="low",
        notes=("Tarification Standard pour contexte inférieur à 272K tokens.",),
    ),
)
_OPENAI_MODEL_BY_ID = {entry.model_id: entry for entry in _OPENAI_MODEL_CATALOG}


class OpenAIModelCatalogView(FrozenModel):
    schema_version: str = "money-heist.openai-model-catalog.v1"
    provider: Literal["openai"] = "openai"
    pricing_currency: Literal["USD"] = "USD"
    pricing_snapshot_at: str = "2026-09-13"
    models: tuple[OpenAIModelCatalogEntry, ...] = _OPENAI_MODEL_CATALOG


class FrontendAIInput(FrozenModel):
    mode: Literal["MOCK", "CACHED", "LIVE_EVAL"] = "MOCK"
    hard_budget_usd: Decimal = Decimal("1")
    model_id: str = "mock-backtest-v1"
    reasoning_effort: ReasoningEffort = "low"
    mock_agent_coverage: bool = False

    @model_validator(mode="after")
    def validate_frontend_ai(self) -> FrontendAIInput:
        if not self.hard_budget_usd.is_finite() or self.hard_budget_usd < 0:
            raise ValueError("hard_budget_usd must be finite and >= 0")
        if self.mode == "MOCK":
            if not self.model_id.startswith("mock-"):
                raise ValueError("MOCK mode requires a mock model_id")
            return self
        if self.mock_agent_coverage:
            raise ValueError("mock_agent_coverage is available only in MOCK mode")
        model = _OPENAI_MODEL_BY_ID.get(self.model_id)
        if model is None:
            raise ValueError("model_id is not in the verified OpenAI pricing catalog")
        if self.reasoning_effort not in model.reasoning_efforts:
            raise ValueError(
                f"reasoning_effort {self.reasoning_effort!r} is unsupported by {self.model_id}"
            )
        return self

    def to_legacy_ai_input(self) -> AIInput:
        # Compatibility bridge only: the core gateway still exposes historical *_eur
        # field names. Frontend V2 values are USD and no FX conversion is performed.
        if self.mode == "MOCK":
            return AIInput(
                mode=self.mode,
                hard_budget_eur=self.hard_budget_usd,
                model_id=self.model_id,
                reasoning_effort=self.reasoning_effort,
                input_per_million_eur=Decimal("0"),
                output_per_million_eur=Decimal("0"),
                cached_input_per_million_eur=None,
                mock_agent_coverage=self.mock_agent_coverage,
            )
        model = _OPENAI_MODEL_BY_ID[self.model_id]
        return AIInput(
            mode=self.mode,
            hard_budget_eur=self.hard_budget_usd,
            model_id=self.model_id,
            reasoning_effort=self.reasoning_effort,
            input_per_million_eur=Decimal(model.input_per_million_usd),
            output_per_million_eur=Decimal(model.output_per_million_usd),
            cached_input_per_million_eur=Decimal(model.cached_input_per_million_usd),
            mock_agent_coverage=False,
        )


class CampaignAIConfigurationView(FrozenModel):
    mode: str
    hard_budget: str
    model_id: str
    reasoning_effort: str
    input_per_million: str
    cached_input_per_million: str | None
    output_per_million: str
    currency: Literal["USD", "EUR"]
    pricing_source: str
    pricing_snapshot_at: str | None = None
    pricing_tier: str | None = None
    mock_agent_coverage: bool


class FrontendCapabilities(FrozenModel):
    schema_version: str = "money-heist.frontend-v2-capabilities.v1"
    runtime_mode: str
    app_env: str
    default_system_id: str
    market_symbols: tuple[str, ...]
    market_timeframes: tuple[str, ...]
    realtime_transport: Literal["POLLING"] = "POLLING"
    live_environment: str
    live_system_id: str | None
    live_timeframes: tuple[str, ...] | None
    live_operational_state: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    live_controls_exposed: bool = False
    chart_provider: Literal["LIGHTWEIGHT_CHARTS"] = "LIGHTWEIGHT_CHARTS"
    chart_data_source: Literal["BACKEND"] = "BACKEND"
    backtest_paper_only: bool = True


class CandleView(FrozenModel):
    time: int = Field(description="Unix seconds at candle close")
    open_time: str
    close_time: str
    open: str
    high: str
    low: str
    close: str
    volume: str
    is_closed: bool


class MarketCandlesView(FrozenModel):
    symbol: str
    timeframe: str
    source: str
    candles: tuple[CandleView, ...]


class MarketConstraintsView(FrozenModel):
    symbol: str
    source: str = "kraken_spot"
    tick_size: str
    qty_step: str
    min_qty: str
    min_notional: str
    max_leverage: str = "1"
    price_precision: int
    quantity_precision: int
    status: str


class ReplayTradeView(FrozenModel):
    trade_id: str
    system_id: str
    symbol: str
    side: str
    quantity: str
    entry_price: str
    exit_price: str
    opened_at: str
    closed_at: str
    net_pnl: str
    fees: str
    slippage_cost: str | None = None


class ReplayEquityView(FrozenModel):
    observed_at: str
    equity: str
    data_kind: str


class ReplayEventView(FrozenModel):
    event_id: str
    observed_at: str
    event_type: str
    label: str
    opportunity_id: str | None = None
    agent: str | None = None
    phase: str | None = None
    price: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class BacktestReplayView(FrozenModel):
    campaign_id: str
    role: BacktestPeriodRole
    symbol: str
    timeframe: str
    candles: tuple[CandleView, ...]
    events: tuple[ReplayEventView, ...]
    traces: tuple[AgentTraceView, ...]
    trades: tuple[ReplayTradeView, ...]
    equity: tuple[ReplayEquityView, ...]


class StoredCampaignRequest(FrozenModel):
    """Campaign configuration that references a persisted V2 dataset."""

    dataset_id: str = Field(min_length=1)
    split: SplitInput
    risk: RiskInput
    market: MarketConstraintsInput
    ai: FrontendAIInput = Field(default_factory=FrontendAIInput)
    execution: ExecutionInput = Field(default_factory=ExecutionInput)
    walk_forward: WalkForwardInput = Field(default_factory=WalkForwardInput)
    derivatives: HistoricalDerivativesInput | None = None
    denver_prior: FrozenDenverPriorInput | None = None
    system_id: str = "balanced_v1"

    def to_campaign_request(self, dataset: DatasetInput) -> CampaignRequest:
        return CampaignRequest(
            dataset=dataset,
            split=self.split,
            risk=self.risk,
            market=self.market,
            ai=self.ai.to_legacy_ai_input(),
            execution=self.execution,
            walk_forward=self.walk_forward,
            derivatives=self.derivatives,
            denver_prior=self.denver_prior,
            system_id=self.system_id,
        )


class DatasetCatalogView(FrozenModel):
    dataset_id: str
    content_sha256: str
    symbol: str
    timeframe: str
    source: str
    candle_count: int
    start_at: str
    end_at: str
    is_valid: bool
    gap_count: int

    @classmethod
    def from_preview(cls, preview: DatasetPreview) -> DatasetCatalogView:
        return cls(
            dataset_id=preview.dataset_id,
            content_sha256=preview.content_sha256,
            symbol=preview.symbol,
            timeframe=preview.timeframe,
            source=preview.source,
            candle_count=preview.candle_count,
            start_at=preview.start_at.isoformat(),
            end_at=preview.end_at.isoformat(),
            is_valid=preview.is_valid,
            gap_count=preview.gap_count,
        )



class LocalCampaignDatasetView(FrozenModel):
    duration_months: int = Field(ge=1)
    symbol: str
    timeframe: str
    rows: int = Field(ge=1)
    size_bytes: int = Field(ge=1)
    dataset_start_utc: str
    dataset_end_utc_inclusive: str
    dataset_end_utc_exclusive: str
    sha256: str
    storage: Literal["generated_prefix", "canonical_source_reference"]
    available: bool


@dataclass(frozen=True, slots=True)
class _LocalCampaignDatasetEntry:
    duration_months: int
    symbol: str
    timeframe: str
    rows: int
    size_bytes: int
    dataset_start_utc: str
    dataset_end_utc_inclusive: str
    dataset_end_utc_exclusive: str
    sha256: str
    storage: Literal["generated_prefix", "canonical_source_reference"]
    path: Path

    def to_view(self) -> LocalCampaignDatasetView:
        return LocalCampaignDatasetView(
            duration_months=self.duration_months,
            symbol=self.symbol,
            timeframe=self.timeframe,
            rows=self.rows,
            size_bytes=self.size_bytes,
            dataset_start_utc=self.dataset_start_utc,
            dataset_end_utc_inclusive=self.dataset_end_utc_inclusive,
            dataset_end_utc_exclusive=self.dataset_end_utc_exclusive,
            sha256=self.sha256,
            storage=self.storage,
            available=self.path.is_file(),
        )


def _campaign_dataset_manifest_path() -> Path:
    configured = os.getenv(_CAMPAIGN_DATASET_MANIFEST_ENV, "").strip()
    if not configured:
        return _DEFAULT_CAMPAIGN_DATASET_MANIFEST
    path = Path(configured)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return path.resolve()


def _manifest_basename(value: str) -> str:
    normalized = value.strip().replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1] if normalized else ""


def _load_local_campaign_dataset_entries() -> tuple[_LocalCampaignDatasetEntry, ...]:
    manifest_path = _campaign_dataset_manifest_path()
    if not manifest_path.is_file():
        return ()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("local campaign dataset manifest is unreadable") from exc
    if payload.get("schema") != _CAMPAIGN_DATASET_MANIFEST_SCHEMA:
        raise ValueError("unsupported local campaign dataset manifest schema")

    source = payload.get("source")
    datasets = payload.get("datasets")
    if not isinstance(source, dict) or not isinstance(datasets, list):
        raise ValueError("local campaign dataset manifest is incomplete")
    symbol = str(source.get("symbol") or _DEFAULT_LOCAL_CAMPAIGN_SYMBOL).strip().upper()
    timeframe = str(source.get("timeframe") or "").strip().lower()
    if not symbol or timeframe not in _TIMEFRAME_SECONDS:
        raise ValueError("local campaign dataset source identity is invalid")
    source_filename = _manifest_basename(str(source.get("path") or ""))
    if not source_filename:
        raise ValueError("local campaign dataset source path is invalid")

    entries: list[_LocalCampaignDatasetEntry] = []
    for raw in datasets:
        if not isinstance(raw, dict):
            raise ValueError("local campaign dataset entry must be an object")
        try:
            duration_months = int(raw["duration_months"])
            rows = int(raw["rows"])
            size_bytes = int(raw["size_bytes"])
            dataset_start_utc = str(raw["dataset_start_utc"])
            dataset_end_utc_inclusive = str(raw["dataset_end_utc_inclusive"])
            dataset_end_utc_exclusive = str(raw["dataset_end_utc_exclusive"])
            sha256 = str(raw["sha256"]).strip().lower()
            storage = str(raw["storage"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("local campaign dataset entry is incomplete") from exc
        if duration_months <= 0 or rows <= 0 or size_bytes <= 0:
            raise ValueError("local campaign dataset numeric metadata is invalid")
        if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
            raise ValueError("local campaign dataset sha256 is invalid")
        if storage == "generated_prefix":
            filename = _manifest_basename(str(raw.get("path") or ""))
            if not filename:
                raise ValueError("generated local campaign dataset path is invalid")
            dataset_path = manifest_path.parent / filename
        elif storage == "canonical_source_reference":
            dataset_path = manifest_path.parent.parent / "backtest_ready" / source_filename
        else:
            raise ValueError("unsupported local campaign dataset storage mode")
        entries.append(
            _LocalCampaignDatasetEntry(
                duration_months=duration_months,
                symbol=symbol,
                timeframe=timeframe,
                rows=rows,
                size_bytes=size_bytes,
                dataset_start_utc=dataset_start_utc,
                dataset_end_utc_inclusive=dataset_end_utc_inclusive,
                dataset_end_utc_exclusive=dataset_end_utc_exclusive,
                sha256=sha256,
                storage=storage,  # type: ignore[arg-type]
                path=dataset_path.resolve(),
            )
        )
    entries.sort(key=lambda item: item.duration_months)
    if len({item.duration_months for item in entries}) != len(entries):
        raise ValueError("local campaign dataset durations must be unique")
    return tuple(entries)


def _local_campaign_entries_or_503() -> tuple[_LocalCampaignDatasetEntry, ...]:
    try:
        return _load_local_campaign_dataset_entries()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class CampaignConfigurationView(FrozenModel):
    campaign_id: str
    dataset_id: str
    dataset: DatasetPreview
    split: SplitInput
    risk: RiskInput
    market: MarketConstraintsInput
    ai: CampaignAIConfigurationView
    execution: ExecutionInput
    walk_forward: WalkForwardInput
    system_id: str


@dataclass(slots=True)
class _FrontendCampaignRecord:
    request: CampaignRequest
    dataset_id: str
    frontend_ai: FrontendAIInput | None = None
    traces: dict[int, AgentTraceView] = field(default_factory=dict)
    watcher: asyncio.Task[None] | None = None
    persist_signature: tuple[Any, ...] | None = None


class FrontendV2Store:
    """Durable UI sidecar around the canonical Batch 16 service.

    The backend BacktestDashboardService remains the execution authority. This store only
    persists immutable V2 inputs and snapshots outputs/traces already emitted by that
    service. It never recalculates Scanner, agents, Risk, fills, positions, or metrics.
    """

    def __init__(self, *, limit: int = 50, storage_dir: Path | str | None = None) -> None:
        self._limit = limit
        configured = os.getenv("MONEY_HEIST_FRONTEND_V2_STORAGE_DIR", "").strip()
        root = (
            Path(storage_dir)
            if storage_dir is not None
            else (
                Path(configured) if configured else _PROJECT_ROOT / ".money-heist" / "frontend-v2"
            )
        )
        self._storage_dir = root.resolve()
        self._campaigns_dir = self._storage_dir / "campaigns"
        self._datasets_dir = self._storage_dir / "datasets"
        self._records: dict[str, _FrontendCampaignRecord] = {}
        self._order: list[str] = []
        for directory in (self._storage_dir, self._campaigns_dir, self._datasets_dir):
            directory.mkdir(parents=True, exist_ok=True)
            with contextlib.suppress(OSError):
                directory.chmod(0o700)

    @staticmethod
    def _atomic_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    @staticmethod
    def _atomic_text(path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, path)

    @staticmethod
    def _read_json(path: Path) -> Any | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _campaign_dir(self, campaign_id: str) -> Path:
        safe = campaign_id.strip()
        if not safe or Path(safe).name != safe:
            raise ValueError("invalid campaign_id")
        return self._campaigns_dir / safe

    def _dataset_dir(self, dataset_id: str) -> Path:
        value = dataset_id.strip()
        if not value:
            raise ValueError("invalid dataset_id")
        # Dataset ids intentionally contain symbols such as BTC/EUR. Never map them
        # directly to filesystem paths; use a deterministic opaque directory key.
        key = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return self._datasets_dir / key

    def save_dataset(self, dataset: DatasetInput, preview: DatasetPreview) -> None:
        directory = self._dataset_dir(preview.dataset_id)
        directory.mkdir(parents=True, exist_ok=True)
        payload = dataset.model_dump(mode="json")
        csv_text = str(payload.pop("csv_text"))
        self._atomic_text(directory / "dataset.csv", csv_text)
        self._atomic_json(directory / "input.json", payload)
        self._atomic_json(directory / "preview.json", preview.model_dump(mode="json"))

    def load_dataset(self, dataset_id: str) -> DatasetInput | None:
        directory = self._dataset_dir(dataset_id)
        payload = self._read_json(directory / "input.json")
        if payload is None:
            return None
        if "csv_text" not in payload:
            try:
                payload["csv_text"] = (directory / "dataset.csv").read_text(encoding="utf-8")
            except OSError:
                return None
        try:
            return DatasetInput.model_validate(payload)
        except ValueError:
            return None

    def get_dataset_preview(self, dataset_id: str) -> DatasetPreview | None:
        payload = self._read_json(self._dataset_dir(dataset_id) / "preview.json")
        if payload is None:
            return None
        try:
            return DatasetPreview.model_validate(payload)
        except ValueError:
            return None

    def list_datasets(self) -> tuple[DatasetPreview, ...]:
        previews: list[DatasetPreview] = []
        for path in self._datasets_dir.iterdir():
            if not path.is_dir():
                continue
            payload = self._read_json(path / "preview.json")
            if payload is None:
                continue
            try:
                preview = DatasetPreview.model_validate(payload)
            except ValueError:
                continue
            previews.append(preview)
        previews.sort(key=lambda value: value.start_at, reverse=True)
        return tuple(previews)

    def remember(
        self,
        campaign_id: str,
        request: CampaignRequest,
        *,
        dataset_id: str,
        frontend_ai: FrontendAIInput | None = None,
    ) -> _FrontendCampaignRecord:
        record = _FrontendCampaignRecord(
            request=request,
            dataset_id=dataset_id,
            frontend_ai=frontend_ai,
        )
        self._records[campaign_id] = record
        if campaign_id in self._order:
            self._order.remove(campaign_id)
        self._order.append(campaign_id)
        directory = self._campaign_dir(campaign_id)
        directory.mkdir(parents=True, exist_ok=True)
        request_payload = request.model_dump(mode="json")
        request_payload.pop("dataset", None)
        self._atomic_json(
            directory / "request.json",
            {
                "dataset_id": dataset_id,
                "config": request_payload,
                "frontend_ai": (
                    None if frontend_ai is None else frontend_ai.model_dump(mode="json")
                ),
            },
        )
        self._trim_memory()
        return record

    def _trim_memory(self) -> None:
        while len(self._order) > self._limit:
            removed = self._order.pop(0)
            old = self._records.pop(removed, None)
            if old is not None and old.watcher is not None and not old.watcher.done():
                old.watcher.cancel()

    def get(self, campaign_id: str) -> _FrontendCampaignRecord | None:
        existing = self._records.get(campaign_id)
        if existing is not None:
            return existing
        payload = self._read_json(self._campaign_dir(campaign_id) / "request.json")
        if not isinstance(payload, dict):
            return None
        try:
            dataset_id = str(payload["dataset_id"])
            frontend_ai_payload = payload.get("frontend_ai")
            frontend_ai = (
                None
                if frontend_ai_payload is None
                else FrontendAIInput.model_validate(frontend_ai_payload)
            )
            if "request" in payload:  # Batch 22 compatibility
                request = CampaignRequest.model_validate(payload["request"])
            else:
                dataset = self.load_dataset(dataset_id)
                if dataset is None:
                    return None
                config = dict(payload["config"])
                request = CampaignRequest(dataset=dataset, **config)
        except (KeyError, TypeError, ValueError):
            return None
        record = _FrontendCampaignRecord(
            request=request,
            dataset_id=dataset_id,
            frontend_ai=frontend_ai,
        )
        traces_payload = self._read_json(self._campaign_dir(campaign_id) / "traces.json")
        if isinstance(traces_payload, list):
            for item in traces_payload:
                try:
                    trace = AgentTraceView.model_validate(item)
                except ValueError:
                    continue
                record.traces[trace.sequence] = trace
        self._records[campaign_id] = record
        self._order.append(campaign_id)
        self._trim_memory()
        return record

    def persist_progress(self, progress: CampaignProgressView) -> None:
        self._atomic_json(
            self._campaign_dir(progress.campaign_id) / "progress.json",
            progress.model_dump(mode="json"),
        )

    def persisted_progress(self, campaign_id: str) -> CampaignProgressView | None:
        payload = self._read_json(self._campaign_dir(campaign_id) / "progress.json")
        if payload is None:
            return None
        try:
            return CampaignProgressView.model_validate(payload)
        except ValueError:
            return None

    def persist_summary(self, summary: CampaignSummary) -> None:
        self._atomic_json(
            self._campaign_dir(summary.campaign_id) / "summary.json",
            summary.model_dump(mode="json"),
        )

    def persisted_summary(self, campaign_id: str) -> CampaignSummary | None:
        payload = self._read_json(self._campaign_dir(campaign_id) / "summary.json")
        if payload is None:
            return None
        try:
            return CampaignSummary.model_validate(payload)
        except ValueError:
            return None

    def list_summaries(self) -> tuple[CampaignSummary, ...]:
        summaries: list[CampaignSummary] = []
        for path in self._campaigns_dir.iterdir():
            if not path.is_dir():
                continue
            summary = self.persisted_summary(path.name)
            if summary is not None:
                summaries.append(summary)
        summaries.sort(key=lambda value: value.created_at, reverse=True)
        return tuple(summaries)

    def persist_traces(self, campaign_id: str) -> None:
        record = self._records.get(campaign_id)
        if record is None:
            return
        ordered = [trace.model_dump(mode="json") for _, trace in sorted(record.traces.items())]
        self._atomic_json(self._campaign_dir(campaign_id) / "traces.json", ordered)

    def persist_export(self, campaign_id: str, name: str, payload: str) -> None:
        if Path(name).name != name:
            return
        directory = self._campaign_dir(campaign_id) / "exports"
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f".{name}.tmp"
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, directory / name)

    def persisted_export(self, campaign_id: str, name: str) -> str | None:
        if Path(name).name != name:
            return None
        try:
            return (self._campaign_dir(campaign_id) / "exports" / name).read_text(encoding="utf-8")
        except OSError:
            return None

    def snapshot_terminal(
        self,
        service: BacktestDashboardService,
        campaign_id: str,
    ) -> None:
        self.persist_traces(campaign_id)
        summary = service.get_campaign(campaign_id)
        if summary is None:
            return
        self.persist_summary(summary)
        for name in summary.exports:
            exported = service.get_export(campaign_id, name)
            if exported is None:
                continue
            self.persist_export(campaign_id, name, exported[1])

    async def watch(self, service: BacktestDashboardService, campaign_id: str) -> None:
        record = self._records.get(campaign_id)
        if record is None:
            return
        try:
            while True:
                progress = service.get_campaign_progress(campaign_id)
                if progress is None:
                    return
                for trace in progress.agent_traces:
                    record.traces[trace.sequence] = trace
                signature = (
                    progress.status,
                    progress.phase,
                    progress.work_done,
                    progress.opportunity_count,
                    progress.executed_order_count,
                    len(record.traces),
                )
                if signature != record.persist_signature:
                    self.persist_progress(progress)
                    self.persist_traces(campaign_id)
                    record.persist_signature = signature
                if progress.status in _TERMINAL_CAMPAIGN_STATES:
                    self.snapshot_terminal(service, campaign_id)
                    return
                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            raise


def _frontend_store(request: Request) -> FrontendV2Store:
    store = getattr(request.app.state, "frontend_v2_store", None)
    if store is None:
        store = FrontendV2Store()
        request.app.state.frontend_v2_store = store
    return store


FrontendStore = Annotated[FrontendV2Store, Depends(_frontend_store)]


def _runtime_mode(value: Any) -> str:
    return str(getattr(value, "value", value))


def _campaign_ai_configuration(record: _FrontendCampaignRecord) -> CampaignAIConfigurationView:
    if record.frontend_ai is not None:
        ai = record.frontend_ai
        if ai.mode == "MOCK":
            return CampaignAIConfigurationView(
                mode=ai.mode,
                hard_budget=str(ai.hard_budget_usd),
                model_id=ai.model_id,
                reasoning_effort=ai.reasoning_effort,
                input_per_million="0",
                cached_input_per_million=None,
                output_per_million="0",
                currency="USD",
                pricing_source="MOCK",
                mock_agent_coverage=ai.mock_agent_coverage,
            )
        model = _OPENAI_MODEL_BY_ID[ai.model_id]
        return CampaignAIConfigurationView(
            mode=ai.mode,
            hard_budget=str(ai.hard_budget_usd),
            model_id=ai.model_id,
            reasoning_effort=ai.reasoning_effort,
            input_per_million=model.input_per_million_usd,
            cached_input_per_million=model.cached_input_per_million_usd,
            output_per_million=model.output_per_million_usd,
            currency="USD",
            pricing_source=model.pricing_source,
            pricing_snapshot_at=model.pricing_snapshot_at,
            pricing_tier=model.pricing_tier,
            mock_agent_coverage=False,
        )
    ai = record.request.ai
    return CampaignAIConfigurationView(
        mode=str(getattr(ai.mode, "value", ai.mode)),
        hard_budget=str(ai.hard_budget_eur),
        model_id=ai.model_id,
        reasoning_effort=ai.reasoning_effort,
        input_per_million=str(ai.input_per_million_eur),
        cached_input_per_million=(
            None
            if ai.cached_input_per_million_eur is None
            else str(ai.cached_input_per_million_eur)
        ),
        output_per_million=str(ai.output_per_million_eur),
        currency="EUR",
        pricing_source="LEGACY_MANUAL",
        mock_agent_coverage=ai.mock_agent_coverage,
    )


@router.get("/capabilities", response_model=FrontendCapabilities)
def frontend_capabilities(request: Request) -> FrontendCapabilities:
    settings = request.app.state.settings
    return FrontendCapabilities(
        runtime_mode=_runtime_mode(settings.runtime_mode),
        app_env=settings.app_env,
        default_system_id=settings.default_system_id,
        market_symbols=tuple(KRAKEN_INITIAL_SYMBOLS),
        market_timeframes=tuple(KRAKEN_INTERVAL_MINUTES),
        live_environment=settings.live_environment,
        live_system_id=settings.live_system_id,
        live_timeframes=settings.live_timeframe_values,
    )


@router.get("/ai/openai/models", response_model=OpenAIModelCatalogView)
def openai_model_catalog() -> OpenAIModelCatalogView:
    return OpenAIModelCatalogView()


def _kraken_market_provider(timeframe: str) -> KrakenPublicMarketDataProvider:
    interval_seconds = _TIMEFRAME_SECONDS.get(timeframe, 3600)
    max_age = timedelta(seconds=max(interval_seconds * 3, 300))
    return KrakenPublicMarketDataProvider(
        ResilientPublicHttpClient(
            StdlibJsonTransport(user_agent="money-heist-frontend-v2/1"),
            policy=RetryPolicy(
                timeout_seconds=5,
                max_attempts=2,
                base_backoff_seconds=0.2,
                max_backoff_seconds=1.0,
                min_request_interval_seconds=0.15,
            ),
        ),
        config=KrakenAdapterConfig(
            freshness_policy=FreshnessPolicy(max_age=max_age),
            snapshot_timeframes=(timeframe,),
            metadata_max_age=timedelta(hours=1),
        ),
    )


def _candle_view(candle: Any) -> CandleView:
    return CandleView(
        time=int(candle.close_time.timestamp()),
        open_time=candle.open_time.isoformat(),
        close_time=candle.close_time.isoformat(),
        open=str(candle.open),
        high=str(candle.high),
        low=str(candle.low),
        close=str(candle.close),
        volume=str(candle.volume),
        is_closed=bool(candle.is_closed),
    )


@router.get("/market/candles", response_model=MarketCandlesView)
async def market_candles(
    symbol: str = Query(default="BTC/EUR"),
    timeframe: str = Query(default="1h"),
    limit: int = Query(default=500, ge=25, le=720),
) -> MarketCandlesView:
    symbol = symbol.strip().upper()
    if symbol not in KRAKEN_INITIAL_SYMBOLS:
        raise HTTPException(status_code=422, detail="symbol is not in the Kraken V1 universe")
    if timeframe not in KRAKEN_INTERVAL_MINUTES:
        raise HTTPException(status_code=422, detail="unsupported Kraken timeframe")
    try:
        candles = await _kraken_market_provider(timeframe).get_candles(symbol, timeframe, limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"market_data_unavailable: {exc}") from exc
    return MarketCandlesView(
        symbol=symbol,
        timeframe=timeframe,
        source="kraken_spot",
        candles=tuple(_candle_view(candle) for candle in candles),
    )


@router.get("/market/constraints", response_model=MarketConstraintsView)
async def market_constraints(symbol: str = Query(default="BTC/EUR")) -> MarketConstraintsView:
    symbol = symbol.strip().upper()
    if symbol not in KRAKEN_INITIAL_SYMBOLS:
        raise HTTPException(status_code=422, detail="symbol is not in the Kraken V1 universe")
    try:
        metadata = await _kraken_market_provider("1h").refresh_symbol_metadata(symbol)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"market_constraints_unavailable: {exc}"
        ) from exc
    return MarketConstraintsView(
        symbol=symbol,
        tick_size=str(metadata.tick_size),
        qty_step=str(metadata.qty_step),
        min_qty=str(metadata.min_qty),
        min_notional=str(metadata.min_notional),
        price_precision=metadata.price_precision,
        quantity_precision=metadata.quantity_precision,
        status=metadata.status,
    )


@router.get(
    "/backtests/local-campaign-datasets",
    response_model=tuple[LocalCampaignDatasetView, ...],
)
def list_local_campaign_datasets() -> tuple[LocalCampaignDatasetView, ...]:
    return tuple(entry.to_view() for entry in _local_campaign_entries_or_503())


@router.post(
    "/backtests/local-campaign-datasets/{duration_months}/import",
    response_model=DatasetPreview,
    status_code=201,
)
def import_local_campaign_dataset(
    duration_months: int,
    service: BacktestService,
    store: FrontendStore,
) -> DatasetPreview:
    entries = _local_campaign_entries_or_503()
    entry = next(
        (item for item in entries if item.duration_months == duration_months),
        None,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown local campaign dataset duration")
    try:
        raw = entry.path.read_bytes()
    except OSError as exc:
        raise HTTPException(
            status_code=404, detail="Local campaign dataset file is missing"
        ) from exc
    if len(raw) != entry.size_bytes:
        raise HTTPException(
            status_code=409,
            detail="Local campaign dataset size does not match its manifest",
        )
    if _sha256_bytes(raw) != entry.sha256:
        raise HTTPException(
            status_code=409,
            detail="Local campaign dataset SHA-256 does not match its manifest",
        )
    try:
        csv_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="local campaign dataset must be UTF-8") from exc

    payload = DatasetInput(
        csv_text=csv_text,
        symbol=entry.symbol,
        timeframe=entry.timeframe,
        source=f"local_campaign_prefix:{entry.duration_months}m:{entry.sha256[:16]}",
        candle_interval_seconds=_TIMEFRAME_SECONDS[entry.timeframe],
    )
    try:
        preview = service.preview_dataset(payload)
    except (BacktestDashboardError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not preview.is_valid:
        raise HTTPException(status_code=422, detail="local campaign dataset preview is not valid")
    if preview.candle_count != entry.rows:
        raise HTTPException(
            status_code=409,
            detail="Local campaign dataset row count does not match its manifest",
        )
    if preview.start_at.date().isoformat() != entry.dataset_start_utc:
        raise HTTPException(
            status_code=409,
            detail="Local campaign dataset start does not match its manifest",
        )
    if preview.end_at.date().isoformat() != entry.dataset_end_utc_exclusive:
        raise HTTPException(
            status_code=409,
            detail="Local campaign dataset end does not match its manifest",
        )
    store.save_dataset(payload, preview)
    return preview


@router.get("/backtests/datasets", response_model=tuple[DatasetCatalogView, ...])
def list_backtest_datasets(store: FrontendStore) -> tuple[DatasetCatalogView, ...]:
    return tuple(DatasetCatalogView.from_preview(value) for value in store.list_datasets())


@router.get("/backtests/dataset", response_model=DatasetPreview)
def get_backtest_dataset(
    store: FrontendStore,
    dataset_id: str = Query(min_length=1),
) -> DatasetPreview:
    preview = store.get_dataset_preview(dataset_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="Unknown persisted dataset_id")
    return preview


@router.post("/backtests/datasets/upload", response_model=DatasetPreview, status_code=201)
async def upload_backtest_dataset(
    request: Request,
    service: BacktestService,
    store: FrontendStore,
    symbol: str = Query(min_length=1),
    timeframe: str = Query(min_length=1),
    source: str = Query(default="frontend_v2:upload.csv", min_length=1),
    candle_interval_seconds: int | None = Query(default=None, ge=1),
) -> DatasetPreview:
    max_bytes = _dataset_upload_max_bytes()
    content_length = request.headers.get("content-length")
    if max_bytes is not None and content_length is not None:
        with contextlib.suppress(ValueError):
            if int(content_length) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"dataset upload exceeds configured limit ({max_bytes // 1024 // 1024} MiB)"
                    ),
                )

    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if max_bytes is not None and len(raw) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"dataset upload exceeds configured limit ({max_bytes // 1024 // 1024} MiB)"
                ),
            )
    try:
        csv_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="dataset CSV must be UTF-8") from exc
    if not csv_text.strip():
        raise HTTPException(status_code=422, detail="dataset CSV is empty")

    payload = DatasetInput(
        csv_text=csv_text,
        symbol=symbol,
        timeframe=timeframe,
        source=source,
        candle_interval_seconds=candle_interval_seconds,
    )
    try:
        preview = service.preview_dataset(payload)
    except (BacktestDashboardError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not preview.is_valid:
        raise HTTPException(status_code=422, detail="dataset preview is not valid")
    store.save_dataset(payload, preview)
    return preview


@router.post("/backtests/datasets", response_model=DatasetPreview, status_code=201)
def save_backtest_dataset(
    payload: DatasetInput,
    service: BacktestService,
    store: FrontendStore,
) -> DatasetPreview:
    try:
        preview = service.preview_dataset(payload)
    except (BacktestDashboardError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not preview.is_valid:
        raise HTTPException(status_code=422, detail="dataset preview is not valid")
    store.save_dataset(payload, preview)
    return preview


async def _launch_campaign(
    payload: CampaignRequest,
    service: BacktestDashboardService,
    store: FrontendV2Store,
    *,
    frontend_ai: FrontendAIInput | None = None,
) -> CampaignProgressView:
    try:
        preview = service.preview_dataset(payload.dataset)
        if not preview.is_valid:
            raise BacktestDashboardError("dataset preview is not valid")
        store.save_dataset(payload.dataset, preview)
        progress = await service.start_campaign(payload)
    except (BacktestDashboardError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record = store.remember(
        progress.campaign_id,
        payload,
        dataset_id=preview.dataset_id,
        frontend_ai=frontend_ai,
    )
    store.persist_progress(progress)
    record.watcher = asyncio.create_task(
        store.watch(service, progress.campaign_id),
        name=f"frontend-v2-trace-capture-{progress.campaign_id}",
    )
    return progress


@router.post("/backtests/runs", response_model=CampaignProgressView, status_code=202)
async def start_backtest_v2(
    payload: CampaignRequest,
    service: BacktestService,
    store: FrontendStore,
) -> CampaignProgressView:
    return await _launch_campaign(payload, service, store)


@router.post(
    "/backtests/runs/from-dataset",
    response_model=CampaignProgressView,
    status_code=202,
)
async def start_backtest_from_dataset(
    payload: StoredCampaignRequest,
    service: BacktestService,
    store: FrontendStore,
) -> CampaignProgressView:
    dataset = store.load_dataset(payload.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Unknown persisted dataset_id")
    return await _launch_campaign(
        payload.to_campaign_request(dataset),
        service,
        store,
        frontend_ai=payload.ai,
    )


@router.get("/backtests/runs", response_model=tuple[CampaignSummary, ...])
def list_backtest_runs(
    service: BacktestService,
    store: FrontendStore,
) -> tuple[CampaignSummary, ...]:
    merged: dict[str, CampaignSummary] = {
        summary.campaign_id: summary for summary in store.list_summaries()
    }
    for summary in service.list_campaigns():
        merged[summary.campaign_id] = summary
    return tuple(sorted(merged.values(), key=lambda value: value.created_at, reverse=True))


@router.get("/backtests/runs/{campaign_id}", response_model=CampaignSummary)
def get_backtest_run(
    campaign_id: str,
    service: BacktestService,
    store: FrontendStore,
) -> CampaignSummary:
    summary = service.get_campaign(campaign_id) or store.persisted_summary(campaign_id)
    if summary is None:
        progress = service.get_campaign_progress(campaign_id) or store.persisted_progress(
            campaign_id
        )
        if progress is None:
            raise HTTPException(status_code=404, detail="Unknown backtest campaign_id")
        raise HTTPException(status_code=409, detail=f"campaign status is {progress.status}")
    return summary


@router.get("/backtests/runs/{campaign_id}/progress", response_model=CampaignProgressView)
def get_backtest_run_progress(
    campaign_id: str,
    service: BacktestService,
    store: FrontendStore,
) -> CampaignProgressView:
    progress = service.get_campaign_progress(campaign_id) or store.persisted_progress(campaign_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Unknown backtest campaign_id")
    return progress


@router.post(
    "/backtests/runs/{campaign_id}/cancel",
    response_model=CampaignProgressView,
)
def cancel_backtest_run(
    campaign_id: str,
    service: BacktestService,
    store: FrontendStore,
) -> CampaignProgressView:
    progress = service.cancel_campaign(campaign_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Unknown backtest campaign_id")
    store.persist_progress(progress)
    return progress


@router.get(
    "/backtests/runs/{campaign_id}/configuration",
    response_model=CampaignConfigurationView,
)
def get_backtest_configuration(
    campaign_id: str,
    service: BacktestService,
    store: FrontendStore,
) -> CampaignConfigurationView:
    record = store.get(campaign_id)
    if record is None:
        raise HTTPException(status_code=404, detail="V2 campaign configuration unavailable")
    preview = store.get_dataset_preview(record.dataset_id)
    if preview is None:
        preview = service.preview_dataset(record.request.dataset)
        store.save_dataset(record.request.dataset, preview)
    return CampaignConfigurationView(
        campaign_id=campaign_id,
        dataset_id=record.dataset_id,
        dataset=preview,
        split=record.request.split,
        risk=record.request.risk,
        market=record.request.market,
        ai=_campaign_ai_configuration(record),
        execution=record.request.execution,
        walk_forward=record.request.walk_forward,
        system_id=record.request.system_id,
    )


def _dataset_interval_seconds(dataset: DatasetInput) -> int:
    if dataset.candle_interval_seconds is not None:
        return dataset.candle_interval_seconds
    interval = _TIMEFRAME_SECONDS.get(dataset.timeframe)
    if interval is None:
        raise HTTPException(
            status_code=409,
            detail="replay unavailable: unknown timeframe and no explicit candle interval",
        )
    return interval


def _parse_replay_candles(dataset: DatasetInput) -> tuple[Any, ...]:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            delete=False,
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            handle.write(dataset.csv_text)
            temp_path = Path(handle.name)
        imported = import_candles_csv(
            temp_path,
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            source=dataset.source,
            candle_interval=timedelta(seconds=_dataset_interval_seconds(dataset)),
        )
        return tuple(imported.candles)
    except HistoricalImportError as exc:
        raise HTTPException(status_code=409, detail=f"replay dataset unavailable: {exc}") from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _role_bounds(request: CampaignRequest, role: BacktestPeriodRole) -> tuple[Any, Any]:
    split = request.split
    if role is BacktestPeriodRole.DESIGN:
        return split.design_start, split.design_end
    if role is BacktestPeriodRole.VALIDATION:
        return split.validation_start, split.validation_end
    return split.oos_start, split.oos_end


def _parse_closed_trades(payload: str) -> tuple[ReplayTradeView, ...]:
    rows = csv.DictReader(payload.splitlines())
    return tuple(
        ReplayTradeView(
            trade_id=row["trade_id"],
            system_id=row["system_id"],
            symbol=row["symbol"],
            side=row["side"],
            quantity=row["quantity"],
            entry_price=row["entry_price"],
            exit_price=row["exit_price"],
            opened_at=row["opened_at"],
            closed_at=row["closed_at"],
            net_pnl=row["net_pnl"],
            fees=row["fees"],
            slippage_cost=row.get("slippage_cost") or None,
        )
        for row in rows
    )


def _parse_equity(payload: str) -> tuple[ReplayEquityView, ...]:
    rows = csv.DictReader(payload.splitlines())
    return tuple(
        ReplayEquityView(
            observed_at=row["observed_at"],
            equity=row["equity"],
            data_kind=row["data_kind"],
        )
        for row in rows
    )


def _trace_events(traces: tuple[AgentTraceView, ...]) -> list[ReplayEventView]:
    events: list[ReplayEventView] = []
    first_by_opportunity: dict[str, AgentTraceView] = {}
    for trace in traces:
        if trace.opportunity_id and trace.opportunity_id not in first_by_opportunity:
            first_by_opportunity[trace.opportunity_id] = trace
    for opportunity_id, trace in first_by_opportunity.items():
        events.append(
            ReplayEventView(
                event_id=f"opportunity:{opportunity_id}",
                observed_at=trace.observed_at.isoformat(),
                event_type="OPPORTUNITY",
                label="CandidateOpportunity",
                opportunity_id=opportunity_id,
                details={"role": trace.role.value},
            )
        )
    for trace in traces:
        events.append(
            ReplayEventView(
                event_id=f"trace:{trace.sequence}",
                observed_at=trace.observed_at.isoformat(),
                event_type=trace.phase,
                label=trace.title,
                opportunity_id=trace.opportunity_id or None,
                agent=trace.agent,
                phase=trace.phase,
                details=trace.details,
            )
        )
    return events


def _trade_events(trades: tuple[ReplayTradeView, ...]) -> list[ReplayEventView]:
    events: list[ReplayEventView] = []
    for trade in trades:
        events.extend(
            (
                ReplayEventView(
                    event_id=f"trade:{trade.trade_id}:entry",
                    observed_at=trade.opened_at,
                    event_type="ENTRY",
                    label=f"{trade.side} entry",
                    price=trade.entry_price,
                    details={"trade_id": trade.trade_id, "quantity": trade.quantity},
                ),
                ReplayEventView(
                    event_id=f"trade:{trade.trade_id}:exit",
                    observed_at=trade.closed_at,
                    event_type="EXIT",
                    label=f"Exit · PnL {trade.net_pnl}",
                    price=trade.exit_price,
                    details={
                        "trade_id": trade.trade_id,
                        "net_pnl": trade.net_pnl,
                        "fees": trade.fees,
                    },
                ),
            )
        )
    return events


def _export_payload(
    service: BacktestDashboardService,
    store: FrontendV2Store,
    campaign_id: str,
    name: str,
) -> str | None:
    exported = service.get_export(campaign_id, name)
    if exported is not None:
        return exported[1]
    return store.persisted_export(campaign_id, name)


@router.get("/backtests/runs/{campaign_id}/replay", response_model=BacktestReplayView)
def backtest_replay(
    campaign_id: str,
    service: BacktestService,
    store: FrontendStore,
    role: BacktestPeriodRole = BacktestPeriodRole.OOS,
) -> BacktestReplayView:
    record = store.get(campaign_id)
    if record is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Replay dataset unavailable for this campaign. Launch campaigns through "
                "/api/frontend/v2/backtests/runs so Frontend V2 can persist the immutable input."
            ),
        )
    summary = service.get_campaign(campaign_id) or store.persisted_summary(campaign_id)
    if summary is None:
        progress = service.get_campaign_progress(campaign_id) or store.persisted_progress(
            campaign_id
        )
        if progress is None:
            raise HTTPException(status_code=404, detail="Unknown backtest campaign_id")
        raise HTTPException(status_code=409, detail=f"campaign status is {progress.status}")

    start, end = _role_bounds(record.request, role)
    raw_candles = _parse_replay_candles(record.request.dataset)
    candles = tuple(
        _candle_view(candle) for candle in raw_candles if start <= candle.close_time <= end
    )
    traces = tuple(trace for _, trace in sorted(record.traces.items()) if trace.role is role)
    prefix = role.value.lower()
    trade_payload = _export_payload(service, store, campaign_id, f"{prefix}-closed-trades.csv")
    equity_payload = _export_payload(service, store, campaign_id, f"{prefix}-equity.csv")
    trades = () if trade_payload is None else _parse_closed_trades(trade_payload)
    equity = () if equity_payload is None else _parse_equity(equity_payload)
    events = _trace_events(traces)
    events.extend(_trade_events(trades))
    events.sort(key=lambda event: (event.observed_at, event.event_id))

    return BacktestReplayView(
        campaign_id=campaign_id,
        role=role,
        symbol=record.request.dataset.symbol,
        timeframe=record.request.dataset.timeframe,
        candles=candles,
        events=tuple(events),
        traces=traces,
        trades=trades,
        equity=equity,
    )


__all__ = ["router", "FrontendV2Store"]
