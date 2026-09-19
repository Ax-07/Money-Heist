from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.canonical import canonical_json, stable_digest, stable_uuid
from app.evaluation.analytics_attribution.funnel_stage_models import (
    FunnelStage,
    FunnelStageAnalyticsAttributionRecord,
    FunnelStageAnalyticsAttributionSet,
)
from app.evaluation.forward_outcomes.models import (
    ForwardOutcomeFirstHit,
    ForwardOutcomeHorizon,
    ForwardOutcomeIncompleteReason,
)

from .models import (
    DECISION_QUALITY_RESEARCH_BUNDLE_SCHEMA_VERSION,
    DECISION_QUALITY_RESEARCH_HORIZONS,
    DECISION_QUALITY_RESEARCH_POLICY_VERSION,
    CandidateResearchRecord,
    DecisionQualityResearchBundle,
)

FUNNEL_DECISION_QUALITY_POLICY_VERSION = "funnel-decision-quality-descriptive-v1"
FUNNEL_DECISION_QUALITY_REPORT_SCHEMA_VERSION = "money-heist.funnel-decision-quality-report.v1"
FUNNEL_DECISION_QUALITY_COHORT_SCHEMA_VERSION = "money-heist.funnel-decision-quality-cohort.v1"
FUNNEL_DECISION_QUALITY_CONTRAST_SCHEMA_VERSION = "money-heist.funnel-decision-quality-contrast.v1"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FunnelDecisionQualityError(ValueError):
    pass


class FunnelDecisionQualityDimension(StrEnum):
    STAGE_REACHABILITY = "STAGE_REACHABILITY"
    STAGE_RESULT = "STAGE_RESULT"
    STAGE_FAILURE = "STAGE_FAILURE"
    SPECIALIST_AGENT = "SPECIALIST_AGENT"
    SPECIALIST_STANCE = "SPECIALIST_STANCE"
    STAGE_REASON = "STAGE_REASON"
    PLAN_SELECTED_AGENT_COUNT = "PLAN_SELECTED_AGENT_COUNT"


class DirectionalFirstHit(StrEnum):
    FAVORABLE = "FAVORABLE"
    ADVERSE = "ADVERSE"
    SAME_CANDLE = "SAME_CANDLE"


class FunnelDecisionQualityContrastKind(StrEnum):
    PALERMO_CLEAR_VS_CAUTION = "PALERMO_CLEAR_VS_CAUTION"
    PALERMO_CLEAR_VS_REJECT = "PALERMO_CLEAR_VS_REJECT"
    PALERMO_CAUTION_VS_REJECT = "PALERMO_CAUTION_VS_REJECT"
    FINAL_LONG_VS_SHORT = "FINAL_LONG_VS_SHORT"
    FINAL_LONG_VS_NO_TRADE = "FINAL_LONG_VS_NO_TRADE"
    FINAL_SHORT_VS_NO_TRADE = "FINAL_SHORT_VS_NO_TRADE"
    RISK_APPROVED_VS_RESIZED = "RISK_APPROVED_VS_RESIZED"
    RISK_APPROVED_VS_REJECTED = "RISK_APPROVED_VS_REJECTED"
    RISK_RESIZED_VS_REJECTED = "RISK_RESIZED_VS_REJECTED"


_FIXED_STAGES: Final = (
    FunnelStage.COMPUTE_GATE,
    FunnelStage.PROFESSOR_PLAN,
    FunnelStage.PALERMO,
    FunnelStage.PROFESSOR_FINAL,
    FunnelStage.TRADE_PROPOSAL,
    FunnelStage.RISK,
    FunnelStage.PAPER,
)
_STAGE_ORDER: Final = {stage: index for index, stage in enumerate(FunnelStage)}
_DIMENSION_ORDER: Final = {
    dimension: index for index, dimension in enumerate(FunnelDecisionQualityDimension)
}
_DIRECTION_AWARE_STAGES: Final = {
    FunnelStage.PROFESSOR_FINAL,
    FunnelStage.TRADE_PROPOSAL,
    FunnelStage.RISK,
    FunnelStage.PAPER,
}


class AlignedOutcome(FrozenModel):
    directional_return_pct: Decimal
    favorable_excursion_pct: Decimal
    adverse_excursion_pct: Decimal
    first_hit_alignment: DirectionalFirstHit


def align_outcome_to_direction(
    *,
    horizon: ForwardOutcomeHorizon,
    direction: str,
) -> AlignedOutcome:
    if not horizon.is_complete:
        raise FunnelDecisionQualityError("direction alignment requires a complete horizon")
    required = (horizon.return_pct, horizon.max_upside_pct, horizon.max_downside_pct)
    if any(value is None for value in required):
        raise FunnelDecisionQualityError("complete horizon is missing price metrics")
    if direction not in {"LONG", "SHORT"}:
        raise FunnelDecisionQualityError("direction must be LONG or SHORT")

    raw_return = horizon.return_pct
    upside = horizon.max_upside_pct
    downside = horizon.max_downside_pct
    assert raw_return is not None and upside is not None and downside is not None

    if direction == "LONG":
        directional_return = raw_return
        favorable = upside
        adverse = abs(downside)
        mapping = {
            ForwardOutcomeFirstHit.MAX_UPSIDE: DirectionalFirstHit.FAVORABLE,
            ForwardOutcomeFirstHit.MAX_DOWNSIDE: DirectionalFirstHit.ADVERSE,
            ForwardOutcomeFirstHit.SAME_CANDLE: DirectionalFirstHit.SAME_CANDLE,
        }
    else:
        directional_return = -raw_return
        favorable = abs(downside)
        adverse = upside
        mapping = {
            ForwardOutcomeFirstHit.MAX_UPSIDE: DirectionalFirstHit.ADVERSE,
            ForwardOutcomeFirstHit.MAX_DOWNSIDE: DirectionalFirstHit.FAVORABLE,
            ForwardOutcomeFirstHit.SAME_CANDLE: DirectionalFirstHit.SAME_CANDLE,
        }
    if horizon.first_hit not in mapping:
        raise FunnelDecisionQualityError("complete horizon has unsupported first_hit")
    return AlignedOutcome(
        directional_return_pct=directional_return,
        favorable_excursion_pct=favorable,
        adverse_excursion_pct=adverse,
        first_hit_alignment=mapping[horizon.first_hit],
    )


class DirectionlessOutcomeStats(FrozenModel):
    horizon_bars: int = Field(gt=0)
    observation_count: int = Field(ge=0)
    outcome_available_count: int = Field(ge=0)
    outcome_missing_count: int = Field(ge=0)
    complete_count: int = Field(ge=0)
    incomplete_count: int = Field(ge=0)
    incomplete_gap_count: int = Field(ge=0)
    incomplete_period_end_count: int = Field(ge=0)
    incomplete_gap_and_period_end_count: int = Field(ge=0)
    raw_return_mean_pct: Decimal | None = None
    raw_return_median_pct: Decimal | None = None
    raw_positive_count: int = Field(ge=0)
    raw_negative_count: int = Field(ge=0)
    raw_flat_count: int = Field(ge=0)
    max_upside_mean_pct: Decimal | None = None
    max_upside_median_pct: Decimal | None = None
    max_downside_mean_pct: Decimal | None = None
    max_downside_median_pct: Decimal | None = None
    max_absolute_excursion_mean_pct: Decimal | None = None
    max_absolute_excursion_median_pct: Decimal | None = None
    first_hit_upside_count: int = Field(ge=0)
    first_hit_downside_count: int = Field(ge=0)
    first_hit_same_candle_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> DirectionlessOutcomeStats:
        if self.outcome_available_count + self.outcome_missing_count != self.observation_count:
            raise ValueError("outcome coverage must conserve observation_count")
        if self.complete_count + self.incomplete_count != self.outcome_available_count:
            raise ValueError("complete + incomplete must equal available outcomes")
        if (
            self.incomplete_gap_count
            + self.incomplete_period_end_count
            + self.incomplete_gap_and_period_end_count
            != self.incomplete_count
        ):
            raise ValueError("incomplete reasons must conserve incomplete_count")
        if (
            self.raw_positive_count + self.raw_negative_count + self.raw_flat_count
            != self.complete_count
        ):
            raise ValueError("raw sign counts must conserve complete_count")
        if (
            self.first_hit_upside_count
            + self.first_hit_downside_count
            + self.first_hit_same_candle_count
            != self.complete_count
        ):
            raise ValueError("first-hit counts must conserve complete_count")
        return self


class DirectionalOutcomeStats(FrozenModel):
    horizon_bars: int = Field(gt=0)
    direction_available_count: int = Field(ge=0)
    direction_unavailable_count: int = Field(ge=0)
    directional_complete_count: int = Field(ge=0)
    directional_return_mean_pct: Decimal | None = None
    directional_return_median_pct: Decimal | None = None
    directionally_positive_count: int = Field(ge=0)
    directionally_negative_count: int = Field(ge=0)
    directionally_flat_count: int = Field(ge=0)
    favorable_excursion_mean_pct: Decimal | None = None
    favorable_excursion_median_pct: Decimal | None = None
    adverse_excursion_mean_pct: Decimal | None = None
    adverse_excursion_median_pct: Decimal | None = None
    favorable_first_hit_count: int = Field(ge=0)
    adverse_first_hit_count: int = Field(ge=0)
    same_candle_first_hit_count: int = Field(ge=0)


class FunnelDecisionQualityCohort(FrozenModel):
    schema_version: str = FUNNEL_DECISION_QUALITY_COHORT_SCHEMA_VERSION
    stage: FunnelStage
    dimension: FunnelDecisionQualityDimension
    key: str = Field(min_length=1)
    multi_valued: bool = False
    candidate_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    direction_available_count: int = Field(ge=0)
    direction_unavailable_count: int = Field(ge=0)
    horizons: tuple[DirectionlessOutcomeStats, ...]
    directional_horizons: tuple[DirectionalOutcomeStats, ...] = ()
    member_refs: tuple[str, ...] = ()
    cohort_fingerprint: str = Field(min_length=64, max_length=64)


class FunnelStageCoverage(FrozenModel):
    stage: FunnelStage
    candidate_count: int = Field(ge=0)
    record_count: int = Field(ge=0)
    reached_count: int = Field(ge=0)
    not_reached_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    with_future_outcome: int = Field(ge=0)
    without_future_outcome: int = Field(ge=0)
    candidates_with_records: int = Field(ge=0)
    unique_agents: tuple[str, ...] = ()


class FunnelDecisionQualityCoverage(FrozenModel):
    candidate_count: int = Field(ge=0)
    candidates_with_future_outcome: int = Field(ge=0)
    candidates_without_future_outcome: int = Field(ge=0)
    candidates_with_analytics: int = Field(ge=0)
    candidates_without_analytics: int = Field(ge=0)
    stages: tuple[FunnelStageCoverage, ...]


class FunnelDecisionQualityContrastHorizon(FrozenModel):
    horizon_bars: int = Field(gt=0)
    left_count: int = Field(ge=0)
    right_count: int = Field(ge=0)
    left_complete_count: int = Field(ge=0)
    right_complete_count: int = Field(ge=0)
    left_direction_available_count: int = Field(ge=0)
    right_direction_available_count: int = Field(ge=0)
    median_raw_return_delta_pct: Decimal | None = None
    median_max_absolute_excursion_delta_pct: Decimal | None = None
    median_directional_return_delta_pct: Decimal | None = None
    median_favorable_excursion_delta_pct: Decimal | None = None
    median_adverse_excursion_delta_pct: Decimal | None = None


class FunnelDecisionQualityContrast(FrozenModel):
    schema_version: str = FUNNEL_DECISION_QUALITY_CONTRAST_SCHEMA_VERSION
    kind: FunnelDecisionQualityContrastKind
    stage: FunnelStage
    left_key: str
    right_key: str
    horizons: tuple[FunnelDecisionQualityContrastHorizon, ...]


class FunnelDecisionQualityReport(FrozenModel):
    schema_version: str = FUNNEL_DECISION_QUALITY_REPORT_SCHEMA_VERSION
    policy_version: str = FUNNEL_DECISION_QUALITY_POLICY_VERSION
    report_id: str = Field(min_length=1)
    research_run_id: str = Field(min_length=1)
    source_backtest_run_id: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    period_role: str = Field(min_length=1)
    source_bundle_fingerprint: str = Field(min_length=64, max_length=64)
    source_funnel_stage_set_fingerprint: str = Field(min_length=64, max_length=64)
    source_decision_record_set_fingerprint: str = Field(min_length=64, max_length=64)
    candidate_count: int = Field(ge=0)
    coverage: FunnelDecisionQualityCoverage
    cohorts: tuple[FunnelDecisionQualityCohort, ...]
    contrasts: tuple[FunnelDecisionQualityContrast, ...]
    report_fingerprint: str = Field(min_length=64, max_length=64)

    def to_json(self) -> str:
        return canonical_json(self.model_dump(mode="python"))


class _Observation:
    def __init__(
        self,
        candidate: CandidateResearchRecord,
        stage_record: FunnelStageAnalyticsAttributionRecord,
        direction: str | None,
    ) -> None:
        self.candidate = candidate
        self.stage_record = stage_record
        self.direction = direction

    @property
    def member_ref(self) -> str:
        return self.stage_record.record_id


def _mean(values: Iterable[Decimal]) -> Decimal | None:
    items = tuple(values)
    return None if not items else sum(items, Decimal("0")) / Decimal(len(items))


def _median(values: Iterable[Decimal]) -> Decimal | None:
    items = tuple(sorted(values))
    if not items:
        return None
    middle = len(items) // 2
    if len(items) % 2:
        return items[middle]
    return (items[middle - 1] + items[middle]) / Decimal("2")


def _horizon(candidate: CandidateResearchRecord, bars: int) -> ForwardOutcomeHorizon | None:
    outcome = candidate.posthoc.future_outcome
    if outcome is None:
        return None
    return next(item for item in outcome.horizons if item.horizon_bars == bars)


def _directionless_stats(
    observations: tuple[_Observation, ...], bars: int
) -> DirectionlessOutcomeStats:
    horizons = tuple(_horizon(item.candidate, bars) for item in observations)
    available = tuple(item for item in horizons if item is not None)
    complete = tuple(item for item in available if item.is_complete)
    incomplete = tuple(item for item in available if not item.is_complete)
    returns = tuple(item.return_pct for item in complete if item.return_pct is not None)
    upsides = tuple(item.max_upside_pct for item in complete if item.max_upside_pct is not None)
    downsides = tuple(
        item.max_downside_pct for item in complete if item.max_downside_pct is not None
    )
    abs_excursions = tuple(
        max(abs(up), abs(down)) for up, down in zip(upsides, downsides, strict=True)
    )
    return DirectionlessOutcomeStats(
        horizon_bars=bars,
        observation_count=len(observations),
        outcome_available_count=len(available),
        outcome_missing_count=len(observations) - len(available),
        complete_count=len(complete),
        incomplete_count=len(incomplete),
        incomplete_gap_count=sum(
            item.incomplete_reason is ForwardOutcomeIncompleteReason.GAP for item in incomplete
        ),
        incomplete_period_end_count=sum(
            item.incomplete_reason is ForwardOutcomeIncompleteReason.PERIOD_END
            for item in incomplete
        ),
        incomplete_gap_and_period_end_count=sum(
            item.incomplete_reason is ForwardOutcomeIncompleteReason.GAP_AND_PERIOD_END
            for item in incomplete
        ),
        raw_return_mean_pct=_mean(returns),
        raw_return_median_pct=_median(returns),
        raw_positive_count=sum(value > 0 for value in returns),
        raw_negative_count=sum(value < 0 for value in returns),
        raw_flat_count=sum(value == 0 for value in returns),
        max_upside_mean_pct=_mean(upsides),
        max_upside_median_pct=_median(upsides),
        max_downside_mean_pct=_mean(downsides),
        max_downside_median_pct=_median(downsides),
        max_absolute_excursion_mean_pct=_mean(abs_excursions),
        max_absolute_excursion_median_pct=_median(abs_excursions),
        first_hit_upside_count=sum(
            item.first_hit is ForwardOutcomeFirstHit.MAX_UPSIDE for item in complete
        ),
        first_hit_downside_count=sum(
            item.first_hit is ForwardOutcomeFirstHit.MAX_DOWNSIDE for item in complete
        ),
        first_hit_same_candle_count=sum(
            item.first_hit is ForwardOutcomeFirstHit.SAME_CANDLE for item in complete
        ),
    )


def _directional_stats(
    observations: tuple[_Observation, ...], bars: int
) -> DirectionalOutcomeStats:
    direction_available = tuple(
        item for item in observations if item.direction in {"LONG", "SHORT"}
    )
    aligned: list[AlignedOutcome] = []
    for item in direction_available:
        horizon = _horizon(item.candidate, bars)
        if horizon is not None and horizon.is_complete:
            aligned.append(
                align_outcome_to_direction(horizon=horizon, direction=item.direction or "")
            )
    returns = tuple(item.directional_return_pct for item in aligned)
    favorable = tuple(item.favorable_excursion_pct for item in aligned)
    adverse = tuple(item.adverse_excursion_pct for item in aligned)
    return DirectionalOutcomeStats(
        horizon_bars=bars,
        direction_available_count=len(direction_available),
        direction_unavailable_count=len(observations) - len(direction_available),
        directional_complete_count=len(aligned),
        directional_return_mean_pct=_mean(returns),
        directional_return_median_pct=_median(returns),
        directionally_positive_count=sum(value > 0 for value in returns),
        directionally_negative_count=sum(value < 0 for value in returns),
        directionally_flat_count=sum(value == 0 for value in returns),
        favorable_excursion_mean_pct=_mean(favorable),
        favorable_excursion_median_pct=_median(favorable),
        adverse_excursion_mean_pct=_mean(adverse),
        adverse_excursion_median_pct=_median(adverse),
        favorable_first_hit_count=sum(
            item.first_hit_alignment is DirectionalFirstHit.FAVORABLE for item in aligned
        ),
        adverse_first_hit_count=sum(
            item.first_hit_alignment is DirectionalFirstHit.ADVERSE for item in aligned
        ),
        same_candle_first_hit_count=sum(
            item.first_hit_alignment is DirectionalFirstHit.SAME_CANDLE for item in aligned
        ),
    )


def _canonical_direction(
    candidate: CandidateResearchRecord,
    records: tuple[FunnelStageAnalyticsAttributionRecord, ...],
) -> str | None:
    final = next((item for item in records if item.stage is FunnelStage.PROFESSOR_FINAL), None)
    proposal = next((item for item in records if item.stage is FunnelStage.TRADE_PROPOSAL), None)
    risk = next((item for item in records if item.stage is FunnelStage.RISK), None)
    direction = (
        final.stage_result if final and final.reached and final.failure_code is None else None
    )
    if direction not in {"LONG", "SHORT", "NO_TRADE", None}:
        raise FunnelDecisionQualityError(
            f"unsupported FINAL direction for {candidate.opportunity_id}: {direction}"
        )
    if direction == "NO_TRADE":
        direction = None
    if (
        proposal
        and proposal.reached
        and proposal.failure_code is None
        and proposal.stage_result is not None
    ):
        if proposal.stage_result not in {"LONG", "SHORT"}:
            raise FunnelDecisionQualityError("TradeProposal side must be LONG or SHORT")
        if direction != proposal.stage_result:
            raise FunnelDecisionQualityError("Professor FINAL and TradeProposal side mismatch")
    if risk and risk.reached and direction is not None:
        decision = candidate.causal.decision
        if (
            decision is not None
            and decision.professor_final_direction in {"LONG", "SHORT"}
            and decision.professor_final_direction != direction
        ):
            raise FunnelDecisionQualityError(
                "24D.1 FINAL direction mismatch with funnel attribution"
            )
    return direction


def _stage_direction(stage: FunnelStage, canonical_direction: str | None) -> str | None:
    return canonical_direction if stage in _DIRECTION_AWARE_STAGES else None


def _validate_inputs(
    bundle: DecisionQualityResearchBundle, stage_set: FunnelStageAnalyticsAttributionSet
) -> None:
    if bundle.schema_version != DECISION_QUALITY_RESEARCH_BUNDLE_SCHEMA_VERSION:
        raise FunnelDecisionQualityError("unsupported Decision Quality bundle schema")
    if bundle.policy_version != DECISION_QUALITY_RESEARCH_POLICY_VERSION:
        raise FunnelDecisionQualityError("unsupported Decision Quality bundle policy")
    source = bundle.research_run.source
    if stage_set.source_backtest_run_id != source.source_backtest_run_id:
        raise FunnelDecisionQualityError("source BacktestRun mismatch")
    if stage_set.analytics_run_id != source.analytics_run_id:
        raise FunnelDecisionQualityError("AnalyticsRun mismatch")
    candidate_ids = {item.opportunity_id for item in bundle.candidate_records}
    foreign = {item.opportunity_id for item in stage_set.records} - candidate_ids
    if foreign:
        raise FunnelDecisionQualityError(
            f"stage attribution contains unknown opportunities: {sorted(foreign)}"
        )

    by_opportunity: dict[str, list[FunnelStageAnalyticsAttributionRecord]] = defaultdict(list)
    for record in stage_set.records:
        by_opportunity[record.opportunity_id].append(record)

    for candidate in bundle.candidate_records:
        stage_records = tuple(by_opportunity.get(candidate.opportunity_id, ()))
        decision = candidate.causal.decision
        if decision is None:
            if stage_records:
                raise FunnelDecisionQualityError(
                    "candidate without Decision Intelligence cannot carry stage records"
                )
            continue
        if not stage_records:
            raise FunnelDecisionQualityError(
                "candidate with Decision Intelligence is missing stage attribution records"
            )
        for record in stage_records:
            if record.decision_intelligence_record_id != decision.record_id:
                raise FunnelDecisionQualityError(
                    "Decision Intelligence record id mismatch for stage attribution"
                )
            if record.decision_intelligence_record_fingerprint != decision.record_fingerprint:
                raise FunnelDecisionQualityError(
                    "Decision Intelligence fingerprint mismatch for stage attribution"
                )
            if record.market_as_of != candidate.causal.observed_at:
                raise FunnelDecisionQualityError(
                    "stage market_as_of must equal Candidate observed_at"
                )


def _stage_coverage(
    candidates: tuple[CandidateResearchRecord, ...],
    records: tuple[FunnelStageAnalyticsAttributionRecord, ...],
) -> tuple[FunnelStageCoverage, ...]:
    result: list[FunnelStageCoverage] = []
    by_stage: dict[FunnelStage, list[FunnelStageAnalyticsAttributionRecord]] = defaultdict(list)
    for record in records:
        by_stage[record.stage].append(record)
    outcomes = {item.opportunity_id: item.posthoc.future_outcome is not None for item in candidates}
    for stage in FunnelStage:
        stage_records = tuple(by_stage.get(stage, ()))
        candidate_ids = {item.opportunity_id for item in stage_records}
        if stage in _FIXED_STAGES:
            expected_ids = {
                item.opportunity_id for item in candidates if item.causal.decision is not None
            }
            if len(stage_records) != len(expected_ids) or candidate_ids != expected_ids:
                raise FunnelDecisionQualityError(
                    f"fixed stage {stage} does not conserve Decision Intelligence coverage"
                )
        result.append(
            FunnelStageCoverage(
                stage=stage,
                candidate_count=len(candidates),
                record_count=len(stage_records),
                reached_count=sum(item.reached for item in stage_records),
                not_reached_count=sum(not item.reached for item in stage_records),
                failure_count=sum(item.failure_code is not None for item in stage_records),
                with_future_outcome=sum(
                    outcomes.get(opportunity_id, False) for opportunity_id in candidate_ids
                ),
                without_future_outcome=sum(
                    not outcomes.get(opportunity_id, False) for opportunity_id in candidate_ids
                ),
                candidates_with_records=len(candidate_ids),
                unique_agents=tuple(
                    sorted({item.agent_id for item in stage_records if item.agent_id is not None})
                ),
            )
        )
    return tuple(result)


def _cohort_specs(
    record: FunnelStageAnalyticsAttributionRecord,
) -> tuple[tuple[FunnelDecisionQualityDimension, str, bool], ...]:
    specs: list[tuple[FunnelDecisionQualityDimension, str, bool]] = []
    if record.stage in _FIXED_STAGES:
        specs.append(
            (
                FunnelDecisionQualityDimension.STAGE_REACHABILITY,
                "REACHED" if record.reached else "NOT_REACHED",
                False,
            )
        )
    if not record.reached:
        return tuple(specs)
    if record.failure_code is not None:
        specs.append((FunnelDecisionQualityDimension.STAGE_FAILURE, record.failure_code, False))
        return tuple(specs)
    if record.stage_result is not None:
        specs.append((FunnelDecisionQualityDimension.STAGE_RESULT, record.stage_result, False))
    if record.stage is FunnelStage.SPECIALIST:
        if record.agent_id is not None:
            specs.append((FunnelDecisionQualityDimension.SPECIALIST_AGENT, record.agent_id, False))
        if record.stage_result is not None:
            specs.append(
                (FunnelDecisionQualityDimension.SPECIALIST_STANCE, record.stage_result, False)
            )
    specs.extend(
        (FunnelDecisionQualityDimension.STAGE_REASON, code, True) for code in record.reason_codes
    )
    if record.stage is FunnelStage.PROFESSOR_PLAN:
        specs.append(
            (
                FunnelDecisionQualityDimension.PLAN_SELECTED_AGENT_COUNT,
                str(len(record.selected_agents)),
                False,
            )
        )
    return tuple(specs)


def _make_cohort(
    *,
    stage: FunnelStage,
    dimension: FunnelDecisionQualityDimension,
    key: str,
    multi_valued: bool,
    observations: tuple[_Observation, ...],
) -> FunnelDecisionQualityCohort:
    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.candidate.causal.observed_at,
                item.candidate.opportunity_id,
                item.stage_record.stage_instance_order or -1,
                item.member_ref,
            ),
        )
    )
    raw = tuple(_directionless_stats(ordered, bars) for bars in DECISION_QUALITY_RESEARCH_HORIZONS)
    directional = (
        tuple(_directional_stats(ordered, bars) for bars in DECISION_QUALITY_RESEARCH_HORIZONS)
        if stage in _DIRECTION_AWARE_STAGES
        else ()
    )
    member_refs = tuple(item.member_ref for item in ordered)
    fingerprint = stable_digest(
        {
            "schema": FUNNEL_DECISION_QUALITY_COHORT_SCHEMA_VERSION,
            "policy": FUNNEL_DECISION_QUALITY_POLICY_VERSION,
            "stage": stage,
            "dimension": dimension,
            "key": key,
            "multi_valued": multi_valued,
            "member_refs": member_refs,
            "horizons": tuple(item.model_dump(mode="python") for item in raw),
            "directional_horizons": tuple(item.model_dump(mode="python") for item in directional),
        }
    )
    candidate_ids = {item.candidate.opportunity_id for item in ordered}
    direction_available = sum(item.direction in {"LONG", "SHORT"} for item in ordered)
    return FunnelDecisionQualityCohort(
        stage=stage,
        dimension=dimension,
        key=key,
        multi_valued=multi_valued,
        candidate_count=len(candidate_ids),
        observation_count=len(ordered),
        direction_available_count=direction_available,
        direction_unavailable_count=len(ordered) - direction_available,
        horizons=raw,
        directional_horizons=directional,
        member_refs=member_refs,
        cohort_fingerprint=fingerprint,
    )


def _delta(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    return None if left is None or right is None else left - right


def _build_contrast(
    kind: FunnelDecisionQualityContrastKind,
    stage: FunnelStage,
    left: FunnelDecisionQualityCohort,
    right: FunnelDecisionQualityCohort,
) -> FunnelDecisionQualityContrast:
    horizons: list[FunnelDecisionQualityContrastHorizon] = []
    for bars in DECISION_QUALITY_RESEARCH_HORIZONS:
        lhs = next(item for item in left.horizons if item.horizon_bars == bars)
        rhs = next(item for item in right.horizons if item.horizon_bars == bars)
        ldir = next((item for item in left.directional_horizons if item.horizon_bars == bars), None)
        rdir = next(
            (item for item in right.directional_horizons if item.horizon_bars == bars), None
        )
        horizons.append(
            FunnelDecisionQualityContrastHorizon(
                horizon_bars=bars,
                left_count=left.observation_count,
                right_count=right.observation_count,
                left_complete_count=lhs.complete_count,
                right_complete_count=rhs.complete_count,
                left_direction_available_count=left.direction_available_count,
                right_direction_available_count=right.direction_available_count,
                median_raw_return_delta_pct=_delta(
                    lhs.raw_return_median_pct, rhs.raw_return_median_pct
                ),
                median_max_absolute_excursion_delta_pct=_delta(
                    lhs.max_absolute_excursion_median_pct, rhs.max_absolute_excursion_median_pct
                ),
                median_directional_return_delta_pct=_delta(
                    ldir.directional_return_median_pct, rdir.directional_return_median_pct
                )
                if ldir and rdir
                else None,
                median_favorable_excursion_delta_pct=_delta(
                    ldir.favorable_excursion_median_pct, rdir.favorable_excursion_median_pct
                )
                if ldir and rdir
                else None,
                median_adverse_excursion_delta_pct=_delta(
                    ldir.adverse_excursion_median_pct, rdir.adverse_excursion_median_pct
                )
                if ldir and rdir
                else None,
            )
        )
    return FunnelDecisionQualityContrast(
        kind=kind, stage=stage, left_key=left.key, right_key=right.key, horizons=tuple(horizons)
    )


def _contrasts(
    cohorts: tuple[FunnelDecisionQualityCohort, ...],
) -> tuple[FunnelDecisionQualityContrast, ...]:
    by_key = {(item.stage, item.dimension, item.key): item for item in cohorts}
    specs = (
        (
            FunnelDecisionQualityContrastKind.PALERMO_CLEAR_VS_CAUTION,
            FunnelStage.PALERMO,
            "CLEAR",
            "CAUTION",
        ),
        (
            FunnelDecisionQualityContrastKind.PALERMO_CLEAR_VS_REJECT,
            FunnelStage.PALERMO,
            "CLEAR",
            "REJECT",
        ),
        (
            FunnelDecisionQualityContrastKind.PALERMO_CAUTION_VS_REJECT,
            FunnelStage.PALERMO,
            "CAUTION",
            "REJECT",
        ),
        (
            FunnelDecisionQualityContrastKind.FINAL_LONG_VS_SHORT,
            FunnelStage.PROFESSOR_FINAL,
            "LONG",
            "SHORT",
        ),
        (
            FunnelDecisionQualityContrastKind.FINAL_LONG_VS_NO_TRADE,
            FunnelStage.PROFESSOR_FINAL,
            "LONG",
            "NO_TRADE",
        ),
        (
            FunnelDecisionQualityContrastKind.FINAL_SHORT_VS_NO_TRADE,
            FunnelStage.PROFESSOR_FINAL,
            "SHORT",
            "NO_TRADE",
        ),
        (
            FunnelDecisionQualityContrastKind.RISK_APPROVED_VS_RESIZED,
            FunnelStage.RISK,
            "APPROVED",
            "RESIZED",
        ),
        (
            FunnelDecisionQualityContrastKind.RISK_APPROVED_VS_REJECTED,
            FunnelStage.RISK,
            "APPROVED",
            "REJECTED",
        ),
        (
            FunnelDecisionQualityContrastKind.RISK_RESIZED_VS_REJECTED,
            FunnelStage.RISK,
            "RESIZED",
            "REJECTED",
        ),
    )
    result = []
    for kind, stage, left_key, right_key in specs:
        left = by_key.get((stage, FunnelDecisionQualityDimension.STAGE_RESULT, left_key))
        right = by_key.get((stage, FunnelDecisionQualityDimension.STAGE_RESULT, right_key))
        if left is not None and right is not None:
            result.append(_build_contrast(kind, stage, left, right))
    return tuple(result)


def build_funnel_decision_quality_report(
    *,
    bundle: DecisionQualityResearchBundle,
    funnel_stage_attribution: FunnelStageAnalyticsAttributionSet,
) -> FunnelDecisionQualityReport:
    _validate_inputs(bundle, funnel_stage_attribution)
    candidates = tuple(
        sorted(
            bundle.candidate_records,
            key=lambda item: (item.causal.observed_at, item.opportunity_id, item.record_id),
        )
    )
    candidate_by_id = {item.opportunity_id: item for item in candidates}
    records_by_candidate: dict[str, list[FunnelStageAnalyticsAttributionRecord]] = defaultdict(list)
    for record in funnel_stage_attribution.records:
        records_by_candidate[record.opportunity_id].append(record)

    observations_by_group: dict[
        tuple[FunnelStage, FunnelDecisionQualityDimension, str, bool], list[_Observation]
    ] = defaultdict(list)
    for candidate in candidates:
        records = tuple(
            sorted(
                records_by_candidate.get(candidate.opportunity_id, ()),
                key=lambda item: (
                    item.stage_order,
                    item.stage_instance_order if item.stage_instance_order is not None else -1,
                    item.stage_instance_id or "",
                    item.record_id,
                ),
            )
        )
        canonical_direction = _canonical_direction(candidate, records)
        for stage_record in records:
            observation = _Observation(
                candidate, stage_record, _stage_direction(stage_record.stage, canonical_direction)
            )
            for dimension, key, multi_valued in _cohort_specs(stage_record):
                observations_by_group[(stage_record.stage, dimension, key, multi_valued)].append(
                    observation
                )

    cohorts = tuple(
        _make_cohort(
            stage=stage,
            dimension=dimension,
            key=key,
            multi_valued=multi_valued,
            observations=tuple(items),
        )
        for (stage, dimension, key, multi_valued), items in sorted(
            observations_by_group.items(),
            key=lambda item: (
                _STAGE_ORDER[item[0][0]],
                _DIMENSION_ORDER[item[0][1]],
                item[0][2],
                item[0][3],
            ),
        )
    )
    stage_coverage = _stage_coverage(candidates, funnel_stage_attribution.records)
    coverage = FunnelDecisionQualityCoverage(
        candidate_count=len(candidates),
        candidates_with_future_outcome=sum(
            item.posthoc.future_outcome is not None for item in candidates
        ),
        candidates_without_future_outcome=sum(
            item.posthoc.future_outcome is None for item in candidates
        ),
        candidates_with_analytics=sum(
            item.causal.analytics.status == "MATCHED" for item in candidates
        ),
        candidates_without_analytics=sum(
            item.causal.analytics.status != "MATCHED" for item in candidates
        ),
        stages=stage_coverage,
    )
    contrasts = _contrasts(cohorts)
    source = bundle.research_run.source
    identity_payload = {
        "schema": FUNNEL_DECISION_QUALITY_REPORT_SCHEMA_VERSION,
        "policy": FUNNEL_DECISION_QUALITY_POLICY_VERSION,
        "research_run_id": bundle.research_run.research_run_id,
        "source_bundle_fingerprint": bundle.bundle_fingerprint,
        "source_funnel_stage_set_fingerprint": funnel_stage_attribution.set_fingerprint,
    }
    report_id = stable_uuid("funnel-decision-quality-report", identity_payload)
    report_fingerprint = stable_digest(
        {
            **identity_payload,
            "source_decision_record_set_fingerprint": (
                funnel_stage_attribution.source_decision_record_set_fingerprint
            ),
            "candidate_count": len(candidates),
            "coverage": coverage.model_dump(mode="python"),
            "cohorts": tuple(item.cohort_fingerprint for item in cohorts),
            "contrasts": tuple(item.model_dump(mode="python") for item in contrasts),
        }
    )
    return FunnelDecisionQualityReport(
        report_id=report_id,
        research_run_id=bundle.research_run.research_run_id,
        source_backtest_run_id=source.source_backtest_run_id,
        analytics_run_id=source.analytics_run_id,
        period_role=source.period_role,
        source_bundle_fingerprint=bundle.bundle_fingerprint,
        source_funnel_stage_set_fingerprint=funnel_stage_attribution.set_fingerprint,
        source_decision_record_set_fingerprint=funnel_stage_attribution.source_decision_record_set_fingerprint,
        candidate_count=len(candidate_by_id),
        coverage=coverage,
        cohorts=cohorts,
        contrasts=contrasts,
        report_fingerprint=report_fingerprint,
    )


__all__ = [
    "AlignedOutcome",
    "DirectionalFirstHit",
    "DirectionalOutcomeStats",
    "DirectionlessOutcomeStats",
    "FUNNEL_DECISION_QUALITY_COHORT_SCHEMA_VERSION",
    "FUNNEL_DECISION_QUALITY_CONTRAST_SCHEMA_VERSION",
    "FUNNEL_DECISION_QUALITY_POLICY_VERSION",
    "FUNNEL_DECISION_QUALITY_REPORT_SCHEMA_VERSION",
    "FunnelDecisionQualityCohort",
    "FunnelDecisionQualityContrast",
    "FunnelDecisionQualityContrastHorizon",
    "FunnelDecisionQualityContrastKind",
    "FunnelDecisionQualityCoverage",
    "FunnelDecisionQualityDimension",
    "FunnelDecisionQualityError",
    "FunnelDecisionQualityReport",
    "FunnelStageCoverage",
    "align_outcome_to_direction",
    "build_funnel_decision_quality_report",
]
