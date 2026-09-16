from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evaluation.forward_outcomes import (
    ForwardOutcomeHorizon,
    ForwardOutcomeHorizonSummary,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScannerOutcomeClassification(StrEnum):
    NO_TRIGGER = "NO_TRIGGER"
    TRIGGER_BELOW_CANDIDATE_THRESHOLD = "TRIGGER_BELOW_CANDIDATE_THRESHOLD"
    CANDIDATE_OPPORTUNITY = "CANDIDATE_OPPORTUNITY"


class ScannerOutcomeGroupDimension(StrEnum):
    CLASSIFICATION = "CLASSIFICATION"
    SCORE = "SCORE"
    TRIGGER = "TRIGGER"
    MARKET_REGIME = "MARKET_REGIME"


class ScannerForwardOutcomeReference(FrozenModel):
    scan_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    observed_at: datetime
    reference_close: Decimal = Field(gt=0)
    classification: ScannerOutcomeClassification
    score: int = Field(ge=0, le=100)
    min_priority_score: int = Field(ge=0, le=100)
    score_margin_to_threshold: int = Field(ge=-100, le=100)
    triggers: tuple[str, ...] = ()
    market_regime: str | None = None
    candidate_opportunity_id: str | None = None

    @model_validator(mode="after")
    def validate_scanner_contract(self) -> ScannerForwardOutcomeReference:
        if tuple(sorted(set(self.triggers))) != self.triggers:
            raise ValueError("triggers must be sorted and unique")
        if self.score_margin_to_threshold != self.score - self.min_priority_score:
            raise ValueError("score_margin_to_threshold must equal score - threshold")

        if self.classification is ScannerOutcomeClassification.NO_TRIGGER:
            if self.triggers:
                raise ValueError("NO_TRIGGER cannot contain triggers")
            if self.candidate_opportunity_id is not None:
                raise ValueError("NO_TRIGGER cannot contain a candidate opportunity")
        elif (
            self.classification
            is ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD
        ):
            if not self.triggers:
                raise ValueError("below-threshold classification requires triggers")
            if self.candidate_opportunity_id is not None:
                raise ValueError(
                    "below-threshold classification cannot contain a candidate"
                )
            if self.score >= self.min_priority_score:
                raise ValueError(
                    "below-threshold classification requires score < threshold"
                )
        else:
            if not self.triggers:
                raise ValueError("candidate classification requires triggers")
            if self.candidate_opportunity_id is None:
                raise ValueError("candidate classification requires opportunity id")
            if self.score < self.min_priority_score:
                raise ValueError(
                    "candidate classification requires score >= threshold"
                )
        return self


class ScannerForwardOutcomeRecord(ScannerForwardOutcomeReference):
    horizons: tuple[ForwardOutcomeHorizon, ...]

    @model_validator(mode="after")
    def validate_horizons(self) -> ScannerForwardOutcomeRecord:
        ordered = tuple(sorted(self.horizons, key=lambda item: item.horizon_bars))
        if ordered != self.horizons:
            raise ValueError("horizons must be sorted")
        if len({item.horizon_bars for item in self.horizons}) != len(self.horizons):
            raise ValueError("horizons must be unique")
        return self


class ScannerOutcomeHorizonStats(FrozenModel):
    horizon_bars: int = Field(gt=0)
    scanner_evaluation_count: int = Field(ge=0)
    complete_count: int = Field(ge=0)
    incomplete_count: int = Field(ge=0)
    raw_return_mean_pct: Decimal | None = None
    raw_return_median_pct: Decimal | None = None
    raw_positive_count: int = Field(ge=0)
    raw_negative_count: int = Field(ge=0)
    raw_flat_count: int = Field(ge=0)
    max_upside_mean_pct: Decimal | None = None
    max_upside_median_pct: Decimal | None = None
    max_downside_mean_pct: Decimal | None = None
    max_downside_median_pct: Decimal | None = None
    first_hit_upside_count: int = Field(ge=0)
    first_hit_downside_count: int = Field(ge=0)
    first_hit_same_candle_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> ScannerOutcomeHorizonStats:
        if self.complete_count + self.incomplete_count != self.scanner_evaluation_count:
            raise ValueError(
                "complete + incomplete must equal scanner_evaluation_count"
            )
        if (
            self.raw_positive_count
            + self.raw_negative_count
            + self.raw_flat_count
            != self.complete_count
        ):
            raise ValueError("raw sign counts must equal complete_count")
        if (
            self.first_hit_upside_count
            + self.first_hit_downside_count
            + self.first_hit_same_candle_count
            != self.complete_count
        ):
            raise ValueError("first-hit counts must equal complete_count")
        metrics = (
            self.raw_return_mean_pct,
            self.raw_return_median_pct,
            self.max_upside_mean_pct,
            self.max_upside_median_pct,
            self.max_downside_mean_pct,
            self.max_downside_median_pct,
        )
        if self.complete_count == 0 and any(item is not None for item in metrics):
            raise ValueError("price statistics require complete outcomes")
        if self.complete_count > 0 and any(item is None for item in metrics):
            raise ValueError("complete outcomes require all price statistics")
        return self


class ScannerOutcomeGroup(FrozenModel):
    dimension: ScannerOutcomeGroupDimension
    key: str = Field(min_length=1)
    scanner_evaluation_count: int = Field(ge=1)
    horizons: tuple[ScannerOutcomeHorizonStats, ...]

    @model_validator(mode="after")
    def validate_horizons(self) -> ScannerOutcomeGroup:
        ordered = tuple(sorted(self.horizons, key=lambda item: item.horizon_bars))
        if ordered != self.horizons:
            raise ValueError("group horizons must be sorted")
        if len({item.horizon_bars for item in self.horizons}) != len(self.horizons):
            raise ValueError("group horizons must be unique")
        if any(
            item.scanner_evaluation_count != self.scanner_evaluation_count
            for item in self.horizons
        ):
            raise ValueError("group horizon counts must match group count")
        return self


class ScannerOutcomeDimensionCoverage(FrozenModel):
    dimension: ScannerOutcomeGroupDimension
    represented_scanner_evaluations: int = Field(ge=0)
    missing_scanner_evaluations: int = Field(ge=0)
    group_count: int = Field(ge=0)
    multi_valued: bool = False


class ScannerForwardOutcomeSummary(FrozenModel):
    scanner_evaluations: int = Field(ge=0)
    no_trigger: int = Field(ge=0)
    trigger_below_candidate_threshold: int = Field(ge=0)
    candidate_opportunities: int = Field(ge=0)
    horizon_counts: tuple[ForwardOutcomeHorizonSummary, ...] = ()

    @model_validator(mode="after")
    def validate_conservation(self) -> ScannerForwardOutcomeSummary:
        if (
            self.no_trigger
            + self.trigger_below_candidate_threshold
            + self.candidate_opportunities
            != self.scanner_evaluations
        ):
            raise ValueError(
                "scanner classifications must conserve scanner_evaluations"
            )
        for item in self.horizon_counts:
            if item.complete + item.incomplete != self.scanner_evaluations:
                raise ValueError(
                    "horizon summary must conserve scanner_evaluations"
                )
        return self


class ScannerForwardOutcomeReport(FrozenModel):
    schema_version: str = "money-heist.scanner-forward-outcomes.v1"
    policy_version: str = "money-heist.scanner-forward-outcomes.close-ohlc.v1"
    run_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    dataset_content_sha256: str = Field(min_length=64, max_length=64)
    dataset_source: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    scanner_version: str = Field(min_length=1)
    min_priority_score: int = Field(ge=0, le=100)
    source_timeframe: str = Field(min_length=1)
    decision_timeframe: str = Field(min_length=1)
    period_start: datetime
    period_end: datetime
    horizons: tuple[int, ...]
    summary: ScannerForwardOutcomeSummary
    dimension_coverage: tuple[ScannerOutcomeDimensionCoverage, ...]
    records: tuple[ScannerForwardOutcomeRecord, ...]
    groups: tuple[ScannerOutcomeGroup, ...]

    @model_validator(mode="after")
    def validate_report(self) -> ScannerForwardOutcomeReport:
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot precede period_start")
        if not self.horizons or tuple(sorted(set(self.horizons))) != self.horizons:
            raise ValueError("horizons must be sorted, unique and non-empty")
        if len(self.records) != self.summary.scanner_evaluations:
            raise ValueError("records must conserve scanner_evaluations")
        scan_ids = tuple(item.scan_id for item in self.records)
        if len(set(scan_ids)) != len(scan_ids):
            raise ValueError("scan_id values must be unique")
        ordered_records = tuple(
            sorted(self.records, key=lambda item: (item.observed_at, item.scan_id))
        )
        if self.records != ordered_records:
            raise ValueError("records must be sorted deterministically")
        if any(item.min_priority_score != self.min_priority_score for item in self.records):
            raise ValueError("all records must use report min_priority_score")
        for record in self.records:
            if tuple(item.horizon_bars for item in record.horizons) != self.horizons:
                raise ValueError("every record must expose report horizons")
        expected_coverage = tuple(
            sorted(self.dimension_coverage, key=lambda item: item.dimension.value)
        )
        if self.dimension_coverage != expected_coverage:
            raise ValueError("dimension_coverage must be sorted deterministically")
        expected_groups = tuple(
            sorted(self.groups, key=lambda item: (item.dimension.value, item.key))
        )
        if self.groups != expected_groups:
            raise ValueError("groups must be sorted deterministically")
        for group in self.groups:
            if tuple(item.horizon_bars for item in group.horizons) != self.horizons:
                raise ValueError("every group must expose report horizons")
        return self
