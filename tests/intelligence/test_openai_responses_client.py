import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from app.intelligence.ai_gateway import (
    IncompleteAIProviderError,
    NonRetryableAIProviderError,
    OpenAIResponsesClient,
    ProviderRequest,
    RetryableAIProviderError,
)


def provider_request():
    return ProviderRequest(
        request_id=uuid4(),
        system_id="balanced_v1",
        agent_id="berlin",
        model_id="configured-model",
        input_text="Analyse BTC",
        instructions="Return only the requested structure.",
        schema_name="Decision",
        json_schema={
            "type": "object",
            "properties": {"stance": {"type": "string"}},
            "required": ["stance"],
            "additionalProperties": False,
        },
        max_output_tokens=200,
        timeout_seconds=5,
        metadata={"prompt_version": "v1"},
    )


def test_openai_client_builds_responses_api_request_and_reads_usage():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "resp_123",
                "model": "configured-model",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"stance":"LONG"}'}],
                    }
                ],
                "usage": {
                    "input_tokens": 120,
                    "input_tokens_details": {"cached_tokens": 20},
                    "output_tokens": 12,
                },
            },
        )

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = OpenAIResponsesClient(api_key="secret-test-key", http_client=http_client)
            return await client.complete(provider_request())

    result = asyncio.run(run())
    assert captured["authorization"] == "Bearer secret-test-key"
    assert captured["body"]["text"]["format"]["type"] == "json_schema"
    assert captured["body"]["text"]["format"]["strict"] is True
    assert captured["body"]["reasoning"] == {"effort": "low"}
    assert captured["body"]["store"] is False
    assert result.output_text == '{"stance":"LONG"}'
    assert result.usage.cached_input_tokens == 20


def test_openai_client_retries_only_retryable_http_statuses():
    async def run(status):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(status, json={"error": {"message": "x"}})
        )
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = OpenAIResponsesClient(api_key="secret", http_client=http_client)
            return await client.complete(provider_request())

    with pytest.raises(RetryableAIProviderError):
        asyncio.run(run(429))
    with pytest.raises(NonRetryableAIProviderError):
        asyncio.run(run(401))


def test_openai_incomplete_response_is_non_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "resp_incomplete",
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "model": "configured-model",
                "output": [],
                "usage": {"input_tokens": 10, "output_tokens": 200},
            },
        )

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = OpenAIResponsesClient(api_key="secret", http_client=http_client)
            return await client.complete(provider_request())

    with pytest.raises(IncompleteAIProviderError, match="max_output_tokens") as caught:
        asyncio.run(run())

    assert caught.value.input_tokens == 10
    assert caught.value.cached_input_tokens == 0
    assert caught.value.output_tokens == 200
    assert caught.value.provider_request_id == "resp_incomplete"
    assert caught.value.model_id == "configured-model"


def test_openai_nonterminal_response_is_not_replayed_automatically():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "resp_queued",
                "status": "queued",
                "model": "configured-model",
                "output": [],
                "usage": {},
            },
        )

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = OpenAIResponsesClient(api_key="secret", http_client=http_client)
            return await client.complete(provider_request())

    with pytest.raises(NonRetryableAIProviderError, match="duplicate spend"):
        asyncio.run(run())


def test_openai_refusal_is_non_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "resp_refusal",
                "model": "configured-model",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "refusal", "refusal": "cannot comply"}],
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = OpenAIResponsesClient(api_key="secret", http_client=http_client)
            return await client.complete(provider_request())

    with pytest.raises(NonRetryableAIProviderError):
        asyncio.run(run())


def test_openai_transport_error_reports_exception_type():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("", request=request)

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = OpenAIResponsesClient(api_key="secret", http_client=http_client)
            return await client.complete(provider_request())

    with pytest.raises(RetryableAIProviderError, match="ReadTimeout"):
        asyncio.run(run())
