from __future__ import annotations

from app.analytics.events import TechnicalEventEngine


def _types(events):
    return tuple(event.event_type for event in events)


def test_pair_cross_above_below_and_equality_semantics(indicator_snapshot_factory) -> None:
    engine = TechnicalEventEngine()
    below = indicator_snapshot_factory(
        0,
        values={"ema_9": 9.0, "ema_20": 10.0},
        candle_count=250,
    )
    equal = indicator_snapshot_factory(
        1,
        values={"ema_9": 10.0, "ema_20": 10.0},
        candle_count=251,
    )
    above = indicator_snapshot_factory(
        2,
        values={"ema_9": 11.0, "ema_20": 10.0},
        candle_count=252,
    )
    back_below = indicator_snapshot_factory(
        3,
        values={"ema_9": 9.0, "ema_20": 10.0},
        candle_count=253,
    )

    assert "EMA_9_CROSS_ABOVE_EMA_20" not in _types(
        engine.detect(below, equal, analytics_run_id="run-a")
    )
    events = engine.detect(equal, above, analytics_run_id="run-a")
    assert _types(events).count("EMA_9_CROSS_ABOVE_EMA_20") == 1
    events = engine.detect(above, back_below, analytics_run_id="run-a")
    assert _types(events).count("EMA_9_CROSS_BELOW_EMA_20") == 1


def test_repeated_equality_emits_at_most_one_cross(indicator_snapshot_factory) -> None:
    engine = TechnicalEventEngine()
    first = indicator_snapshot_factory(
        0,
        values={"ema_9": 10.0, "ema_20": 10.0},
        candle_count=250,
    )
    second = indicator_snapshot_factory(
        1,
        values={"ema_9": 10.0, "ema_20": 10.0},
        candle_count=251,
    )
    third = indicator_snapshot_factory(
        2,
        values={"ema_9": 10.1, "ema_20": 10.0},
        candle_count=252,
    )
    fourth = indicator_snapshot_factory(
        3,
        values={"ema_9": 10.2, "ema_20": 10.0},
        candle_count=253,
    )

    assert "EMA_9_CROSS_ABOVE_EMA_20" not in _types(
        engine.detect(first, second, analytics_run_id="run-a")
    )
    assert (
        _types(engine.detect(second, third, analytics_run_id="run-a")).count(
            "EMA_9_CROSS_ABOVE_EMA_20"
        )
        == 1
    )
    assert "EMA_9_CROSS_ABOVE_EMA_20" not in _types(
        engine.detect(third, fourth, analytics_run_id="run-a")
    )


def test_no_cross_when_relation_does_not_change(indicator_snapshot_factory) -> None:
    previous = indicator_snapshot_factory(
        0,
        values={"ema_20": 9.0, "ema_50": 10.0},
        candle_count=250,
    )
    current = indicator_snapshot_factory(
        1,
        values={"ema_20": 9.5, "ema_50": 10.0},
        candle_count=251,
    )
    events = TechnicalEventEngine().detect(previous, current, analytics_run_id="run-a")
    assert "EMA_20_CROSS_ABOVE_EMA_50" not in _types(events)
    assert "EMA_20_CROSS_BELOW_EMA_50" not in _types(events)
