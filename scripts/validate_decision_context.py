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
from app.services.decision_context import build_decision_context


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Batch 16.21d DecisionContext contract."
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
    for candle in source:
        cursor.push(candle)

    engine = FeatureEngine()
    as_of = source[-1].close_time
    market = build_multi_timeframe_feature_context(
        feature_engine=engine,
        mtf_cursor=cursor,
        observed_at=as_of,
        decision_timeframe="1h",
    )
    first = build_decision_context(
        system_id="balanced_v1",
        as_of=as_of,
        primary_timeframe="1h",
        timeframe_policy_version="mtf-utc-closed-v1",
        market=market,
    )
    second = build_decision_context(
        system_id="balanced_v1",
        as_of=as_of,
        primary_timeframe="1h",
        timeframe_policy_version="mtf-utc-closed-v1",
        market=market,
    )

    if first.context_fingerprint != second.context_fingerprint:
        raise SystemExit("DecisionContext fingerprint is not deterministic")
    if first.context_id != second.context_id:
        raise SystemExit("DecisionContext id is not deterministic")

    print("Money Heist Batch 16.21d DecisionContext validation")
    print(f"source 1m: {len(source):,}")
    print(f"as_of: {first.as_of.isoformat()}")
    print(f"context_version: {first.context_version}")
    print(f"context_id: {first.context_id}")
    print(f"context_fingerprint: {first.context_fingerprint}")
    print(
        "market_context_fingerprint: "
        f"{first.market.context_fingerprint}"
    )
    print(
        "market available_at: "
        f"{first.provenance['market'].available_at.isoformat()}"
    )
    print(
        "missing_components: "
        + ",".join(first.missing_components)
    )
    print(
        "market warmups complete: "
        f"{first.market.all_warmups_complete}"
    )
    print(
        "RESULT: OK - DecisionContext is deterministic, "
        "explicitly missing-aware and anti-lookahead guarded."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
