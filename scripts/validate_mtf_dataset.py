from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.market.historical import import_candles_csv
from app.market.multitimeframe import build_historical_mtf_slice


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Money Heist 1m CSV through the MTF foundation."
    )
    parser.add_argument("csv", type=Path, help="Backtest-ready 1m CSV")
    parser.add_argument("--symbol", default="BTC/USDC")
    args = parser.parse_args()

    imported = import_candles_csv(
        args.csv,
        symbol=args.symbol,
        timeframe="1m",
        source="binance_spot_historical",
        candle_interval=timedelta(minutes=1),
    )
    if not imported.quality.is_valid:
        raise SystemExit(
            "SOURCE INVALID: "
            f"gaps={imported.quality.gap_count} "
            f"duplicates={imported.quality.has_duplicates}"
        )

    as_of = imported.candles[-1].close_time
    view = build_historical_mtf_slice(
        imported.candles,
        as_of=as_of,
        target_timeframes=("15m", "1h", "4h", "1d"),
    )

    print("Money Heist Batch 16.21a MTF validation")
    print(f"source: {args.csv}")
    print(f"symbol: {view.symbol}")
    print(f"source timeframe: {view.source_timeframe}")
    print(f"as_of: {view.as_of.isoformat()}")
    print(f"policy: {view.policy_version}")
    print(f"visible source candles: {view.source_candle_count:,}")
    print(f"source fingerprint: {view.source_fingerprint}")
    print(f"fingerprint: {view.fingerprint}")
    for timeframe in view.target_timeframes:
        series = view.candles_by_timeframe[timeframe]
        first = series[0].open_time.isoformat() if series else "-"
        last = series[-1].close_time.isoformat() if series else "-"
        print(
            f"{timeframe}: rows={len(series):,} "
            f"first={first} last={last}"
        )

    print("RESULT: OK - closed UTC buckets only, no source gaps.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
