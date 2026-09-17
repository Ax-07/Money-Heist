from __future__ import annotations

import asyncio
from decimal import Decimal

from pydantic import BaseModel

from app.intelligence.ai_gateway import (
    AGENT_DIALOGUE_LANGUAGE,
    AGENT_DIALOGUE_LANGUAGE_VERSION,
    PROMPT_TRANSPORT_VERSION,
    AIBudgetLedger,
    AIGateway,
    AIGatewayRequest,
    ModelPricing,
    ModelRoute,
    ModelRouter,
    ProviderResponse,
    TokenUsage,
    apply_agent_dialogue_language_contract,
)


class _Decision(BaseModel):
    stance: str
    explanation: str


class _RecordingClient:
    provider_name = "openai"

    def __init__(self) -> None:
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ProviderResponse(
            provider_request_id="resp-fr",
            model_id=request.model_id,
            output_text='{"stance":"LONG","explanation":"Signal confirmé."}',
            usage=TokenUsage(input_tokens=20, output_tokens=5),
            latency_ms=1,
        )


def _route() -> ModelRoute:
    return ModelRoute(
        route_id="core_reasoning",
        provider="openai",
        model_id="configured-model",
        pricing=ModelPricing(
            input_per_million_eur=Decimal("1"),
            output_per_million_eur=Decimal("1"),
        ),
    )


def test_language_contract_is_french_and_preserves_machine_tokens():
    rendered = apply_agent_dialogue_language_contract("Return LONG or NO_TRADE.")
    assert AGENT_DIALOGUE_LANGUAGE == "fr-FR"
    assert AGENT_DIALOGUE_LANGUAGE_VERSION == "money-heist.agent-dialogue.fr.v1"
    assert PROMPT_TRANSPORT_VERSION == "money-heist.prompt-transport.v3"
    assert "français" in rendered
    assert "LONG" in rendered
    assert "NO_TRADE" in rendered
    assert "clés JSON" in rendered
    assert "source_key/source_index" in rendered


def test_language_contract_is_idempotent():
    first = apply_agent_dialogue_language_contract("Stable instructions.")
    second = apply_agent_dialogue_language_contract(first)
    assert first == second


def test_gateway_applies_french_contract_without_changing_structured_enum_value():
    async def scenario():
        client = _RecordingClient()
        gateway = AIGateway(
            router=ModelRouter([_route()]),
            clients={"openai": client},
            budget=AIBudgetLedger(Decimal("10")),
            max_attempts=1,
            retry_backoff_seconds=0,
        )
        result = await gateway.generate_structured(
            AIGatewayRequest(
                system_id="balanced_v1",
                agent_id="berlin",
                prompt_version="v5",
                model_route="core_reasoning",
                instructions="Analyze the supplied market context.",
                input_text='{"price":123}',
            ),
            _Decision,
        )
        return client.requests[0], result

    provider_request, result = asyncio.run(scenario())
    assert "money-heist.agent-dialogue.fr.v1" in provider_request.instructions
    assert "français" in provider_request.instructions
    assert result.output.stance == "LONG"
    assert result.output.explanation == "Signal confirmé."
