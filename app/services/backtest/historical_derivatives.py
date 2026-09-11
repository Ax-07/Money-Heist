from __future__ import annotations

import csv
import hashlib
import json
from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from app.agents.models import RioContext
from app.market.exchange.kraken_futures import DerivativesPositioningSnapshot


HISTORICAL_DERIVATIVES_ARCHIVE_VERSION = "historical-derivatives-funding-v1"
HISTORICAL_DERIVATIVES_SOURCE = "kraken_futures_historical_funding"

CANONICAL_FUNDING_FIELDS = (
    "symbol",
    "instrument",
    "observed_at",
    "available_at",
    "funding_rate",
)

_RIO_FUNDING_ONLY_MISSING_FIELDS = (
    "long_liquidations_notional",
    "long_short_ratio",
    "open_interest",
    "open_interest_change_pct",
    "short_liquidations_notional",
)

_TIMESTAMP_CANDIDATES = (
    "timestamp",
    "time",
    "date",
    "datetime",
    "funding_time",
    "funding_timestamp",
    "fundingtime",
    "fundingtimestamp",
)
_FUNDING_CANDIDATES = (
    "funding_rate",
    "fundingrate",
    "funding",
    "rate",
)


def _utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _utc(value, field="datetime").isoformat().replace("+00:00", "Z")


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("funding_rate must be finite")
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _parse_decimal(raw: str, *, field: str) -> Decimal:
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal") from exc
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    return value


def _parse_timestamp(raw: str, *, field: str) -> datetime:
    text = str(raw).strip()
    if not text:
        raise ValueError(f"{field} must not be blank")

    try:
        numeric = Decimal(text)
    except InvalidOperation:
        numeric = None

    if numeric is not None and numeric.is_finite():
        absolute = abs(numeric)
        if absolute >= Decimal("1000000000000000"):
            seconds = numeric / Decimal("1000000")
        elif absolute >= Decimal("1000000000000"):
            seconds = numeric / Decimal("1000")
        else:
            seconds = numeric
        return datetime.fromtimestamp(float(seconds), tz=UTC)

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} is not ISO-8601 or Unix epoch") from exc
    return _utc(parsed, field=field)


def _normalize_column(value: str) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def _detect_column(
    fieldnames: Iterable[str],
    *,
    explicit: str | None,
    candidates: tuple[str, ...],
    label: str,
) -> str:
    names = tuple(str(item) for item in fieldnames)
    if explicit is not None:
        if explicit not in names:
            raise ValueError(
                f"{label} column {explicit!r} not found; available={names!r}"
            )
        return explicit

    normalized: dict[str, list[str]] = {}
    for name in names:
        normalized.setdefault(_normalize_column(name), []).append(name)

    matches: list[str] = []
    for candidate in candidates:
        matches.extend(normalized.get(candidate, ()))

    unique = tuple(dict.fromkeys(matches))
    if len(unique) != 1:
        raise ValueError(
            f"could not uniquely detect {label} column; "
            f"available={names!r}; pass the explicit column name"
        )
    return unique[0]


@dataclass(frozen=True, slots=True)
class HistoricalFundingPoint:
    observed_at: datetime
    available_at: datetime
    funding_rate: Decimal

    def __post_init__(self) -> None:
        observed = _utc(self.observed_at, field="observed_at")
        available = _utc(self.available_at, field="available_at")
        if available < observed:
            raise ValueError("available_at must be >= observed_at")
        if not self.funding_rate.is_finite():
            raise ValueError("funding_rate must be finite")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "available_at", available)


@dataclass(frozen=True, slots=True)
class HistoricalFundingArchive:
    symbol: str
    instrument: str
    points: tuple[HistoricalFundingPoint, ...]
    dataset_fingerprint: str
    version: str = HISTORICAL_DERIVATIVES_ARCHIVE_VERSION
    source: str = HISTORICAL_DERIVATIVES_SOURCE

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        instrument = self.instrument.strip().upper()
        if symbol.count("/") != 1:
            raise ValueError("symbol must use canonical BASE/QUOTE form")
        if not instrument:
            raise ValueError("instrument must not be blank")
        if not self.points:
            raise ValueError("historical funding archive must not be empty")

        previous_observed: datetime | None = None
        previous_available: datetime | None = None
        seen: set[tuple[datetime, datetime]] = set()
        for point in self.points:
            key = (point.observed_at, point.available_at)
            if key in seen:
                raise ValueError("duplicate funding point timestamp")
            seen.add(key)
            if (
                previous_observed is not None
                and point.observed_at <= previous_observed
            ):
                raise ValueError("funding observed_at must be strictly increasing")
            if (
                previous_available is not None
                and point.available_at < previous_available
            ):
                raise ValueError("funding available_at must be non-decreasing")
            previous_observed = point.observed_at
            previous_available = point.available_at

        fingerprint = self.dataset_fingerprint.strip().lower()
        if len(fingerprint) != 64 or any(
            char not in "0123456789abcdef" for char in fingerprint
        ):
            raise ValueError("dataset_fingerprint must be SHA-256 hex")

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "instrument", instrument)
        object.__setattr__(self, "dataset_fingerprint", fingerprint)

    @classmethod
    def from_canonical_csv(cls, path: str | Path) -> "HistoricalFundingArchive":
        csv_path = Path(path)
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError("canonical funding CSV has no header")
            if tuple(reader.fieldnames) != CANONICAL_FUNDING_FIELDS:
                raise ValueError(
                    "canonical funding CSV header must be exactly "
                    + ",".join(CANONICAL_FUNDING_FIELDS)
                )

            rows = list(reader)

        if not rows:
            raise ValueError("canonical funding CSV has no data rows")

        symbol: str | None = None
        instrument: str | None = None
        points: list[HistoricalFundingPoint] = []
        canonical_rows: list[dict[str, str]] = []

        for index, row in enumerate(rows, start=2):
            row_symbol = str(row["symbol"]).strip().upper()
            row_instrument = str(row["instrument"]).strip().upper()
            if symbol is None:
                symbol = row_symbol
                instrument = row_instrument
            if row_symbol != symbol or row_instrument != instrument:
                raise ValueError(
                    f"row {index}: mixed symbol/instrument archives are forbidden"
                )

            point = HistoricalFundingPoint(
                observed_at=_parse_timestamp(
                    row["observed_at"],
                    field=f"row {index} observed_at",
                ),
                available_at=_parse_timestamp(
                    row["available_at"],
                    field=f"row {index} available_at",
                ),
                funding_rate=_parse_decimal(
                    row["funding_rate"],
                    field=f"row {index} funding_rate",
                ),
            )
            points.append(point)
            canonical_rows.append(
                {
                    "symbol": row_symbol,
                    "instrument": row_instrument,
                    "observed_at": _iso(point.observed_at),
                    "available_at": _iso(point.available_at),
                    "funding_rate": _decimal_text(point.funding_rate),
                }
            )

        assert symbol is not None
        assert instrument is not None
        payload = {
            "schema": HISTORICAL_DERIVATIVES_ARCHIVE_VERSION,
            "source": HISTORICAL_DERIVATIVES_SOURCE,
            "symbol": symbol,
            "instrument": instrument,
            "rows": canonical_rows,
        }
        digest = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()

        return cls(
            symbol=symbol,
            instrument=instrument,
            points=tuple(points),
            dataset_fingerprint=digest,
        )

    @property
    def first_observed_at(self) -> datetime:
        return self.points[0].observed_at

    @property
    def last_observed_at(self) -> datetime:
        return self.points[-1].observed_at

    def point_at(
        self,
        *,
        as_of: datetime,
        max_age: timedelta,
    ) -> HistoricalFundingPoint | None:
        cutoff = _utc(as_of, field="as_of")
        if max_age <= timedelta(0):
            raise ValueError("max_age must be > 0")

        available_times = tuple(point.available_at for point in self.points)
        index = bisect_right(available_times, cutoff) - 1
        if index < 0:
            return None

        point = self.points[index]
        if point.observed_at > cutoff:
            raise ValueError(
                "archive invariant broken: selected observation is in the future"
            )
        if cutoff - point.observed_at > max_age:
            return None
        return point

    def positioning_snapshot_at(
        self,
        *,
        as_of: datetime,
        max_age: timedelta = timedelta(hours=2),
    ) -> DerivativesPositioningSnapshot | None:
        point = self.point_at(as_of=as_of, max_age=max_age)
        if point is None:
            return None
        return DerivativesPositioningSnapshot(
            source=self.source,
            symbol=self.symbol,
            instrument=self.instrument,
            observed_at=point.observed_at,
            received_at=point.available_at,
            funding_rate=point.funding_rate,
            open_interest=None,
            open_interest_change_pct=None,
            long_short_ratio=None,
            long_liquidations_notional=None,
            short_liquidations_notional=None,
            missing_fields=_RIO_FUNDING_ONLY_MISSING_FIELDS,
        )

    def rio_context_at(
        self,
        *,
        as_of: datetime,
        max_age: timedelta = timedelta(hours=2),
    ) -> RioContext | None:
        snapshot = self.positioning_snapshot_at(as_of=as_of, max_age=max_age)
        if snapshot is None:
            return None
        return RioContext(
            source=snapshot.source,
            instrument=snapshot.instrument,
            observed_at=snapshot.observed_at,
            is_stale=False,
            data_quality="DEGRADED",
            funding_rate=float(snapshot.funding_rate),
            open_interest=None,
            open_interest_change_pct=None,
            long_liquidations_notional=None,
            short_liquidations_notional=None,
            long_short_ratio=None,
            missing_fields=snapshot.missing_fields,
        )


def normalize_kraken_funding_csv(
    *,
    input_path: str | Path,
    output_path: str | Path,
    symbol: str,
    instrument: str,
    timestamp_column: str | None = None,
    funding_column: str | None = None,
    availability_lag: timedelta = timedelta(0),
) -> HistoricalFundingArchive:
    if availability_lag < timedelta(0):
        raise ValueError("availability_lag must be >= 0")

    raw_path = Path(input_path)
    output = Path(output_path)

    with raw_path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        if reader.fieldnames is None:
            raise ValueError("raw Kraken funding CSV has no header")

        timestamp_name = _detect_column(
            reader.fieldnames,
            explicit=timestamp_column,
            candidates=_TIMESTAMP_CANDIDATES,
            label="timestamp",
        )
        funding_name = _detect_column(
            reader.fieldnames,
            explicit=funding_column,
            candidates=_FUNDING_CANDIDATES,
            label="funding",
        )

        parsed: list[HistoricalFundingPoint] = []
        for row_index, row in enumerate(reader, start=2):
            if not any(str(value or "").strip() for value in row.values()):
                continue
            observed = _parse_timestamp(
                str(row.get(timestamp_name, "")),
                field=f"row {row_index} {timestamp_name}",
            )
            funding = _parse_decimal(
                str(row.get(funding_name, "")),
                field=f"row {row_index} {funding_name}",
            )
            parsed.append(
                HistoricalFundingPoint(
                    observed_at=observed,
                    available_at=observed + availability_lag,
                    funding_rate=funding,
                )
            )

    if not parsed:
        raise ValueError("raw Kraken funding CSV has no usable rows")

    parsed.sort(key=lambda item: (item.observed_at, item.available_at))
    for previous, current in zip(parsed, parsed[1:], strict=False):
        if current.observed_at <= previous.observed_at:
            raise ValueError("raw Kraken funding timestamps must be unique")

    output.parent.mkdir(parents=True, exist_ok=True)
    canonical_symbol = symbol.strip().upper()
    canonical_instrument = instrument.strip().upper()
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_FUNDING_FIELDS)
        writer.writeheader()
        for point in parsed:
            writer.writerow(
                {
                    "symbol": canonical_symbol,
                    "instrument": canonical_instrument,
                    "observed_at": _iso(point.observed_at),
                    "available_at": _iso(point.available_at),
                    "funding_rate": _decimal_text(point.funding_rate),
                }
            )

    return HistoricalFundingArchive.from_canonical_csv(output)
