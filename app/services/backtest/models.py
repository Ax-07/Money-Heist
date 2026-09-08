from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from .dataset import DatasetRef
from .ids import stable_uuid


class BacktestAIMode(StrEnum):
    MOCK = "MOCK"
    CACHED = "CACHED"
    LIVE_EVAL = "LIVE_EVAL"


class IntrabarPolicy(StrEnum):
    STOP_FIRST = "STOP_FIRST"


class BacktestRunStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def _freeze_versions(values: Mapping[str, str], *, field_name: str) -> Mapping[str, str]:
    normalized: dict[str, str] = {}
    for key, value in values.items():
        key_text = str(key).strip()
        value_text = str(value).strip()
        if not key_text or not value_text:
            raise ValueError(f"{field_name} keys and values must not be empty")
        normalized[key_text] = value_text
    return MappingProxyType(dict(sorted(normalized.items())))


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _require_finite_non_negative(value: Decimal, *, field_name: str) -> None:
    if not value.is_finite() or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Immutable inputs that materially define one replay experiment."""

    system_id: str
    risk_version: str
    code_version: str = "batch16-v1"
    execution_model_version: str = "historical-ohlc-v1"
    random_seed: int = 0
    ai_mode: BacktestAIMode = BacktestAIMode.MOCK
    initial_balance: Decimal = Decimal("100")
    maker_fee_bps: Decimal = Decimal("10")
    taker_fee_bps: Decimal = Decimal("20")
    market_slippage_bps: Decimal = Decimal("5")
    intrabar_policy: IntrabarPolicy = IntrabarPolicy.STOP_FIRST
    feature_version: str = "feature-engine-v1"
    scanner_version: str = "scanner-v1"
    prompt_versions: Mapping[str, str] = field(default_factory=dict)
    model_versions: Mapping[str, str] = field(default_factory=dict)
    execution_assumptions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "system_id",
            "risk_version",
            "code_version",
            "execution_model_version",
            "feature_version",
            "scanner_version",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be empty")
        if isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int):
            raise ValueError("random_seed must be an integer")
        if self.random_seed < 0:
            raise ValueError("random_seed must be >= 0")
        if not self.initial_balance.is_finite() or self.initial_balance <= 0:
            raise ValueError("initial_balance must be finite and > 0")
        for field_name in ("maker_fee_bps", "taker_fee_bps", "market_slippage_bps"):
            _require_finite_non_negative(getattr(self, field_name), field_name=field_name)
        object.__setattr__(
            self,
            "prompt_versions",
            _freeze_versions(self.prompt_versions, field_name="prompt_versions"),
        )
        object.__setattr__(
            self,
            "model_versions",
            _freeze_versions(self.model_versions, field_name="model_versions"),
        )
        object.__setattr__(
            self,
            "execution_assumptions",
            _freeze_versions(self.execution_assumptions, field_name="execution_assumptions"),
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "system_id": self.system_id,
            "risk_version": self.risk_version,
            "code_version": self.code_version,
            "execution_model_version": self.execution_model_version,
            "random_seed": self.random_seed,
            "ai_mode": self.ai_mode,
            "initial_balance": self.initial_balance,
            "maker_fee_bps": self.maker_fee_bps,
            "taker_fee_bps": self.taker_fee_bps,
            "market_slippage_bps": self.market_slippage_bps,
            "intrabar_policy": self.intrabar_policy,
            "feature_version": self.feature_version,
            "scanner_version": self.scanner_version,
            "prompt_versions": self.prompt_versions,
            "model_versions": self.model_versions,
            "execution_assumptions": self.execution_assumptions,
        }


@dataclass(frozen=True, slots=True)
class BacktestRun:
    run_id: str
    dataset: DatasetRef
    config: BacktestConfig
    period_start: datetime
    period_end: datetime

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        start = _as_utc(self.period_start, field_name="period_start")
        end = _as_utc(self.period_end, field_name="period_end")
        if end < start:
            raise ValueError("period_end cannot precede period_start")
        if start < self.dataset.start_at or end > self.dataset.end_at:
            raise ValueError("backtest period must stay within dataset bounds")
        object.__setattr__(self, "period_start", start)
        object.__setattr__(self, "period_end", end)

    @classmethod
    def create(
        cls,
        *,
        dataset: DatasetRef,
        config: BacktestConfig,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> BacktestRun:
        start = _as_utc(period_start or dataset.start_at, field_name="period_start")
        end = _as_utc(period_end or dataset.end_at, field_name="period_end")
        if end < start:
            raise ValueError("period_end cannot precede period_start")
        payload = {
            "schema": "money-heist.backtest-run.v2",
            "dataset": dataset.canonical_payload(),
            "config": config.canonical_payload(),
            "period_start": start,
            "period_end": end,
        }
        return cls(
            run_id=stable_uuid("backtest-run", payload),
            dataset=dataset,
            config=config,
            period_start=start,
            period_end=end,
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "dataset": self.dataset.canonical_payload(),
            "config": self.config.canonical_payload(),
            "period_start": self.period_start,
            "period_end": self.period_end,
        }


@dataclass(frozen=True, slots=True)
class BacktestResult:
    run: BacktestRun
    status: BacktestRunStatus
    processed_candles: int = 0
    opportunity_count: int = 0
    executed_order_count: int = 0
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("processed_candles", "opportunity_count", "executed_order_count"):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be >= 0")
        if self.status is BacktestRunStatus.FAILED and not (self.failure_reason or "").strip():
            raise ValueError("FAILED backtest results require failure_reason")
        if self.status is BacktestRunStatus.COMPLETED and self.failure_reason is not None:
            raise ValueError("COMPLETED backtest results cannot carry failure_reason")
