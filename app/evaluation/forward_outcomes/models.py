from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ForwardOutcomeFirstHit(StrEnum):
    MAX_UPSIDE = "MAX_UPSIDE"
    MAX_DOWNSIDE = "MAX_DOWNSIDE"
    SAME_CANDLE = "SAME_CANDLE"
    NONE = "NONE"


class ForwardOutcomeIncompleteReason(StrEnum):
    GAP = "GAP"
    PERIOD_END = "PERIOD_END"
    GAP_AND_PERIOD_END = "GAP_AND_PERIOD_END"


class ForwardOutcomeReference(FrozenModel):
    opportunity_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    observed_at: datetime
    reference_close: Decimal = Field(gt=0)
    terminal_status: str = Field(min_length=1)
    professor_direction: str | None = None
    proposal_side: str | None = None


class ForwardOutcomeHorizon(FrozenModel):
    horizon_bars: int = Field(gt=0)
    is_complete: bool
    bars_observed: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    boundary_missing_bars: int = Field(ge=0)
    missing_close_times: tuple[datetime, ...] = ()
    expected_end_at: datetime
    return_pct: Decimal | None = None
    max_upside_pct: Decimal | None = None
    max_downside_pct: Decimal | None = None
    max_upside_at: datetime | None = None
    max_downside_at: datetime | None = None
    first_hit: ForwardOutcomeFirstHit = ForwardOutcomeFirstHit.NONE
    first_hit_at: datetime | None = None
    incomplete_reason: ForwardOutcomeIncompleteReason | None = None

    @model_validator(mode="after")
    def validate_completeness(self) -> ForwardOutcomeHorizon:
        if self.bars_observed > self.horizon_bars:
            raise ValueError("bars_observed cannot exceed horizon_bars")
        if self.gap_count != len(self.missing_close_times):
            raise ValueError("gap_count must match missing_close_times")
        if self.is_complete:
            if self.bars_observed != self.horizon_bars:
                raise ValueError("complete horizon must observe every bar")
            if self.gap_count or self.boundary_missing_bars:
                raise ValueError("complete horizon cannot contain missing bars")
            if self.incomplete_reason is not None:
                raise ValueError("complete horizon cannot have incomplete_reason")
            required = (
                self.return_pct,
                self.max_upside_pct,
                self.max_downside_pct,
                self.max_upside_at,
                self.max_downside_at,
                self.first_hit_at,
            )
            if any(item is None for item in required):
                raise ValueError("complete horizon requires all price outcome fields")
            if self.first_hit is ForwardOutcomeFirstHit.NONE:
                raise ValueError("complete horizon requires first_hit")
        else:
            metrics = (
                self.return_pct,
                self.max_upside_pct,
                self.max_downside_pct,
                self.max_upside_at,
                self.max_downside_at,
                self.first_hit_at,
            )
            if any(item is not None for item in metrics):
                raise ValueError("incomplete horizon must not publish partial price metrics")
            if self.first_hit is not ForwardOutcomeFirstHit.NONE:
                raise ValueError("incomplete horizon first_hit must be NONE")
            if self.incomplete_reason is None:
                raise ValueError("incomplete horizon requires incomplete_reason")
        return self


class ForwardOutcomeRecord(FrozenModel):
    opportunity_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    observed_at: datetime
    reference_close: Decimal = Field(gt=0)
    terminal_status: str = Field(min_length=1)
    professor_direction: str | None = None
    proposal_side: str | None = None
    horizons: tuple[ForwardOutcomeHorizon, ...]

    @model_validator(mode="after")
    def validate_horizon_order(self) -> ForwardOutcomeRecord:
        ordered = tuple(sorted(self.horizons, key=lambda item: item.horizon_bars))
        if self.horizons != ordered:
            raise ValueError("horizons must be sorted")
        if len({item.horizon_bars for item in self.horizons}) != len(self.horizons):
            raise ValueError("horizons must be unique")
        return self


class ForwardOutcomeStatusCount(FrozenModel):
    status: str = Field(min_length=1)
    count: int = Field(ge=1)


class ForwardOutcomeHorizonSummary(FrozenModel):
    horizon_bars: int = Field(gt=0)
    complete: int = Field(ge=0)
    incomplete: int = Field(ge=0)
    with_gaps: int = Field(ge=0)


class ForwardOutcomeSummary(FrozenModel):
    opportunity_count: int = Field(ge=0)
    status_counts: tuple[ForwardOutcomeStatusCount, ...] = ()
    horizon_counts: tuple[ForwardOutcomeHorizonSummary, ...] = ()

    @model_validator(mode="after")
    def validate_summary(self) -> ForwardOutcomeSummary:
        if sum(item.count for item in self.status_counts) != self.opportunity_count:
            raise ValueError("status_counts must conserve opportunity_count")
        for item in self.horizon_counts:
            if item.complete + item.incomplete != self.opportunity_count:
                raise ValueError("horizon summary must conserve opportunity_count")
            if item.with_gaps > item.incomplete:
                raise ValueError("with_gaps cannot exceed incomplete")
        return self


class ForwardOutcomeReport(FrozenModel):
    schema_version: str = "money-heist.forward-outcomes.v1"
    policy_version: str = "money-heist.forward-outcomes.close-ohlc.v1"
    run_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    dataset_content_sha256: str = Field(min_length=64, max_length=64)
    dataset_source: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    source_timeframe: str = Field(min_length=1)
    decision_timeframe: str = Field(min_length=1)
    period_start: datetime
    period_end: datetime
    horizons: tuple[int, ...]
    summary: ForwardOutcomeSummary
    records: tuple[ForwardOutcomeRecord, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> ForwardOutcomeReport:
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot precede period_start")
        if not self.horizons or any(item <= 0 for item in self.horizons):
            raise ValueError("horizons must contain positive bar counts")
        if tuple(sorted(set(self.horizons))) != self.horizons:
            raise ValueError("horizons must be sorted and unique")
        ordered = tuple(
            sorted(self.records, key=lambda item: (item.observed_at, item.opportunity_id))
        )
        if self.records != ordered:
            raise ValueError("records must be sorted deterministically")
        if len(self.records) != self.summary.opportunity_count:
            raise ValueError("records must conserve summary opportunity_count")
        for record in self.records:
            if tuple(item.horizon_bars for item in record.horizons) != self.horizons:
                raise ValueError("every record must expose the report horizons")
        return self
