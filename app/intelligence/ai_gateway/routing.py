from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import AIConfigurationError


class PromptCacheMode(StrEnum):
    DISABLED = "disabled"
    OPENAI_EXPLICIT = "openai_explicit"


class PromptCacheCapability(StrEnum):
    NONE = "none"
    OPENAI_EXPLICIT = "openai_explicit"


class PromptCachePolicy(BaseModel):
    """Provider transport policy; disabled by default for backward compatibility."""

    model_config = ConfigDict(frozen=True)

    mode: PromptCacheMode = PromptCacheMode.DISABLED
    ttl: Literal["30m"] = "30m"
    prompt_cache_key: str | None = Field(default=None, min_length=1, max_length=200)


class ModelPricing(BaseModel):
    """Pricing is configuration-driven and expressed in EUR / 1M tokens."""

    model_config = ConfigDict(frozen=True)

    input_per_million_eur: Decimal = Field(ge=0)
    output_per_million_eur: Decimal = Field(ge=0)
    cached_input_per_million_eur: Decimal | None = Field(default=None, ge=0)
    cache_write_input_per_million_eur: Decimal | None = Field(default=None, ge=0)

    def cached_rate(self) -> Decimal:
        return (
            self.cached_input_per_million_eur
            if self.cached_input_per_million_eur is not None
            else self.input_per_million_eur
        )

    def cache_write_rate(self) -> Decimal:
        return (
            self.cache_write_input_per_million_eur
            if self.cache_write_input_per_million_eur is not None
            else self.input_per_million_eur
        )

    def worst_input_rate(self) -> Decimal:
        return max(
            self.input_per_million_eur,
            self.cached_rate(),
            self.cache_write_rate(),
        )


class ModelRoute(BaseModel):
    model_config = ConfigDict(frozen=True)

    route_id: str = Field(min_length=1, max_length=100)
    provider: Literal["openai", "mock"]
    model_id: str = Field(min_length=1, max_length=200)
    pricing: ModelPricing
    max_output_tokens: int = Field(default=1200, ge=1)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"
    fallback_route_id: str | None = Field(default=None, min_length=1, max_length=100)
    prompt_cache_capability: PromptCacheCapability = PromptCacheCapability.NONE
    prompt_cache_policy: PromptCachePolicy = Field(default_factory=PromptCachePolicy)

    @model_validator(mode="after")
    def validate_route(self) -> ModelRoute:
        if self.fallback_route_id == self.route_id:
            raise ValueError("fallback_route_id cannot point to the same route")
        if (
            self.prompt_cache_capability is PromptCacheCapability.OPENAI_EXPLICIT
            and self.provider != "openai"
        ):
            raise ValueError("OpenAI prompt cache capability requires provider='openai'")
        if self.prompt_cache_policy.mode is PromptCacheMode.OPENAI_EXPLICIT:
            if self.provider != "openai":
                raise ValueError("OpenAI explicit prompt caching requires provider='openai'")
            if self.prompt_cache_capability is not PromptCacheCapability.OPENAI_EXPLICIT:
                raise ValueError(
                    "OpenAI explicit prompt caching requires the route to declare "
                    "prompt_cache_capability='openai_explicit'"
                )
        return self


class ModelRouter:
    def __init__(self, routes: list[ModelRoute]):
        if not routes:
            raise AIConfigurationError("At least one AI model route is required")
        self._routes = {route.route_id: route for route in routes}
        if len(self._routes) != len(routes):
            raise AIConfigurationError("Duplicate route_id in AI model routes")
        self._validate_fallbacks()

    def get(self, route_id: str) -> ModelRoute:
        try:
            return self._routes[route_id]
        except KeyError as exc:
            raise AIConfigurationError(f"Unknown AI model route: {route_id}") from exc

    def route_chain(self, route_id: str) -> list[ModelRoute]:
        chain: list[ModelRoute] = []
        seen: set[str] = set()
        current = self.get(route_id)
        while True:
            if current.route_id in seen:
                raise AIConfigurationError("Fallback route cycle detected")
            seen.add(current.route_id)
            chain.append(current)
            if current.fallback_route_id is None:
                return chain
            current = self.get(current.fallback_route_id)

    def _validate_fallbacks(self) -> None:
        for route in self._routes.values():
            if route.fallback_route_id is not None and route.fallback_route_id not in self._routes:
                raise AIConfigurationError(
                    f"Route {route.route_id!r} references unknown fallback "
                    f"{route.fallback_route_id!r}"
                )
            self.route_chain(route.route_id)
