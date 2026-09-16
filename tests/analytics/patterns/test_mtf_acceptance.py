from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.analytics.patterns.engine import patterns_at
from app.analytics.patterns.models import PatternPivot
from app.analytics.structure import StructureSource
from app.market.models import Candle

BASE = datetime(2026, 3, 1, tzinfo=UTC)


def _candles(timeframe: str, step_hours: int) -> tuple[Candle, ...]:
    return tuple(
        Candle(
            symbol="BTC/USDC",
            timeframe=timeframe,
            open_time=BASE + timedelta(hours=index * step_hours),
            close_time=BASE + timedelta(hours=(index + 1) * step_hours),
            open=Decimal("105"),
            high=Decimal("106"),
            low=Decimal("104"),
            close=Decimal("105"),
            volume=Decimal("10"),
            is_closed=True,
        )
        for index in range(16)
    )


def _pivots(timeframe: str, step_hours: int) -> tuple[PatternPivot, ...]:
    values = (
        (2, "HIGH", "110"),
        (5, "LOW", "100"),
        (8, "HIGH", "110"),
    )
    return tuple(
        PatternPivot(
            pivot_id=f"{timeframe}-pivot-{index}",
            kind=kind,
            price=Decimal(price),
            pivot_at=BASE + timedelta(hours=index * step_hours),
            confirmed_at=BASE + timedelta(hours=(index + 1) * step_hours),
            symbol="BTC/USDC",
            timeframe=timeframe,
            source=StructureSource.CAUSAL_ZIGZAG,
            source_fingerprint=f"{index + 1:064x}"[-64:],
            source_cursor_fingerprint="a" * 64,
            atr_at_pivot=Decimal("4"),
            candle_index=index,
            confirmed_index=index,
        )
        for index, kind, price in values
    )


@pytest.mark.parametrize(("timeframe", "step_hours"), [("1h", 1), ("4h", 4)])
def test_pattern_source_timeframe_cannot_read_beyond_closed_prefix(
    timeframe: str,
    step_hours: int,
) -> None:
    candles = _candles(timeframe, step_hours)
    pivots = _pivots(timeframe, step_hours)
    cutoff = candles[12].close_time
    prefix = tuple(candle for candle in candles if candle.close_time <= cutoff)

    full_result = patterns_at(
        candles=candles,
        pivots=pivots,
        as_of=cutoff,
        analytics_run_id=f"run-{timeframe}",
        source_cursor_fingerprint="f" * 64,
    )
    prefix_result = patterns_at(
        candles=prefix,
        pivots=pivots,
        as_of=cutoff,
        analytics_run_id=f"run-{timeframe}",
        source_cursor_fingerprint="f" * 64,
    )

    assert [
        (item.pattern_id, item.current_status, item.pattern_fingerprint) for item in full_result
    ] == [
        (item.pattern_id, item.current_status, item.pattern_fingerprint) for item in prefix_result
    ]
