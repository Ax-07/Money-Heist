from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime

from app.analytics import AnalyticsLabRun, AnalyticsSnapshot


class AnalyticsSnapshotIndex:
    """Read-only exact-key index over canonical AnalyticsSnapshot artifacts."""

    def __init__(
        self,
        *,
        analytics_run: AnalyticsLabRun,
        snapshots: Iterable[AnalyticsSnapshot],
    ) -> None:
        self.analytics_run = analytics_run
        ordered = tuple(
            sorted(snapshots, key=lambda item: (item.as_of, item.snapshot_id))
        )
        snapshot_ids = tuple(item.snapshot_id for item in ordered)
        if len(set(snapshot_ids)) != len(snapshot_ids):
            raise ValueError(
                "analytics snapshot index cannot contain duplicate snapshot_id"
            )

        buckets: dict[
            tuple[str, str, datetime], list[AnalyticsSnapshot]
        ] = defaultdict(list)
        for snapshot in ordered:
            self._validate_snapshot(snapshot)
            buckets[
                (
                    snapshot.symbol,
                    snapshot.decision_timeframe,
                    snapshot.as_of.astimezone(UTC),
                )
            ].append(snapshot)

        self._snapshots = ordered
        self._buckets = {
            key: tuple(value)
            for key, value in sorted(
                buckets.items(),
                key=lambda item: (item[0][2], item[0][0], item[0][1]),
            )
        }

    def _validate_snapshot(self, snapshot: AnalyticsSnapshot) -> None:
        run = self.analytics_run
        expected = {
            "analytics_run_id": run.analytics_run_id,
            "source_backtest_run_id": run.source_backtest_run_id,
            "dataset_id": run.dataset_id,
            "dataset_version": run.dataset_version,
            "dataset_content_sha256": run.dataset_content_sha256,
            "symbol": run.symbol,
            "decision_timeframe": run.decision_timeframe,
            "mtf_policy_version": run.mtf_policy_version,
        }
        for field_name, expected_value in expected.items():
            if getattr(snapshot, field_name) != expected_value:
                raise ValueError(
                    f"analytics snapshot {field_name} does not match AnalyticsLabRun"
                )
        if not run.period_start <= snapshot.as_of <= run.period_end:
            raise ValueError(
                "analytics snapshot as_of is outside AnalyticsLabRun period"
            )
        if (
            snapshot.component_versions.canonical_payload()
            != run.component_versions.canonical_payload()
        ):
            raise ValueError(
                "analytics snapshot component_versions do not match AnalyticsLabRun"
            )

    @property
    def snapshots(self) -> tuple[AnalyticsSnapshot, ...]:
        return self._snapshots

    def exact(
        self,
        *,
        symbol: str,
        decision_timeframe: str,
        as_of: datetime,
    ) -> tuple[AnalyticsSnapshot, ...]:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        key = (symbol, decision_timeframe, as_of.astimezone(UTC))
        return self._buckets.get(key, ())


__all__ = ["AnalyticsSnapshotIndex"]
