from __future__ import annotations

import pytest

from app.analytics.events import (
    TECHNICAL_EVENT_TYPES,
    TechnicalEventEngine,
    TechnicalEventInputError,
)


def _types(events):
    return tuple(event.event_type for event in events)


def test_missing_previous_or_current_indicator_produces_no_event(
    indicator_snapshot_factory,
) -> None:
    engine = TechnicalEventEngine()
    missing_previous = indicator_snapshot_factory(0, values={}, candle_count=250)
    current = indicator_snapshot_factory(1, values={"rsi_14": 29.0}, candle_count=251)
    assert engine.detect(missing_previous, current, analytics_run_id="run") == ()

    previous = indicator_snapshot_factory(0, values={"rsi_14": 31.0}, candle_count=250)
    missing_current = indicator_snapshot_factory(1, values={}, candle_count=251)
    assert engine.detect(previous, missing_current, analytics_run_id="run") == ()


def test_warmup_false_produces_no_event(indicator_snapshot_factory) -> None:
    previous = indicator_snapshot_factory(
        0,
        values={"rsi_14": 31.0},
        candle_count=250,
    )
    current = indicator_snapshot_factory(
        1,
        values={"rsi_14": 29.0},
        candle_count=251,
        warmup_false={"rsi_14"},
    )
    assert TechnicalEventEngine().detect(previous, current, analytics_run_id="run") == ()


def test_same_candle_count_is_no_new_closed_timeframe_event(indicator_snapshot_factory) -> None:
    previous = indicator_snapshot_factory(
        0,
        values={"volume_ratio_20": 1.0},
        candle_count=250,
    )
    current = indicator_snapshot_factory(
        1,
        values={"volume_ratio_20": 2.0},
        candle_count=250,
    )
    assert TechnicalEventEngine().detect(previous, current, analytics_run_id="run") == ()


def test_skipped_snapshot_is_rejected(indicator_snapshot_factory) -> None:
    previous = indicator_snapshot_factory(
        0,
        values={"rsi_14": 40.0},
        candle_count=250,
    )
    current = indicator_snapshot_factory(
        2,
        values={"rsi_14": 60.0},
        candle_count=252,
    )
    with pytest.raises(TechnicalEventInputError, match="consecutive"):
        TechnicalEventEngine().detect(previous, current, analytics_run_id="run")


def test_multiple_events_follow_registry_order(indicator_snapshot_factory) -> None:
    previous = indicator_snapshot_factory(
        0,
        values={
            "ema_9": 9.0,
            "ema_20": 10.0,
            "rsi_14": 49.0,
            "volume_ratio_20": 1.0,
        },
        candle_count=250,
    )
    current = indicator_snapshot_factory(
        1,
        values={
            "ema_9": 11.0,
            "ema_20": 10.0,
            "rsi_14": 51.0,
            "volume_ratio_20": 1.6,
        },
        candle_count=251,
    )
    events = TechnicalEventEngine().detect(previous, current, analytics_run_id="run")
    positions = [TECHNICAL_EVENT_TYPES.index(event.event_type) for event in events]
    assert positions == sorted(positions)
    assert _types(events) == (
        "EMA_9_CROSS_ABOVE_EMA_20",
        "RSI_14_CROSS_ABOVE_50",
        "VOLUME_SPIKE_20",
    )
