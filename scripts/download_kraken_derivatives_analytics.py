from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.market.exchange.transport import (
    ResilientPublicHttpClient,
    RetryPolicy,
    StdlibJsonTransport,
)
from app.services.backtest.historical_derivatives_analytics import (
    HistoricalDerivativesPoint,
    write_canonical_derivatives_csv,
)


BASE_URL = "https://futures.kraken.com/api/charts/v1/analytics"


def _utc(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


def _timestamp(value: Any) -> datetime:
    if isinstance(value, bool):
        raise ValueError("timestamp must be numeric")
    numeric = float(value)
    if not isfinite(numeric) or numeric <= 0:
        raise ValueError("timestamp must be positive and finite")
    seconds = numeric / 1000 if numeric >= 1_000_000_000_000 else numeric
    return datetime.fromtimestamp(seconds, tz=UTC)


def _decimal(value: Any, *, non_negative: bool) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"metric is not decimal: {value!r}") from exc
    if not parsed.is_finite():
        raise ValueError("metric must be finite")
    if non_negative and parsed < 0:
        raise ValueError("metric must be >= 0")
    return parsed


def _close_series(
    raw: Sequence[Any],
    *,
    expected: int,
) -> tuple[Any, ...]:
    if len(raw) == expected and all(not _is_sequence(item) for item in raw):
        return tuple(raw)
    if (
        len(raw) == 4
        and all(_is_sequence(item) for item in raw)
        and all(len(item) == expected for item in raw)
    ):
        return tuple(raw[3])
    if (
        len(raw) == expected
        and all(_is_sequence(item) and len(item) >= 4 for item in raw)
    ):
        return tuple(item[3] for item in raw)
    if expected == 0:
        return ()
    raise ValueError("unsupported Kraken analytics series shape")


def _parse_response(
    payload: Any,
    *,
    metric: str,
) -> tuple[dict[datetime, Decimal], bool]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{metric}: top-level payload must be object")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise ValueError(f"{metric}: missing result object")
    errors = result.get("errors")
    if errors is None and isinstance(result.get("data"), Mapping):
        errors = result["data"].get("errors")
    if _is_sequence(errors) and errors:
        raise ValueError(f"{metric}: Kraken returned errors")

    raw_timestamps = result.get("timestamp")
    if not _is_sequence(raw_timestamps):
        raise ValueError(f"{metric}: missing timestamp series")
    timestamps = tuple(_timestamp(item) for item in raw_timestamps)

    data = result.get("data")
    if metric == "funding":
        if not isinstance(data, Mapping):
            raise ValueError("funding: data must be object")
        raw = data.get("rate")
        if not _is_sequence(raw):
            raise ValueError("funding: missing rate series")
        series = _close_series(raw, expected=len(timestamps))
        non_negative = False
    elif metric == "open-interest":
        raw = data.get("openInterest") if isinstance(data, Mapping) else data
        if not _is_sequence(raw):
            raise ValueError("open-interest: missing series")
        series = _close_series(raw, expected=len(timestamps))
        non_negative = True
    elif metric == "long-short-ratio":
        raw = data.get("ratio") if isinstance(data, Mapping) else data
        if not _is_sequence(raw):
            raise ValueError("long-short-ratio: missing series")
        series = _close_series(raw, expected=len(timestamps))
        non_negative = True
    else:
        raise ValueError(f"unsupported metric {metric}")

    if len(series) != len(timestamps):
        raise ValueError(f"{metric}: timestamp/value length mismatch")

    points = {
        timestamp: _decimal(value, non_negative=non_negative)
        for timestamp, value in zip(timestamps, series, strict=True)
    }
    return points, bool(result.get("more", False))


async def _fetch_window(
    client: ResilientPublicHttpClient,
    *,
    instrument: str,
    metric: str,
    start: datetime,
    end: datetime,
    interval: int,
) -> tuple[dict[datetime, Decimal], bool]:
    response = await client.get_json(
        f"{BASE_URL}/{instrument}/{metric}",
        params={
            "since": int(start.timestamp()),
            "to": int(end.timestamp()),
            "interval": interval,
        },
    )
    return _parse_response(response.payload, metric=metric)


async def _collect(
    client: ResilientPublicHttpClient,
    *,
    instrument: str,
    metric: str,
    start: datetime,
    end: datetime,
    interval: int,
) -> dict[datetime, Decimal]:
    values: dict[datetime, Decimal] = {}

    async def recurse(window_start: datetime, window_end: datetime) -> None:
        points, more = await _fetch_window(
            client,
            instrument=instrument,
            metric=metric,
            start=window_start,
            end=window_end,
            interval=interval,
        )
        if more:
            if window_end - window_start <= timedelta(hours=6):
                raise RuntimeError(
                    f"{metric}: pagination still required in minimum window"
                )
            midpoint = window_start + (window_end - window_start) / 2
            await recurse(window_start, midpoint)
            await recurse(midpoint, window_end)
            return

        for timestamp, value in points.items():
            previous = values.get(timestamp)
            if previous is not None and previous != value:
                raise ValueError(
                    f"{metric}: conflicting duplicate at {timestamp.isoformat()}"
                )
            values[timestamp] = value

    cursor = start
    while cursor < end:
        if cursor.month == 12:
            next_month = cursor.replace(
                year=cursor.year + 1,
                month=1,
                day=1,
            )
        else:
            next_month = cursor.replace(
                month=cursor.month + 1,
                day=1,
            )
        boundary = min(next_month, end)
        if boundary <= cursor:
            boundary = min(cursor + timedelta(days=31), end)
        await recurse(cursor, boundary)
        cursor = boundary

    return values


def _expected_grid(
    start: datetime,
    end: datetime,
    *,
    step: timedelta,
) -> tuple[datetime, ...]:
    values: list[datetime] = []
    cursor = start
    while cursor <= end:
        values.append(cursor)
        cursor += step
    return tuple(values)


async def _main(args: argparse.Namespace) -> int:
    start = _utc(args.start)
    end = _utc(args.end)
    if end <= start:
        raise SystemExit("--end must be after --start")
    if args.availability_lag_seconds < 0:
        raise SystemExit("--availability-lag-seconds must be >= 0")

    interval = args.interval
    step = timedelta(seconds=interval)
    lag = timedelta(seconds=args.availability_lag_seconds)

    client = ResilientPublicHttpClient(
        StdlibJsonTransport(
            user_agent="money-heist-historical-derivatives-download/1"
        ),
        policy=RetryPolicy(
            timeout_seconds=15.0,
            max_attempts=3,
            base_backoff_seconds=0.5,
            max_backoff_seconds=4.0,
            min_request_interval_seconds=0.25,
        ),
    )

    print("Downloading Kraken historical derivatives analytics...")
    oi = await _collect(
        client,
        instrument=args.instrument,
        metric="open-interest",
        start=start - step,
        end=end,
        interval=interval,
    )
    ratio = await _collect(
        client,
        instrument=args.instrument,
        metric="long-short-ratio",
        start=start,
        end=end,
        interval=interval,
    )
    funding = await _collect(
        client,
        instrument=args.instrument,
        metric="funding",
        start=start,
        end=end,
        interval=interval,
    )

    grid = _expected_grid(start, end, step=step)
    missing_oi = [timestamp for timestamp in grid if timestamp not in oi]
    missing_ratio = [timestamp for timestamp in grid if timestamp not in ratio]
    if missing_oi:
        raise SystemExit(
            f"open-interest has {len(missing_oi)} missing hourly point(s)"
        )
    if missing_ratio:
        raise SystemExit(
            f"long-short-ratio has {len(missing_ratio)} missing hourly point(s)"
        )

    rows: list[HistoricalDerivativesPoint] = []
    for timestamp in grid:
        current_oi = oi[timestamp]
        previous_oi = oi.get(timestamp - step)
        oi_change = None
        if previous_oi is not None and previous_oi != 0:
            oi_change = (
                (current_oi - previous_oi)
                / previous_oi
                * Decimal("100")
            )
        rows.append(
            HistoricalDerivativesPoint(
                observed_at=timestamp,
                available_at=timestamp + lag,
                funding_rate=funding.get(timestamp),
                open_interest=current_oi,
                open_interest_change_pct=oi_change,
                long_short_ratio=ratio[timestamp],
            )
        )

    archive = write_canonical_derivatives_csv(
        path=args.output,
        symbol=args.symbol,
        instrument=args.instrument,
        rows=rows,
    )

    counts = archive.metric_counts()
    print("Money Heist historical derivatives archive downloaded")
    print(f"version: {archive.version}")
    print(f"symbol: {archive.symbol}")
    print(f"instrument: {archive.instrument}")
    print(f"rows: {len(archive.points):,}")
    print(f"first_observed_at: {archive.first_observed_at.isoformat()}")
    print(f"last_observed_at: {archive.last_observed_at.isoformat()}")
    print(f"availability_lag_seconds: {args.availability_lag_seconds}")
    print(f"funding_points: {counts['funding_rate']:,}")
    print(f"open_interest_points: {counts['open_interest']:,}")
    print(
        "open_interest_change_points: "
        f"{counts['open_interest_change_pct']:,}"
    )
    print(f"long_short_ratio_points: {counts['long_short_ratio']:,}")
    print(
        "first_funding_at: "
        f"{archive.first_metric_observed_at('funding_rate')}"
    )
    print(f"dataset_fingerprint: {archive.dataset_fingerprint}")
    print(f"output: {args.output}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Download Kraken PF_XBTUSD historical analytics into the "
            "Money Heist canonical cutoff-safe archive."
        )
    )
    parser.add_argument("output", type=Path)
    parser.add_argument("--symbol", default="BTC/USDC")
    parser.add_argument("--instrument", default="PF_XBTUSD")
    parser.add_argument(
        "--start",
        default="2025-09-11T00:00:00Z",
    )
    parser.add_argument(
        "--end",
        default="2026-09-11T00:00:00Z",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        choices=(3600,),
    )
    parser.add_argument(
        "--availability-lag-seconds",
        type=int,
        default=3600,
        help=(
            "Conservative replay availability lag. Default 3600 means an "
            "hourly analytics point is usable only after its hourly bucket "
            "has fully elapsed."
        ),
    )
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
