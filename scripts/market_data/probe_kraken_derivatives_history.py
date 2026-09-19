from __future__ import annotations

import argparse
import asyncio
import json
import sys
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
ANALYTICS_TYPES = (
    "funding",
    "open-interest",
    "long-short-ratio",
    "liquidation-volume",
)


def _utc(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("probe timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _shape(value: Any) -> str:
    if isinstance(value, dict):
        keys = ",".join(sorted(str(key) for key in value))
        return f"object(keys={keys})"
    if isinstance(value, list):
        if not value:
            return "list(len=0)"
        first = value[0]
        if isinstance(first, list):
            lengths = sorted({len(item) for item in value if isinstance(item, list)})
            return f"list(len={len(value)}, nested_lengths={lengths})"
        return f"list(len={len(value)}, first_type={type(first).__name__})"
    return type(value).__name__


async def _query(
    client: ResilientPublicHttpClient,
    *,
    instrument: str,
    analytics_type: str,
    start: datetime,
    end: datetime,
    interval: int,
) -> dict[str, Any]:
    response = await client.get_json(
        f"{BASE_URL}/{instrument}/{analytics_type}",
        params={
            "since": int(start.timestamp()),
            "to": int(end.timestamp()),
            "interval": interval,
        },
    )
    payload = response.payload
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "reason": f"top-level payload is {type(payload).__name__}",
        }

    result = payload.get("result")
    if not isinstance(result, dict):
        return {
            "ok": False,
            "reason": f"result is {type(result).__name__}",
            "payload_keys": sorted(payload),
        }

    timestamps = result.get("timestamp")
    if not isinstance(timestamps, list):
        timestamps = []

    data = result.get("data")
    report: dict[str, Any] = {
        "ok": True,
        "count": len(timestamps),
        "more": bool(result.get("more", False)),
        "result_keys": sorted(result),
        "data_shape": _shape(data),
    }

    if timestamps:
        report["first_timestamp"] = timestamps[0]
        report["last_timestamp"] = timestamps[-1]
        try:
            first = datetime.fromtimestamp(float(timestamps[0]), tz=UTC)
            last = datetime.fromtimestamp(float(timestamps[-1]), tz=UTC)
        except (TypeError, ValueError, OSError):
            pass
        else:
            report["first_utc"] = first.isoformat()
            report["last_utc"] = last.isoformat()

    if isinstance(data, dict):
        report["data_keys"] = sorted(data)
        report["data_key_shapes"] = {
            str(key): _shape(value)
            for key, value in sorted(data.items(), key=lambda item: str(item[0]))
        }

    errors = payload.get("errors") or result.get("errors")
    if errors:
        report["errors"] = errors

    return report


async def _main(args: argparse.Namespace) -> int:
    client = ResilientPublicHttpClient(
        StdlibJsonTransport(user_agent="money-heist-kraken-history-probe/1"),
        policy=RetryPolicy(
            timeout_seconds=15.0,
            max_attempts=3,
            base_backoff_seconds=0.5,
            max_backoff_seconds=4.0,
            min_request_interval_seconds=0.35,
        ),
    )

    dataset_start = _utc(args.start)
    dataset_end = _utc(args.end)
    if dataset_end <= dataset_start:
        raise SystemExit("--end must be after --start")

    midpoint = dataset_start + (dataset_end - dataset_start) / 2
    windows = (
        ("START", dataset_start, dataset_start + timedelta(days=1)),
        ("MID", midpoint, midpoint + timedelta(days=1)),
        ("END", dataset_end - timedelta(days=1), dataset_end),
    )

    print("Money Heist Kraken Derivatives historical coverage probe")
    print(f"instrument: {args.instrument}")
    print(f"dataset_window: {dataset_start.isoformat()} -> {dataset_end.isoformat()}")
    print(f"interval_seconds: {args.interval}")
    print()

    overall_ok = True
    summary: dict[str, dict[str, int]] = {
        analytics_type: {"nonempty": 0, "empty": 0, "failed": 0}
        for analytics_type in ANALYTICS_TYPES
    }

    for label, start, end in windows:
        print(f"[{label}] {start.isoformat()} -> {end.isoformat()}")
        for analytics_type in ANALYTICS_TYPES:
            try:
                report = await _query(
                    client,
                    instrument=args.instrument,
                    analytics_type=analytics_type,
                    start=start,
                    end=end,
                    interval=args.interval,
                )
            except Exception as exc:
                overall_ok = False
                summary[analytics_type]["failed"] += 1
                print(
                    f"  {analytics_type}: FAILED "
                    f"{type(exc).__name__}: {exc}"
                )
                continue

            if not report.get("ok"):
                overall_ok = False
                summary[analytics_type]["failed"] += 1
                print(
                    f"  {analytics_type}: INVALID "
                    + json.dumps(report, sort_keys=True, default=str)
                )
                continue

            count = int(report.get("count", 0))
            if count:
                summary[analytics_type]["nonempty"] += 1
            else:
                summary[analytics_type]["empty"] += 1

            data_keys = report.get("data_keys", [])
            first_utc = report.get("first_utc", "-")
            last_utc = report.get("last_utc", "-")
            print(
                f"  {analytics_type}: count={count} "
                f"more={report.get('more')} "
                f"first={first_utc} last={last_utc} "
                f"data_keys={','.join(data_keys) if data_keys else '-'}"
            )
            if args.verbose:
                print(
                    "    "
                    + json.dumps(
                        report,
                        sort_keys=True,
                        default=str,
                    )
                )
        print()

    print("SUMMARY")
    for analytics_type, values in summary.items():
        print(
            f"  {analytics_type}: "
            f"nonempty_windows={values['nonempty']} "
            f"empty_windows={values['empty']} "
            f"failed_windows={values['failed']}"
        )

    print()
    print(
        "Interpretation: funding/open-interest/long-short-ratio with "
        "nonempty_windows=3 are strong candidates for full historical replay. "
        "liquidation-volume is only an availability probe; Money Heist will "
        "not map aggregate liquidation volume to long/short liquidation fields."
    )
    return 0 if overall_ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe Kraken Futures Market Analytics historical coverage."
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
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())

