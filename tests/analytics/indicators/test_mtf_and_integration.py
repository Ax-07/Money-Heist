from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics import AnalyticsAsOfInput, AnalyticsLabRun, AnalyticsPeriodRole
from app.analytics.indicators import (
    ANALYTICS_INDICATOR_REGISTRY_IDENTITY,
    AnalyticsIndicatorEngine,
    build_analytics_snapshot_with_indicators,
    indicator_component_versions,
)
from app.market.models import Candle
from app.market.multitimeframe import build_historical_mtf_slice

DATASET_SHA = "d" * 64
CURSOR_SHA = "e" * 64


def _hourly(count: int) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    output = []
    for index in range(count):
        open_time = base + timedelta(hours=index)
        close = Decimal(str(100 + index))
        output.append(
            Candle(
                symbol="BTC/EUR",
                timeframe="1h",
                open_time=open_time,
                close_time=open_time + timedelta(hours=1),
                open=close,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=Decimal("100"),
                is_closed=True,
            )
        )
    return output


def test_mtf_slice_drops_incomplete_4h_and_1d_and_is_stable() -> None:
    candles = _hourly(30)
    as_of = candles[-1].close_time
    first = build_historical_mtf_slice(candles, as_of=as_of, target_timeframes=("1h", "4h", "1d"))
    second = build_historical_mtf_slice(candles, as_of=as_of, target_timeframes=("1h", "4h", "1d"))
    assert len(first.candles_by_timeframe["4h"]) == 7
    assert len(first.candles_by_timeframe["1d"]) == 1
    assert first.fingerprint == second.fingerprint
    assert first.candles_by_timeframe["4h"][-1].close_time <= as_of
    assert first.candles_by_timeframe["1d"][-1].close_time <= as_of


def test_engine_consumes_existing_mtf_candles_without_resampling() -> None:
    candles = _hourly(100)
    as_of = candles[-1].close_time
    mtf = build_historical_mtf_slice(candles, as_of=as_of, target_timeframes=("4h",))
    snapshot = AnalyticsIndicatorEngine().compute(
        mtf.candles_by_timeframe["4h"],
        symbol="BTC/EUR",
        timeframe="4h",
        as_of=as_of,
        source_cursor_fingerprint=mtf.fingerprint,
    )
    assert snapshot.timeframe == "4h"
    assert snapshot.source_cursor_fingerprint == mtf.fingerprint
    assert snapshot.candle_count == len(mtf.candles_by_timeframe["4h"])


def test_24a1_snapshot_integration_is_typed_and_registry_identity_changes_analytics_only() -> None:
    candles = _hourly(60)
    as_of = candles[-1].close_time
    versions = indicator_component_versions()
    assert versions.indicator_registry_version == ANALYTICS_INDICATOR_REGISTRY_IDENTITY
    run = AnalyticsLabRun.create(
        source_backtest_run_id="source-run",
        dataset_id="dataset",
        dataset_version="v1",
        dataset_content_sha256=DATASET_SHA,
        dataset_source="historical-test",
        system_id="balanced_v1",
        symbol="BTC/EUR",
        source_timeframe="1h",
        decision_timeframe="1h",
        period_start=candles[0].open_time,
        period_end=as_of,
        period_role=AnalyticsPeriodRole.OOS,
        mtf_policy_version="mtf-utc-closed-v1",
        component_versions=versions,
    )
    as_of_input = AnalyticsAsOfInput(
        source_backtest_run_id="source-run",
        dataset_id="dataset",
        dataset_version="v1",
        dataset_content_sha256=DATASET_SHA,
        dataset_source="historical-test",
        system_id="balanced_v1",
        symbol="BTC/EUR",
        source_timeframe="1h",
        decision_timeframe="1h",
        as_of=as_of,
        mtf_policy_version="mtf-utc-closed-v1",
        source_cursor_fingerprint=CURSOR_SHA,
    )
    snapshot = build_analytics_snapshot_with_indicators(
        analytics_run=run,
        as_of_input=as_of_input,
        candles=candles,
    )
    indicator_component = snapshot.components["indicators"]
    assert indicator_component.source_cursor_fingerprint == CURSOR_SHA
    assert indicator_component.as_of == as_of
    assert indicator_component.symbol == "BTC/EUR"
    assert snapshot.source_cursor_fingerprint == CURSOR_SHA

    changed_versions = replace(
        versions,
        indicator_registry_version=versions.indicator_registry_version + "-changed",
    )
    changed_run = AnalyticsLabRun.create(
        source_backtest_run_id="source-run",
        dataset_id="dataset",
        dataset_version="v1",
        dataset_content_sha256=DATASET_SHA,
        dataset_source="historical-test",
        system_id="balanced_v1",
        symbol="BTC/EUR",
        source_timeframe="1h",
        decision_timeframe="1h",
        period_start=candles[0].open_time,
        period_end=as_of,
        period_role=AnalyticsPeriodRole.OOS,
        mtf_policy_version="mtf-utc-closed-v1",
        component_versions=changed_versions,
    )
    assert changed_run.source_backtest_run_id == run.source_backtest_run_id
    assert changed_run.analytics_run_id != run.analytics_run_id
