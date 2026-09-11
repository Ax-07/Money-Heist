from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.market.features import FeatureEngine
from app.market.historical import import_candles_csv
from app.market.multitimeframe import HistoricalMultiTimeframeCursor
from app.market.scanner import DeterministicScanner


def _load(path: Path, *, timeframe: str, interval: timedelta):
    result = import_candles_csv(
        path,
        symbol="BTC/USDC",
        timeframe=timeframe,
        source="binance_spot_historical",
        candle_interval=interval,
    )
    if not result.quality.is_valid:
        raise SystemExit(
            f"{timeframe} dataset invalid: gaps={result.quality.gap_count}"
        )
    return result.candles


def _signature(series, *, system_id: str):
    engine = FeatureEngine()
    scanner = DeterministicScanner()
    previous = None
    output = []
    warmup = engine.config.warmup_bars

    for count in range(warmup, len(series) + 1):
        visible = series[:count]
        observed_at = visible[-1].close_time
        feature = engine.compute(
            visible,
            symbol="BTC/USDC",
            timeframe="1h",
            observed_at=observed_at,
        )
        scan = scanner.scan(
            feature,
            system_id=system_id,
            previous=previous,
        )
        previous = feature
        opportunity = scan.opportunity
        output.append(
            (
                observed_at,
                feature.snapshot_id,
                scan.score,
                tuple(item.value for item in scan.triggers),
                opportunity.opportunity_id if opportunity else None,
            )
        )
    return tuple(output)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate real Feature/Scanner parity for 1m->1h replay."
    )
    parser.add_argument("source_1m", type=Path)
    parser.add_argument("--system-id", default="balanced_v1")
    args = parser.parse_args()

    source = _load(
        args.source_1m,
        timeframe="1m",
        interval=timedelta(minutes=1),
    )
    reference_path = args.source_1m.with_name(
        args.source_1m.name.replace("_1m_", "_1h_", 1)
    )
    reference = _load(
        reference_path,
        timeframe="1h",
        interval=timedelta(hours=1),
    )

    cursor = HistoricalMultiTimeframeCursor(
        source_timeframe="1m",
        target_timeframes=("15m", "1h", "4h", "1d"),
    )
    for candle in source:
        cursor.push(candle)
    derived = cursor.series("1h")

    if derived != reference:
        raise SystemExit("1h candle parity failed before Feature/Scanner check")

    print("Computing native 1h Feature/Scanner sequence...")
    native_signature = _signature(
        reference,
        system_id=args.system_id,
    )
    print("Computing 1m->1h Feature/Scanner sequence...")
    derived_signature = _signature(
        derived,
        system_id=args.system_id,
    )

    if native_signature != derived_signature:
        mismatch = next(
            index
            for index, pair in enumerate(
                zip(native_signature, derived_signature)
            )
            if pair[0] != pair[1]
        )
        raise SystemExit(
            f"Feature/Scanner parity mismatch at decision index {mismatch}"
        )

    opportunities = sum(
        1 for item in native_signature if item[-1] is not None
    )
    print(f"decision points: {len(native_signature):,}")
    print(f"opportunities: {opportunities:,}")
    print(
        "RESULT: OK - native 1h and incremental 1m->1h produce "
        "identical Feature/Scanner decisions."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
