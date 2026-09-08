from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.intelligence.ai_gateway.models import ProviderRequest, ProviderResponse, TokenUsage
from app.services.backtest import (
    BacktestAIClient,
    BacktestAIContext,
    BacktestAIMode,
    BacktestCacheMissError,
    BacktestResponseCache,
)


def sync_test(func):
    def wrapper():
        return asyncio.run(func())

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


class RecordingClient:
    def __init__(self, provider_name: str, response: ProviderResponse):
        self.provider_name = provider_name
        self.response = response
        self.calls = 0

    async def complete(self, request):
        del request
        self.calls += 1
        return self.response


def provider_request(
    *,
    input_text: str = "market=btc",
    request_id: str = "10000000-0000-0000-0000-000000000001",
) -> ProviderRequest:
    return ProviderRequest(
        request_id=UUID(request_id),
        system_id="balanced_v1",
        agent_id="professor",
        model_id="model-v1",
        input_text=input_text,
        instructions="return json",
        schema_name="ProfessorDecision",
        json_schema={"type": "object"},
        max_output_tokens=256,
        timeout_seconds=10.0,
        metadata={
            "prompt_version": "professor-v1",
            "route_id": "route-v1",
        },
    )


def provider_response() -> ProviderResponse:
    return ProviderResponse(
        provider_request_id="provider-1",
        model_id="model-v1",
        output_text='{"direction":"NO_TRADE"}',
        usage=TokenUsage(
            input_tokens=100,
            cached_input_tokens=0,
            output_tokens=20,
        ),
        latency_ms=50,
    )


def context(run_id: str = "run-1", *, cache_scope_id: str | None = None) -> BacktestAIContext:
    return BacktestAIContext(
        run_id=run_id,
        cache_scope_id=cache_scope_id,
        prompt_versions={"professor": "professor-v1"},
        model_versions={"professor": "model-v1"},
    )


@sync_test
async def test_mock_mode_accepts_only_explicit_mock_provider() -> None:
    response = provider_response()
    mock = RecordingClient("mock", response)
    client = BacktestAIClient(
        mode=BacktestAIMode.MOCK,
        context=context(),
        mock_client=mock,
    )

    assert await client.complete(provider_request()) == response
    assert mock.calls == 1

    with pytest.raises(ValueError, match="provider_name='mock'"):
        BacktestAIClient(
            mode=BacktestAIMode.MOCK,
            context=context(),
            mock_client=RecordingClient("openai", response),
        )


@sync_test
async def test_cached_mode_never_calls_upstream_and_fails_closed_on_miss() -> None:
    cache = BacktestResponseCache()
    request = provider_request()
    response = provider_response()
    cache.put(request, response, context=context())

    forbidden = RecordingClient("openai", response)
    client = BacktestAIClient(
        mode=BacktestAIMode.CACHED,
        context=context(),
        cache=cache,
        live_client=forbidden,
    )

    assert await client.complete(request) == response
    assert forbidden.calls == 0

    with pytest.raises(BacktestCacheMissError):
        await client.complete(provider_request(input_text="different input"))
    assert forbidden.calls == 0


@sync_test
async def test_live_eval_delegates_and_can_seed_future_cached_replay() -> None:
    cache = BacktestResponseCache()
    response = provider_response()
    live = RecordingClient("openai", response)
    request = provider_request()

    live_eval = BacktestAIClient(
        mode=BacktestAIMode.LIVE_EVAL,
        context=context(cache_scope_id="experiment-a"),
        cache=cache,
        live_client=live,
    )
    assert await live_eval.complete(request) == response
    assert live.calls == 1
    assert len(cache) == 1

    cached = BacktestAIClient(
        mode=BacktestAIMode.CACHED,
        context=context("another-run", cache_scope_id="experiment-a"),
        cache=cache,
    )
    assert await cached.complete(request) == response
    assert live.calls == 1


def test_cache_key_ignores_volatile_request_id_but_tracks_material_request() -> None:
    cache = BacktestResponseCache()
    stable_context = context(cache_scope_id="experiment-a")
    first = provider_request(request_id="10000000-0000-0000-0000-000000000001")
    same_business = provider_request(request_id="20000000-0000-0000-0000-000000000002")
    changed = provider_request(input_text="changed")

    assert cache.key_for(first, context=stable_context) == cache.key_for(
        same_business,
        context=stable_context,
    )
    assert cache.key_for(first, context=stable_context) != cache.key_for(
        changed,
        context=stable_context,
    )


def test_cache_roundtrips_v2_json() -> None:
    cache = BacktestResponseCache()
    request = provider_request()
    response = provider_response()
    cache.put(request, response, context=context(cache_scope_id="experiment-a"))

    payload = cache.export_json()
    assert "money-heist.backtest-ai-cache.v2" in payload
    restored = BacktestResponseCache.import_json(payload)
    assert restored.require(
        request,
        context=context("new-run", cache_scope_id="experiment-a"),
    ) == response


def test_from_run_cache_scope_ignores_ai_mode_but_keeps_run_id_for_audit() -> None:
    class Config:
        def __init__(self, mode: BacktestAIMode):
            self.ai_mode = mode
            self.prompt_versions = {"professor": "v1"}
            self.model_versions = {"professor": "model-v1"}

        def canonical_payload(self):
            return {
                "system_id": "balanced_v1",
                "ai_mode": self.ai_mode,
                "code_version": "commit-a",
            }

    dataset = SimpleNamespace(
        canonical_payload=lambda: {"dataset_id": "dataset-a", "version": "sha256:a"}
    )
    period_start = datetime(2026, 1, 1, tzinfo=UTC)
    period_end = datetime(2026, 2, 1, tzinfo=UTC)
    live = SimpleNamespace(
        run_id="run-live",
        dataset=dataset,
        period_start=period_start,
        period_end=period_end,
        config=Config(BacktestAIMode.LIVE_EVAL),
    )
    cached = SimpleNamespace(
        run_id="run-cached",
        dataset=dataset,
        period_start=period_start,
        period_end=period_end,
        config=Config(BacktestAIMode.CACHED),
    )

    live_context = BacktestAIContext.from_run(live)
    cached_context = BacktestAIContext.from_run(cached)
    assert live_context.run_id != cached_context.run_id
    assert live_context.cache_scope_id == cached_context.cache_scope_id
