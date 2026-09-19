from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .budget import AIBudgetLedger
from .client import AIClient
from .errors import (
    AIConfigurationError,
    BudgetExceededError,
    IncompleteAIProviderError,
    RetryableAIProviderError,
    StructuredOutputError,
)
from .models import (
    AIGatewayRequest,
    AIGatewayResult,
    AIUsageRecord,
    ProviderRequest,
    TokenUsage,
)
from .pricing import (
    calculate_cost_eur,
    calculate_uncached_cost_eur,
    estimate_max_request_cost_eur,
)
from .prompt_cache import (
    apply_agent_dialogue_language_contract,
    build_cacheable_developer_prefix,
    schema_fingerprint,
    stable_prefix_fingerprint,
)
from .routing import ModelRoute, ModelRouter, PromptCacheMode
from .strict_schema import build_strict_json_schema
from .usage import AIUsageRecorder, InMemoryAIUsageRecorder

StructuredT = TypeVar("StructuredT", bound=BaseModel)


class AIGateway(Generic[StructuredT]):
    def __init__(
        self,
        *,
        router: ModelRouter,
        clients: Mapping[str, AIClient],
        budget: AIBudgetLedger,
        max_attempts: int = 2,
        retry_backoff_seconds: float = 0.05,
        usage_recorder: AIUsageRecorder | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be >= 0")
        self._router = router
        self._clients = dict(clients)
        self._budget = budget
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        self._usage_recorder = usage_recorder or InMemoryAIUsageRecorder()

    async def generate_structured(
        self,
        request: AIGatewayRequest,
        output_model: type[StructuredT],
    ) -> AIGatewayResult[StructuredT]:
        schema_name = self._schema_name(output_model)
        json_schema = build_strict_json_schema(output_model)
        schema_sha256 = schema_fingerprint(json_schema)
        rendered_instructions = apply_agent_dialogue_language_contract(request.instructions)
        request = request.model_copy(update={"instructions": rendered_instructions})
        last_error: Exception | None = None

        for route in self._router.route_chain(request.model_route):
            max_output_tokens = request.max_output_tokens or route.max_output_tokens
            cacheable_prefix, prefix_sha256 = self._cache_transport(
                route=route,
                request=request,
                schema_name=schema_name,
                schema_sha256=schema_sha256,
            )
            reservation_cost = estimate_max_request_cost_eur(
                input_text=request.input_text,
                instructions=request.instructions,
                max_output_tokens=max_output_tokens,
                pricing=route.pricing,
                json_schema=json_schema,
                cacheable_developer_prefix=cacheable_prefix,
            )
            if not self._budget.can_reserve(reservation_cost):
                last_error = BudgetExceededError(
                    f"Route {route.route_id!r} cannot fit inside remaining AI budget"
                )
                continue

            try:
                return await self._run_route(
                    route=route,
                    request=request,
                    output_model=output_model,
                    schema_name=schema_name,
                    json_schema=json_schema,
                    schema_sha256=schema_sha256,
                    cacheable_prefix=cacheable_prefix,
                    prefix_sha256=prefix_sha256,
                    max_output_tokens=max_output_tokens,
                    reservation_cost=reservation_cost,
                )
            except BudgetExceededError as exc:
                snapshot = self._budget.snapshot()
                if snapshot.spent_eur > snapshot.hard_limit_eur:
                    raise
                last_error = exc
                continue

        if last_error is not None:
            raise last_error
        raise BudgetExceededError("No AI model route could be selected within budget")

    async def _run_route(
        self,
        *,
        route: ModelRoute,
        request: AIGatewayRequest,
        output_model: type[StructuredT],
        schema_name: str,
        json_schema: dict,
        schema_sha256: str,
        cacheable_prefix: str | None,
        prefix_sha256: str | None,
        max_output_tokens: int,
        reservation_cost,
    ) -> AIGatewayResult[StructuredT]:
        client = self._clients.get(route.provider)
        if client is None:
            raise AIConfigurationError(f"No AI client registered for provider {route.provider!r}")

        request_usage_records: list[AIUsageRecord] = []
        cache_mode = route.prompt_cache_policy.mode.value
        for attempt in range(1, self._max_attempts + 1):
            reservation_id = self._budget.reserve(reservation_cost)
            provider_request = ProviderRequest(
                request_id=request.request_id,
                system_id=request.system_id,
                agent_id=request.agent_id,
                model_id=route.model_id,
                input_text=request.input_text,
                instructions=request.instructions,
                cacheable_developer_prefix=cacheable_prefix,
                schema_name=schema_name,
                json_schema=json_schema,
                schema_sha256=schema_sha256,
                max_output_tokens=max_output_tokens,
                timeout_seconds=request.timeout_seconds or route.timeout_seconds,
                reasoning_effort=route.reasoning_effort,
                prompt_cache_mode=cache_mode,
                prompt_cache_ttl=route.prompt_cache_policy.ttl,
                prompt_cache_key=route.prompt_cache_policy.prompt_cache_key,
                prompt_render_version=request.prompt_render_version,
                stable_prefix_sha256=prefix_sha256,
                metadata={
                    **request.metadata,
                    "system_id": request.system_id,
                    "agent_id": request.agent_id,
                    "prompt_version": request.prompt_version,
                    "prompt_render_version": request.prompt_render_version,
                    "route_id": route.route_id,
                    "prompt_cache_mode": cache_mode,
                    "schema_sha256": schema_sha256,
                    **(
                        {"stable_prefix_sha256": prefix_sha256}
                        if prefix_sha256 is not None
                        else {}
                    ),
                },
            )

            try:
                provider_response = await client.complete(provider_request)
            except IncompleteAIProviderError as exc:
                incomplete_usage = TokenUsage(
                    input_tokens=exc.input_tokens,
                    cached_input_tokens=exc.cached_input_tokens,
                    cache_write_tokens=exc.cache_write_tokens,
                    output_tokens=exc.output_tokens,
                )
                actual_cost = calculate_cost_eur(incomplete_usage, route.pricing)
                uncached_cost = calculate_uncached_cost_eur(incomplete_usage, route.pricing)

                settle_error: BudgetExceededError | None = None
                try:
                    self._budget.settle(reservation_id, actual_cost)
                except BudgetExceededError as budget_exc:
                    settle_error = budget_exc

                usage_record = self._usage_record(
                    request=request,
                    route=route,
                    model_id=exc.model_id,
                    usage=incomplete_usage,
                    actual_cost=actual_cost,
                    uncached_cost=uncached_cost,
                    latency_ms=exc.latency_ms,
                    attempt=attempt,
                    cache_mode=cache_mode,
                    prefix_sha256=prefix_sha256,
                    prompt_cache_diagnostics=exc.prompt_cache_diagnostics,
                )
                await self._usage_recorder.record(usage_record)

                if settle_error is not None:
                    raise settle_error from exc
                raise
            except RetryableAIProviderError:
                self._budget.release(reservation_id)
                if attempt >= self._max_attempts:
                    raise
                await self._backoff(attempt)
                continue
            except Exception:
                self._budget.release(reservation_id)
                raise

            actual_cost = calculate_cost_eur(provider_response.usage, route.pricing)
            uncached_cost = calculate_uncached_cost_eur(provider_response.usage, route.pricing)
            self._budget.settle(reservation_id, actual_cost)
            usage_record = self._usage_record(
                request=request,
                route=route,
                model_id=provider_response.model_id,
                usage=provider_response.usage,
                actual_cost=actual_cost,
                uncached_cost=uncached_cost,
                latency_ms=provider_response.latency_ms,
                attempt=attempt,
                cache_mode=cache_mode,
                prefix_sha256=prefix_sha256,
                prompt_cache_diagnostics=provider_response.prompt_cache_diagnostics,
            )
            await self._usage_recorder.record(usage_record)
            request_usage_records.append(usage_record)

            try:
                parsed = output_model.model_validate_json(provider_response.output_text)
            except ValidationError as exc:
                if attempt >= self._max_attempts:
                    raise StructuredOutputError(
                        f"Structured output validation failed after {attempt} attempt(s)"
                    ) from exc
                await self._backoff(attempt)
                continue

            return AIGatewayResult[StructuredT](
                request_id=request.request_id,
                route_id=route.route_id,
                model_id=provider_response.model_id,
                output=parsed,
                usage=usage_record,
                usage_records=tuple(request_usage_records),
                attempts=attempt,
                provider_request_id=provider_response.provider_request_id,
            )

        raise RuntimeError("Unreachable AI gateway state")

    @staticmethod
    def _usage_record(
        *,
        request: AIGatewayRequest,
        route: ModelRoute,
        model_id: str,
        usage: TokenUsage,
        actual_cost,
        uncached_cost,
        latency_ms: int,
        attempt: int,
        cache_mode: str,
        prefix_sha256: str | None,
        prompt_cache_diagnostics: dict | None,
    ) -> AIUsageRecord:
        return AIUsageRecord(
            request_id=request.request_id,
            system_id=request.system_id,
            agent_id=request.agent_id,
            route_id=route.route_id,
            model_id=model_id,
            input_tokens=usage.input_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost=actual_cost,
            estimated_cost_without_cache=uncached_cost,
            latency_ms=latency_ms,
            attempt=attempt,
            prompt_cache_mode=cache_mode,
            prompt_render_version=request.prompt_render_version,
            stable_prefix_sha256=prefix_sha256,
            prompt_cache_diagnostics=prompt_cache_diagnostics,
        )

    @staticmethod
    def _cache_transport(
        *,
        route: ModelRoute,
        request: AIGatewayRequest,
        schema_name: str,
        schema_sha256: str,
    ) -> tuple[str | None, str | None]:
        if route.prompt_cache_policy.mode is not PromptCacheMode.OPENAI_EXPLICIT:
            return None, None
        prefix = build_cacheable_developer_prefix(
            agent_id=request.agent_id,
            prompt_version=request.prompt_version,
            prompt_render_version=request.prompt_render_version,
            instructions=request.instructions,
            schema_name=schema_name,
            schema_sha256=schema_sha256,
        )
        return prefix, stable_prefix_fingerprint(prefix)

    async def _backoff(self, attempt: int) -> None:
        if self._retry_backoff_seconds == 0:
            return
        await asyncio.sleep(self._retry_backoff_seconds * attempt)

    @staticmethod
    def _schema_name(model: type[BaseModel]) -> str:
        raw = model.__name__
        normalized = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in raw)
        return normalized[:64] or "structured_output"
