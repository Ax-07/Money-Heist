from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.backtest.denver_prior import (
    DenverPriorPolicy,
    freeze_denver_prior,
)
from app.services.backtest.setup_stats import (
    HistoricalSetupStatsCatalog,
)


def _utc(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("--cutoff must be timezone-aware")
    return value.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze an existing Denver setup-stats catalog into a "
            "content-addressed anti-contamination prior."
        )
    )
    parser.add_argument("input_catalog", type=Path)
    parser.add_argument("output_prior", type=Path)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument(
        "--policy",
        choices=tuple(item.value for item in DenverPriorPolicy),
        default=DenverPriorPolicy.STRICT_PRE_OOS.value,
    )
    args = parser.parse_args()

    source = HistoricalSetupStatsCatalog.from_json(
        args.input_catalog.read_text(encoding="utf-8")
    )
    prior = freeze_denver_prior(
        source,
        cutoff=_utc(args.cutoff),
        policy=DenverPriorPolicy(args.policy),
    )

    args.output_prior.parent.mkdir(parents=True, exist_ok=True)
    args.output_prior.write_text(
        prior.to_json() + "\n",
        encoding="utf-8",
    )

    print("Money Heist frozen Denver prior created")
    print(f"prior_version: {prior.version}")
    print(f"prior_id: {prior.prior_id}")
    print(f"policy: {prior.policy.value}")
    print(f"cutoff: {prior.cutoff.isoformat()}")
    print(f"observation_count: {prior.observation_count}")
    print(f"source_roles: {','.join(prior.source_period_roles)}")
    print(f"source_runs: {len(prior.source_run_ids)}")
    print(f"source_datasets: {len(prior.source_dataset_ids)}")
    print(f"catalog_id: {prior.catalog.catalog_id}")
    print(f"output: {args.output_prior}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
