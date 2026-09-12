from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.backtest.denver_prior import FrozenDenverPriorCatalog
from app.services.backtest.denver_runtime import (
    DenverActivationMode,
    denver_prior_execution_assumptions,
    denver_runner_kwargs,
    validate_denver_prior_compatibility,
)
from app.services.backtest.mtf_runtime import mtf_execution_assumptions
from app.services.backtest.splits import BacktestPeriodRole


def _utc(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate explicit frozen Denver runtime activation."
    )
    parser.add_argument("prior_json", type=Path)
    parser.add_argument("--source-timeframe", default="1m")
    parser.add_argument("--symbol", default="BTC/USDC")
    parser.add_argument("--system-id", default="balanced_v1")
    parser.add_argument("--oos-start", required=True)
    parser.add_argument(
        "--activation-mode",
        choices=("OOS_ONLY", "ALL_PERIODS"),
        default="OOS_ONLY",
    )
    args = parser.parse_args()

    prior = FrozenDenverPriorCatalog.from_json(
        args.prior_json.read_text(encoding="utf-8")
    )
    mode = DenverActivationMode(args.activation_mode)

    validate_denver_prior_compatibility(
        prior,
        system_id=args.system_id,
        symbol=args.symbol,
        decision_timeframe="1h",
    )
    prior.validate_for_target(
        period_start=_utc(args.oos_start),
        formal_oos=(mode is DenverActivationMode.OOS_ONLY),
    )

    assumptions = mtf_execution_assumptions(args.source_timeframe)
    assumptions.update(
        denver_prior_execution_assumptions(
            prior,
            activation_mode=mode,
        )
    )

    design = denver_runner_kwargs(
        assumptions,
        prior,
        role=BacktestPeriodRole.DESIGN,
    )
    validation = denver_runner_kwargs(
        assumptions,
        prior,
        role=BacktestPeriodRole.VALIDATION,
    )
    oos = denver_runner_kwargs(
        assumptions,
        prior,
        role=BacktestPeriodRole.OOS,
    )

    print("Money Heist Batch 16.21p Denver Runtime Activation")
    print(f"runtime_version: {assumptions['denver_runtime_version']}")
    print(f"activation_mode: {mode.value}")
    print(f"prior_id: {prior.prior_id}")
    print(f"prior_policy: {prior.policy.value}")
    print(f"prior_cutoff: {prior.cutoff.isoformat()}")
    print(f"source_timeframe: {args.source_timeframe}")
    print(f"design_injected: {bool(design)}")
    print(f"validation_injected: {bool(validation)}")
    print(f"oos_injected: {bool(oos)}")
    print("RESULT: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
