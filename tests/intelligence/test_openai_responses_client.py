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


def provider_request(**overrides):
    values = dict(
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
        schema_sha256="a" * 64,
        max_output_tokens=200,
        timeout_seconds=5,
        metadata={"prompt_version": "v1"},
    )
    values.update(overrides)
    return ProviderRequest(**values)


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
                    "input_tokens_details": {
                        "cached_tokens": 20,
                        "cache_write_tokens": 30,
                    },
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
    assert captured["body"]["input"] == "Analyse BTC"
    assert captured["body"]["instructions"] == "Return only the requested structure."
    assert "prompt_cache_options" not in captured["body"]
    assert result.output_text == '{"stance":"LONG"}'
    assert result.usage.cached_input_tokens == 20
    assert result.usage.cache_write_tokens == 30
    assert result.usage.normal_input_tokens == 70


def test_openai_explicit_prompt_cache_places_dynamic_content_after_breakpoint():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "resp_cache",
                "model": "configured-model",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"stance":"LONG"}'}],
                    }
                ],
                "usage": {
                    "input_tokens": 100,
                    "input_tokens_details": {
                        "cached_tokens": 80,
                        "cache_write_tokens": 0,
                    },
                    "output_tokens": 10,
                },
                "prompt_cache_diagnostics": {"type": "hit"},
            },
        )

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = OpenAIResponsesClient(api_key="secret", http_client=http_client)
            return await client.complete(
                provider_request(
                    input_text='{"snapshot_id":"dynamic-2"}',
                    cacheable_developer_prefix="STABLE PREFIX v1",
                    prompt_cache_mode="openai_explicit",
                    prompt_cache_ttl="30m",
                    prompt_cache_key=None,
                    stable_prefix_sha256="b" * 64,
                )
            )

    result = asyncio.run(run())
    body = captured["body"]
    assert body["store"] is False
    assert body["prompt_cache_options"] == {"mode": "explicit", "ttl": "30m"}
    assert "prompt_cache_key" not in body
    assert "instructions" not in body
    assert body["input"][0]["role"] == "developer"
    stable_block = body["input"][0]["content"][0]
    assert stable_block == {
        "type": "input_text",
        "text": "STABLE PREFIX v1",
        "prompt_cache_breakpoint": {"mode": "explicit"},
    }
    assert body["input"][1]["role"] == "user"
    assert body["input"][1]["content"][0]["text"] == '{"snapshot_id":"dynamic-2"}'
    assert result.usage.cached_input_tokens == 80
    assert result.prompt_cache_diagnostics == {"type": "hit"}


def test_openai_explicit_prompt_cache_key_is_optional_but_forwarded_when_configured():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "resp_cache_key",
                "model": "configured-model",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"stance":"LONG"}'}],
                    }
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = OpenAIResponsesClient(api_key="secret", http_client=http_client)
            return await client.complete(
                provider_request(
                    cacheable_developer_prefix="stable",
                    prompt_cache_mode="openai_explicit",
                    prompt_cache_key="money-heist-shared-v1",
                    stable_prefix_sha256="b" * 64,
                )
            )

    asyncio.run(run())
    assert captured["body"]["prompt_cache_key"] == "money-heist-shared-v1"


def test_openai_rejects_impossible_usage_partition_fail_closed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "resp_bad_usage",
                "model": "configured-model",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"stance":"LONG"}'}],
                    }
                ],
                "usage": {
                    "input_tokens": 10,
                    "input_tokens_details": {
                        "cached_tokens": 8,
                        "cache_write_tokens": 5,
                    },
                    "output_tokens": 1,
                },
            },
        )

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = OpenAIResponsesClient(api_key="secret", http_client=http_client)
            return await client.complete(provider_request())

    with pytest.raises(NonRetryableAIProviderError, match="impossible"):
        asyncio.run(run())


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


def test_openai_incomplete_response_is_non_retryable_and_preserves_cache_write_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "resp_incomplete",
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "model": "configured-model",
                "output": [],
                "usage": {
                    "input_tokens": 10,
                    "input_tokens_details": {"cache_write_tokens": 6},
                    "output_tokens": 200,
                },
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
    assert caught.value.cache_write_tokens == 6
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
