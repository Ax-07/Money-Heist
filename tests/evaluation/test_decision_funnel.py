from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.evaluation.decision_funnel import (
    DecisionFunnelObservationCounts,
    aggregate_decision_funnel,
)

NOW = datetime(2026, 9, 16, tzinfo=UTC)


def _enum(value: str):
    return SimpleNamespace(value=value)


def _point(*, triggers=(), opportunity=None, pipeline=None):
    scan = SimpleNamespace(triggers=triggers, opportunity=opportunity)
    return SimpleNamespace(scan_result=scan, opportunity=opportunity, pipeline_result=pipeline)


def test_decision_funnel_aggregates_existing_pipeline_outputs_without_replaying_logic() -> None:
    blocked_opp = SimpleNamespace(opportunity_id="opp-blocked")
    blocked_gate = SimpleNamespace(allows_ai=False, reason=_enum("PRIORITY_TOO_LOW"))
    blocked_orchestration = SimpleNamespace(
        compute_gate=blocked_gate,
        professor_plan=None,
        professor_decision=None,
        trade_proposal=None,
        failure=None,
        status=_enum("NO_ANALYSIS"),
    )
    blocked_pipeline = SimpleNamespace(
        status=_enum("NO_ANALYSIS"),
        orchestration_result=blocked_orchestration,
        risk_record=None,
        order=None,
        fill=None,
        failure=None,
    )

    no_trade_opp = SimpleNamespace(opportunity_id="opp-no-trade")
    allowed_gate = SimpleNamespace(allows_ai=True, reason=_enum("ALLOWED_MINI_CREW"))
    no_trade_orchestration = SimpleNamespace(
        compute_gate=allowed_gate,
        professor_plan=SimpleNamespace(decision="MINI_CREW"),
        professor_decision=SimpleNamespace(direction="NO_TRADE"),
        trade_proposal=None,
        failure=None,
        status=_enum("NO_TRADE"),
    )
    no_trade_pipeline = SimpleNamespace(
        status=_enum("NO_TRADE"),
        orchestration_result=no_trade_orchestration,
        risk_record=None,
        order=None,
        fill=None,
        failure=None,
    )

    executed_opp = SimpleNamespace(opportunity_id="opp-executed")
    risk_decision = SimpleNamespace(
        status=_enum("RESIZED"),
        reason_codes=(_enum("RESIZED_EXPOSURE"), _enum("RESIZED_QTY_STEP")),
    )
    executed_orchestration = SimpleNamespace(
        compute_gate=allowed_gate,
        professor_plan=SimpleNamespace(decision="MINI_CREW"),
        professor_decision=SimpleNamespace(direction="LONG"),
        trade_proposal=SimpleNamespace(proposal_id="proposal-1"),
        failure=None,
        status=_enum("TRADE_PROPOSAL"),
    )
    executed_pipeline = SimpleNamespace(
        status=_enum("EXECUTED"),
        orchestration_result=executed_orchestration,
        risk_record=SimpleNamespace(decision=risk_decision),
        order=SimpleNamespace(broker_order_id="entry-order"),
        fill=SimpleNamespace(fill_id="entry-fill"),
        failure=None,
    )

    points = (
        _point(),
        _point(triggers=(_enum("RANGE_BREAK"),)),
        _point(
            triggers=(_enum("VOLUME_EXPANSION"),),
            opportunity=blocked_opp,
            pipeline=blocked_pipeline,
        ),
        _point(
            triggers=(_enum("TREND_STRENGTH"),),
            opportunity=no_trade_opp,
            pipeline=no_trade_pipeline,
        ),
        _point(
            triggers=(_enum("MOMENTUM_EXTREME"),),
            opportunity=executed_opp,
            pipeline=executed_pipeline,
        ),
    )
    report = aggregate_decision_funnel(
        run_id="run-1",
        dataset_id="dataset-1",
        dataset_version="dataset-v1",
        system_id="balanced_v1",
        period_start=NOW,
        period_end=NOW,
        candles_evaluated=7,
        observation_counts=DecisionFunnelObservationCounts(
            pre_scanner_warmup_skipped=1,
            pre_scanner_not_decision_close_skipped=1,
        ),
        replay_points=points,
        closed_trades=1,
        broker_executions=(
            SimpleNamespace(broker_order_id="entry-order"),
            SimpleNamespace(broker_order_id="exit-order"),
        ),
    )

    counts = report.counts
    assert counts.scanner_evaluations == 5
    assert counts.scanner_no_trigger == 1
    assert counts.scanner_triggered == 4
    assert counts.candidate_opportunities == 3
    assert counts.compute_gate_blocked == 1
    assert counts.compute_gate_allowed == 2
    assert counts.ai_orchestrations_triggered == 2
    assert counts.professor_no_trade == 1
    assert counts.trade_proposals_created == 1
    assert counts.risk_resized == 1
    assert counts.orders_submitted == 1
    assert counts.fills == 1
    assert report.post_hoc.closed_trades == 1
    assert report.post_hoc.broker_orders_total == 2
    assert report.post_hoc.broker_fills_total == 2

    reason_map = {(item.stage, item.code): item.count for item in report.reason_counts}
    assert reason_map[("REPLAY", "WARMUP_INCOMPLETE")] == 1
    assert reason_map[("REPLAY", "NOT_DECISION_TIMEFRAME_CLOSE")] == 1
    assert reason_map[("SCANNER", "NO_TRIGGER")] == 1
    assert reason_map[("SCANNER", "TRIGGER_BELOW_CANDIDATE_THRESHOLD")] == 1
    assert reason_map[("COMPUTE_GATE", "PRIORITY_TOO_LOW")] == 1
    assert reason_map[("PROFESSOR_FINAL", "NO_TRADE")] == 1
    assert reason_map[("RISK", "RESIZED_EXPOSURE")] == 1
    assert reason_map[("RISK", "RESIZED_QTY_STEP")] == 1
