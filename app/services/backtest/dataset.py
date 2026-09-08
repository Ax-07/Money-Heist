from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any

from .ids import stable_digest


def _read(candle: Any, *names: str, default: Any = None, required: bool = False) -> Any:
    if isinstance(candle, Mapping):
        for name in names:
            if name in candle:
                return candle[name]
    else:
        for name in names:
            if hasattr(candle, name):
                return getattr(candle, name)
    if required:
        raise ValueError(f"candle is missing required field; expected one of {names}")
    return default


def _canonical_datetime(value: Any, *, field: str) -> tuple[datetime, str]:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise ValueError(f"{field} must be a datetime or ISO-8601 string")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    utc_value = parsed.astimezone(UTC)
    return utc_value, utc_value.isoformat().replace("+00:00", "Z")


def _canonical_decimal(value: Any, *, field: str) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    if field == "volume" and number < 0:
        raise ValueError("volume cannot be negative")
    if field != "volume" and number <= 0:
        raise ValueError(f"{field} must be > 0")
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def canonical_candle_rows(
    candles: Sequence[Any],
    *,
    expected_symbol: str | None = None,
    expected_timeframe: str | None = None,
) -> tuple[dict[str, Any], ...]:
    rows: list[tuple[datetime, dict[str, Any]]] = []
    for candle in candles:
        candle_symbol = _read(candle, "symbol")
        candle_timeframe = _read(candle, "timeframe")
        if (
            candle_symbol is not None
            and expected_symbol is not None
            and str(candle_symbol).strip() != expected_symbol
        ):
            raise ValueError("candle symbol does not match dataset symbol")
        if (
            candle_timeframe is not None
            and expected_timeframe is not None
            and str(candle_timeframe).strip() != expected_timeframe
        ):
            raise ValueError("candle timeframe does not match dataset timeframe")

        raw_open_time = _read(candle, "open_time", "timestamp", required=True)
        open_time, open_text = _canonical_datetime(raw_open_time, field="open_time")
        raw_close_time = _read(candle, "close_time", default=raw_open_time)
        close_time, close_text = _canonical_datetime(raw_close_time, field="close_time")
        if close_time <= open_time:
            raise ValueError("candle close_time must be after open_time")

        row = {
            "open_time": open_text,
            "close_time": close_text,
            "open": _canonical_decimal(_read(candle, "open", required=True), field="open"),
            "high": _canonical_decimal(_read(candle, "high", required=True), field="high"),
            "low": _canonical_decimal(_read(candle, "low", required=True), field="low"),
            "close": _canonical_decimal(_read(candle, "close", required=True), field="close"),
            "volume": _canonical_decimal(_read(candle, "volume", required=True), field="volume"),
            "is_closed": bool(_read(candle, "is_closed", default=True)),
        }
        high = Decimal(row["high"])
        low = Decimal(row["low"])
        open_price = Decimal(row["open"])
        close_price = Decimal(row["close"])
        if high < low:
            raise ValueError("candle high must be >= low")
        if high < max(open_price, close_price):
            raise ValueError("candle high is lower than open/close")
        if low > min(open_price, close_price):
            raise ValueError("candle low is greater than open/close")
        rows.append((open_time, row))

    if not rows:
        raise ValueError("dataset requires at least one candle")

    rows.sort(key=lambda item: item[0])
    open_times = [item[0] for item in rows]
    if len(open_times) != len(set(open_times)):
        raise ValueError("dataset cannot contain duplicate candle open_time values")
    return tuple(item[1] for item in rows)


def _freeze_metadata(metadata: Mapping[str, str]) -> Mapping[str, str]:
    normalized: dict[str, str] = {}
    for key, value in metadata.items():
        key_text = str(key).strip()
        value_text = str(value).strip()
        if not key_text:
            raise ValueError("dataset metadata keys must not be empty")
        normalized[key_text] = value_text
    return MappingProxyType(dict(sorted(normalized.items())))


@dataclass(frozen=True, slots=True)
class DatasetRef:
    """Immutable content-addressed identity for one selected historical dataset."""

    dataset_id: str
    version: str
    content_sha256: str
    symbol: str
    timeframe: str
    source: str
    candle_count: int
    start_at: datetime
    end_at: datetime
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("dataset_id", "version", "symbol", "timeframe", "source"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be empty")
        digest = self.content_sha256.lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("content_sha256 must be a 64-character hexadecimal digest")
        if self.candle_count <= 0:
            raise ValueError("candle_count must be > 0")
        start_at = self._as_utc(self.start_at, "start_at")
        end_at = self._as_utc(self.end_at, "end_at")
        if end_at < start_at:
            raise ValueError("end_at cannot precede start_at")
        object.__setattr__(self, "content_sha256", digest)
        object.__setattr__(self, "start_at", start_at)
        object.__setattr__(self, "end_at", end_at)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    @classmethod
    def from_candles(
        cls,
        candles: Sequence[Any],
        *,
        symbol: str,
        timeframe: str,
        source: str,
        metadata: Mapping[str, str] | None = None,
    ) -> DatasetRef:
        symbol = symbol.strip()
        timeframe = timeframe.strip()
        source = source.strip()
        for field_name, value in (
            ("symbol", symbol),
            ("timeframe", timeframe),
            ("source", source),
        ):
            if not value:
                raise ValueError(f"{field_name} must not be empty")

        rows = canonical_candle_rows(
            candles,
            expected_symbol=symbol,
            expected_timeframe=timeframe,
        )
        digest = stable_digest(
            {
                "schema": "money-heist.dataset.v1",
                "symbol": symbol,
                "timeframe": timeframe,
                "source": source,
                "candles": rows,
            }
        )
        start_at, _ = _canonical_datetime(rows[0]["open_time"], field="start_at")
        end_at, _ = _canonical_datetime(rows[-1]["close_time"], field="end_at")
        return cls(
            dataset_id=f"{symbol}:{timeframe}:{digest[:16]}",
            version=f"sha256:{digest}",
            content_sha256=digest,
            symbol=symbol,
            timeframe=timeframe,
            source=source,
            candle_count=len(rows),
            start_at=start_at,
            end_at=end_at,
            metadata=metadata or {},
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "content_sha256": self.content_sha256,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "source": self.source,
            "candle_count": self.candle_count,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "metadata": self.metadata,
        }

    @staticmethod
    def _as_utc(value: datetime, field_name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value.astimezone(UTC)
