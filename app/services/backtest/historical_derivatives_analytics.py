from __future__ import annotations

import csv
import hashlib
import json
from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable

from app.agents.models import RioContext
from app.market.exchange.kraken_futures import DerivativesPositioningSnapshot


HISTORICAL_DERIVATIVES_ANALYTICS_VERSION = "historical-derivatives-analytics-v1"
HISTORICAL_DERIVATIVES_ANALYTICS_SOURCE = "kraken_futures_historical_analytics"
HISTORICAL_DERIVATIVES_CONTEXT_BINDING_VERSION = "historical-derivatives-rio-v1"

CANONICAL_DERIVATIVES_FIELDS = (
    "symbol",
    "instrument",
    "observed_at",
    "available_at",
    "funding_rate",
    "open_interest",
    "open_interest_change_pct",
    "long_short_ratio",
)

_LIQUIDATION_MISSING = (
    "long_liquidations_notional",
    "short_liquidations_notional",
)


def _utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _parse_timestamp(raw: str, *, field: str) -> datetime:
    text = str(raw).strip()
    if not text:
        raise ValueError(f"{field} must not be blank")
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    return _utc(value, field=field)


def _parse_optional_decimal(
    raw: str | None,
    *,
    field: str,
    non_negative: bool = False,
) -> Decimal | None:
    text = "" if raw is None else str(raw).strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal") from exc
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    if non_negative and value < 0:
        raise ValueError(f"{field} must be >= 0")
    return value


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    if not value.is_finite():
        raise ValueError("decimal value must be finite")
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _iso(value: datetime) -> str:
    return _utc(value, field="datetime").isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class HistoricalDerivativesPoint:
    observed_at: datetime
    available_at: datetime
    funding_rate: Decimal | None
    open_interest: Decimal | None
    open_interest_change_pct: Decimal | None
    long_short_ratio: Decimal | None

    def __post_init__(self) -> None:
        observed = _utc(self.observed_at, field="observed_at")
        available = _utc(self.available_at, field="available_at")
        if available < observed:
            raise ValueError("available_at must be >= observed_at")
        for field_name in (
            "funding_rate",
            "open_interest",
            "open_interest_change_pct",
            "long_short_ratio",
        ):
            value = getattr(self, field_name)
            if value is not None and not value.is_finite():
                raise ValueError(f"{field_name} must be finite")
        if self.open_interest is not None and self.open_interest < 0:
            raise ValueError("open_interest must be >= 0")
        if self.long_short_ratio is not None and self.long_short_ratio < 0:
            raise ValueError("long_short_ratio must be >= 0")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "available_at", available)


@dataclass(frozen=True, slots=True)
class HistoricalDerivativesAnalyticsArchive:
    symbol: str
    instrument: str
    points: tuple[HistoricalDerivativesPoint, ...]
    dataset_fingerprint: str
    version: str = HISTORICAL_DERIVATIVES_ANALYTICS_VERSION
    source: str = HISTORICAL_DERIVATIVES_ANALYTICS_SOURCE

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        instrument = self.instrument.strip().upper()
        if symbol.count("/") != 1:
            raise ValueError("symbol must use canonical BASE/QUOTE form")
        if not instrument:
            raise ValueError("instrument must not be blank")
        if not self.points:
            raise ValueError("historical derivatives archive must not be empty")

        previous_observed: datetime | None = None
        previous_available: datetime | None = None
        for point in self.points:
            if previous_observed is not None and point.observed_at <= previous_observed:
                raise ValueError("observed_at must be strictly increasing")
            if previous_available is not None and point.available_at < previous_available:
                raise ValueError("available_at must be non-decreasing")
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
    def from_canonical_csv(
        cls,
        path: str | Path,
    ) -> "HistoricalDerivativesAnalyticsArchive":
        csv_path = Path(path)
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError("canonical derivatives CSV has no header")
            if tuple(reader.fieldnames) != CANONICAL_DERIVATIVES_FIELDS:
                raise ValueError(
                    "canonical derivatives CSV header must be exactly "
                    + ",".join(CANONICAL_DERIVATIVES_FIELDS)
                )
            rows = list(reader)

        if not rows:
            raise ValueError("canonical derivatives CSV has no data rows")

        symbol: str | None = None
        instrument: str | None = None
        points: list[HistoricalDerivativesPoint] = []
        canonical_rows: list[dict[str, str]] = []

        for row_number, row in enumerate(rows, start=2):
            row_symbol = str(row["symbol"]).strip().upper()
            row_instrument = str(row["instrument"]).strip().upper()
            if symbol is None:
                symbol = row_symbol
                instrument = row_instrument
            if row_symbol != symbol or row_instrument != instrument:
                raise ValueError(
                    f"row {row_number}: mixed symbol/instrument archives are forbidden"
                )

            point = HistoricalDerivativesPoint(
                observed_at=_parse_timestamp(
                    row["observed_at"],
                    field=f"row {row_number} observed_at",
                ),
                available_at=_parse_timestamp(
                    row["available_at"],
                    field=f"row {row_number} available_at",
                ),
                funding_rate=_parse_optional_decimal(
                    row["funding_rate"],
                    field=f"row {row_number} funding_rate",
                ),
                open_interest=_parse_optional_decimal(
                    row["open_interest"],
                    field=f"row {row_number} open_interest",
                    non_negative=True,
                ),
                open_interest_change_pct=_parse_optional_decimal(
                    row["open_interest_change_pct"],
                    field=f"row {row_number} open_interest_change_pct",
                ),
                long_short_ratio=_parse_optional_decimal(
                    row["long_short_ratio"],
                    field=f"row {row_number} long_short_ratio",
                    non_negative=True,
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
                    "open_interest": _decimal_text(point.open_interest),
                    "open_interest_change_pct": _decimal_text(
                        point.open_interest_change_pct
                    ),
                    "long_short_ratio": _decimal_text(point.long_short_ratio),
                }
            )

        assert symbol is not None
        assert instrument is not None
        payload = {
            "schema": HISTORICAL_DERIVATIVES_ANALYTICS_VERSION,
            "source": HISTORICAL_DERIVATIVES_ANALYTICS_SOURCE,
            "symbol": symbol,
            "instrument": instrument,
            "rows": canonical_rows,
        }
        fingerprint = hashlib.sha256(
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
            dataset_fingerprint=fingerprint,
        )

    @property
    def first_observed_at(self) -> datetime:
        return self.points[0].observed_at

    @property
    def last_observed_at(self) -> datetime:
        return self.points[-1].observed_at

    def metric_counts(self) -> dict[str, int]:
        return {
            "funding_rate": sum(
                point.funding_rate is not None for point in self.points
            ),
            "open_interest": sum(
                point.open_interest is not None for point in self.points
            ),
            "open_interest_change_pct": sum(
                point.open_interest_change_pct is not None for point in self.points
            ),
            "long_short_ratio": sum(
                point.long_short_ratio is not None for point in self.points
            ),
        }

    def first_metric_observed_at(self, metric: str) -> datetime | None:
        self._metric_getter(metric)
        for point in self.points:
            if getattr(point, metric) is not None:
                return point.observed_at
        return None

    def metric_at(
        self,
        metric: str,
        *,
        as_of: datetime,
        max_age: timedelta,
    ) -> tuple[HistoricalDerivativesPoint, Decimal] | None:
        getter = self._metric_getter(metric)
        cutoff = _utc(as_of, field="as_of")
        if max_age <= timedelta(0):
            raise ValueError("max_age must be > 0")

        available_times = tuple(point.available_at for point in self.points)
        index = bisect_right(available_times, cutoff) - 1
        while index >= 0:
            point = self.points[index]
            value = getter(point)
            if value is not None:
                if point.observed_at > cutoff:
                    raise ValueError(
                        "archive invariant broken: selected metric is in the future"
                    )
                if cutoff - point.observed_at > max_age:
                    return None
                return point, value
            index -= 1
        return None

    def positioning_snapshot_at(
        self,
        *,
        as_of: datetime,
        max_age: timedelta = timedelta(hours=2),
    ) -> DerivativesPositioningSnapshot | None:
        metric_names = (
            "funding_rate",
            "open_interest",
            "open_interest_change_pct",
            "long_short_ratio",
        )
        selected = {
            metric: self.metric_at(metric, as_of=as_of, max_age=max_age)
            for metric in metric_names
        }
        if not any(value is not None for value in selected.values()):
            return None

        observed_at = max(
            item[0].observed_at
            for item in selected.values()
            if item is not None
        )
        available_at = max(
            item[0].available_at
            for item in selected.values()
            if item is not None
        )
        missing = list(_LIQUIDATION_MISSING)
        for metric in metric_names:
            if selected[metric] is None:
                missing.append(metric)

        def value(metric: str) -> Decimal | None:
            item = selected[metric]
            return None if item is None else item[1]

        return DerivativesPositioningSnapshot(
            source=self.source,
            symbol=self.symbol,
            instrument=self.instrument,
            observed_at=observed_at,
            received_at=available_at,
            funding_rate=value("funding_rate"),
            open_interest=value("open_interest"),
            open_interest_change_pct=value("open_interest_change_pct"),
            long_short_ratio=value("long_short_ratio"),
            long_liquidations_notional=None,
            short_liquidations_notional=None,
            missing_fields=tuple(sorted(missing)),
        )

    def rio_context_from_snapshot(
        self,
        snapshot: DerivativesPositioningSnapshot,
    ) -> RioContext:
        if snapshot.source != self.source:
            raise ValueError("snapshot source does not match historical archive")
        if snapshot.symbol != self.symbol:
            raise ValueError("snapshot symbol does not match historical archive")
        if snapshot.instrument != self.instrument:
            raise ValueError("snapshot instrument does not match historical archive")

        core = (
            snapshot.funding_rate,
            snapshot.open_interest,
            snapshot.long_short_ratio,
        )
        present = sum(value is not None for value in core)
        if present == 3:
            quality = "RELIABLE"
        elif snapshot.available_metric_count > 0:
            quality = "DEGRADED"
        else:
            quality = "INSUFFICIENT"

        return RioContext(
            source=snapshot.source,
            instrument=snapshot.instrument,
            observed_at=snapshot.observed_at,
            is_stale=False,
            data_quality=quality,
            funding_rate=(
                None if snapshot.funding_rate is None else float(snapshot.funding_rate)
            ),
            open_interest=(
                None if snapshot.open_interest is None else float(snapshot.open_interest)
            ),
            open_interest_change_pct=(
                None
                if snapshot.open_interest_change_pct is None
                else float(snapshot.open_interest_change_pct)
            ),
            long_liquidations_notional=None,
            short_liquidations_notional=None,
            long_short_ratio=(
                None
                if snapshot.long_short_ratio is None
                else float(snapshot.long_short_ratio)
            ),
            missing_fields=snapshot.missing_fields,
        )

    def rio_context_at(
        self,
        *,
        as_of: datetime,
        max_age: timedelta = timedelta(hours=2),
    ) -> RioContext | None:
        snapshot = self.positioning_snapshot_at(
            as_of=as_of,
            max_age=max_age,
        )
        if snapshot is None:
            return None
        return self.rio_context_from_snapshot(snapshot)

    @staticmethod
    def _metric_getter(
        metric: str,
    ) -> Callable[[HistoricalDerivativesPoint], Decimal | None]:
        allowed = {
            "funding_rate",
            "open_interest",
            "open_interest_change_pct",
            "long_short_ratio",
        }
        if metric not in allowed:
            raise ValueError(f"unsupported derivatives metric: {metric}")
        return lambda point: getattr(point, metric)


def write_canonical_derivatives_csv(
    *,
    path: str | Path,
    symbol: str,
    instrument: str,
    rows: Iterable[HistoricalDerivativesPoint],
) -> HistoricalDerivativesAnalyticsArchive:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    canonical_symbol = symbol.strip().upper()
    canonical_instrument = instrument.strip().upper()

    frozen = tuple(rows)
    if not frozen:
        raise ValueError("rows must not be empty")

    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CANONICAL_DERIVATIVES_FIELDS,
        )
        writer.writeheader()
        for point in frozen:
            writer.writerow(
                {
                    "symbol": canonical_symbol,
                    "instrument": canonical_instrument,
                    "observed_at": _iso(point.observed_at),
                    "available_at": _iso(point.available_at),
                    "funding_rate": _decimal_text(point.funding_rate),
                    "open_interest": _decimal_text(point.open_interest),
                    "open_interest_change_pct": _decimal_text(
                        point.open_interest_change_pct
                    ),
                    "long_short_ratio": _decimal_text(point.long_short_ratio),
                }
            )

    return HistoricalDerivativesAnalyticsArchive.from_canonical_csv(output)
