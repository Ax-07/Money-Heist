"""Manual paid smoke for OpenAI explicit Prompt Caching.

PAPER/analysis-only: this script imports no broker, Risk Engine execution router, or LIVE module.
It deliberately performs two AI calls with an identical stable agent/schema prefix and different
market payloads. It never pads the prefix to force cache eligibility.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from decimal import Decimal

from app.agents import Berlin
from app.intelligence.ai_gateway import (
    AIBudgetLedger,
    AIGateway,
    InMemoryAIUsageRecorder,
    ModelPricing,
    ModelRoute,
    ModelRouter,
    OpenAIResponsesClient,
    PromptCacheCapability,
    PromptCacheMode,
    PromptCachePolicy,
)


def _decimal(value: str) -> Decimal:
    return Decimal(value)


async def _run(args: argparse.Namespace) -> None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required for this manual paid smoke")

    pricing = ModelPricing(
        input_per_million_eur=args.input_price,
        cached_input_per_million_eur=args.cached_input_price,
        cache_write_input_per_million_eur=args.cache_write_price,
        output_per_million_eur=args.output_price,
    )
    policy = PromptCachePolicy(
        mode=PromptCacheMode.OPENAI_EXPLICIT,
        prompt_cache_key=args.prompt_cache_key,
    )
    route = ModelRoute(
        route_id="core_reasoning",
        provider="openai",
        model_id=args.model,
        pricing=pricing,
        max_output_tokens=args.max_output_tokens,
        reasoning_effort=args.reasoning_effort,
        prompt_cache_capability=PromptCacheCapability.OPENAI_EXPLICIT,
        prompt_cache_policy=policy,
    )
    usage = InMemoryAIUsageRecorder()
    gateway = AIGateway(
        router=ModelRouter([route]),
        clients={
            "openai": OpenAIResponsesClient(
                api_key=api_key,
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            )
        },
        budget=AIBudgetLedger(args.budget_eur),
        max_attempts=1,
        retry_backoff_seconds=0,
        usage_recorder=usage,
    )
    berlin = Berlin(gateway)

    contexts = (
        {
            "features": {"adx": 28.0, "rsi": 53.0},
            "structure": {"state": "trend"},
            "snapshot_marker": "prompt-cache-smoke-A",
        },
        {
            "features": {"adx": 31.0, "rsi": 57.0},
            "structure": {"state": "trend"},
            "snapshot_marker": "prompt-cache-smoke-B",
        },
    )

    results = []
    for index, market_context in enumerate(contexts, start=1):
        result = await berlin.analyze(
            system_id="prompt_cache_smoke_paper_only",
            opportunity={
                "symbol": "BTC/EUR",
                "snapshot_id": f"prompt-cache-smoke-{index}",
            },
            market_context=market_context,
        )
        results.append(result)
        record = result.usage
        print(
            f"call={index} model={record.model_id} "
            f"normal_input={record.normal_input_tokens} "
            f"cache_write={record.cache_write_tokens} "
            f"cache_read={record.cached_input_tokens} "
            f"output={record.output_tokens} cost_eur={record.estimated_cost} "
            f"uncached_estimate_eur={record.estimated_cost_without_cache} "
            f"prefix_sha256={record.stable_prefix_sha256}"
        )

    first, second = (item.usage for item in results)
    if first.stable_prefix_sha256 != second.stable_prefix_sha256:
        raise SystemExit("FAIL: stable prefix fingerprint changed across dynamic snapshots")

    print("stable_prefix_same=true")
    if first.cache_write_tokens == 0:
        print(
            "note=first call reported no cache write; the natural stable prefix may be below "
            "the provider eligibility threshold or the provider may have reused an existing entry"
        )
    if second.cached_input_tokens == 0:
        print(
            "note=second call reported no cache read; inspect provider diagnostics/eligibility. "
            "No artificial padding was added."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--budget-eur", type=_decimal, required=True)
    parser.add_argument("--input-price", type=_decimal, required=True)
    parser.add_argument("--cached-input-price", type=_decimal, required=True)
    parser.add_argument("--cache-write-price", type=_decimal, required=True)
    parser.add_argument("--output-price", type=_decimal, required=True)
    parser.add_argument("--prompt-cache-key", default=None)
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--max-output-tokens", type=int, default=800)
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
