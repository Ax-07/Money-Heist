from datetime import UTC, datetime, timedelta

import pytest

from app.services.backtest import DatasetRef

START = datetime(2026, 1, 1, tzinfo=UTC)


def candle(index: int, *, close: str | None = None) -> dict[str, object]:
    open_time = START + timedelta(minutes=5 * index)
    price = 100 + index
    close_value = float(close) if close is not None else price + 0.25
    return {
        "symbol": "BTC/EUR",
        "timeframe": "5m",
        "open_time": open_time,
        "close_time": open_time + timedelta(minutes=5),
        "open": price,
        "high": max(price + 1, close_value),
        "low": min(price - 1, close_value),
        "close": close_value,
        "volume": 1000 + index,
        "is_closed": True,
    }


def test_dataset_ref_is_content_addressed_and_order_independent() -> None:
    candles = [candle(0), candle(1), candle(2)]
    first = DatasetRef.from_candles(
        candles,
        symbol="BTC/EUR",
        timeframe="5m",
        source="fixture",
        metadata={"gap_count": "0", "quality": "GOOD"},
    )
    second = DatasetRef.from_candles(
        list(reversed(candles)),
        symbol="BTC/EUR",
        timeframe="5m",
        source="fixture",
        metadata={"quality": "GOOD", "gap_count": "0"},
    )

    assert first == second
    assert first.version == f"sha256:{first.content_sha256}"
    assert first.candle_count == 3
    assert first.start_at == START
    assert first.end_at == START + timedelta(minutes=15)


def test_dataset_hash_changes_when_market_data_changes() -> None:
    base = [candle(0), candle(1), candle(2)]
    mutated = [candle(0), candle(1), candle(2, close="150")]

    first = DatasetRef.from_candles(
        base, symbol="BTC/EUR", timeframe="5m", source="fixture"
    )
    second = DatasetRef.from_candles(
        mutated, symbol="BTC/EUR", timeframe="5m", source="fixture"
    )

    assert first.content_sha256 != second.content_sha256
    assert first.dataset_id != second.dataset_id


def test_dataset_rejects_duplicate_or_naive_timestamps() -> None:
    duplicate = [candle(0), candle(0)]
    with pytest.raises(ValueError, match="duplicate"):
        DatasetRef.from_candles(
            duplicate, symbol="BTC/EUR", timeframe="5m", source="fixture"
        )

    naive = candle(0)
    naive["open_time"] = datetime(2026, 1, 1)
    naive["close_time"] = datetime(2026, 1, 1, 0, 5)
    with pytest.raises(ValueError, match="timezone-aware"):
        DatasetRef.from_candles(
            [naive], symbol="BTC/EUR", timeframe="5m", source="fixture"
        )


def test_dataset_rejects_symbol_or_timeframe_mismatch() -> None:
    wrong_symbol = candle(0)
    wrong_symbol["symbol"] = "ETH/EUR"
    with pytest.raises(ValueError, match="symbol"):
        DatasetRef.from_candles(
            [wrong_symbol], symbol="BTC/EUR", timeframe="5m", source="fixture"
        )

    wrong_timeframe = candle(0)
    wrong_timeframe["timeframe"] = "1h"
    with pytest.raises(ValueError, match="timeframe"):
        DatasetRef.from_candles(
            [wrong_timeframe], symbol="BTC/EUR", timeframe="5m", source="fixture"
        )
