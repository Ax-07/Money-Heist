from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.analytics import AnalyticsLabRun, AnalyticsSnapshot
from app.common.canonical import stable_digest, stable_uuid
from app.evaluation.scanner_observations import (
    ScannerObservation,
    ScannerOutcomeClassification,
    build_scanner_observation,
    resolve_replay_cursor_fingerprint,
    resolve_replay_policy_version,
    validate_replay_decision_context,
)

from .models import (
    OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION,
    AnalyticsSnapshotRef,
    DecisionObservationKey,
    OpportunityAnalyticsLinkSet,
    OpportunityAnalyticsLinkStatus,
)
from .resolver import AnalyticsResolution, AnalyticsSnapshotResolver

SCANNER_ANALYTICS_ATTRIBUTION_SCHEMA_VERSION = (
    "money-heist.scanner-analytics-attribution.v1"
)
SCANNER_ANALYTICS_ATTRIBUTION_SET_SCHEMA_VERSION = (
    "money-heist.scanner-analytics-attribution-set.v1"
)
SCANNER_ANALYTICS_ATTRIBUTION_PROJECTION_VERSION = "scanner-analytics-attribution-v1"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _snapshot_id(resolution: AnalyticsResolution) -> str | None:
    snapshot = resolution.analytics_snapshot
    return snapshot.analytics_snapshot_id if snapshot is not None else None


class ScannerAnalyticsRef(FrozenModel):
    status: OpportunityAnalyticsLinkStatus
    analytics_snapshot: AnalyticsSnapshotRef | None = None
    diagnostics: tuple[str, ...] = ()
    opportunity_analytics_link_id: str | None = None
    decision_intelligence_record_id: str | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> ScannerAnalyticsRef:
        if tuple(sorted(set(self.diagnostics))) != self.diagnostics:
            raise ValueError("diagnostics must be sorted and unique")
        if (
            self.status is OpportunityAnalyticsLinkStatus.MATCHED
            and self.analytics_snapshot is None
        ):
            raise ValueError("MATCHED Scanner attribution requires analytics_snapshot")
        return self


class ScannerAnalyticsAttributionRecord(FrozenModel):
    schema_version: str = SCANNER_ANALYTICS_ATTRIBUTION_SCHEMA_VERSION
    projection_version: str = SCANNER_ANALYTICS_ATTRIBUTION_PROJECTION_VERSION
    analytics_match_policy_version: str = OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION
    record_id: str = Field(min_length=1)
    record_fingerprint: str = Field(min_length=64, max_length=64)
    source_backtest_run_id: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    scanner_evaluation_id: str = Field(min_length=1)
    observation: DecisionObservationKey
    scanner: ScannerObservation
    analytics: ScannerAnalyticsRef

    @field_validator("record_fingerprint")
    @classmethod
    def normalize_record_fingerprint(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("record_fingerprint must be a SHA-256 hex digest")
        return normalized

    @model_validator(mode="after")
    def validate_contract(self) -> ScannerAnalyticsAttributionRecord:
        if self.schema_version != SCANNER_ANALYTICS_ATTRIBUTION_SCHEMA_VERSION:
            raise ValueError("unsupported Scanner Analytics attribution schema")
        if self.projection_version != SCANNER_ANALYTICS_ATTRIBUTION_PROJECTION_VERSION:
            raise ValueError("unsupported Scanner Analytics projection version")
        if (
            self.analytics_match_policy_version
            != OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION
        ):
            raise ValueError("unsupported Analytics matching policy")
        if self.source_backtest_run_id != self.observation.source_backtest_run_id:
            raise ValueError("record source BacktestRun must match observation")
        if self.scanner_evaluation_id != self.scanner.scanner_evaluation_id:
            raise ValueError("record Scanner evaluation id must match Scanner projection")
        if self.scanner_evaluation_id != self.observation.feature_snapshot_id:
            raise ValueError("Scanner evaluation id must equal FeatureSnapshot.snapshot_id")
        if self.scanner.snapshot_id != self.observation.feature_snapshot_id:
            raise ValueError("Scanner snapshot must match observation feature snapshot")
        if self.scanner.observed_at != self.observation.observed_at:
            raise ValueError("Scanner observed_at must match observation")
        if self.scanner.symbol != self.observation.symbol:
            raise ValueError("Scanner symbol must match observation")
        if self.scanner.decision_timeframe != self.observation.decision_timeframe:
            raise ValueError("Scanner timeframe must match observation")
        if self.scanner.feature_version != self.observation.feature_version:
            raise ValueError("Scanner feature version must match observation")
        if self.scanner.scanner_version != self.observation.scanner_version:
            raise ValueError("Scanner version must match observation")

        is_candidate = (
            self.scanner.classification
            is ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY
        )
        candidate_refs = (
            self.analytics.opportunity_analytics_link_id,
            self.analytics.decision_intelligence_record_id,
        )
        if not is_candidate and any(value is not None for value in candidate_refs):
            raise ValueError("non-candidate Scanner records cannot carry candidate refs")

        snapshot = self.analytics.analytics_snapshot
        if self.analytics.status is OpportunityAnalyticsLinkStatus.MATCHED:
            assert snapshot is not None
            source = self.observation
            parity = (
                snapshot.analytics_run_id == self.analytics_run_id,
                snapshot.source_backtest_run_id == source.source_backtest_run_id,
                snapshot.dataset_id == source.dataset_id,
                snapshot.dataset_version == source.dataset_version,
                snapshot.dataset_content_sha256 == source.dataset_content_sha256,
                snapshot.symbol == source.symbol,
                snapshot.decision_timeframe == source.decision_timeframe,
                snapshot.as_of == source.observed_at,
                snapshot.mtf_policy_version == source.mtf_policy_version,
                snapshot.source_cursor_fingerprint == source.source_cursor_fingerprint,
            )
            if not all(parity):
                raise ValueError("MATCHED Scanner attribution must have exact parity")
        return self

    @classmethod
    def create(
        cls,
        *,
        source_backtest_run_id: str,
        analytics_run_id: str,
        observation: DecisionObservationKey,
        scanner: ScannerObservation,
        analytics: ScannerAnalyticsRef,
    ) -> ScannerAnalyticsAttributionRecord:
        identity_payload = {
            "schema": SCANNER_ANALYTICS_ATTRIBUTION_SCHEMA_VERSION,
            "projection_version": SCANNER_ANALYTICS_ATTRIBUTION_PROJECTION_VERSION,
            "analytics_match_policy_version": (
                OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION
            ),
            "source_backtest_run_id": source_backtest_run_id,
            "analytics_run_id": analytics_run_id,
            "scanner_evaluation_id": scanner.scanner_evaluation_id,
        }
        fingerprint_payload = {
            **identity_payload,
            "observation": observation.model_dump(mode="python"),
            "scanner": scanner.model_dump(mode="python"),
            "analytics": analytics.model_dump(mode="python"),
        }
        return cls(
            record_id=stable_uuid("scanner-analytics-attribution", identity_payload),
            record_fingerprint=stable_digest(fingerprint_payload),
            source_backtest_run_id=source_backtest_run_id,
            analytics_run_id=analytics_run_id,
            scanner_evaluation_id=scanner.scanner_evaluation_id,
            observation=observation,
            scanner=scanner,
            analytics=analytics,
        )


class ScannerAnalyticsAttributionSet(FrozenModel):
    schema_version: str = SCANNER_ANALYTICS_ATTRIBUTION_SET_SCHEMA_VERSION
    projection_version: str = SCANNER_ANALYTICS_ATTRIBUTION_PROJECTION_VERSION
    analytics_match_policy_version: str = OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION
    source_backtest_run_id: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    analytics_period_role: str = Field(min_length=1)
    total_scanner_evaluations: int = Field(ge=0)
    matched_analytics: int = Field(ge=0)
    unmatched_analytics: int = Field(ge=0)
    no_trigger_count: int = Field(ge=0)
    below_threshold_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    records: tuple[ScannerAnalyticsAttributionRecord, ...]
    set_fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("set_fingerprint")
    @classmethod
    def normalize_set_fingerprint(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("set_fingerprint must be a SHA-256 hex digest")
        return normalized

    @model_validator(mode="after")
    def validate_counts_and_order(self) -> ScannerAnalyticsAttributionSet:
        if self.total_scanner_evaluations != len(self.records):
            raise ValueError("total_scanner_evaluations must equal records length")
        if self.matched_analytics + self.unmatched_analytics != len(self.records):
            raise ValueError("Analytics counts must conserve Scanner evaluations")
        if (
            self.no_trigger_count
            + self.below_threshold_count
            + self.candidate_count
            != len(self.records)
        ):
            raise ValueError("Scanner classes must conserve Scanner evaluations")
        ids = tuple(item.scanner_evaluation_id for item in self.records)
        if len(set(ids)) != len(ids):
            raise ValueError("Scanner attribution set cannot contain duplicate evaluations")
        for item in self.records:
            if item.source_backtest_run_id != self.source_backtest_run_id:
                raise ValueError("record source BacktestRun does not match set")
            if item.analytics_run_id != self.analytics_run_id:
                raise ValueError("record AnalyticsLabRun does not match set")
        ordered = tuple(
            sorted(
                self.records,
                key=lambda item: (
                    item.observation.observed_at,
                    item.scanner_evaluation_id,
                    item.record_id,
                ),
            )
        )
        if ordered != self.records:
            raise ValueError("Scanner attribution records must be deterministically sorted")
        return self

    @classmethod
    def create(
        cls,
        *,
        source_backtest_run_id: str,
        analytics_run_id: str,
        analytics_period_role: str,
        records: tuple[ScannerAnalyticsAttributionRecord, ...],
    ) -> ScannerAnalyticsAttributionSet:
        ordered = tuple(
            sorted(
                records,
                key=lambda item: (
                    item.observation.observed_at,
                    item.scanner_evaluation_id,
                    item.record_id,
                ),
            )
        )
        matched = sum(
            1
            for item in ordered
            if item.analytics.status is OpportunityAnalyticsLinkStatus.MATCHED
        )
        no_trigger = sum(
            1
            for item in ordered
            if item.scanner.classification is ScannerOutcomeClassification.NO_TRIGGER
        )
        below = sum(
            1
            for item in ordered
            if item.scanner.classification
            is ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD
        )
        candidate = sum(
            1
            for item in ordered
            if item.scanner.classification
            is ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY
        )
        fingerprint_payload = {
            "schema": SCANNER_ANALYTICS_ATTRIBUTION_SET_SCHEMA_VERSION,
            "projection_version": SCANNER_ANALYTICS_ATTRIBUTION_PROJECTION_VERSION,
            "analytics_match_policy_version": (
                OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION
            ),
            "source_backtest_run_id": source_backtest_run_id,
            "analytics_run_id": analytics_run_id,
            "analytics_period_role": analytics_period_role,
            "record_fingerprints": tuple(item.record_fingerprint for item in ordered),
        }
        return cls(
            source_backtest_run_id=source_backtest_run_id,
            analytics_run_id=analytics_run_id,
            analytics_period_role=analytics_period_role,
            total_scanner_evaluations=len(ordered),
            matched_analytics=matched,
            unmatched_analytics=len(ordered) - matched,
            no_trigger_count=no_trigger,
            below_threshold_count=below,
            candidate_count=candidate,
            records=ordered,
            set_fingerprint=stable_digest(fingerprint_payload),
        )


def _build_scanner_sources(
    replay_result: Any,
    *,
    min_priority_score: int,
) -> tuple[tuple[DecisionObservationKey, ScannerObservation], ...]:
    backtest_result = replay_result.backtest_result
    status = _value(getattr(backtest_result, "status", None))
    if status is not None and str(status) != "COMPLETED":
        raise ValueError("Scanner attribution requires a completed Historical Replay")
    run = backtest_result.run
    dataset = run.dataset
    config = run.config

    output: list[tuple[DecisionObservationKey, ScannerObservation]] = []
    seen_scan_ids: set[str] = set()
    for point in replay_result.points:
        scanner = build_scanner_observation(
            point,
            scanner_version=str(config.scanner_version),
            min_priority_score=int(min_priority_score),
        )
        feature = point.feature_snapshot
        if scanner.scanner_evaluation_id in seen_scan_ids:
            raise ValueError("replay contains duplicate Scanner evaluation id")
        seen_scan_ids.add(scanner.scanner_evaluation_id)

        if scanner.symbol != str(dataset.symbol):
            raise ValueError("FeatureSnapshot.symbol must match source DatasetRef")
        if scanner.feature_version != str(config.feature_version):
            raise ValueError("FeatureSnapshot.feature_version must match BacktestConfig")
        if scanner.scanner_version != str(config.scanner_version):
            raise ValueError("Scanner version must match BacktestConfig")

        opportunity = getattr(point.scan_result, "opportunity", None)
        point_opportunity = getattr(point, "opportunity", opportunity)
        if opportunity is None and point_opportunity is not None:
            raise ValueError("replay point opportunity conflicts with ScanResult")
        if opportunity is not None:
            if point_opportunity is None or str(point_opportunity.opportunity_id) != str(
                opportunity.opportunity_id
            ):
                raise ValueError("replay point opportunity conflicts with ScanResult")
            if str(opportunity.system_id) != str(config.system_id):
                raise ValueError("CandidateOpportunity.system_id must match BacktestConfig")
            if str(opportunity.symbol) != scanner.symbol:
                raise ValueError("CandidateOpportunity.symbol must match Scanner observation")
            if str(opportunity.timeframe) != scanner.decision_timeframe:
                raise ValueError(
                    "CandidateOpportunity.timeframe must match Scanner observation"
                )

        cursor_fingerprint = resolve_replay_cursor_fingerprint(point)
        mtf_policy_version = resolve_replay_policy_version(run, point)
        validate_replay_decision_context(
            point=point,
            observed_at=scanner.observed_at,
            symbol=scanner.symbol,
            decision_timeframe=scanner.decision_timeframe,
            cursor_fingerprint=cursor_fingerprint,
        )

        key = DecisionObservationKey(
            source_backtest_run_id=str(run.run_id),
            dataset_id=str(dataset.dataset_id),
            dataset_version=str(dataset.version),
            dataset_content_sha256=str(dataset.content_sha256),
            dataset_source=str(dataset.source),
            system_id=str(config.system_id),
            symbol=scanner.symbol,
            source_timeframe=str(dataset.timeframe),
            decision_timeframe=scanner.decision_timeframe,
            observed_at=scanner.observed_at,
            mtf_policy_version=mtf_policy_version,
            source_cursor_fingerprint=cursor_fingerprint,
            feature_snapshot_id=str(feature.snapshot_id),
            feature_version=scanner.feature_version,
            scanner_version=scanner.scanner_version,
        )
        output.append((key, scanner))

    return tuple(
        sorted(
            output,
            key=lambda item: (
                item[0].observed_at,
                item[1].scanner_evaluation_id,
            ),
        )
    )


def _opportunity_link_map(
    links: OpportunityAnalyticsLinkSet | None,
    *,
    source_backtest_run_id: str,
    analytics_run_id: str,
) -> dict[str, Any] | None:
    if links is None:
        return None
    if links.source_backtest_run_id != source_backtest_run_id:
        raise ValueError("Opportunity Analytics link set source BacktestRun mismatch")
    if links.analytics_run_id != analytics_run_id:
        raise ValueError("Opportunity Analytics link set AnalyticsLabRun mismatch")
    return {item.opportunity.opportunity_id: item for item in links.links}


def _decision_record_map(
    record_set: Any | None,
    *,
    source_backtest_run_id: str,
    analytics_run_id: str,
) -> dict[str, Any] | None:
    if record_set is None:
        return None
    if str(record_set.source_backtest_run_id) != source_backtest_run_id:
        raise ValueError("Decision Intelligence set source BacktestRun mismatch")
    if str(record_set.analytics_run_id) != analytics_run_id:
        raise ValueError("Decision Intelligence set AnalyticsLabRun mismatch")
    records = tuple(record_set.records)
    mapping = {str(item.opportunity_id): item for item in records}
    if len(mapping) != len(records):
        raise ValueError("Decision Intelligence set contains duplicate opportunity ids")
    return mapping


def _validate_candidate_opportunity_link(
    *,
    opportunity_id: str,
    source: DecisionObservationKey,
    resolution: AnalyticsResolution,
    link_map: dict[str, Any] | None,
) -> str | None:
    if link_map is None:
        return None
    link = link_map.get(opportunity_id)
    if link is None:
        raise ValueError("candidate Scanner evaluation is missing its 24B.1 link")
    if link.opportunity.observation != source:
        raise ValueError("candidate Scanner observation does not match its 24B.1 link")
    if link.status is not resolution.status:
        raise ValueError("candidate Scanner Analytics status diverges from 24B.1")
    if link.analytics_snapshot != resolution.analytics_snapshot:
        raise ValueError("candidate Scanner Analytics snapshot diverges from 24B.1")
    if tuple(link.diagnostics) != resolution.diagnostics:
        raise ValueError("candidate Scanner Analytics diagnostics diverge from 24B.1")
    return str(link.link_id)


def _validate_candidate_decision_record(
    *,
    opportunity_id: str,
    source: DecisionObservationKey,
    scanner: ScannerObservation,
    resolution: AnalyticsResolution,
    record_map: dict[str, Any] | None,
) -> str | None:
    if record_map is None:
        return None
    record = record_map.get(opportunity_id)
    if record is None:
        raise ValueError("candidate Scanner evaluation is missing its 24B.2 record")
    if str(record.source_backtest_run_id) != source.source_backtest_run_id:
        raise ValueError("24B.2 source BacktestRun diverges from Scanner attribution")
    if str(record.opportunity_id) != opportunity_id:
        raise ValueError("24B.2 opportunity id diverges from Scanner attribution")
    if str(record.scanner.snapshot_id) != scanner.scanner_evaluation_id:
        raise ValueError("24B.2 Scanner snapshot diverges from Scanner attribution")
    if record.observed_at != source.observed_at:
        raise ValueError("24B.2 observed_at diverges from Scanner attribution")
    if str(record.analytics.status) != resolution.status.value:
        raise ValueError("24B.2 Analytics status diverges from Scanner attribution")
    if getattr(record.analytics, "analytics_snapshot_id", None) != _snapshot_id(resolution):
        raise ValueError("24B.2 Analytics snapshot diverges from Scanner attribution")
    return str(record.record_id)


def build_scanner_analytics_attribution(
    replay_result: Any,
    *,
    analytics_run: AnalyticsLabRun,
    snapshots: Iterable[AnalyticsSnapshot],
    min_priority_score: int,
    opportunity_links: OpportunityAnalyticsLinkSet | None = None,
    decision_intelligence_records: Any | None = None,
) -> ScannerAnalyticsAttributionSet:
    """Attribute every existing Scanner evaluation to an exact AnalyticsSnapshot.

    The function is post-hoc and read-only: it consumes Historical Replay artifacts,
    never reruns Scanner, and never feeds Analytics back into a decision path.
    """

    sources = _build_scanner_sources(
        replay_result,
        min_priority_score=int(min_priority_score),
    )
    source_backtest_run_id = str(replay_result.backtest_result.run.run_id)
    analytics_run_id = str(analytics_run.analytics_run_id)
    link_map = _opportunity_link_map(
        opportunity_links,
        source_backtest_run_id=source_backtest_run_id,
        analytics_run_id=analytics_run_id,
    )
    record_map = _decision_record_map(
        decision_intelligence_records,
        source_backtest_run_id=source_backtest_run_id,
        analytics_run_id=analytics_run_id,
    )
    resolver = AnalyticsSnapshotResolver(
        analytics_run=analytics_run,
        snapshots=snapshots,
    )

    records: list[ScannerAnalyticsAttributionRecord] = []
    for source, scanner in sources:
        resolution = resolver.resolve(source)
        link_id = None
        decision_record_id = None
        opportunity_id = scanner.candidate_opportunity_id
        if opportunity_id is not None:
            link_id = _validate_candidate_opportunity_link(
                opportunity_id=opportunity_id,
                source=source,
                resolution=resolution,
                link_map=link_map,
            )
            decision_record_id = _validate_candidate_decision_record(
                opportunity_id=opportunity_id,
                source=source,
                scanner=scanner,
                resolution=resolution,
                record_map=record_map,
            )

        analytics = ScannerAnalyticsRef(
            status=resolution.status,
            analytics_snapshot=resolution.analytics_snapshot,
            diagnostics=resolution.diagnostics,
            opportunity_analytics_link_id=link_id,
            decision_intelligence_record_id=decision_record_id,
        )
        records.append(
            ScannerAnalyticsAttributionRecord.create(
                source_backtest_run_id=source_backtest_run_id,
                analytics_run_id=analytics_run_id,
                observation=source,
                scanner=scanner,
                analytics=analytics,
            )
        )

    return ScannerAnalyticsAttributionSet.create(
        source_backtest_run_id=source_backtest_run_id,
        analytics_run_id=analytics_run_id,
        analytics_period_role=str(_value(analytics_run.period_role)),
        records=tuple(records),
    )


__all__ = [
    "SCANNER_ANALYTICS_ATTRIBUTION_PROJECTION_VERSION",
    "SCANNER_ANALYTICS_ATTRIBUTION_SCHEMA_VERSION",
    "SCANNER_ANALYTICS_ATTRIBUTION_SET_SCHEMA_VERSION",
    "ScannerAnalyticsAttributionRecord",
    "ScannerAnalyticsAttributionSet",
    "ScannerAnalyticsRef",
    "build_scanner_analytics_attribution",
]
