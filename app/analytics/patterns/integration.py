from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.analytics.events import ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY
from app.analytics.indicators import (
    ANALYTICS_INDICATOR_REGISTRY_IDENTITY,
    AnalyticsIndicatorSnapshot,
)
from app.analytics.models import (
    AnalyticsAsOfInput,
    AnalyticsComponentVersions,
    AnalyticsLabRun,
    AnalyticsSnapshot,
)
from app.analytics.structure import ANALYTICS_STRUCTURE_IDENTITY
from app.analytics.zigzag import CAUSAL_ZIGZAG_REGISTRY_IDENTITY, CausalZigZagPivot
from app.market.models import Candle

from .engine import patterns_at
from .lifecycle import occurrence_at
from .models import PatternOccurrence
from .pivots import pattern_pivots_from_causal_zigzag
from .registry import ANALYTICS_PATTERN_REGISTRY_IDENTITY

ANALYTICS_24A5_BUNDLE_VERSION = "analytics-lab-24a5-patterns-causal-lifecycle-v1"


def causal_pattern_component_versions(
    *,
    structure_version: str = ANALYTICS_STRUCTURE_IDENTITY,
    analytics_bundle_version: str = ANALYTICS_24A5_BUNDLE_VERSION,
) -> AnalyticsComponentVersions:
    return AnalyticsComponentVersions(
        analytics_bundle_version=analytics_bundle_version,
        indicator_registry_version=ANALYTICS_INDICATOR_REGISTRY_IDENTITY,
        event_registry_version=ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY,
        structure_version=structure_version,
        zigzag_version=CAUSAL_ZIGZAG_REGISTRY_IDENTITY,
        pattern_registry_version=ANALYTICS_PATTERN_REGISTRY_IDENTITY,
        context_engine_version="not-installed",
        sequence_engine_version="not-installed",
    )


def compute_patterns_from_causal_zigzag(
    *,
    analytics_run: AnalyticsLabRun,
    candles: Sequence[Candle],
    zigzag_pivots: Sequence[CausalZigZagPivot],
    as_of_input: AnalyticsAsOfInput,
) -> tuple[PatternOccurrence, ...]:
    versions = analytics_run.component_versions
    if versions.pattern_registry_version != ANALYTICS_PATTERN_REGISTRY_IDENTITY:
        raise ValueError("analytics run does not identify installed pattern registry")
    if versions.zigzag_version != CAUSAL_ZIGZAG_REGISTRY_IDENTITY:
        raise ValueError("analytics run does not identify installed ZigZag registry")
    if as_of_input.as_of > analytics_run.period_end:
        raise ValueError("pattern as_of exceeds analytics run period")

    visible_zigzag = tuple(
        pivot for pivot in zigzag_pivots if pivot.confirmed_at <= as_of_input.as_of
    )
    pivots = pattern_pivots_from_causal_zigzag(visible_zigzag)
    return patterns_at(
        candles=candles,
        pivots=pivots,
        as_of=as_of_input.as_of,
        analytics_run_id=analytics_run.analytics_run_id,
        source_cursor_fingerprint=as_of_input.source_cursor_fingerprint,
    )


def build_analytics_snapshot_with_patterns(
    *,
    analytics_run: AnalyticsLabRun,
    as_of_input: AnalyticsAsOfInput,
    indicators: AnalyticsIndicatorSnapshot,
    technical_events: Sequence[Any],
    market_structure: Any,
    zigzag_pivots: Sequence[CausalZigZagPivot],
    patterns: Sequence[PatternOccurrence],
) -> AnalyticsSnapshot:
    visible_zigzag = tuple(
        pivot for pivot in zigzag_pivots if pivot.confirmed_at <= as_of_input.as_of
    )
    visible_patterns = tuple(
        projected
        for pattern in patterns
        if (projected := occurrence_at(pattern, as_of_input.as_of)) is not None
    )
    return AnalyticsSnapshot.create(
        analytics_run=analytics_run,
        as_of_input=as_of_input,
        components={
            "indicators": indicators,
            "technical_events": tuple(technical_events),
            "market_structure": market_structure,
            "zigzag_pivots": visible_zigzag,
            "patterns": visible_patterns,
        },
    )


__all__ = [
    "ANALYTICS_24A5_BUNDLE_VERSION",
    "build_analytics_snapshot_with_patterns",
    "causal_pattern_component_versions",
    "compute_patterns_from_causal_zigzag",
]
