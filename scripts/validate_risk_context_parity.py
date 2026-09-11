from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.market.features import FeatureEngine
from app.market.features.multitimeframe import build_multi_timeframe_feature_context
from app.market.historical import import_candles_csv
from app.market.multitimeframe import HistoricalMultiTimeframeCursor
from app.market.structure import build_market_structure_context
from app.services.decision_context import (
    ContextAvailability,
    OptionalContextSection,
    ProvenanceRecord,
    RISK_CONTEXT_BINDING_VERSION,
    build_decision_context,
)
from app.trading.risk.models import MarketConstraints, PortfolioRiskState


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Batch 16.21h portfolio and market-constraints parity."
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

    as_of = source[-1].close_time
    market = build_multi_timeframe_feature_context(
        feature_engine=FeatureEngine(),
        mtf_cursor=cursor,
        observed_at=as_of,
        decision_timeframe="1h",
    )
    structure = build_market_structure_context(
        mtf_cursor=cursor,
        observed_at=as_of,
    )
    structure_section = OptionalContextSection(
        status=ContextAvailability.AVAILABLE,
        payload=structure.to_payload(),
    )
    structure_provenance = ProvenanceRecord(
        component="structure",
        source="closed_ohlcv_market_structure",
        observed_at=as_of,
        available_at=as_of,
        quality="COMPLETE" if structure.all_structures_ready else "PARTIAL",
        missing_fields=tuple(
            [f"missing:{item}" for item in structure.missing_timeframes]
            + [f"incomplete:{item}" for item in structure.incomplete_timeframes]
        ),
        source_fingerprint=structure.context_fingerprint,
    )

    portfolio = PortfolioRiskState(
        equity=Decimal("987.65"),
        day_start_equity=Decimal("1000"),
        equity_peak=Decimal("1025"),
        daily_pnl=Decimal("-12.35"),
        open_positions=2,
        open_risk_amount=Decimal("7.50"),
        correlated_risk_amount=Decimal("5.00"),
        gross_exposure_amount=Decimal("320.00"),
    )
    constraints = MarketConstraints(
        qty_step=Decimal("0.00001"),
        min_qty=Decimal("0.0001"),
        min_notional=Decimal("10"),
        max_qty=Decimal("5"),
        max_leverage=Decimal("2"),
    )

    first = build_decision_context(
        system_id="balanced_v1",
        as_of=as_of,
        primary_timeframe="1h",
        timeframe_policy_version="mtf-utc-closed-v1",
        market=market,
        structure=structure_section,
        portfolio_state=portfolio,
        market_constraints=constraints,
        provenance={"structure": structure_provenance},
    )
    second = build_decision_context(
        system_id="balanced_v1",
        as_of=as_of,
        primary_timeframe="1h",
        timeframe_policy_version="mtf-utc-closed-v1",
        market=market,
        structure=structure_section,
        portfolio_state=portfolio,
        market_constraints=constraints,
        provenance={"structure": structure_provenance},
    )

    if first.context_id != second.context_id:
        raise SystemExit("DecisionContext id is not deterministic")
    if first.context_fingerprint != second.context_fingerprint:
        raise SystemExit("DecisionContext fingerprint is not deterministic")
    if first.portfolio_summary is None:
        raise SystemExit("portfolio_summary is missing")
    if first.market_constraints is None:
        raise SystemExit("market_constraints is missing")
    if "portfolio_summary" in first.missing_components:
        raise SystemExit("portfolio_summary remains marked missing")
    if "market_constraints" in first.missing_components:
        raise SystemExit("market_constraints remains marked missing")

    print("Money Heist Batch 16.21h Risk Context Parity validation")
    print(f"source 1m: {len(source):,}")
    print(f"binding_version: {RISK_CONTEXT_BINDING_VERSION}")
    print(f"as_of: {as_of.isoformat()}")
    print(f"context_id: {first.context_id}")
    print(f"context_fingerprint: {first.context_fingerprint}")
    print("portfolio_summary: AVAILABLE")
    print(f"  equity: {first.portfolio_summary.equity}")
    print(f"  daily_pnl: {first.portfolio_summary.daily_pnl}")
    print(f"  open_positions: {first.portfolio_summary.open_positions}")
    print(f"  open_risk_amount: {first.portfolio_summary.open_risk_amount}")
    print("market_constraints: AVAILABLE")
    print(f"  qty_step: {first.market_constraints.qty_step}")
    print(f"  min_qty: {first.market_constraints.min_qty}")
    print(f"  min_notional: {first.market_constraints.min_notional}")
    print(f"  max_qty: {first.market_constraints.max_qty}")
    print(f"  max_leverage: {first.market_constraints.max_leverage}")
    print(
        "RESULT: OK - agents can receive frozen decision-time portfolio and "
        "market constraints while Risk Engine authority remains downstream."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
