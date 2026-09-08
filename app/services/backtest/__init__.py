"""Batch 16 deterministic historical replay foundations."""

from .ai_modes import BacktestAIClient
from .cache import BacktestAIContext, BacktestCacheMissError, BacktestResponseCache
from .clock import ReplayClock, as_utc
from .dataset import DatasetRef, canonical_candle_rows
from .evaluation import (
    BacktestEvaluationBundle,
    equity_points_from_replay,
    evaluate_historical_replay,
    final_marks_from_replay,
)
from .ids import ReplayIdFactory, canonical_json, stable_digest, stable_uuid
from .intrabar import HistoricalExitReason, IntrabarResolution, resolve_intrabar
from .lifecycle import (
    HistoricalExitEvent,
    HistoricalPositionLifecycle,
    HistoricalTradeProtection,
)
from .models import (
    BacktestAIMode,
    BacktestConfig,
    BacktestResult,
    BacktestRun,
    BacktestRunStatus,
    IntrabarPolicy,
)
from .portfolio import BacktestPortfolioStateProvider
from .reproducibility import (
    BacktestBusinessFingerprint,
    assert_reproducible,
    business_payload,
    fingerprint_backtest,
)
from .runner import HistoricalReplayPoint, HistoricalReplayResult, HistoricalReplayRunner

__all__ = [
    "BacktestAIClient",
    "BacktestAIContext",
    "BacktestAIMode",
    "BacktestBusinessFingerprint",
    "BacktestCacheMissError",
    "BacktestConfig",
    "BacktestEvaluationBundle",
    "BacktestPortfolioStateProvider",
    "BacktestResponseCache",
    "BacktestResult",
    "BacktestRun",
    "BacktestRunStatus",
    "DatasetRef",
    "HistoricalExitEvent",
    "HistoricalExitReason",
    "HistoricalPositionLifecycle",
    "HistoricalReplayPoint",
    "HistoricalReplayResult",
    "HistoricalReplayRunner",
    "HistoricalTradeProtection",
    "IntrabarPolicy",
    "IntrabarResolution",
    "ReplayClock",
    "ReplayIdFactory",
    "as_utc",
    "assert_reproducible",
    "business_payload",
    "canonical_candle_rows",
    "canonical_json",
    "equity_points_from_replay",
    "evaluate_historical_replay",
    "final_marks_from_replay",
    "fingerprint_backtest",
    "resolve_intrabar",
    "stable_digest",
    "stable_uuid",
]
