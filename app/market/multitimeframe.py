from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from .models import Candle


class MultiTimeframeError(ValueError):
    """Raised when deterministic multi-timeframe construction is unsafe."""


_TIMEFRAME_RE = re.compile(r"^(?P<count>[1-9][0-9]*)(?P<unit>[mhd])$")
_UNIT_SECONDS = {
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
}


def timeframe_interval(timeframe: str) -> timedelta:
    """Return a fixed UTC interval for supported candle timeframes."""

    normalized = timeframe.strip().lower()
    match = _TIMEFRAME_RE.fullmatch(normalized)
    if match is None:
        raise MultiTimeframeError(
            f"unsupported timeframe {timeframe!r}; expected forms like "
            "1m, 15m, 1h, 4h, 1d"
        )
    seconds = int(match.group("count")) * _UNIT_SECONDS[match.group("unit")]
    return timedelta(seconds=seconds)


def _as_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MultiTimeframeError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _validate_source(candles: Sequence[Candle]) -> tuple[Candle, ...]:
    series = tuple(candles)
    if not series:
        raise MultiTimeframeError("source candles must not be empty")

    symbol = series[0].symbol
    timeframe = series[0].timeframe
    interval = timeframe_interval(timeframe)

    previous: Candle | None = None
    for candle in series:
        if candle.symbol != symbol:
            raise MultiTimeframeError("source candles must contain one symbol")
        if candle.timeframe != timeframe:
            raise MultiTimeframeError("source candles must contain one timeframe")
        if not candle.is_closed:
            raise MultiTimeframeError("source candles must all be closed")
        if candle.close_time - candle.open_time != interval:
            raise MultiTimeframeError(
                "source candle duration does not match its timeframe"
            )

        if previous is not None:
            if candle.open_time <= previous.open_time:
                raise MultiTimeframeError(
                    "source candles must be strictly chronological"
                )
            if candle.open_time != previous.open_time + interval:
                raise MultiTimeframeError(
                    "source candles contain a gap or are not exactly contiguous"
                )
            if previous.close_time != candle.open_time:
                raise MultiTimeframeError(
                    "source candle close/open boundaries are not contiguous"
                )
        previous = candle

    return series


def _visible_source(
    candles: Sequence[Candle],
    *,
    as_of: datetime | None,
) -> tuple[Candle, ...]:
    """Return and validate only the source prefix visible at ``as_of``.

    Future candles are deliberately not validated. This prevents a future gap
    or malformed future row from changing the outcome of an earlier replay
    decision through an exception side-channel.
    """

    raw = tuple(candles)
    if not raw:
        raise MultiTimeframeError("source candles must not be empty")
    if as_of is None:
        return _validate_source(raw)

    cutoff = _as_utc(as_of, field="as_of")
    visible: list[Candle] = []
    for candle in raw:
        if candle.close_time <= cutoff:
            visible.append(candle)
            continue
        break

    if not visible:
        return ()
    return _validate_source(visible)


def _bucket_start(value: datetime, interval: timedelta) -> datetime:
    seconds = int(interval.total_seconds())
    epoch_seconds = int(value.timestamp())
    bucket_epoch = (epoch_seconds // seconds) * seconds
    return datetime.fromtimestamp(bucket_epoch, tz=UTC)


def _aggregate_bucket(
    bucket: Sequence[Candle],
    *,
    target_timeframe: str,
    bucket_start: datetime,
    target_interval: timedelta,
) -> Candle:
    first = bucket[0]
    last = bucket[-1]
    return Candle(
        symbol=first.symbol,
        timeframe=target_timeframe,
        open_time=bucket_start,
        close_time=bucket_start + target_interval,
        open=first.open,
        high=max(item.high for item in bucket),
        low=min(item.low for item in bucket),
        close=last.close,
        volume=sum((item.volume for item in bucket), start=Decimal("0")),
        is_closed=True,
    )


def resample_closed_candles(
    candles: Sequence[Candle],
    *,
    target_timeframe: str,
    as_of: datetime | None = None,
) -> tuple[Candle, ...]:
    """Resample a contiguous closed series into complete UTC-aligned buckets.

    Only the source prefix whose ``close_time <= as_of`` is visible and
    validated. Incomplete edge buckets are dropped. An internal visible-source
    gap is rejected rather than silently manufacturing a higher-timeframe
    candle.
    """

    series = _visible_source(candles, as_of=as_of)
    if not series:
        return ()

    source_timeframe = series[0].timeframe
    source_interval = timeframe_interval(source_timeframe)
    target_timeframe = target_timeframe.strip().lower()
    target_interval = timeframe_interval(target_timeframe)

    source_seconds = int(source_interval.total_seconds())
    target_seconds = int(target_interval.total_seconds())
    if target_seconds < source_seconds:
        raise MultiTimeframeError(
            "target timeframe cannot be smaller than source timeframe"
        )
    if target_seconds % source_seconds != 0:
        raise MultiTimeframeError(
            "target timeframe must be an exact multiple of source timeframe"
        )

    if target_seconds == source_seconds:
        return series

    expected_count = target_seconds // source_seconds
    grouped: dict[datetime, list[Candle]] = {}
    for candle in series:
        start = _bucket_start(candle.open_time, target_interval)
        grouped.setdefault(start, []).append(candle)

    output: list[Candle] = []
    for start in sorted(grouped):
        bucket = grouped[start]
        end = start + target_interval

        # Dataset/as_of boundaries may cut through a bucket. Such buckets are
        # intentionally omitted; only fully closed UTC buckets are emitted.
        if len(bucket) != expected_count:
            continue
        if bucket[0].open_time != start or bucket[-1].close_time != end:
            continue

        output.append(
            _aggregate_bucket(
                bucket,
                target_timeframe=target_timeframe,
                bucket_start=start,
                target_interval=target_interval,
            )
        )

    return tuple(output)


def _canonical_candle(candle: Candle) -> dict[str, str | bool]:
    return {
        "symbol": candle.symbol,
        "timeframe": candle.timeframe,
        "open_time": candle.open_time.isoformat().replace("+00:00", "Z"),
        "close_time": candle.close_time.isoformat().replace("+00:00", "Z"),
        "open": format(candle.open.normalize(), "f"),
        "high": format(candle.high.normalize(), "f"),
        "low": format(candle.low.normalize(), "f"),
        "close": format(candle.close.normalize(), "f"),
        "volume": (
            "0"
            if candle.volume == 0
            else format(candle.volume.normalize(), "f")
        ),
        "is_closed": candle.is_closed,
    }


def _series_fingerprint(candles: Sequence[Candle]) -> str:
    hasher = hashlib.sha256()
    hasher.update(b"money-heist.visible-source-candles.v1\n")
    for candle in candles:
        encoded = json.dumps(
            _canonical_candle(candle),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        hasher.update(encoded)
        hasher.update(b"\n")
    return hasher.hexdigest()


def _fingerprint(
    *,
    source_timeframe: str,
    source_fingerprint: str,
    source_candle_count: int,
    target_timeframes: tuple[str, ...],
    as_of: datetime,
    policy_version: str,
    candles_by_timeframe: Mapping[str, tuple[Candle, ...]],
) -> str:
    payload = {
        "schema": "money-heist.historical-mtf-slice.v1",
        "policy_version": policy_version,
        "source_timeframe": source_timeframe,
        "source_fingerprint": source_fingerprint,
        "source_candle_count": source_candle_count,
        "target_timeframes": target_timeframes,
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "candles": {
            timeframe: [_canonical_candle(item) for item in series]
            for timeframe, series in sorted(candles_by_timeframe.items())
        },
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class HistoricalMultiTimeframeSlice:
    """Immutable, fingerprinted historical market view available at one time."""

    symbol: str
    source_timeframe: str
    source_candle_count: int
    source_fingerprint: str
    target_timeframes: tuple[str, ...]
    as_of: datetime
    policy_version: str
    candles_by_timeframe: Mapping[str, tuple[Candle, ...]]
    fingerprint: str

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.source_candle_count <= 0:
            raise ValueError("source_candle_count must be > 0")
        if not self.policy_version.strip():
            raise ValueError("policy_version must not be empty")
        as_of = _as_utc(self.as_of, field="as_of")
        frozen = MappingProxyType(
            {
                key: tuple(value)
                for key, value in sorted(self.candles_by_timeframe.items())
            }
        )
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "candles_by_timeframe", frozen)


def build_historical_mtf_slice(
    candles: Sequence[Candle],
    *,
    as_of: datetime,
    target_timeframes: Sequence[str] = ("15m", "1h", "4h", "1d"),
    policy_version: str = "mtf-utc-closed-v1",
) -> HistoricalMultiTimeframeSlice:
    """Build a deterministic historical MTF view without look-ahead."""

    cutoff = _as_utc(as_of, field="as_of")
    visible = _visible_source(candles, as_of=cutoff)
    if not visible:
        raise MultiTimeframeError("no source candles are available at as_of")

    policy_version = policy_version.strip()
    if not policy_version:
        raise MultiTimeframeError("policy_version must not be empty")

    normalized_targets = tuple(
        timeframe.strip().lower() for timeframe in target_timeframes
    )
    if not normalized_targets:
        raise MultiTimeframeError("target_timeframes must not be empty")
    if any(not timeframe for timeframe in normalized_targets):
        raise MultiTimeframeError("target_timeframes must not contain blanks")
    if len(set(normalized_targets)) != len(normalized_targets):
        raise MultiTimeframeError("target_timeframes must be unique")

    source_timeframe = visible[0].timeframe
    source_interval = timeframe_interval(source_timeframe)
    for target in normalized_targets:
        target_interval = timeframe_interval(target)
        if target_interval < source_interval:
            raise MultiTimeframeError(
                f"target timeframe {target} is smaller than source "
                f"{source_timeframe}"
            )
        if (
            int(target_interval.total_seconds())
            % int(source_interval.total_seconds())
            != 0
        ):
            raise MultiTimeframeError(
                f"target timeframe {target} is not divisible by source "
                f"{source_timeframe}"
            )

    built = {
        target: resample_closed_candles(
            visible,
            target_timeframe=target,
        )
        for target in normalized_targets
    }
    frozen = MappingProxyType(dict(sorted(built.items())))
    source_fingerprint = _series_fingerprint(visible)
    fingerprint = _fingerprint(
        source_timeframe=source_timeframe,
        source_fingerprint=source_fingerprint,
        source_candle_count=len(visible),
        target_timeframes=normalized_targets,
        as_of=cutoff,
        policy_version=policy_version,
        candles_by_timeframe=frozen,
    )
    return HistoricalMultiTimeframeSlice(
        symbol=visible[0].symbol,
        source_timeframe=source_timeframe,
        source_candle_count=len(visible),
        source_fingerprint=source_fingerprint,
        target_timeframes=normalized_targets,
        as_of=cutoff,
        policy_version=policy_version,
        candles_by_timeframe=frozen,
        fingerprint=fingerprint,
    )


@dataclass(frozen=True, slots=True)
class HistoricalMultiTimeframeCursorState:
    """Compact immutable state of one incremental historical MTF cursor."""

    symbol: str
    source_timeframe: str
    source_candle_count: int
    target_timeframes: tuple[str, ...]
    as_of: datetime
    policy_version: str
    source_fingerprint: str
    cursor_fingerprint: str
    candle_counts: tuple[tuple[str, int], ...]
    latest_close_times: tuple[tuple[str, datetime], ...]


class HistoricalMultiTimeframeCursor:
    """Incrementally build closed UTC MTF candles from one source stream."""

    def __init__(
        self,
        *,
        source_timeframe: str,
        target_timeframes: Sequence[str] = ("15m", "1h", "4h", "1d"),
        policy_version: str = "mtf-utc-closed-v1",
    ) -> None:
        self.source_timeframe = source_timeframe.strip().lower()
        self.source_interval = timeframe_interval(self.source_timeframe)
        self.target_timeframes = tuple(
            item.strip().lower() for item in target_timeframes
        )
        self.policy_version = policy_version.strip()

        if not self.target_timeframes:
            raise MultiTimeframeError("target_timeframes must not be empty")
        if any(not item for item in self.target_timeframes):
            raise MultiTimeframeError(
                "target_timeframes must not contain blanks"
            )
        if len(set(self.target_timeframes)) != len(self.target_timeframes):
            raise MultiTimeframeError("target_timeframes must be unique")
        if not self.policy_version:
            raise MultiTimeframeError("policy_version must not be empty")

        source_seconds = int(self.source_interval.total_seconds())
        self._target_intervals: dict[str, timedelta] = {}
        self._expected_counts: dict[str, int] = {}
        for target in self.target_timeframes:
            interval = timeframe_interval(target)
            seconds = int(interval.total_seconds())
            if seconds < source_seconds:
                raise MultiTimeframeError(
                    f"target timeframe {target} is smaller than source "
                    f"{self.source_timeframe}"
                )
            if seconds % source_seconds != 0:
                raise MultiTimeframeError(
                    f"target timeframe {target} is not divisible by source "
                    f"{self.source_timeframe}"
                )
            self._target_intervals[target] = interval
            self._expected_counts[target] = seconds // source_seconds

        self._symbol: str | None = None
        self._last_source: Candle | None = None
        self._source_count = 0
        self._as_of: datetime | None = None
        self._series: dict[str, list[Candle]] = {
            target: [] for target in self.target_timeframes
        }
        self._pending: dict[str, tuple[datetime, list[Candle]] | None] = {
            target: None for target in self.target_timeframes
        }

        self._source_hasher = hashlib.sha256()
        self._source_hasher.update(
            b"money-heist.visible-source-candles.v1\n"
        )
        self._target_hashers: dict[str, Any] = {}
        for target in self.target_timeframes:
            hasher = hashlib.sha256()
            hasher.update(
                (
                    "money-heist.incremental-mtf-series.v1:"
                    f"{target}\n"
                ).encode("utf-8")
            )
            self._target_hashers[target] = hasher

    @property
    def source_candle_count(self) -> int:
        return self._source_count

    @property
    def as_of(self) -> datetime | None:
        return self._as_of

    def series(self, timeframe: str) -> tuple[Candle, ...]:
        key = timeframe.strip().lower()
        if key not in self._series:
            raise MultiTimeframeError(
                f"timeframe {timeframe!r} is not configured on this cursor"
            )
        return tuple(self._series[key])

    def push(self, candle: Candle) -> tuple[str, ...]:
        """Consume one next closed source candle and return emitted timeframes."""

        if candle.timeframe != self.source_timeframe:
            raise MultiTimeframeError(
                "cursor source candle timeframe does not match configuration"
            )
        if not candle.is_closed:
            raise MultiTimeframeError(
                "cursor accepts closed source candles only"
            )
        if candle.close_time - candle.open_time != self.source_interval:
            raise MultiTimeframeError(
                "source candle duration does not match cursor timeframe"
            )

        if self._symbol is None:
            self._symbol = candle.symbol
        elif candle.symbol != self._symbol:
            raise MultiTimeframeError(
                "cursor source candles must contain one symbol"
            )

        if self._last_source is not None:
            expected_open = self._last_source.open_time + self.source_interval
            if candle.open_time != expected_open:
                raise MultiTimeframeError(
                    "cursor source candles contain a gap or are out of order"
                )
            if self._last_source.close_time != candle.open_time:
                raise MultiTimeframeError(
                    "cursor source candle boundaries are not contiguous"
                )

        self._hash_candle(self._source_hasher, candle)
        self._source_count += 1
        self._as_of = candle.close_time
        self._last_source = candle

        emitted: list[str] = []
        for target in self.target_timeframes:
            target_interval = self._target_intervals[target]
            expected_count = self._expected_counts[target]

            if expected_count == 1:
                derived = Candle(
                    symbol=candle.symbol,
                    timeframe=target,
                    open_time=candle.open_time,
                    close_time=candle.close_time,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                    is_closed=True,
                )
                self._emit(target, derived)
                emitted.append(target)
                continue

            bucket_start = _bucket_start(
                candle.open_time,
                target_interval,
            )
            current = self._pending[target]
            if current is None or current[0] != bucket_start:
                current = (bucket_start, [])
                self._pending[target] = current

            current[1].append(candle)
            bucket_end = bucket_start + target_interval
            if candle.close_time != bucket_end:
                continue

            bucket = current[1]
            self._pending[target] = None
            if len(bucket) != expected_count:
                continue
            if (
                bucket[0].open_time != bucket_start
                or bucket[-1].close_time != bucket_end
            ):
                continue

            derived = _aggregate_bucket(
                bucket,
                target_timeframe=target,
                bucket_start=bucket_start,
                target_interval=target_interval,
            )
            self._emit(target, derived)
            emitted.append(target)

        return tuple(emitted)

    def state(self) -> HistoricalMultiTimeframeCursorState:
        if (
            self._symbol is None
            or self._as_of is None
            or self._source_count <= 0
        ):
            raise MultiTimeframeError("cursor has not consumed source data")

        source_fingerprint = self._source_hasher.copy().hexdigest()
        series_fingerprints = tuple(
            (
                target,
                self._target_hashers[target].copy().hexdigest(),
                len(self._series[target]),
            )
            for target in self.target_timeframes
        )
        payload = {
            "schema": "money-heist.historical-mtf-cursor.v1",
            "symbol": self._symbol,
            "source_timeframe": self.source_timeframe,
            "source_candle_count": self._source_count,
            "source_fingerprint": source_fingerprint,
            "target_timeframes": self.target_timeframes,
            "series_fingerprints": series_fingerprints,
            "as_of": self._as_of.isoformat().replace("+00:00", "Z"),
            "policy_version": self.policy_version,
        }
        cursor_fingerprint = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()

        counts = tuple(
            (target, len(self._series[target]))
            for target in self.target_timeframes
        )
        latest = tuple(
            (target, self._series[target][-1].close_time)
            for target in self.target_timeframes
            if self._series[target]
        )
        return HistoricalMultiTimeframeCursorState(
            symbol=self._symbol,
            source_timeframe=self.source_timeframe,
            source_candle_count=self._source_count,
            target_timeframes=self.target_timeframes,
            as_of=self._as_of,
            policy_version=self.policy_version,
            source_fingerprint=source_fingerprint,
            cursor_fingerprint=cursor_fingerprint,
            candle_counts=counts,
            latest_close_times=latest,
        )

    def _emit(self, timeframe: str, candle: Candle) -> None:
        self._series[timeframe].append(candle)
        self._hash_candle(self._target_hashers[timeframe], candle)

    @staticmethod
    def _hash_candle(hasher: Any, candle: Candle) -> None:
        encoded = json.dumps(
            _canonical_candle(candle),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        hasher.update(encoded)
        hasher.update(b"\n")
