from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market.models import Candle


@pytest.fixture
def trend_candles_factory():
    def build(
        count: int,
        *,
        start: float = 100.0,
        step: float = 1.0,
        volume: float = 100.0,
        timeframe: str = "1h",
    ) -> list[Candle]:
        output: list[Candle] = []
        base = datetime(2026, 1, 1, tzinfo=UTC)
        interval = timedelta(hours=1)
        for index in range(count):
            close = start + index * step
            open_time = base + index * interval
            output.append(
                Candle(
                    symbol="BTC/EUR",
                    timeframe=timeframe,
                    open_time=open_time,
                    close_time=open_time + interval,
                    open=Decimal(str(close - 0.25)),
                    high=Decimal(str(close + 1.0)),
                    low=Decimal(str(close - 1.0)),
                    close=Decimal(str(close)),
                    volume=Decimal(str(volume)),
                    is_closed=True,
                )
            )
        return output

    return build
