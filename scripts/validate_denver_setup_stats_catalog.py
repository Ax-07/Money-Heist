from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.backtest.setup_stats import (
    HistoricalSetupStatsCatalog,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a Denver setup-stats catalog exported by the "
            "Money Heist Backtest Dashboard."
        )
    )
    parser.add_argument("catalog_json", type=Path)
    args = parser.parse_args()

    raw = args.catalog_json.read_text(encoding="utf-8").strip()
    catalog = HistoricalSetupStatsCatalog.from_json(raw)
    canonical = catalog.to_json()
    if canonical != raw:
        raise SystemExit(
            "catalog is valid but not stored in canonical Money Heist form"
        )

    roles = Counter(
        item.period_role.value for item in catalog.observations
    )
    setups = {item.setup.setup_id for item in catalog.observations}
    closes = tuple(item.closed_at for item in catalog.observations)

    print("Money Heist Batch 16.21n Denver Catalog Export validation")
    print(f"catalog_id: {catalog.catalog_id}")
    print(f"observation_count: {len(catalog.observations)}")
    print(f"setup_count: {len(setups)}")
    print(f"design_observations: {roles.get('DESIGN', 0)}")
    print(f"validation_observations: {roles.get('VALIDATION', 0)}")
    print(f"oos_observations: {roles.get('OOS', 0)}")
    print(f"strategy_fingerprint: {catalog.strategy_fingerprint}")
    if closes:
        print(f"first_closed_at: {min(closes).isoformat()}")
        print(f"last_closed_at: {max(closes).isoformat()}")
    else:
        print("first_closed_at: NONE")
        print("last_closed_at: NONE")
    print(
        "RESULT: OK - catalog round-trips canonically and preserves "
        "the original DESIGN/VALIDATION/OOS roles."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
