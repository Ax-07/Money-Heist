import asyncio
from decimal import Decimal

import pytest
from pydantic import BaseModel, Field

from app.intelligence.ai_gateway import (
    AIBudgetLedger,
    AIGateway,
    AIGatewayRequest,
    BudgetExceededError,
    MockAIClient,
    ModelPricing,
    ModelRoute,
    ModelRouter,
    ProviderResponse,
    RetryableAIProviderError,
    StructuredOutputError,
    TokenUsage,
)


class Decision(BaseModel):
    stance: str
    confidence: float = Field(ge=0, le=1)


def build_gateway(responses, *, budget="5", max_attempts=2, routes=None):
    client = MockAIClient(responses)
    routes = routes or [
        ModelRoute(
            route_id="primary",
            provider="mock",
            model_id="mock-primary",
            pricing=ModelPricing(
                input_per_million_eur=Decimal("1"),
                output_per_million_eur=Decimal("2"),
            ),
            max_output_tokens=100,
        )
    ]
    gateway = AIGateway(
        router=ModelRouter(routes),
        clients={"mock": client},
        budget=AIBudgetLedger(budget),
        max_attempts=max_attempts,
        retry_backoff_seconds=0,
    )
    return gateway, client


def request(route="primary"):
    return AIGatewayRequest(
        system_id="balanced_v1",
        agent_id="berlin",
        prompt_version="v1",
        model_route=route,
        input_text="Analyse BTC",
    )


def response(text, *, model="mock-primary", input_tokens=100, output_tokens=20):
    return ProviderResponse(
        provider_request_id="mock-response-1",
        model_id=model,
        output_text=text,
        usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        latency_ms=3,
    )


def test_mock_gateway_returns_validated_structured_output_and_usage():
    gateway, client = build_gateway([response('{"stance":"LONG","confidence":0.72}')])
    result = asyncio.run(gateway.generate_structured(request(), Decision))
    assert result.output.stance == "LONG"
    assert result.output.confidence == 0.72
    assert result.usage.agent_id == "berlin"
    assert result.usage.currency == "EUR"
    assert result.usage.estimated_cost > Decimal("0")
    assert len(client.requests) == 1
    assert client.requests[0].schema_name == "Decision"


def test_invalid_structured_output_is_retried_once_then_succeeds():
    gateway, client = build_gateway([
        response('{"stance":"LONG","confidence":9}'),
        response('{"stance":"NEUTRAL","confidence":0.5}'),
    ])
    result = asyncio.run(gateway.generate_structured(request(), Decision))
    assert result.attempts == 2
    assert result.output.stance == "NEUTRAL"
    assert len(result.usage_records) == 2
    assert [record.attempt for record in result.usage_records] == [1, 2]
    assert len(client.requests) == 2


def test_invalid_structured_output_fails_after_bounded_attempts():
    gateway, client = build_gateway([
        response("not-json"),
        response("still-not-json"),
    ])
    with pytest.raises(StructuredOutputError):
        asyncio.run(gateway.generate_structured(request(), Decision))
    assert len(client.requests) == 2


def test_retryable_provider_error_is_bounded():
    gateway, client = build_gateway([
        RetryableAIProviderError("timeout"),
        RetryableAIProviderError("timeout"),
    ])
    with pytest.raises(RetryableAIProviderError):
        asyncio.run(gateway.generate_structured(request(), Decision))
    assert len(client.requests) == 2


def test_hard_budget_blocks_call_before_provider_is_used():
    gateway, client = build_gateway([response('{"stance":"LONG","confidence":0.7}')], budget="0")
    with pytest.raises(BudgetExceededError):
        asyncio.run(gateway.generate_structured(request(), Decision))
    assert client.requests == []


def test_fallback_route_is_selected_when_primary_does_not_fit_budget():
    expensive = ModelRoute(
        route_id="expensive",
        provider="mock",
        model_id="expensive-model",
        pricing=ModelPricing(
            input_per_million_eur=Decimal("1000"),
            output_per_million_eur=Decimal("1000"),
        ),
        max_output_tokens=100,
        fallback_route_id="cheap",
    )
    cheap = ModelRoute(
        route_id="cheap",
        provider="mock",
        model_id="cheap-model",
        pricing=ModelPricing(
            input_per_million_eur=Decimal("0"),
            output_per_million_eur=Decimal("0"),
        ),
        max_output_tokens=100,
    )
    gateway, client = build_gateway(
        [response('{"stance":"LONG","confidence":0.7}', model="cheap-model")],
        budget="0.001",
        routes=[expensive, cheap],
    )
    result = asyncio.run(gateway.generate_structured(request("expensive"), Decision))
    assert result.route_id == "cheap"
    assert client.requests[0].model_id == "cheap-model"


def test_failed_retry_releases_reservation_for_next_attempt():
    zero_pricing = ModelPricing(input_per_million_eur=Decimal("0"), output_per_million_eur=Decimal("0"))
    route = ModelRoute(
        route_id="primary",
        provider="mock",
        model_id="mock-primary",
        pricing=zero_pricing,
        max_output_tokens=100,
    )
    gateway, _ = build_gateway(
        [RetryableAIProviderError("temporary"), response('{"stance":"LONG","confidence":0.7}')],
        budget="0",
        routes=[route],
    )
    result = asyncio.run(gateway.generate_structured(request(), Decision))
    assert result.attempts == 2
