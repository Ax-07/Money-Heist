from __future__ import annotations

from app.analytics.events import TechnicalEventEngine


def _types(events):
    return {event.event_type for event in events}


def test_price_ema200_uses_analytics_distance_transition(indicator_snapshot_factory) -> None:
    previous = indicator_snapshot_factory(
        0,
        values={"ema_200_distance_pct": -0.01},
        candle_count=250,
    )
    current = indicator_snapshot_factory(
        1,
        values={"ema_200_distance_pct": 0.01},
        candle_count=251,
    )
    events = TechnicalEventEngine().detect(previous, current, analytics_run_id="run-price")
    assert "PRICE_CROSS_ABOVE_EMA_200" in _types(events)


def test_bollinger_break_and_return_are_state_transitions(indicator_snapshot_factory) -> None:
    inside = indicator_snapshot_factory(
        0,
        values={"bb_position_20_2": 0.95},
        candle_count=250,
    )
    above = indicator_snapshot_factory(
        1,
        values={"bb_position_20_2": 1.05},
        candle_count=251,
    )
    still_above = indicator_snapshot_factory(
        2,
        values={"bb_position_20_2": 1.10},
        candle_count=252,
    )
    returned = indicator_snapshot_factory(
        3,
        values={"bb_position_20_2": 1.0},
        candle_count=253,
    )
    engine = TechnicalEventEngine()
    assert "PRICE_BREAK_ABOVE_BOLLINGER_UPPER" in _types(
        engine.detect(inside, above, analytics_run_id="run-bb")
    )
    assert "PRICE_BREAK_ABOVE_BOLLINGER_UPPER" not in _types(
        engine.detect(above, still_above, analytics_run_id="run-bb")
    )
    assert "PRICE_RETURN_INSIDE_FROM_ABOVE_BOLLINGER" in _types(
        engine.detect(still_above, returned, analytics_run_id="run-bb")
    )


def test_donchian_break_is_non_repeating_close_transition(indicator_snapshot_factory) -> None:
    inside = indicator_snapshot_factory(
        0,
        values={"distance_to_high_20_pct": -0.1},
        candle_count=250,
    )
    breakout = indicator_snapshot_factory(
        1,
        values={"distance_to_high_20_pct": 0.2},
        candle_count=251,
    )
    extended = indicator_snapshot_factory(
        2,
        values={"distance_to_high_20_pct": 0.3},
        candle_count=252,
    )
    engine = TechnicalEventEngine()
    assert "PRICE_BREAK_ABOVE_DONCHIAN_20" in _types(
        engine.detect(inside, breakout, analytics_run_id="run-donchian")
    )
    assert "PRICE_BREAK_ABOVE_DONCHIAN_20" not in _types(
        engine.detect(breakout, extended, analytics_run_id="run-donchian")
    )
