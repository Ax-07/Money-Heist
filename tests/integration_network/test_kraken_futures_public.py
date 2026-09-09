from __future__ import annotations

import asyncio
import os
from datetime import timedelta

import pytest

from app.market.exchange import (
    KrakenFuturesAnalyticsConfig,
    KrakenFuturesAnalyticsProvider,
    ResilientPublicHttpClient,
    RetryPolicy,
    StdlibJsonTransport,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_KRAKEN_FUTURES_NETWORK_SMOKE") != "1",
    reason="set RUN_KRAKEN_FUTURES_NETWORK_SMOKE=1 to call Kraken Futures public API",
)


def test_kraken_futures_public_analytics_smoke() -> None:
    provider = KrakenFuturesAnalyticsProvider(
        ResilientPublicHttpClient(
            StdlibJsonTransport(),
            policy=RetryPolicy(
                timeout_seconds=8,
                max_attempts=2,
                min_request_interval_seconds=0.25,
            ),
        ),
        config=KrakenFuturesAnalyticsConfig(
            interval_seconds=300,
            lookback=timedelta(hours=2),
            max_metric_age=timedelta(minutes=30),
        ),
    )

    snapshot = asyncio.run(provider.get_positioning_snapshot("BTC/EUR"))

    assert snapshot.instrument == "PF_XBTUSD"
    assert snapshot.available_metric_count >= 1
    assert snapshot.source == "kraken_futures_analytics"
