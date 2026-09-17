from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, model_validator

from app.analytics import AnalyticsLabRun, AnalyticsSnapshot
from app.common.canonical import stable_digest

from .index import AnalyticsSnapshotIndex
from .models import (
    AnalyticsSnapshotRef,
    DecisionObservationKey,
    OpportunityAnalyticsLinkStatus,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _snapshot_ref(snapshot: AnalyticsSnapshot) -> AnalyticsSnapshotRef:
    return AnalyticsSnapshotRef(
        analytics_run_id=snapshot.analytics_run_id,
        analytics_snapshot_id=snapshot.snapshot_id,
        analytics_snapshot_fingerprint=stable_digest(snapshot.identity_payload()),
        source_backtest_run_id=snapshot.source_backtest_run_id,
        dataset_id=snapshot.dataset_id,
        dataset_version=snapshot.dataset_version,
        dataset_content_sha256=snapshot.dataset_content_sha256,
        symbol=snapshot.symbol,
        decision_timeframe=snapshot.decision_timeframe,
        as_of=snapshot.as_of,
        mtf_policy_version=snapshot.mtf_policy_version,
        source_cursor_fingerprint=snapshot.source_cursor_fingerprint,
        analytics_bundle_version=snapshot.analytics_bundle_version,
    )


class AnalyticsResolution(FrozenModel):
    """Generic exact attribution result for one causal observation."""

    status: OpportunityAnalyticsLinkStatus
    analytics_snapshot: AnalyticsSnapshotRef | None = None
    diagnostics: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_contract(self) -> AnalyticsResolution:
        if tuple(sorted(set(self.diagnostics))) != self.diagnostics:
            raise ValueError("diagnostics must be sorted and unique")
        if (
            self.status is OpportunityAnalyticsLinkStatus.MATCHED
            and self.analytics_snapshot is None
        ):
            raise ValueError("MATCHED resolution requires analytics_snapshot")
        return self

    @classmethod
    def create(
        cls,
        *,
        status: OpportunityAnalyticsLinkStatus,
        analytics_snapshot: AnalyticsSnapshotRef | None = None,
        diagnostics: tuple[str, ...] = (),
    ) -> AnalyticsResolution:
        return cls(
            status=status,
            analytics_snapshot=analytics_snapshot,
            diagnostics=tuple(sorted(set(diagnostics))),
        )


class AnalyticsSnapshotResolver:
    """Single exact matching engine shared by Opportunity and Scanner attribution."""

    def __init__(
        self,
        *,
        analytics_run: AnalyticsLabRun,
        snapshots: Iterable[AnalyticsSnapshot],
    ) -> None:
        self.analytics_run = analytics_run
        self.index = AnalyticsSnapshotIndex(
            analytics_run=analytics_run,
            snapshots=snapshots,
        )

    def resolve(self, source: DecisionObservationKey) -> AnalyticsResolution:
        run = self.analytics_run

        if source.source_backtest_run_id != run.source_backtest_run_id:
            return self._unresolved(
                OpportunityAnalyticsLinkStatus.SOURCE_BACKTEST_RUN_MISMATCH,
                "source BacktestRun does not match explicit AnalyticsLabRun",
            )

        source_dataset = (
            source.dataset_id,
            source.dataset_version,
            source.dataset_content_sha256,
            source.dataset_source,
        )
        analytics_dataset = (
            run.dataset_id,
            run.dataset_version,
            run.dataset_content_sha256,
            run.dataset_source,
        )
        if source_dataset != analytics_dataset:
            return self._unresolved(
                OpportunityAnalyticsLinkStatus.DATASET_MISMATCH,
                "dataset id/version/SHA/source mismatch",
            )
        if source.system_id != run.system_id:
            return self._unresolved(
                OpportunityAnalyticsLinkStatus.SYSTEM_MISMATCH,
                "system_id mismatch",
            )
        if source.symbol != run.symbol:
            return self._unresolved(
                OpportunityAnalyticsLinkStatus.SYMBOL_MISMATCH,
                "symbol mismatch",
            )
        if source.source_timeframe != run.source_timeframe:
            return self._unresolved(
                OpportunityAnalyticsLinkStatus.SOURCE_TIMEFRAME_MISMATCH,
                "source timeframe mismatch",
            )
        if source.decision_timeframe != run.decision_timeframe:
            return self._unresolved(
                OpportunityAnalyticsLinkStatus.TIMEFRAME_MISMATCH,
                "decision timeframe mismatch",
            )
        if source.mtf_policy_version is None:
            return self._unresolved(
                OpportunityAnalyticsLinkStatus.SOURCE_PROVENANCE_INCOMPLETE,
                "source replay does not expose mtf_policy_version",
            )
        if source.mtf_policy_version != run.mtf_policy_version:
            return self._unresolved(
                OpportunityAnalyticsLinkStatus.MTF_POLICY_MISMATCH,
                "MTF policy mismatch",
            )
        if not run.period_start <= source.observed_at <= run.period_end:
            return self._unresolved(
                OpportunityAnalyticsLinkStatus.AS_OF_MISMATCH,
                "opportunity as_of is outside AnalyticsLabRun period",
            )
        if source.source_cursor_fingerprint is None:
            return self._unresolved(
                OpportunityAnalyticsLinkStatus.SOURCE_PROVENANCE_INCOMPLETE,
                "source replay does not expose source_cursor_fingerprint",
            )

        candidates = self.index.exact(
            symbol=source.symbol,
            decision_timeframe=source.decision_timeframe,
            as_of=source.observed_at,
        )
        if not candidates:
            return self._unresolved(
                OpportunityAnalyticsLinkStatus.MISSING_ANALYTICS_SNAPSHOT,
                "no exact AnalyticsSnapshot exists for symbol/timeframe/as_of",
            )
        if len(candidates) > 1:
            candidate_ids = tuple(sorted(item.snapshot_id for item in candidates))
            return self._unresolved(
                OpportunityAnalyticsLinkStatus.AMBIGUOUS_ANALYTICS_SNAPSHOT,
                (
                    "multiple exact AnalyticsSnapshot candidates: "
                    + ",".join(candidate_ids)
                ),
            )

        snapshot_ref = _snapshot_ref(candidates[0])
        if source.source_cursor_fingerprint != snapshot_ref.source_cursor_fingerprint:
            return AnalyticsResolution.create(
                status=OpportunityAnalyticsLinkStatus.CURSOR_FINGERPRINT_MISMATCH,
                analytics_snapshot=snapshot_ref,
                diagnostics=("source cursor fingerprint mismatch",),
            )

        return AnalyticsResolution.create(
            status=OpportunityAnalyticsLinkStatus.MATCHED,
            analytics_snapshot=snapshot_ref,
        )

    @staticmethod
    def _unresolved(
        status: OpportunityAnalyticsLinkStatus,
        diagnostic: str,
    ) -> AnalyticsResolution:
        return AnalyticsResolution.create(
            status=status,
            diagnostics=(diagnostic,),
        )


__all__ = [
    "AnalyticsResolution",
    "AnalyticsSnapshotResolver",
]
