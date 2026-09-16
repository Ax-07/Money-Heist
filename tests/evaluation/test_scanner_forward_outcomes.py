from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.evaluation.scanner_forward_outcomes import (
    ScannerForwardOutcomeReference,
    ScannerOutcomeClassification,
    ScannerOutcomeGroupDimension,
    compute_scanner_forward_outcomes,
)


START = datetime(2026, 1, 1, tzinfo=UTC)
INTERVAL = timedelta(hours=1)


def candle(step: int, *, close: str, high: str, low: str):
    close_time = START + INTERVAL * step
    return SimpleNamespace(
        close_time=close_time,
        close=Decimal(close),
        high=Decimal(high),
        low=Decimal(low),
    )


def ref(
    scan_id: str,
    classification: ScannerOutcomeClassification,
    *,
    score: int,
    triggers: tuple[str, ...] = (),
    candidate: str | None = None,
    regime: str = "range",
):
    threshold = 35
    return ScannerForwardOutcomeReference(
        scan_id=scan_id,
        snapshot_id=f"snap-{scan_id}",
        observed_at=START,
        reference_close=Decimal("100"),
        classification=classification,
        score=score,
        min_priority_score=threshold,
        score_margin_to_threshold=score - threshold,
        triggers=tuple(sorted(triggers)),
        market_regime=regime,
        candidate_opportunity_id=candidate,
    )


def build(refs, *, period_end=None, horizons=(1, 3)):
    if period_end is None:
        period_end = START + INTERVAL * 3
    return compute_scanner_forward_outcomes(
        run_id="run-1",
        dataset_id="dataset-1",
        dataset_version="sha256:" + "a" * 64,
        dataset_content_sha256="a" * 64,
        dataset_source="fixture",
        system_id="balanced_v1",
        scanner_version="scanner-v1",
        min_priority_score=35,
        source_timeframe="1h",
        decision_timeframe="1h",
        period_start=START,
        period_end=period_end,
        references=refs,
        decision_candles=(
            candle(1, close="102", high="104", low="99"),
            candle(2, close="98", high="103", low="95"),
            candle(3, close="105", high="108", low="97"),
        ),
        decision_interval=INTERVAL,
        horizons=horizons,
    )


def group(report, dimension, key):
    return next(
        item
        for item in report.groups
        if item.dimension is dimension and item.key == key
    )


def test_scanner_outcomes_cover_all_three_scanner_classes():
    report = build(
        (
            ref(
                "scan-1",
                ScannerOutcomeClassification.NO_TRIGGER,
                score=0,
            ),
            ref(
                "scan-2",
                ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD,
                score=20,
                triggers=("volume_expansion",),
            ),
            ref(
                "scan-3",
                ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY,
                score=35,
                triggers=("range_break",),
                candidate="opp-3",
            ),
        )
    )

    assert report.summary.scanner_evaluations == 3
    assert report.summary.no_trigger == 1
    assert report.summary.trigger_below_candidate_threshold == 1
    assert report.summary.candidate_opportunities == 1
    assert [item.score_margin_to_threshold for item in report.records] == [
        -35,
        -15,
        0,
    ]


def test_exact_score_groups_expose_post_hoc_outcomes_without_score_bands():
    report = build(
        (
            ref(
                "scan-1",
                ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD,
                score=20,
                triggers=("volume_expansion",),
            ),
            ref(
                "scan-2",
                ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD,
                score=20,
                triggers=("volatility_expansion",),
            ),
        ),
        horizons=(1,),
    )

    score_20 = group(report, ScannerOutcomeGroupDimension.SCORE, "20")
    stats = score_20.horizons[0]
    assert score_20.scanner_evaluation_count == 2
    assert stats.complete_count == 2
    assert stats.raw_return_mean_pct == Decimal("2.00")
    assert stats.max_upside_mean_pct == Decimal("4.00")
    assert stats.max_downside_mean_pct == Decimal("-1.00")


def test_trigger_groups_are_multi_valued_and_do_not_claim_exclusive_counts():
    report = build(
        (
            ref(
                "scan-1",
                ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY,
                score=55,
                triggers=("range_break", "volume_expansion"),
                candidate="opp-1",
            ),
            ref(
                "scan-2",
                ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD,
                score=20,
                triggers=("volume_expansion",),
            ),
        ),
        horizons=(1,),
    )

    trigger_coverage = next(
        item
        for item in report.dimension_coverage
        if item.dimension is ScannerOutcomeGroupDimension.TRIGGER
    )
    assert trigger_coverage.multi_valued is True
    assert trigger_coverage.represented_scanner_evaluations == 2
    assert group(
        report,
        ScannerOutcomeGroupDimension.TRIGGER,
        "volume_expansion",
    ).scanner_evaluation_count == 2
    assert group(
        report,
        ScannerOutcomeGroupDimension.TRIGGER,
        "range_break",
    ).scanner_evaluation_count == 1


def test_incomplete_horizons_remain_in_counts_but_not_price_statistics():
    report = build(
        (
            ref(
                "scan-1",
                ScannerOutcomeClassification.NO_TRIGGER,
                score=0,
            ),
        ),
        period_end=START + INTERVAL,
        horizons=(3,),
    )
    no_trigger = group(
        report,
        ScannerOutcomeGroupDimension.CLASSIFICATION,
        "NO_TRIGGER",
    )
    stats = no_trigger.horizons[0]
    assert stats.complete_count == 0
    assert stats.incomplete_count == 1
    assert stats.raw_return_mean_pct is None
    assert stats.max_upside_mean_pct is None
