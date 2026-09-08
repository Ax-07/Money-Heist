from __future__ import annotations

from typing import Any

from app.intelligence.ai_gateway.client import AIClient
from app.intelligence.ai_gateway.models import ProviderRequest, ProviderResponse

from .cache import BacktestAIContext, BacktestResponseCache
from .models import BacktestAIMode


class BacktestAIClient:
    """Provider client boundary enforcing the selected Batch 16 AI mode.

    MOCK delegates only to an explicitly injected mock provider.
    CACHED never calls an upstream provider and fails closed on cache miss.
    LIVE_EVAL delegates to a real provider client but remains only an AI path;
    trading execution is still owned by the PAPER pipeline.
    """

    provider_name = "backtest"

    def __init__(
        self,
        *,
        mode: BacktestAIMode,
        context: BacktestAIContext,
        cache: BacktestResponseCache | None = None,
        mock_client: AIClient | None = None,
        live_client: AIClient | None = None,
    ) -> None:
        self.mode = mode
        self.context = context
        self.cache = cache
        self.mock_client = mock_client
        self.live_client = live_client

        if mode is BacktestAIMode.MOCK:
            if mock_client is None:
                raise ValueError("MOCK mode requires mock_client")
            if getattr(mock_client, "provider_name", None) != "mock":
                raise ValueError("MOCK mode accepts only provider_name='mock'")
        elif mode is BacktestAIMode.CACHED:
            if cache is None:
                raise ValueError("CACHED mode requires BacktestResponseCache")
        elif mode is BacktestAIMode.LIVE_EVAL:
            if live_client is None:
                raise ValueError("LIVE_EVAL mode requires live_client")
        else:
            raise ValueError(f"unsupported backtest AI mode: {mode}")

    @classmethod
    def from_run(
        cls,
        run: Any,
        *,
        cache: BacktestResponseCache | None = None,
        mock_client: AIClient | None = None,
        live_client: AIClient | None = None,
    ) -> BacktestAIClient:
        return cls(
            mode=run.config.ai_mode,
            context=BacktestAIContext.from_run(run),
            cache=cache,
            mock_client=mock_client,
            live_client=live_client,
        )

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        if self.mode is BacktestAIMode.MOCK:
            assert self.mock_client is not None
            return await self.mock_client.complete(request)

        if self.mode is BacktestAIMode.CACHED:
            assert self.cache is not None
            return self.cache.require(request, context=self.context)

        assert self.mode is BacktestAIMode.LIVE_EVAL
        assert self.live_client is not None
        response = await self.live_client.complete(request)
        if self.cache is not None:
            self.cache.put(request, response, context=self.context)
        return response


__all__ = ["BacktestAIClient"]
