from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .prompt_cache import PROMPT_TRANSPORT_VERSION

StructuredT = TypeVar("StructuredT", bound=BaseModel)


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_input_partition(self) -> TokenUsage:
        if self.cached_input_tokens + self.cache_write_tokens > self.input_tokens:
            raise ValueError(
                "cached_input_tokens + cache_write_tokens cannot exceed input_tokens"
            )
        return self

    @property
    def normal_input_tokens(self) -> int:
        return self.input_tokens - self.cached_input_tokens - self.cache_write_tokens

    @property
    def cache_read_ratio(self) -> Decimal:
        if self.input_tokens == 0:
            return Decimal("0")
        return Decimal(self.cached_input_tokens) / Decimal(self.input_tokens)


class AIUsageRecord(BaseModel):
    """Auditable usage record aligned with the AI Gateway provider accounting."""

    model_config = ConfigDict(frozen=True)

    usage_id: UUID = Field(default_factory=uuid4)
    request_id: UUID
    system_id: str
    agent_id: str
    route_id: str
    model_id: str
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost: Decimal = Field(ge=0)
    estimated_cost_without_cache: Decimal | None = Field(default=None, ge=0)
    currency: Literal["EUR"] = "EUR"
    latency_ms: int = Field(ge=0)
    attempt: int = Field(ge=1)
    prompt_cache_mode: Literal["disabled", "openai_explicit"] = "disabled"
    prompt_render_version: str = PROMPT_TRANSPORT_VERSION
    stable_prefix_sha256: str | None = None
    prompt_cache_diagnostics: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_input_partition(self) -> AIUsageRecord:
        if self.cached_input_tokens + self.cache_write_tokens > self.input_tokens:
            raise ValueError(
                "cached_input_tokens + cache_write_tokens cannot exceed input_tokens"
            )
        return self

    @property
    def normal_input_tokens(self) -> int:
        return self.input_tokens - self.cached_input_tokens - self.cache_write_tokens


class AIGatewayRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: UUID = Field(default_factory=uuid4)
    system_id: str = Field(min_length=1, max_length=100)
    agent_id: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=100)
    prompt_render_version: str = Field(
        default=PROMPT_TRANSPORT_VERSION,
        min_length=1,
        max_length=100,
    )
    model_route: str = Field(min_length=1, max_length=100)
    input_text: str = Field(min_length=1)
    instructions: str | None = None
    max_output_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0, le=300)
    opportunity_id: UUID | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class ProviderRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: UUID
    system_id: str
    agent_id: str
    model_id: str
    input_text: str
    instructions: str | None = None
    cacheable_developer_prefix: str | None = None
    schema_name: str
    json_schema: dict[str, Any]
    schema_sha256: str = ""
    max_output_tokens: int = Field(ge=1)
    timeout_seconds: float = Field(gt=0)
    reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"
    prompt_cache_mode: Literal["disabled", "openai_explicit"] = "disabled"
    prompt_cache_ttl: Literal["30m"] = "30m"
    prompt_cache_key: str | None = Field(default=None, min_length=1, max_length=200)
    prompt_render_version: str = PROMPT_TRANSPORT_VERSION
    stable_prefix_sha256: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_cache_transport(self) -> ProviderRequest:
        if self.prompt_cache_mode == "openai_explicit":
            if not self.cacheable_developer_prefix:
                raise ValueError(
                    "openai_explicit prompt caching requires cacheable_developer_prefix"
                )
            if not self.stable_prefix_sha256:
                raise ValueError(
                    "openai_explicit prompt caching requires stable_prefix_sha256"
                )
        return self


class ProviderResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_request_id: str | None = None
    model_id: str
    output_text: str
    usage: TokenUsage
    latency_ms: int = Field(ge=0)
    prompt_cache_diagnostics: dict[str, Any] | None = None


class AIGatewayResult(BaseModel, Generic[StructuredT]):
    model_config = ConfigDict(frozen=True)

    request_id: UUID
    route_id: str
    model_id: str
    output: StructuredT
    usage: AIUsageRecord
    usage_records: tuple[AIUsageRecord, ...] = ()
    attempts: int = Field(ge=1)
    provider_request_id: str | None = None
