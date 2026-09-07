from decimal import Decimal

from app.intelligence.ai_gateway import (
    ModelPricing,
    TokenUsage,
    calculate_cost_eur,
    estimate_max_request_cost_eur,
    estimate_upper_bound_input_tokens,
)


def test_cost_uses_separate_cached_rate():
    pricing = ModelPricing(
        input_per_million_eur=Decimal("2"),
        cached_input_per_million_eur=Decimal("0.5"),
        output_per_million_eur=Decimal("8"),
    )
    usage = TokenUsage(input_tokens=1_000_000, cached_input_tokens=400_000, output_tokens=100_000)
    assert calculate_cost_eur(usage, pricing) == Decimal("2.200000")


def test_input_upper_bound_accounts_for_utf8_and_overhead():
    assert estimate_upper_bound_input_tokens("abc", None) == 259
    assert estimate_upper_bound_input_tokens("é", None) == 258


def test_reservation_uses_expensive_uncached_input_rate():
    pricing = ModelPricing(
        input_per_million_eur=Decimal("10"),
        cached_input_per_million_eur=Decimal("1"),
        output_per_million_eur=Decimal("10"),
    )
    amount = estimate_max_request_cost_eur(
        input_text="x" * 100,
        instructions=None,
        max_output_tokens=100,
        pricing=pricing,
    )
    assert amount > Decimal("0")
