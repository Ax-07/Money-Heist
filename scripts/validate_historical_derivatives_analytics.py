from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.backtest.historical_derivatives_analytics import (
    HistoricalDerivativesAnalyticsArchive,
)


def _utc(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _grid(start: datetime, end: datetime) -> tuple[datetime, ...]:
    values = []
    cursor = start
    step = timedelta(hours=1)
    while cursor <= end:
        values.append(cursor)
        cursor += step
    return tuple(values)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the full historical derivatives analytics archive."
    )
    parser.add_argument("canonical_csv", type=Path)
    parser.add_argument(
        "--start",
        default="2025-09-11T00:00:00Z",
    )
    parser.add_argument(
        "--end",
        default="2026-09-11T00:00:00Z",
    )
    args = parser.parse_args()

    start = _utc(args.start)
    end = _utc(args.end)
    archive = HistoricalDerivativesAnalyticsArchive.from_canonical_csv(
        args.canonical_csv
    )
    expected = _grid(start, end)
    by_time = {point.observed_at: point for point in archive.points}

    missing_rows = [item for item in expected if item not in by_time]
    if missing_rows:
        raise SystemExit(
            f"canonical archive is missing {len(missing_rows)} hourly row(s)"
        )

    missing_oi = [
        item for item in expected if by_time[item].open_interest is None
    ]
    missing_ratio = [
        item for item in expected if by_time[item].long_short_ratio is None
    ]
    if missing_oi:
        raise SystemExit(
            f"open interest missing at {len(missing_oi)} hourly point(s)"
        )
    if missing_ratio:
        raise SystemExit(
            f"long/short ratio missing at {len(missing_ratio)} hourly point(s)"
        )

    funding_times = [
        item
        for item in expected
        if by_time[item].funding_rate is not None
    ]
    if funding_times:
        first_funding = funding_times[0]
        expected_funding = [
            item for item in expected if item >= first_funding
        ]
        missing_after_start = [
            item
            for item in expected_funding
            if by_time[item].funding_rate is None
        ]
        if missing_after_start:
            raise SystemExit(
                "funding has internal gaps after first availability: "
                f"{len(missing_after_start)} point(s)"
            )
    else:
        first_funding = None

    before_funding_time = (
        first_funding - timedelta(hours=1)
        if first_funding is not None and first_funding > start
        else start
    )
    degraded = archive.rio_context_at(
        as_of=before_funding_time + timedelta(hours=1),
        max_age=timedelta(hours=2),
    )
    if degraded is None:
        raise SystemExit("pre-funding Rio context is unexpectedly unavailable")
    if first_funding is not None and first_funding > start:
        if degraded.funding_rate is not None:
            raise SystemExit("funding was backfilled into pre-funding context")
        if degraded.data_quality != "DEGRADED":
            raise SystemExit("pre-funding Rio context must be DEGRADED")

    latest_as_of = end + timedelta(hours=1)
    latest = archive.rio_context_at(
        as_of=latest_as_of,
        max_age=timedelta(hours=2),
    )
    if latest is None:
        raise SystemExit("latest Rio context is unexpectedly unavailable")

    counts = archive.metric_counts()
    print("Money Heist Batch 16.21j Historical Derivatives validation")
    print(f"version: {archive.version}")
    print(f"symbol: {archive.symbol}")
    print(f"instrument: {archive.instrument}")
    print(f"rows: {len(archive.points):,}")
    print(f"expected_hourly_rows: {len(expected):,}")
    print(f"open_interest_points: {counts['open_interest']:,}")
    print(f"long_short_ratio_points: {counts['long_short_ratio']:,}")
    print(f"funding_points: {counts['funding_rate']:,}")
    print(f"first_funding_at: {first_funding}")
    print(
        "open_interest_change_points: "
        f"{counts['open_interest_change_pct']:,}"
    )
    print(f"latest_rio_quality: {latest.data_quality}")
    print(f"dataset_fingerprint: {archive.dataset_fingerprint}")
    print("liquidations: UNAVAILABLE")
    print(
        "RESULT: OK - OI and long/short ratio are complete, funding gaps "
        "remain explicit, and no derivative metric is interpolated."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
