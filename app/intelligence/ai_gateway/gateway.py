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
    RetryableAIProviderError,
    StructuredOutputError,
)
from .models import AIGatewayRequest, AIGatewayResult, AIUsageRecord, ProviderRequest
from .pricing import calculate_cost_eur, estimate_max_request_cost_eur
from .routing import ModelRoute, ModelRouter
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
        json_schema = output_model.model_json_schema()
        last_error: Exception | None = None

        for route in self._router.route_chain(request.model_route):
            max_output_tokens = request.max_output_tokens or route.max_output_tokens
            reservation_cost = estimate_max_request_cost_eur(
                input_text=request.input_text,
                instructions=request.instructions,
                max_output_tokens=max_output_tokens,
                pricing=route.pricing,
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
                    max_output_tokens=max_output_tokens,
                    reservation_cost=reservation_cost,
                )
            except BudgetExceededError as exc:
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
        max_output_tokens: int,
        reservation_cost,
    ) -> AIGatewayResult[StructuredT]:
        client = self._clients.get(route.provider)
        if client is None:
            raise AIConfigurationError(f"No AI client registered for provider {route.provider!r}")

        request_usage_records: list[AIUsageRecord] = []
        for attempt in range(1, self._max_attempts + 1):
            reservation_id = self._budget.reserve(reservation_cost)
            provider_request = ProviderRequest(
                request_id=request.request_id,
                system_id=request.system_id,
                agent_id=request.agent_id,
                model_id=route.model_id,
                input_text=request.input_text,
                instructions=request.instructions,
                schema_name=schema_name,
                json_schema=json_schema,
                max_output_tokens=max_output_tokens,
                timeout_seconds=route.timeout_seconds,
                metadata={
                    **request.metadata,
                    "system_id": request.system_id,
                    "agent_id": request.agent_id,
                    "prompt_version": request.prompt_version,
                    "route_id": route.route_id,
                },
            )

            try:
                provider_response = await client.complete(provider_request)
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
            self._budget.settle(reservation_id, actual_cost)
            usage_record = AIUsageRecord(
                request_id=request.request_id,
                system_id=request.system_id,
                agent_id=request.agent_id,
                route_id=route.route_id,
                model_id=provider_response.model_id,
                input_tokens=provider_response.usage.input_tokens,
                cached_input_tokens=provider_response.usage.cached_input_tokens,
                output_tokens=provider_response.usage.output_tokens,
                estimated_cost=actual_cost,
                latency_ms=provider_response.latency_ms,
                attempt=attempt,
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

    async def _backoff(self, attempt: int) -> None:
        if self._retry_backoff_seconds == 0:
            return
        await asyncio.sleep(self._retry_backoff_seconds * attempt)

    @staticmethod
    def _schema_name(model: type[BaseModel]) -> str:
        raw = model.__name__
        normalized = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in raw)
        return normalized[:64] or "structured_output"
