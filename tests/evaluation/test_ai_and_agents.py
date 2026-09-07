from datetime import datetime, timezone
from decimal import Decimal

from app.evaluation import calculate_agent_metrics, calculate_ai_cost_metrics
from app.evaluation.models import (
    AgentCallEntry,
    AgentObservation,
    AIUsageEntry,
    OpportunityTrace,
)


NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


def usage(request: str, agent: str, cost: str, route: str, model: str, latency: int = 100):
    return AIUsageEntry(
        request_id=request,
        agent_id=agent,
        route_id=route,
        model_id=model,
        estimated_cost_eur=Decimal(cost),
        latency_ms=latency,
        attempt=1,
        created_at=NOW,
    )


def call(request: str, agent: str, opportunity: str, prompt: str, route: str, model: str):
    return AgentCallEntry(
        request_id=request,
        agent_id=agent,
        opportunity_id=opportunity,
        phase="specialist" if agent in {"berlin", "tokyo", "nairobi"} else "core",
        prompt_version=prompt,
        route_id=route,
        model_id=model,
    )


def trace_one() -> OpportunityTrace:
    calls = (
        call("r-prof", "professor", "opp-1", "professor.v2", "route-pro", "gpt-pro"),
        call("r-ber", "berlin", "opp-1", "berlin.v1", "route-mini", "gpt-mini"),
        call("r-tok", "tokyo", "opp-1", "tokyo.v1", "route-mini", "gpt-mini"),
        call("r-nai", "nairobi", "opp-1", "nairobi.v1", "route-mini", "gpt-mini"),
        call("r-pal", "palermo", "opp-1", "palermo.v1", "route-mini", "gpt-mini"),
    )
    observations = (
        AgentObservation("r-ber", "berlin", "opp-1", "specialist", "LONG", Decimal("0.8"), "LONG"),
        AgentObservation("r-tok", "tokyo", "opp-1", "specialist", "SHORT", Decimal("0.6"), "LONG"),
        AgentObservation(
            "r-nai", "nairobi", "opp-1", "specialist", "NEUTRAL", Decimal("0.7"), "LONG"
        ),
        AgentObservation("r-pal", "palermo", "opp-1", "red_team", "CAUTION", None, "LONG"),
        AgentObservation(
            "r-prof",
            "professor",
            "opp-1",
            "final_decision",
            "LONG",
            Decimal("0.75"),
            "LONG",
        ),
    )
    return OpportunityTrace(
        opportunity_id="opp-1",
        source_snapshot_id="snap-1",
        system_id="balanced_v1",
        final_decision="LONG",
        proposal_id="prop-1",
        risk_decision_id="risk-1",
        risk_status="APPROVED",
        broker_order_id="order-1",
        fill_id="fill-1",
        prompt_versions=tuple(item.prompt_version for item in calls if item.prompt_version),
        agent_calls=calls,
        observations=observations,
    )


def test_ai_cost_total_by_agent_opportunity_risk_trade_model_and_route() -> None:
    entries = (
        usage("r-prof", "professor", "0.05", "route-pro", "gpt-pro"),
        usage("r-ber", "berlin", "0.01", "route-mini", "gpt-mini"),
        usage("r-tok", "tokyo", "0.02", "route-mini", "gpt-mini"),
        usage("r-nai", "nairobi", "0.01", "route-mini", "gpt-mini"),
        usage("r-pal", "palermo", "0.01", "route-mini", "gpt-mini"),
    )
    metrics = calculate_ai_cost_metrics(entries, (trace_one(),))
    assert metrics.total_cost_eur == Decimal("0.10")
    assert metrics.by_agent["berlin"] == Decimal("0.01")
    assert metrics.by_agent["professor"] == Decimal("0.05")
    assert metrics.by_opportunity["opp-1"] == Decimal("0.10")
    assert metrics.by_risk_decision["risk-1"] == Decimal("0.10")
    assert metrics.by_trade["order-1"] == Decimal("0.10")
    assert metrics.by_model["gpt-mini"] == Decimal("0.05")
    assert metrics.by_route["route-mini"] == Decimal("0.05")
    assert metrics.average_cost_per_opportunity.value == Decimal("0.10")
    assert metrics.average_cost_per_risk_decision.value == Decimal("0.10")
    assert metrics.average_cost_per_executed_trade.value == Decimal("0.10")


def test_unattributed_usage_is_kept_in_total_but_not_falsely_attached() -> None:
    entries = (usage("unknown", "lisbon", "0.03", "route-mini", "gpt-mini"),)
    metrics = calculate_ai_cost_metrics(entries, (trace_one(),))
    assert metrics.total_cost_eur == Decimal("0.03")
    assert metrics.unattributed_to_opportunity_eur == Decimal("0.03")
    assert not metrics.by_opportunity
    assert metrics.average_cost_per_executed_trade.value is None


def test_agent_metrics_cover_core_and_specialists_and_keep_versions() -> None:
    entries = (
        usage("r-prof", "professor", "0.05", "route-pro", "gpt-pro", 200),
        usage("r-ber", "berlin", "0.01", "route-mini", "gpt-mini", 100),
        usage("r-tok", "tokyo", "0.02", "route-mini", "gpt-mini", 120),
        usage("r-nai", "nairobi", "0.01", "route-mini", "gpt-mini", 110),
        usage("r-pal", "palermo", "0.01", "route-mini", "gpt-mini", 130),
    )
    metrics = {item.agent_id: item for item in calculate_agent_metrics(entries, (trace_one(),))}
    assert set(metrics) == {"berlin", "tokyo", "nairobi", "palermo", "professor"}
    assert metrics["berlin"].call_count == 1
    assert metrics["berlin"].total_cost_eur == Decimal("0.01")
    assert metrics["berlin"].average_latency_ms.value == Decimal("100")
    assert metrics["berlin"].average_confidence.value == Decimal("0.8")
    assert metrics["berlin"].participation_frequency.value == Decimal("1")
    assert metrics["berlin"].stance_counts["LONG"] == 1
    assert metrics["berlin"].disagreement_frequency.value == Decimal("0")
    assert metrics["tokyo"].disagreement_frequency.value == Decimal("1")
    assert metrics["nairobi"].disagreement_frequency.value == Decimal("1")
    assert metrics["palermo"].average_confidence.value is None
    assert metrics["palermo"].disagreement_frequency.value is None
    assert metrics["professor"].prompt_versions == ("professor.v2",)
    assert metrics["professor"].model_ids == ("gpt-pro",)
    assert metrics["professor"].route_ids == ("route-pro",)
    assert metrics["professor"].final_decision_counts["LONG"] == 1
