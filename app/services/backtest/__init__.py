"""Batch 16 deterministic historical replay and validation toolkit."""

from .advanced_mock import (
    DeterministicAdvancedSpecialistMockProvider,
    MockProviderPort,
)
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
from .exports import (
    BacktestRunManifest,
    build_run_manifest,
    closed_trades_to_csv,
    equity_curve_to_csv,
    manifest_to_json,
    split_report_to_json,
    walk_forward_report_to_json,
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
from .reports import (
    BacktestMetricSnapshot,
    BacktestPeriodReport,
    BacktestSplitReport,
    WalkForwardReport,
)
from .reproducibility import (
    BacktestBusinessFingerprint,
    assert_reproducible,
    business_payload,
    fingerprint_backtest,
)
from .runner import HistoricalReplayPoint, HistoricalReplayResult, HistoricalReplayRunner
from .setup_stats import (
    CATALOG_SCHEMA,
    SETUP_DEFINITION_VERSION,
    DenverSetupStatsContextProvider,
    HistoricalSetupKey,
    HistoricalSetupObservation,
    HistoricalSetupStats,
    HistoricalSetupStatsCatalog,
    catalog_from_historical_runs,
    observations_from_historical_replay,
)
from .splits import BacktestPeriod, BacktestPeriodRole, BacktestRunSet, BacktestSplitPlan
from .walk_forward import (
    WalkForwardPlan,
    WalkForwardSplitExecutor,
    WalkForwardWindow,
    build_walk_forward_plan,
    execute_walk_forward,
)

__all__ = [
    "BacktestAIClient",
    "BacktestAIContext",
    "BacktestAIMode",
    "BacktestBusinessFingerprint",
    "BacktestCacheMissError",
    "BacktestConfig",
    "BacktestEvaluationBundle",
    "BacktestMetricSnapshot",
    "BacktestPeriod",
    "BacktestPeriodReport",
    "BacktestPeriodRole",
    "BacktestPortfolioStateProvider",
    "BacktestResponseCache",
    "BacktestResult",
    "BacktestRun",
    "BacktestRunManifest",
    "BacktestRunSet",
    "BacktestRunStatus",
    "BacktestSplitPlan",
    "BacktestSplitReport",
    "CATALOG_SCHEMA",
    "DatasetRef",
    "DeterministicAdvancedSpecialistMockProvider",
    "DenverSetupStatsContextProvider",
    "HistoricalExitEvent",
    "HistoricalExitReason",
    "HistoricalPositionLifecycle",
    "HistoricalReplayPoint",
    "HistoricalReplayResult",
    "HistoricalReplayRunner",
    "HistoricalSetupKey",
    "HistoricalSetupObservation",
    "HistoricalSetupStats",
    "HistoricalSetupStatsCatalog",
    "HistoricalTradeProtection",
    "IntrabarPolicy",
    "IntrabarResolution",
    "MockProviderPort",
    "ReplayClock",
    "ReplayIdFactory",
    "SETUP_DEFINITION_VERSION",
    "WalkForwardPlan",
    "WalkForwardReport",
    "WalkForwardSplitExecutor",
    "WalkForwardWindow",
    "as_utc",
    "assert_reproducible",
    "build_run_manifest",
    "build_walk_forward_plan",
    "business_payload",
    "canonical_candle_rows",
    "canonical_json",
    "catalog_from_historical_runs",
    "closed_trades_to_csv",
    "equity_curve_to_csv",
    "equity_points_from_replay",
    "evaluate_historical_replay",
    "execute_walk_forward",
    "final_marks_from_replay",
    "fingerprint_backtest",
    "manifest_to_json",
    "observations_from_historical_replay",
    "resolve_intrabar",
    "split_report_to_json",
    "stable_digest",
    "stable_uuid",
    "walk_forward_report_to_json",
]
