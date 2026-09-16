from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FunnelAttributionDimension(StrEnum):
    TERMINAL_STATUS = "TERMINAL_STATUS"
    MARKET_REGIME = "MARKET_REGIME"
    SCANNER_TRIGGER = "SCANNER_TRIGGER"
    COMPUTE_GATE_REASON = "COMPUTE_GATE_REASON"
    PROFESSOR_PLAN_DECISION = "PROFESSOR_PLAN_DECISION"
    SELECTED_AGENT = "SELECTED_AGENT"
    ORCHESTRATION_FAILURE = "ORCHESTRATION_FAILURE"
    PROFESSOR_DIRECTION = "PROFESSOR_DIRECTION"
    PROPOSAL_SIDE = "PROPOSAL_SIDE"
    RISK_STATUS = "RISK_STATUS"
    RISK_REASON = "RISK_REASON"
    PAPER_PIPELINE_FAILURE = "PAPER_PIPELINE_FAILURE"


class FunnelOutcomeSubject(FrozenModel):
    opportunity_id: str = Field(min_length=1)
    observed_at: datetime
    terminal_status: str = Field(min_length=1)
    market_regime: str | None = None
    scanner_triggers: tuple[str, ...] = ()
    compute_gate_reason: str | None = None
    professor_plan_decision: str | None = None
    selected_agents: tuple[str, ...] = ()
    orchestration_failure_code: str | None = None
    professor_direction: str | None = None
    proposal_side: str | None = None
    risk_status: str | None = None
    risk_reason_codes: tuple[str, ...] = ()
    paper_pipeline_failure_code: str | None = None

    @model_validator(mode="after")
    def validate_multi_values(self) -> FunnelOutcomeSubject:
        for field_name in ("scanner_triggers", "selected_agents", "risk_reason_codes"):
            values = getattr(self, field_name)
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"{field_name} must be sorted and unique")
        return self


class FunnelOutcomeHorizonStats(FrozenModel):
    horizon_bars: int = Field(gt=0)
    opportunity_count: int = Field(ge=0)
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
    directional_count: int = Field(ge=0)
    directional_return_mean_pct: Decimal | None = None
    directional_return_median_pct: Decimal | None = None
    directional_positive_count: int = Field(ge=0)
    directional_negative_count: int = Field(ge=0)
    directional_flat_count: int = Field(ge=0)
    favorable_excursion_mean_pct: Decimal | None = None
    favorable_excursion_median_pct: Decimal | None = None
    adverse_excursion_mean_pct: Decimal | None = None
    adverse_excursion_median_pct: Decimal | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> FunnelOutcomeHorizonStats:
        if self.complete_count + self.incomplete_count != self.opportunity_count:
            raise ValueError("complete + incomplete must equal opportunity_count")
        if (
            self.raw_positive_count
            + self.raw_negative_count
            + self.raw_flat_count
            != self.complete_count
        ):
            raise ValueError("raw sign counts must equal complete_count")
        if self.directional_count > self.complete_count:
            raise ValueError("directional_count cannot exceed complete_count")
        if (
            self.directional_positive_count
            + self.directional_negative_count
            + self.directional_flat_count
            != self.directional_count
        ):
            raise ValueError("directional sign counts must equal directional_count")
        raw_metrics = (
            self.raw_return_mean_pct,
            self.raw_return_median_pct,
            self.max_upside_mean_pct,
            self.max_upside_median_pct,
            self.max_downside_mean_pct,
            self.max_downside_median_pct,
        )
        if self.complete_count == 0 and any(item is not None for item in raw_metrics):
            raise ValueError("raw metrics require at least one complete outcome")
        if self.complete_count > 0 and any(item is None for item in raw_metrics):
            raise ValueError("complete outcomes require all raw aggregate metrics")
        directional_metrics = (
            self.directional_return_mean_pct,
            self.directional_return_median_pct,
            self.favorable_excursion_mean_pct,
            self.favorable_excursion_median_pct,
            self.adverse_excursion_mean_pct,
            self.adverse_excursion_median_pct,
        )
        if self.directional_count == 0 and any(
            item is not None for item in directional_metrics
        ):
            raise ValueError("directional metrics require directional samples")
        if self.directional_count > 0 and any(
            item is None for item in directional_metrics
        ):
            raise ValueError("directional samples require all directional metrics")
        return self


class FunnelOutcomeGroup(FrozenModel):
    dimension: FunnelAttributionDimension
    key: str = Field(min_length=1)
    opportunity_count: int = Field(ge=1)
    horizons: tuple[FunnelOutcomeHorizonStats, ...]

    @model_validator(mode="after")
    def validate_horizons(self) -> FunnelOutcomeGroup:
        ordered = tuple(sorted(self.horizons, key=lambda item: item.horizon_bars))
        if ordered != self.horizons:
            raise ValueError("group horizons must be sorted")
        if len({item.horizon_bars for item in self.horizons}) != len(self.horizons):
            raise ValueError("group horizons must be unique")
        if any(item.opportunity_count != self.opportunity_count for item in self.horizons):
            raise ValueError("group horizon opportunity_count must match group")
        return self


class FunnelOutcomeDimensionCoverage(FrozenModel):
    dimension: FunnelAttributionDimension
    represented_opportunities: int = Field(ge=0)
    missing_opportunities: int = Field(ge=0)
    group_count: int = Field(ge=0)
    multi_valued: bool = False

    @model_validator(mode="after")
    def validate_total(self) -> FunnelOutcomeDimensionCoverage:
        if self.group_count == 0 and self.represented_opportunities != 0:
            raise ValueError("represented opportunities require at least one group")
        return self


class FunnelOutcomeAttributionCoverage(FrozenModel):
    candidate_opportunities: int = Field(ge=0)
    forward_outcome_records: int = Field(ge=0)
    scanner_no_trigger_outcomes_available: bool = False
    scanner_below_candidate_threshold_outcomes_available: bool = False

    @model_validator(mode="after")
    def validate_candidate_coverage(self) -> FunnelOutcomeAttributionCoverage:
        if self.forward_outcome_records != self.candidate_opportunities:
            raise ValueError(
                "Batch 23A.3 requires one Forward Outcome per CandidateOpportunity"
            )
        return self


class FunnelOutcomeAttributionReport(FrozenModel):
    schema_version: str = "money-heist.funnel-outcome-attribution.v1"
    policy_version: str = "money-heist.funnel-outcome-attribution.descriptive.v1"
    run_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    period_start: datetime
    period_end: datetime
    horizons: tuple[int, ...]
    coverage: FunnelOutcomeAttributionCoverage
    dimension_coverage: tuple[FunnelOutcomeDimensionCoverage, ...]
    subjects: tuple[FunnelOutcomeSubject, ...]
    groups: tuple[FunnelOutcomeGroup, ...]

    @model_validator(mode="after")
    def validate_report(self) -> FunnelOutcomeAttributionReport:
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot precede period_start")
        if tuple(sorted(set(self.horizons))) != self.horizons:
            raise ValueError("horizons must be sorted and unique")
        if len(self.subjects) != self.coverage.candidate_opportunities:
            raise ValueError("subjects must conserve candidate_opportunities")
        subject_ids = tuple(item.opportunity_id for item in self.subjects)
        if len(set(subject_ids)) != len(subject_ids):
            raise ValueError("subjects must contain unique opportunity ids")
        ordered_subjects = tuple(
            sorted(self.subjects, key=lambda item: (item.observed_at, item.opportunity_id))
        )
        if self.subjects != ordered_subjects:
            raise ValueError("subjects must be sorted deterministically")
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
        terminal = next(
            (
                item
                for item in self.dimension_coverage
                if item.dimension is FunnelAttributionDimension.TERMINAL_STATUS
            ),
            None,
        )
        if terminal is None:
            raise ValueError("TERMINAL_STATUS coverage is required")
        if (
            terminal.represented_opportunities
            != self.coverage.candidate_opportunities
            or terminal.missing_opportunities != 0
        ):
            raise ValueError("TERMINAL_STATUS must cover every candidate")
        for group in self.groups:
            if tuple(item.horizon_bars for item in group.horizons) != self.horizons:
                raise ValueError("every group must expose report horizons")
        return self
