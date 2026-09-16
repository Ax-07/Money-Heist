from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.events import TechnicalEventEngine
from app.analytics.indicators import AnalyticsIndicatorEngine
from app.common.canonical import stable_digest
from app.market.models import Candle


def _candles_with_volume_spike() -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    candles = []
    for index in range(21):
        close = Decimal(str(100 + (index % 3) * 0.1))
        open_time = base + timedelta(hours=index)
        candles.append(
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
    return candles


def _indicator(candles, index: int, *, source_cursor: str):
    return AnalyticsIndicatorEngine().compute(
        candles,
        symbol="BTC/EUR",
        timeframe="1h",
        as_of=candles[index].close_time,
        source_cursor_fingerprint=source_cursor,
    )


def test_technical_events_prefix_invariance() -> None:
    candles = _candles_with_volume_spike()
    previous_cursor = stable_digest({"cursor": 19})
    current_cursor = stable_digest({"cursor": 20})
    previous_full = _indicator(candles, 19, source_cursor=previous_cursor)
    current_full = _indicator(candles, 20, source_cursor=current_cursor)
    previous_truncated = _indicator(candles[:20], 19, source_cursor=previous_cursor)
    current_truncated = _indicator(candles[:21], 20, source_cursor=current_cursor)

    engine = TechnicalEventEngine()
    full_events = engine.detect(previous_full, current_full, analytics_run_id="run-prefix")
    truncated_events = engine.detect(
        previous_truncated,
        current_truncated,
        analytics_run_id="run-prefix",
    )
    assert tuple(event.canonical_payload() for event in full_events) == tuple(
        event.canonical_payload() for event in truncated_events
    )
    assert "VOLUME_SPIKE_20" in {event.event_type for event in full_events}


def test_future_malformed_candle_cannot_change_event_at_t() -> None:
    candles = _candles_with_volume_spike()
    future_close_time = candles[-1].close_time + timedelta(hours=1)
    malformed_future = {
        "symbol": "WRONG/FUTURE",
        "timeframe": "999h",
        "close_time": future_close_time,
        "high": "not-a-number",
        "low": None,
        "close": object(),
        "volume": -1,
        "is_closed": True,
    }
    previous_cursor = stable_digest({"cursor": 19})
    current_cursor = stable_digest({"cursor": 20})
    previous = _indicator(candles, 19, source_cursor=previous_cursor)
    truncated = _indicator(candles, 20, source_cursor=current_cursor)
    full = AnalyticsIndicatorEngine().compute(
        [*candles, malformed_future],
        symbol="BTC/EUR",
        timeframe="1h",
        as_of=candles[-1].close_time,
        source_cursor_fingerprint=current_cursor,
    )
    engine = TechnicalEventEngine()
    expected = engine.detect(previous, truncated, analytics_run_id="run-future")
    observed = engine.detect(previous, full, analytics_run_id="run-future")
    assert tuple(event.canonical_payload() for event in expected) == tuple(
        event.canonical_payload() for event in observed
    )


def test_incomplete_higher_timeframe_candle_cannot_emit_event() -> None:
    base = datetime(2026, 2, 1, tzinfo=UTC)
    candles = []
    for index in range(20):
        open_time = base + timedelta(hours=4 * index)
        close = Decimal("100")
        candles.append(
            Candle(
                symbol="BTC/EUR",
                timeframe="4h",
                open_time=open_time,
                close_time=open_time + timedelta(hours=4),
                open=close,
                high=close + Decimal("1"),
                low=close - Decimal("1"),
                close=close,
                volume=Decimal("100"),
                is_closed=True,
            )
        )
    next_open = candles[-1].close_time
    incomplete = Candle(
        symbol="BTC/EUR",
        timeframe="4h",
        open_time=next_open,
        close_time=next_open + timedelta(hours=4),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=Decimal("1000"),
        is_closed=False,
    )
    indicator_engine = AnalyticsIndicatorEngine()
    previous = indicator_engine.compute(
        candles,
        symbol="BTC/EUR",
        timeframe="4h",
        as_of=candles[-1].close_time,
        source_cursor_fingerprint=stable_digest({"4h": 20}),
    )
    current = indicator_engine.compute(
        [*candles, incomplete],
        symbol="BTC/EUR",
        timeframe="4h",
        as_of=next_open + timedelta(hours=2),
        source_cursor_fingerprint=stable_digest({"4h": "incomplete"}),
    )
    assert current.candle_count == previous.candle_count
    assert (
        TechnicalEventEngine().detect(
            previous,
            current,
            analytics_run_id="run-4h",
        )
        == ()
    )
