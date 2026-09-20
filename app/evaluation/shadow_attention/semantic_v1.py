from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.canonical import stable_uuid

from .models import (
    ShadowAttentionComparison,
    ShadowAttentionReason,
    ShadowAttentionReasonKind,
    ShadowAttentionReport,
)

SHADOW_ATTENTION_SEMANTIC_V1_SCHEMA_VERSION = (
    "money-heist.shadow-attention-semantic-v1-report.v1"
)
SHADOW_ATTENTION_SEMANTIC_V1_POLICY_VERSION = (
    "shadow-attention-semantic-same-bar-mature-v1"
)
MATURE_PATTERN_STATUSES = frozenset({"CONFIRMED", "FAILED", "INVALIDATED"})


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class SemanticAttentionClause(StrEnum):
    DIVERSE_TECHNICAL_FAMILIES = "DIVERSE_TECHNICAL_FAMILIES"
    TECHNICAL_PLUS_ZIGZAG = "TECHNICAL_PLUS_ZIGZAG"
    MATURE_PATTERN_TRANSITION = "MATURE_PATTERN_TRANSITION"


class SemanticAttentionObservation(FrozenModel):
    observation_id: str = Field(min_length=1)
    source_v0_observation_id: str = Field(min_length=1)
    scanner_evaluation_id: str = Field(min_length=1)
    observed_at: datetime
    analytics_matched: bool
    analytics_snapshot_id: str | None = None
    scanner_classification: str = Field(min_length=1)
    scanner_score: int = Field(ge=0, le=100)
    scanner_triggers: tuple[str, ...] = ()
    scanner_wake: bool
    shadow_wake: bool
    comparison: ShadowAttentionComparison
    clauses: tuple[SemanticAttentionClause, ...] = ()
    reasons: tuple[ShadowAttentionReason, ...] = ()

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_contract(self) -> SemanticAttentionObservation:
        if tuple(sorted(set(self.scanner_triggers))) != self.scanner_triggers:
            raise ValueError("scanner_triggers must be sorted and unique")
        if self.analytics_matched != (self.analytics_snapshot_id is not None):
            raise ValueError("analytics_matched must agree with analytics_snapshot_id")
        if tuple(sorted(set(self.clauses), key=lambda item: item.value)) != self.clauses:
            raise ValueError("clauses must be sorted and unique")
        ordered_reasons = tuple(
            sorted(
                self.reasons,
                key=lambda item: (item.kind.value, item.key, item.source_id),
            )
        )
        if ordered_reasons != self.reasons:
            raise ValueError("reasons must be deterministically sorted")
        if self.shadow_wake != bool(self.clauses):
            raise ValueError("shadow_wake must equal bool(clauses)")
        if not self.analytics_matched:
            if self.shadow_wake or self.clauses or self.reasons:
                raise ValueError("unmatched Analytics cannot wake semantic v1")
            expected = ShadowAttentionComparison.UNAVAILABLE
        elif self.scanner_wake and self.shadow_wake:
            expected = ShadowAttentionComparison.BOTH
        elif self.scanner_wake:
            expected = ShadowAttentionComparison.SCANNER_ONLY
        elif self.shadow_wake:
            expected = ShadowAttentionComparison.SHADOW_ONLY
        else:
            expected = ShadowAttentionComparison.NEITHER
        if self.comparison is not expected:
            raise ValueError("comparison does not match wake states")
        return self


class SemanticAttentionSummary(FrozenModel):
    scanner_evaluations: int = Field(ge=0)
    analytics_matched: int = Field(ge=0)
    analytics_unmatched: int = Field(ge=0)
    scanner_wakes: int = Field(ge=0)
    shadow_wakes: int = Field(ge=0)
    both: int = Field(ge=0)
    scanner_only: int = Field(ge=0)
    shadow_only: int = Field(ge=0)
    neither: int = Field(ge=0)
    unavailable: int = Field(ge=0)
    unavailable_scanner_wakes: int = Field(ge=0)
    unavailable_scanner_sleeps: int = Field(ge=0)
    diverse_technical_family_wakes: int = Field(ge=0)
    technical_plus_zigzag_wakes: int = Field(ge=0)
    mature_pattern_transition_wakes: int = Field(ge=0)
    multi_clause_wakes: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_conservation(self) -> SemanticAttentionSummary:
        if self.analytics_matched + self.analytics_unmatched != self.scanner_evaluations:
            raise ValueError("Analytics coverage must conserve Scanner evaluations")
        if (
            self.both
            + self.scanner_only
            + self.unavailable_scanner_wakes
            != self.scanner_wakes
        ):
            raise ValueError("Scanner comparison counts do not conserve scanner_wakes")
        if self.both + self.shadow_only != self.shadow_wakes:
            raise ValueError("Shadow comparison counts do not conserve shadow_wakes")
        if (
            self.both
            + self.scanner_only
            + self.shadow_only
            + self.neither
            + self.unavailable
            != self.scanner_evaluations
        ):
            raise ValueError("comparison counts must conserve Scanner evaluations")
        if self.unavailable != self.analytics_unmatched:
            raise ValueError("unavailable must equal analytics_unmatched")
        if (
            self.unavailable_scanner_wakes + self.unavailable_scanner_sleeps
            != self.unavailable
        ):
            raise ValueError("unavailable wake/sleep counts must conserve unavailable")
        return self


class SemanticAttentionReport(FrozenModel):
    schema_version: str = SHADOW_ATTENTION_SEMANTIC_V1_SCHEMA_VERSION
    policy_version: str = SHADOW_ATTENTION_SEMANTIC_V1_POLICY_VERSION
    source_v0_policy_version: str = Field(min_length=1)
    source_backtest_run_id: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    period_role: str = Field(min_length=1)
    summary: SemanticAttentionSummary
    records: tuple[SemanticAttentionObservation, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> SemanticAttentionReport:
        if self.schema_version != SHADOW_ATTENTION_SEMANTIC_V1_SCHEMA_VERSION:
            raise ValueError("unsupported semantic v1 schema_version")
        if self.policy_version != SHADOW_ATTENTION_SEMANTIC_V1_POLICY_VERSION:
            raise ValueError("unsupported semantic v1 policy_version")
        if self.period_role not in {"DESIGN", "VALIDATION", "OOS"}:
            raise ValueError("period_role must be DESIGN, VALIDATION or OOS")
        if len(self.records) != self.summary.scanner_evaluations:
            raise ValueError("records must conserve scanner_evaluations")
        ordered = tuple(
            sorted(
                self.records,
                key=lambda item: (item.observed_at, item.scanner_evaluation_id),
            )
        )
        if ordered != self.records:
            raise ValueError("records must be deterministically sorted")
        return self

    def to_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


def _pattern_status(reason: ShadowAttentionReason) -> str:
    key = reason.key.strip().upper()
    return key.rsplit(":", maxsplit=1)[-1] if ":" in key else key


def _semantic_clauses(
    reasons: tuple[ShadowAttentionReason, ...],
) -> tuple[SemanticAttentionClause, ...]:
    technical = tuple(
        reason
        for reason in reasons
        if reason.kind is ShadowAttentionReasonKind.TECHNICAL_EVENT
    )
    technical_families = {
        str(reason.metadata.get("family", "")).strip().upper()
        for reason in technical
        if str(reason.metadata.get("family", "")).strip()
    }
    has_zigzag = any(
        reason.kind is ShadowAttentionReasonKind.ZIGZAG_CONFIRMATION
        for reason in reasons
    )
    has_mature_pattern = any(
        reason.kind is ShadowAttentionReasonKind.PATTERN_TRANSITION
        and _pattern_status(reason) in MATURE_PATTERN_STATUSES
        for reason in reasons
    )

    clauses: list[SemanticAttentionClause] = []
    if len(technical_families) >= 2:
        clauses.append(SemanticAttentionClause.DIVERSE_TECHNICAL_FAMILIES)
    if technical and has_zigzag:
        clauses.append(SemanticAttentionClause.TECHNICAL_PLUS_ZIGZAG)
    if has_mature_pattern:
        clauses.append(SemanticAttentionClause.MATURE_PATTERN_TRANSITION)
    return tuple(sorted(clauses, key=lambda item: item.value))


def _comparison(
    *,
    matched: bool,
    scanner_wake: bool,
    shadow_wake: bool,
) -> ShadowAttentionComparison:
    if not matched:
        return ShadowAttentionComparison.UNAVAILABLE
    if scanner_wake and shadow_wake:
        return ShadowAttentionComparison.BOTH
    if scanner_wake:
        return ShadowAttentionComparison.SCANNER_ONLY
    if shadow_wake:
        return ShadowAttentionComparison.SHADOW_ONLY
    return ShadowAttentionComparison.NEITHER


def build_semantic_attention_v1_report(
    source: ShadowAttentionReport,
) -> SemanticAttentionReport:
    """Freeze the semantic v1 candidate over an existing exact-join v0 report.

    This remains observation-only. No outcome, price direction, Scanner score,
    persistent state or trading authority enters the wake decision.
    """

    records: list[SemanticAttentionObservation] = []
    clause_counts: Counter[SemanticAttentionClause] = Counter()

    for item in source.records:
        clauses: tuple[SemanticAttentionClause, ...] = ()
        reasons: tuple[ShadowAttentionReason, ...] = ()
        if item.analytics_matched:
            clauses = _semantic_clauses(item.reasons)
            if clauses:
                reasons = item.reasons
        shadow_wake = bool(clauses)
        for clause in clauses:
            clause_counts[clause] += 1

        identity = {
            "policy": SHADOW_ATTENTION_SEMANTIC_V1_POLICY_VERSION,
            "source_v0_observation_id": item.observation_id,
            "scanner_evaluation_id": item.scanner_evaluation_id,
            "observed_at": item.observed_at,
            "clauses": tuple(clause.value for clause in clauses),
        }
        records.append(
            SemanticAttentionObservation(
                observation_id=stable_uuid("shadow-attention-semantic-v1", identity),
                source_v0_observation_id=item.observation_id,
                scanner_evaluation_id=item.scanner_evaluation_id,
                observed_at=item.observed_at,
                analytics_matched=item.analytics_matched,
                analytics_snapshot_id=item.analytics_snapshot_id,
                scanner_classification=item.scanner_classification,
                scanner_score=item.scanner_score,
                scanner_triggers=item.scanner_triggers,
                scanner_wake=item.scanner_wake,
                shadow_wake=shadow_wake,
                comparison=_comparison(
                    matched=item.analytics_matched,
                    scanner_wake=item.scanner_wake,
                    shadow_wake=shadow_wake,
                ),
                clauses=clauses,
                reasons=reasons,
            )
        )

    ordered = tuple(
        sorted(
            records,
            key=lambda item: (item.observed_at, item.scanner_evaluation_id),
        )
    )
    comparisons = Counter(item.comparison for item in ordered)
    summary = SemanticAttentionSummary(
        scanner_evaluations=len(ordered),
        analytics_matched=sum(item.analytics_matched for item in ordered),
        analytics_unmatched=sum(not item.analytics_matched for item in ordered),
        scanner_wakes=sum(item.scanner_wake for item in ordered),
        shadow_wakes=sum(item.shadow_wake for item in ordered),
        both=comparisons[ShadowAttentionComparison.BOTH],
        scanner_only=comparisons[ShadowAttentionComparison.SCANNER_ONLY],
        shadow_only=comparisons[ShadowAttentionComparison.SHADOW_ONLY],
        neither=comparisons[ShadowAttentionComparison.NEITHER],
        unavailable=comparisons[ShadowAttentionComparison.UNAVAILABLE],
        unavailable_scanner_wakes=sum(
            item.comparison is ShadowAttentionComparison.UNAVAILABLE and item.scanner_wake
            for item in ordered
        ),
        unavailable_scanner_sleeps=sum(
            item.comparison is ShadowAttentionComparison.UNAVAILABLE and not item.scanner_wake
            for item in ordered
        ),
        diverse_technical_family_wakes=clause_counts[
            SemanticAttentionClause.DIVERSE_TECHNICAL_FAMILIES
        ],
        technical_plus_zigzag_wakes=clause_counts[
            SemanticAttentionClause.TECHNICAL_PLUS_ZIGZAG
        ],
        mature_pattern_transition_wakes=clause_counts[
            SemanticAttentionClause.MATURE_PATTERN_TRANSITION
        ],
        multi_clause_wakes=sum(len(item.clauses) >= 2 for item in ordered),
    )
    return SemanticAttentionReport(
        source_v0_policy_version=source.policy_version,
        source_backtest_run_id=source.source_backtest_run_id,
        analytics_run_id=source.analytics_run_id,
        period_role=source.period_role,
        summary=summary,
        records=ordered,
    )


def semantic_attention_v1_export_name(period_role: str) -> str:
    normalized = str(getattr(period_role, "value", period_role)).strip().lower()
    if normalized not in {"design", "validation", "oos"}:
        raise ValueError("period_role must be DESIGN, VALIDATION or OOS")
    return f"shadow-attention-semantic-v1-{normalized}.json"


__all__ = [
    "MATURE_PATTERN_STATUSES",
    "SHADOW_ATTENTION_SEMANTIC_V1_POLICY_VERSION",
    "SHADOW_ATTENTION_SEMANTIC_V1_SCHEMA_VERSION",
    "SemanticAttentionClause",
    "SemanticAttentionObservation",
    "SemanticAttentionReport",
    "SemanticAttentionSummary",
    "build_semantic_attention_v1_report",
    "semantic_attention_v1_export_name",
]
