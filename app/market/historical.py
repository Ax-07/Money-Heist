from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .models import Candle, HistoricalImportResult
from .quality import (
    MarketDataValidationError,
    build_quality,
    count_gaps,
    validate_candle_series,
)


class HistoricalImportError(ValueError):
    """Erreur contrôlée lors d'un import historique."""


_REQUIRED_COLUMNS = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
}


def _parse_timestamp(raw: str) -> datetime:
    raw = raw.strip()
    if not raw:
        raise HistoricalImportError("empty timestamp")

    # Unix seconds or milliseconds.
    try:
        numeric = Decimal(raw)
    except InvalidOperation:
        numeric = None

    if numeric is not None:
        value = float(numeric)
        if abs(value) >= 100_000_000_000:
            value /= 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)

    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HistoricalImportError(f"invalid timestamp: {raw!r}") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HistoricalImportError("historical timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _parse_decimal(raw: str, field: str) -> Decimal:
    try:
        return Decimal(raw.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise HistoricalImportError(f"invalid decimal for {field}: {raw!r}") from exc


def import_candles_csv(
    path: str | Path,
    *,
    symbol: str,
    timeframe: str,
    source: str = "historical_csv",
    candle_interval: timedelta,
) -> HistoricalImportResult:
    """Importe un CSV OHLCV simple vers les modèles internes normalisés.

    Le CSV doit contenir : timestamp, open, high, low, close, volume.
    ``timestamp`` accepte ISO-8601 timezone-aware, Unix secondes ou millisecondes.
    Les lignes sont triées chronologiquement avant validation.
    """

    if candle_interval <= timedelta(0):
        raise ValueError("candle_interval must be > 0")

    csv_path = Path(path)
    try:
        handle = csv_path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise HistoricalImportError(f"cannot open CSV: {csv_path}") from exc

    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise HistoricalImportError("CSV has no header")

        header = {name.strip().lower() for name in reader.fieldnames}
        missing = sorted(_REQUIRED_COLUMNS - header)
        if missing:
            raise HistoricalImportError(
                f"CSV missing required columns: {', '.join(missing)}"
            )

        rows: list[Candle] = []
        for line_number, raw_row in enumerate(reader, start=2):
            row = {
                (key or "").strip().lower(): value
                for key, value in raw_row.items()
            }
            try:
                open_time = _parse_timestamp(row["timestamp"])
                rows.append(
                    Candle(
                        symbol=symbol,
                        timeframe=timeframe,
                        open_time=open_time,
                        close_time=open_time + candle_interval,
                        open=_parse_decimal(row["open"], "open"),
                        high=_parse_decimal(row["high"], "high"),
                        low=_parse_decimal(row["low"], "low"),
                        close=_parse_decimal(row["close"], "close"),
                        volume=_parse_decimal(row["volume"], "volume"),
                        is_closed=True,
                    )
                )
            except (KeyError, ValueError) as exc:
                raise HistoricalImportError(
                    f"invalid CSV row at line {line_number}: {exc}"
                ) from exc

    rows.sort(key=lambda candle: candle.open_time)

    try:
        series = validate_candle_series(rows, expected_interval=candle_interval)
        gap_count = count_gaps(series, expected_interval=candle_interval)
    except MarketDataValidationError as exc:
        raise HistoricalImportError(str(exc)) from exc

    quality = build_quality(stale=False, gap_count=gap_count)
    return HistoricalImportResult(
        symbol=symbol,
        timeframe=timeframe,
        source=source,
        candles=series,
        quality=quality,
    )
