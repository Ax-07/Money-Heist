from decimal import Decimal

from app.evaluation.ai_costs import calculate_ai_cost_metrics
from app.evaluation.models import AIUsageEntry, MetricStatus


def _usage(
    request_id: str,
    *,
    input_tokens: int,
    cached_input_tokens: int,
    cache_write_tokens: int,
    output_tokens: int,
    cost: str,
    uncached_cost: str,
    agent: str = "berlin",
    route: str = "core_reasoning",
    model: str = "model-test",
) -> AIUsageEntry:
    return AIUsageEntry(
        request_id=request_id,
        agent_id=agent,
        route_id=route,
        model_id=model,
        estimated_cost_eur=Decimal(cost),
        latency_ms=10,
        attempt=1,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        cache_write_tokens=cache_write_tokens,
        output_tokens=output_tokens,
        estimated_cost_without_cache_eur=Decimal(uncached_cost),
        prompt_cache_mode="openai_explicit",
        prompt_render_version="money-heist.prompt-transport.v2",
    )


def test_cache_metrics_distinguish_initial_write_and_later_read() -> None:
    usage = (
        _usage(
            "write",
            input_tokens=1000,
            cached_input_tokens=0,
            cache_write_tokens=800,
            output_tokens=50,
            cost="0.0030",
            uncached_cost="0.0025",
        ),
        _usage(
            "read",
            input_tokens=1000,
            cached_input_tokens=800,
            cache_write_tokens=0,
            output_tokens=50,
            cost="0.0010",
            uncached_cost="0.0025",
        ),
    )

    metrics = calculate_ai_cost_metrics(usage, ())

    assert metrics.cache.normal_input_tokens == 400
    assert metrics.cache.cache_write_tokens == 800
    assert metrics.cache.cached_input_tokens == 800
    assert metrics.cache.output_tokens == 100
    assert metrics.cache.actual_cost_eur == Decimal("0.0040")
    assert metrics.cache.estimated_cost_without_cache_eur.value == Decimal("0.0050")
    assert metrics.cache.net_cache_savings_eur.value == Decimal("0.0010")
    assert metrics.cache.cache_read_ratio.value == Decimal("0.4")
    assert metrics.cache.net_cache_savings_eur.status is MetricStatus.AVAILABLE


def test_cache_activity_without_uncached_baseline_does_not_claim_savings() -> None:
    item = AIUsageEntry(
        request_id="read",
        agent_id="berlin",
        route_id="core_reasoning",
        model_id="model-test",
        estimated_cost_eur=Decimal("0.001"),
        latency_ms=10,
        attempt=1,
        input_tokens=1000,
        cached_input_tokens=800,
        cache_write_tokens=0,
        output_tokens=50,
        estimated_cost_without_cache_eur=None,
        prompt_cache_mode="openai_explicit",
    )

    metrics = calculate_ai_cost_metrics((item,), ())

    assert metrics.cache.cached_input_tokens == 800
    assert metrics.cache.net_cache_savings_eur.status is MetricStatus.UNAVAILABLE
