from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.analytics.models import (
    AnalyticsAsOfInput,
    AnalyticsComponentVersions,
    AnalyticsLabRun,
    AnalyticsSnapshot,
)

from .engine import AnalyticsIndicatorEngine
from .models import AnalyticsIndicatorSnapshot
from .registry import ANALYTICS_INDICATOR_REGISTRY_IDENTITY

ANALYTICS_24A2_BUNDLE_VERSION = "analytics-lab-24a2-rich-indicators-v1"


def indicator_component_versions(
    *,
    analytics_bundle_version: str = ANALYTICS_24A2_BUNDLE_VERSION,
) -> AnalyticsComponentVersions:
    """Return the 24A.2 Analytics identity with the installed registry fingerprint."""

    return AnalyticsComponentVersions(
        analytics_bundle_version=analytics_bundle_version,
        indicator_registry_version=ANALYTICS_INDICATOR_REGISTRY_IDENTITY,
        event_registry_version="not-installed",
        structure_version="not-installed",
        zigzag_version="not-installed",
        pattern_registry_version="not-installed",
        context_engine_version="not-installed",
        sequence_engine_version="not-installed",
    )


def compute_indicator_component(
    *,
    analytics_run: AnalyticsLabRun,
    as_of_input: AnalyticsAsOfInput,
    candles: Sequence[Any],
    engine: AnalyticsIndicatorEngine | None = None,
) -> AnalyticsIndicatorSnapshot:
    """Compute the typed indicator component for one existing 24A.1 as-of input.

    The caller supplies candles already exposed by Money Heist's historical MTF
    machinery. No resampling, ingestion, gap filling or external data access occurs here.
    """

    if (
        analytics_run.component_versions.indicator_registry_version
        != ANALYTICS_INDICATOR_REGISTRY_IDENTITY
    ):
        raise ValueError("analytics run does not identify the installed 24A.2 indicator registry")
    if as_of_input.source_backtest_run_id != analytics_run.source_backtest_run_id:
        raise ValueError("as_of_input and analytics_run source backtest run differ")
    if as_of_input.symbol != analytics_run.symbol:
        raise ValueError("as_of_input and analytics_run symbol differ")
    if as_of_input.decision_timeframe != analytics_run.decision_timeframe:
        raise ValueError("as_of_input and analytics_run decision timeframe differ")

    calculator = engine or AnalyticsIndicatorEngine()
    return calculator.compute(
        candles,
        symbol=as_of_input.symbol,
        timeframe=as_of_input.decision_timeframe,
        as_of=as_of_input.as_of,
        source_cursor_fingerprint=as_of_input.source_cursor_fingerprint,
    )


def build_analytics_snapshot_with_indicators(
    *,
    analytics_run: AnalyticsLabRun,
    as_of_input: AnalyticsAsOfInput,
    candles: Sequence[Any],
    engine: AnalyticsIndicatorEngine | None = None,
) -> AnalyticsSnapshot:
    """Integrate the typed 24A.2 component without changing the 24A.1 snapshot schema."""

    indicators = compute_indicator_component(
        analytics_run=analytics_run,
        as_of_input=as_of_input,
        candles=candles,
        engine=engine,
    )
    return AnalyticsSnapshot.create(
        analytics_run=analytics_run,
        as_of_input=as_of_input,
        components={"indicators": indicators},
    )


__all__ = [
    "ANALYTICS_24A2_BUNDLE_VERSION",
    "build_analytics_snapshot_with_indicators",
    "compute_indicator_component",
    "indicator_component_versions",
]
