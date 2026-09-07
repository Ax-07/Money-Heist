from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .models import AICostMetrics, AIUsageEntry, Metric, OpportunityTrace, ZERO


def calculate_ai_cost_metrics(
    usage: tuple[AIUsageEntry, ...],
    traces: tuple[OpportunityTrace, ...],
) -> AICostMetrics:
    by_agent: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_model: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_route: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_opportunity: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_risk: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_trade: dict[str, Decimal] = defaultdict(lambda: ZERO)

    request_to_trace: dict[str, OpportunityTrace] = {}
    for trace in traces:
        request_ids = {call.request_id for call in trace.agent_calls} | set(
            trace.agent_request_ids
        )
        for request_id in request_ids:
            existing = request_to_trace.get(request_id)
            if existing is not None and existing.opportunity_id != trace.opportunity_id:
                raise ValueError(
                    f"AI request {request_id} is linked to multiple opportunities"
                )
            request_to_trace[request_id] = trace

    total = ZERO
    unattributed = ZERO
    for item in usage:
        total += item.estimated_cost_eur
        by_agent[item.agent_id] += item.estimated_cost_eur
        by_model[item.model_id] += item.estimated_cost_eur
        by_route[item.route_id] += item.estimated_cost_eur

        trace = request_to_trace.get(item.request_id)
        if trace is None:
            unattributed += item.estimated_cost_eur
            continue
        by_opportunity[trace.opportunity_id] += item.estimated_cost_eur
        if trace.risk_decision_id is not None:
            by_risk[trace.risk_decision_id] += item.estimated_cost_eur
        if trace.broker_order_id is not None:
            by_trade[trace.broker_order_id] += item.estimated_cost_eur

    average_per_opportunity = (
        Metric.available(sum(by_opportunity.values(), ZERO) / Decimal(len(by_opportunity)))
        if by_opportunity
        else Metric.unavailable("NO_ATTRIBUTED_OPPORTUNITIES")
    )
    average_per_risk = (
        Metric.available(sum(by_risk.values(), ZERO) / Decimal(len(by_risk)))
        if by_risk
        else Metric.unavailable("NO_ATTRIBUTED_RISK_DECISIONS")
    )
    average_per_trade = (
        Metric.available(sum(by_trade.values(), ZERO) / Decimal(len(by_trade)))
        if by_trade
        else Metric.unavailable("NO_ATTRIBUTED_EXECUTED_TRADES")
    )

    return AICostMetrics(
        total_cost_eur=total,
        by_agent=AICostMetrics.freeze(by_agent),
        by_model=AICostMetrics.freeze(by_model),
        by_route=AICostMetrics.freeze(by_route),
        by_opportunity=AICostMetrics.freeze(by_opportunity),
        by_risk_decision=AICostMetrics.freeze(by_risk),
        by_trade=AICostMetrics.freeze(by_trade),
        unattributed_to_opportunity_eur=unattributed,
        average_cost_per_opportunity=average_per_opportunity,
        average_cost_per_risk_decision=average_per_risk,
        average_cost_per_executed_trade=average_per_trade,
    )
