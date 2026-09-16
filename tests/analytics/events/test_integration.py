from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics import AnalyticsAsOfInput, AnalyticsLabRun, AnalyticsPeriodRole
from app.analytics.events import (
    ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY,
    build_analytics_snapshot_with_indicators_and_events,
    technical_event_component_versions,
)
from app.analytics.indicators import (
    ANALYTICS_INDICATOR_REGISTRY_IDENTITY,
    AnalyticsIndicatorEngine,
)
from app.common.canonical import stable_digest
from app.market.models import Candle

DATASET_SHA = "d" * 64


def _candles() -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    output = []
    for index in range(21):
        open_time = base + timedelta(hours=index)
        close = Decimal(str(100 + (index % 2) * 0.1))
        output.append(
            Candle(
                symbol="BTC/EUR",
                timeframe="1h",
                open_time=open_time,
                close_time=open_time + timedelta(hours=1),
                open=close,
                high=close + Decimal("1"),
                low=close - Decimal("1"),
                close=close,
                volume=Decimal("200" if index == 20 else "100"),
                is_closed=True,
            )
        )
    return output


def _run(candles: list[Candle], versions=None) -> AnalyticsLabRun:
    versions = versions or technical_event_component_versions()
    return AnalyticsLabRun.create(
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
        period_end=candles[-1].close_time,
        period_role=AnalyticsPeriodRole.OOS,
        mtf_policy_version="mtf-utc-closed-v1",
        component_versions=versions,
    )


def _as_of(candles: list[Candle], index: int, cursor: str) -> AnalyticsAsOfInput:
    return AnalyticsAsOfInput(
        source_backtest_run_id="source-run",
        dataset_id="dataset",
        dataset_version="v1",
        dataset_content_sha256=DATASET_SHA,
        dataset_source="historical-test",
        system_id="balanced_v1",
        symbol="BTC/EUR",
        source_timeframe="1h",
        decision_timeframe="1h",
        as_of=candles[index].close_time,
        mtf_policy_version="mtf-utc-closed-v1",
        source_cursor_fingerprint=cursor,
    )


def test_indicator_to_events_to_analytics_snapshot_is_stable() -> None:
    candles = _candles()
    versions = technical_event_component_versions()
    assert versions.indicator_registry_version == ANALYTICS_INDICATOR_REGISTRY_IDENTITY
    assert versions.event_registry_version == ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY
    run = _run(candles, versions)
    previous_cursor = stable_digest({"cursor": 19})
    current_cursor = stable_digest({"cursor": 20})
    indicator_engine = AnalyticsIndicatorEngine()
    previous = indicator_engine.compute(
        candles,
        symbol="BTC/EUR",
        timeframe="1h",
        as_of=candles[19].close_time,
        source_cursor_fingerprint=previous_cursor,
    )
    as_of_input = _as_of(candles, 20, current_cursor)

    first = build_analytics_snapshot_with_indicators_and_events(
        analytics_run=run,
        as_of_input=as_of_input,
        candles=candles,
        previous_indicator_snapshot=previous,
    )
    second = build_analytics_snapshot_with_indicators_and_events(
        analytics_run=run,
        as_of_input=as_of_input,
        candles=candles,
        previous_indicator_snapshot=previous,
    )
    assert first.snapshot_id == second.snapshot_id
    assert (
        first.components["indicators"].snapshot_fingerprint
        == second.components["indicators"].snapshot_fingerprint
    )
    assert tuple(
        event.event_fingerprint for event in first.components["technical_events"]
    ) == tuple(event.event_fingerprint for event in second.components["technical_events"])
    assert "VOLUME_SPIKE_20" in {event.event_type for event in first.components["technical_events"]}
    assert all(event.available_at <= first.as_of for event in first.components["technical_events"])


def test_event_registry_version_changes_analytics_identity_not_source_backtest_identity() -> None:
    candles = _candles()
    versions = technical_event_component_versions()
    baseline = _run(candles, versions)
    changed = _run(
        candles,
        replace(
            versions,
            event_registry_version=versions.event_registry_version + "-changed",
        ),
    )
    assert changed.source_backtest_run_id == baseline.source_backtest_run_id
    assert changed.analytics_run_id != baseline.analytics_run_id


def test_technical_events_participate_in_analytics_snapshot_identity() -> None:
    candles = _candles()
    run = _run(candles)
    previous_cursor = stable_digest({"cursor": 19})
    current_cursor = stable_digest({"cursor": 20})
    previous = AnalyticsIndicatorEngine().compute(
        candles,
        symbol="BTC/EUR",
        timeframe="1h",
        as_of=candles[19].close_time,
        source_cursor_fingerprint=previous_cursor,
    )
    as_of_input = _as_of(candles, 20, current_cursor)
    with_event = build_analytics_snapshot_with_indicators_and_events(
        analytics_run=run,
        as_of_input=as_of_input,
        candles=candles,
        previous_indicator_snapshot=previous,
    )
    without_event = build_analytics_snapshot_with_indicators_and_events(
        analytics_run=run,
        as_of_input=as_of_input,
        candles=candles,
        previous_indicator_snapshot=None,
    )
    assert with_event.components["technical_events"]
    assert without_event.components["technical_events"] == ()
    assert with_event.snapshot_id != without_event.snapshot_id
