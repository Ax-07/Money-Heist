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
    ProviderResponse,
    TokenUsage,
)


class Decision(BaseModel):
    stance: str


class RecordingClient:
    provider_name = "mock"

    def __init__(self) -> None:
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ProviderResponse(
            provider_request_id="timeout-test",
            model_id=request.model_id,
            output_text='{"stance":"NO_TRADE"}',
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            latency_ms=1,
        )


def _gateway(client: RecordingClient) -> AIGateway:
    route = ModelRoute(
        route_id="core_reasoning",
        provider="mock",
        model_id="mock-model",
        pricing=ModelPricing(
            input_per_million_eur=Decimal("0"),
            output_per_million_eur=Decimal("0"),
        ),
        max_output_tokens=1200,
        timeout_seconds=30.0,
    )
    return AIGateway(
        router=ModelRouter([route]),
        clients={"mock": client},
        budget=AIBudgetLedger("1"),
        max_attempts=1,
        retry_backoff_seconds=0,
    )


def test_request_timeout_override_reaches_provider():
    client = RecordingClient()
    request = AIGatewayRequest(
        system_id="balanced_v1",
        agent_id="palermo",
        prompt_version="v1",
        model_route="core_reasoning",
        input_text="x",
        timeout_seconds=90.0,
    )

    asyncio.run(_gateway(client).generate_structured(request, Decision))

    assert len(client.requests) == 1
    assert client.requests[0].timeout_seconds == 90.0


def test_route_timeout_remains_default_without_request_override():
    client = RecordingClient()
    request = AIGatewayRequest(
        system_id="balanced_v1",
        agent_id="berlin",
        prompt_version="v1",
        model_route="core_reasoning",
        input_text="x",
    )

    asyncio.run(_gateway(client).generate_structured(request, Decision))

    assert len(client.requests) == 1
    assert client.requests[0].timeout_seconds == 30.0
