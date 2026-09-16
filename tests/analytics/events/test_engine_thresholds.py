from __future__ import annotations

from app.analytics.events import TechnicalEventEngine


def _types(events):
    return tuple(event.event_type for event in events)


def test_rsi_threshold_state_transitions_do_not_repeat(indicator_snapshot_factory) -> None:
    engine = TechnicalEventEngine()
    outside = indicator_snapshot_factory(0, values={"rsi_14": 31.0}, candle_count=250)
    inside = indicator_snapshot_factory(1, values={"rsi_14": 29.0}, candle_count=251)
    still_inside = indicator_snapshot_factory(2, values={"rsi_14": 28.0}, candle_count=252)
    equality = indicator_snapshot_factory(3, values={"rsi_14": 30.0}, candle_count=253)

    assert "RSI_14_ENTER_OVERSOLD" in _types(
        engine.detect(outside, inside, analytics_run_id="run-rsi")
    )
    assert "RSI_14_ENTER_OVERSOLD" not in _types(
        engine.detect(inside, still_inside, analytics_run_id="run-rsi")
    )
    assert "RSI_14_EXIT_OVERSOLD" in _types(
        engine.detect(still_inside, equality, analytics_run_id="run-rsi")
    )


def test_adx_uses_strict_cross_around_25(indicator_snapshot_factory) -> None:
    engine = TechnicalEventEngine()
    equal = indicator_snapshot_factory(0, values={"adx_14": 25.0}, candle_count=250)
    above = indicator_snapshot_factory(1, values={"adx_14": 26.0}, candle_count=251)
    back_equal = indicator_snapshot_factory(2, values={"adx_14": 25.0}, candle_count=252)
    below = indicator_snapshot_factory(3, values={"adx_14": 24.0}, candle_count=253)

    assert "ADX_14_CROSS_ABOVE_25" in _types(
        engine.detect(equal, above, analytics_run_id="run-adx")
    )
    assert "ADX_14_CROSS_BELOW_25" not in _types(
        engine.detect(above, back_equal, analytics_run_id="run-adx")
    )
    assert "ADX_14_CROSS_BELOW_25" in _types(
        engine.detect(back_equal, below, analytics_run_id="run-adx")
    )


def test_volume_spike_is_threshold_entry_only(indicator_snapshot_factory) -> None:
    engine = TechnicalEventEngine()
    below = indicator_snapshot_factory(0, values={"volume_ratio_20": 1.49}, candle_count=250)
    threshold = indicator_snapshot_factory(1, values={"volume_ratio_20": 1.5}, candle_count=251)
    above = indicator_snapshot_factory(2, values={"volume_ratio_20": 1.8}, candle_count=252)

    first = engine.detect(below, threshold, analytics_run_id="run-volume")
    second = engine.detect(threshold, above, analytics_run_id="run-volume")
    assert _types(first).count("VOLUME_SPIKE_20") == 1
    assert "VOLUME_SPIKE_20" not in _types(second)


def test_mfi_enter_and_exit_use_20_and_80_state_boundaries(indicator_snapshot_factory) -> None:
    engine = TechnicalEventEngine()
    middle = indicator_snapshot_factory(0, values={"mfi_14": 50.0}, candle_count=250)
    oversold = indicator_snapshot_factory(1, values={"mfi_14": 19.0}, candle_count=251)
    exit_oversold = indicator_snapshot_factory(2, values={"mfi_14": 20.0}, candle_count=252)
    overbought = indicator_snapshot_factory(3, values={"mfi_14": 81.0}, candle_count=253)
    exit_overbought = indicator_snapshot_factory(4, values={"mfi_14": 80.0}, candle_count=254)

    assert "MFI_14_ENTER_OVERSOLD" in _types(
        engine.detect(middle, oversold, analytics_run_id="run-mfi")
    )
    assert "MFI_14_EXIT_OVERSOLD" in _types(
        engine.detect(oversold, exit_oversold, analytics_run_id="run-mfi")
    )
    assert "MFI_14_ENTER_OVERBOUGHT" in _types(
        engine.detect(exit_oversold, overbought, analytics_run_id="run-mfi")
    )
    assert "MFI_14_EXIT_OVERBOUGHT" in _types(
        engine.detect(overbought, exit_overbought, analytics_run_id="run-mfi")
    )
