from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.market.historical import import_candles_csv
from app.market.multitimeframe import HistoricalMultiTimeframeCursor


INTERVALS = {
    "1m": timedelta(minutes=1),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


def load(path: Path, *, timeframe: str):
    result = import_candles_csv(
        path,
        symbol="BTC/USDC",
        timeframe=timeframe,
        source="binance_spot_historical",
        candle_interval=INTERVALS[timeframe],
    )
    if not result.quality.is_valid:
        raise SystemExit(
            f"{timeframe} reference invalid: "
            f"gaps={result.quality.gap_count}"
        )
    return result.candles


def reference_for(source: Path, timeframe: str) -> Path:
    token = "_1m_"
    if token not in source.name:
        raise SystemExit(
            "source filename must contain '_1m_' so reference names can be derived"
        )
    return source.with_name(
        source.name.replace(token, f"_{timeframe}_", 1)
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate incremental MTF cursor against annual CSV exports."
    )
    parser.add_argument("source_1m", type=Path)
    args = parser.parse_args()

    source = load(args.source_1m, timeframe="1m")
    cursor = HistoricalMultiTimeframeCursor(
        source_timeframe="1m",
        target_timeframes=("15m", "1h", "4h", "1d"),
    )
    for candle in source:
        cursor.push(candle)

    print("Money Heist Batch 16.21b annual MTF cursor validation")
    print(f"source 1m: {len(source):,}")
    for timeframe in ("15m", "1h", "4h", "1d"):
        reference_path = reference_for(args.source_1m, timeframe)
        reference = load(reference_path, timeframe=timeframe)
        derived = cursor.series(timeframe)
        if derived != reference:
            mismatch = next(
                (
                    index
                    for index, pair in enumerate(zip(derived, reference))
                    if pair[0] != pair[1]
                ),
                None,
            )
            raise SystemExit(
                f"{timeframe}: MISMATCH "
                f"derived={len(derived):,} reference={len(reference):,} "
                f"first_mismatch={mismatch}"
            )
        print(f"{timeframe}: exact={len(derived):,}")

    state = cursor.state()
    print(f"source fingerprint: {state.source_fingerprint}")
    print(f"cursor fingerprint: {state.cursor_fingerprint}")
    print("RESULT: OK - incremental cursor exactly matches annual references.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
