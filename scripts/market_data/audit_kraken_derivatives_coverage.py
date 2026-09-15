from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.market.exchange.transport import (
    ResilientPublicHttpClient,
    RetryPolicy,
    StdlibJsonTransport,
)

BASE_URL = "https://futures.kraken.com/api/charts/v1/analytics"
METRICS = ("funding", "open-interest", "long-short-ratio")


def _utc(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: Any) -> datetime:
    numeric = float(value)
    seconds = numeric / 1000 if numeric >= 1_000_000_000_000 else numeric
    return datetime.fromtimestamp(seconds, tz=UTC)


@dataclass
class MetricAudit:
    timestamps: set[datetime]
    request_count: int = 0
    empty_windows: int = 0
    split_windows: int = 0
    failures: int = 0

    @classmethod
    def create(cls) -> "MetricAudit":
        return cls(timestamps=set())


async def _fetch(
    client: ResilientPublicHttpClient,
    *,
    instrument: str,
    metric: str,
    start: datetime,
    end: datetime,
    interval: int,
) -> tuple[list[datetime], bool, dict[str, Any]]:
    response = await client.get_json(
        f"{BASE_URL}/{instrument}/{metric}",
        params={
            "since": int(start.timestamp()),
            "to": int(end.timestamp()),
            "interval": interval,
        },
    )
    payload = response.payload
    if not isinstance(payload, dict):
        raise ValueError(f"{metric}: top-level payload is not an object")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError(f"{metric}: missing result object")

    errors = result.get("errors")
    if errors:
        raise ValueError(f"{metric}: API errors={errors!r}")

    raw_timestamps = result.get("timestamp")
    if raw_timestamps is None:
        raw_timestamps = []
    if not isinstance(raw_timestamps, list):
        raise ValueError(f"{metric}: timestamp is not a list")

    timestamps = [_timestamp(item) for item in raw_timestamps]
    return timestamps, bool(result.get("more", False)), result


async def _collect_window(
    client: ResilientPublicHttpClient,
    *,
    audit: MetricAudit,
    instrument: str,
    metric: str,
    start: datetime,
    end: datetime,
    interval: int,
    min_split: timedelta = timedelta(hours=6),
) -> None:
    audit.request_count += 1
    try:
        timestamps, more, _ = await _fetch(
            client,
            instrument=instrument,
            metric=metric,
            start=start,
            end=end,
            interval=interval,
        )
    except Exception as exc:
        audit.failures += 1
        print(
            f"FAILED {metric} {start.isoformat()} -> {end.isoformat()}: "
            f"{type(exc).__name__}: {exc}"
        )
        return

    if more and end - start > min_split:
        audit.split_windows += 1
        midpoint = start + (end - start) / 2
        await _collect_window(
            client,
            audit=audit,
            instrument=instrument,
            metric=metric,
            start=start,
            end=midpoint,
            interval=interval,
            min_split=min_split,
        )
        await _collect_window(
            client,
            audit=audit,
            instrument=instrument,
            metric=metric,
            start=midpoint,
            end=end,
            interval=interval,
            min_split=min_split,
        )
        return

    if more:
        raise RuntimeError(
            f"{metric}: API still reports more=True in minimum split "
            f"{start.isoformat()} -> {end.isoformat()}"
        )

    if not timestamps:
        audit.empty_windows += 1
    audit.timestamps.update(timestamps)


def _month_windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    windows: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        if cursor.month == 12:
            next_month = cursor.replace(
                year=cursor.year + 1, month=1, day=1
            )
        else:
            next_month = cursor.replace(
                month=cursor.month + 1, day=1
            )
        boundary = min(next_month, end)
        if boundary <= cursor:
            boundary = min(cursor + timedelta(days=31), end)
        windows.append((cursor, boundary))
        cursor = boundary
    return windows


def _expected_grid(
    start: datetime,
    end: datetime,
    interval_seconds: int,
) -> set[datetime]:
    step = timedelta(seconds=interval_seconds)
    cursor = start
    out: set[datetime] = set()
    while cursor <= end:
        out.add(cursor)
        cursor += step
    return out


def _gap_runs(
    missing: list[datetime],
    *,
    step: timedelta,
) -> list[tuple[datetime, datetime, int]]:
    if not missing:
        return []
    runs: list[tuple[datetime, datetime, int]] = []
    run_start = missing[0]
    previous = missing[0]
    count = 1
    for item in missing[1:]:
        if item - previous == step:
            previous = item
            count += 1
            continue
        runs.append((run_start, previous, count))
        run_start = item
        previous = item
        count = 1
    runs.append((run_start, previous, count))
    return runs


async def _main(args: argparse.Namespace) -> int:
    start = _utc(args.start)
    end = _utc(args.end)
    if end <= start:
        raise SystemExit("--end must be after --start")

    client = ResilientPublicHttpClient(
        StdlibJsonTransport(
            user_agent="money-heist-kraken-derivatives-coverage/1"
        ),
        policy=RetryPolicy(
            timeout_seconds=15.0,
            max_attempts=3,
            base_backoff_seconds=0.5,
            max_backoff_seconds=4.0,
            min_request_interval_seconds=0.25,
        ),
    )

    audits = {metric: MetricAudit.create() for metric in METRICS}
    windows = _month_windows(start, end)

    print("Money Heist Kraken Derivatives full-period coverage audit")
    print(f"instrument: {args.instrument}")
    print(f"window: {start.isoformat()} -> {end.isoformat()}")
    print(f"interval_seconds: {args.interval}")
    print(f"top_level_windows: {len(windows)}")
    print()

    for index, (window_start, window_end) in enumerate(windows, start=1):
        print(
            f"[{index:02d}/{len(windows):02d}] "
            f"{window_start.date()} -> {window_end.date()}"
        )
        for metric in METRICS:
            before = len(audits[metric].timestamps)
            await _collect_window(
                client,
                audit=audits[metric],
                instrument=args.instrument,
                metric=metric,
                start=window_start,
                end=window_end,
                interval=args.interval,
            )
            gained = len(audits[metric].timestamps) - before
            print(f"  {metric}: +{gained}")
        print()

    expected = _expected_grid(start, end, args.interval)
    step = timedelta(seconds=args.interval)
    manifest: dict[str, Any] = {
        "instrument": args.instrument,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "interval_seconds": args.interval,
        "expected_grid_points_inclusive": len(expected),
        "metrics": {},
    }

    print("SUMMARY")
    for metric, audit in audits.items():
        in_window = sorted(
            item for item in audit.timestamps if start <= item <= end
        )
        present = set(in_window)
        missing = sorted(expected - present)
        runs = _gap_runs(missing, step=step)
        largest = max(runs, key=lambda item: item[2], default=None)

        print(f"  {metric}")
        print(f"    points_in_window: {len(in_window):,}")
        print(
            f"    first: {in_window[0].isoformat() if in_window else '-'}"
        )
        print(
            f"    last: {in_window[-1].isoformat() if in_window else '-'}"
        )
        print(f"    missing_grid_points: {len(missing):,}")
        print(f"    gap_runs: {len(runs):,}")
        if largest is not None:
            print(
                "    largest_gap: "
                f"{largest[0].isoformat()} -> {largest[1].isoformat()} "
                f"({largest[2]} point(s))"
            )
        print(f"    requests: {audit.request_count}")
        print(f"    empty_windows: {audit.empty_windows}")
        print(f"    split_windows: {audit.split_windows}")
        print(f"    failures: {audit.failures}")

        manifest["metrics"][metric] = {
            "points_in_window": len(in_window),
            "first": in_window[0].isoformat() if in_window else None,
            "last": in_window[-1].isoformat() if in_window else None,
            "missing_grid_points": len(missing),
            "gap_runs": [
                {
                    "start": run_start.isoformat(),
                    "end": run_end.isoformat(),
                    "points": count,
                }
                for run_start, run_end, count in runs
            ],
            "requests": audit.request_count,
            "empty_windows": audit.empty_windows,
            "split_windows": audit.split_windows,
            "failures": audit.failures,
        }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print()
    print(f"manifest: {output}")
    print(
        "RESULT: coverage measured. Do not wire Rio until gap policy is "
        "defined from this manifest."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Kraken Futures historical analytics coverage over the "
            "full Money Heist backtest period."
        )
    )
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
        choices=(60, 300, 900, 1800, 3600, 14400, 43200, 86400, 604800),
    )
    parser.add_argument(
        "--output",
        default=(
            "data/historical/kraken_futures/"
            "kraken_pf_xbtusd_coverage_2025-09-11_2026-09-11.json"
        ),
    )
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())

