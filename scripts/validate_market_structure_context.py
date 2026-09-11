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
from app.market.structure import build_market_structure_context
from app.services.decision_context import (
    ContextAvailability,
    OptionalContextSection,
    ProvenanceRecord,
    build_decision_context,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Batch 16.21f historical market structure."
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

    as_of = source[-1].close_time
    structure = build_market_structure_context(
        mtf_cursor=cursor,
        observed_at=as_of,
    )
    repeated = build_market_structure_context(
        mtf_cursor=cursor,
        observed_at=as_of,
    )
    if structure.context_fingerprint != repeated.context_fingerprint:
        raise SystemExit("market structure fingerprint is not deterministic")

    engine = FeatureEngine()
    market = build_multi_timeframe_feature_context(
        feature_engine=engine,
        mtf_cursor=cursor,
        observed_at=as_of,
        decision_timeframe="1h",
    )
    section = OptionalContextSection(
        status=ContextAvailability.AVAILABLE,
        payload=structure.to_payload(),
    )
    quality = "COMPLETE" if structure.all_structures_ready else "PARTIAL"
    missing = tuple(
        [f"missing:{item}" for item in structure.missing_timeframes]
        + [f"incomplete:{item}" for item in structure.incomplete_timeframes]
    )
    provenance = ProvenanceRecord(
        component="structure",
        source="closed_ohlcv_market_structure",
        observed_at=as_of,
        available_at=as_of,
        quality=quality,
        missing_fields=missing,
        source_fingerprint=structure.context_fingerprint,
    )
    decision = build_decision_context(
        system_id="balanced_v1",
        as_of=as_of,
        primary_timeframe="1h",
        timeframe_policy_version="mtf-utc-closed-v1",
        market=market,
        structure=section,
        provenance={"structure": provenance},
    )

    if decision.structure.status is not ContextAvailability.AVAILABLE:
        raise SystemExit("DecisionContext structure is not AVAILABLE")
    if "structure" in decision.missing_components:
        raise SystemExit("DecisionContext still marks structure missing")
    if decision.microstructure.status is not ContextAvailability.UNAVAILABLE:
        raise SystemExit("microstructure must remain UNAVAILABLE")

    print("Money Heist Batch 16.21f Market Structure validation")
    print(f"source 1m: {len(source):,}")
    print(f"as_of: {as_of.isoformat()}")
    print(f"structure_fingerprint: {structure.context_fingerprint}")
    print(f"all_timeframes_available: {structure.all_timeframes_available}")
    print(f"all_structures_ready: {structure.all_structures_ready}")
    print(
        "incomplete_timeframes: "
        + (
            ",".join(structure.incomplete_timeframes)
            if structure.incomplete_timeframes
            else "-"
        )
    )
    for timeframe in structure.requested_timeframes:
        summary = structure.timeframes.get(timeframe)
        if summary is None:
            print(f"  {timeframe}: MISSING")
            continue
        print(
            f"  {timeframe}: "
            f"structure={summary.swing_structure.value} "
            f"breakout={summary.breakout_state.value} "
            f"location={summary.range_location.value} "
            f"range=[{summary.prior_range_low},{summary.prior_range_high}] "
            f"missing={','.join(summary.missing_fields) or '-'}"
        )
    print("DecisionContext structure: AVAILABLE")
    print("DecisionContext microstructure: UNAVAILABLE")
    print(
        "RESULT: OK - historical price structure is deterministic, "
        "closed-candle-only and separately scoped from microstructure."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
