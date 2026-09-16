from datetime import UTC, datetime
from decimal import Decimal

from app.analytics import AnalyticsComponentVersions, AnalyticsPeriodRole
from app.market.multitimeframe import HistoricalMultiTimeframeCursorState
from app.services.backtest.analytics_lab import (
    build_analytics_as_of_input,
    build_analytics_lab_run,
)
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.splits import BacktestPeriodRole


def _dataset() -> DatasetRef:
    return DatasetRef(
        dataset_id="BTC/USDC:1h:dataset",
        version="sha256:" + "a" * 64,
        content_sha256="a" * 64,
        symbol="BTC/USDC",
        timeframe="1h",
        source="historical-csv",
        candle_count=100,
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 1, 31, 23, tzinfo=UTC),
    )


def _backtest_run() -> BacktestRun:
    config = BacktestConfig(
        system_id="balanced_v1",
        risk_version="risk-v1",
        code_version="55a5333941ffc043b26b5e30f4b9fdafbd1cf8b0",
        initial_balance=Decimal("100"),
        execution_assumptions={
            "historical_source_timeframe": "1h",
            "decision_timeframe": "1h",
            "mtf_policy_version": "mtf-utc-closed-v1",
        },
    )
    return BacktestRun.create(dataset=_dataset(), config=config)


def _cursor_state(as_of: datetime) -> HistoricalMultiTimeframeCursorState:
    return HistoricalMultiTimeframeCursorState(
        symbol="BTC/USDC",
        source_timeframe="1h",
        source_candle_count=10,
        target_timeframes=("1h", "4h"),
        as_of=as_of,
        policy_version="mtf-utc-closed-v1",
        source_fingerprint="b" * 64,
        cursor_fingerprint="c" * 64,
        candle_counts=(("1h", 10), ("4h", 2)),
        latest_close_times=(("1h", as_of),),
    )


def test_analytics_identity_is_distinct_and_versions_do_not_change_backtest_run_id() -> None:
    source = _backtest_run()
    original_backtest_id = source.run_id
    original_config_payload = source.config.canonical_payload()

    a = build_analytics_lab_run(
        source,
        period_role=BacktestPeriodRole.OOS,
        component_versions=AnalyticsComponentVersions.foundation(
            analytics_bundle_version="analytics-v1"
        ),
    )
    b = build_analytics_lab_run(
        source,
        period_role=BacktestPeriodRole.OOS,
        component_versions=AnalyticsComponentVersions.foundation(
            analytics_bundle_version="analytics-v2"
        ),
    )

    assert source.run_id == original_backtest_id
    assert source.config.canonical_payload() == original_config_payload
    assert not any("analytics" in key.lower() for key in original_config_payload)
    assert a.source_backtest_run_id == source.run_id
    assert b.source_backtest_run_id == source.run_id
    assert a.analytics_run_id != b.analytics_run_id
    assert a.analytics_run_id != source.run_id
    assert a.period_role is AnalyticsPeriodRole.OOS


def test_as_of_adapter_preserves_dataset_cursor_and_mtf_provenance() -> None:
    source = _backtest_run()
    as_of = datetime(2026, 1, 10, 12, tzinfo=UTC)
    result = build_analytics_as_of_input(source, _cursor_state(as_of))

    assert result.source_backtest_run_id == source.run_id
    assert result.dataset_id == source.dataset.dataset_id
    assert result.dataset_content_sha256 == source.dataset.content_sha256
    assert result.as_of == as_of
    assert result.mtf_policy_version == "mtf-utc-closed-v1"
    assert result.source_cursor_fingerprint == "c" * 64
