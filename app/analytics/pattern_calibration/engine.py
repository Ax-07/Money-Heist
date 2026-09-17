from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from app.analytics.models import AnalyticsLabRun
from app.analytics.patterns.engine import pattern_evaluations_at
from app.analytics.patterns.models import PatternPivot
from app.analytics.structure import StructureSource
from app.market.models import Candle

from .comparison import summarize_pattern_source
from .models import (
    PatternCalibrationReport,
    PatternCalibrationRun,
    PatternCandidateDiagnostic,
    PatternSourceCalibration,
)


def calibrate_pattern_sources(
    *,
    analytics_run: AnalyticsLabRun,
    candles: Sequence[Candle],
    pivots_by_source: Mapping[StructureSource, Sequence[PatternPivot]],
    as_of: datetime,
) -> PatternCalibrationReport:
    if not pivots_by_source:
        raise ValueError("calibration requires at least one pivot source")
    calibration_run = PatternCalibrationRun.create(
        analytics_run,
        pivot_sources=[source.value for source in pivots_by_source],
    )
    source_results: list[PatternSourceCalibration] = []
    for source, supplied in sorted(pivots_by_source.items(), key=lambda item: item[0].value):
        if any(pivot.source != source for pivot in supplied):
            raise ValueError("pivot source mapping does not match PatternPivot.source")
        visible = tuple(pivot for pivot in supplied if pivot.confirmed_at <= as_of)
        cursor_fp = visible[-1].source_cursor_fingerprint if visible else "0" * 64
        evaluated = pattern_evaluations_at(
            candles=candles,
            pivots=visible,
            as_of=as_of,
            analytics_run_id=analytics_run.analytics_run_id,
            source_cursor_fingerprint=cursor_fp,
        )
        diagnostics = tuple(
            PatternCandidateDiagnostic.from_evaluation(
                item, calibration_run=calibration_run, as_of=as_of
            )
            for item in evaluated.candidates
        )
        summary = summarize_pattern_source(
            pivot_source=source.value,
            pivot_count=len({pivot.pivot_id for pivot in visible}),
            diagnostics=diagnostics,
        )
        source_results.append(
            PatternSourceCalibration(
                pivot_source=source.value,
                pivot_count=summary.pivot_count,
                diagnostics=diagnostics,
                accepted_pattern_ids=tuple(pattern.pattern_id for pattern in evaluated.patterns),
                summary=summary,
            )
        )
    return PatternCalibrationReport.create(
        calibration_run=calibration_run,
        as_of=as_of,
        sources=source_results,
    )


def merge_pattern_calibration_reports(
    reports: Sequence[PatternCalibrationReport],
) -> PatternCalibrationReport:
    """Merge repeated as-of observations without counting a stable candidate twice."""
    if not reports:
        raise ValueError("at least one calibration report is required")
    ordered = tuple(sorted(reports, key=lambda item: item.as_of))
    first = ordered[0]
    if any(
        item.calibration_run.calibration_run_id != first.calibration_run.calibration_run_id
        for item in ordered
    ):
        raise ValueError("reports belong to different calibration runs")

    by_source: dict[str, dict[str, PatternCandidateDiagnostic]] = {}
    pivot_counts: dict[str, int] = {}
    accepted_ids: dict[str, set[str]] = {}
    for report in ordered:
        for source in report.sources:
            pivot_counts[source.pivot_source] = max(
                pivot_counts.get(source.pivot_source, 0), source.pivot_count
            )
            accepted_ids.setdefault(source.pivot_source, set()).update(source.accepted_pattern_ids)
            bucket = by_source.setdefault(source.pivot_source, {})
            for diagnostic in source.diagnostics:
                previous = bucket.get(diagnostic.candidate_id)
                if (
                    previous is not None
                    and previous.candidate_fingerprint != diagnostic.candidate_fingerprint
                ):
                    raise ValueError("stable candidate changed across as-of observations")
                if previous is None or diagnostic.observed_as_of > previous.observed_as_of:
                    bucket[diagnostic.candidate_id] = diagnostic

    merged_sources: list[PatternSourceCalibration] = []
    for source_name in sorted(by_source):
        diagnostics = tuple(
            sorted(
                by_source[source_name].values(),
                key=lambda item: (item.detected_at, item.candidate_id),
            )
        )
        summary = summarize_pattern_source(
            pivot_source=source_name,
            pivot_count=pivot_counts[source_name],
            diagnostics=diagnostics,
        )
        merged_sources.append(
            PatternSourceCalibration(
                pivot_source=source_name,
                pivot_count=summary.pivot_count,
                diagnostics=diagnostics,
                accepted_pattern_ids=tuple(sorted(accepted_ids.get(source_name, set()))),
                summary=summary,
            )
        )
    return PatternCalibrationReport.create(
        calibration_run=first.calibration_run,
        as_of=ordered[-1].as_of,
        sources=merged_sources,
    )
