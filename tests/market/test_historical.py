from datetime import timedelta, timezone
from pathlib import Path

import pytest

from app.market.historical import HistoricalImportError, import_candles_csv


def write_csv(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "candles.csv"
    path.write_text(content, encoding="utf-8")
    return path


def test_csv_import_sorts_rows_and_normalizes(tmp_path: Path):
    path = write_csv(
        tmp_path,
        "timestamp,open,high,low,close,volume\n"
        "2026-09-07T12:01:00Z,101,102,100,101.5,11\n"
        "2026-09-07T12:00:00Z,100,101,99,100.5,10\n",
    )
    result = import_candles_csv(
        path,
        symbol="BTCUSDT",
        timeframe="1m",
        candle_interval=timedelta(minutes=1),
    )
    assert len(result.candles) == 2
    assert result.candles[0].open_time.minute == 0
    assert result.candles[0].open_time.tzinfo == timezone.utc
    assert result.quality.is_valid is True


def test_csv_import_detects_gap(tmp_path: Path):
    path = write_csv(
        tmp_path,
        "timestamp,open,high,low,close,volume\n"
        "2026-09-07T12:00:00Z,100,101,99,100.5,10\n"
        "2026-09-07T12:03:00Z,101,102,100,101.5,11\n",
    )
    result = import_candles_csv(
        path,
        symbol="BTCUSDT",
        timeframe="1m",
        candle_interval=timedelta(minutes=1),
    )
    assert result.quality.gap_count == 2
    assert result.quality.is_valid is False


def test_csv_import_rejects_missing_columns(tmp_path: Path):
    path = write_csv(tmp_path, "timestamp,open,close\n1,100,101\n")
    with pytest.raises(HistoricalImportError, match="missing required columns"):
        import_candles_csv(
            path,
            symbol="BTCUSDT",
            timeframe="1m",
            candle_interval=timedelta(minutes=1),
        )


def test_csv_import_rejects_duplicate_timestamp(tmp_path: Path):
    path = write_csv(
        tmp_path,
        "timestamp,open,high,low,close,volume\n"
        "2026-09-07T12:00:00Z,100,101,99,100.5,10\n"
        "2026-09-07T12:00:00Z,100,101,99,100.5,10\n",
    )
    with pytest.raises(HistoricalImportError, match="duplicate"):
        import_candles_csv(
            path,
            symbol="BTCUSDT",
            timeframe="1m",
            candle_interval=timedelta(minutes=1),
        )
