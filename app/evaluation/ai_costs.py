from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .models import (
    ZERO,
    AICacheSliceMetrics,
    AICostMetrics,
    AIUsageEntry,
    Metric,
    OpportunityTrace,
)


def _cache_slice(items: tuple[AIUsageEntry, ...]) -> AICacheSliceMetrics:
    input_tokens = sum(item.input_tokens for item in items)
    cached_tokens = sum(item.cached_input_tokens for item in items)
    cache_write_tokens = sum(item.cache_write_tokens for item in items)
    output_tokens = sum(item.output_tokens for item in items)
    normal_tokens = sum(item.normal_input_tokens for item in items)
    actual_cost = sum((item.estimated_cost_eur for item in items), ZERO)

    cache_read_ratio = (
        Metric.available(Decimal(cached_tokens) / Decimal(input_tokens))
        if input_tokens > 0
        else Metric.unavailable("NO_AI_INPUT_TOKENS")
    )

    uncached_values = [item.estimated_cost_without_cache_eur for item in items]
    if all(value is not None for value in uncached_values):
        uncached = sum((value for value in uncached_values if value is not None), ZERO)
        uncached_metric = Metric.available(uncached)
        savings_metric = Metric.available(uncached - actual_cost)
    else:
        uncached_metric = Metric.unavailable("UNCACHED_COST_NOT_RECORDED")
        savings_metric = Metric.unavailable("UNCACHED_COST_NOT_RECORDED")

    return AICacheSliceMetrics(
        request_count=len(items),
        input_tokens=input_tokens,
        normal_input_tokens=normal_tokens,
        cached_input_tokens=cached_tokens,
        cache_write_tokens=cache_write_tokens,
        output_tokens=output_tokens,
        cache_read_ratio=cache_read_ratio,
        actual_cost_eur=actual_cost,
        estimated_cost_without_cache_eur=uncached_metric,
        net_cache_savings_eur=savings_metric,
    )


def _group_cache(
    usage: tuple[AIUsageEntry, ...],
    key,
) -> dict[str, AICacheSliceMetrics]:
    grouped: dict[str, list[AIUsageEntry]] = defaultdict(list)
    for item in usage:
        grouped[str(key(item))].append(item)
    return {
        name: _cache_slice(tuple(items))
        for name, items in sorted(grouped.items())
    }


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
        cache=_cache_slice(usage),
        cache_by_agent=AICostMetrics.freeze_cache(
            _group_cache(usage, lambda item: item.agent_id)
        ),
        cache_by_model=AICostMetrics.freeze_cache(
            _group_cache(usage, lambda item: item.model_id)
        ),
        cache_by_route=AICostMetrics.freeze_cache(
            _group_cache(usage, lambda item: item.route_id)
        ),
    )
