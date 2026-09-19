import asyncio
from datetime import UTC, datetime

import pytest

from app.market.models import MarketSnapshot, SnapshotQuality
from app.market.provider import InMemoryMarketDataProvider, MarketDataProvider


def test_in_memory_provider_implements_market_data_protocol():
    snapshot = MarketSnapshot(
        symbol="BTCUSDT",
        source="test",
        observed_at=datetime(2026, 9, 7, 12, 0, tzinfo=UTC),
        received_at=datetime(2026, 9, 7, 12, 0, tzinfo=UTC),
        quality=SnapshotQuality(),
    )
    provider = InMemoryMarketDataProvider(snapshots={"BTCUSDT": snapshot})
    assert isinstance(provider, MarketDataProvider)
    assert asyncio.run(provider.get_snapshot("BTCUSDT")) == snapshot


def test_in_memory_provider_rejects_non_positive_limit():
    provider = InMemoryMarketDataProvider()
    with pytest.raises(ValueError, match="limit"):
        asyncio.run(provider.get_candles("BTCUSDT", "1m", 0))
