import inspect
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.evaluation import EvaluationService
from app.evaluation.lisbon import DeterministicLisbonReporter
from app.evaluation.models import (
    AgentCallEntry,
    AIUsageEntry,
    CounterfactualOutcome,
    EvaluationSource,
    ExecutionRecord,
    OpportunityTrace,
    SelfFundingStatus,
)


NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


def executions(exit_price: str):
    return (
        ExecutionRecord(
            "f1", "o1", "balanced_v1", "BTCUSDT", "BUY", "MARKET",
            Decimal("1"), Decimal("100"), Decimal("1"), NOW, Decimal("0")
        ),
        ExecutionRecord(
            "f2", "o2", "balanced_v1", "BTCUSDT", "SELL", "MARKET",
            Decimal("1"),
            Decimal(exit_price),
            Decimal("1"),
            NOW + timedelta(minutes=1),
            Decimal("0"),
        ),
    )


def trace() -> OpportunityTrace:
    call = AgentCallEntry("r1", "professor", "opp", "finalize", "v1", "route", "model")
    return OpportunityTrace(
        "opp", "snap", "balanced_v1", "LONG", "proposal", "risk", "APPROVED",
        "o1", "f1", ("v1",), (call,), ()
    )


def ai(cost: str):
    return AIUsageEntry("r1", "professor", "route", "model", Decimal(cost), 10, 1, NOW)


def test_trading_net_economic_net_and_self_funding_above_one() -> None:
    report = EvaluationService().evaluate(
        EvaluationSource(
            executions=executions("120"),
            ai_usage=(ai("5"),),
            opportunity_traces=(trace(),),
        )
    )
    assert report.trading.trading_net.value == Decimal("18")
    assert report.economic_net.value == Decimal("13")
    assert report.self_funding_ratio.status is SelfFundingStatus.AVAILABLE
    assert report.self_funding_ratio.value == Decimal("3.6")


def test_self_funding_below_one() -> None:
    report = EvaluationService().evaluate(
        EvaluationSource(
            executions=executions("105"),
            ai_usage=(ai("10"),),
            opportunity_traces=(trace(),),
        )
    )
    assert report.trading.trading_net.value == Decimal("3")
    assert report.economic_net.value == Decimal("-7")
    assert report.self_funding_ratio.value == Decimal("0.3")
    assert any(rec.code == "REVIEW_COMPUTE_EFFICIENCY" for rec in report.lisbon.recommendations)


def test_zero_ai_cost_returns_explicit_zero_cost_status_not_infinity() -> None:
    report = EvaluationService().evaluate(EvaluationSource(executions=executions("120")))
    assert report.self_funding_ratio.value is None
    assert report.self_funding_ratio.status is SelfFundingStatus.ZERO_AI_COST


def test_counterfactual_outcome_is_preserved_but_excluded_from_realized_metrics() -> None:
    counterfactual = CounterfactualOutcome(
        opportunity_id="opp-shadow",
        label="hypothetical_no_risk_rejection",
        hypothetical_pnl=Decimal("999"),
    )
    report = EvaluationService().evaluate(
        EvaluationSource(executions=executions("120"), counterfactual_outcomes=(counterfactual,))
    )
    assert report.trading.execution_realized_pnl == Decimal("20")
    assert report.counterfactual_outcomes == (counterfactual,)
    assert "COUNTERFACTUAL_EXCLUDED" in report.lisbon.data_scope


def test_lisbon_is_read_only_and_has_no_risk_or_budget_mutation_contract() -> None:
    signature = inspect.signature(DeterministicLisbonReporter.build)
    assert "risk_engine" not in signature.parameters
    assert "risk_profile" not in signature.parameters
    assert "budget" not in signature.parameters
    reporter = DeterministicLisbonReporter()
    assert not hasattr(reporter, "risk_engine")
    assert not hasattr(reporter, "budget_controller")
    assert not hasattr(reporter, "set_agent_state")
