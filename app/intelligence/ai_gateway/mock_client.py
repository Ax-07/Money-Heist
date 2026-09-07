from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from .models import ProviderRequest, ProviderResponse, TokenUsage


class MockAIClient:
    provider_name = "mock"

    def __init__(self, responses: Iterable[ProviderResponse | Exception] | None = None):
        self._responses = deque(responses or [])
        self.requests: list[ProviderRequest] = []

    def push(self, response: ProviderResponse | Exception) -> None:
        self._responses.append(response)

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if not self._responses:
            return ProviderResponse(
                provider_request_id=f"mock-{len(self.requests)}",
                model_id=request.model_id,
                output_text="{}",
                usage=TokenUsage(),
                latency_ms=0,
            )
        item = self._responses.popleft()
        if isinstance(item, Exception):
            raise item
        return item
