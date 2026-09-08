from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.intelligence.ai_gateway.models import ProviderRequest, ProviderResponse

from .ids import canonical_json, stable_digest

CACHE_SCHEMA_VERSION = "money-heist.backtest-ai-cache.v1"


def _freeze(values: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(
        dict(
            sorted(
                (str(key).strip(), str(value).strip())
                for key, value in values.items()
            )
        )
    )


@dataclass(frozen=True, slots=True)
class BacktestAIContext:
    """Stable experiment identity used to scope deterministic AI cache entries."""

    run_id: str
    prompt_versions: Mapping[str, str]
    model_versions: Mapping[str, str]
    schema_version: str = CACHE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.schema_version.strip():
            raise ValueError("schema_version must not be empty")
        object.__setattr__(self, "prompt_versions", _freeze(self.prompt_versions))
        object.__setattr__(self, "model_versions", _freeze(self.model_versions))

    @classmethod
    def from_run(cls, run: Any) -> BacktestAIContext:
        return cls(
            run_id=str(run.run_id),
            prompt_versions=run.config.prompt_versions,
            model_versions=run.config.model_versions,
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "prompt_versions": self.prompt_versions,
            "model_versions": self.model_versions,
            "schema_version": self.schema_version,
        }


class BacktestCacheMissError(LookupError):
    """Raised when CACHED mode cannot resolve a deterministic provider response."""


class BacktestResponseCache:
    """In-memory deterministic provider-response cache with stable JSON import/export."""

    def __init__(self) -> None:
        self._responses: dict[str, ProviderResponse] = {}

    def key_for(self, request: ProviderRequest, *, context: BacktestAIContext) -> str:
        payload = {
            "schema": CACHE_SCHEMA_VERSION,
            "context": context.canonical_payload(),
            "request": request.model_dump(mode="json"),
        }
        return stable_digest(payload)

    def put(
        self,
        request: ProviderRequest,
        response: ProviderResponse,
        *,
        context: BacktestAIContext,
    ) -> str:
        key = self.key_for(request, context=context)
        self._responses[key] = response
        return key

    def get(
        self,
        request: ProviderRequest,
        *,
        context: BacktestAIContext,
    ) -> ProviderResponse | None:
        return self._responses.get(self.key_for(request, context=context))

    def require(
        self,
        request: ProviderRequest,
        *,
        context: BacktestAIContext,
    ) -> ProviderResponse:
        response = self.get(request, context=context)
        if response is None:
            raise BacktestCacheMissError(
                "deterministic AI cache miss for current run/config/request"
            )
        return response

    def export_json(self) -> str:
        entries = [
            {
                "key": key,
                "response": response.model_dump(mode="json"),
            }
            for key, response in sorted(self._responses.items())
        ]
        return canonical_json(
            {
                "schema": CACHE_SCHEMA_VERSION,
                "entries": entries,
            }
        )

    @classmethod
    def import_json(cls, payload: str) -> BacktestResponseCache:
        raw = json.loads(payload)
        if raw.get("schema") != CACHE_SCHEMA_VERSION:
            raise ValueError("unsupported backtest AI cache schema")
        cache = cls()
        for entry in raw.get("entries", []):
            key = str(entry["key"])
            if len(key) != 64:
                raise ValueError("invalid backtest AI cache key")
            cache._responses[key] = ProviderResponse.model_validate(entry["response"])
        return cache

    def __len__(self) -> int:
        return len(self._responses)


__all__ = [
    "BacktestAIContext",
    "BacktestCacheMissError",
    "BacktestResponseCache",
    "CACHE_SCHEMA_VERSION",
]
