from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.zigzag import (
    CausalZigZagEngine,
    CausalZigZagInputBar,
    ZigZagPivotKind,
)
from app.market.models import Candle

START = datetime(2026, 1, 1, tzinfo=UTC)
FP_A = "a" * 64
FP_B = "b" * 64


def _bar(
    index: int,
    *,
    high: str,
    low: str,
    atr: float | None = 2.0,
) -> CausalZigZagInputBar:
    open_time = START + timedelta(hours=index)
    close_time = open_time + timedelta(hours=1)
    high_d = Decimal(high)
    low_d = Decimal(low)
    close = (high_d + low_d) / Decimal("2")
    candle = Candle(
        symbol="BTC/EUR",
        timeframe="1h",
        open_time=open_time,
        close_time=close_time,
        open=close,
        high=high_d,
        low=low_d,
        close=close,
        volume=Decimal("1"),
        is_closed=True,
    )
    return CausalZigZagInputBar(
        candle=candle,
        atr_at_candle=atr,
        source_cursor_fingerprint=FP_A,
        source_indicator_snapshot_fingerprint=FP_B,
    )


def test_candidate_replacement_and_exact_threshold_are_causal() -> None:
    bars = (
        _bar(0, high="100", low="98"),
        _bar(1, high="103", low="100"),
        _bar(2, high="106", low="103"),
        _bar(3, high="105", low="102"),  # exact 4 = 2 x ATR reversal
    )
    pivots = CausalZigZagEngine(reversal_multiple=2.0).compute(
        bars,
        analytics_run_id="run-1",
    )
    high = next(p for p in pivots if p.kind == ZigZagPivotKind.HIGH)
    assert high.price == Decimal("106")
    assert high.pivot_at == bars[2].candle.close_time
    assert high.confirmed_at == bars[3].candle.close_time
    assert high.reversal_threshold == Decimal("4")


def test_atr_is_locked_at_candidate() -> None:
    bars = (
        _bar(0, high="100", low="98", atr=10.0),
        _bar(1, high="110", low="100", atr=10.0),
        _bar(2, high="109", low="91", atr=15.0),
        _bar(3, high="109", low="90", atr=15.0),
    )
    pivots = CausalZigZagEngine(reversal_multiple=2.0).compute(
        bars,
        analytics_run_id="run-1",
    )
    high = next(p for p in pivots if p.kind == ZigZagPivotKind.HIGH)
    assert high.atr_at_pivot == Decimal("10.0")
    assert high.reversal_threshold == Decimal("20.00")


def test_new_extreme_cannot_be_confirmed_on_same_ohlc() -> None:
    bars = (
        _bar(0, high="100", low="98"),
        _bar(1, high="103", low="100"),
        _bar(2, high="110", low="100"),
        _bar(3, high="109", low="106"),
        _bar(4, high="109", low="106"),
    )
    pivots = CausalZigZagEngine(reversal_multiple=2.0).compute(
        bars,
        analytics_run_id="run-1",
    )
    assert all(
        not (
            pivot.pivot_at == bars[2].candle.close_time
            and pivot.confirmed_at == bars[2].candle.close_time
        )
        for pivot in pivots
    )


def test_initial_same_candle_ambiguity_does_not_invent_first_swing() -> None:
    bars = (
        _bar(0, high="100", low="98"),
        _bar(1, high="110", low="90"),
    )
    pivots = CausalZigZagEngine(reversal_multiple=2.0).compute(
        bars,
        analytics_run_id="run-1",
    )
    assert pivots == ()


def test_prefix_invariance_and_no_retroactive_mutation() -> None:
    prefix = (
        _bar(0, high="100", low="98"),
        _bar(1, high="103", low="100"),
        _bar(2, high="106", low="103"),
        _bar(3, high="105", low="102"),
    )
    future = (
        _bar(4, high="120", low="101"),
        _bar(5, high="121", low="80"),
    )
    engine = CausalZigZagEngine(reversal_multiple=2.0)
    at_t = engine.compute(prefix, analytics_run_id="run-1")
    full = engine.compute(prefix + future, analytics_run_id="run-1")
    visible = tuple(p for p in full if p.confirmed_at <= prefix[-1].candle.close_time)
    assert visible == at_t
    assert [p.pivot_id for p in visible] == [p.pivot_id for p in at_t]
    assert [p.pivot_fingerprint for p in visible] == [
        p.pivot_fingerprint for p in at_t
    ]


def test_confirmed_pivots_alternate() -> None:
    bars = (
        _bar(0, high="100", low="98"),
        _bar(1, high="103", low="100"),
        _bar(2, high="106", low="103"),
        _bar(3, high="105", low="102"),
        _bar(4, high="103", low="99"),
        _bar(5, high="104", low="100"),
    )
    pivots = CausalZigZagEngine(reversal_multiple=2.0).compute(
        bars,
        analytics_run_id="run-1",
    )
    kinds = [pivot.kind for pivot in pivots]
    assert all(left != right for left, right in zip(kinds, kinds[1:], strict=False))
