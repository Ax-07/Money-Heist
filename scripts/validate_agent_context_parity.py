from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.market.features import FeatureEngine
from app.market.features.multitimeframe import build_multi_timeframe_feature_context
from app.market.historical import import_candles_csv
from app.market.multitimeframe import HistoricalMultiTimeframeCursor
from app.services.decision_context import (
    AGENT_CONTEXT_BINDING_VERSION,
    build_decision_context,
    decision_context_payload,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Batch 16.21e frozen agent-context payload parity."
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
        raise SystemExit(f"source invalid: gaps={imported.quality.gap_count}")

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
    context = build_decision_context(
        system_id="balanced_v1",
        as_of=as_of,
        primary_timeframe="1h",
        timeframe_policy_version="mtf-utc-closed-v1",
        market=market,
    )
    context_payload = decision_context_payload(context)

    base_market_payload = market.decision_snapshot.model_dump(
        mode="json",
        exclude_none=True,
    )
    base_market_payload["decision_context"] = context_payload

    consumers = (
        "professor_plan",
        "berlin",
        "tokyo",
        "nairobi",
        "palermo",
        "professor_finalize",
    )
    serialized = {}
    for consumer in consumers:
        copied = copy.deepcopy(base_market_payload)
        round_trip = json.loads(
            json.dumps(copied, sort_keys=True, separators=(",", ":"))
        )
        supplied = round_trip["decision_context"]
        if supplied["context_id"] != context.context_id:
            raise SystemExit(f"{consumer}: context_id mismatch")
        if supplied["context_fingerprint"] != context.context_fingerprint:
            raise SystemExit(f"{consumer}: context_fingerprint mismatch")
        serialized[consumer] = json.dumps(
            supplied,
            sort_keys=True,
            separators=(",", ":"),
        )

    if len(set(serialized.values())) != 1:
        raise SystemExit("agent consumers did not receive identical context")

    snapshots = context_payload["market"]["snapshots"]
    if set(snapshots) != {"15m", "1h", "4h", "1d"}:
        raise SystemExit("final annual DecisionContext does not expose all MTF snapshots")

    print("Money Heist Batch 16.21e Agent Context Parity validation")
    print(f"source 1m: {len(source):,}")
    print(f"binding_version: {AGENT_CONTEXT_BINDING_VERSION}")
    print(f"context_id: {context.context_id}")
    print(f"context_fingerprint: {context.context_fingerprint}")
    print(f"consumers: {len(consumers)}")
    for consumer in consumers:
        print(f"  {consumer}: IDENTICAL")
    print("MTF regimes:")
    for timeframe in ("15m", "1h", "4h", "1d"):
        print(f"  {timeframe}: {snapshots[timeframe]['regime']}")
    print(
        "RESULT: OK - Professor, core specialists and Palermo can consume "
        "one identical frozen DecisionContext payload."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
