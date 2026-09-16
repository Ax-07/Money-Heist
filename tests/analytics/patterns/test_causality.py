from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.patterns.engine import patterns_at
from app.analytics.patterns.models import PatternPivot, PatternStatus
from app.analytics.structure import StructureSource
from app.market.models import Candle


def _candle(i, close=105, high=106, low=104, timeframe="1h"):
    start = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=i)
    return Candle(
        symbol="BTC/EUR",
        timeframe=timeframe,
        open_time=start,
        close_time=start + timedelta(hours=1),
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("10"),
        is_closed=True,
    )


def _pivot(pid, kind, price, index, confirmed_index, timeframe="1h"):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return PatternPivot(
        pivot_id=pid,
        kind=kind,
        price=Decimal(str(price)),
        pivot_at=base + timedelta(hours=index),
        confirmed_at=base + timedelta(hours=confirmed_index + 1),
        symbol="BTC/EUR",
        timeframe=timeframe,
        source=StructureSource.CAUSAL_ZIGZAG,
        source_fingerprint=pid[0] * 64,
        source_cursor_fingerprint="a" * 64,
        atr_at_pivot=Decimal("4"),
        candle_index=index,
        confirmed_index=confirmed_index,
    )


def _series():
    candles = [_candle(i) for i in range(25)]
    candles[0] = _candle(0, 100, 101, 99)
    candles[2] = _candle(2, 105, 106, 104)
    candles[4] = _candle(4, 110, 111, 109)
    candles[7] = _candle(7, 100, 101, 99)
    candles[10] = _candle(10, 110, 111, 109)
    candles[13] = _candle(13, 98, 99, 97)
    pivots = (
        _pivot("b1", "HIGH", 110, 4, 5),
        _pivot("c2", "LOW", 100, 7, 8),
        _pivot("d3", "HIGH", 110, 10, 11),
    )
    return tuple(candles), pivots


def _forming_series():
    candles = tuple(_candle(i, close=105, high=109, low=101) for i in range(25))
    pivots = (
        _pivot("b1", "HIGH", 110, 4, 5),
        _pivot("c2", "LOW", 100, 7, 8),
        _pivot("d3", "HIGH", 110, 10, 11),
    )
    return candles, pivots


def _run(candles, pivots, cutoff):
    return patterns_at(
        candles=candles,
        pivots=pivots,
        as_of=cutoff,
        analytics_run_id="run",
        source_cursor_fingerprint="e" * 64,
    )


def test_pattern_cannot_use_unconfirmed_pivot():
    candles, pivots = _series()
    before = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=11)
    assert _run(candles, pivots, before) == ()


def test_pattern_prefix_invariance():
    candles, pivots = _series()
    cutoff = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=14)
    full = _run(candles, pivots, cutoff)
    prefix = _run(
        tuple(candle for candle in candles if candle.close_time <= cutoff),
        pivots,
        cutoff,
    )
    assert [
        (pattern.pattern_id, pattern.current_status, pattern.pattern_fingerprint)
        for pattern in full
    ] == [
        (pattern.pattern_id, pattern.current_status, pattern.pattern_fingerprint)
        for pattern in prefix
    ]


def test_future_extreme_does_not_change_past_state():
    candles, pivots = _series()
    cutoff = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=14)
    baseline = _run(candles, pivots, cutoff)
    future = list(candles)
    future[20] = _candle(20, 105, 1000, 1)
    changed = _run(tuple(future), pivots, cutoff)
    assert [(pattern.pattern_id, pattern.pattern_fingerprint) for pattern in baseline] == [
        (pattern.pattern_id, pattern.pattern_fingerprint) for pattern in changed
    ]


def test_same_candle_intrabar_extremes_do_not_invent_breakout_order():
    candles, pivots = _forming_series()
    rows = list(candles)
    rows[12] = _candle(12, close=105, high=120, low=90)
    cutoff = rows[12].close_time
    result = _run(tuple(rows), pivots, cutoff)
    assert result
    assert result[0].current_status == PatternStatus.FORMING


def test_timeout_becomes_available_on_deadline_close_not_one_bar_later():
    candles, pivots = _forming_series()
    before_deadline = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=22)
    at_deadline = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=23)
    before = _run(candles, pivots, before_deadline)
    deadline = _run(candles, pivots, at_deadline)
    assert before
    assert deadline
    assert before[0].current_status == PatternStatus.FORMING
    assert deadline[0].current_status == PatternStatus.FAILED
    assert deadline[0].failed_at == at_deadline


def test_mtf_incomplete_candle_is_invisible():
    candles, pivots = _series()
    open_candle = candles[-1].model_copy(update={"is_closed": False})
    result = _run(
        (*candles[:-1], open_candle),
        pivots,
        open_candle.close_time,
    )
    assert all(pattern.detected_at <= open_candle.close_time for pattern in result)
