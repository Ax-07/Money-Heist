from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from decimal import Decimal
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.canonical import canonical_json, stable_digest, stable_uuid
from app.evaluation.forward_outcomes.models import (
    ForwardOutcomeFirstHit,
    ForwardOutcomeHorizon,
    ForwardOutcomeIncompleteReason,
)

from .models import (
    DECISION_QUALITY_RESEARCH_BUNDLE_SCHEMA_VERSION,
    DECISION_QUALITY_RESEARCH_HORIZONS,
    DECISION_QUALITY_RESEARCH_POLICY_VERSION,
    DecisionQualityResearchBundle,
    ScannerResearchRecord,
)

SCANNER_FILTERING_QUALITY_POLICY_VERSION = "scanner-filtering-quality-descriptive-v1"
SCANNER_FILTERING_QUALITY_REPORT_SCHEMA_VERSION = (
    "money-heist.scanner-filtering-quality-report.v1"
)
SCANNER_FILTERING_COHORT_SCHEMA_VERSION = "money-heist.scanner-filtering-cohort.v1"
SCANNER_FILTERING_CONTRAST_SCHEMA_VERSION = "money-heist.scanner-filtering-contrast.v1"

NO_TRIGGER: Final = "NO_TRIGGER"
BELOW_THRESHOLD: Final = "TRIGGER_BELOW_CANDIDATE_THRESHOLD"
CANDIDATE: Final = "CANDIDATE_OPPORTUNITY"
CLASSIFICATIONS: Final = (NO_TRIGGER, BELOW_THRESHOLD, CANDIDATE)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScannerFilteringDimension(StrEnum):
    CLASSIFICATION = "CLASSIFICATION"
    SCORE = "SCORE"
    SCORE_MARGIN = "SCORE_MARGIN"
    TRIGGER = "TRIGGER"
    MARKET_REGIME = "MARKET_REGIME"


class ScannerFilteringContrastKind(StrEnum):
    CANDIDATE_VS_BELOW_THRESHOLD = "CANDIDATE_VS_BELOW_THRESHOLD"
    CANDIDATE_VS_NO_TRIGGER = "CANDIDATE_VS_NO_TRIGGER"
    BELOW_THRESHOLD_VS_NO_TRIGGER = "BELOW_THRESHOLD_VS_NO_TRIGGER"


_DIMENSION_ORDER: Final = {
    ScannerFilteringDimension.CLASSIFICATION: 0,
    ScannerFilteringDimension.SCORE: 1,
    ScannerFilteringDimension.SCORE_MARGIN: 2,
    ScannerFilteringDimension.TRIGGER: 3,
    ScannerFilteringDimension.MARKET_REGIME: 4,
}
_CONTRAST_PAIRS: Final = (
    (
        ScannerFilteringContrastKind.CANDIDATE_VS_BELOW_THRESHOLD,
        CANDIDATE,
        BELOW_THRESHOLD,
    ),
    (
        ScannerFilteringContrastKind.CANDIDATE_VS_NO_TRIGGER,
        CANDIDATE,
        NO_TRIGGER,
    ),
    (
        ScannerFilteringContrastKind.BELOW_THRESHOLD_VS_NO_TRIGGER,
        BELOW_THRESHOLD,
        NO_TRIGGER,
    ),
)


class ScannerFilteringClassificationSummary(FrozenModel):
    scanner_count: int = Field(ge=0)
    no_trigger_count: int = Field(ge=0)
    below_threshold_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    triggered_count: int = Field(ge=0)
    no_trigger_rate: Decimal | None = None
    below_threshold_rate: Decimal | None = None
    candidate_rate: Decimal | None = None

    @model_validator(mode="after")
    def validate_conservation(self) -> ScannerFilteringClassificationSummary:
        if (
            self.no_trigger_count + self.below_threshold_count + self.candidate_count
            != self.scanner_count
        ):
            raise ValueError("Scanner classifications must conserve scanner_count")
        if self.triggered_count != self.below_threshold_count + self.candidate_count:
            raise ValueError("triggered_count must equal below_threshold + candidate")
        expected_rates = (
            _rate(self.no_trigger_count, self.scanner_count),
            _rate(self.below_threshold_count, self.scanner_count),
            _rate(self.candidate_count, self.scanner_count),
        )
        if (
            self.no_trigger_rate,
            self.below_threshold_rate,
            self.candidate_rate,
        ) != expected_rates:
            raise ValueError("classification rates do not match raw counts")
        return self


class ScannerFilteringHorizonStats(FrozenModel):
    horizon_bars: int = Field(gt=0)
    scanner_count: int = Field(ge=0)
    outcome_available_count: int = Field(ge=0)
    outcome_missing_count: int = Field(ge=0)
    complete_count: int = Field(ge=0)
    incomplete_count: int = Field(ge=0)
    incomplete_gap_count: int = Field(ge=0)
    incomplete_period_end_count: int = Field(ge=0)
    incomplete_gap_and_period_end_count: int = Field(ge=0)
    complete_rate: Decimal | None = None

    raw_return_mean_pct: Decimal | None = None
    raw_return_median_pct: Decimal | None = None
    raw_positive_count: int = Field(ge=0)
    raw_negative_count: int = Field(ge=0)
    raw_flat_count: int = Field(ge=0)
    positive_rate: Decimal | None = None

    max_upside_mean_pct: Decimal | None = None
    max_upside_median_pct: Decimal | None = None
    max_downside_mean_pct: Decimal | None = None
    max_downside_median_pct: Decimal | None = None
    max_absolute_excursion_mean_pct: Decimal | None = None
    max_absolute_excursion_median_pct: Decimal | None = None

    first_hit_upside_count: int = Field(ge=0)
    first_hit_downside_count: int = Field(ge=0)
    first_hit_same_candle_count: int = Field(ge=0)
    first_hit_upside_rate: Decimal | None = None
    first_hit_downside_rate: Decimal | None = None

    @model_validator(mode="after")
    def validate_conservation(self) -> ScannerFilteringHorizonStats:
        if self.outcome_available_count + self.outcome_missing_count != self.scanner_count:
            raise ValueError("outcome availability must conserve scanner_count")
        if self.complete_count + self.incomplete_count != self.outcome_available_count:
            raise ValueError("complete + incomplete must equal outcomes available")
        if (
            self.incomplete_gap_count
            + self.incomplete_period_end_count
            + self.incomplete_gap_and_period_end_count
            != self.incomplete_count
        ):
            raise ValueError("incomplete reason counts must equal incomplete_count")
        if (
            self.raw_positive_count + self.raw_negative_count + self.raw_flat_count
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

        price_metrics = (
            self.raw_return_mean_pct,
            self.raw_return_median_pct,
            self.max_upside_mean_pct,
            self.max_upside_median_pct,
            self.max_downside_mean_pct,
            self.max_downside_median_pct,
            self.max_absolute_excursion_mean_pct,
            self.max_absolute_excursion_median_pct,
        )
        if self.complete_count == 0 and any(value is not None for value in price_metrics):
            raise ValueError("price statistics require complete outcomes")
        if self.complete_count > 0 and any(value is None for value in price_metrics):
            raise ValueError("complete outcomes require every price statistic")

        if self.complete_rate != _rate(self.complete_count, self.outcome_available_count):
            raise ValueError("complete_rate does not match raw counts")
        if self.positive_rate != _rate(self.raw_positive_count, self.complete_count):
            raise ValueError("positive_rate does not match raw counts")
        if self.first_hit_upside_rate != _rate(
            self.first_hit_upside_count, self.complete_count
        ):
            raise ValueError("first_hit_upside_rate does not match raw counts")
        if self.first_hit_downside_rate != _rate(
            self.first_hit_downside_count, self.complete_count
        ):
            raise ValueError("first_hit_downside_rate does not match raw counts")
        return self


class ScannerFilteringCohort(FrozenModel):
    schema_version: str = SCANNER_FILTERING_COHORT_SCHEMA_VERSION
    dimension: ScannerFilteringDimension
    key: str = Field(min_length=1)
    numeric_value: int | None = None
    multi_valued: bool = False
    scanner_count: int = Field(ge=0)
    classification_summary: ScannerFilteringClassificationSummary
    horizons: tuple[ScannerFilteringHorizonStats, ...]
    cohort_fingerprint: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_contract(self) -> ScannerFilteringCohort:
        if self.schema_version != SCANNER_FILTERING_COHORT_SCHEMA_VERSION:
            raise ValueError("unsupported Scanner Filtering cohort schema")
        numeric = self.dimension in {
            ScannerFilteringDimension.SCORE,
            ScannerFilteringDimension.SCORE_MARGIN,
        }
        if numeric and self.numeric_value is None:
            raise ValueError("numeric Scanner dimension requires numeric_value")
        if not numeric and self.numeric_value is not None:
            raise ValueError("non-numeric Scanner dimension cannot carry numeric_value")
        if numeric and self.key != str(self.numeric_value):
            raise ValueError("numeric Scanner group key must match numeric_value")
        if self.multi_valued != (self.dimension is ScannerFilteringDimension.TRIGGER):
            raise ValueError("only TRIGGER is a multi-valued Scanner dimension")
        if self.classification_summary.scanner_count != self.scanner_count:
            raise ValueError("cohort classification summary must conserve scanner_count")
        if tuple(item.horizon_bars for item in self.horizons) != (
            *DECISION_QUALITY_RESEARCH_HORIZONS,
        ):
            raise ValueError("cohort must expose H1/H3/H5/H10/H20")
        if any(item.scanner_count != self.scanner_count for item in self.horizons):
            raise ValueError("cohort horizon scanner_count mismatch")
        return self


class ScannerFilteringDimensionCoverage(FrozenModel):
    dimension: ScannerFilteringDimension
    represented_scanner_count: int = Field(ge=0)
    missing_scanner_count: int = Field(ge=0)
    cohort_count: int = Field(ge=0)
    multi_valued: bool = False

    @model_validator(mode="after")
    def validate_semantics(self) -> ScannerFilteringDimensionCoverage:
        if self.multi_valued != (self.dimension is ScannerFilteringDimension.TRIGGER):
            raise ValueError("only TRIGGER is a multi-valued Scanner dimension")
        return self


class ScannerFilteringCoverageHorizon(FrozenModel):
    horizon_bars: int = Field(gt=0)
    scanner_records: int = Field(ge=0)
    with_future_outcome: int = Field(ge=0)
    without_future_outcome: int = Field(ge=0)
    complete_count: int = Field(ge=0)
    incomplete_count: int = Field(ge=0)
    incomplete_gap_count: int = Field(ge=0)
    incomplete_period_end_count: int = Field(ge=0)
    incomplete_gap_and_period_end_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_conservation(self) -> ScannerFilteringCoverageHorizon:
        if self.with_future_outcome + self.without_future_outcome != self.scanner_records:
            raise ValueError("outcome availability must conserve scanner_records")
        if self.complete_count + self.incomplete_count != self.with_future_outcome:
            raise ValueError("complete + incomplete must equal records with Forward Outcome")
        if (
            self.incomplete_gap_count
            + self.incomplete_period_end_count
            + self.incomplete_gap_and_period_end_count
            != self.incomplete_count
        ):
            raise ValueError("incomplete reason counts must equal incomplete_count")
        return self


class ScannerFilteringCoverage(FrozenModel):
    scanner_records: int = Field(ge=0)
    with_future_outcome: int = Field(ge=0)
    without_future_outcome: int = Field(ge=0)
    with_analytics: int = Field(ge=0)
    without_analytics: int = Field(ge=0)
    horizons: tuple[ScannerFilteringCoverageHorizon, ...]

    @model_validator(mode="after")
    def validate_conservation(self) -> ScannerFilteringCoverage:
        if self.with_future_outcome + self.without_future_outcome != self.scanner_records:
            raise ValueError("future outcome coverage must conserve scanner_records")
        if self.with_analytics + self.without_analytics != self.scanner_records:
            raise ValueError("Analytics coverage must conserve scanner_records")
        if tuple(item.horizon_bars for item in self.horizons) != (
            *DECISION_QUALITY_RESEARCH_HORIZONS,
        ):
            raise ValueError("coverage must expose H1/H3/H5/H10/H20")
        if any(item.scanner_records != self.scanner_records for item in self.horizons):
            raise ValueError("coverage horizon scanner_records mismatch")
        return self


class ScannerFilteringContrastHorizon(FrozenModel):
    horizon_bars: int = Field(gt=0)
    left_scanner_count: int = Field(ge=0)
    right_scanner_count: int = Field(ge=0)
    left_complete_count: int = Field(ge=0)
    right_complete_count: int = Field(ge=0)
    median_raw_return_delta_pct: Decimal | None = None
    median_max_upside_delta_pct: Decimal | None = None
    median_max_downside_delta_pct: Decimal | None = None
    median_max_absolute_excursion_delta_pct: Decimal | None = None
    positive_rate_delta: Decimal | None = None
    first_hit_upside_rate_delta: Decimal | None = None
    first_hit_downside_rate_delta: Decimal | None = None


class ScannerFilteringContrast(FrozenModel):
    schema_version: str = SCANNER_FILTERING_CONTRAST_SCHEMA_VERSION
    kind: ScannerFilteringContrastKind
    left_classification: str = Field(min_length=1)
    right_classification: str = Field(min_length=1)
    horizons: tuple[ScannerFilteringContrastHorizon, ...]

    @model_validator(mode="after")
    def validate_contract(self) -> ScannerFilteringContrast:
        if self.schema_version != SCANNER_FILTERING_CONTRAST_SCHEMA_VERSION:
            raise ValueError("unsupported Scanner Filtering contrast schema")
        if self.left_classification not in CLASSIFICATIONS:
            raise ValueError("unsupported left Scanner classification")
        if self.right_classification not in CLASSIFICATIONS:
            raise ValueError("unsupported right Scanner classification")
        if tuple(item.horizon_bars for item in self.horizons) != (
            *DECISION_QUALITY_RESEARCH_HORIZONS,
        ):
            raise ValueError("contrast must expose H1/H3/H5/H10/H20")
        return self


class ScannerFilteringQualityReport(FrozenModel):
    schema_version: str = SCANNER_FILTERING_QUALITY_REPORT_SCHEMA_VERSION
    policy_version: str = SCANNER_FILTERING_QUALITY_POLICY_VERSION
    report_id: str = Field(min_length=1)
    research_run_id: str = Field(min_length=1)
    source_backtest_run_id: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    period_role: str = Field(min_length=1)
    source_bundle_fingerprint: str = Field(min_length=64, max_length=64)
    scanner_count: int = Field(ge=0)
    classification_summary: ScannerFilteringClassificationSummary
    coverage: ScannerFilteringCoverage
    dimension_coverage: tuple[ScannerFilteringDimensionCoverage, ...]
    cohorts: tuple[ScannerFilteringCohort, ...]
    contrasts: tuple[ScannerFilteringContrast, ...]
    report_fingerprint: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_contract(self) -> ScannerFilteringQualityReport:
        if self.schema_version != SCANNER_FILTERING_QUALITY_REPORT_SCHEMA_VERSION:
            raise ValueError("unsupported Scanner Filtering Quality report schema")
        if self.policy_version != SCANNER_FILTERING_QUALITY_POLICY_VERSION:
            raise ValueError("unsupported Scanner Filtering Quality policy")
        if self.period_role not in {"DESIGN", "VALIDATION", "OOS"}:
            raise ValueError("period_role must be DESIGN, VALIDATION or OOS")
        if self.classification_summary.scanner_count != self.scanner_count:
            raise ValueError("classification summary must conserve scanner_count")
        if self.coverage.scanner_records != self.scanner_count:
            raise ValueError("coverage must conserve scanner_count")
        expected_dimensions = tuple(
            sorted(self.dimension_coverage, key=lambda item: _DIMENSION_ORDER[item.dimension])
        )
        if self.dimension_coverage != expected_dimensions:
            raise ValueError("dimension coverage must use deterministic dimension ordering")
        if tuple(item.dimension for item in self.dimension_coverage) != tuple(
            ScannerFilteringDimension
        ):
            raise ValueError("dimension coverage must expose every v1 dimension exactly once")
        if any(
            item.represented_scanner_count + item.missing_scanner_count != self.scanner_count
            for item in self.dimension_coverage
        ):
            raise ValueError("dimension coverage must conserve scanner_count")
        classification_keys = tuple(
            item.key
            for item in self.cohorts
            if item.dimension is ScannerFilteringDimension.CLASSIFICATION
        )
        if classification_keys != tuple(sorted(CLASSIFICATIONS)):
            raise ValueError("classification cohorts must expose the three canonical cohorts")
        expected_cohorts = tuple(sorted(self.cohorts, key=_cohort_sort_key))
        if self.cohorts != expected_cohorts:
            raise ValueError("cohorts must be deterministically ordered")
        expected_contrasts = tuple(item[0] for item in _CONTRAST_PAIRS)
        if tuple(item.kind for item in self.contrasts) != expected_contrasts:
            raise ValueError("contrasts must use the canonical v1 order")
        return self

    def to_json(self) -> str:
        return canonical_json(self.model_dump(mode="python"))


class ScannerFilteringQualityError(ValueError):
    """Fail-closed input contract error for Scanner Filtering research."""


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, start=Decimal("0")) / Decimal(len(values))


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")


def _max_absolute_excursion(horizon: ForwardOutcomeHorizon) -> Decimal:
    if not horizon.is_complete:
        raise ValueError("max absolute excursion requires a complete horizon")
    if horizon.max_upside_pct is None or horizon.max_downside_pct is None:
        raise ValueError("complete horizon is missing excursion metrics")
    return max(horizon.max_upside_pct, abs(horizon.max_downside_pct))


def _classification_summary(
    records: Iterable[ScannerResearchRecord],
) -> ScannerFilteringClassificationSummary:
    records = tuple(records)
    counts = Counter(item.causal.scanner.classification for item in records)
    unsupported = set(counts) - set(CLASSIFICATIONS)
    if unsupported:
        raise ScannerFilteringQualityError(
            f"unsupported Scanner classifications: {sorted(unsupported)}"
        )
    total = len(records)
    no_trigger = counts[NO_TRIGGER]
    below = counts[BELOW_THRESHOLD]
    candidate = counts[CANDIDATE]
    return ScannerFilteringClassificationSummary(
        scanner_count=total,
        no_trigger_count=no_trigger,
        below_threshold_count=below,
        candidate_count=candidate,
        triggered_count=below + candidate,
        no_trigger_rate=_rate(no_trigger, total),
        below_threshold_rate=_rate(below, total),
        candidate_rate=_rate(candidate, total),
    )


def _validate_bundle(bundle: DecisionQualityResearchBundle) -> None:
    if bundle.schema_version != DECISION_QUALITY_RESEARCH_BUNDLE_SCHEMA_VERSION:
        raise ScannerFilteringQualityError(
            f"unsupported Decision Quality bundle schema: {bundle.schema_version}"
        )
    if bundle.policy_version != DECISION_QUALITY_RESEARCH_POLICY_VERSION:
        raise ScannerFilteringQualityError(
            f"unsupported Decision Quality bundle policy: {bundle.policy_version}"
        )
    if bundle.research_run.policy_version != DECISION_QUALITY_RESEARCH_POLICY_VERSION:
        raise ScannerFilteringQualityError("research run policy is incompatible with 24D.2")

    source = bundle.research_run.source
    for record in bundle.scanner_records:
        if record.research_run_id != bundle.research_run.research_run_id:
            raise ScannerFilteringQualityError("Scanner record research_run_id mismatch")
        if record.period_role != source.period_role:
            raise ScannerFilteringQualityError("Scanner record period_role mismatch")
        outcome = record.posthoc.future_outcome
        if outcome is None:
            continue
        horizons = tuple(item.horizon_bars for item in outcome.horizons)
        if horizons != DECISION_QUALITY_RESEARCH_HORIZONS:
            raise ScannerFilteringQualityError(
                "Scanner Forward Outcome must expose canonical H1/H3/H5/H10/H20"
            )


def _record_horizon(
    record: ScannerResearchRecord,
    horizon_bars: int,
) -> ForwardOutcomeHorizon | None:
    outcome = record.posthoc.future_outcome
    if outcome is None:
        return None
    for horizon in outcome.horizons:
        if horizon.horizon_bars == horizon_bars:
            return horizon
    raise ScannerFilteringQualityError(
        f"Scanner outcome {record.scan_id} is missing H{horizon_bars}"
    )


def _horizon_stats(
    records: tuple[ScannerResearchRecord, ...],
    horizon_bars: int,
) -> ScannerFilteringHorizonStats:
    available: list[ForwardOutcomeHorizon] = []
    for record in records:
        horizon = _record_horizon(record, horizon_bars)
        if horizon is not None:
            available.append(horizon)
    complete = [item for item in available if item.is_complete]
    incomplete = [item for item in available if not item.is_complete]
    incomplete_reasons = Counter(item.incomplete_reason for item in incomplete)

    returns: list[Decimal] = []
    upside: list[Decimal] = []
    downside: list[Decimal] = []
    absolute_excursion: list[Decimal] = []
    for item in complete:
        if (
            item.return_pct is None
            or item.max_upside_pct is None
            or item.max_downside_pct is None
        ):
            raise ScannerFilteringQualityError(
                "complete Scanner Forward Outcome is missing price metrics"
            )
        returns.append(item.return_pct)
        upside.append(item.max_upside_pct)
        downside.append(item.max_downside_pct)
        absolute_excursion.append(_max_absolute_excursion(item))

    positive = sum(value > 0 for value in returns)
    negative = sum(value < 0 for value in returns)
    flat = len(returns) - positive - negative
    first_hits = Counter(item.first_hit for item in complete)
    if first_hits[ForwardOutcomeFirstHit.NONE]:
        raise ScannerFilteringQualityError("complete horizon cannot have first_hit NONE")

    scanner_count = len(records)
    outcome_available = len(available)
    complete_count = len(complete)
    return ScannerFilteringHorizonStats(
        horizon_bars=horizon_bars,
        scanner_count=scanner_count,
        outcome_available_count=outcome_available,
        outcome_missing_count=scanner_count - outcome_available,
        complete_count=complete_count,
        incomplete_count=outcome_available - complete_count,
        incomplete_gap_count=incomplete_reasons[ForwardOutcomeIncompleteReason.GAP],
        incomplete_period_end_count=incomplete_reasons[
            ForwardOutcomeIncompleteReason.PERIOD_END
        ],
        incomplete_gap_and_period_end_count=incomplete_reasons[
            ForwardOutcomeIncompleteReason.GAP_AND_PERIOD_END
        ],
        complete_rate=_rate(complete_count, outcome_available),
        raw_return_mean_pct=_mean(returns),
        raw_return_median_pct=_median(returns),
        raw_positive_count=positive,
        raw_negative_count=negative,
        raw_flat_count=flat,
        positive_rate=_rate(positive, complete_count),
        max_upside_mean_pct=_mean(upside),
        max_upside_median_pct=_median(upside),
        max_downside_mean_pct=_mean(downside),
        max_downside_median_pct=_median(downside),
        max_absolute_excursion_mean_pct=_mean(absolute_excursion),
        max_absolute_excursion_median_pct=_median(absolute_excursion),
        first_hit_upside_count=first_hits[ForwardOutcomeFirstHit.MAX_UPSIDE],
        first_hit_downside_count=first_hits[ForwardOutcomeFirstHit.MAX_DOWNSIDE],
        first_hit_same_candle_count=first_hits[ForwardOutcomeFirstHit.SAME_CANDLE],
        first_hit_upside_rate=_rate(
            first_hits[ForwardOutcomeFirstHit.MAX_UPSIDE], complete_count
        ),
        first_hit_downside_rate=_rate(
            first_hits[ForwardOutcomeFirstHit.MAX_DOWNSIDE], complete_count
        ),
    )


def _coverage(records: tuple[ScannerResearchRecord, ...]) -> ScannerFilteringCoverage:
    with_outcome = sum(item.posthoc.future_outcome is not None for item in records)
    with_analytics = sum(item.causal.analytics.status == "MATCHED" for item in records)
    horizons = []
    for horizon_bars in DECISION_QUALITY_RESEARCH_HORIZONS:
        available = [
            horizon
            for record in records
            if (horizon := _record_horizon(record, horizon_bars)) is not None
        ]
        complete = sum(item.is_complete for item in available)
        incomplete = [item for item in available if not item.is_complete]
        incomplete_reasons = Counter(item.incomplete_reason for item in incomplete)
        horizons.append(
            ScannerFilteringCoverageHorizon(
                horizon_bars=horizon_bars,
                scanner_records=len(records),
                with_future_outcome=with_outcome,
                without_future_outcome=len(records) - with_outcome,
                complete_count=complete,
                incomplete_count=len(available) - complete,
                incomplete_gap_count=incomplete_reasons[ForwardOutcomeIncompleteReason.GAP],
                incomplete_period_end_count=incomplete_reasons[
                    ForwardOutcomeIncompleteReason.PERIOD_END
                ],
                incomplete_gap_and_period_end_count=incomplete_reasons[
                    ForwardOutcomeIncompleteReason.GAP_AND_PERIOD_END
                ],
            )
        )
    return ScannerFilteringCoverage(
        scanner_records=len(records),
        with_future_outcome=with_outcome,
        without_future_outcome=len(records) - with_outcome,
        with_analytics=with_analytics,
        without_analytics=len(records) - with_analytics,
        horizons=tuple(horizons),
    )


def _dimension_values(
    record: ScannerResearchRecord,
    dimension: ScannerFilteringDimension,
) -> tuple[tuple[str, int | None], ...]:
    scanner = record.causal.scanner
    if dimension is ScannerFilteringDimension.CLASSIFICATION:
        return ((scanner.classification, None),)
    if dimension is ScannerFilteringDimension.SCORE:
        return ((str(scanner.score), scanner.score),)
    if dimension is ScannerFilteringDimension.SCORE_MARGIN:
        return ((str(scanner.score_margin), scanner.score_margin),)
    if dimension is ScannerFilteringDimension.TRIGGER:
        return tuple((trigger, None) for trigger in scanner.triggers)
    if dimension is ScannerFilteringDimension.MARKET_REGIME:
        if scanner.market_regime is None:
            return ()
        return ((scanner.market_regime, None),)
    raise AssertionError(f"unsupported Scanner Filtering dimension: {dimension}")


def _cohort_sort_key(cohort: ScannerFilteringCohort) -> tuple[int, int, int | str]:
    dimension_order = _DIMENSION_ORDER[cohort.dimension]
    if cohort.numeric_value is not None:
        return (dimension_order, 0, cohort.numeric_value)
    return (dimension_order, 1, cohort.key)


def _build_cohort(
    *,
    bundle: DecisionQualityResearchBundle,
    dimension: ScannerFilteringDimension,
    key: str,
    numeric_value: int | None,
    records: tuple[ScannerResearchRecord, ...],
) -> ScannerFilteringCohort:
    horizons = tuple(
        _horizon_stats(records, horizon_bars)
        for horizon_bars in DECISION_QUALITY_RESEARCH_HORIZONS
    )
    summary = _classification_summary(records)
    payload = {
        "schema_version": SCANNER_FILTERING_COHORT_SCHEMA_VERSION,
        "policy_version": SCANNER_FILTERING_QUALITY_POLICY_VERSION,
        "research_run_id": bundle.research_run.research_run_id,
        "dimension": dimension,
        "key": key,
        "numeric_value": numeric_value,
        "member_record_fingerprints": tuple(
            sorted(item.record_fingerprint for item in records)
        ),
        "classification_summary": summary.model_dump(mode="python"),
        "horizons": tuple(item.model_dump(mode="python") for item in horizons),
    }
    return ScannerFilteringCohort(
        dimension=dimension,
        key=key,
        numeric_value=numeric_value,
        multi_valued=dimension is ScannerFilteringDimension.TRIGGER,
        scanner_count=len(records),
        classification_summary=summary,
        horizons=horizons,
        cohort_fingerprint=stable_digest(payload),
    )


def _build_cohorts(
    bundle: DecisionQualityResearchBundle,
) -> tuple[
    tuple[ScannerFilteringCohort, ...], tuple[ScannerFilteringDimensionCoverage, ...]
]:
    records = bundle.scanner_records
    grouped: dict[
        tuple[ScannerFilteringDimension, str, int | None], list[ScannerResearchRecord]
    ] = defaultdict(list)
    represented: dict[ScannerFilteringDimension, set[str]] = {
        dimension: set() for dimension in ScannerFilteringDimension
    }

    for record in records:
        for dimension in ScannerFilteringDimension:
            values = _dimension_values(record, dimension)
            if values:
                represented[dimension].add(record.record_id)
            for key, numeric_value in values:
                grouped[(dimension, key, numeric_value)].append(record)

    # The three primary classification cohorts are contractual even when N=0.
    for classification in CLASSIFICATIONS:
        grouped.setdefault(
            (ScannerFilteringDimension.CLASSIFICATION, classification, None), []
        )

    cohorts = tuple(
        sorted(
            (
                _build_cohort(
                    bundle=bundle,
                    dimension=dimension,
                    key=key,
                    numeric_value=numeric_value,
                    records=tuple(
                        sorted(
                            group_records,
                            key=lambda item: (
                                item.causal.observed_at,
                                item.scan_id,
                                item.record_id,
                            ),
                        )
                    ),
                )
                for (dimension, key, numeric_value), group_records in grouped.items()
            ),
            key=_cohort_sort_key,
        )
    )

    coverage = []
    for dimension in ScannerFilteringDimension:
        dimension_cohorts = [item for item in cohorts if item.dimension is dimension]
        coverage.append(
            ScannerFilteringDimensionCoverage(
                dimension=dimension,
                represented_scanner_count=len(represented[dimension]),
                missing_scanner_count=len(records) - len(represented[dimension]),
                cohort_count=len(dimension_cohorts),
                multi_valued=dimension is ScannerFilteringDimension.TRIGGER,
            )
        )
    return cohorts, tuple(sorted(coverage, key=lambda item: _DIMENSION_ORDER[item.dimension]))


def _delta(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return left - right


def _build_contrasts(
    cohorts: tuple[ScannerFilteringCohort, ...],
) -> tuple[ScannerFilteringContrast, ...]:
    classification_cohorts = {
        item.key: item
        for item in cohorts
        if item.dimension is ScannerFilteringDimension.CLASSIFICATION
    }
    contrasts = []
    for kind, left_key, right_key in _CONTRAST_PAIRS:
        left = classification_cohorts[left_key]
        right = classification_cohorts[right_key]
        horizons = []
        for left_stats, right_stats in zip(left.horizons, right.horizons, strict=True):
            if left_stats.horizon_bars != right_stats.horizon_bars:
                raise ScannerFilteringQualityError("classification horizon mismatch")
            horizons.append(
                ScannerFilteringContrastHorizon(
                    horizon_bars=left_stats.horizon_bars,
                    left_scanner_count=left.scanner_count,
                    right_scanner_count=right.scanner_count,
                    left_complete_count=left_stats.complete_count,
                    right_complete_count=right_stats.complete_count,
                    median_raw_return_delta_pct=_delta(
                        left_stats.raw_return_median_pct,
                        right_stats.raw_return_median_pct,
                    ),
                    median_max_upside_delta_pct=_delta(
                        left_stats.max_upside_median_pct,
                        right_stats.max_upside_median_pct,
                    ),
                    median_max_downside_delta_pct=_delta(
                        left_stats.max_downside_median_pct,
                        right_stats.max_downside_median_pct,
                    ),
                    median_max_absolute_excursion_delta_pct=_delta(
                        left_stats.max_absolute_excursion_median_pct,
                        right_stats.max_absolute_excursion_median_pct,
                    ),
                    positive_rate_delta=_delta(
                        left_stats.positive_rate, right_stats.positive_rate
                    ),
                    first_hit_upside_rate_delta=_delta(
                        left_stats.first_hit_upside_rate,
                        right_stats.first_hit_upside_rate,
                    ),
                    first_hit_downside_rate_delta=_delta(
                        left_stats.first_hit_downside_rate,
                        right_stats.first_hit_downside_rate,
                    ),
                )
            )
        contrasts.append(
            ScannerFilteringContrast(
                kind=kind,
                left_classification=left_key,
                right_classification=right_key,
                horizons=tuple(horizons),
            )
        )
    return tuple(contrasts)


def build_scanner_filtering_quality_report(
    *,
    bundle: DecisionQualityResearchBundle,
) -> ScannerFilteringQualityReport:
    """Build a pure descriptive Scanner filtering report from canonical 24D.1 records."""

    _validate_bundle(bundle)
    records = bundle.scanner_records
    source = bundle.research_run.source
    classification_summary = _classification_summary(records)
    coverage = _coverage(records)
    cohorts, dimension_coverage = _build_cohorts(bundle)
    contrasts = _build_contrasts(cohorts)

    report_identity = {
        "schema_version": SCANNER_FILTERING_QUALITY_REPORT_SCHEMA_VERSION,
        "policy_version": SCANNER_FILTERING_QUALITY_POLICY_VERSION,
        "research_run_id": bundle.research_run.research_run_id,
        "period_role": source.period_role,
    }
    report_id = stable_uuid("scanner-filtering-quality-report", report_identity)
    fingerprint_payload = {
        **report_identity,
        "report_id": report_id,
        "source_bundle_fingerprint": bundle.bundle_fingerprint,
        "classification_summary": classification_summary.model_dump(mode="python"),
        "coverage": coverage.model_dump(mode="python"),
        "dimension_coverage": tuple(
            item.model_dump(mode="python") for item in dimension_coverage
        ),
        "cohort_fingerprints": tuple(item.cohort_fingerprint for item in cohorts),
        "contrasts": tuple(item.model_dump(mode="python") for item in contrasts),
    }
    return ScannerFilteringQualityReport(
        report_id=report_id,
        research_run_id=bundle.research_run.research_run_id,
        source_backtest_run_id=source.source_backtest_run_id,
        analytics_run_id=source.analytics_run_id,
        period_role=source.period_role,
        source_bundle_fingerprint=bundle.bundle_fingerprint,
        scanner_count=len(records),
        classification_summary=classification_summary,
        coverage=coverage,
        dimension_coverage=dimension_coverage,
        cohorts=cohorts,
        contrasts=contrasts,
        report_fingerprint=stable_digest(fingerprint_payload),
    )


__all__ = [
    "SCANNER_FILTERING_COHORT_SCHEMA_VERSION",
    "SCANNER_FILTERING_CONTRAST_SCHEMA_VERSION",
    "SCANNER_FILTERING_QUALITY_POLICY_VERSION",
    "SCANNER_FILTERING_QUALITY_REPORT_SCHEMA_VERSION",
    "ScannerFilteringClassificationSummary",
    "ScannerFilteringCohort",
    "ScannerFilteringContrast",
    "ScannerFilteringContrastHorizon",
    "ScannerFilteringContrastKind",
    "ScannerFilteringCoverage",
    "ScannerFilteringCoverageHorizon",
    "ScannerFilteringDimension",
    "ScannerFilteringDimensionCoverage",
    "ScannerFilteringHorizonStats",
    "ScannerFilteringQualityError",
    "ScannerFilteringQualityReport",
    "build_scanner_filtering_quality_report",
]
