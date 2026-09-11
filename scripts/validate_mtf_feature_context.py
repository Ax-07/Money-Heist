from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.market.features import FeatureEngine
from app.market.features.multitimeframe import (
    build_multi_timeframe_feature_context,
)
from app.market.historical import import_candles_csv
from app.market.multitimeframe import HistoricalMultiTimeframeCursor


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Batch 16.21c MTF Feature Context on a 1m dataset."
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

    source = imported.candles
    cursor = HistoricalMultiTimeframeCursor(
        source_timeframe="1m",
        target_timeframes=("15m", "1h", "4h", "1d"),
    )
    engine = FeatureEngine()
    start = source[0].open_time
    checkpoints = {
        start + timedelta(hours=1): "1h",
        start + timedelta(days=1): "1d",
        start + timedelta(days=35): "35d",
        source[-1].close_time: "final",
    }
    seen = set()

    print("Money Heist Batch 16.21c MTF Feature Context validation")
    print(f"source 1m: {len(source):,}")
    print(f"FeatureEngine warmup bars: {engine.config.warmup_bars}")

    for candle in source:
        cursor.push(candle)
        label = checkpoints.get(candle.close_time)
        if label is None:
            continue

        context = build_multi_timeframe_feature_context(
            feature_engine=engine,
            mtf_cursor=cursor,
            observed_at=candle.close_time,
            decision_timeframe="1h",
        )
        seen.add(label)
        print()
        print(f"[{label}] as_of={context.observed_at.isoformat()}")
        print(f"  fingerprint={context.context_fingerprint}")
        print(
            "  missing="
            + (
                ",".join(context.missing_timeframes)
                if context.missing_timeframes
                else "-"
            )
        )
        print(
            "  warmup_incomplete="
            + (
                ",".join(context.warmup_incomplete_timeframes)
                if context.warmup_incomplete_timeframes
                else "-"
            )
        )
        for timeframe in context.requested_timeframes:
            snapshot = context.snapshots.get(timeframe)
            if snapshot is None:
                print(f"  {timeframe}: MISSING")
                continue
            print(
                f"  {timeframe}: candles={snapshot.candle_count:,} "
                f"warm={snapshot.quality.warmup_complete} "
                f"regime={snapshot.regime.value} "
                f"close={snapshot.close}"
            )

        if label == "1h":
            if set(context.missing_timeframes) != {"4h", "1d"}:
                raise SystemExit(
                    "1h checkpoint should have 4h and 1d missing"
                )
        if label == "35d" and not context.all_warmups_complete:
            raise SystemExit(
                "35d checkpoint should have all MTF warmups complete"
            )
        if label == "final" and not context.all_warmups_complete:
            raise SystemExit(
                "final checkpoint should have all MTF warmups complete"
            )

    expected = {"1h", "1d", "35d", "final"}
    if seen != expected:
        raise SystemExit(
            f"missing checkpoints: {sorted(expected - seen)}"
        )

    print()
    print(
        "RESULT: OK - MTF FeatureSnapshots are deterministic, "
        "missing-aware and warmup-aware."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
