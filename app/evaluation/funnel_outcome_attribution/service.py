from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from app.evaluation.forward_outcomes import ForwardOutcomeRecord, ForwardOutcomeReport

from .models import (
    FunnelAttributionDimension,
    FunnelOutcomeAttributionCoverage,
    FunnelOutcomeAttributionReport,
    FunnelOutcomeDimensionCoverage,
    FunnelOutcomeGroup,
    FunnelOutcomeHorizonStats,
    FunnelOutcomeSubject,
)

_MULTI_VALUED = {
    FunnelAttributionDimension.SCANNER_TRIGGER,
    FunnelAttributionDimension.SELECTED_AGENT,
    FunnelAttributionDimension.RISK_REASON,
}


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


def _sign_counts(values: list[Decimal]) -> tuple[int, int, int]:
    positive = sum(1 for item in values if item > 0)
    negative = sum(1 for item in values if item < 0)
    flat = len(values) - positive - negative
    return positive, negative, flat


def _direction(subject: FunnelOutcomeSubject) -> str | None:
    if subject.proposal_side in {"LONG", "SHORT"}:
        return subject.proposal_side
    if subject.professor_direction in {"LONG", "SHORT"}:
        return subject.professor_direction
    return None


def _dimension_values(
    subject: FunnelOutcomeSubject,
    dimension: FunnelAttributionDimension,
) -> tuple[str, ...]:
    if dimension is FunnelAttributionDimension.TERMINAL_STATUS:
        return (subject.terminal_status,)
    if dimension is FunnelAttributionDimension.MARKET_REGIME:
        return (subject.market_regime,) if subject.market_regime else ()
    if dimension is FunnelAttributionDimension.SCANNER_TRIGGER:
        return subject.scanner_triggers
    if dimension is FunnelAttributionDimension.COMPUTE_GATE_REASON:
        return (subject.compute_gate_reason,) if subject.compute_gate_reason else ()
    if dimension is FunnelAttributionDimension.PROFESSOR_PLAN_DECISION:
        return (
            (subject.professor_plan_decision,)
            if subject.professor_plan_decision
            else ()
        )
    if dimension is FunnelAttributionDimension.SELECTED_AGENT:
        return subject.selected_agents
    if dimension is FunnelAttributionDimension.ORCHESTRATION_FAILURE:
        return (
            (subject.orchestration_failure_code,)
            if subject.orchestration_failure_code
            else ()
        )
    if dimension is FunnelAttributionDimension.PROFESSOR_DIRECTION:
        return (subject.professor_direction,) if subject.professor_direction else ()
    if dimension is FunnelAttributionDimension.PROPOSAL_SIDE:
        return (subject.proposal_side,) if subject.proposal_side else ()
    if dimension is FunnelAttributionDimension.RISK_STATUS:
        return (subject.risk_status,) if subject.risk_status else ()
    if dimension is FunnelAttributionDimension.RISK_REASON:
        return subject.risk_reason_codes
    if dimension is FunnelAttributionDimension.PAPER_PIPELINE_FAILURE:
        return (
            (subject.paper_pipeline_failure_code,)
            if subject.paper_pipeline_failure_code
            else ()
        )
    raise AssertionError(f"unsupported dimension: {dimension}")


def _horizon_stats(
    pairs: list[tuple[FunnelOutcomeSubject, ForwardOutcomeRecord]],
    horizon_bars: int,
) -> FunnelOutcomeHorizonStats:
    outcomes = []
    for subject, record in pairs:
        horizon = next(
            item for item in record.horizons if item.horizon_bars == horizon_bars
        )
        outcomes.append((subject, horizon))

    complete = [(subject, item) for subject, item in outcomes if item.is_complete]
    raw_returns = [item.return_pct for _, item in complete]
    raw_upside = [item.max_upside_pct for _, item in complete]
    raw_downside = [item.max_downside_pct for _, item in complete]
    if any(item is None for item in raw_returns + raw_upside + raw_downside):
        raise ValueError("complete Forward Outcome contains missing price metrics")
    raw_returns = [item for item in raw_returns if item is not None]
    raw_upside = [item for item in raw_upside if item is not None]
    raw_downside = [item for item in raw_downside if item is not None]

    directional_returns: list[Decimal] = []
    favorable_excursions: list[Decimal] = []
    adverse_excursions: list[Decimal] = []
    zero = Decimal("0")
    for subject, item in complete:
        direction = _direction(subject)
        if direction is None:
            continue
        assert item.return_pct is not None
        assert item.max_upside_pct is not None
        assert item.max_downside_pct is not None
        if direction == "LONG":
            directional_returns.append(item.return_pct)
            favorable_excursions.append(max(zero, item.max_upside_pct))
            adverse_excursions.append(max(zero, -item.max_downside_pct))
        else:
            directional_returns.append(-item.return_pct)
            favorable_excursions.append(max(zero, -item.max_downside_pct))
            adverse_excursions.append(max(zero, item.max_upside_pct))

    raw_positive, raw_negative, raw_flat = _sign_counts(raw_returns)
    dir_positive, dir_negative, dir_flat = _sign_counts(directional_returns)
    return FunnelOutcomeHorizonStats(
        horizon_bars=horizon_bars,
        opportunity_count=len(pairs),
        complete_count=len(complete),
        incomplete_count=len(pairs) - len(complete),
        raw_return_mean_pct=_mean(raw_returns),
        raw_return_median_pct=_median(raw_returns),
        raw_positive_count=raw_positive,
        raw_negative_count=raw_negative,
        raw_flat_count=raw_flat,
        max_upside_mean_pct=_mean(raw_upside),
        max_upside_median_pct=_median(raw_upside),
        max_downside_mean_pct=_mean(raw_downside),
        max_downside_median_pct=_median(raw_downside),
        directional_count=len(directional_returns),
        directional_return_mean_pct=_mean(directional_returns),
        directional_return_median_pct=_median(directional_returns),
        directional_positive_count=dir_positive,
        directional_negative_count=dir_negative,
        directional_flat_count=dir_flat,
        favorable_excursion_mean_pct=_mean(favorable_excursions),
        favorable_excursion_median_pct=_median(favorable_excursions),
        adverse_excursion_mean_pct=_mean(adverse_excursions),
        adverse_excursion_median_pct=_median(adverse_excursions),
    )


def aggregate_funnel_outcome_attribution(
    *,
    forward_outcomes: ForwardOutcomeReport,
    subjects: Iterable[FunnelOutcomeSubject],
    candidate_opportunity_count: int,
) -> FunnelOutcomeAttributionReport:
    """Cross candidate-stage funnel metadata with already-computed Forward Outcomes.

    This is descriptive post-hoc analysis. It never invokes Scanner, agents, Risk,
    broker, lifecycle, or any market-data provider.
    """

    ordered_subjects = tuple(
        sorted(subjects, key=lambda item: (item.observed_at, item.opportunity_id))
    )
    if candidate_opportunity_count != len(ordered_subjects):
        raise ValueError("candidate_opportunity_count does not match subject count")
    subject_by_id = {item.opportunity_id: item for item in ordered_subjects}
    if len(subject_by_id) != len(ordered_subjects):
        raise ValueError("subject opportunity ids must be unique")

    outcome_by_id = {item.opportunity_id: item for item in forward_outcomes.records}
    if len(outcome_by_id) != len(forward_outcomes.records):
        raise ValueError("Forward Outcome opportunity ids must be unique")
    if set(subject_by_id) != set(outcome_by_id):
        raise ValueError(
            "Funnel subjects and Forward Outcomes must cover the same opportunities"
        )

    for opportunity_id, subject in subject_by_id.items():
        record = outcome_by_id[opportunity_id]
        if subject.observed_at != record.observed_at:
            raise ValueError("subject observed_at does not match Forward Outcome")
        if subject.terminal_status != record.terminal_status:
            raise ValueError("subject terminal_status does not match Forward Outcome")
        if subject.professor_direction != record.professor_direction:
            raise ValueError("subject professor_direction does not match Forward Outcome")
        if subject.proposal_side != record.proposal_side:
            raise ValueError("subject proposal_side does not match Forward Outcome")

    dimensions = tuple(FunnelAttributionDimension)
    grouped: dict[
        tuple[FunnelAttributionDimension, str],
        list[tuple[FunnelOutcomeSubject, ForwardOutcomeRecord]],
    ] = defaultdict(list)
    coverage: list[FunnelOutcomeDimensionCoverage] = []

    for dimension in dimensions:
        represented_ids: set[str] = set()
        keys: set[str] = set()
        for subject in ordered_subjects:
            values = _dimension_values(subject, dimension)
            if values:
                represented_ids.add(subject.opportunity_id)
            for value in values:
                keys.add(value)
                grouped[(dimension, value)].append(
                    (subject, outcome_by_id[subject.opportunity_id])
                )
        coverage.append(
            FunnelOutcomeDimensionCoverage(
                dimension=dimension,
                represented_opportunities=len(represented_ids),
                missing_opportunities=len(ordered_subjects) - len(represented_ids),
                group_count=len(keys),
                multi_valued=dimension in _MULTI_VALUED,
            )
        )

    groups = []
    for (dimension, key), pairs in sorted(
        grouped.items(), key=lambda item: (item[0][0].value, item[0][1])
    ):
        groups.append(
            FunnelOutcomeGroup(
                dimension=dimension,
                key=key,
                opportunity_count=len(pairs),
                horizons=tuple(
                    _horizon_stats(pairs, horizon)
                    for horizon in forward_outcomes.horizons
                ),
            )
        )

    return FunnelOutcomeAttributionReport(
        run_id=forward_outcomes.run_id,
        dataset_id=forward_outcomes.dataset_id,
        dataset_version=forward_outcomes.dataset_version,
        system_id=forward_outcomes.system_id,
        period_start=forward_outcomes.period_start,
        period_end=forward_outcomes.period_end,
        horizons=forward_outcomes.horizons,
        coverage=FunnelOutcomeAttributionCoverage(
            candidate_opportunities=candidate_opportunity_count,
            forward_outcome_records=len(forward_outcomes.records),
            scanner_no_trigger_outcomes_available=False,
            scanner_below_candidate_threshold_outcomes_available=False,
        ),
        dimension_coverage=tuple(
            sorted(coverage, key=lambda item: item.dimension.value)
        ),
        subjects=ordered_subjects,
        groups=tuple(groups),
    )


__all__ = ["aggregate_funnel_outcome_attribution"]
