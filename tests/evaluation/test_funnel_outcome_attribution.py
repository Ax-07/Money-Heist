from datetime import UTC, datetime
from decimal import Decimal

from app.evaluation.forward_outcomes import (
    ForwardOutcomeHorizon,
    ForwardOutcomeHorizonSummary,
    ForwardOutcomeRecord,
    ForwardOutcomeReport,
    ForwardOutcomeStatusCount,
    ForwardOutcomeSummary,
)
from app.evaluation.funnel_outcome_attribution import (
    FunnelAttributionDimension,
    FunnelOutcomeSubject,
    aggregate_funnel_outcome_attribution,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def complete_horizon(
    horizon: int,
    *,
    ret: str,
    up: str,
    down: str,
) -> ForwardOutcomeHorizon:
    return ForwardOutcomeHorizon(
        horizon_bars=horizon,
        is_complete=True,
        bars_observed=horizon,
        gap_count=0,
        boundary_missing_bars=0,
        expected_end_at=NOW,
        return_pct=Decimal(ret),
        max_upside_pct=Decimal(up),
        max_downside_pct=Decimal(down),
        max_upside_at=NOW,
        max_downside_at=NOW,
        first_hit="SAME_CANDLE",
        first_hit_at=NOW,
    )


def incomplete_horizon(horizon: int) -> ForwardOutcomeHorizon:
    return ForwardOutcomeHorizon(
        horizon_bars=horizon,
        is_complete=False,
        bars_observed=0,
        gap_count=0,
        boundary_missing_bars=horizon,
        expected_end_at=NOW,
        incomplete_reason="PERIOD_END",
    )


def record(
    opportunity_id: str,
    status: str,
    *,
    ret: str,
    up: str,
    down: str,
    direction: str | None = None,
    side: str | None = None,
    h3_complete: bool = True,
) -> ForwardOutcomeRecord:
    return ForwardOutcomeRecord(
        opportunity_id=opportunity_id,
        snapshot_id=f"snap-{opportunity_id}",
        observed_at=NOW,
        reference_close=Decimal("100"),
        terminal_status=status,
        professor_direction=direction,
        proposal_side=side,
        horizons=(
            complete_horizon(1, ret=ret, up=up, down=down),
            (
                complete_horizon(3, ret=ret, up=up, down=down)
                if h3_complete
                else incomplete_horizon(3)
            ),
        ),
    )


def report(records: tuple[ForwardOutcomeRecord, ...]) -> ForwardOutcomeReport:
    statuses: dict[str, int] = {}
    for item in records:
        statuses[item.terminal_status] = statuses.get(item.terminal_status, 0) + 1
    return ForwardOutcomeReport(
        run_id="run-1",
        dataset_id="dataset-1",
        dataset_version="sha256:" + "a" * 64,
        dataset_content_sha256="a" * 64,
        dataset_source="fixture",
        system_id="balanced_v1",
        source_timeframe="1h",
        decision_timeframe="1h",
        period_start=NOW,
        period_end=NOW,
        horizons=(1, 3),
        summary=ForwardOutcomeSummary(
            opportunity_count=len(records),
            status_counts=tuple(
                ForwardOutcomeStatusCount(status=key, count=value)
                for key, value in sorted(statuses.items())
            ),
            horizon_counts=(
                ForwardOutcomeHorizonSummary(
                    horizon_bars=1,
                    complete=len(records),
                    incomplete=0,
                    with_gaps=0,
                ),
                ForwardOutcomeHorizonSummary(
                    horizon_bars=3,
                    complete=sum(
                        1 for item in records if item.horizons[1].is_complete
                    ),
                    incomplete=sum(
                        1 for item in records if not item.horizons[1].is_complete
                    ),
                    with_gaps=0,
                ),
            ),
        ),
        records=records,
    )


def group(result, dimension, key):
    return next(
        item
        for item in result.groups
        if item.dimension is dimension and item.key == key
    )


def test_terminal_status_group_reports_raw_and_directional_statistics():
    outcomes = report(
        (
            record(
                "opp-1",
                "RISK_REJECTED",
                ret="5",
                up="8",
                down="-2",
                direction="LONG",
                side="LONG",
            ),
            record(
                "opp-2",
                "RISK_REJECTED",
                ret="-4",
                up="1",
                down="-6",
                direction="SHORT",
                side="SHORT",
            ),
            record(
                "opp-3",
                "NO_TRADE",
                ret="2",
                up="4",
                down="-1",
                direction="NO_TRADE",
            ),
        )
    )
    subjects = (
        FunnelOutcomeSubject(
            opportunity_id="opp-1",
            observed_at=NOW,
            terminal_status="RISK_REJECTED",
            scanner_triggers=("range_break",),
            professor_direction="LONG",
            proposal_side="LONG",
            risk_status="REJECTED",
            risk_reason_codes=("MAX_RISK_PER_TRADE",),
        ),
        FunnelOutcomeSubject(
            opportunity_id="opp-2",
            observed_at=NOW,
            terminal_status="RISK_REJECTED",
            scanner_triggers=("range_break", "trend_strength"),
            professor_direction="SHORT",
            proposal_side="SHORT",
            risk_status="REJECTED",
            risk_reason_codes=("MAX_RISK_PER_TRADE",),
        ),
        FunnelOutcomeSubject(
            opportunity_id="opp-3",
            observed_at=NOW,
            terminal_status="NO_TRADE",
            scanner_triggers=("trend_strength",),
            professor_direction="NO_TRADE",
        ),
    )

    result = aggregate_funnel_outcome_attribution(
        forward_outcomes=outcomes,
        subjects=subjects,
        candidate_opportunity_count=3,
    )

    rejected = group(
        result,
        FunnelAttributionDimension.TERMINAL_STATUS,
        "RISK_REJECTED",
    )
    h1 = rejected.horizons[0]
    assert h1.opportunity_count == 2
    assert h1.raw_return_mean_pct == Decimal("0.5")
    assert h1.raw_return_median_pct == Decimal("0.5")
    assert h1.raw_positive_count == 1
    assert h1.raw_negative_count == 1
    assert h1.directional_count == 2
    assert h1.directional_return_mean_pct == Decimal("4.5")
    assert h1.directional_return_median_pct == Decimal("4.5")
    assert h1.directional_positive_count == 2
    assert h1.favorable_excursion_mean_pct == Decimal("7")
    assert h1.adverse_excursion_mean_pct == Decimal("1.5")

    no_trade = group(
        result,
        FunnelAttributionDimension.TERMINAL_STATUS,
        "NO_TRADE",
    )
    assert no_trade.horizons[0].directional_count == 0
    assert no_trade.horizons[0].directional_return_mean_pct is None


def test_multi_value_dimensions_overlap_without_breaking_unique_coverage():
    outcomes = report(
        (
            record("opp-1", "NO_TRADE", ret="1", up="2", down="-1"),
            record("opp-2", "NO_TRADE", ret="-1", up="1", down="-2"),
        )
    )
    subjects = (
        FunnelOutcomeSubject(
            opportunity_id="opp-1",
            observed_at=NOW,
            terminal_status="NO_TRADE",
            scanner_triggers=("range_break", "trend_strength"),
        ),
        FunnelOutcomeSubject(
            opportunity_id="opp-2",
            observed_at=NOW,
            terminal_status="NO_TRADE",
            scanner_triggers=("trend_strength",),
        ),
    )
    result = aggregate_funnel_outcome_attribution(
        forward_outcomes=outcomes,
        subjects=subjects,
        candidate_opportunity_count=2,
    )
    trigger_coverage = next(
        item
        for item in result.dimension_coverage
        if item.dimension is FunnelAttributionDimension.SCANNER_TRIGGER
    )
    assert trigger_coverage.represented_opportunities == 2
    assert trigger_coverage.missing_opportunities == 0
    assert trigger_coverage.group_count == 2
    assert trigger_coverage.multi_valued is True
    assert group(
        result,
        FunnelAttributionDimension.SCANNER_TRIGGER,
        "trend_strength",
    ).opportunity_count == 2
    assert group(
        result,
        FunnelAttributionDimension.SCANNER_TRIGGER,
        "range_break",
    ).opportunity_count == 1


def test_incomplete_horizon_is_counted_but_excluded_from_price_statistics():
    outcomes = report(
        (
            record(
                "opp-1",
                "NO_TRADE",
                ret="3",
                up="4",
                down="-2",
                h3_complete=False,
            ),
        )
    )
    subject = FunnelOutcomeSubject(
        opportunity_id="opp-1",
        observed_at=NOW,
        terminal_status="NO_TRADE",
        scanner_triggers=("range_break",),
    )
    result = aggregate_funnel_outcome_attribution(
        forward_outcomes=outcomes,
        subjects=(subject,),
        candidate_opportunity_count=1,
    )
    status = group(
        result,
        FunnelAttributionDimension.TERMINAL_STATUS,
        "NO_TRADE",
    )
    h3 = status.horizons[1]
    assert h3.complete_count == 0
    assert h3.incomplete_count == 1
    assert h3.raw_return_mean_pct is None
    assert h3.max_upside_mean_pct is None


def test_report_explicitly_marks_pre_candidate_scanner_outcomes_unavailable():
    outcomes = report(
        (record("opp-1", "NO_TRADE", ret="1", up="2", down="-1"),)
    )
    result = aggregate_funnel_outcome_attribution(
        forward_outcomes=outcomes,
        subjects=(
            FunnelOutcomeSubject(
                opportunity_id="opp-1",
                observed_at=NOW,
                terminal_status="NO_TRADE",
            ),
        ),
        candidate_opportunity_count=1,
    )
    assert result.coverage.scanner_no_trigger_outcomes_available is False
    assert (
        result.coverage.scanner_below_candidate_threshold_outcomes_available
        is False
    )
