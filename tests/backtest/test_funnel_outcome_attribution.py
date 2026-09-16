from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.evaluation.forward_outcomes import (
    ForwardOutcomeHorizon,
    ForwardOutcomeHorizonSummary,
    ForwardOutcomeRecord,
    ForwardOutcomeReport,
    ForwardOutcomeStatusCount,
    ForwardOutcomeSummary,
)
from app.evaluation.funnel_outcome_attribution import FunnelAttributionDimension
from app.services.backtest.funnel_outcome_attribution import (
    build_funnel_outcome_attribution_report,
)


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def forward_report() -> ForwardOutcomeReport:
    horizon = ForwardOutcomeHorizon(
        horizon_bars=1,
        is_complete=True,
        bars_observed=1,
        gap_count=0,
        boundary_missing_bars=0,
        expected_end_at=NOW,
        return_pct=Decimal("2"),
        max_upside_pct=Decimal("4"),
        max_downside_pct=Decimal("-1"),
        max_upside_at=NOW,
        max_downside_at=NOW,
        first_hit="SAME_CANDLE",
        first_hit_at=NOW,
    )
    record = ForwardOutcomeRecord(
        opportunity_id="opp-1",
        snapshot_id="snap-1",
        observed_at=NOW,
        reference_close=Decimal("100"),
        terminal_status="RISK_REJECTED",
        professor_direction="LONG",
        proposal_side="LONG",
        horizons=(horizon,),
    )
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
        horizons=(1,),
        summary=ForwardOutcomeSummary(
            opportunity_count=1,
            status_counts=(
                ForwardOutcomeStatusCount(status="RISK_REJECTED", count=1),
            ),
            horizon_counts=(
                ForwardOutcomeHorizonSummary(
                    horizon_bars=1,
                    complete=1,
                    incomplete=0,
                    with_gaps=0,
                ),
            ),
        ),
        records=(record,),
    )


def replay_and_funnel(candidate_count: int = 1):
    opportunity = SimpleNamespace(
        opportunity_id="opp-1",
        triggers=(
            SimpleNamespace(value="range_break"),
            SimpleNamespace(value="trend_strength"),
        ),
    )
    risk_decision = SimpleNamespace(
        status=SimpleNamespace(value="REJECTED"),
        reason_codes=(SimpleNamespace(value="MAX_RISK_PER_TRADE"),),
    )
    orchestration = SimpleNamespace(
        compute_gate=SimpleNamespace(
            reason=SimpleNamespace(value="ALLOWED_FULL_CREW")
        ),
        professor_plan=SimpleNamespace(
            decision="FULL_CREW",
            selected_agents=("berlin", "tokyo"),
        ),
        failure=None,
        professor_decision=SimpleNamespace(direction="LONG"),
        trade_proposal=SimpleNamespace(side="LONG"),
    )
    pipeline = SimpleNamespace(
        status=SimpleNamespace(value="RISK_REJECTED"),
        orchestration_result=orchestration,
        risk_record=SimpleNamespace(decision=risk_decision),
        failure=None,
    )
    point = SimpleNamespace(
        opportunity=opportunity,
        observed_at=NOW,
        feature_snapshot=SimpleNamespace(
            regime=SimpleNamespace(value="bullish_trend")
        ),
        pipeline_result=pipeline,
    )
    dataset = SimpleNamespace(
        dataset_id="dataset-1",
        version="sha256:" + "a" * 64,
    )
    run = SimpleNamespace(
        run_id="run-1",
        dataset=dataset,
        config=SimpleNamespace(system_id="balanced_v1"),
    )
    replay = SimpleNamespace(
        backtest_result=SimpleNamespace(run=run),
        points=(point,),
    )
    funnel = SimpleNamespace(
        run_id="run-1",
        dataset_id="dataset-1",
        system_id="balanced_v1",
        counts=SimpleNamespace(candidate_opportunities=candidate_count),
    )
    return replay, funnel


def test_adapter_extracts_candidate_stage_dimensions():
    replay, funnel = replay_and_funnel()
    result = build_funnel_outcome_attribution_report(
        replay,
        funnel,
        forward_report(),
    )
    subject = result.subjects[0]
    assert subject.scanner_triggers == ("range_break", "trend_strength")
    assert subject.market_regime == "bullish_trend"
    assert subject.compute_gate_reason == "ALLOWED_FULL_CREW"
    assert subject.professor_plan_decision == "FULL_CREW"
    assert subject.selected_agents == ("berlin", "tokyo")
    assert subject.professor_direction == "LONG"
    assert subject.proposal_side == "LONG"
    assert subject.risk_status == "REJECTED"
    assert subject.risk_reason_codes == ("MAX_RISK_PER_TRADE",)

    risk_group = next(
        item
        for item in result.groups
        if item.dimension is FunnelAttributionDimension.RISK_REASON
        and item.key == "MAX_RISK_PER_TRADE"
    )
    assert risk_group.opportunity_count == 1
    assert risk_group.horizons[0].directional_return_mean_pct == Decimal("2")


def test_adapter_rejects_candidate_count_mismatch():
    replay, funnel = replay_and_funnel(candidate_count=2)
    with pytest.raises(ValueError, match="candidate_opportunity_count"):
        build_funnel_outcome_attribution_report(
            replay,
            funnel,
            forward_report(),
        )
