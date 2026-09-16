from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any

from app.evaluation.forward_outcomes import (
    DEFAULT_FORWARD_HORIZONS,
    ForwardOutcomeFirstHit,
    ForwardOutcomeReference,
    ForwardOutcomeReport,
    compute_forward_outcomes,
)

from .models import (
    ScannerForwardOutcomeRecord,
    ScannerForwardOutcomeReference,
    ScannerForwardOutcomeReport,
    ScannerForwardOutcomeSummary,
    ScannerOutcomeClassification,
    ScannerOutcomeDimensionCoverage,
    ScannerOutcomeGroup,
    ScannerOutcomeGroupDimension,
    ScannerOutcomeHorizonStats,
)


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


def _dimension_values(
    record: ScannerForwardOutcomeRecord,
    dimension: ScannerOutcomeGroupDimension,
) -> tuple[str, ...]:
    if dimension is ScannerOutcomeGroupDimension.CLASSIFICATION:
        return (record.classification.value,)
    if dimension is ScannerOutcomeGroupDimension.SCORE:
        return (str(record.score),)
    if dimension is ScannerOutcomeGroupDimension.TRIGGER:
        return record.triggers
    if dimension is ScannerOutcomeGroupDimension.MARKET_REGIME:
        return (record.market_regime,) if record.market_regime is not None else ()
    raise AssertionError(f"unsupported scanner outcome dimension: {dimension}")


def _horizon_stats(
    records: list[ScannerForwardOutcomeRecord],
    horizon_bars: int,
) -> ScannerOutcomeHorizonStats:
    horizons = [
        next(item for item in record.horizons if item.horizon_bars == horizon_bars)
        for record in records
    ]
    complete = [item for item in horizons if item.is_complete]

    returns = [item.return_pct for item in complete]
    upside = [item.max_upside_pct for item in complete]
    downside = [item.max_downside_pct for item in complete]
    if any(item is None for item in returns + upside + downside):
        raise ValueError("complete Forward Outcome contains missing price metrics")
    returns = [item for item in returns if item is not None]
    upside = [item for item in upside if item is not None]
    downside = [item for item in downside if item is not None]

    positive, negative, flat = _sign_counts(returns)
    first_hits = Counter(item.first_hit for item in complete)
    return ScannerOutcomeHorizonStats(
        horizon_bars=horizon_bars,
        scanner_evaluation_count=len(records),
        complete_count=len(complete),
        incomplete_count=len(records) - len(complete),
        raw_return_mean_pct=_mean(returns),
        raw_return_median_pct=_median(returns),
        raw_positive_count=positive,
        raw_negative_count=negative,
        raw_flat_count=flat,
        max_upside_mean_pct=_mean(upside),
        max_upside_median_pct=_median(upside),
        max_downside_mean_pct=_mean(downside),
        max_downside_median_pct=_median(downside),
        first_hit_upside_count=first_hits[ForwardOutcomeFirstHit.MAX_UPSIDE],
        first_hit_downside_count=first_hits[ForwardOutcomeFirstHit.MAX_DOWNSIDE],
        first_hit_same_candle_count=first_hits[ForwardOutcomeFirstHit.SAME_CANDLE],
    )


def compute_scanner_forward_outcomes(
    *,
    run_id: str,
    dataset_id: str,
    dataset_version: str,
    dataset_content_sha256: str,
    dataset_source: str,
    system_id: str,
    scanner_version: str,
    min_priority_score: int,
    source_timeframe: str,
    decision_timeframe: str,
    period_start: Any,
    period_end: Any,
    references: Iterable[ScannerForwardOutcomeReference],
    decision_candles: Sequence[Any],
    decision_interval: Any,
    horizons: Sequence[int] = DEFAULT_FORWARD_HORIZONS,
) -> ScannerForwardOutcomeReport:
    """Measure every Scanner evaluation using the Batch 23A.2 market-outcome engine."""

    refs = tuple(
        sorted(references, key=lambda item: (item.observed_at, item.scan_id))
    )
    if any(item.min_priority_score != min_priority_score for item in refs):
        raise ValueError("reference threshold does not match report threshold")

    generic_refs = tuple(
        ForwardOutcomeReference(
            opportunity_id=item.scan_id,
            snapshot_id=item.snapshot_id,
            observed_at=item.observed_at,
            reference_close=item.reference_close,
            terminal_status=item.classification.value,
        )
        for item in refs
    )
    generic: ForwardOutcomeReport = compute_forward_outcomes(
        run_id=run_id,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        dataset_content_sha256=dataset_content_sha256,
        dataset_source=dataset_source,
        system_id=system_id,
        source_timeframe=source_timeframe,
        decision_timeframe=decision_timeframe,
        period_start=period_start,
        period_end=period_end,
        references=generic_refs,
        decision_candles=decision_candles,
        decision_interval=decision_interval,
        horizons=horizons,
    )
    generic_by_id = {item.opportunity_id: item for item in generic.records}
    if len(generic_by_id) != len(generic.records):
        raise ValueError("generic Forward Outcome ids must be unique")

    records = tuple(
        ScannerForwardOutcomeRecord(
            **reference.model_dump(mode="python"),
            horizons=generic_by_id[reference.scan_id].horizons,
        )
        for reference in refs
    )

    class_counts = Counter(item.classification for item in records)
    groups_by_key: dict[
        tuple[ScannerOutcomeGroupDimension, str],
        list[ScannerForwardOutcomeRecord],
    ] = defaultdict(list)
    coverage: list[ScannerOutcomeDimensionCoverage] = []

    for dimension in ScannerOutcomeGroupDimension:
        represented_ids: set[str] = set()
        keys: set[str] = set()
        for record in records:
            values = _dimension_values(record, dimension)
            if values:
                represented_ids.add(record.scan_id)
            for value in values:
                keys.add(value)
                groups_by_key[(dimension, value)].append(record)
        coverage.append(
            ScannerOutcomeDimensionCoverage(
                dimension=dimension,
                represented_scanner_evaluations=len(represented_ids),
                missing_scanner_evaluations=len(records) - len(represented_ids),
                group_count=len(keys),
                multi_valued=dimension is ScannerOutcomeGroupDimension.TRIGGER,
            )
        )

    groups = tuple(
        ScannerOutcomeGroup(
            dimension=dimension,
            key=key,
            scanner_evaluation_count=len(group_records),
            horizons=tuple(
                _horizon_stats(group_records, horizon)
                for horizon in generic.horizons
            ),
        )
        for (dimension, key), group_records in sorted(
            groups_by_key.items(),
            key=lambda item: (item[0][0].value, item[0][1]),
        )
    )

    return ScannerForwardOutcomeReport(
        run_id=run_id,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        dataset_content_sha256=dataset_content_sha256,
        dataset_source=dataset_source,
        system_id=system_id,
        scanner_version=scanner_version,
        min_priority_score=min_priority_score,
        source_timeframe=source_timeframe,
        decision_timeframe=decision_timeframe,
        period_start=period_start,
        period_end=period_end,
        horizons=generic.horizons,
        summary=ScannerForwardOutcomeSummary(
            scanner_evaluations=len(records),
            no_trigger=class_counts[ScannerOutcomeClassification.NO_TRIGGER],
            trigger_below_candidate_threshold=class_counts[
                ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD
            ],
            candidate_opportunities=class_counts[
                ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY
            ],
            horizon_counts=generic.summary.horizon_counts,
        ),
        dimension_coverage=tuple(
            sorted(coverage, key=lambda item: item.dimension.value)
        ),
        records=records,
        groups=groups,
    )


__all__ = ["compute_scanner_forward_outcomes"]
