from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market.models import Candle
from app.market.multitimeframe import HistoricalMultiTimeframeCursor
from app.market.structure import (
    BreakoutState,
    MARKET_STRUCTURE_VERSION,
    SwingStructure,
    build_market_structure_context,
)


START = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(index, *, high, low, close):
    opened = START + timedelta(hours=index)
    return Candle(
        symbol="BTC/USDC",
        timeframe="1h",
        open_time=opened,
        close_time=opened + timedelta(hours=1),
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("100"),
        is_closed=True,
    )


def _cursor(candles):
    cursor = HistoricalMultiTimeframeCursor(
        source_timeframe="1h",
        target_timeframes=("1h",),
    )
    for candle in candles:
        cursor.push(candle)
    return cursor


def test_structure_detects_bullish_hh_hl_from_closed_pivots():
    highs = [10, 11, 14, 11, 10, 12, 13, 16, 13, 12, 14, 15, 18, 15, 14]
    lows = [8, 9, 10, 9, 7, 9, 10, 11, 10, 8, 10, 11, 12, 11, 10]
    candles = [
        _candle(index, high=high, low=low, close=(high + low) / 2)
        for index, (high, low) in enumerate(zip(highs, lows, strict=True))
    ]
    cursor = _cursor(candles)
    context = build_market_structure_context(
        mtf_cursor=cursor,
        observed_at=candles[-1].close_time,
        range_lookback=5,
        pivot_span=2,
    )

    summary = context.timeframes["1h"]
    assert context.version == MARKET_STRUCTURE_VERSION
    assert summary.swing_structure is SwingStructure.BULLISH_HH_HL
    assert summary.latest_swing_high.price > summary.previous_swing_high.price
    assert summary.latest_swing_low.price > summary.previous_swing_low.price
    assert summary.orderbook_available is False
    assert summary.liquidation_data_available is False


def test_structure_detects_false_break_without_future_candle():
    candles = []
    for index in range(6):
        candles.append(
            _candle(
                index,
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("100"),
            )
        )
    candles.append(
        _candle(
            6,
            high=Decimal("115"),
            low=Decimal("95"),
            close=Decimal("109"),
        )
    )
    cursor = _cursor(candles)
    context = build_market_structure_context(
        mtf_cursor=cursor,
        observed_at=candles[-1].close_time,
        range_lookback=5,
    )

    assert (
        context.timeframes["1h"].breakout_state
        is BreakoutState.FALSE_BREAK_UP
    )


def test_structure_rejects_as_of_different_from_cursor_state():
    candles = [
        _candle(index, high=110 + index, low=90 + index, close=100 + index)
        for index in range(6)
    ]
    cursor = _cursor(candles)

    with pytest.raises(ValueError, match="cursor as_of"):
        build_market_structure_context(
            mtf_cursor=cursor,
            observed_at=candles[-1].close_time - timedelta(hours=1),
            range_lookback=5,
        )


def test_structure_fingerprint_is_deterministic():
    candles = [
        _candle(index, high=110 + index, low=90 + index, close=100 + index)
        for index in range(30)
    ]
    cursor = _cursor(candles)
    first = build_market_structure_context(
        mtf_cursor=cursor,
        observed_at=candles[-1].close_time,
    )
    second = build_market_structure_context(
        mtf_cursor=cursor,
        observed_at=candles[-1].close_time,
    )

    assert first.context_fingerprint == second.context_fingerprint
    assert first.to_payload() == second.to_payload()
