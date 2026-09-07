from __future__ import annotations

from decimal import Decimal, ROUND_UP

from .models import TokenUsage
from .routing import ModelPricing


_ONE_MILLION = Decimal("1000000")
_CENT = Decimal("0.000001")


def calculate_cost_eur(usage: TokenUsage, pricing: ModelPricing) -> Decimal:
    non_cached = max(usage.input_tokens - usage.cached_input_tokens, 0)
    amount = (
        Decimal(non_cached) * pricing.input_per_million_eur
        + Decimal(usage.cached_input_tokens) * pricing.cached_rate()
        + Decimal(usage.output_tokens) * pricing.output_per_million_eur
    ) / _ONE_MILLION
    return amount.quantize(_CENT, rounding=ROUND_UP)


def estimate_upper_bound_input_tokens(input_text: str, instructions: str | None) -> int:
    """Conservative tokenizer-free upper bound based on UTF-8 bytes plus framing headroom."""

    payload_bytes = len(input_text.encode("utf-8"))
    if instructions:
        payload_bytes += len(instructions.encode("utf-8"))
    return payload_bytes + 256


def estimate_max_request_cost_eur(
    *,
    input_text: str,
    instructions: str | None,
    max_output_tokens: int,
    pricing: ModelPricing,
) -> Decimal:
    input_upper_bound = estimate_upper_bound_input_tokens(input_text, instructions)
    # Cached input is not assumed for the reservation: the expensive input rate is used.
    usage = TokenUsage(
        input_tokens=input_upper_bound,
        cached_input_tokens=0,
        output_tokens=max_output_tokens,
    )
    return calculate_cost_eur(usage, pricing)
