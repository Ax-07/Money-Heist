from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.backtest.historical_derivatives import (
    normalize_kraken_funding_csv,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize one Kraken Derivatives historical funding CSV into "
            "Money Heist's cutoff-safe canonical archive."
        )
    )
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--timestamp-column")
    parser.add_argument("--funding-column")
    parser.add_argument(
        "--availability-lag-seconds",
        type=int,
        default=0,
        help=(
            "Conservative delay added to each source timestamp before the "
            "funding point may be used in replay."
        ),
    )
    args = parser.parse_args()

    if args.availability_lag_seconds < 0:
        raise SystemExit("--availability-lag-seconds must be >= 0")

    archive = normalize_kraken_funding_csv(
        input_path=args.input_csv,
        output_path=args.output_csv,
        symbol=args.symbol,
        instrument=args.instrument,
        timestamp_column=args.timestamp_column,
        funding_column=args.funding_column,
        availability_lag=timedelta(
            seconds=args.availability_lag_seconds
        ),
    )

    print("Money Heist historical funding archive prepared")
    print(f"version: {archive.version}")
    print(f"symbol: {archive.symbol}")
    print(f"instrument: {archive.instrument}")
    print(f"rows: {len(archive.points):,}")
    print(f"first_observed_at: {archive.first_observed_at.isoformat()}")
    print(f"last_observed_at: {archive.last_observed_at.isoformat()}")
    print(f"dataset_fingerprint: {archive.dataset_fingerprint}")
    print(f"output: {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
