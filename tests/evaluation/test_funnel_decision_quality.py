from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.common.canonical import stable_digest
from app.evaluation.analytics_attribution.funnel_stage_models import (
    FunnelStage,
    FunnelStageAnalyticsAttributionRecord,
    FunnelStageAnalyticsAttributionSet,
)
from app.evaluation.decision_quality.funnel_quality import (
    DirectionalFirstHit,
    FunnelDecisionQualityDimension,
    FunnelDecisionQualityError,
    align_outcome_to_direction,
    build_funnel_decision_quality_report,
)
from app.evaluation.decision_quality.models import (
    AnalyticsResearchRef,
    CandidateCausalBlock,
    CandidateDecisionResearchRef,
    CandidateJoinCoverage,
    CandidatePosthocBlock,
    CandidateResearchRecord,
    DecisionQualityResearchBundle,
    DecisionQualityResearchRun,
    ResearchOutcomeDefinition,
    ResearchSourceIdentity,
    ScannerJoinCoverage,
    ScannerResearchProjection,
)
from app.evaluation.forward_outcomes.models import (
    ForwardOutcomeFirstHit,
    ForwardOutcomeHorizon,
    ForwardOutcomeIncompleteReason,
    ForwardOutcomeRecord,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
HORIZONS = (1, 3, 5, 10, 20)
SHA = "a" * 64


def complete_horizon(
    bars: int,
    *,
    raw_return: str = "4",
    upside: str = "6",
    downside: str = "-2",
    first_hit: ForwardOutcomeFirstHit = ForwardOutcomeFirstHit.MAX_UPSIDE,
) -> ForwardOutcomeHorizon:
    return ForwardOutcomeHorizon(
        horizon_bars=bars,
        is_complete=True,
        bars_observed=bars,
        gap_count=0,
        boundary_missing_bars=0,
        expected_end_at=NOW + timedelta(hours=bars),
        return_pct=Decimal(raw_return),
        max_upside_pct=Decimal(upside),
        max_downside_pct=Decimal(downside),
        max_upside_at=NOW + timedelta(minutes=1),
        max_downside_at=NOW + timedelta(minutes=2),
        first_hit=first_hit,
        first_hit_at=NOW + timedelta(minutes=1),
    )


def incomplete_horizon(bars: int) -> ForwardOutcomeHorizon:
    return ForwardOutcomeHorizon(
        horizon_bars=bars,
        is_complete=False,
        bars_observed=bars - 1,
        gap_count=0,
        boundary_missing_bars=1,
        expected_end_at=NOW + timedelta(hours=bars),
        incomplete_reason=ForwardOutcomeIncompleteReason.PERIOD_END,
    )


def test_long_direction_alignment() -> None:
    aligned = align_outcome_to_direction(horizon=complete_horizon(10), direction="LONG")
    assert aligned.directional_return_pct == Decimal("4")
    assert aligned.favorable_excursion_pct == Decimal("6")
    assert aligned.adverse_excursion_pct == Decimal("2")
    assert aligned.first_hit_alignment is DirectionalFirstHit.FAVORABLE


def test_short_direction_alignment() -> None:
    aligned = align_outcome_to_direction(horizon=complete_horizon(10), direction="SHORT")
    assert aligned.directional_return_pct == Decimal("-4")
    assert aligned.favorable_excursion_pct == Decimal("2")
    assert aligned.adverse_excursion_pct == Decimal("6")
    assert aligned.first_hit_alignment is DirectionalFirstHit.ADVERSE


def test_short_favorable_market_alignment() -> None:
    aligned = align_outcome_to_direction(
        horizon=complete_horizon(
            10,
            raw_return="-5",
            upside="1",
            downside="-7",
            first_hit=ForwardOutcomeFirstHit.MAX_DOWNSIDE,
        ),
        direction="SHORT",
    )
    assert aligned.directional_return_pct == Decimal("5")
    assert aligned.favorable_excursion_pct == Decimal("7")
    assert aligned.adverse_excursion_pct == Decimal("1")
    assert aligned.first_hit_alignment is DirectionalFirstHit.FAVORABLE


def test_same_candle_is_preserved() -> None:
    aligned = align_outcome_to_direction(
        horizon=complete_horizon(10, first_hit=ForwardOutcomeFirstHit.SAME_CANDLE),
        direction="LONG",
    )
    assert aligned.first_hit_alignment is DirectionalFirstHit.SAME_CANDLE


def test_incomplete_cannot_be_direction_aligned() -> None:
    with pytest.raises(FunnelDecisionQualityError, match="complete horizon"):
        align_outcome_to_direction(horizon=incomplete_horizon(20), direction="LONG")


def source_identity(run: str = "run-a", analytics: str = "analytics-a") -> ResearchSourceIdentity:
    return ResearchSourceIdentity(
        source_backtest_run_id=run,
        analytics_run_id=analytics,
        period_role="OOS",
        dataset_id="dataset",
        dataset_version="v1",
        dataset_content_sha256=SHA,
        dataset_source="fixture",
        system_id="balanced_v1",
        symbol="BTC/EUR",
        source_timeframe="1h",
        decision_timeframe="1h",
    )


def candidate(
    opportunity_id: str, *, direction: str | None, with_outcome: bool = True
) -> CandidateResearchRecord:
    source = source_identity()
    scanner = ScannerResearchProjection(
        scanner_evaluation_id=f"scan-{opportunity_id}",
        snapshot_id=f"scan-{opportunity_id}",
        classification="CANDIDATE_OPPORTUNITY",
        score=50,
        candidate_threshold=35,
        score_margin=15,
        triggers=("RANGE_BREAK",),
        candidate_opportunity_id=opportunity_id,
    )
    analytics = AnalyticsResearchRef(
        attribution_record_id=f"attr-{opportunity_id}",
        attribution_record_fingerprint=SHA,
        analytics_run_id="analytics-a",
        status="UNMATCHED",
        diagnostics=("fixture",),
    )
    decision = CandidateDecisionResearchRef(
        record_id=f"di-{opportunity_id}",
        record_fingerprint=SHA,
        opportunity_fingerprint=SHA,
        professor_final_direction=direction,
    )
    causal = CandidateCausalBlock(
        source=source,
        opportunity_id=opportunity_id,
        observed_at=NOW,
        scanner=scanner,
        analytics=analytics,
        decision=decision,
        causal_fingerprint=SHA,
    )
    outcome = None
    if with_outcome:
        outcome = ForwardOutcomeRecord(
            opportunity_id=opportunity_id,
            snapshot_id=scanner.snapshot_id,
            observed_at=NOW,
            reference_close=Decimal("100"),
            terminal_status="FIXTURE",
            professor_direction=direction,
            proposal_side=direction if direction in {"LONG", "SHORT"} else None,
            horizons=tuple(complete_horizon(bars) for bars in HORIZONS),
        )
    posthoc = CandidatePosthocBlock(
        future_outcome=outcome,
        outcome_fingerprint=stable_digest(outcome.model_dump(mode="python")) if outcome else None,
    )
    return CandidateResearchRecord(
        research_run_id="research-a",
        record_id=f"cr-{opportunity_id}",
        record_fingerprint=SHA,
        period_role="OOS",
        opportunity_id=opportunity_id,
        causal=causal,
        posthoc=posthoc,
        join_status="MISSING_ANALYTICS",
        join_issues=("MISSING_ANALYTICS",),
    )


def stage_record(
    opportunity_id: str,
    stage: FunnelStage,
    *,
    reached: bool = True,
    result: str | None = None,
    failure: str | None = None,
    reasons: tuple[str, ...] = (),
    agent: str | None = None,
    order: int | None = None,
) -> FunnelStageAnalyticsAttributionRecord:
    return FunnelStageAnalyticsAttributionRecord.model_construct(
        record_id=f"{opportunity_id}-{stage}-{agent or 'fixed'}",
        record_fingerprint=SHA,
        source_backtest_run_id="run-a",
        analytics_run_id="analytics-a",
        decision_intelligence_record_id=f"di-{opportunity_id}",
        decision_intelligence_record_fingerprint=SHA,
        opportunity_id=opportunity_id,
        system_id="balanced_v1",
        symbol="BTC/EUR",
        decision_timeframe="1h",
        stage=stage,
        stage_order=list(FunnelStage).index(stage) * 10 + 10,
        stage_instance_id=agent,
        stage_instance_order=order,
        agent_id=agent,
        reached=reached,
        stage_status="FAILED" if failure else ("COMPLETED" if reached else None),
        stage_result=result,
        reason_codes=reasons,
        selected_agents=("berlin", "tokyo")
        if stage is FunnelStage.PROFESSOR_PLAN and reached
        else (),
        failure_code=failure,
        failure_stage="fixture" if failure else None,
        source_projection_path="fixture",
        source_projection_fingerprint=SHA,
        market_as_of=NOW,
        analytics_link_id="link",
        analytics_link_fingerprint=SHA,
        analytics_link_policy_version="fixture",
        analytics_link_status="UNMATCHED",
        analytics_diagnostics=(),
    )


def fixed_records(
    opportunity_id: str, *, final: str = "LONG", risk: str = "APPROVED"
) -> tuple[FunnelStageAnalyticsAttributionRecord, ...]:
    return (
        stage_record(opportunity_id, FunnelStage.COMPUTE_GATE, result="LEVEL_2_MINI_CREW"),
        stage_record(opportunity_id, FunnelStage.PROFESSOR_PLAN, result="ANALYZE"),
        stage_record(opportunity_id, FunnelStage.PALERMO, result="CAUTION"),
        stage_record(opportunity_id, FunnelStage.PROFESSOR_FINAL, result=final),
        stage_record(
            opportunity_id,
            FunnelStage.TRADE_PROPOSAL,
            reached=final != "NO_TRADE",
            result=final if final != "NO_TRADE" else None,
        ),
        stage_record(
            opportunity_id,
            FunnelStage.RISK,
            reached=final != "NO_TRADE",
            result=risk if final != "NO_TRADE" else None,
            reasons=("MIN_EXPECTED_RR",) if risk == "REJECTED" else (),
        ),
        stage_record(
            opportunity_id,
            FunnelStage.PAPER,
            reached=final != "NO_TRADE" and risk != "REJECTED",
            result="FILLED" if risk != "REJECTED" else None,
        ),
    )


def bundle_and_stage_set(
    *, final: str = "LONG", risk: str = "APPROVED"
) -> tuple[DecisionQualityResearchBundle, FunnelStageAnalyticsAttributionSet]:
    item = candidate("opp-1", direction=final if final != "NO_TRADE" else None)
    source = source_identity()
    run = DecisionQualityResearchRun(
        research_run_id="research-a",
        run_fingerprint=SHA,
        source=source,
        outcome_definition=ResearchOutcomeDefinition(
            forward_outcome_schema_version="money-heist.forward-outcomes.v1",
            forward_outcome_policy_version="money-heist.forward-outcomes.close-ohlc.v1",
            scanner_forward_outcome_schema_version="money-heist.scanner-forward-outcomes.v1",
            scanner_forward_outcome_policy_version="money-heist.scanner-forward-outcomes.close-ohlc.v1",
            horizons=HORIZONS,
        ),
    )
    bundle = DecisionQualityResearchBundle(
        research_run=run,
        candidate_records=(item,),
        scanner_records=(),
        candidate_coverage=CandidateJoinCoverage(
            total=1,
            joined=0,
            missing_decision_intelligence=0,
            missing_forward_outcome=0,
            missing_analytics=1,
        ),
        scanner_coverage=ScannerJoinCoverage(
            total=0, joined=0, missing_forward_outcome=0, missing_analytics=0
        ),
        bundle_fingerprint=SHA,
    )
    records = fixed_records("opp-1", final=final, risk=risk)
    stage_set = FunnelStageAnalyticsAttributionSet.model_construct(
        source_backtest_run_id="run-a",
        analytics_run_id="analytics-a",
        source_decision_record_set_fingerprint=SHA,
        decision_record_count=1,
        covered_decision_record_count=1,
        stage_record_count=len(records),
        reached_stage_count=sum(item.reached for item in records),
        not_reached_stage_count=sum(not item.reached for item in records),
        matched_analytics_stage_count=0,
        unmatched_analytics_stage_count=len(records),
        records=records,
        set_fingerprint=SHA,
    )
    return bundle, stage_set


def test_early_stage_cohorts_are_directionless() -> None:
    bundle, stages = bundle_and_stage_set(final="LONG")
    report = build_funnel_decision_quality_report(bundle=bundle, funnel_stage_attribution=stages)
    palermo = next(
        item
        for item in report.cohorts
        if item.stage is FunnelStage.PALERMO
        and item.dimension is FunnelDecisionQualityDimension.STAGE_RESULT
    )
    assert palermo.key == "CAUTION"
    assert palermo.direction_available_count == 0
    assert palermo.directional_horizons == ()


def test_final_long_has_directional_metrics_and_no_trade_has_none() -> None:
    bundle, stages = bundle_and_stage_set(final="LONG")
    report = build_funnel_decision_quality_report(bundle=bundle, funnel_stage_attribution=stages)
    final = next(
        item
        for item in report.cohorts
        if item.stage is FunnelStage.PROFESSOR_FINAL
        and item.dimension is FunnelDecisionQualityDimension.STAGE_RESULT
        and item.key == "LONG"
    )
    assert final.directional_horizons[3].directional_return_median_pct == Decimal("4")

    bundle_nt, stages_nt = bundle_and_stage_set(final="NO_TRADE")
    report_nt = build_funnel_decision_quality_report(
        bundle=bundle_nt, funnel_stage_attribution=stages_nt
    )
    no_trade = next(
        item
        for item in report_nt.cohorts
        if item.stage is FunnelStage.PROFESSOR_FINAL
        and item.dimension is FunnelDecisionQualityDimension.STAGE_RESULT
        and item.key == "NO_TRADE"
    )
    assert no_trade.direction_available_count == 0
    assert all(item.directional_complete_count == 0 for item in no_trade.directional_horizons)


def test_risk_rejected_reason_is_multivalued_and_direction_aware() -> None:
    bundle, stages = bundle_and_stage_set(final="LONG", risk="REJECTED")
    report = build_funnel_decision_quality_report(bundle=bundle, funnel_stage_attribution=stages)
    risk_reason = next(
        item
        for item in report.cohorts
        if item.stage is FunnelStage.RISK
        and item.dimension is FunnelDecisionQualityDimension.STAGE_REASON
    )
    assert risk_reason.key == "MIN_EXPECTED_RR"
    assert risk_reason.multi_valued is True
    assert risk_reason.direction_available_count == 1


def test_run_and_analytics_mismatch_fail_closed() -> None:
    bundle, stages = bundle_and_stage_set()
    with pytest.raises(FunnelDecisionQualityError, match="BacktestRun"):
        build_funnel_decision_quality_report(
            bundle=bundle,
            funnel_stage_attribution=stages.model_copy(update={"source_backtest_run_id": "run-b"}),
        )
    with pytest.raises(FunnelDecisionQualityError, match="AnalyticsRun"):
        build_funnel_decision_quality_report(
            bundle=bundle,
            funnel_stage_attribution=stages.model_copy(update={"analytics_run_id": "analytics-b"}),
        )


def test_unknown_opportunity_fails_closed() -> None:
    bundle, stages = bundle_and_stage_set()
    foreign = stages.records[0].model_copy(update={"opportunity_id": "foreign"})
    with pytest.raises(FunnelDecisionQualityError, match="unknown opportunities"):
        build_funnel_decision_quality_report(
            bundle=bundle,
            funnel_stage_attribution=stages.model_copy(
                update={"records": (foreign, *stages.records[1:])}
            ),
        )


def test_deterministic_json_under_input_shuffle() -> None:
    bundle, stages = bundle_and_stage_set()
    first = build_funnel_decision_quality_report(bundle=bundle, funnel_stage_attribution=stages)
    shuffled = stages.model_copy(update={"records": tuple(reversed(stages.records))})
    second = build_funnel_decision_quality_report(bundle=bundle, funnel_stage_attribution=shuffled)
    assert first.report_id == second.report_id
    assert first.report_fingerprint == second.report_fingerprint
    assert first.to_json() == second.to_json()
