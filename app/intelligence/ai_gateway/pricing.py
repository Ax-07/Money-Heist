from __future__ import annotations

import json
from decimal import ROUND_UP, Decimal

from .models import TokenUsage
from .routing import ModelPricing

_ONE_MILLION = Decimal("1000000")
_CENT = Decimal("0.000001")


def _money(amount: Decimal) -> Decimal:
    return amount.quantize(_CENT, rounding=ROUND_UP)


def calculate_cost_eur(usage: TokenUsage, pricing: ModelPricing) -> Decimal:
    """Calculate actual provider cost from the four mutually exclusive token buckets."""

    amount = (
        Decimal(usage.normal_input_tokens) * pricing.input_per_million_eur
        + Decimal(usage.cached_input_tokens) * pricing.cached_rate()
        + Decimal(usage.cache_write_tokens) * pricing.cache_write_rate()
        + Decimal(usage.output_tokens) * pricing.output_per_million_eur
    ) / _ONE_MILLION
    return _money(amount)


def calculate_uncached_cost_eur(usage: TokenUsage, pricing: ModelPricing) -> Decimal:
    """Counterfactual cost if every input token had been processed at normal input price."""

    amount = (
        Decimal(usage.input_tokens) * pricing.input_per_million_eur
        + Decimal(usage.output_tokens) * pricing.output_per_million_eur
    ) / _ONE_MILLION
    return _money(amount)


def estimate_upper_bound_input_tokens(
    input_text: str,
    instructions: str | None,
    *,
    json_schema: dict | None = None,
    cacheable_developer_prefix: str | None = None,
) -> int:
    """Conservative tokenizer-free upper bound based on UTF-8 bytes plus framing headroom.

    This intentionally over-reserves: one UTF-8 byte is treated as up to one input token.
    Structured Output schema bytes and the provider-facing stable prefix are included because
    both contribute provider context even though the historical implementation only counted
    `input_text` and top-level instructions.
    """

    payload_bytes = len(input_text.encode("utf-8"))
    if cacheable_developer_prefix is not None:
        payload_bytes += len(cacheable_developer_prefix.encode("utf-8"))
    elif instructions:
        payload_bytes += len(instructions.encode("utf-8"))
    if json_schema is not None:
        payload_bytes += len(
            json.dumps(
                json_schema,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        )
    return payload_bytes + 256


def estimate_max_request_cost_eur(
    *,
    input_text: str,
    instructions: str | None,
    max_output_tokens: int,
    pricing: ModelPricing,
    json_schema: dict | None = None,
    cacheable_developer_prefix: str | None = None,
) -> Decimal:
    input_upper_bound = estimate_upper_bound_input_tokens(
        input_text,
        instructions,
        json_schema=json_schema,
        cacheable_developer_prefix=cacheable_developer_prefix,
    )
    amount = (
        Decimal(input_upper_bound) * pricing.worst_input_rate()
        + Decimal(max_output_tokens) * pricing.output_per_million_eur
    ) / _ONE_MILLION
    return _money(amount)
