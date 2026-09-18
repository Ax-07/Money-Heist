from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.common.canonical import stable_digest
from app.evaluation.decision_quality.models import (
    AnalyticsResearchRef,
    CandidateJoinCoverage,
    DecisionQualityResearchBundle,
    DecisionQualityResearchRun,
    ResearchJoinIssue,
    ResearchJoinStatus,
    ResearchOutcomeDefinition,
    ResearchSourceIdentity,
    ScannerCausalBlock,
    ScannerJoinCoverage,
    ScannerPosthocBlock,
    ScannerResearchProjection,
    ScannerResearchRecord,
)
from app.evaluation.decision_quality.scanner_filtering import (
    BELOW_THRESHOLD,
    CANDIDATE,
    NO_TRIGGER,
    ScannerFilteringContrastKind,
    ScannerFilteringDimension,
    ScannerFilteringQualityError,
    build_scanner_filtering_quality_report,
)
from app.evaluation.forward_outcomes.models import (
    ForwardOutcomeFirstHit,
    ForwardOutcomeHorizon,
    ForwardOutcomeIncompleteReason,
)
from app.evaluation.scanner_forward_outcomes.models import ScannerForwardOutcomeRecord
from app.evaluation.scanner_observations import ScannerOutcomeClassification

START = datetime(2026, 1, 1, tzinfo=UTC)
HORIZONS = (1, 3, 5, 10, 20)


def complete_horizon(
    horizon: int,
    *,
    return_pct: str,
    max_upside_pct: str,
    max_downside_pct: str,
    first_hit: ForwardOutcomeFirstHit = ForwardOutcomeFirstHit.MAX_UPSIDE,
) -> ForwardOutcomeHorizon:
    upside_at = START + timedelta(hours=horizon)
    downside_at = upside_at + timedelta(minutes=1)
    first_hit_at = upside_at
    if first_hit is ForwardOutcomeFirstHit.MAX_DOWNSIDE:
        downside_at = START + timedelta(hours=horizon)
        upside_at = downside_at + timedelta(minutes=1)
        first_hit_at = downside_at
    elif first_hit is ForwardOutcomeFirstHit.SAME_CANDLE:
        downside_at = upside_at
        first_hit_at = upside_at
    return ForwardOutcomeHorizon(
        horizon_bars=horizon,
        is_complete=True,
        bars_observed=horizon,
        gap_count=0,
        boundary_missing_bars=0,
        missing_close_times=(),
        expected_end_at=START + timedelta(hours=horizon),
        return_pct=Decimal(return_pct),
        max_upside_pct=Decimal(max_upside_pct),
        max_downside_pct=Decimal(max_downside_pct),
        max_upside_at=upside_at,
        max_downside_at=downside_at,
        first_hit=first_hit,
        first_hit_at=first_hit_at,
    )


def incomplete_horizon(horizon: int) -> ForwardOutcomeHorizon:
    return ForwardOutcomeHorizon(
        horizon_bars=horizon,
        is_complete=False,
        bars_observed=max(horizon - 1, 0),
        gap_count=0,
        boundary_missing_bars=1,
        missing_close_times=(),
        expected_end_at=START + timedelta(hours=horizon),
        incomplete_reason=ForwardOutcomeIncompleteReason.PERIOD_END,
    )


def incomplete_horizon_with_reason(
    horizon: int,
    reason: ForwardOutcomeIncompleteReason,
) -> ForwardOutcomeHorizon:
    gap = reason in {
        ForwardOutcomeIncompleteReason.GAP,
        ForwardOutcomeIncompleteReason.GAP_AND_PERIOD_END,
    }
    period_end = reason in {
        ForwardOutcomeIncompleteReason.PERIOD_END,
        ForwardOutcomeIncompleteReason.GAP_AND_PERIOD_END,
    }
    missing_time = START + timedelta(hours=horizon)
    return ForwardOutcomeHorizon(
        horizon_bars=horizon,
        is_complete=False,
        bars_observed=horizon - int(gap) - int(period_end),
        gap_count=int(gap),
        boundary_missing_bars=int(period_end),
        missing_close_times=(missing_time,) if gap else (),
        expected_end_at=missing_time,
        incomplete_reason=reason,
    )


def outcome(
    *,
    scan_id: str,
    classification: ScannerOutcomeClassification,
    score: int,
    threshold: int,
    triggers: tuple[str, ...],
    market_regime: str | None,
    opportunity_id: str | None,
    return_pct: str,
    max_upside_pct: str,
    max_downside_pct: str,
    first_hit: ForwardOutcomeFirstHit = ForwardOutcomeFirstHit.MAX_UPSIDE,
    incomplete: tuple[int, ...] = (),
) -> ScannerForwardOutcomeRecord:
    horizons = tuple(
        incomplete_horizon(horizon)
        if horizon in incomplete
        else complete_horizon(
            horizon,
            return_pct=return_pct,
            max_upside_pct=max_upside_pct,
            max_downside_pct=max_downside_pct,
            first_hit=first_hit,
        )
        for horizon in HORIZONS
    )
    return ScannerForwardOutcomeRecord(
        scan_id=scan_id,
        snapshot_id=scan_id,
        observed_at=START + timedelta(hours=int(scan_id.split("-")[-1])),
        reference_close=Decimal("100"),
        classification=classification,
        score=score,
        min_priority_score=threshold,
        score_margin_to_threshold=score - threshold,
        triggers=triggers,
        market_regime=market_regime,
        candidate_opportunity_id=opportunity_id,
        horizons=horizons,
    )


def scanner_record(
    *,
    index: int,
    classification: ScannerOutcomeClassification,
    score: int,
    triggers: tuple[str, ...],
    market_regime: str | None,
    outcome_record: ScannerForwardOutcomeRecord | None,
    analytics_matched: bool = True,
) -> ScannerResearchRecord:
    scan_id = f"scan-{index}"
    opportunity_id = (
        f"opp-{index}"
        if classification is ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY
        else None
    )
    source = ResearchSourceIdentity(
        source_backtest_run_id="run-oos",
        analytics_run_id="analytics-oos",
        period_role="OOS",
        dataset_id="dataset-1",
        dataset_version="v1",
        dataset_content_sha256="a" * 64,
        dataset_source="fixture",
        system_id="balanced_v1",
        symbol="BTC/EUR",
        source_timeframe="1h",
        decision_timeframe="1h",
    )
    scanner = ScannerResearchProjection(
        scanner_evaluation_id=scan_id,
        snapshot_id=scan_id,
        classification=classification.value,
        score=score,
        candidate_threshold=35,
        score_margin=score - 35,
        triggers=triggers,
        market_regime=market_regime,
        candidate_opportunity_id=opportunity_id,
    )
    analytics = AnalyticsResearchRef(
        attribution_record_id=f"analytics-{index}",
        attribution_record_fingerprint=stable_digest({"analytics": index}),
        analytics_run_id="analytics-oos",
        status="MATCHED" if analytics_matched else "MISSING_ANALYTICS_SNAPSHOT",
        analytics_snapshot_id=f"snapshot-{index}" if analytics_matched else None,
        analytics_snapshot_fingerprint=(
            stable_digest({"snapshot": index}) if analytics_matched else None
        ),
        analytics_as_of=START + timedelta(hours=index) if analytics_matched else None,
        diagnostics=() if analytics_matched else ("missing",),
    )
    causal = ScannerCausalBlock(
        source=source,
        scan_id=scan_id,
        observed_at=START + timedelta(hours=index),
        scanner=scanner,
        analytics=analytics,
        causal_fingerprint=stable_digest({"causal": index, "score": score}),
    )
    posthoc = ScannerPosthocBlock(
        future_outcome=outcome_record,
        outcome_fingerprint=(
            None
            if outcome_record is None
            else stable_digest(outcome_record.model_dump(mode="python"))
        ),
    )
    issues = []
    if outcome_record is None:
        issues.append(ResearchJoinIssue.MISSING_FORWARD_OUTCOME)
    if not analytics_matched:
        issues.append(ResearchJoinIssue.MISSING_ANALYTICS)
    issues_tuple = tuple(sorted(issues, key=lambda item: item.value))
    status = ResearchJoinStatus.MATCHED
    if ResearchJoinIssue.MISSING_FORWARD_OUTCOME in issues_tuple:
        status = ResearchJoinStatus.MISSING_FORWARD_OUTCOME
    elif ResearchJoinIssue.MISSING_ANALYTICS in issues_tuple:
        status = ResearchJoinStatus.MISSING_ANALYTICS
    fingerprint = stable_digest(
        {
            "causal": causal.causal_fingerprint,
            "posthoc": posthoc.outcome_fingerprint,
            "issues": issues_tuple,
        }
    )
    return ScannerResearchRecord(
        research_run_id="research-oos",
        record_id=f"record-{index}",
        record_fingerprint=fingerprint,
        period_role="OOS",
        scan_id=scan_id,
        causal=causal,
        posthoc=posthoc,
        join_status=status,
        join_issues=issues_tuple,
    )


def build_bundle(*, candidate_return_override: str | None = None) -> DecisionQualityResearchBundle:
    specs = [
        # N=2 NO_TRIGGER, one without outcome.
        (
            0,
            ScannerOutcomeClassification.NO_TRIGGER,
            0,
            (),
            "RANGE",
            "0",
            "0",
            "0",
            ForwardOutcomeFirstHit.SAME_CANDLE,
            (),
            True,
            True,
        ),
        (
            1,
            ScannerOutcomeClassification.NO_TRIGGER,
            0,
            (),
            None,
            "0",
            "0",
            "0",
            ForwardOutcomeFirstHit.SAME_CANDLE,
            (),
            False,
            True,
        ),
        # N=2 below threshold. First scan has two triggers to prove multi-valued semantics.
        (
            2,
            ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD,
            33,
            ("RANGE_BREAK", "VOLUME_EXPANSION"),
            "RANGE",
            "-1",
            "2",
            "-1",
            ForwardOutcomeFirstHit.MAX_DOWNSIDE,
            (),
            True,
            True,
        ),
        (
            3,
            ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD,
            34,
            ("RANGE_BREAK",),
            "TREND",
            "1",
            "4",
            "-2",
            ForwardOutcomeFirstHit.MAX_UPSIDE,
            (),
            True,
            True,
        ),
        # N=2 candidate: max absolute excursions are 5 and 7 => mean/median 6.
        (
            4,
            ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY,
            35,
            ("RANGE_BREAK", "VOLUME_EXPANSION"),
            "TREND",
            candidate_return_override or "2",
            "3",
            "-5",
            ForwardOutcomeFirstHit.MAX_DOWNSIDE,
            (),
            True,
            False,
        ),
        (
            5,
            ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY,
            36,
            ("VOLUME_EXPANSION",),
            "TREND",
            "4",
            "7",
            "-2",
            ForwardOutcomeFirstHit.MAX_UPSIDE,
            (20,),
            True,
            True,
        ),
    ]
    records = []
    for (
        index,
        classification,
        score,
        triggers,
        regime,
        return_pct,
        max_upside,
        max_downside,
        first_hit,
        incomplete,
        has_outcome,
        analytics_matched,
    ) in specs:
        scan_id = f"scan-{index}"
        opportunity_id = (
            f"opp-{index}"
            if classification is ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY
            else None
        )
        out = None
        if has_outcome:
            out = outcome(
                scan_id=scan_id,
                classification=classification,
                score=score,
                threshold=35,
                triggers=triggers,
                market_regime=regime,
                opportunity_id=opportunity_id,
                return_pct=return_pct,
                max_upside_pct=max_upside,
                max_downside_pct=max_downside,
                first_hit=first_hit,
                incomplete=incomplete,
            )
        records.append(
            scanner_record(
                index=index,
                classification=classification,
                score=score,
                triggers=triggers,
                market_regime=regime,
                outcome_record=out,
                analytics_matched=analytics_matched,
            )
        )

    source = records[0].causal.source
    research_run = DecisionQualityResearchRun(
        research_run_id="research-oos",
        run_fingerprint=stable_digest({"run": "research-oos"}),
        source=source,
        outcome_definition=ResearchOutcomeDefinition(
            forward_outcome_schema_version="money-heist.forward-outcomes.v1",
            forward_outcome_policy_version="money-heist.forward-outcomes.close-ohlc.v1",
            scanner_forward_outcome_schema_version="money-heist.scanner-forward-outcomes.v1",
            scanner_forward_outcome_policy_version=(
                "money-heist.scanner-forward-outcomes.close-ohlc.v1"
            ),
            horizons=HORIZONS,
        ),
    )
    ordered = tuple(sorted(records, key=lambda item: (item.causal.observed_at, item.scan_id)))
    coverage = ScannerJoinCoverage(
        total=len(ordered),
        joined=sum(item.join_status is ResearchJoinStatus.MATCHED for item in ordered),
        missing_forward_outcome=sum(
            ResearchJoinIssue.MISSING_FORWARD_OUTCOME in item.join_issues for item in ordered
        ),
        missing_analytics=sum(
            ResearchJoinIssue.MISSING_ANALYTICS in item.join_issues for item in ordered
        ),
    )
    return DecisionQualityResearchBundle(
        research_run=research_run,
        candidate_records=(),
        scanner_records=ordered,
        candidate_coverage=CandidateJoinCoverage(
            total=0,
            joined=0,
            missing_decision_intelligence=0,
            missing_forward_outcome=0,
            missing_analytics=0,
        ),
        scanner_coverage=coverage,
        bundle_fingerprint=stable_digest(tuple(item.record_fingerprint for item in ordered)),
    )


def cohort(report, dimension: ScannerFilteringDimension, key: str):
    return next(item for item in report.cohorts if item.dimension is dimension and item.key == key)




def test_classification_groups_use_stable_string_key_order() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    keys = [
        item.key
        for item in report.cohorts
        if item.dimension is ScannerFilteringDimension.CLASSIFICATION
    ]
    assert keys == sorted((NO_TRIGGER, BELOW_THRESHOLD, CANDIDATE))

def test_classification_counts_selection_rates_and_period_role() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    assert report.period_role == "OOS"
    assert report.scanner_count == 6
    assert report.classification_summary.no_trigger_count == 2
    assert report.classification_summary.below_threshold_count == 2
    assert report.classification_summary.candidate_count == 2
    assert report.classification_summary.triggered_count == 4
    assert report.classification_summary.candidate_rate == Decimal("2") / Decimal("6")


def test_directionless_max_absolute_excursion_and_even_mean_median() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    candidate = cohort(report, ScannerFilteringDimension.CLASSIFICATION, CANDIDATE)
    h10 = next(item for item in candidate.horizons if item.horizon_bars == 10)
    # (+3, -5) -> 5 and (+7, -2) -> 7. Direction is intentionally absent.
    assert h10.max_absolute_excursion_mean_pct == Decimal("6")
    assert h10.max_absolute_excursion_median_pct == Decimal("6")
    assert h10.raw_return_mean_pct == Decimal("3")
    assert h10.raw_return_median_pct == Decimal("3")


def test_incomplete_horizon_is_counted_but_excluded_from_price_stats() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    candidate = cohort(report, ScannerFilteringDimension.CLASSIFICATION, CANDIDATE)
    h20 = next(item for item in candidate.horizons if item.horizon_bars == 20)
    assert h20.outcome_available_count == 2
    assert h20.complete_count == 1
    assert h20.incomplete_count == 1
    assert h20.raw_return_mean_pct == Decimal("2")
    assert h20.max_absolute_excursion_mean_pct == Decimal("5")


def test_missing_outcome_stays_in_scanner_counts_and_out_of_price_stats() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    no_trigger = cohort(report, ScannerFilteringDimension.CLASSIFICATION, NO_TRIGGER)
    h10 = next(item for item in no_trigger.horizons if item.horizon_bars == 10)
    assert no_trigger.scanner_count == 2
    assert h10.outcome_available_count == 1
    assert h10.outcome_missing_count == 1
    assert h10.complete_count == 1
    assert report.coverage.with_future_outcome == 5
    assert report.coverage.without_future_outcome == 1


def test_analytics_missing_does_not_remove_valid_outcome() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    candidate = cohort(report, ScannerFilteringDimension.CLASSIFICATION, CANDIDATE)
    h10 = next(item for item in candidate.horizons if item.horizon_bars == 10)
    assert report.coverage.with_analytics == 5
    assert report.coverage.without_analytics == 1
    assert h10.complete_count == 2


def test_score_margin_is_numeric_and_sorted_not_lexical() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    margins = [
        item.numeric_value
        for item in report.cohorts
        if item.dimension is ScannerFilteringDimension.SCORE_MARGIN
    ]
    assert margins == [-35, -2, -1, 0, 1]
    assert all(
        item.key == str(item.numeric_value)
        for item in report.cohorts
        if item.dimension is ScannerFilteringDimension.SCORE_MARGIN
    )


def test_score_groups_only_observed_values() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    scores = [
        item.numeric_value
        for item in report.cohorts
        if item.dimension is ScannerFilteringDimension.SCORE
    ]
    assert scores == [0, 33, 34, 35, 36]
    assert 1 not in scores


def test_trigger_groups_are_multi_valued_and_not_conservative() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    trigger_groups = [
        item for item in report.cohorts if item.dimension is ScannerFilteringDimension.TRIGGER
    ]
    counts = {item.key: item.scanner_count for item in trigger_groups}
    assert counts == {"RANGE_BREAK": 3, "VOLUME_EXPANSION": 3}
    assert sum(counts.values()) == 6
    assert report.classification_summary.triggered_count == 4
    coverage = next(
        item
        for item in report.dimension_coverage
        if item.dimension is ScannerFilteringDimension.TRIGGER
    )
    assert coverage.multi_valued is True
    assert coverage.represented_scanner_count == 4
    assert coverage.missing_scanner_count == 2


def test_market_regime_none_is_missing_not_unknown_cohort() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    regimes = [
        item.key
        for item in report.cohorts
        if item.dimension is ScannerFilteringDimension.MARKET_REGIME
    ]
    assert regimes == ["RANGE", "TREND"]
    assert "UNKNOWN" not in regimes
    coverage = next(
        item
        for item in report.dimension_coverage
        if item.dimension is ScannerFilteringDimension.MARKET_REGIME
    )
    assert coverage.represented_scanner_count == 5
    assert coverage.missing_scanner_count == 1


def test_classification_contrasts_are_descriptive_deltas_only() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    contrast = next(
        item
        for item in report.contrasts
        if item.kind is ScannerFilteringContrastKind.CANDIDATE_VS_BELOW_THRESHOLD
    )
    h10 = next(item for item in contrast.horizons if item.horizon_bars == 10)
    assert contrast.left_classification == CANDIDATE
    assert contrast.right_classification == BELOW_THRESHOLD
    assert h10.median_raw_return_delta_pct == Decimal("3")
    assert h10.median_max_absolute_excursion_delta_pct == Decimal("3")
    assert "winner" not in type(contrast).model_fields


def test_first_hit_and_sign_conservation() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    candidate = cohort(report, ScannerFilteringDimension.CLASSIFICATION, CANDIDATE)
    h10 = next(item for item in candidate.horizons if item.horizon_bars == 10)
    assert h10.raw_positive_count + h10.raw_negative_count + h10.raw_flat_count == 2
    assert (
        h10.first_hit_upside_count
        + h10.first_hit_downside_count
        + h10.first_hit_same_candle_count
        == 2
    )
    assert h10.first_hit_upside_count == 1
    assert h10.first_hit_downside_count == 1


def test_zero_flat_excursion_is_zero() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    no_trigger = cohort(report, ScannerFilteringDimension.CLASSIFICATION, NO_TRIGGER)
    h10 = next(item for item in no_trigger.horizons if item.horizon_bars == 10)
    assert h10.raw_return_mean_pct == Decimal("0")
    assert h10.max_absolute_excursion_mean_pct == Decimal("0")
    assert h10.raw_flat_count == 1


def test_median_odd_uses_middle_complete_observation() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    range_break = cohort(report, ScannerFilteringDimension.TRIGGER, "RANGE_BREAK")
    h10 = next(item for item in range_break.horizons if item.horizon_bars == 10)
    assert h10.complete_count == 3
    assert h10.raw_return_median_pct == Decimal("1")
    assert h10.max_absolute_excursion_median_pct == Decimal("4")


def test_incomplete_reason_is_preserved_in_counts() -> None:
    report = build_scanner_filtering_quality_report(bundle=build_bundle())
    candidate = cohort(report, ScannerFilteringDimension.CLASSIFICATION, CANDIDATE)
    h20 = next(item for item in candidate.horizons if item.horizon_bars == 20)
    assert h20.incomplete_period_end_count == 1
    assert h20.incomplete_gap_count == 0
    assert h20.incomplete_gap_and_period_end_count == 0
    coverage_h20 = next(item for item in report.coverage.horizons if item.horizon_bars == 20)
    assert coverage_h20.incomplete_period_end_count == 1


def test_gap_and_gap_period_end_reasons_are_conserved() -> None:
    bundle = build_bundle()
    replacements = {
        "scan-2": ForwardOutcomeIncompleteReason.GAP,
        "scan-3": ForwardOutcomeIncompleteReason.GAP_AND_PERIOD_END,
    }
    records = []
    for record in bundle.scanner_records:
        reason = replacements.get(record.scan_id)
        if reason is None:
            records.append(record)
            continue
        outcome_record = record.posthoc.future_outcome
        assert outcome_record is not None
        horizons = tuple(
            incomplete_horizon_with_reason(20, reason)
            if item.horizon_bars == 20
            else item
            for item in outcome_record.horizons
        )
        updated_outcome = outcome_record.model_copy(update={"horizons": horizons})
        updated_posthoc = record.posthoc.model_copy(
            update={
                "future_outcome": updated_outcome,
                "outcome_fingerprint": stable_digest(
                    updated_outcome.model_dump(mode="python")
                ),
            }
        )
        records.append(
            record.model_copy(
                update={
                    "posthoc": updated_posthoc,
                    "record_fingerprint": stable_digest(
                        {
                            "record": record.record_id,
                            "posthoc": updated_posthoc.outcome_fingerprint,
                        }
                    ),
                }
            )
        )
    changed = tuple(records)
    changed_bundle = bundle.model_copy(
        update={
            "scanner_records": changed,
            "bundle_fingerprint": stable_digest(
                tuple(item.record_fingerprint for item in changed)
            ),
        }
    )
    report = build_scanner_filtering_quality_report(bundle=changed_bundle)
    below = cohort(
        report,
        ScannerFilteringDimension.CLASSIFICATION,
        BELOW_THRESHOLD,
    )
    h20 = next(item for item in below.horizons if item.horizon_bars == 20)
    assert h20.complete_count == 0
    assert h20.incomplete_count == 2
    assert h20.incomplete_gap_count == 1
    assert h20.incomplete_gap_and_period_end_count == 1
    assert h20.incomplete_period_end_count == 0
    assert h20.raw_return_mean_pct is None
    coverage_h20 = next(
        item for item in report.coverage.horizons if item.horizon_bars == 20
    )
    assert coverage_h20.incomplete_gap_count == 1
    assert coverage_h20.incomplete_gap_and_period_end_count == 1
    assert coverage_h20.incomplete_period_end_count == 1


def test_empty_classification_cohort_has_none_rates_not_false_zero_observations() -> None:
    base = build_bundle()
    records = tuple(
        item for item in base.scanner_records if item.causal.scanner.classification != NO_TRIGGER
    )
    coverage = ScannerJoinCoverage(
        total=len(records),
        joined=sum(item.join_status is ResearchJoinStatus.MATCHED for item in records),
        missing_forward_outcome=sum(
            ResearchJoinIssue.MISSING_FORWARD_OUTCOME in item.join_issues for item in records
        ),
        missing_analytics=sum(
            ResearchJoinIssue.MISSING_ANALYTICS in item.join_issues for item in records
        ),
    )
    bundle = DecisionQualityResearchBundle(
        research_run=base.research_run,
        candidate_records=(),
        scanner_records=records,
        candidate_coverage=CandidateJoinCoverage(
            total=0,
            joined=0,
            missing_decision_intelligence=0,
            missing_forward_outcome=0,
            missing_analytics=0,
        ),
        scanner_coverage=coverage,
        bundle_fingerprint=stable_digest(tuple(item.record_fingerprint for item in records)),
    )
    report = build_scanner_filtering_quality_report(bundle=bundle)
    empty = cohort(report, ScannerFilteringDimension.CLASSIFICATION, NO_TRIGGER)
    h10 = next(item for item in empty.horizons if item.horizon_bars == 10)
    assert empty.scanner_count == 0
    assert empty.classification_summary.no_trigger_rate is None
    assert h10.complete_rate is None
    assert h10.positive_rate is None
    assert h10.first_hit_upside_rate is None


def test_policy_mismatch_fails_closed() -> None:
    bundle = build_bundle().model_copy(update={"policy_version": "future-policy-v2"})
    with pytest.raises(
        ScannerFilteringQualityError,
        match="unsupported Decision Quality bundle policy",
    ):
        build_scanner_filtering_quality_report(bundle=bundle)


def test_deterministic_ordering_ids_fingerprints_and_json() -> None:
    bundle = build_bundle()
    first = build_scanner_filtering_quality_report(bundle=bundle)
    reversed_bundle = bundle.model_copy(
        update={"scanner_records": tuple(reversed(bundle.scanner_records))}
    )
    second = build_scanner_filtering_quality_report(bundle=reversed_bundle)
    assert first.report_id == second.report_id
    assert first.report_fingerprint == second.report_fingerprint
    assert first.to_json() == second.to_json()
    assert [item.cohort_fingerprint for item in first.cohorts] == [
        item.cohort_fingerprint for item in second.cohorts
    ]


def test_source_metric_change_changes_fingerprint_but_not_report_id() -> None:
    first = build_scanner_filtering_quality_report(bundle=build_bundle())
    second = build_scanner_filtering_quality_report(
        bundle=build_bundle(candidate_return_override="9")
    )
    assert first.report_id == second.report_id
    assert first.report_fingerprint != second.report_fingerprint


def test_builder_does_not_mutate_bundle_or_forward_outcomes() -> None:
    bundle = build_bundle()
    before = deepcopy(bundle.model_dump(mode="python"))
    outcome_before = deepcopy(
        bundle.scanner_records[0].posthoc.future_outcome.model_dump(mode="python")
    )
    build_scanner_filtering_quality_report(bundle=bundle)
    assert bundle.model_dump(mode="python") == before
    assert (
        bundle.scanner_records[0].posthoc.future_outcome.model_dump(mode="python")
        == outcome_before
    )
