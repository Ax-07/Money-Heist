from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from app.evaluation.forward_outcomes import DEFAULT_FORWARD_HORIZONS
from app.evaluation.scanner_forward_outcomes import (
    ScannerForwardOutcomeReference,
    ScannerForwardOutcomeReport,
    ScannerOutcomeClassification,
    compute_scanner_forward_outcomes,
)
from app.market.multitimeframe import timeframe_interval

from .forward_outcomes import (
    build_outcome_decision_candles,
    resolve_outcome_decision_timeframe,
)


def _value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _classification(scan_result: Any) -> ScannerOutcomeClassification:
    triggers = tuple(getattr(scan_result, "triggers", ()) or ())
    opportunity = getattr(scan_result, "opportunity", None)
    if opportunity is not None:
        return ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY
    if triggers:
        return ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD
    return ScannerOutcomeClassification.NO_TRIGGER


def _references(
    replay_result: Any,
    *,
    min_priority_score: int,
) -> tuple[ScannerForwardOutcomeReference, ...]:
    output: list[ScannerForwardOutcomeReference] = []
    for point in replay_result.points:
        scan_result = getattr(point, "scan_result", None)
        feature = getattr(point, "feature_snapshot", None)
        if scan_result is None or feature is None:
            raise ValueError(
                "Scanner Forward Outcomes require scan_result and feature_snapshot "
                "for every replay point"
            )

        score = int(scan_result.score)
        triggers = tuple(
            sorted(
                {
                    text
                    for item in tuple(getattr(scan_result, "triggers", ()) or ())
                    if (text := _value(item)) is not None
                }
            )
        )
        opportunity = getattr(scan_result, "opportunity", None)
        snapshot_id = str(feature.snapshot_id)
        candidate_id = None
        if opportunity is not None:
            candidate_id = str(opportunity.opportunity_id)
            if int(opportunity.priority_score) != score:
                raise ValueError(
                    "CandidateOpportunity.priority_score must match ScanResult.score"
                )
            if str(opportunity.snapshot_id) != snapshot_id:
                raise ValueError(
                    "CandidateOpportunity.snapshot_id must match FeatureSnapshot"
                )

        output.append(
            ScannerForwardOutcomeReference(
                scan_id=snapshot_id,
                snapshot_id=snapshot_id,
                observed_at=point.observed_at,
                reference_close=Decimal(str(feature.close)),
                classification=_classification(scan_result),
                score=score,
                min_priority_score=min_priority_score,
                score_margin_to_threshold=score - min_priority_score,
                triggers=triggers,
                market_regime=_value(getattr(feature, "regime", None)),
                candidate_opportunity_id=candidate_id,
            )
        )
    return tuple(output)


def build_scanner_forward_outcomes_report(
    replay_result: Any,
    candles: Sequence[Any],
    decision_funnel: Any,
    *,
    scanner_version: str,
    min_priority_score: int,
    horizons: Sequence[int] = DEFAULT_FORWARD_HORIZONS,
) -> ScannerForwardOutcomeReport:
    """Cover every Scanner evaluation, including points below candidate creation."""

    run = replay_result.backtest_result.run
    if decision_funnel.run_id != run.run_id:
        raise ValueError("Decision Funnel run_id does not match replay")
    if decision_funnel.dataset_id != run.dataset.dataset_id:
        raise ValueError("Decision Funnel dataset_id does not match replay")
    if decision_funnel.system_id != run.config.system_id:
        raise ValueError("Decision Funnel system_id does not match replay")
    if str(run.config.scanner_version) != str(scanner_version):
        raise ValueError("scanner_version does not match BacktestConfig")

    decision_timeframe = resolve_outcome_decision_timeframe(replay_result)
    decision_candles = build_outcome_decision_candles(
        replay_result=replay_result,
        candles=candles,
        decision_timeframe=decision_timeframe,
    )
    report = compute_scanner_forward_outcomes(
        run_id=run.run_id,
        dataset_id=run.dataset.dataset_id,
        dataset_version=run.dataset.version,
        dataset_content_sha256=run.dataset.content_sha256,
        dataset_source=run.dataset.source,
        system_id=run.config.system_id,
        scanner_version=str(scanner_version),
        min_priority_score=int(min_priority_score),
        source_timeframe=run.dataset.timeframe,
        decision_timeframe=decision_timeframe,
        period_start=run.period_start,
        period_end=run.period_end,
        references=_references(
            replay_result,
            min_priority_score=int(min_priority_score),
        ),
        decision_candles=decision_candles,
        decision_interval=timeframe_interval(decision_timeframe),
        horizons=horizons,
    )

    counts = decision_funnel.counts
    expected_below = int(counts.scanner_triggered) - int(
        counts.candidate_opportunities
    )
    if expected_below < 0:
        raise ValueError("Decision Funnel candidate count exceeds scanner_triggered")
    expected = (
        int(counts.scanner_evaluations),
        int(counts.scanner_no_trigger),
        expected_below,
        int(counts.candidate_opportunities),
    )
    actual = (
        report.summary.scanner_evaluations,
        report.summary.no_trigger,
        report.summary.trigger_below_candidate_threshold,
        report.summary.candidate_opportunities,
    )
    if actual != expected:
        raise ValueError(
            "Scanner Forward Outcomes do not conserve Decision Funnel Scanner counts"
        )
    return report


__all__ = [
    "ScannerForwardOutcomeReport",
    "build_scanner_forward_outcomes_report",
]
