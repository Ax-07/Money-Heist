from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.backtest.historical_derivatives_analytics import (
    HISTORICAL_DERIVATIVES_CONTEXT_BINDING_VERSION,
    HistoricalDerivativesAnalyticsArchive,
)


def _at(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("validator timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _check_context(
    archive: HistoricalDerivativesAnalyticsArchive,
    *,
    as_of: datetime,
    expected_quality: str,
    expect_funding: bool,
):
    snapshot = archive.positioning_snapshot_at(
        as_of=as_of,
        max_age=timedelta(hours=2),
    )
    if snapshot is None:
        raise SystemExit(f"no derivatives snapshot at {as_of.isoformat()}")
    rio = archive.rio_context_from_snapshot(snapshot)
    if rio.data_quality != expected_quality:
        raise SystemExit(
            f"unexpected Rio quality at {as_of.isoformat()}: "
            f"{rio.data_quality}"
        )
    if (rio.funding_rate is not None) != expect_funding:
        raise SystemExit(
            f"unexpected funding availability at {as_of.isoformat()}"
        )
    if rio.open_interest is None:
        raise SystemExit("open_interest unexpectedly unavailable")
    if rio.open_interest_change_pct is None:
        raise SystemExit("open_interest_change_pct unexpectedly unavailable")
    if rio.long_short_ratio is None:
        raise SystemExit("long_short_ratio unexpectedly unavailable")
    if rio.long_liquidations_notional is not None:
        raise SystemExit("long liquidations must remain unavailable")
    if rio.short_liquidations_notional is not None:
        raise SystemExit("short liquidations must remain unavailable")

    if rio.open_interest != float(snapshot.open_interest):
        raise SystemExit("Rio open_interest diverges from frozen snapshot")
    if rio.open_interest_change_pct != float(snapshot.open_interest_change_pct):
        raise SystemExit("Rio OI change diverges from frozen snapshot")
    if rio.long_short_ratio != float(snapshot.long_short_ratio):
        raise SystemExit("Rio long/short ratio diverges from frozen snapshot")
    if expect_funding and rio.funding_rate != float(snapshot.funding_rate):
        raise SystemExit("Rio funding diverges from frozen snapshot")

    return snapshot, rio


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Batch 16.21k frozen historical Rio projection."
    )
    parser.add_argument("canonical_csv", type=Path)
    args = parser.parse_args()

    archive = HistoricalDerivativesAnalyticsArchive.from_canonical_csv(
        args.canonical_csv
    )

    pre_snapshot, pre_rio = _check_context(
        archive,
        as_of=_at("2025-10-01T12:00:00Z"),
        expected_quality="DEGRADED",
        expect_funding=False,
    )
    post_snapshot, post_rio = _check_context(
        archive,
        as_of=_at("2026-09-10T12:00:00Z"),
        expected_quality="RELIABLE",
        expect_funding=True,
    )

    print("Money Heist Batch 16.21k Historical Rio Wiring validation")
    print(
        "binding_version: "
        f"{HISTORICAL_DERIVATIVES_CONTEXT_BINDING_VERSION}"
    )
    print(f"archive_version: {archive.version}")
    print(f"archive_fingerprint: {archive.dataset_fingerprint}")
    print("pre_funding:")
    print(f"  snapshot_observed_at: {pre_snapshot.observed_at.isoformat()}")
    print(f"  snapshot_available_at: {pre_snapshot.received_at.isoformat()}")
    print(f"  rio_quality: {pre_rio.data_quality}")
    print("  funding_rate: UNAVAILABLE")
    print(f"  open_interest: {pre_rio.open_interest}")
    print(f"  open_interest_change_pct: {pre_rio.open_interest_change_pct}")
    print(f"  long_short_ratio: {pre_rio.long_short_ratio}")
    print("post_funding:")
    print(f"  snapshot_observed_at: {post_snapshot.observed_at.isoformat()}")
    print(f"  snapshot_available_at: {post_snapshot.received_at.isoformat()}")
    print(f"  rio_quality: {post_rio.data_quality}")
    print(f"  funding_rate: {post_rio.funding_rate}")
    print(f"  open_interest: {post_rio.open_interest}")
    print(f"  open_interest_change_pct: {post_rio.open_interest_change_pct}")
    print(f"  long_short_ratio: {post_rio.long_short_ratio}")
    print("liquidations: UNAVAILABLE")
    print(
        "RESULT: OK - Rio is projected from the exact frozen cutoff-safe "
        "derivatives snapshot with no synthetic metrics."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
