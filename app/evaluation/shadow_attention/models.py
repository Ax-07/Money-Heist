from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHADOW_ATTENTION_SCHEMA_VERSION = "money-heist.shadow-attention-report.v0"
SHADOW_ATTENTION_POLICY_VERSION = "shadow-attention-observation-only-v0"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class ShadowAttentionReasonKind(StrEnum):
    TECHNICAL_EVENT = "TECHNICAL_EVENT"
    ZIGZAG_CONFIRMATION = "ZIGZAG_CONFIRMATION"
    PATTERN_TRANSITION = "PATTERN_TRANSITION"


class ShadowAttentionComparison(StrEnum):
    BOTH = "BOTH"
    SCANNER_ONLY = "SCANNER_ONLY"
    SHADOW_ONLY = "SHADOW_ONLY"
    NEITHER = "NEITHER"
    UNAVAILABLE = "UNAVAILABLE"


class ShadowAttentionReason(FrozenModel):
    kind: ShadowAttentionReasonKind
    key: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    available_at: datetime
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("available_at")
    @classmethod
    def normalize_available_at(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_metadata(self) -> ShadowAttentionReason:
        invalid_metadata = any(
            not str(key).strip() or not str(value).strip()
            for key, value in self.metadata.items()
        )
        if invalid_metadata:
            raise ValueError("reason metadata keys and values must not be blank")
        return self


class ShadowAttentionObservation(FrozenModel):
    observation_id: str = Field(min_length=1)
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
    reasons: tuple[ShadowAttentionReason, ...] = ()

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_contract(self) -> ShadowAttentionObservation:
        if tuple(sorted(set(self.scanner_triggers))) != self.scanner_triggers:
            raise ValueError("scanner_triggers must be sorted and unique")
        if self.analytics_matched != (self.analytics_snapshot_id is not None):
            raise ValueError("analytics_matched must agree with analytics_snapshot_id")
        ordered = tuple(
            sorted(
                self.reasons,
                key=lambda item: (item.kind.value, item.key, item.source_id),
            )
        )
        if ordered != self.reasons:
            raise ValueError("reasons must be deterministically sorted")
        if self.shadow_wake != bool(self.reasons):
            raise ValueError("shadow_wake must equal bool(reasons)")
        if not self.analytics_matched:
            if self.reasons or self.shadow_wake:
                raise ValueError("unmatched Analytics cannot wake Shadow Attention")
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


class ShadowAttentionSummary(FrozenModel):
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
    technical_event_wakes: int = Field(ge=0)
    zigzag_confirmation_wakes: int = Field(ge=0)
    pattern_transition_wakes: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_conservation(self) -> ShadowAttentionSummary:
        if self.analytics_matched + self.analytics_unmatched != self.scanner_evaluations:
            raise ValueError("Analytics coverage must conserve Scanner evaluations")
        if (
            self.both
            + self.scanner_only
            + self.unavailable_scanner_wakes
            != self.scanner_wakes
        ):
            raise ValueError("Scanner wake comparison counts do not conserve scanner_wakes")
        if self.both + self.shadow_only != self.shadow_wakes:
            raise ValueError("Shadow wake comparison counts do not conserve shadow_wakes")
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
            raise ValueError(
                "unavailable Scanner wake/sleep counts must conserve unavailable"
            )
        return self


class ShadowAttentionReport(FrozenModel):
    schema_version: str = SHADOW_ATTENTION_SCHEMA_VERSION
    policy_version: str = SHADOW_ATTENTION_POLICY_VERSION
    source_backtest_run_id: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    period_role: str = Field(min_length=1)
    summary: ShadowAttentionSummary
    records: tuple[ShadowAttentionObservation, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> ShadowAttentionReport:
        if self.schema_version != SHADOW_ATTENTION_SCHEMA_VERSION:
            raise ValueError("unsupported Shadow Attention schema_version")
        if self.policy_version != SHADOW_ATTENTION_POLICY_VERSION:
            raise ValueError("unsupported Shadow Attention policy_version")
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
        ids = tuple(item.scanner_evaluation_id for item in self.records)
        if len(set(ids)) != len(ids):
            raise ValueError("Scanner evaluations must be unique")
        return self

    def to_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
