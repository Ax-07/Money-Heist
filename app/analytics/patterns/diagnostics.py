from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from app.common.canonical import stable_digest, stable_uuid

from .models import PatternOccurrence, PatternPivot
from .registry import ANALYTICS_PATTERN_REGISTRY_VERSION, PatternType

PATTERN_CANDIDATE_SCHEMA_VERSION = "money-heist.analytics-pattern-candidate.v1"


class PatternCandidateFamily(StrEnum):
    DOUBLE = "DOUBLE"
    HEAD_SHOULDERS = "HEAD_SHOULDERS"
    GEOMETRY = "GEOMETRY"


class PatternRejectionReason(StrEnum):
    INVALID_PIVOT_ORDER = "INVALID_PIVOT_ORDER"
    SPACING_TOO_SHORT = "SPACING_TOO_SHORT"
    SPACING_TOO_LONG = "SPACING_TOO_LONG"
    OUTER_LEVELS_TOO_FAR_APART = "OUTER_LEVELS_TOO_FAR_APART"
    INTERMEDIATE_RETRACEMENT_TOO_SHALLOW = "INTERMEDIATE_RETRACEMENT_TOO_SHALLOW"
    PRIOR_TREND_CONFLICT = "PRIOR_TREND_CONFLICT"
    SHOULDERS_TOO_ASYMMETRIC = "SHOULDERS_TOO_ASYMMETRIC"
    NECKLINE_POINTS_TOO_ASYMMETRIC = "NECKLINE_POINTS_TOO_ASYMMETRIC"
    HEAD_NOT_PROMINENT_ENOUGH = "HEAD_NOT_PROMINENT_ENOUGH"
    TIME_SYMMETRY_OUT_OF_RANGE = "TIME_SYMMETRY_OUT_OF_RANGE"
    DURATION_TOO_SHORT = "DURATION_TOO_SHORT"
    DURATION_TOO_LONG = "DURATION_TOO_LONG"
    TRENDLINE_FIT_ERROR_TOO_HIGH = "TRENDLINE_FIT_ERROR_TOO_HIGH"
    TRENDLINE_BOUNDS_CROSSED = "TRENDLINE_BOUNDS_CROSSED"
    STRUCTURE_TOO_NARROW = "STRUCTURE_TOO_NARROW"
    GEOMETRY_NOT_CLASSIFIED = "GEOMETRY_NOT_CLASSIFIED"
    PARALLEL_LINES_HAVE_NO_APEX = "PARALLEL_LINES_HAVE_NO_APEX"
    APEX_NOT_IN_FUTURE = "APEX_NOT_IN_FUTURE"
    APEX_TOO_FAR = "APEX_TOO_FAR"
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"


def _freeze(values: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(sorted(values.items())))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("candidate datetime must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class PatternRuleEvaluation:
    rule_id: str
    passed: bool
    observed: Mapping[str, Any]
    required: Mapping[str, Any]
    rejection_reason: PatternRejectionReason | None = None

    def __post_init__(self) -> None:
        rule_id = self.rule_id.strip()
        if not rule_id:
            raise ValueError("rule_id must not be empty")
        if self.passed and self.rejection_reason is not None:
            raise ValueError("passing rule cannot carry a rejection reason")
        if not self.passed and self.rejection_reason is None:
            raise ValueError("failing rule requires a rejection reason")
        object.__setattr__(self, "rule_id", rule_id)
        object.__setattr__(self, "observed", _freeze(self.observed))
        object.__setattr__(self, "required", _freeze(self.required))


@dataclass(frozen=True, slots=True)
class PatternCandidateEvaluation:
    candidate_id: str
    candidate_family: PatternCandidateFamily
    pattern_type: str
    pivot_source: str
    symbol: str
    timeframe: str
    detected_at: datetime
    source_pivot_ids: tuple[str, ...]
    source_pivot_fingerprints: tuple[str, ...]
    geometry_accepted: bool
    accepted: bool
    pattern_id: str | None
    rejection_reasons: tuple[PatternRejectionReason, ...]
    diagnostic_flags: tuple[str, ...]
    metrics: Mapping[str, Any]
    rule_evaluations: tuple[PatternRuleEvaluation, ...]
    registry_version: str
    candidate_fingerprint: str
    schema_version: str = PATTERN_CANDIDATE_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        family: PatternCandidateFamily,
        pattern_type: PatternType | str | None,
        pivots: Sequence[PatternPivot],
        geometry_accepted: bool,
        accepted: bool,
        occurrence: PatternOccurrence | None,
        rejection_reasons: Sequence[PatternRejectionReason],
        diagnostic_flags: Sequence[str],
        metrics: Mapping[str, Any],
        rule_evaluations: Sequence[PatternRuleEvaluation],
    ) -> PatternCandidateEvaluation:
        if not pivots:
            raise ValueError("candidate requires pivots")
        if len({pivot.source for pivot in pivots}) != 1:
            raise ValueError("candidate pivots must share source")
        if (
            len({pivot.symbol for pivot in pivots}) != 1
            or len({pivot.timeframe for pivot in pivots}) != 1
        ):
            raise ValueError("candidate pivots must share symbol/timeframe")
        type_value = (
            "GEOMETRY_UNCLASSIFIED"
            if pattern_type is None
            else getattr(pattern_type, "value", str(pattern_type))
        )
        pivot_ids = tuple(pivot.pivot_id for pivot in pivots)
        pivot_fingerprints = tuple(pivot.source_fingerprint for pivot in pivots)
        identity = {
            "schema_version": PATTERN_CANDIDATE_SCHEMA_VERSION,
            "candidate_family": family,
            "pattern_type": type_value,
            "pivot_source": pivots[0].source,
            "symbol": pivots[0].symbol,
            "timeframe": pivots[0].timeframe,
            "source_pivot_ids": pivot_ids,
            "source_pivot_fingerprints": pivot_fingerprints,
            "registry_version": ANALYTICS_PATTERN_REGISTRY_VERSION,
        }
        normalized_reasons = tuple(rejection_reasons)
        normalized_flags = tuple(sorted(set(diagnostic_flags)))
        frozen_metrics = _freeze(metrics)
        evaluations = tuple(rule_evaluations)
        detected_at = _utc(max(pivot.confirmed_at for pivot in pivots))
        fingerprint_payload = {
            "identity": identity,
            "detected_at": detected_at,
            "geometry_accepted": geometry_accepted,
            "accepted": accepted,
            "rejection_reasons": normalized_reasons,
            "diagnostic_flags": normalized_flags,
            "metrics": frozen_metrics,
            "rule_evaluations": evaluations,
        }
        return cls(
            candidate_id=stable_uuid("analytics-pattern-candidate", identity),
            candidate_family=family,
            pattern_type=type_value,
            pivot_source=pivots[0].source.value,
            symbol=pivots[0].symbol,
            timeframe=pivots[0].timeframe,
            detected_at=detected_at,
            source_pivot_ids=pivot_ids,
            source_pivot_fingerprints=pivot_fingerprints,
            geometry_accepted=geometry_accepted,
            accepted=accepted,
            pattern_id=occurrence.pattern_id if accepted and occurrence is not None else None,
            rejection_reasons=normalized_reasons,
            diagnostic_flags=normalized_flags,
            metrics=frozen_metrics,
            rule_evaluations=evaluations,
            registry_version=ANALYTICS_PATTERN_REGISTRY_VERSION,
            candidate_fingerprint=stable_digest(fingerprint_payload),
        )


@dataclass(frozen=True, slots=True)
class PatternEvaluationResult:
    patterns: tuple[PatternOccurrence, ...]
    candidates: tuple[PatternCandidateEvaluation, ...]
