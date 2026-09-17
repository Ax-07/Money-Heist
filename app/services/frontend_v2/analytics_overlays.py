from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator, model_validator

from app.services.frontend_v2.decision_intelligence import (
    FrontendDecisionIntelligenceProjectionService,
    FrontendFunnelStageProjection,
    FrontendScannerEvaluationProjection,
)

FRONTEND_ANALYTICS_GEOMETRY_SCHEMA_VERSION = "money-heist.frontend-analytics-geometry.v1"
FRONTEND_ANALYTICS_OVERLAYS_SCHEMA_VERSION = "money-heist.frontend-analytics-overlays.v1"
PeriodRole = Literal["DESIGN", "VALIDATION", "OOS"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _decimal(value: object | None) -> str | None:
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
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="python"))
    if hasattr(value, "canonical_payload"):
        return _json_value(value.canonical_payload())
    raise TypeError(f"unsupported overlay projection value: {type(value).__name__}")


class FrontendTechnicalEventOverlay(FrozenModel):
    event_id: str
    event_type: str
    family: str
    direction: str
    symbol: str
    timeframe: str
    event_at: datetime
    available_at: datetime
    event_fingerprint: str
    evidence: JsonValue

    @field_validator("event_at", "available_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime) -> datetime:
        return _utc(value)


class FrontendSwingPointOverlay(FrozenModel):
    kind: str
    price: str
    close_time: datetime

    @field_validator("close_time")
    @classmethod
    def normalize_close_time(cls, value: datetime) -> datetime:
        return _utc(value)


class FrontendStructureTimeframeOverlay(FrozenModel):
    timeframe: str
    observed_at: datetime
    close: str
    prior_range_high: str | None = None
    prior_range_low: str | None = None
    range_location: str
    breakout_state: str
    swing_structure: str
    previous_swing_high: FrontendSwingPointOverlay | None = None
    latest_swing_high: FrontendSwingPointOverlay | None = None
    previous_swing_low: FrontendSwingPointOverlay | None = None
    latest_swing_low: FrontendSwingPointOverlay | None = None
    missing_fields: tuple[str, ...] = ()

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _utc(value)


class FrontendStructureOverlay(FrozenModel):
    structure_id: str
    symbol: str
    as_of: datetime
    source_cursor_fingerprint: str
    timeframes: tuple[FrontendStructureTimeframeOverlay, ...]

    @field_validator("as_of")
    @classmethod
    def normalize_as_of(cls, value: datetime) -> datetime:
        return _utc(value)


class FrontendZigZagPivotOverlay(FrozenModel):
    pivot_id: str
    kind: str
    symbol: str
    timeframe: str
    pivot_at: datetime
    confirmed_at: datetime
    price: str
    atr_at_pivot: str
    reversal_multiple: str
    reversal_threshold: str
    amplitude_pct: str | None = None
    amplitude_atr: str | None = None
    bars_from_previous: int | None = None
    pivot_fingerprint: str

    @field_validator("pivot_at", "confirmed_at")
    @classmethod
    def normalize_pivot_timestamps(cls, value: datetime) -> datetime:
        return _utc(value)


class FrontendPatternPointOverlay(FrozenModel):
    role: str
    pivot_id: str
    kind: str
    price: str
    pivot_at: datetime
    confirmed_at: datetime

    @field_validator("pivot_at", "confirmed_at")
    @classmethod
    def normalize_point_timestamps(cls, value: datetime) -> datetime:
        return _utc(value)


class FrontendPatternSegmentOverlay(FrozenModel):
    role: str
    start_at: datetime
    start_price: str
    end_at: datetime
    end_price: str
    slope_per_bar: str

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_segment_timestamps(cls, value: datetime) -> datetime:
        return _utc(value)


class FrontendPatternTransitionOverlay(FrozenModel):
    status: str
    occurred_at: datetime
    available_at: datetime
    reason: str
    evidence: JsonValue
    fingerprint: str

    @field_validator("occurred_at", "available_at")
    @classmethod
    def normalize_transition_timestamps(cls, value: datetime) -> datetime:
        return _utc(value)


class FrontendPatternOverlay(FrozenModel):
    pattern_id: str
    pattern_type: str
    family: str
    direction: str
    symbol: str
    timeframe: str
    start_at: datetime
    detected_at: datetime
    end_at: datetime
    confirmed_at: datetime | None = None
    failed_at: datetime | None = None
    invalidated_at: datetime | None = None
    current_status: str
    pivot_source: str
    points: tuple[FrontendPatternPointOverlay, ...]
    segments: tuple[FrontendPatternSegmentOverlay, ...]
    breakout_level: str | None = None
    metrics: JsonValue
    diagnostic_flags: tuple[str, ...]
    transitions: tuple[FrontendPatternTransitionOverlay, ...]
    pattern_fingerprint: str

    @field_validator(
        "start_at",
        "detected_at",
        "end_at",
        "confirmed_at",
        "failed_at",
        "invalidated_at",
    )
    @classmethod
    def normalize_pattern_timestamps(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)


class FrontendAnalyticsGeometryProjection(FrozenModel):
    schema_version: str = FRONTEND_ANALYTICS_GEOMETRY_SCHEMA_VERSION
    campaign_id: str
    role: PeriodRole
    analytics_run_id: str
    technical_events: tuple[FrontendTechnicalEventOverlay, ...] = ()
    structure: tuple[FrontendStructureOverlay, ...] = ()
    zigzag_pivots: tuple[FrontendZigZagPivotOverlay, ...] = ()
    patterns: tuple[FrontendPatternOverlay, ...] = ()

    @model_validator(mode="after")
    def validate_ordering(self) -> FrontendAnalyticsGeometryProjection:
        if self.technical_events != tuple(
            sorted(self.technical_events, key=lambda item: (item.event_at, item.event_id))
        ):
            raise ValueError("technical events must be deterministically sorted")
        if self.structure != tuple(
            sorted(self.structure, key=lambda item: (item.as_of, item.structure_id))
        ):
            raise ValueError("structure observations must be deterministically sorted")
        if self.zigzag_pivots != tuple(
            sorted(self.zigzag_pivots, key=lambda item: (item.pivot_at, item.pivot_id))
        ):
            raise ValueError("ZigZag pivots must be deterministically sorted")
        if self.patterns != tuple(
            sorted(self.patterns, key=lambda item: (item.detected_at, item.pattern_id))
        ):
            raise ValueError("patterns must be deterministically sorted")
        return self


class FrontendAnalyticsOverlaysProjection(FrozenModel):
    schema_version: str = FRONTEND_ANALYTICS_OVERLAYS_SCHEMA_VERSION
    campaign_id: str
    role: PeriodRole
    analytics_available: bool
    unavailable_reason: str | None = None
    source_backtest_run_id: str | None = None
    analytics_run_id: str | None = None
    scanner: tuple[FrontendScannerEvaluationProjection, ...] = ()
    funnel_stages: tuple[FrontendFunnelStageProjection, ...] = ()
    technical_events: tuple[FrontendTechnicalEventOverlay, ...] = ()
    structure: tuple[FrontendStructureOverlay, ...] = ()
    zigzag_pivots: tuple[FrontendZigZagPivotOverlay, ...] = ()
    patterns: tuple[FrontendPatternOverlay, ...] = ()

    @model_validator(mode="after")
    def validate_availability(self) -> FrontendAnalyticsOverlaysProjection:
        if not self.analytics_available:
            if any(
                (
                    self.scanner,
                    self.funnel_stages,
                    self.technical_events,
                    self.structure,
                    self.zigzag_pivots,
                    self.patterns,
                )
            ):
                raise ValueError("unavailable overlays projection cannot carry overlay data")
            return self
        if self.analytics_run_id is None or self.source_backtest_run_id is None:
            raise ValueError("available overlays require run identities")
        return self


class OverlayArtifactStore(Protocol):
    def persisted_export(self, campaign_id: str, name: str) -> str | None: ...

    def persist_export(self, campaign_id: str, name: str, payload: str) -> None: ...


def geometry_export_name(role: PeriodRole) -> str:
    return f"frontend-analytics-overlays-{role.lower()}.json"


def _swing(value: Any | None) -> FrontendSwingPointOverlay | None:
    if value is None:
        return None
    return FrontendSwingPointOverlay(
        kind=str(value.kind),
        price=str(value.price),
        close_time=value.close_time,
    )


def _structure(value: Any) -> FrontendStructureOverlay:
    context = value.context
    timeframes = tuple(
        FrontendStructureTimeframeOverlay(
            timeframe=str(item.timeframe),
            observed_at=item.observed_at,
            close=str(item.close),
            prior_range_high=_decimal(item.prior_range_high),
            prior_range_low=_decimal(item.prior_range_low),
            range_location=str(item.range_location),
            breakout_state=str(item.breakout_state),
            swing_structure=str(item.swing_structure),
            previous_swing_high=_swing(item.previous_swing_high),
            latest_swing_high=_swing(item.latest_swing_high),
            previous_swing_low=_swing(item.previous_swing_low),
            latest_swing_low=_swing(item.latest_swing_low),
            missing_fields=tuple(item.missing_fields),
        )
        for _, item in sorted(context.timeframes.items())
    )
    return FrontendStructureOverlay(
        structure_id=str(value.fingerprint),
        symbol=str(value.symbol),
        as_of=value.as_of,
        source_cursor_fingerprint=str(value.source_cursor_fingerprint),
        timeframes=timeframes,
    )


def _event(value: Any) -> FrontendTechnicalEventOverlay:
    return FrontendTechnicalEventOverlay(
        event_id=str(value.event_id),
        event_type=str(value.event_type),
        family=str(value.family),
        direction=str(value.direction),
        symbol=str(value.symbol),
        timeframe=str(value.timeframe),
        event_at=value.event_at,
        available_at=value.available_at,
        event_fingerprint=str(value.event_fingerprint),
        evidence=_json_value(value.evidence.canonical_payload()),
    )


def _pivot(value: Any) -> FrontendZigZagPivotOverlay:
    return FrontendZigZagPivotOverlay(
        pivot_id=str(value.pivot_id),
        kind=str(value.kind),
        symbol=str(value.symbol),
        timeframe=str(value.timeframe),
        pivot_at=value.pivot_at,
        confirmed_at=value.confirmed_at,
        price=str(value.price),
        atr_at_pivot=str(value.atr_at_pivot),
        reversal_multiple=str(value.reversal_multiple),
        reversal_threshold=str(value.reversal_threshold),
        amplitude_pct=_decimal(value.amplitude_pct),
        amplitude_atr=_decimal(value.amplitude_atr),
        bars_from_previous=value.bars_from_previous,
        pivot_fingerprint=str(value.pivot_fingerprint),
    )


def _pattern(value: Any) -> FrontendPatternOverlay:
    return FrontendPatternOverlay(
        pattern_id=str(value.pattern_id),
        pattern_type=str(value.pattern_type),
        family=str(value.family),
        direction=str(value.direction),
        symbol=str(value.symbol),
        timeframe=str(value.timeframe),
        start_at=value.start_at,
        detected_at=value.detected_at,
        end_at=value.end_at,
        confirmed_at=value.confirmed_at,
        failed_at=value.failed_at,
        invalidated_at=value.invalidated_at,
        current_status=str(value.current_status),
        pivot_source=str(value.pivot_source),
        points=tuple(
            FrontendPatternPointOverlay(
                role=str(item.role),
                pivot_id=str(item.pivot_id),
                kind=str(item.kind),
                price=str(item.price),
                pivot_at=item.pivot_at,
                confirmed_at=item.confirmed_at,
            )
            for item in value.points
        ),
        segments=tuple(
            FrontendPatternSegmentOverlay(
                role=str(item.role),
                start_at=item.start_at,
                start_price=str(item.start_price),
                end_at=item.end_at,
                end_price=str(item.end_price),
                slope_per_bar=str(item.slope_per_bar),
            )
            for item in value.segments
        ),
        breakout_level=_decimal(value.breakout_level),
        metrics=_json_value(dict(value.metrics)),
        diagnostic_flags=tuple(value.diagnostic_flags),
        transitions=tuple(
            FrontendPatternTransitionOverlay(
                status=str(item.status),
                occurred_at=item.occurred_at,
                available_at=item.available_at,
                reason=str(item.reason),
                evidence=_json_value(dict(item.evidence)),
                fingerprint=str(item.fingerprint),
            )
            for item in value.transitions
        ),
        pattern_fingerprint=str(value.pattern_fingerprint),
    )


def build_frontend_analytics_geometry_projection(
    *,
    campaign_id: str,
    role: PeriodRole,
    analytics_run_id: str,
    analytics_snapshots: tuple[Any, ...],
) -> FrontendAnalyticsGeometryProjection:
    """Project canonical 24A objects once; never derive Analytics from OHLCV."""

    events: dict[str, FrontendTechnicalEventOverlay] = {}
    structure: dict[str, FrontendStructureOverlay] = {}
    pivots: dict[str, FrontendZigZagPivotOverlay] = {}
    patterns: dict[str, FrontendPatternOverlay] = {}

    for snapshot in sorted(analytics_snapshots, key=lambda item: (item.as_of, item.snapshot_id)):
        if str(snapshot.analytics_run_id) != analytics_run_id:
            raise ValueError("Analytics snapshot belongs to another AnalyticsRun")
        components = snapshot.components
        for item in components.get("technical_events", ()):
            events[str(item.event_id)] = _event(item)
        structure_item = components.get("market_structure")
        if structure_item is not None:
            projected_structure = _structure(structure_item)
            structure[projected_structure.structure_id] = projected_structure
        for item in components.get("zigzag_pivots", ()):
            pivots[str(item.pivot_id)] = _pivot(item)
        for item in components.get("patterns", ()):
            # Same pattern_id evolves causally. The latest projected occurrence carries the
            # longest transition history; the browser replays that history by available_at.
            patterns[str(item.pattern_id)] = _pattern(item)

    return FrontendAnalyticsGeometryProjection(
        campaign_id=campaign_id,
        role=role,
        analytics_run_id=analytics_run_id,
        technical_events=tuple(
            sorted(events.values(), key=lambda item: (item.event_at, item.event_id))
        ),
        structure=tuple(
            sorted(structure.values(), key=lambda item: (item.as_of, item.structure_id))
        ),
        zigzag_pivots=tuple(
            sorted(pivots.values(), key=lambda item: (item.pivot_at, item.pivot_id))
        ),
        patterns=tuple(
            sorted(patterns.values(), key=lambda item: (item.detected_at, item.pattern_id))
        ),
    )


def persist_frontend_analytics_geometry_projection(
    store: OverlayArtifactStore,
    projection: FrontendAnalyticsGeometryProjection,
) -> None:
    store.persist_export(
        projection.campaign_id,
        geometry_export_name(projection.role),
        json.dumps(
            projection.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
    )


class FrontendAnalyticsOverlayProjectionService:
    """Combine persisted 24C.1 attribution with optional precomputed 24A chart geometry."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._decision_service = FrontendDecisionIntelligenceProjectionService(store)

    def overlays(
        self,
        campaign_id: str,
        role: PeriodRole,
    ) -> FrontendAnalyticsOverlaysProjection:
        bundle = self._decision_service.load_bundle(campaign_id, role)
        if bundle is None:
            return FrontendAnalyticsOverlaysProjection(
                campaign_id=campaign_id,
                role=role,
                analytics_available=False,
                unavailable_reason="PRECOMPUTED_ANALYTICS_UNAVAILABLE",
            )
        if not bundle.analytics.analytics_available or bundle.analytics.run is None:
            return FrontendAnalyticsOverlaysProjection(
                campaign_id=campaign_id,
                role=role,
                analytics_available=False,
                unavailable_reason=(
                    bundle.analytics.unavailable_reason
                    or "PRECOMPUTED_ANALYTICS_UNAVAILABLE"
                ),
            )

        geometry_payload = self._store.persisted_export(campaign_id, geometry_export_name(role))
        geometry: FrontendAnalyticsGeometryProjection | None = None
        if geometry_payload is not None:
            try:
                geometry = FrontendAnalyticsGeometryProjection.model_validate_json(geometry_payload)
            except ValueError as exc:
                raise ValueError(
                    f"invalid persisted Analytics overlay geometry for {campaign_id}/{role}"
                ) from exc
            if geometry.campaign_id != campaign_id or geometry.role != role:
                raise ValueError("persisted Analytics overlay geometry identity mismatch")
            if geometry.analytics_run_id != bundle.analytics.run.analytics_run_id:
                raise ValueError("Analytics overlay geometry run identity mismatch")

        return FrontendAnalyticsOverlaysProjection(
            campaign_id=campaign_id,
            role=role,
            analytics_available=True,
            source_backtest_run_id=bundle.analytics.run.source_backtest_run_id,
            analytics_run_id=bundle.analytics.run.analytics_run_id,
            scanner=bundle.scanner.records,
            funnel_stages=bundle.funnel_stages,
            technical_events=() if geometry is None else geometry.technical_events,
            structure=() if geometry is None else geometry.structure,
            zigzag_pivots=() if geometry is None else geometry.zigzag_pivots,
            patterns=() if geometry is None else geometry.patterns,
        )


__all__ = [
    "FRONTEND_ANALYTICS_GEOMETRY_SCHEMA_VERSION",
    "FRONTEND_ANALYTICS_OVERLAYS_SCHEMA_VERSION",
    "FrontendAnalyticsGeometryProjection",
    "FrontendAnalyticsOverlayProjectionService",
    "FrontendAnalyticsOverlaysProjection",
    "build_frontend_analytics_geometry_projection",
    "geometry_export_name",
    "persist_frontend_analytics_geometry_projection",
]
