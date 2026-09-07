from __future__ import annotations

from typing import Protocol

from .models import ProviderRequest, ProviderResponse


class AIClient(Protocol):
    provider_name: str

    async def complete(self, request: ProviderRequest) -> ProviderResponse: ...
