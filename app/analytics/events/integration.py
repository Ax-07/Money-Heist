from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.analytics.indicators import (
    ANALYTICS_INDICATOR_REGISTRY_IDENTITY,
    AnalyticsIndicatorEngine,
    AnalyticsIndicatorSnapshot,
    compute_indicator_component,
)
from app.analytics.models import (
    AnalyticsAsOfInput,
    AnalyticsComponentVersions,
    AnalyticsLabRun,
    AnalyticsSnapshot,
)

from .engine import TechnicalEventEngine
from .models import TechnicalEventObservation
from .registry import ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY

ANALYTICS_24A3_BUNDLE_VERSION = "analytics-lab-24a3-technical-events-v1"


def technical_event_component_versions(
    *,
    analytics_bundle_version: str = ANALYTICS_24A3_BUNDLE_VERSION,
) -> AnalyticsComponentVersions:
    """Return the 24A.3 Analytics identity with indicator and event registries installed."""

    return AnalyticsComponentVersions(
        analytics_bundle_version=analytics_bundle_version,
        indicator_registry_version=ANALYTICS_INDICATOR_REGISTRY_IDENTITY,
        event_registry_version=ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY,
        structure_version="not-installed",
        zigzag_version="not-installed",
        pattern_registry_version="not-installed",
        context_engine_version="not-installed",
        sequence_engine_version="not-installed",
    )


def compute_technical_event_component(
    *,
    analytics_run: AnalyticsLabRun,
    previous_indicator_snapshot: AnalyticsIndicatorSnapshot | None,
    current_indicator_snapshot: AnalyticsIndicatorSnapshot,
    engine: TechnicalEventEngine | None = None,
) -> tuple[TechnicalEventObservation, ...]:
    """Detect Technical Events from already-computed Analytics Indicator snapshots."""

    versions = analytics_run.component_versions
    if versions.indicator_registry_version != ANALYTICS_INDICATOR_REGISTRY_IDENTITY:
        raise ValueError(
            "analytics run does not identify the installed Analytics indicator registry"
        )
    if versions.event_registry_version != ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY:
        raise ValueError("analytics run does not identify the installed Technical Event registry")
    if current_indicator_snapshot.symbol != analytics_run.symbol:
        raise ValueError("current indicator snapshot symbol differs from analytics run")
    if current_indicator_snapshot.timeframe != analytics_run.decision_timeframe:
        raise ValueError("current indicator snapshot timeframe differs from analytics run")

    detector = engine or TechnicalEventEngine()
    events = detector.detect(
        previous_indicator_snapshot,
        current_indicator_snapshot,
        analytics_run_id=analytics_run.analytics_run_id,
    )
    if any(event.available_at > current_indicator_snapshot.as_of for event in events):
        raise ValueError("technical event availability cannot exceed current indicator as_of")
    return events


def build_analytics_snapshot_with_indicators_and_events(
    *,
    analytics_run: AnalyticsLabRun,
    as_of_input: AnalyticsAsOfInput,
    candles: Sequence[Any],
    previous_indicator_snapshot: AnalyticsIndicatorSnapshot | None,
    indicator_engine: AnalyticsIndicatorEngine | None = None,
    event_engine: TechnicalEventEngine | None = None,
) -> AnalyticsSnapshot:
    """Build the 24A.3 AnalyticsSnapshot without modifying any business-path object."""

    current_indicators = compute_indicator_component(
        analytics_run=analytics_run,
        as_of_input=as_of_input,
        candles=candles,
        engine=indicator_engine,
    )
    events = compute_technical_event_component(
        analytics_run=analytics_run,
        previous_indicator_snapshot=previous_indicator_snapshot,
        current_indicator_snapshot=current_indicators,
        engine=event_engine,
    )
    if any(event.available_at > as_of_input.as_of for event in events):
        raise ValueError("lookahead rejected: technical event available_at exceeds snapshot as_of")
    return AnalyticsSnapshot.create(
        analytics_run=analytics_run,
        as_of_input=as_of_input,
        components={
            "indicators": current_indicators,
            "technical_events": events,
        },
    )


__all__ = [
    "ANALYTICS_24A3_BUNDLE_VERSION",
    "build_analytics_snapshot_with_indicators_and_events",
    "compute_technical_event_component",
    "technical_event_component_versions",
]
