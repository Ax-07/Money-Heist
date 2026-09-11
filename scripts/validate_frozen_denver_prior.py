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
    FrozenDenverPriorCatalog,
)


def _utc(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("--target-start must be timezone-aware")
    return value.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a frozen Money Heist Denver prior artifact."
    )
    parser.add_argument("prior_json", type=Path)
    parser.add_argument("--target-start")
    parser.add_argument("--formal-oos", action="store_true")
    args = parser.parse_args()

    raw = args.prior_json.read_text(encoding="utf-8")
    prior = FrozenDenverPriorCatalog.from_json(raw)
    restored = FrozenDenverPriorCatalog.from_json(prior.to_json())
    if restored.prior_id != prior.prior_id:
        raise SystemExit("round-trip prior identity mismatch")

    if args.target_start:
        prior.validate_for_target(
            period_start=_utc(args.target_start),
            formal_oos=args.formal_oos,
        )
    elif args.formal_oos:
        raise SystemExit("--formal-oos requires --target-start")

    if prior.policy is DenverPriorPolicy.STRICT_PRE_OOS:
        if "OOS" in prior.source_period_roles:
            raise SystemExit("STRICT_PRE_OOS prior contains OOS observations")

    if any(
        item.closed_at > prior.cutoff
        for item in prior.catalog.observations
    ):
        raise SystemExit("prior contains observations after cutoff")

    print("Money Heist Batch 16.21m Frozen Denver Prior validation")
    print(f"prior_version: {prior.version}")
    print(f"prior_id: {prior.prior_id}")
    print(f"policy: {prior.policy.value}")
    print(f"cutoff: {prior.cutoff.isoformat()}")
    print(f"observation_count: {prior.observation_count}")
    print(f"source_roles: {','.join(prior.source_period_roles)}")
    print(f"catalog_id: {prior.catalog.catalog_id}")
    print(
        "source_strategy_fingerprint: "
        f"{prior.catalog.strategy_fingerprint}"
    )
    if args.target_start:
        print(f"target_start: {_utc(args.target_start).isoformat()}")
        print(f"formal_oos: {args.formal_oos}")
    print(
        "RESULT: OK - Denver prior is frozen, content-addressed and "
        "contains no information after its declared cutoff."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
