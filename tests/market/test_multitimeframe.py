from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market.models import Candle
from app.market.multitimeframe import (
    MultiTimeframeError,
    build_historical_mtf_slice,
    resample_closed_candles,
)


def minute_series(
    *,
    start: datetime,
    count: int,
    symbol: str = "BTC/USDC",
) -> tuple[Candle, ...]:
    candles = []
    for index in range(count):
        opened = start + timedelta(minutes=index)
        price = Decimal("100") + Decimal(index)
        candles.append(
            Candle(
                symbol=symbol,
                timeframe="1m",
                open_time=opened,
                close_time=opened + timedelta(minutes=1),
                open=price,
                high=price + Decimal("2"),
                low=price - Decimal("1"),
                close=price + Decimal("1"),
                volume=Decimal(index + 1),
                is_closed=True,
            )
        )
    return tuple(candles)


def test_resample_1m_to_15m_aggregates_ohlcv():
    source = minute_series(
        start=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        count=15,
    )

    result = resample_closed_candles(source, target_timeframe="15m")

    assert len(result) == 1
    candle = result[0]
    assert candle.open_time == datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    assert candle.close_time == datetime(2026, 9, 1, 0, 15, tzinfo=UTC)
    assert candle.open == Decimal("100")
    assert candle.high == Decimal("116")
    assert candle.low == Decimal("99")
    assert candle.close == Decimal("115")
    assert candle.volume == Decimal("120")


def test_as_of_never_exposes_incomplete_4h_bucket():
    source = minute_series(
        start=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        count=240,
    )

    before_close = resample_closed_candles(
        source,
        target_timeframe="4h",
        as_of=datetime(2026, 9, 1, 15, 0, tzinfo=UTC),
    )
    at_close = resample_closed_candles(
        source,
        target_timeframe="4h",
        as_of=datetime(2026, 9, 1, 16, 0, tzinfo=UTC),
    )

    assert before_close == ()
    assert len(at_close) == 1
    assert at_close[0].open_time.hour == 12
    assert at_close[0].close_time.hour == 16


def test_resampler_uses_utc_alignment_and_drops_partial_edges():
    source = minute_series(
        start=datetime(2026, 9, 1, 0, 5, tzinfo=UTC),
        count=60,
    )

    result = resample_closed_candles(source, target_timeframe="15m")

    assert [item.open_time.minute for item in result] == [15, 30, 45]
    assert all(item.open_time.second == 0 for item in result)


def test_resampler_rejects_internal_source_gap():
    source = list(
        minute_series(
            start=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
            count=30,
        )
    )
    del source[10]

    with pytest.raises(MultiTimeframeError, match="gap"):
        resample_closed_candles(source, target_timeframe="15m")



def test_future_gap_cannot_change_an_earlier_as_of_result():
    start = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    visible = list(minute_series(start=start, count=60))
    future_with_gap = Candle(
        symbol="BTC/USDC",
        timeframe="1m",
        open_time=start + timedelta(minutes=120),
        close_time=start + timedelta(minutes=121),
        open=Decimal("300"),
        high=Decimal("301"),
        low=Decimal("299"),
        close=Decimal("300"),
        volume=Decimal("1"),
        is_closed=True,
    )
    source = tuple(visible + [future_with_gap])
    as_of = start + timedelta(minutes=60)

    result = resample_closed_candles(
        source,
        target_timeframe="15m",
        as_of=as_of,
    )

    assert len(result) == 4
    assert result[-1].close_time == as_of

def test_historical_mtf_slice_has_expected_counts_and_no_lookahead():
    start = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    source = minute_series(start=start, count=24 * 60)
    as_of = start + timedelta(days=1)

    result = build_historical_mtf_slice(
        source,
        as_of=as_of,
        target_timeframes=("15m", "1h", "4h", "1d"),
    )

    assert len(result.candles_by_timeframe["15m"]) == 96
    assert len(result.candles_by_timeframe["1h"]) == 24
    assert len(result.candles_by_timeframe["4h"]) == 6
    assert len(result.candles_by_timeframe["1d"]) == 1
    assert all(
        candle.close_time <= as_of
        for series in result.candles_by_timeframe.values()
        for candle in series
    )


def test_historical_mtf_slice_fingerprint_is_deterministic_and_policy_bound():
    source = minute_series(
        start=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        count=60,
    )
    as_of = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)

    first = build_historical_mtf_slice(
        source,
        as_of=as_of,
        target_timeframes=("15m", "1h"),
    )
    second = build_historical_mtf_slice(
        source,
        as_of=as_of,
        target_timeframes=("15m", "1h"),
    )
    changed_policy = build_historical_mtf_slice(
        source,
        as_of=as_of,
        target_timeframes=("15m", "1h"),
        policy_version="mtf-utc-closed-v2",
    )

    assert first.fingerprint == second.fingerprint
    assert first.source_fingerprint == second.source_fingerprint
    assert first.source_candle_count == 60
    assert first.fingerprint != changed_policy.fingerprint
