from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.analytics import (
    AnalyticsAsOfInput,
    AnalyticsLabManifest,
    AnalyticsLabRun,
    AnalyticsPeriodRole,
    AnalyticsSnapshot,
    build_analytics_manifest,
)
from app.analytics.events import compute_technical_event_component
from app.analytics.indicators import AnalyticsIndicatorEngine, AnalyticsIndicatorSnapshot
from app.analytics.patterns import (
    build_analytics_snapshot_with_patterns,
    compute_patterns_from_causal_zigzag,
)
from app.analytics.research import causal_research_component_versions
from app.analytics.structure import project_money_heist_structure
from app.analytics.zigzag import compute_causal_zigzag_component
from app.common.canonical import stable_digest
from app.evaluation.analytics_attribution import (
    build_funnel_stage_analytics_attribution,
    build_scanner_analytics_attribution,
    link_replay_opportunities,
)
from app.evaluation.decision_intelligence import build_decision_intelligence_record_set
from app.market.multitimeframe import HistoricalMultiTimeframeCursor
from app.market.structure import build_market_structure_context
from app.services.backtest.analytics_lab import (
    build_analytics_as_of_input,
    build_analytics_lab_run,
)
from app.services.backtest.models import BacktestRun
from app.services.backtest.splits import BacktestPeriodRole
from app.services.frontend_v2.analytics_overlays import (
    FrontendAnalyticsGeometryProjection,
    build_frontend_analytics_geometry_projection,
    geometry_export_name,
)
from app.services.frontend_v2.decision_intelligence import (
    FrontendDecisionIntelligenceBundle,
    build_frontend_decision_intelligence_bundle,
    bundle_to_json,
    projection_export_name,
)

SINGLE_TIMEFRAME_ANALYTICS_POLICY_VERSION = "single-timeframe-closed-v1"


@dataclass(frozen=True, slots=True)
class FrontendPostRunProjection:
    """Role-scoped 24A -> 24B -> 24C projection for one completed replay."""

    analytics_run: AnalyticsLabRun
    analytics_manifest: AnalyticsLabManifest
    analytics_snapshots: tuple[AnalyticsSnapshot, ...]
    decision_bundle: FrontendDecisionIntelligenceBundle
    geometry: FrontendAnalyticsGeometryProjection

    def exports(self) -> dict[str, tuple[str, str]]:
        geometry_json = json.dumps(
            self.geometry.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return {
            projection_export_name(self.decision_bundle.role): (
                "application/json",
                bundle_to_json(self.decision_bundle),
            ),
            geometry_export_name(self.geometry.role): (
                "application/json",
                geometry_json,
            ),
        }


def _has_full_mtf_provenance(run: BacktestRun) -> bool:
    assumptions = run.config.execution_assumptions
    return all(
        str(assumptions.get(key, "")).strip()
        for key in (
            "mtf_runtime_version",
            "historical_source_timeframe",
            "decision_timeframe",
            "mtf_timeframes",
            "mtf_policy_version",
            "market_structure_version",
        )
    )


def _configured_timeframes(run: BacktestRun) -> tuple[str, ...]:
    raw = str(run.config.execution_assumptions.get("mtf_timeframes", ""))
    values = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    if not values:
        raise ValueError("Analytics post-processing requires configured mtf_timeframes")
    return values


def _points_by_time(replay: Any) -> dict[Any, Any]:
    points: dict[Any, Any] = {}
    for point in replay.points:
        if point.observed_at in points:
            raise ValueError("Historical Replay contains duplicate observation timestamps")
        points[point.observed_at] = point
    return points


def _single_timeframe_cursor_fingerprint(
    *,
    run: BacktestRun,
    visible_candles: tuple[Any, ...],
    as_of: Any,
) -> str:
    return stable_digest(
        {
            "schema": "money-heist.single-timeframe-analytics-cursor.v1",
            "source_backtest_run_id": run.run_id,
            "symbol": run.dataset.symbol,
            "timeframe": run.dataset.timeframe,
            "as_of": as_of,
            "candles": tuple(
                (
                    candle.open_time,
                    candle.close_time,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                )
                for candle in visible_candles
            ),
        }
    )


def _single_timeframe_run(
    run: BacktestRun,
    *,
    role: BacktestPeriodRole,
) -> AnalyticsLabRun:
    return AnalyticsLabRun.create(
        source_backtest_run_id=run.run_id,
        dataset_id=run.dataset.dataset_id,
        dataset_version=run.dataset.version,
        dataset_content_sha256=run.dataset.content_sha256,
        dataset_source=run.dataset.source,
        system_id=run.config.system_id,
        symbol=run.dataset.symbol,
        source_timeframe=run.dataset.timeframe,
        decision_timeframe=run.dataset.timeframe,
        period_start=run.period_start,
        period_end=run.period_end,
        period_role=AnalyticsPeriodRole(role.value),
        mtf_policy_version=SINGLE_TIMEFRAME_ANALYTICS_POLICY_VERSION,
        component_versions=causal_research_component_versions(),
    )


def _single_timeframe_as_of_input(
    run: BacktestRun,
    *,
    analytics_run: AnalyticsLabRun,
    as_of: Any,
    source_cursor_fingerprint: str,
) -> AnalyticsAsOfInput:
    return AnalyticsAsOfInput(
        source_backtest_run_id=run.run_id,
        dataset_id=run.dataset.dataset_id,
        dataset_version=run.dataset.version,
        dataset_content_sha256=run.dataset.content_sha256,
        dataset_source=run.dataset.source,
        system_id=run.config.system_id,
        symbol=run.dataset.symbol,
        source_timeframe=analytics_run.source_timeframe,
        decision_timeframe=analytics_run.decision_timeframe,
        as_of=as_of,
        mtf_policy_version=analytics_run.mtf_policy_version,
        source_cursor_fingerprint=source_cursor_fingerprint,
    )


def _build_full_mtf_analytics(
    *,
    run: BacktestRun,
    role: BacktestPeriodRole,
    candles: tuple[Any, ...],
    replay: Any,
) -> tuple[AnalyticsLabRun, tuple[AnalyticsSnapshot, ...], AnalyticsLabManifest]:
    analytics_run = build_analytics_lab_run(
        run,
        period_role=role,
        component_versions=causal_research_component_versions(),
    )
    cursor = HistoricalMultiTimeframeCursor(
        source_timeframe=analytics_run.source_timeframe,
        target_timeframes=_configured_timeframes(run),
        policy_version=analytics_run.mtf_policy_version,
    )
    points = _points_by_time(replay)
    indicator_engine = AnalyticsIndicatorEngine()
    indicator_history: list[AnalyticsIndicatorSnapshot] = []
    previous_indicators: AnalyticsIndicatorSnapshot | None = None
    snapshots: list[AnalyticsSnapshot] = []
    consumed: set[Any] = set()

    for candle in sorted(candles, key=lambda item: item.close_time):
        if candle.close_time > run.period_end:
            break
        emitted = cursor.push(candle)
        if analytics_run.decision_timeframe not in emitted:
            continue

        state = cursor.state()
        decision_candles = cursor.series(analytics_run.decision_timeframe)
        current_indicators = indicator_engine.compute(
            decision_candles,
            symbol=analytics_run.symbol,
            timeframe=analytics_run.decision_timeframe,
            as_of=state.as_of,
            source_cursor_fingerprint=state.cursor_fingerprint,
        )
        technical_events = compute_technical_event_component(
            analytics_run=analytics_run,
            previous_indicator_snapshot=previous_indicators,
            current_indicator_snapshot=current_indicators,
        )
        indicator_history.append(current_indicators)
        previous_indicators = current_indicators

        point = points.get(state.as_of)
        if point is None:
            continue
        consumed.add(state.as_of)
        if point.mtf_cursor_fingerprint is None:
            raise ValueError("Analytics-compatible replay point is missing MTF provenance")
        if str(point.mtf_cursor_fingerprint) != state.cursor_fingerprint:
            raise ValueError("post-run MTF cursor differs from Historical Replay")

        as_of_input = build_analytics_as_of_input(run, state)
        structure_context = build_market_structure_context(
            mtf_cursor=cursor,
            observed_at=state.as_of,
            version=str(run.config.execution_assumptions["market_structure_version"]),
        )
        if point.market_structure_context is not None and (
            point.market_structure_context.context_fingerprint
            != structure_context.context_fingerprint
        ):
            raise ValueError("post-run market structure differs from Historical Replay")
        structure = project_money_heist_structure(structure_context)
        pivots = compute_causal_zigzag_component(
            analytics_run=analytics_run,
            candles=decision_candles,
            indicator_snapshots=tuple(indicator_history),
            as_of=state.as_of,
        )
        patterns = compute_patterns_from_causal_zigzag(
            analytics_run=analytics_run,
            candles=decision_candles,
            zigzag_pivots=pivots,
            as_of_input=as_of_input,
        )
        snapshots.append(
            build_analytics_snapshot_with_patterns(
                analytics_run=analytics_run,
                as_of_input=as_of_input,
                indicators=current_indicators,
                technical_events=technical_events,
                market_structure=structure,
                zigzag_pivots=pivots,
                patterns=patterns,
            )
        )

    missing = tuple(sorted(set(points) - consumed))
    if missing:
        raise ValueError(
            "post-run Analytics did not cover every replay observation: "
            + ",".join(value.isoformat() for value in missing[:5])
        )

    ordered = tuple(sorted(snapshots, key=lambda item: (item.as_of, item.snapshot_id)))
    return analytics_run, ordered, build_analytics_manifest(analytics_run, ordered)


def _build_single_timeframe_analytics(
    *,
    run: BacktestRun,
    role: BacktestPeriodRole,
    candles: tuple[Any, ...],
    replay: Any,
) -> tuple[AnalyticsLabRun, tuple[AnalyticsSnapshot, ...], AnalyticsLabManifest]:
    analytics_run = _single_timeframe_run(run, role=role)
    points = _points_by_time(replay)
    indicator_engine = AnalyticsIndicatorEngine()
    indicator_history: list[AnalyticsIndicatorSnapshot] = []
    previous_indicators: AnalyticsIndicatorSnapshot | None = None
    snapshots: list[AnalyticsSnapshot] = []
    visible: list[Any] = []
    consumed: set[Any] = set()

    for candle in sorted(candles, key=lambda item: item.close_time):
        if candle.close_time > run.period_end:
            break
        visible.append(candle)
        cursor_fingerprint = _single_timeframe_cursor_fingerprint(
            run=run,
            visible_candles=tuple(visible),
            as_of=candle.close_time,
        )
        current_indicators = indicator_engine.compute(
            tuple(visible),
            symbol=analytics_run.symbol,
            timeframe=analytics_run.decision_timeframe,
            as_of=candle.close_time,
            source_cursor_fingerprint=cursor_fingerprint,
        )
        technical_events = compute_technical_event_component(
            analytics_run=analytics_run,
            previous_indicator_snapshot=previous_indicators,
            current_indicator_snapshot=current_indicators,
        )
        indicator_history.append(current_indicators)
        previous_indicators = current_indicators

        point = points.get(candle.close_time)
        if point is None:
            continue
        consumed.add(candle.close_time)
        as_of_input = _single_timeframe_as_of_input(
            run,
            analytics_run=analytics_run,
            as_of=candle.close_time,
            source_cursor_fingerprint=cursor_fingerprint,
        )
        pivots = compute_causal_zigzag_component(
            analytics_run=analytics_run,
            candles=tuple(visible),
            indicator_snapshots=tuple(indicator_history),
            as_of=candle.close_time,
        )
        patterns = compute_patterns_from_causal_zigzag(
            analytics_run=analytics_run,
            candles=tuple(visible),
            zigzag_pivots=pivots,
            as_of_input=as_of_input,
        )
        snapshots.append(
            build_analytics_snapshot_with_patterns(
                analytics_run=analytics_run,
                as_of_input=as_of_input,
                indicators=current_indicators,
                technical_events=technical_events,
                market_structure=None,
                zigzag_pivots=pivots,
                patterns=patterns,
            )
        )

    missing = tuple(sorted(set(points) - consumed))
    if missing:
        raise ValueError(
            "single-timeframe Analytics did not cover every replay observation: "
            + ",".join(value.isoformat() for value in missing[:5])
        )

    ordered = tuple(sorted(snapshots, key=lambda item: (item.as_of, item.snapshot_id)))
    return analytics_run, ordered, build_analytics_manifest(analytics_run, ordered)


def _build_analytics_artifacts(
    *,
    run: BacktestRun,
    role: BacktestPeriodRole,
    candles: tuple[Any, ...],
    replay: Any,
) -> tuple[AnalyticsLabRun, tuple[AnalyticsSnapshot, ...], AnalyticsLabManifest]:
    if str(replay.backtest_result.run.run_id) != str(run.run_id):
        raise ValueError("Historical Replay does not belong to requested BacktestRun")
    if _has_full_mtf_provenance(run):
        return _build_full_mtf_analytics(
            run=run,
            role=role,
            candles=candles,
            replay=replay,
        )
    return _build_single_timeframe_analytics(
        run=run,
        role=role,
        candles=candles,
        replay=replay,
    )


def build_frontend_postrun_projection(
    *,
    campaign_id: str,
    role: BacktestPeriodRole,
    run: BacktestRun,
    candles: tuple[Any, ...],
    replay: Any,
    decision_funnel_report: Any,
    min_priority_score: int,
) -> FrontendPostRunProjection:
    """Automatically materialize 24A -> 24B -> 24C after a completed role replay.

    This is post-hoc and observation-only. Scanner, agents, Risk and PAPER are
    never re-run here.
    """

    analytics_run, snapshots, manifest = _build_analytics_artifacts(
        run=run,
        role=role,
        candles=candles,
        replay=replay,
    )
    opportunity_links = link_replay_opportunities(
        replay,
        analytics_run=analytics_run,
        snapshots=snapshots,
    )
    decision_records = build_decision_intelligence_record_set(
        replay,
        analytics_links=opportunity_links,
        decision_funnel_report=decision_funnel_report,
    )
    scanner_attribution = build_scanner_analytics_attribution(
        replay,
        analytics_run=analytics_run,
        snapshots=snapshots,
        min_priority_score=min_priority_score,
        opportunity_links=opportunity_links,
        decision_intelligence_records=decision_records,
    )
    funnel_attribution = build_funnel_stage_analytics_attribution(decision_records)

    role_value = role.value
    decision_bundle = build_frontend_decision_intelligence_bundle(
        campaign_id=campaign_id,
        role=role_value,
        analytics_run=analytics_run,
        analytics_manifest=manifest,
        analytics_snapshots=snapshots,
        scanner_attribution=scanner_attribution,
        opportunity_links=opportunity_links,
        decision_intelligence=decision_records,
        funnel_stage_attribution=funnel_attribution,
    )
    geometry = build_frontend_analytics_geometry_projection(
        campaign_id=campaign_id,
        role=role_value,
        analytics_run_id=analytics_run.analytics_run_id,
        analytics_snapshots=snapshots,
    )
    return FrontendPostRunProjection(
        analytics_run=analytics_run,
        analytics_manifest=manifest,
        analytics_snapshots=snapshots,
        decision_bundle=decision_bundle,
        geometry=geometry,
    )


def build_frontend_postrun_exports(
    *,
    campaign_id: str,
    role: BacktestPeriodRole,
    run: BacktestRun,
    candles: tuple[Any, ...],
    replay: Any,
    decision_funnel_report: Any,
    min_priority_score: int,
) -> dict[str, tuple[str, str]]:
    return build_frontend_postrun_projection(
        campaign_id=campaign_id,
        role=role,
        run=run,
        candles=candles,
        replay=replay,
        decision_funnel_report=decision_funnel_report,
        min_priority_score=min_priority_score,
    ).exports()


__all__ = [
    "FrontendPostRunProjection",
    "SINGLE_TIMEFRAME_ANALYTICS_POLICY_VERSION",
    "build_frontend_postrun_exports",
    "build_frontend_postrun_projection",
]
