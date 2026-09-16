from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
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
from app.market.models import Candle
from app.market.multitimeframe import HistoricalMultiTimeframeCursor

from .engine import CausalZigZagEngine
from .models import CausalZigZagInputBar, CausalZigZagPivot
from .registry import (
    CAUSAL_ZIGZAG_ATR_INDICATOR_ID,
    CAUSAL_ZIGZAG_REGISTRY_IDENTITY,
)

ANALYTICS_24A4_BUNDLE_VERSION = "analytics-lab-24a4-causal-structure-zigzag-v1"


def _as_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def causal_structure_component_versions(
    *,
    structure_version: str = ANALYTICS_STRUCTURE_IDENTITY,
    analytics_bundle_version: str = ANALYTICS_24A4_BUNDLE_VERSION,
) -> AnalyticsComponentVersions:
    return AnalyticsComponentVersions(
        analytics_bundle_version=analytics_bundle_version,
        indicator_registry_version=ANALYTICS_INDICATOR_REGISTRY_IDENTITY,
        event_registry_version=ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY,
        structure_version=structure_version,
        zigzag_version=CAUSAL_ZIGZAG_REGISTRY_IDENTITY,
        pattern_registry_version="not-installed",
        context_engine_version="not-installed",
        sequence_engine_version="not-installed",
    )


def canonical_candles_from_mtf_cursor(
    *,
    mtf_cursor: HistoricalMultiTimeframeCursor,
    timeframe: str,
    as_of: datetime,
) -> tuple[Candle, ...]:
    """Return only canonical closed candles already emitted by Money Heist MTF."""
    cutoff = _as_utc(as_of, field="as_of")
    state = mtf_cursor.state()
    if state.as_of != cutoff:
        raise ValueError("MTF cursor as_of must equal ZigZag as_of")
    normalized_timeframe = timeframe.strip().lower()
    if normalized_timeframe not in mtf_cursor.target_timeframes:
        raise ValueError("ZigZag timeframe is not configured on MTF cursor")
    candles = mtf_cursor.series(normalized_timeframe)
    if any(not candle.is_closed for candle in candles):
        raise ValueError("MTF cursor exposed a non-closed candle")
    if any(candle.close_time > cutoff for candle in candles):
        raise ValueError("lookahead rejected: MTF candle closes after ZigZag as_of")
    return candles


def build_zigzag_input_bars(
    *,
    candles: Sequence[Candle],
    indicator_snapshots: Sequence[AnalyticsIndicatorSnapshot],
) -> tuple[CausalZigZagInputBar, ...]:
    if len(candles) != len(indicator_snapshots):
        raise ValueError("candles and indicator_snapshots must have equal length")

    bars: list[CausalZigZagInputBar] = []
    for candle, snapshot in zip(candles, indicator_snapshots, strict=True):
        if candle.symbol != snapshot.symbol or candle.timeframe != snapshot.timeframe:
            raise ValueError("candle and indicator snapshot identity differ")
        if candle.close_time != snapshot.as_of:
            raise ValueError(
                "indicator snapshot as_of must equal its closed candle close_time"
            )
        atr_value = snapshot.value(CAUSAL_ZIGZAG_ATR_INDICATOR_ID)
        bars.append(
            CausalZigZagInputBar(
                candle=candle,
                atr_at_candle=atr_value.value if atr_value.available else None,
                source_cursor_fingerprint=snapshot.source_cursor_fingerprint,
                source_indicator_snapshot_fingerprint=snapshot.snapshot_fingerprint,
            )
        )
    return tuple(bars)


def compute_causal_zigzag_component(
    *,
    analytics_run: AnalyticsLabRun,
    candles: Sequence[Candle],
    indicator_snapshots: Sequence[AnalyticsIndicatorSnapshot],
    as_of: datetime,
    engine: CausalZigZagEngine | None = None,
) -> tuple[CausalZigZagPivot, ...]:
    versions = analytics_run.component_versions
    if versions.indicator_registry_version != ANALYTICS_INDICATOR_REGISTRY_IDENTITY:
        raise ValueError("analytics run does not identify installed indicator registry")
    if versions.zigzag_version != CAUSAL_ZIGZAG_REGISTRY_IDENTITY:
        raise ValueError("analytics run does not identify installed ZigZag registry")

    cutoff = _as_utc(as_of, field="as_of")
    visible_candles = tuple(candle for candle in candles if candle.close_time <= cutoff)
    visible_snapshots = tuple(
        snapshot for snapshot in indicator_snapshots if snapshot.as_of <= cutoff
    )
    bars = build_zigzag_input_bars(
        candles=visible_candles,
        indicator_snapshots=visible_snapshots,
    )
    calculator = engine or CausalZigZagEngine()
    pivots = calculator.compute(
        bars,
        analytics_run_id=analytics_run.analytics_run_id,
    )
    if any(pivot.confirmed_at > cutoff for pivot in pivots):
        raise ValueError("lookahead rejected: ZigZag pivot confirmed after as_of")
    return pivots


def compute_causal_zigzag_from_mtf_cursor(
    *,
    analytics_run: AnalyticsLabRun,
    mtf_cursor: HistoricalMultiTimeframeCursor,
    timeframe: str,
    indicator_snapshots: Sequence[AnalyticsIndicatorSnapshot],
    as_of: datetime,
    engine: CausalZigZagEngine | None = None,
) -> tuple[CausalZigZagPivot, ...]:
    """Canonical replay entry point: candles come only from the Money Heist MTF cursor."""
    normalized_timeframe = timeframe.strip().lower()
    if normalized_timeframe != analytics_run.decision_timeframe:
        raise ValueError("ZigZag timeframe must equal analytics run decision_timeframe")
    candles = canonical_candles_from_mtf_cursor(
        mtf_cursor=mtf_cursor,
        timeframe=normalized_timeframe,
        as_of=as_of,
    )
    return compute_causal_zigzag_component(
        analytics_run=analytics_run,
        candles=candles,
        indicator_snapshots=indicator_snapshots,
        as_of=as_of,
        engine=engine,
    )


def build_analytics_snapshot_with_structure_and_zigzag(
    *,
    analytics_run: AnalyticsLabRun,
    as_of_input: AnalyticsAsOfInput,
    indicators: AnalyticsIndicatorSnapshot,
    technical_events: Sequence[Any],
    market_structure: Any,
    zigzag_pivots: Sequence[CausalZigZagPivot],
) -> AnalyticsSnapshot:
    if any(pivot.confirmed_at > as_of_input.as_of for pivot in zigzag_pivots):
        raise ValueError("snapshot cannot expose an unconfirmed ZigZag pivot")
    return AnalyticsSnapshot.create(
        analytics_run=analytics_run,
        as_of_input=as_of_input,
        components={
            "indicators": indicators,
            "technical_events": tuple(technical_events),
            "market_structure": market_structure,
            "zigzag_pivots": tuple(zigzag_pivots),
        },
    )


__all__ = [
    "ANALYTICS_24A4_BUNDLE_VERSION",
    "build_analytics_snapshot_with_structure_and_zigzag",
    "build_zigzag_input_bars",
    "canonical_candles_from_mtf_cursor",
    "causal_structure_component_versions",
    "compute_causal_zigzag_component",
    "compute_causal_zigzag_from_mtf_cursor",
]
