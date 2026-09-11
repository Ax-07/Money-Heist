from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.backtest.historical_derivatives import (
    HistoricalFundingArchive,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a canonical Money Heist historical funding archive."
    )
    parser.add_argument("canonical_csv", type=Path)
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=7200,
    )
    args = parser.parse_args()
    if args.max_age_seconds <= 0:
        raise SystemExit("--max-age-seconds must be > 0")

    archive = HistoricalFundingArchive.from_canonical_csv(
        args.canonical_csv
    )
    as_of = archive.points[-1].available_at
    snapshot = archive.positioning_snapshot_at(
        as_of=as_of,
        max_age=timedelta(seconds=args.max_age_seconds),
    )
    rio = archive.rio_context_at(
        as_of=as_of,
        max_age=timedelta(seconds=args.max_age_seconds),
    )
    if snapshot is None or rio is None:
        raise SystemExit("latest funding point is unexpectedly unavailable")
    if rio.data_quality != "DEGRADED" or not rio.usable:
        raise SystemExit("funding-only Rio context must be DEGRADED but usable")
    if snapshot.open_interest is not None:
        raise SystemExit("open_interest must not be fabricated")
    if snapshot.long_short_ratio is not None:
        raise SystemExit("long_short_ratio must not be fabricated")

    print("Money Heist Batch 16.21i Historical Funding Archive validation")
    print(f"version: {archive.version}")
    print(f"source: {archive.source}")
    print(f"symbol: {archive.symbol}")
    print(f"instrument: {archive.instrument}")
    print(f"rows: {len(archive.points):,}")
    print(f"first_observed_at: {archive.first_observed_at.isoformat()}")
    print(f"last_observed_at: {archive.last_observed_at.isoformat()}")
    print(f"dataset_fingerprint: {archive.dataset_fingerprint}")
    print(f"latest_funding_rate: {snapshot.funding_rate}")
    print("rio_data_quality: DEGRADED")
    print("open_interest: UNAVAILABLE")
    print("long_short_ratio: UNAVAILABLE")
    print("liquidations: UNAVAILABLE")
    print(
        "RESULT: OK - historical funding is cutoff-safe and the unavailable "
        "derivatives metrics remain explicit."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
