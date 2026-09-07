from __future__ import annotations

from decimal import Decimal

import asyncio

from app.dashboard.models import (
    DashboardAvailability,
    DashboardEventKind,
    DashboardProvenance,
)
from app.dashboard.projection import ShadowDashboardProjector

from ._helpers import NOW, fake_fleet_result, fake_runner


def test_projector_reads_three_systems_without_mutating_runtime():
    runner = fake_runner()
    result = fake_fleet_result()
    projector = ShadowDashboardProjector(clock=lambda: NOW)
    snapshot = asyncio.run(projector.capture(runner=runner, fleet_result=result))
    assert len(snapshot.systems) == 3
    assert snapshot.system_state == "OBSERVABLE"
    assert snapshot.root_opportunity_id == "root-1"


def test_projector_exposes_paper_account_values():
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(), fleet_result=fake_fleet_result()
    ))
    system = snapshot.systems[0]
    assert system.account.availability is DashboardAvailability.AVAILABLE
    assert system.account.cash_balance == Decimal("91.5")
    assert system.account.equity == Decimal("101.25")
    assert system.account.open_positions == 1


def test_projector_exposes_positions_orders_and_fills():
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(), fleet_result=fake_fleet_result()
    ))
    system = snapshot.systems[0]
    assert system.positions_availability is DashboardAvailability.AVAILABLE
    assert system.positions[0].side == "LONG"
    assert system.orders[0].status == "FILLED"
    assert system.fills[0].provenance is DashboardProvenance.PAPER_EXECUTED


def test_projector_exposes_professor_proposal_and_risk_reason_codes():
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(), fleet_result=fake_fleet_result()
    ))
    decision = snapshot.systems[0].latest_decision
    assert decision is not None
    assert decision.pipeline_status == "EXECUTED"
    assert decision.professor.direction == "LONG"
    assert decision.proposal.side == "LONG"
    assert decision.risk.status == "APPROVED"
    assert decision.risk.reason_codes == ("APPROVED",)


def test_projector_keeps_ai_cost_scoped_by_system():
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(), fleet_result=fake_fleet_result()
    ))
    for system in snapshot.systems:
        assert system.ai_usage.record_count == 1
        assert system.ai_usage.total_cost_eur == Decimal("0.08")
        assert system.ai_usage.by_agent_eur == {"berlin": Decimal("0.08")}


def test_projector_exposes_batch10_trading_economic_and_self_funding():
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(), fleet_result=fake_fleet_result()
    ))
    metrics = snapshot.systems[0].batch10.metrics
    assert metrics["trading_net"].value == Decimal("2.05")
    assert metrics["economic_net"].value == Decimal("1.75")
    assert metrics["self_funding_ratio"].value == Decimal("6.833333")
    assert metrics["max_drawdown_abs"].value == Decimal("0.4")


def test_projector_keeps_unbounded_batch10_metric_explicit():
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(), fleet_result=fake_fleet_result()
    ))
    metric = snapshot.systems[0].batch10.metrics["profit_factor"]
    assert metric.value is None
    assert metric.availability is DashboardAvailability.UNBOUNDED
    assert metric.reason == "no losing trades"


def test_projector_marks_counterfactual_as_counterfactual():
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(), fleet_result=fake_fleet_result()
    ))
    item = snapshot.systems[0].batch10.counterfactuals[0]
    assert item.provenance is DashboardProvenance.COUNTERFACTUAL
    assert item.hypothetical_pnl == Decimal("-1.2")


def test_projector_exposes_batch11_comparison_without_winner():
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(), fleet_result=fake_fleet_result()
    ))
    comparison = snapshot.comparison
    assert comparison.metrics["trading_net"].availability is DashboardAvailability.AVAILABLE
    assert len(comparison.metrics["trading_net"].values) == 3
    assert comparison.promotion_system_id is None
    assert comparison.risk_change is None


def test_account_read_failure_is_unavailable_and_degrades_snapshot():
    system_id = "shadow_balanced_v1"
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(fail_account_system=system_id),
        fleet_result=fake_fleet_result(),
    ))
    system = snapshot.by_system_id()[system_id]
    assert system.account.availability is DashboardAvailability.UNAVAILABLE
    assert system.account.equity is None
    assert snapshot.system_state == "PARTIAL"
    assert any(event.code == "ACCOUNT_STATE_UNAVAILABLE" for event in snapshot.events)


def test_evaluation_failure_does_not_remove_paper_execution():
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(),
        fleet_result=fake_fleet_result(evaluation_status="FAILED"),
    ))
    system = snapshot.systems[0]
    assert system.latest_decision.pipeline_status == "EXECUTED"
    assert system.orders[0].status == "FILLED"
    assert system.batch10.status == "FAILED"
    assert system.batch10.metrics["trading_net"].value is None
    assert any(event.kind is DashboardEventKind.EVALUATION for event in snapshot.events)


def test_risk_event_is_separate_from_professor_proposal():
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(), fleet_result=fake_fleet_result()
    ))
    risk_events = [event for event in snapshot.events if event.kind is DashboardEventKind.RISK]
    assert len(risk_events) == 3
    assert all(event.source == "risk_engine" for event in risk_events)


def test_projected_systems_never_claim_live_execution():
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(), fleet_result=fake_fleet_result()
    ))
    assert snapshot.live_execution is False
    assert all(system.live_execution is False for system in snapshot.systems)
    assert all(system.mode == "SHADOW" for system in snapshot.systems)
    assert all(system.execution_mode == "PAPER" for system in snapshot.systems)


def test_projector_exposes_scanner_opportunities_without_trade_direction():
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(), fleet_result=fake_fleet_result()
    ))
    assert len(snapshot.opportunities) == 3
    opportunity = snapshot.opportunities[0]
    assert opportunity.symbol == "BTCUSDT"
    assert opportunity.priority_score == 81
    assert opportunity.triggers == ("range_break",)
    assert not hasattr(opportunity, "side")


def test_projector_exposes_current_decisions_as_top_level_read_history():
    snapshot = asyncio.run(ShadowDashboardProjector(clock=lambda: NOW).capture(
        runner=fake_runner(), fleet_result=fake_fleet_result()
    ))
    assert len(snapshot.decisions) == 3
    assert {item.pipeline_status for item in snapshot.decisions} == {"EXECUTED"}
