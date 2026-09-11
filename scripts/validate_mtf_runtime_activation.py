from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.market.historical import import_candles_csv
from app.services.backtest.mtf_runtime import (
    mtf_execution_assumptions,
    mtf_runner_kwargs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Batch 16.21g runtime MTF activation."
    )
    parser.add_argument("source_1m", type=Path)
    args = parser.parse_args()

    imported = import_candles_csv(
        args.source_1m,
        symbol="BTC/USDC",
        timeframe="1m",
        source="binance_spot_historical",
        candle_interval=timedelta(minutes=1),
    )
    if not imported.quality.is_valid:
        raise SystemExit(
            f"source invalid: gaps={imported.quality.gap_count}"
        )

    assumptions = mtf_execution_assumptions(imported.timeframe)
    kwargs = mtf_runner_kwargs(assumptions)
    if kwargs.get("decision_timeframe") != "1h":
        raise SystemExit("1m canonical dataset did not activate 1h decision runtime")
    if tuple(kwargs.get("mtf_timeframes", ())) != ("15m", "1h", "4h", "1d"):
        raise SystemExit("canonical dataset did not activate full MTF targets")

    legacy = mtf_execution_assumptions("1h")
    if legacy:
        raise SystemExit("native 1h source must remain legacy")

    print("Money Heist Batch 16.21g Runtime MTF Activation validation")
    print(f"source 1m: {len(imported.candles):,}")
    print("runtime_version: historical-mtf-runtime-v1")
    print("decision_timeframe: 1h")
    print("mtf_timeframes: 15m,1h,4h,1d")
    print("1m source: MTF ENABLED")
    print("1h source: LEGACY (15m cannot be reconstructed)")
    print(
        "RESULT: OK - compatible historical sources activate the full MTF "
        "runtime while incompatible 1h sources remain non-fabricated legacy."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
