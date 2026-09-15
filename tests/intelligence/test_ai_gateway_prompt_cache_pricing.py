from decimal import Decimal

import pytest

from app.intelligence.ai_gateway.models import TokenUsage
from app.intelligence.ai_gateway.pricing import (
    calculate_cost_eur,
    calculate_uncached_cost_eur,
    estimate_max_request_cost_eur,
)
from app.intelligence.ai_gateway.routing import ModelPricing


def pricing() -> ModelPricing:
    return ModelPricing(
        input_per_million_eur=Decimal("2"),
        output_per_million_eur=Decimal("10"),
        cached_input_per_million_eur=Decimal("0.2"),
        cache_write_input_per_million_eur=Decimal("2.5"),
    )


def test_cost_separates_normal_cache_write_cache_read_and_output():
    usage = TokenUsage(
        input_tokens=1000,
        cached_input_tokens=200,
        cache_write_tokens=300,
        output_tokens=100,
    )
    # 500*2 + 200*.2 + 300*2.5 + 100*10 = 2790 / 1M
    assert usage.normal_input_tokens == 500
    assert calculate_cost_eur(usage, pricing()) == Decimal("0.002790")
    # Counterfactual: every 1000 input token at ordinary input price + output.
    assert calculate_uncached_cost_eur(usage, pricing()) == Decimal("0.003000")


def test_token_usage_rejects_overlapping_input_buckets_fail_closed():
    with pytest.raises(ValueError):
        TokenUsage(
            input_tokens=10,
            cached_input_tokens=8,
            cache_write_tokens=3,
            output_tokens=0,
        )


def test_mock_compatibility_defaults_cache_write_tokens_to_zero():
    usage = TokenUsage(input_tokens=12, cached_input_tokens=2, output_tokens=1)
    assert usage.cache_write_tokens == 0
    assert usage.normal_input_tokens == 10


def test_budget_reservation_uses_cache_write_rate_when_it_is_the_worst_case():
    expensive_write = ModelPricing(
        input_per_million_eur=Decimal("1"),
        output_per_million_eur=Decimal("0"),
        cached_input_per_million_eur=Decimal("0.1"),
        cache_write_input_per_million_eur=Decimal("4"),
    )
    normal_only = ModelPricing(
        input_per_million_eur=Decimal("1"),
        output_per_million_eur=Decimal("0"),
        cached_input_per_million_eur=Decimal("0.1"),
        cache_write_input_per_million_eur=Decimal("1"),
    )
    kwargs = dict(
        input_text="x" * 1000,
        instructions="stable",
        max_output_tokens=1,
        json_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )
    assert estimate_max_request_cost_eur(pricing=expensive_write, **kwargs) > (
        estimate_max_request_cost_eur(pricing=normal_only, **kwargs)
    )
