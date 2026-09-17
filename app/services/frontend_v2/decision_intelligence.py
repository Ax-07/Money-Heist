from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from app.common.canonical import stable_digest

FRONTEND_DECISION_INTELLIGENCE_BUNDLE_SCHEMA_VERSION = "money-heist.frontend-decision-intelligence-bundle.v1"
FRONTEND_ANALYTICS_PROJECTION_SCHEMA_VERSION = "money-heist.frontend-analytics-projection.v1"
FRONTEND_SCANNER_ANALYTICS_SCHEMA_VERSION = "money-heist.frontend-scanner-analytics.v1"
FRONTEND_DECISION_DETAIL_SCHEMA_VERSION = "money-heist.frontend-decision-intelligence-detail.v1"

PeriodRole = Literal["DESIGN", "VALIDATION", "OOS"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, Enum):
        return _json_value(value.value)
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if hasattr(value, "canonical_payload"):
        return _json_value(value.canonical_payload())
    raise TypeError(f"unsupported projection value: {type(value).__name__}")


class FrontendAnalyticsRunProjection(FrozenModel):
    analytics_run_id: str
    identity_sha256: str
    source_backtest_run_id: str
    dataset_id: str
    dataset_version: str
    dataset_content_sha256: str
    dataset_source: str
    system_id: str
    symbol: str
    source_timeframe: str
    decision_timeframe: str
    period_start: datetime
    period_end: datetime
    period_role: PeriodRole
    mtf_policy_version: str
    analytics_bundle_version: str
    component_versions: dict[str, str]
    analytics_sha256: str
    snapshot_count: int = Field(ge=0)

    @field_validator("period_start", "period_end")
    @classmethod
    def normalize_timestamps(cls, value: datetime) -> datetime:
        return _utc(value)


class FrontendAnalyticsSnapshotProjection(FrozenModel):
    snapshot_id: str
    analytics_run_id: str
    as_of: datetime
    symbol: str
    decision_timeframe: str
    snapshot_fingerprint: str
    source_cursor_fingerprint: str
    component_names: tuple[str, ...] = ()

    @field_validator("as_of")
    @classmethod
    def normalize_as_of(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("component_names")
    @classmethod
    def validate_component_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("component_names must be sorted and unique")
        return value


class FrontendAnalyticsProjection(FrozenModel):
    schema_version: str = FRONTEND_ANALYTICS_PROJECTION_SCHEMA_VERSION
    campaign_id: str
    role: PeriodRole
    analytics_available: bool
    unavailable_reason: str | None = None
    run: FrontendAnalyticsRunProjection | None = None
    snapshots: tuple[FrontendAnalyticsSnapshotProjection, ...] = ()
    opportunity_count: int = Field(default=0, ge=0)
    scanner_evaluation_count: int = Field(default=0, ge=0)
    decision_record_count: int = Field(default=0, ge=0)
    funnel_stage_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_availability(self) -> FrontendAnalyticsProjection:
        if self.analytics_available:
            if self.run is None:
                raise ValueError("available Analytics projection requires run identity")
            if self.unavailable_reason is not None:
                raise ValueError("available Analytics projection cannot carry unavailable_reason")
        elif self.run is not None or self.snapshots:
            raise ValueError("unavailable Analytics projection cannot carry Analytics artifacts")
        ordered = tuple(sorted(self.snapshots, key=lambda item: (item.as_of, item.snapshot_id)))
        if ordered != self.snapshots:
            raise ValueError("Analytics snapshots must be deterministically sorted")
        return self


class FrontendAnalyticsRefProjection(FrozenModel):
    status: str
    analytics_run_id: str
    analytics_link_id: str | None = None
    analytics_link_fingerprint: str | None = None
    analytics_link_policy_version: str | None = None
    opportunity_analytics_link_id: str | None = None
    decision_intelligence_record_id: str | None = None
    analytics_snapshot_id: str | None = None
    analytics_snapshot_fingerprint: str | None = None
    analytics_as_of: datetime | None = None
    source_cursor_fingerprint: str | None = None
    analytics_snapshot_source_cursor_fingerprint: str | None = None
    diagnostics: tuple[str, ...] = ()

    @field_validator("analytics_as_of")
    @classmethod
    def normalize_analytics_as_of(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)


class FrontendScannerEvaluationProjection(FrozenModel):
    record_id: str
    scanner_evaluation_id: str
    observed_at: datetime
    symbol: str
    decision_timeframe: str
    classification: str
    score: int = Field(ge=0, le=100)
    priority_score: int = Field(ge=0, le=100)
    candidate_threshold: int = Field(ge=0, le=100)
    score_margin: int = Field(ge=-100, le=100)
    triggers: tuple[str, ...] = ()
    market_regime: str | None = None
    candidate_opportunity_id: str | None = None
    analytics: FrontendAnalyticsRefProjection

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _utc(value)


class FrontendScannerAnalyticsProjection(FrozenModel):
    schema_version: str = FRONTEND_SCANNER_ANALYTICS_SCHEMA_VERSION
    campaign_id: str
    role: PeriodRole
    analytics_available: bool
    unavailable_reason: str | None = None
    source_backtest_run_id: str | None = None
    analytics_run_id: str | None = None
    total_scanner_evaluations: int = Field(default=0, ge=0)
    matched_analytics: int = Field(default=0, ge=0)
    unmatched_analytics: int = Field(default=0, ge=0)
    no_trigger_count: int = Field(default=0, ge=0)
    below_threshold_count: int = Field(default=0, ge=0)
    candidate_count: int = Field(default=0, ge=0)
    records: tuple[FrontendScannerEvaluationProjection, ...] = ()

    @model_validator(mode="after")
    def validate_counts(self) -> FrontendScannerAnalyticsProjection:
        if not self.analytics_available:
            if self.records:
                raise ValueError("unavailable scanner projection cannot carry records")
            return self
        if self.source_backtest_run_id is None or self.analytics_run_id is None:
            raise ValueError("available scanner projection requires run identities")
        if self.total_scanner_evaluations != len(self.records):
            raise ValueError("scanner total must equal records length")
        if self.matched_analytics + self.unmatched_analytics != len(self.records):
            raise ValueError("scanner Analytics counts must conserve records")
        if self.no_trigger_count + self.below_threshold_count + self.candidate_count != len(self.records):
            raise ValueError("scanner class counts must conserve records")
        ordered = tuple(sorted(self.records, key=lambda item: (item.observed_at, item.scanner_evaluation_id)))
        if ordered != self.records:
            raise ValueError("scanner records must be deterministically sorted")
        return self


class FrontendOpportunityAnalyticsLinkProjection(FrozenModel):
    link_id: str
    link_fingerprint: str
    status: str
    opportunity_id: str
    opportunity_fingerprint: str
    observed_at: datetime
    decision_timeframe: str
    analytics_snapshot_id: str | None = None
    analytics_snapshot_fingerprint: str | None = None
    analytics_as_of: datetime | None = None
    diagnostics: tuple[str, ...] = ()

    @field_validator("observed_at", "analytics_as_of")
    @classmethod
    def normalize_optional_timestamps(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)


class FrontendFunnelStageProjection(FrozenModel):
    record_id: str
    record_fingerprint: str
    decision_intelligence_record_id: str
    opportunity_id: str
    stage: str
    stage_order: int = Field(ge=0)
    stage_instance_id: str | None = None
    stage_instance_order: int | None = None
    agent_id: str | None = None
    agent_request_id: str | None = None
    agent_prompt_version: str | None = None
    agent_route_id: str | None = None
    agent_model_id: str | None = None
    reached: bool
    stage_status: str | None = None
    stage_result: str | None = None
    reason_codes: tuple[str, ...] = ()
    selected_agents: tuple[str, ...] = ()
    confidence: float | None = Field(default=None, ge=0, le=1)
    severity: float | None = Field(default=None, ge=0, le=1)
    failure_code: str | None = None
    failure_stage: str | None = None
    failure_agent_id: str | None = None
    market_as_of: datetime
    operational_at: datetime | None = None
    source_artifact_ref: str | None = None
    source_artifact_fingerprint: str | None = None
    source_projection_fingerprint: str
    analytics: FrontendAnalyticsRefProjection

    @field_validator("market_as_of", "operational_at")
    @classmethod
    def normalize_stage_timestamps(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)


class FrontendDecisionContextProjection(FrozenModel):
    present: bool
    context_id: str | None = None
    context_fingerprint: str | None = None
    schema_version: str | None = None
    context_version: str | None = None
    system_id: str | None = None
    symbol: str | None = None
    as_of: datetime | None = None
    primary_timeframe: str | None = None
    timeframe_policy_version: str | None = None
    source_cursor_fingerprint: str | None = None

    @field_validator("as_of")
    @classmethod
    def normalize_as_of(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)


class FrontendDecisionRecordProjection(FrozenModel):
    record_id: str
    record_fingerprint: str
    source_backtest_run_id: str
    analytics_run_id: str
    opportunity_id: str
    opportunity_fingerprint: str
    system_id: str
    symbol: str
    decision_timeframe: str
    observed_at: datetime
    scanner: FrontendScannerEvaluationProjection
    decision_context: FrontendDecisionContextProjection
    decision: JsonValue
    analytics: FrontendAnalyticsRefProjection

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _utc(value)


class FrontendDecisionIntelligenceDetailProjection(FrozenModel):
    schema_version: str = FRONTEND_DECISION_DETAIL_SCHEMA_VERSION
    campaign_id: str
    role: PeriodRole
    opportunity_id: str
    decision_intelligence_available: bool
    unavailable_reason: str | None = None
    opportunity_link: FrontendOpportunityAnalyticsLinkProjection | None = None
    record: FrontendDecisionRecordProjection | None = None
    funnel_stages: tuple[FrontendFunnelStageProjection, ...] = ()

    @model_validator(mode="after")
    def validate_availability(self) -> FrontendDecisionIntelligenceDetailProjection:
        if self.decision_intelligence_available:
            if self.record is None:
                raise ValueError("available Decision Intelligence detail requires record")
            if self.record.opportunity_id != self.opportunity_id:
                raise ValueError("Decision Intelligence opportunity mismatch")
        elif self.record is not None or self.funnel_stages:
            raise ValueError("unavailable Decision Intelligence cannot carry decision artifacts")
        if any(item.opportunity_id != self.opportunity_id for item in self.funnel_stages):
            raise ValueError("funnel stage opportunity mismatch")
        ordered = tuple(
            sorted(
                self.funnel_stages,
                key=lambda item: (
                    item.stage_order,
                    item.stage_instance_order if item.stage_instance_order is not None else -1,
                    item.record_id,
                ),
            )
        )
        if ordered != self.funnel_stages:
            raise ValueError("detail funnel stages must be deterministically sorted")
        return self


class FrontendDecisionIntelligenceBundle(FrozenModel):
    schema_version: str = FRONTEND_DECISION_INTELLIGENCE_BUNDLE_SCHEMA_VERSION
    campaign_id: str
    role: PeriodRole
    analytics: FrontendAnalyticsProjection
    scanner: FrontendScannerAnalyticsProjection
    opportunity_links: tuple[FrontendOpportunityAnalyticsLinkProjection, ...] = ()
    decisions: tuple[FrontendDecisionRecordProjection, ...] = ()
    funnel_stages: tuple[FrontendFunnelStageProjection, ...] = ()

    @model_validator(mode="after")
    def validate_bundle(self) -> FrontendDecisionIntelligenceBundle:
        if self.analytics.campaign_id != self.campaign_id or self.analytics.role != self.role:
            raise ValueError("Analytics projection identity mismatch")
        if self.scanner.campaign_id != self.campaign_id or self.scanner.role != self.role:
            raise ValueError("Scanner projection identity mismatch")
        expected_links = tuple(
            sorted(
                self.opportunity_links,
                key=lambda item: (item.observed_at, item.opportunity_id, item.link_id),
            )
        )
        if expected_links != self.opportunity_links:
            raise ValueError("opportunity Analytics links must be deterministically sorted")
        decision_ids = tuple(item.opportunity_id for item in self.decisions)
        if len(set(decision_ids)) != len(decision_ids):
            raise ValueError("Decision Intelligence bundle cannot duplicate opportunity ids")
        expected_decisions = tuple(sorted(self.decisions, key=lambda item: (item.observed_at, item.opportunity_id)))
        if expected_decisions != self.decisions:
            raise ValueError("Decision Intelligence records must be deterministically sorted")
        expected_stages = tuple(
            sorted(
                self.funnel_stages,
                key=lambda item: (
                    item.market_as_of,
                    item.opportunity_id,
                    item.stage_order,
                    item.stage_instance_order if item.stage_instance_order is not None else -1,
                    item.record_id,
                ),
            )
        )
        if expected_stages != self.funnel_stages:
            raise ValueError("funnel stages must be deterministically sorted")
        return self


class ProjectionArtifactStore(Protocol):
    def get(self, campaign_id: str) -> object | None: ...

    def persisted_export(self, campaign_id: str, name: str) -> str | None: ...


class WritableProjectionArtifactStore(ProjectionArtifactStore, Protocol):
    def persist_export(self, campaign_id: str, name: str, payload: str) -> None: ...


class CampaignNotFoundError(LookupError):
    pass


class OpportunityNotFoundError(LookupError):
    pass


def projection_export_name(role: PeriodRole) -> str:
    return f"frontend-decision-intelligence-{role.lower()}.json"


class FrontendDecisionIntelligenceProjectionService:
    """Serve precomputed 24A/24B artifacts without invoking any compute pipeline."""

    def __init__(self, store: ProjectionArtifactStore) -> None:
        self._store = store

    def _campaign_exists(self, campaign_id: str) -> bool:
        return self._store.get(campaign_id) is not None

    def load_bundle(
        self,
        campaign_id: str,
        role: PeriodRole,
    ) -> FrontendDecisionIntelligenceBundle | None:
        if not self._campaign_exists(campaign_id):
            raise CampaignNotFoundError(f"campaign not found: {campaign_id}")
        payload = self._store.persisted_export(campaign_id, projection_export_name(role))
        if payload is None:
            return None
        try:
            bundle = FrontendDecisionIntelligenceBundle.model_validate_json(payload)
        except ValueError as exc:
            raise ValueError(f"invalid persisted Decision Intelligence projection for {campaign_id}/{role}") from exc
        if bundle.campaign_id != campaign_id or bundle.role != role:
            raise ValueError("persisted Decision Intelligence projection identity mismatch")
        return bundle

    def analytics(self, campaign_id: str, role: PeriodRole) -> FrontendAnalyticsProjection:
        bundle = self.load_bundle(campaign_id, role)
        if bundle is not None:
            return bundle.analytics
        return FrontendAnalyticsProjection(
            campaign_id=campaign_id,
            role=role,
            analytics_available=False,
            unavailable_reason="PRECOMPUTED_ANALYTICS_UNAVAILABLE",
        )

    def scanner(
        self,
        campaign_id: str,
        role: PeriodRole,
    ) -> FrontendScannerAnalyticsProjection:
        bundle = self.load_bundle(campaign_id, role)
        if bundle is not None:
            return bundle.scanner
        return FrontendScannerAnalyticsProjection(
            campaign_id=campaign_id,
            role=role,
            analytics_available=False,
            unavailable_reason="PRECOMPUTED_ANALYTICS_UNAVAILABLE",
        )

    def decision_detail(
        self,
        campaign_id: str,
        role: PeriodRole,
        opportunity_id: str,
    ) -> FrontendDecisionIntelligenceDetailProjection:
        bundle = self.load_bundle(campaign_id, role)
        if bundle is None:
            return FrontendDecisionIntelligenceDetailProjection(
                campaign_id=campaign_id,
                role=role,
                opportunity_id=opportunity_id,
                decision_intelligence_available=False,
                unavailable_reason="PRECOMPUTED_DECISION_INTELLIGENCE_UNAVAILABLE",
            )
        links = {item.opportunity_id: item for item in bundle.opportunity_links}
        decisions = {item.opportunity_id: item for item in bundle.decisions}
        known_ids = set(links) | set(decisions)
        if opportunity_id not in known_ids:
            raise OpportunityNotFoundError(f"opportunity not found: {opportunity_id}")
        record = decisions.get(opportunity_id)
        if record is None:
            return FrontendDecisionIntelligenceDetailProjection(
                campaign_id=campaign_id,
                role=role,
                opportunity_id=opportunity_id,
                decision_intelligence_available=False,
                unavailable_reason="DECISION_INTELLIGENCE_UNAVAILABLE",
                opportunity_link=links.get(opportunity_id),
            )
        stages = tuple(item for item in bundle.funnel_stages if item.opportunity_id == opportunity_id)
        return FrontendDecisionIntelligenceDetailProjection(
            campaign_id=campaign_id,
            role=role,
            opportunity_id=opportunity_id,
            decision_intelligence_available=True,
            opportunity_link=links.get(opportunity_id),
            record=record,
            funnel_stages=stages,
        )


def _analytics_ref_from_decision(value: Any) -> FrontendAnalyticsRefProjection:
    return FrontendAnalyticsRefProjection(
        status=str(value.status),
        analytics_run_id=str(value.analytics_run_id),
        analytics_link_id=value.link_id,
        analytics_link_fingerprint=value.link_fingerprint,
        analytics_link_policy_version=value.link_policy_version,
        analytics_snapshot_id=value.analytics_snapshot_id,
        analytics_snapshot_fingerprint=value.analytics_snapshot_fingerprint,
        analytics_as_of=value.analytics_as_of,
        source_cursor_fingerprint=value.source_cursor_fingerprint,
        analytics_snapshot_source_cursor_fingerprint=(value.analytics_snapshot_source_cursor_fingerprint),
        diagnostics=tuple(value.diagnostics),
    )


def _scanner_record_from_attribution(value: Any) -> FrontendScannerEvaluationProjection:
    scanner = value.scanner
    analytics_snapshot = value.analytics.analytics_snapshot
    return FrontendScannerEvaluationProjection(
        record_id=str(value.record_id),
        scanner_evaluation_id=str(value.scanner_evaluation_id),
        observed_at=scanner.observed_at,
        symbol=str(scanner.symbol),
        decision_timeframe=str(scanner.decision_timeframe),
        classification=str(scanner.classification),
        score=int(scanner.score),
        priority_score=int(scanner.score),
        candidate_threshold=int(scanner.candidate_threshold),
        score_margin=int(scanner.score_margin),
        triggers=tuple(scanner.triggers),
        market_regime=scanner.market_regime,
        candidate_opportunity_id=scanner.candidate_opportunity_id,
        analytics=FrontendAnalyticsRefProjection(
            status=str(value.analytics.status),
            analytics_run_id=str(value.analytics_run_id),
            opportunity_analytics_link_id=value.analytics.opportunity_analytics_link_id,
            decision_intelligence_record_id=value.analytics.decision_intelligence_record_id,
            analytics_snapshot_id=(None if analytics_snapshot is None else analytics_snapshot.analytics_snapshot_id),
            analytics_snapshot_fingerprint=(None if analytics_snapshot is None else analytics_snapshot.analytics_snapshot_fingerprint),
            analytics_as_of=None if analytics_snapshot is None else analytics_snapshot.as_of,
            source_cursor_fingerprint=value.observation.source_cursor_fingerprint,
            analytics_snapshot_source_cursor_fingerprint=(None if analytics_snapshot is None else analytics_snapshot.source_cursor_fingerprint),
            diagnostics=tuple(value.analytics.diagnostics),
        ),
    )


def _opportunity_link(value: Any) -> FrontendOpportunityAnalyticsLinkProjection:
    snapshot = value.analytics_snapshot
    observation = value.opportunity.observation
    return FrontendOpportunityAnalyticsLinkProjection(
        link_id=str(value.link_id),
        link_fingerprint=str(value.link_fingerprint),
        status=str(value.status),
        opportunity_id=str(value.opportunity.opportunity_id),
        opportunity_fingerprint=str(value.opportunity.opportunity_fingerprint),
        observed_at=observation.observed_at,
        decision_timeframe=str(observation.decision_timeframe),
        analytics_snapshot_id=None if snapshot is None else snapshot.analytics_snapshot_id,
        analytics_snapshot_fingerprint=(None if snapshot is None else snapshot.analytics_snapshot_fingerprint),
        analytics_as_of=None if snapshot is None else snapshot.as_of,
        diagnostics=tuple(value.diagnostics),
    )


def _decision_record(
    value: Any,
    scanner_by_evaluation: dict[str, FrontendScannerEvaluationProjection],
) -> FrontendDecisionRecordProjection:
    scanner = scanner_by_evaluation.get(str(value.scanner.snapshot_id))
    if scanner is None:
        raise ValueError("Decision Intelligence record is missing Scanner attribution")
    context = value.decision_context
    return FrontendDecisionRecordProjection(
        record_id=str(value.record_id),
        record_fingerprint=str(value.record_fingerprint),
        source_backtest_run_id=str(value.source_backtest_run_id),
        analytics_run_id=str(value.analytics_run_id),
        opportunity_id=str(value.opportunity_id),
        opportunity_fingerprint=str(value.opportunity_fingerprint),
        system_id=str(value.system_id),
        symbol=str(value.symbol),
        decision_timeframe=str(value.decision_timeframe),
        observed_at=value.observed_at,
        scanner=scanner,
        decision_context=FrontendDecisionContextProjection(
            present=bool(context.present),
            context_id=context.context_id,
            context_fingerprint=context.context_fingerprint,
            schema_version=context.schema_version,
            context_version=context.context_version,
            system_id=context.system_id,
            symbol=context.symbol,
            as_of=context.as_of,
            primary_timeframe=context.primary_timeframe,
            timeframe_policy_version=context.timeframe_policy_version,
            source_cursor_fingerprint=context.source_cursor_fingerprint,
        ),
        decision=_json_value(value.decision),
        analytics=_analytics_ref_from_decision(value.analytics),
    )


def _funnel_stage(value: Any) -> FrontendFunnelStageProjection:
    return FrontendFunnelStageProjection(
        record_id=str(value.record_id),
        record_fingerprint=str(value.record_fingerprint),
        decision_intelligence_record_id=str(value.decision_intelligence_record_id),
        opportunity_id=str(value.opportunity_id),
        stage=str(value.stage),
        stage_order=int(value.stage_order),
        stage_instance_id=value.stage_instance_id,
        stage_instance_order=value.stage_instance_order,
        agent_id=value.agent_id,
        agent_request_id=value.agent_request_id,
        agent_prompt_version=value.agent_prompt_version,
        agent_route_id=value.agent_route_id,
        agent_model_id=value.agent_model_id,
        reached=bool(value.reached),
        stage_status=value.stage_status,
        stage_result=value.stage_result,
        reason_codes=tuple(value.reason_codes),
        selected_agents=tuple(value.selected_agents),
        confidence=value.confidence,
        severity=value.severity,
        failure_code=value.failure_code,
        failure_stage=value.failure_stage,
        failure_agent_id=value.failure_agent_id,
        market_as_of=value.market_as_of,
        operational_at=value.operational_at,
        source_artifact_ref=value.source_artifact_ref,
        source_artifact_fingerprint=value.source_artifact_fingerprint,
        source_projection_fingerprint=str(value.source_projection_fingerprint),
        analytics=FrontendAnalyticsRefProjection(
            status=str(value.analytics_link_status),
            analytics_run_id=str(value.analytics_run_id),
            analytics_link_id=value.analytics_link_id,
            analytics_link_fingerprint=value.analytics_link_fingerprint,
            analytics_link_policy_version=value.analytics_link_policy_version,
            decision_intelligence_record_id=value.decision_intelligence_record_id,
            analytics_snapshot_id=value.analytics_snapshot_id,
            analytics_snapshot_fingerprint=value.analytics_snapshot_fingerprint,
            analytics_as_of=value.analytics_as_of,
            source_cursor_fingerprint=value.source_cursor_fingerprint,
            analytics_snapshot_source_cursor_fingerprint=(value.analytics_snapshot_source_cursor_fingerprint),
            diagnostics=tuple(value.analytics_diagnostics),
        ),
    )


def build_frontend_decision_intelligence_bundle(
    *,
    campaign_id: str,
    role: PeriodRole,
    analytics_run: Any,
    analytics_manifest: Any,
    analytics_snapshots: tuple[Any, ...],
    scanner_attribution: Any,
    opportunity_links: Any,
    decision_intelligence: Any,
    funnel_stage_attribution: Any,
) -> FrontendDecisionIntelligenceBundle:
    """Purely project already-computed 24A/24B artifacts for durable frontend storage."""

    analytics_run_id = str(analytics_run.analytics_run_id)
    source_backtest_run_id = str(analytics_run.source_backtest_run_id)
    if str(analytics_manifest.analytics_run_id) != analytics_run_id:
        raise ValueError("Analytics manifest does not belong to AnalyticsLabRun")
    if str(analytics_manifest.source_backtest_run_id) != source_backtest_run_id:
        raise ValueError("Analytics manifest source BacktestRun mismatch")
    if str(analytics_manifest.period_role) != role:
        raise ValueError("Analytics manifest period role does not match frontend role")
    source_sets = (
        scanner_attribution,
        opportunity_links,
        decision_intelligence,
        funnel_stage_attribution,
    )
    for source_set in source_sets:
        if str(source_set.analytics_run_id) != analytics_run_id:
            raise ValueError("24B artifact AnalyticsRun mismatch")
        if str(source_set.source_backtest_run_id) != source_backtest_run_id:
            raise ValueError("24B artifact source BacktestRun mismatch")

    snapshots = tuple(
        FrontendAnalyticsSnapshotProjection(
            snapshot_id=str(item.snapshot_id),
            analytics_run_id=str(item.analytics_run_id),
            as_of=item.as_of,
            symbol=str(item.symbol),
            decision_timeframe=str(item.decision_timeframe),
            snapshot_fingerprint=stable_digest(item.identity_payload()),
            source_cursor_fingerprint=str(item.source_cursor_fingerprint),
            component_names=tuple(sorted(str(key) for key in item.components)),
        )
        for item in sorted(analytics_snapshots, key=lambda item: (item.as_of, item.snapshot_id))
    )
    if int(analytics_manifest.snapshot_count) != len(snapshots):
        raise ValueError("Analytics manifest snapshot_count does not match snapshots")
    if any(item.analytics_run_id != analytics_run_id for item in snapshots):
        raise ValueError("Analytics snapshot belongs to another AnalyticsRun")

    scanner_records = tuple(_scanner_record_from_attribution(item) for item in scanner_attribution.records)
    scanner_by_evaluation = {item.scanner_evaluation_id: item for item in scanner_records}
    link_records = tuple(_opportunity_link(item) for item in opportunity_links.links)
    decision_records = tuple(_decision_record(item, scanner_by_evaluation) for item in decision_intelligence.records)
    stage_records = tuple(_funnel_stage(item) for item in funnel_stage_attribution.records)

    analytics_projection = FrontendAnalyticsProjection(
        campaign_id=campaign_id,
        role=role,
        analytics_available=True,
        run=FrontendAnalyticsRunProjection(
            analytics_run_id=analytics_run_id,
            identity_sha256=str(analytics_run.identity_sha256),
            source_backtest_run_id=source_backtest_run_id,
            dataset_id=str(analytics_run.dataset_id),
            dataset_version=str(analytics_run.dataset_version),
            dataset_content_sha256=str(analytics_run.dataset_content_sha256),
            dataset_source=str(analytics_run.dataset_source),
            system_id=str(analytics_run.system_id),
            symbol=str(analytics_run.symbol),
            source_timeframe=str(analytics_run.source_timeframe),
            decision_timeframe=str(analytics_run.decision_timeframe),
            period_start=analytics_run.period_start,
            period_end=analytics_run.period_end,
            period_role=str(analytics_run.period_role),
            mtf_policy_version=str(analytics_run.mtf_policy_version),
            analytics_bundle_version=str(analytics_run.component_versions.analytics_bundle_version),
            component_versions={str(key): str(item) for key, item in analytics_run.component_versions.canonical_payload().items()},
            analytics_sha256=str(analytics_manifest.analytics_sha256),
            snapshot_count=int(analytics_manifest.snapshot_count),
        ),
        snapshots=snapshots,
        opportunity_count=int(opportunity_links.total_opportunities),
        scanner_evaluation_count=int(scanner_attribution.total_scanner_evaluations),
        decision_record_count=int(decision_intelligence.record_count),
        funnel_stage_count=int(funnel_stage_attribution.stage_record_count),
    )
    scanner_projection = FrontendScannerAnalyticsProjection(
        campaign_id=campaign_id,
        role=role,
        analytics_available=True,
        source_backtest_run_id=str(scanner_attribution.source_backtest_run_id),
        analytics_run_id=str(scanner_attribution.analytics_run_id),
        total_scanner_evaluations=int(scanner_attribution.total_scanner_evaluations),
        matched_analytics=int(scanner_attribution.matched_analytics),
        unmatched_analytics=int(scanner_attribution.unmatched_analytics),
        no_trigger_count=int(scanner_attribution.no_trigger_count),
        below_threshold_count=int(scanner_attribution.below_threshold_count),
        candidate_count=int(scanner_attribution.candidate_count),
        records=scanner_records,
    )
    return FrontendDecisionIntelligenceBundle(
        campaign_id=campaign_id,
        role=role,
        analytics=analytics_projection,
        scanner=scanner_projection,
        opportunity_links=link_records,
        decisions=decision_records,
        funnel_stages=stage_records,
    )


def bundle_to_json(bundle: FrontendDecisionIntelligenceBundle) -> str:
    """Serialize a stable frontend bundle without lossy Decimal conversion."""

    return json.dumps(
        bundle.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def persist_frontend_decision_intelligence_bundle(
    store: WritableProjectionArtifactStore,
    bundle: FrontendDecisionIntelligenceBundle,
) -> None:
    """Persist one already-projected role bundle through the existing V2 sidecar."""

    store.persist_export(
        bundle.campaign_id,
        projection_export_name(bundle.role),
        bundle_to_json(bundle),
    )


__all__ = [
    "CampaignNotFoundError",
    "FRONTEND_DECISION_INTELLIGENCE_BUNDLE_SCHEMA_VERSION",
    "FrontendAnalyticsProjection",
    "FrontendDecisionIntelligenceBundle",
    "FrontendDecisionIntelligenceDetailProjection",
    "FrontendDecisionIntelligenceProjectionService",
    "FrontendScannerAnalyticsProjection",
    "OpportunityNotFoundError",
    "build_frontend_decision_intelligence_bundle",
    "bundle_to_json",
    "persist_frontend_decision_intelligence_bundle",
    "projection_export_name",
]
