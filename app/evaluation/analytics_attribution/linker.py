from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from app.analytics import AnalyticsLabRun, AnalyticsSnapshot
from app.common.canonical import stable_digest

from .index import AnalyticsSnapshotIndex
from .models import (
    AnalyticsSnapshotRef,
    DecisionObservationKey,
    OpportunityAnalyticsLink,
    OpportunityAnalyticsLinkSet,
    OpportunityAnalyticsLinkStatus,
    OpportunityObservationRef,
)


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    return value


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


def _resolved_policy_version(run: Any, point: Any) -> str | None:
    assumptions = getattr(getattr(run, "config", None), "execution_assumptions", {})
    configured = str(assumptions.get("mtf_policy_version", "")).strip()
    context = getattr(point, "decision_context", None)
    context_policy = (
        str(getattr(context, "timeframe_policy_version", "")).strip()
        if context is not None
        else ""
    )
    if configured and context_policy and configured != context_policy:
        raise ValueError("DecisionContext timeframe policy conflicts with BacktestRun")
    return configured or context_policy or None


def _resolved_cursor_fingerprint(point: Any) -> str | None:
    point_cursor = getattr(point, "mtf_cursor_fingerprint", None)
    context = getattr(point, "decision_context", None)
    context_cursor = None
    if context is not None:
        market = getattr(context, "market", None)
        context_cursor = getattr(market, "source_cursor_fingerprint", None)
    if (
        point_cursor is not None
        and context_cursor is not None
        and str(point_cursor) != str(context_cursor)
    ):
        raise ValueError(
            "DecisionContext market cursor fingerprint conflicts with replay point"
        )
    value = point_cursor if point_cursor is not None else context_cursor
    return str(value) if value is not None else None


def _validate_optional_decision_context(
    *,
    point: Any,
    observed_at: datetime,
    symbol: str,
    decision_timeframe: str,
    cursor_fingerprint: str | None,
) -> tuple[str | None, str | None]:
    context = getattr(point, "decision_context", None)
    if context is None:
        return None, None

    context_as_of = _as_utc(
        context.as_of,
        field_name="DecisionContext.as_of",
    )
    if context_as_of != observed_at:
        raise ValueError("DecisionContext.as_of must match replay point observed_at")
    if str(context.symbol) != symbol:
        raise ValueError("DecisionContext.symbol must match opportunity symbol")
    if str(context.primary_timeframe) != decision_timeframe:
        raise ValueError(
            "DecisionContext.primary_timeframe must match opportunity timeframe"
        )
    if cursor_fingerprint is not None:
        market = getattr(context, "market", None)
        context_cursor = getattr(market, "source_cursor_fingerprint", None)
        if context_cursor is None or str(context_cursor) != cursor_fingerprint:
            raise ValueError(
                "DecisionContext market cursor fingerprint must match replay point"
            )

    context_id = str(context.context_id)
    context_fingerprint = str(context.context_fingerprint)
    return context_id, context_fingerprint


def build_opportunity_observations(
    replay_result: Any,
) -> tuple[OpportunityObservationRef, ...]:
    """Adapt replay artifacts into generic causal observation identities.

    CandidateOpportunity remains unchanged. Its current `created_at` is validated as
    the causal observation time because the production Scanner sets it from
    FeatureSnapshot.observed_at.
    """

    backtest_result = replay_result.backtest_result
    status = _value(getattr(backtest_result, "status", None))
    if status is not None and str(status) != "COMPLETED":
        raise ValueError("analytics attribution requires a completed Historical Replay")
    run = backtest_result.run
    dataset = run.dataset
    config = run.config

    observations: list[OpportunityObservationRef] = []
    seen_opportunities: set[str] = set()
    for point in replay_result.points:
        opportunity = getattr(point, "opportunity", None)
        if opportunity is None:
            continue
        feature = getattr(point, "feature_snapshot", None)
        if feature is None:
            raise ValueError(
                "CandidateOpportunity replay point requires feature_snapshot"
            )

        observed_at = _as_utc(point.observed_at, field_name="replay point observed_at")
        feature_observed_at = _as_utc(
            feature.observed_at,
            field_name="FeatureSnapshot.observed_at",
        )
        opportunity_created_at = _as_utc(
            opportunity.created_at,
            field_name="CandidateOpportunity.created_at",
        )
        if feature_observed_at != observed_at or opportunity_created_at != observed_at:
            raise ValueError(
                "CandidateOpportunity, FeatureSnapshot and replay point "
                "must share as_of"
            )

        if str(opportunity.snapshot_id) != str(feature.snapshot_id):
            raise ValueError(
                "CandidateOpportunity.snapshot_id must match "
                "FeatureSnapshot.snapshot_id"
            )
        if str(opportunity.symbol) != str(feature.symbol):
            raise ValueError(
                "CandidateOpportunity.symbol must match FeatureSnapshot.symbol"
            )
        if str(opportunity.timeframe) != str(feature.timeframe):
            raise ValueError(
                "CandidateOpportunity.timeframe must match FeatureSnapshot.timeframe"
            )
        if str(opportunity.symbol) != str(dataset.symbol):
            raise ValueError("CandidateOpportunity.symbol must match source DatasetRef")
        if str(opportunity.system_id) != str(config.system_id):
            raise ValueError("CandidateOpportunity.system_id must match BacktestConfig")
        if str(feature.feature_version) != str(config.feature_version):
            raise ValueError(
                "FeatureSnapshot.feature_version must match BacktestConfig"
            )
        if str(opportunity.scanner_version) != str(config.scanner_version):
            raise ValueError(
                "CandidateOpportunity.scanner_version must match BacktestConfig"
            )

        decision_timeframe = str(
            getattr(point, "decision_timeframe", None) or feature.timeframe
        )
        if decision_timeframe != str(opportunity.timeframe):
            raise ValueError(
                "replay decision_timeframe must match CandidateOpportunity.timeframe"
            )

        cursor_fingerprint = _resolved_cursor_fingerprint(point)
        mtf_policy_version = _resolved_policy_version(run, point)
        context_id, context_fingerprint = _validate_optional_decision_context(
            point=point,
            observed_at=observed_at,
            symbol=str(opportunity.symbol),
            decision_timeframe=decision_timeframe,
            cursor_fingerprint=cursor_fingerprint,
        )

        opportunity_id = str(opportunity.opportunity_id)
        if opportunity_id in seen_opportunities:
            raise ValueError(
                "replay contains duplicate CandidateOpportunity.opportunity_id"
            )
        seen_opportunities.add(opportunity_id)

        key = DecisionObservationKey(
            source_backtest_run_id=str(run.run_id),
            dataset_id=str(dataset.dataset_id),
            dataset_version=str(dataset.version),
            dataset_content_sha256=str(dataset.content_sha256),
            dataset_source=str(dataset.source),
            system_id=str(config.system_id),
            symbol=str(opportunity.symbol),
            source_timeframe=str(dataset.timeframe),
            decision_timeframe=decision_timeframe,
            observed_at=observed_at,
            mtf_policy_version=mtf_policy_version,
            source_cursor_fingerprint=cursor_fingerprint,
            feature_snapshot_id=str(feature.snapshot_id),
            feature_version=str(feature.feature_version),
            scanner_version=str(opportunity.scanner_version),
        )
        observations.append(
            OpportunityObservationRef(
                observation=key,
                opportunity_id=opportunity_id,
                opportunity_fingerprint=stable_digest(_payload(opportunity)),
                decision_context_id=context_id,
                decision_context_fingerprint=context_fingerprint,
            )
        )

    return tuple(
        sorted(
            observations,
            key=lambda item: (
                item.observation.observed_at,
                item.opportunity_id,
            ),
        )
    )


class OpportunityAnalyticsLinker:
    """Join existing decision and Analytics artifacts without recomputation."""

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

    def link(self, opportunity: OpportunityObservationRef) -> OpportunityAnalyticsLink:
        source = opportunity.observation
        run = self.analytics_run

        if source.source_backtest_run_id != run.source_backtest_run_id:
            return self._unresolved(
                opportunity,
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
                opportunity,
                OpportunityAnalyticsLinkStatus.DATASET_MISMATCH,
                "dataset id/version/SHA/source mismatch",
            )
        if source.system_id != run.system_id:
            return self._unresolved(
                opportunity,
                OpportunityAnalyticsLinkStatus.SYSTEM_MISMATCH,
                "system_id mismatch",
            )
        if source.symbol != run.symbol:
            return self._unresolved(
                opportunity,
                OpportunityAnalyticsLinkStatus.SYMBOL_MISMATCH,
                "symbol mismatch",
            )
        if source.source_timeframe != run.source_timeframe:
            return self._unresolved(
                opportunity,
                OpportunityAnalyticsLinkStatus.SOURCE_TIMEFRAME_MISMATCH,
                "source timeframe mismatch",
            )
        if source.decision_timeframe != run.decision_timeframe:
            return self._unresolved(
                opportunity,
                OpportunityAnalyticsLinkStatus.TIMEFRAME_MISMATCH,
                "decision timeframe mismatch",
            )
        if source.mtf_policy_version is None:
            return self._unresolved(
                opportunity,
                OpportunityAnalyticsLinkStatus.SOURCE_PROVENANCE_INCOMPLETE,
                "source replay does not expose mtf_policy_version",
            )
        if source.mtf_policy_version != run.mtf_policy_version:
            return self._unresolved(
                opportunity,
                OpportunityAnalyticsLinkStatus.MTF_POLICY_MISMATCH,
                "MTF policy mismatch",
            )
        if not run.period_start <= source.observed_at <= run.period_end:
            return self._unresolved(
                opportunity,
                OpportunityAnalyticsLinkStatus.AS_OF_MISMATCH,
                "opportunity as_of is outside AnalyticsLabRun period",
            )
        if source.source_cursor_fingerprint is None:
            return self._unresolved(
                opportunity,
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
                opportunity,
                OpportunityAnalyticsLinkStatus.MISSING_ANALYTICS_SNAPSHOT,
                "no exact AnalyticsSnapshot exists for symbol/timeframe/as_of",
            )
        if len(candidates) > 1:
            candidate_ids = tuple(sorted(item.snapshot_id for item in candidates))
            return self._unresolved(
                opportunity,
                OpportunityAnalyticsLinkStatus.AMBIGUOUS_ANALYTICS_SNAPSHOT,
                (
                    "multiple exact AnalyticsSnapshot candidates: "
                    + ",".join(candidate_ids)
                ),
            )

        snapshot_ref = _snapshot_ref(candidates[0])
        if (
            source.source_cursor_fingerprint
            != snapshot_ref.source_cursor_fingerprint
        ):
            return OpportunityAnalyticsLink.create(
                analytics_run_id=run.analytics_run_id,
                status=OpportunityAnalyticsLinkStatus.CURSOR_FINGERPRINT_MISMATCH,
                opportunity=opportunity,
                analytics_snapshot=snapshot_ref,
                diagnostics=("source cursor fingerprint mismatch",),
            )

        return OpportunityAnalyticsLink.create(
            analytics_run_id=run.analytics_run_id,
            status=OpportunityAnalyticsLinkStatus.MATCHED,
            opportunity=opportunity,
            analytics_snapshot=snapshot_ref,
        )

    def _unresolved(
        self,
        opportunity: OpportunityObservationRef,
        status: OpportunityAnalyticsLinkStatus,
        diagnostic: str,
    ) -> OpportunityAnalyticsLink:
        return OpportunityAnalyticsLink.create(
            analytics_run_id=self.analytics_run.analytics_run_id,
            status=status,
            opportunity=opportunity,
            diagnostics=(diagnostic,),
        )

    def link_all(
        self,
        opportunities: Iterable[OpportunityObservationRef],
    ) -> OpportunityAnalyticsLinkSet:
        links = tuple(self.link(item) for item in opportunities)
        source_run_ids = {
            item.opportunity.observation.source_backtest_run_id for item in links
        }
        if len(source_run_ids) > 1:
            raise ValueError("link set cannot mix source BacktestRun identities")
        source_backtest_run_id = (
            next(iter(source_run_ids))
            if source_run_ids
            else self.analytics_run.source_backtest_run_id
        )
        return OpportunityAnalyticsLinkSet.create(
            source_backtest_run_id=source_backtest_run_id,
            analytics_run_id=self.analytics_run.analytics_run_id,
            analytics_period_role=str(_value(self.analytics_run.period_role)),
            links=links,
        )


def link_replay_opportunities(
    replay_result: Any,
    *,
    analytics_run: AnalyticsLabRun,
    snapshots: Iterable[AnalyticsSnapshot],
) -> OpportunityAnalyticsLinkSet:
    """Link all CandidateOpportunity artifacts from one completed replay post-hoc."""

    observations = build_opportunity_observations(replay_result)
    return OpportunityAnalyticsLinker(
        analytics_run=analytics_run,
        snapshots=snapshots,
    ).link_all(observations)


__all__ = [
    "OpportunityAnalyticsLinker",
    "build_opportunity_observations",
    "link_replay_opportunities",
]
