from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.market.models import Candle
from app.market.multitimeframe import (
    HistoricalMultiTimeframeCursor,
    build_historical_mtf_slice,
)


def _minute_series(*, start: datetime, count: int) -> tuple[Candle, ...]:
    output = []
    for index in range(count):
        opened = start + timedelta(minutes=index)
        price = Decimal("100") + Decimal(index) / Decimal("100")
        output.append(
            Candle(
                symbol="BTC/USDC",
                timeframe="1m",
                open_time=opened,
                close_time=opened + timedelta(minutes=1),
                open=price,
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                close=price + Decimal("0.25"),
                volume=Decimal(index + 1),
                is_closed=True,
            )
        )
    return tuple(output)


def test_incremental_cursor_matches_batch_resampler_for_one_day():
    start = datetime(2026, 9, 1, tzinfo=UTC)
    source = _minute_series(start=start, count=24 * 60)
    cursor = HistoricalMultiTimeframeCursor(
        source_timeframe="1m",
        target_timeframes=("15m", "1h", "4h", "1d"),
    )

    for candle in source:
        cursor.push(candle)

    batch = build_historical_mtf_slice(
        source,
        as_of=source[-1].close_time,
        target_timeframes=("15m", "1h", "4h", "1d"),
    )
    for timeframe in ("15m", "1h", "4h", "1d"):
        assert cursor.series(timeframe) == batch.candles_by_timeframe[timeframe]

    state = cursor.state()
    assert state.source_candle_count == 1440
    assert state.source_fingerprint == batch.source_fingerprint
    assert dict(state.candle_counts) == {
        "15m": 96,
        "1h": 24,
        "4h": 6,
        "1d": 1,
    }


def test_incremental_cursor_does_not_emit_partial_higher_timeframe():
    start = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    source = _minute_series(start=start, count=239)
    cursor = HistoricalMultiTimeframeCursor(
        source_timeframe="1m",
        target_timeframes=("1h", "4h"),
    )

    for candle in source:
        cursor.push(candle)

    assert len(cursor.series("1h")) == 3
    assert cursor.series("4h") == ()

    final = _minute_series(
        start=start + timedelta(minutes=239),
        count=1,
    )[0]
    cursor.push(final)

    assert len(cursor.series("1h")) == 4
    assert len(cursor.series("4h")) == 1
    assert cursor.series("4h")[-1].close_time == datetime(
        2026, 9, 1, 16, 0, tzinfo=UTC
    )
