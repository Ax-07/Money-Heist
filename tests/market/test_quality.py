from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.market.models import Candle
from app.market.quality import (
    FreshnessPolicy,
    MarketDataValidationError,
    count_gaps,
    is_stale,
    validate_candle_series,
)
from app.market.snapshot import create_market_snapshot


def make_candle(minute: int) -> Candle:
    start = datetime(2026, 9, 7, 12, minute, tzinfo=timezone.utc)
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open_time=start,
        close_time=start + timedelta(minutes=1),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("10"),
    )


def test_freshness_policy_marks_old_data_stale():
    now = datetime(2026, 9, 7, 12, 5, tzinfo=timezone.utc)
    observed = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    assert is_stale(
        observed,
        now=now,
        policy=FreshnessPolicy(max_age=timedelta(minutes=2)),
    )


def test_freshness_rejects_large_future_timestamp():
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(MarketDataValidationError, match="future"):
        is_stale(
            now + timedelta(minutes=1),
            now=now,
            policy=FreshnessPolicy(max_age=timedelta(minutes=2)),
        )


def test_series_rejects_duplicate_candles():
    item = make_candle(0)
    with pytest.raises(MarketDataValidationError, match="duplicate"):
        validate_candle_series((item, item))


def test_gap_detection_counts_missing_intervals():
    series = (make_candle(0), make_candle(1), make_candle(4))
    assert count_gaps(series, expected_interval=timedelta(minutes=1)) == 2


def test_snapshot_quality_becomes_invalid_when_stale_or_gapped():
    observed = datetime(2026, 9, 7, 12, 1, tzinfo=timezone.utc)
    snapshot = create_market_snapshot(
        symbol="BTCUSDT",
        source="unit-test",
        observed_at=observed,
        received_at=observed,
        now=datetime(2026, 9, 7, 12, 10, tzinfo=timezone.utc),
        freshness_policy=FreshnessPolicy(max_age=timedelta(minutes=2)),
        candle_sets={"1m": (make_candle(0), make_candle(2))},
        expected_intervals={"1m": timedelta(minutes=1)},
    )
    assert snapshot.quality.is_stale is True
    assert snapshot.quality.gap_count == 1
    assert snapshot.quality.is_valid is False
