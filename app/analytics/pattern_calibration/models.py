from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.analytics.models import AnalyticsLabRun, AnalyticsPeriodRole
from app.analytics.patterns.diagnostics import (
    PatternCandidateEvaluation,
    PatternRejectionReason,
    PatternRuleEvaluation,
)
from app.analytics.patterns.registry import ANALYTICS_PATTERN_REGISTRY_IDENTITY
from app.common.canonical import canonical_json, stable_digest, stable_uuid

from .registry import (
    PATTERN_CALIBRATION_VERSION,
    PATTERN_COMPARISON_SEMANTICS_VERSION,
    PATTERN_REJECTION_TAXONOMY_VERSION,
)

PATTERN_CALIBRATION_RUN_SCHEMA_VERSION = "money-heist.pattern-calibration-run.v1"
PATTERN_CALIBRATION_REPORT_SCHEMA_VERSION = "money-heist.pattern-calibration-report.v1"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("calibration datetime must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class PatternCalibrationRun:
    calibration_run_id: str
    analytics_run_id: str
    source_backtest_run_id: str
    dataset_id: str
    dataset_version: str
    dataset_content_sha256: str
    symbol: str
    timeframe: str
    period_start: datetime
    period_end: datetime
    period_role: AnalyticsPeriodRole
    pattern_registry_version: str
    calibration_version: str
    rejection_taxonomy_version: str
    comparison_semantics_version: str
    pivot_sources: tuple[str, ...]
    fingerprint: str
    schema_version: str = PATTERN_CALIBRATION_RUN_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        analytics_run: AnalyticsLabRun,
        *,
        pivot_sources: Sequence[str],
        calibration_version: str = PATTERN_CALIBRATION_VERSION,
    ) -> PatternCalibrationRun:
        sources = tuple(sorted(set(pivot_sources)))
        if not sources:
            raise ValueError("calibration run requires at least one pivot source")
        if (
            analytics_run.component_versions.pattern_registry_version
            != ANALYTICS_PATTERN_REGISTRY_IDENTITY
        ):
            raise ValueError("analytics run does not identify installed pattern registry")
        identity = {
            "schema_version": PATTERN_CALIBRATION_RUN_SCHEMA_VERSION,
            "analytics_run_id": analytics_run.analytics_run_id,
            "calibration_version": calibration_version,
            "rejection_taxonomy_version": PATTERN_REJECTION_TAXONOMY_VERSION,
            "comparison_semantics_version": PATTERN_COMPARISON_SEMANTICS_VERSION,
            "pattern_registry_version": ANALYTICS_PATTERN_REGISTRY_IDENTITY,
            "pivot_sources": sources,
        }
        return cls(
            calibration_run_id=stable_uuid("pattern-calibration-run", identity),
            analytics_run_id=analytics_run.analytics_run_id,
            source_backtest_run_id=analytics_run.source_backtest_run_id,
            dataset_id=analytics_run.dataset_id,
            dataset_version=analytics_run.dataset_version,
            dataset_content_sha256=analytics_run.dataset_content_sha256,
            symbol=analytics_run.symbol,
            timeframe=analytics_run.decision_timeframe,
            period_start=analytics_run.period_start,
            period_end=analytics_run.period_end,
            period_role=analytics_run.period_role,
            pattern_registry_version=ANALYTICS_PATTERN_REGISTRY_IDENTITY,
            calibration_version=calibration_version,
            rejection_taxonomy_version=PATTERN_REJECTION_TAXONOMY_VERSION,
            comparison_semantics_version=PATTERN_COMPARISON_SEMANTICS_VERSION,
            pivot_sources=sources,
            fingerprint=stable_digest(identity),
        )


@dataclass(frozen=True, slots=True)
class PatternCandidateDiagnostic:
    candidate_id: str
    calibration_run_id: str
    analytics_run_id: str
    pattern_type: str
    candidate_family: str
    pivot_source: str
    symbol: str
    timeframe: str
    detected_at: datetime
    observed_as_of: datetime
    source_pivot_ids: tuple[str, ...]
    source_pivot_fingerprints: tuple[str, ...]
    accepted: bool
    pattern_id: str | None
    rejection_reasons: tuple[PatternRejectionReason, ...]
    diagnostic_flags: tuple[str, ...]
    metrics: Mapping[str, Any]
    rule_evaluations: tuple[PatternRuleEvaluation, ...]
    pattern_registry_version: str
    calibration_version: str
    candidate_fingerprint: str

    @classmethod
    def from_evaluation(
        cls,
        evaluation: PatternCandidateEvaluation,
        *,
        calibration_run: PatternCalibrationRun,
        as_of: datetime,
    ) -> PatternCandidateDiagnostic:
        return cls(
            candidate_id=evaluation.candidate_id,
            calibration_run_id=calibration_run.calibration_run_id,
            analytics_run_id=calibration_run.analytics_run_id,
            pattern_type=evaluation.pattern_type,
            candidate_family=evaluation.candidate_family.value,
            pivot_source=evaluation.pivot_source,
            symbol=evaluation.symbol,
            timeframe=evaluation.timeframe,
            detected_at=evaluation.detected_at,
            observed_as_of=_utc(as_of),
            source_pivot_ids=evaluation.source_pivot_ids,
            source_pivot_fingerprints=evaluation.source_pivot_fingerprints,
            accepted=evaluation.accepted,
            pattern_id=evaluation.pattern_id,
            rejection_reasons=evaluation.rejection_reasons,
            diagnostic_flags=evaluation.diagnostic_flags,
            metrics=evaluation.metrics,
            rule_evaluations=evaluation.rule_evaluations,
            pattern_registry_version=ANALYTICS_PATTERN_REGISTRY_IDENTITY,
            calibration_version=calibration_run.calibration_version,
            candidate_fingerprint=evaluation.candidate_fingerprint,
        )


@dataclass(frozen=True, slots=True)
class PatternTypeSummary:
    pattern_type: str
    candidate_count: int
    accepted_count: int
    rejected_count: int
    acceptance_ratio: float
    rejection_reason_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class PatternSourceSummary:
    pivot_source: str
    pivot_count: int
    candidate_count: int
    accepted_count: int
    rejected_count: int
    acceptance_ratio: float
    accepted_by_pattern_type: Mapping[str, int]
    rejected_by_pattern_type: Mapping[str, int]
    rejection_reason_counts: Mapping[str, int]
    per_pattern: tuple[PatternTypeSummary, ...]


@dataclass(frozen=True, slots=True)
class PatternSourceCalibration:
    pivot_source: str
    pivot_count: int
    diagnostics: tuple[PatternCandidateDiagnostic, ...]
    accepted_pattern_ids: tuple[str, ...]
    summary: PatternSourceSummary


@dataclass(frozen=True, slots=True)
class PatternSourceComparison:
    pattern_registry_version: str
    comparison_semantics_version: str
    same_pattern_registry_version: bool
    sources: tuple[PatternSourceSummary, ...]
    fingerprint: str

    @classmethod
    def create(
        cls,
        sources: Sequence[PatternSourceSummary],
        *,
        pattern_registry_versions: Sequence[str],
    ) -> PatternSourceComparison:
        versions = tuple(pattern_registry_versions)
        if not versions or len(set(versions)) != 1:
            raise ValueError("pivot-source comparison requires identical Pattern Registry versions")
        if versions[0] != ANALYTICS_PATTERN_REGISTRY_IDENTITY:
            raise ValueError("comparison registry differs from installed Pattern Registry")
        ordered = tuple(sorted(sources, key=lambda item: item.pivot_source))
        payload = {
            "pattern_registry_version": versions[0],
            "comparison_semantics_version": PATTERN_COMPARISON_SEMANTICS_VERSION,
            "same_pattern_registry_version": True,
            "sources": ordered,
        }
        return cls(
            pattern_registry_version=versions[0],
            comparison_semantics_version=PATTERN_COMPARISON_SEMANTICS_VERSION,
            same_pattern_registry_version=True,
            sources=ordered,
            fingerprint=stable_digest(payload),
        )


@dataclass(frozen=True, slots=True)
class PatternCalibrationReport:
    calibration_run: PatternCalibrationRun
    as_of: datetime
    period_role: AnalyticsPeriodRole
    sources: tuple[PatternSourceCalibration, ...]
    comparison: PatternSourceComparison
    fingerprint: str
    schema_version: str = PATTERN_CALIBRATION_REPORT_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        calibration_run: PatternCalibrationRun,
        as_of: datetime,
        sources: Sequence[PatternSourceCalibration],
    ) -> PatternCalibrationReport:
        cutoff = _utc(as_of)
        if not calibration_run.period_start <= cutoff <= calibration_run.period_end:
            raise ValueError("calibration as_of must stay inside AnalyticsLabRun period")
        ordered = tuple(sorted(sources, key=lambda item: item.pivot_source))
        comparison = PatternSourceComparison.create(
            [item.summary for item in ordered],
            pattern_registry_versions=[calibration_run.pattern_registry_version for _ in ordered],
        )
        payload = {
            "schema_version": PATTERN_CALIBRATION_REPORT_SCHEMA_VERSION,
            "calibration_run_id": calibration_run.calibration_run_id,
            "as_of": cutoff,
            "period_role": calibration_run.period_role,
            "sources": ordered,
            "comparison": comparison,
        }
        return cls(
            calibration_run=calibration_run,
            as_of=cutoff,
            period_role=calibration_run.period_role,
            sources=ordered,
            comparison=comparison,
            fingerprint=stable_digest(payload),
        )


def pattern_calibration_report_to_json(report: PatternCalibrationReport) -> str:
    return canonical_json(report)
