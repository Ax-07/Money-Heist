from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.market.exchange import (
    KrakenAdapterConfig,
    KrakenPublicMarketDataProvider,
    ResilientPublicHttpClient,
    RetryPolicy,
    StdlibJsonTransport,
)
from app.market.quality import FreshnessPolicy


pytestmark = pytest.mark.skipif(
    os.getenv("MONEY_HEIST_RUN_NETWORK_TESTS") != "1",
    reason="set MONEY_HEIST_RUN_NETWORK_TESTS=1 to exercise Kraken public REST",
)


def run(coro):
    return asyncio.run(coro)


def provider() -> KrakenPublicMarketDataProvider:
    return KrakenPublicMarketDataProvider(
        ResilientPublicHttpClient(
            StdlibJsonTransport(),
            policy=RetryPolicy(),
        ),
        config=KrakenAdapterConfig(
            freshness_policy=FreshnessPolicy(max_age=timedelta(minutes=5)),
            snapshot_timeframes=("1m",),
            metadata_max_age=timedelta(hours=1),
        ),
    )


def test_kraken_public_metadata_price_and_ohlc_smoke():
    adapter = provider()

    async def scenario():
        metadata = await adapter.refresh_symbol_metadata("BTC/EUR")
        current = await adapter.get_current_price("BTC/EUR")
        candles = await adapter.get_candles("BTC/EUR", "1m", 3)
        return metadata, current, candles

    metadata, current, candles = run(scenario())

    assert metadata.base_asset == "BTC"
    assert metadata.quote_asset == "EUR"
    assert metadata.tick_size > Decimal("0")
    assert metadata.qty_step > Decimal("0")
    assert metadata.min_qty > Decimal("0")
    assert metadata.min_notional > Decimal("0")
    assert current.price > Decimal("0")
    assert current.observed_at <= datetime.now(timezone.utc) + timedelta(seconds=5)
    assert candles
    assert candles[-1].is_closed is False
