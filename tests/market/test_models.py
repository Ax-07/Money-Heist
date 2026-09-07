from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.market.models import Candle, MarketSnapshot, SnapshotQuality


def candle(**overrides):
    values = {
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "open_time": datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc),
        "close_time": datetime(2026, 9, 7, 12, 1, tzinfo=timezone.utc),
        "open": Decimal("50000"),
        "high": Decimal("50100"),
        "low": Decimal("49900"),
        "close": Decimal("50050"),
        "volume": Decimal("12.5"),
    }
    values.update(overrides)
    return Candle(**values)


def test_candle_normalizes_timestamps_to_utc():
    result = candle()
    assert result.open_time.tzinfo == timezone.utc
    assert result.close_time.tzinfo == timezone.utc


def test_candle_rejects_naive_timestamp():
    with pytest.raises(ValidationError, match="timezone-aware"):
        candle(open_time=datetime(2026, 9, 7, 12, 0))


def test_candle_rejects_incoherent_high():
    with pytest.raises(ValidationError, match="high must be"):
        candle(high=Decimal("49999"))


def test_snapshot_rejects_candle_from_other_symbol():
    foreign = candle(symbol="ETHUSDT")
    with pytest.raises(ValidationError, match="match snapshot symbol"):
        MarketSnapshot(
            symbol="BTCUSDT",
            source="test",
            observed_at=datetime(2026, 9, 7, 12, 1, tzinfo=timezone.utc),
            received_at=datetime(2026, 9, 7, 12, 1, tzinfo=timezone.utc),
            candles={"1m": (foreign,)},
            quality=SnapshotQuality(),
        )
