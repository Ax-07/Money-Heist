import asyncio
from decimal import Decimal

from pydantic import BaseModel

from app.intelligence.ai_gateway import (
    AIBudgetLedger,
    AIGateway,
    AIGatewayRequest,
    ModelPricing,
    ModelRoute,
    ModelRouter,
    PromptCacheCapability,
    PromptCacheMode,
    PromptCachePolicy,
    ProviderResponse,
    TokenUsage,
)


class Decision(BaseModel):
    stance: str


class RecordingClient:
    provider_name = "openai"

    def __init__(self) -> None:
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ProviderResponse(
            provider_request_id="resp-test",
            model_id=request.model_id,
            output_text='{"stance":"LONG"}',
            usage=TokenUsage(input_tokens=10, output_tokens=2),
            latency_ms=1,
        )


def route(*, cache: bool) -> ModelRoute:
    return ModelRoute(
        route_id="core_reasoning",
        provider="openai",
        model_id="configured-model",
        pricing=ModelPricing(
            input_per_million_eur=Decimal("1"),
            output_per_million_eur=Decimal("1"),
            cached_input_per_million_eur=Decimal("0.1"),
            cache_write_input_per_million_eur=Decimal("1.25"),
        ),
        prompt_cache_capability=(
            PromptCacheCapability.OPENAI_EXPLICIT
            if cache
            else PromptCacheCapability.NONE
        ),
        prompt_cache_policy=PromptCachePolicy(
            mode=(
                PromptCacheMode.OPENAI_EXPLICIT
                if cache
                else PromptCacheMode.DISABLED
            )
        ),
    )


def test_dynamic_snapshot_does_not_change_stable_prefix_or_schema_fingerprint():
    async def scenario():
        client = RecordingClient()
        gateway = AIGateway(
            router=ModelRouter([route(cache=True)]),
            clients={"openai": client},
            budget=AIBudgetLedger(Decimal("10")),
            max_attempts=1,
            retry_backoff_seconds=0,
        )
        for snapshot in ("snapshot-A", "snapshot-B"):
            await gateway.generate_structured(
                AIGatewayRequest(
                    system_id="balanced_v1",
                    agent_id="berlin",
                    prompt_version="v5",
                    model_route="core_reasoning",
                    instructions="Stable Berlin instructions.",
                    input_text=f'{{"snapshot_id":"{snapshot}","price":123}}',
                ),
                Decision,
            )
        return client.requests

    first, second = asyncio.run(scenario())
    assert first.input_text != second.input_text
    assert first.cacheable_developer_prefix == second.cacheable_developer_prefix
    assert first.stable_prefix_sha256 == second.stable_prefix_sha256
    assert first.schema_sha256 == second.schema_sha256
    assert first.prompt_cache_mode == second.prompt_cache_mode == "openai_explicit"
    assert "snapshot-A" not in first.cacheable_developer_prefix
    assert "snapshot-B" not in second.cacheable_developer_prefix


def test_no_cache_route_preserves_simple_transport_contract():
    async def scenario():
        client = RecordingClient()
        gateway = AIGateway(
            router=ModelRouter([route(cache=False)]),
            clients={"openai": client},
            budget=AIBudgetLedger(Decimal("10")),
            max_attempts=1,
            retry_backoff_seconds=0,
        )
        await gateway.generate_structured(
            AIGatewayRequest(
                system_id="balanced_v1",
                agent_id="berlin",
                prompt_version="v5",
                model_route="core_reasoning",
                instructions="Stable Berlin instructions.",
                input_text='{"snapshot_id":"snapshot-A"}',
            ),
            Decision,
        )
        return client.requests[0]

    request = asyncio.run(scenario())
    assert request.prompt_cache_mode == "disabled"
    assert request.cacheable_developer_prefix is None
    assert request.stable_prefix_sha256 is None


def test_route_must_explicitly_declare_openai_cache_capability():
    try:
        ModelRoute(
            route_id="bad",
            provider="openai",
            model_id="anything",
            pricing=ModelPricing(
                input_per_million_eur=Decimal("1"),
                output_per_million_eur=Decimal("1"),
            ),
            prompt_cache_policy=PromptCachePolicy(mode=PromptCacheMode.OPENAI_EXPLICIT),
        )
    except ValueError:
        return
    raise AssertionError("route accepted cache policy without declared capability")


def test_hard_budget_rejects_request_when_cache_write_worst_case_does_not_fit():
    async def scenario():
        client = RecordingClient()
        costly = ModelRoute(
            route_id="core_reasoning",
            provider="openai",
            model_id="configured-model",
            pricing=ModelPricing(
                input_per_million_eur=Decimal("0.01"),
                output_per_million_eur=Decimal("0"),
                cached_input_per_million_eur=Decimal("0.001"),
                cache_write_input_per_million_eur=Decimal("1000"),
            ),
            max_output_tokens=1,
            prompt_cache_capability=PromptCacheCapability.OPENAI_EXPLICIT,
            prompt_cache_policy=PromptCachePolicy(mode=PromptCacheMode.OPENAI_EXPLICIT),
        )
        gateway = AIGateway(
            router=ModelRouter([costly]),
            clients={"openai": client},
            budget=AIBudgetLedger(Decimal("0.000001")),
            max_attempts=1,
            retry_backoff_seconds=0,
        )
        await gateway.generate_structured(
            AIGatewayRequest(
                system_id="balanced_v1",
                agent_id="berlin",
                prompt_version="v5",
                model_route="core_reasoning",
                instructions="stable",
                input_text="dynamic",
                max_output_tokens=1,
            ),
            Decision,
        )

    from app.intelligence.ai_gateway import BudgetExceededError

    try:
        asyncio.run(scenario())
    except BudgetExceededError:
        return
    raise AssertionError("hard budget did not fail closed on cache-write worst case")
