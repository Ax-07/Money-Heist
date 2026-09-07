from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from types import MappingProxyType

from .models import AgentMetrics, AIUsageEntry, Metric, OpportunityTrace, ZERO


def calculate_agent_metrics(
    usage: tuple[AIUsageEntry, ...],
    traces: tuple[OpportunityTrace, ...],
) -> tuple[AgentMetrics, ...]:
    total_opportunities = len({trace.opportunity_id for trace in traces})
    usage_by_agent: dict[str, list[AIUsageEntry]] = defaultdict(list)
    usage_by_request: dict[str, list[AIUsageEntry]] = defaultdict(list)
    for item in usage:
        usage_by_agent[item.agent_id].append(item)
        usage_by_request[item.request_id].append(item)

    calls_by_agent = defaultdict(list)
    observations_by_agent = defaultdict(list)
    decisions_by_agent: dict[str, Counter[str]] = defaultdict(Counter)
    opportunities_by_agent: dict[str, set[str]] = defaultdict(set)

    for trace in traces:
        participating_agents = set()
        for request_id in trace.agent_request_ids:
            for usage_item in usage_by_request.get(request_id, ()):
                participating_agents.add(usage_item.agent_id)
                opportunities_by_agent[usage_item.agent_id].add(trace.opportunity_id)
        for call in trace.agent_calls:
            calls_by_agent[call.agent_id].append(call)
            participating_agents.add(call.agent_id)
            opportunities_by_agent[call.agent_id].add(trace.opportunity_id)
        for observation in trace.observations:
            observations_by_agent[observation.agent_id].append(observation)
        if trace.final_decision is not None:
            for agent_id in participating_agents:
                decisions_by_agent[agent_id][trace.final_decision] += 1

    agent_ids = sorted(set(usage_by_agent) | set(calls_by_agent) | set(observations_by_agent))
    result = []
    for agent_id in agent_ids:
        agent_usage = usage_by_agent[agent_id]
        calls = calls_by_agent[agent_id]
        observations = observations_by_agent[agent_id]

        request_ids = {item.request_id for item in agent_usage} | {
            call.request_id for call in calls
        }
        call_count = len(request_ids)
        total_cost = sum((item.estimated_cost_eur for item in agent_usage), ZERO)
        average_cost = (
            Metric.available(total_cost / Decimal(call_count))
            if call_count
            else Metric.unavailable("NO_CALLS")
        )

        latencies = [
            Decimal(item.latency_ms)
            for item in agent_usage
            if item.latency_ms is not None
        ]
        average_latency = (
            Metric.available(sum(latencies, ZERO) / Decimal(len(latencies)))
            if latencies
            else Metric.unavailable("LATENCY_NOT_AVAILABLE")
        )

        participation = (
            Metric.available(
                Decimal(len(opportunities_by_agent[agent_id])) / Decimal(total_opportunities)
            )
            if total_opportunities
            else Metric.unavailable("NO_OPPORTUNITIES")
        )

        comparable = [
            observation
            for observation in observations
            if observation.phase == "specialist"
            and observation.stance in {"LONG", "SHORT", "NEUTRAL"}
            and observation.final_decision in {"LONG", "SHORT"}
        ]
        if comparable:
            disagreements = sum(
                observation.stance != observation.final_decision for observation in comparable
            )
            disagreement = Metric.available(
                Decimal(disagreements) / Decimal(len(comparable))
            )
        else:
            disagreement = Metric.unavailable("NO_COMPARABLE_DIRECTIONAL_DECISIONS")

        confidences = [
            observation.confidence
            for observation in observations
            if observation.confidence is not None
        ]
        average_confidence = (
            Metric.available(sum(confidences, ZERO) / Decimal(len(confidences)))
            if confidences
            else Metric.unavailable("CONFIDENCE_NOT_AVAILABLE")
        )

        stance_counts = Counter(
            observation.stance for observation in observations if observation.stance is not None
        )
        prompt_versions = sorted(
            {call.prompt_version for call in calls if call.prompt_version is not None}
        )
        route_ids = sorted(
            {item.route_id for item in agent_usage}
            | {call.route_id for call in calls if call.route_id is not None}
        )
        model_ids = sorted(
            {item.model_id for item in agent_usage}
            | {call.model_id for call in calls if call.model_id is not None}
        )

        result.append(
            AgentMetrics(
                agent_id=agent_id,
                call_count=call_count,
                attempt_count=len(agent_usage),
                total_cost_eur=total_cost,
                average_cost_eur=average_cost,
                average_latency_ms=average_latency,
                participation_frequency=participation,
                disagreement_frequency=disagreement,
                average_confidence=average_confidence,
                stance_counts=MappingProxyType(dict(sorted(stance_counts.items()))),
                final_decision_counts=MappingProxyType(
                    dict(sorted(decisions_by_agent[agent_id].items()))
                ),
                prompt_versions=tuple(prompt_versions),
                route_ids=tuple(route_ids),
                model_ids=tuple(model_ids),
            )
        )

    return tuple(result)
