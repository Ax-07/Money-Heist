from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

StructuredT = TypeVar("StructuredT", bound=BaseModel)


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @field_validator("cached_input_tokens")
    @classmethod
    def cached_tokens_cannot_exceed_input(cls, value: int, info):
        input_tokens = info.data.get("input_tokens")
        if input_tokens is not None and value > input_tokens:
            raise ValueError("cached_input_tokens cannot exceed input_tokens")
        return value


class AIUsageRecord(BaseModel):
    """Auditable usage record aligned with 08_API_ET_MODELES_DE_DONNEES.md."""

    model_config = ConfigDict(frozen=True)

    usage_id: UUID = Field(default_factory=uuid4)
    request_id: UUID
    system_id: str
    agent_id: str
    route_id: str
    model_id: str
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost: Decimal = Field(ge=0)
    currency: Literal["EUR"] = "EUR"
    latency_ms: int = Field(ge=0)
    attempt: int = Field(ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AIGatewayRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: UUID = Field(default_factory=uuid4)
    system_id: str = Field(min_length=1, max_length=100)
    agent_id: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=100)
    model_route: str = Field(min_length=1, max_length=100)
    input_text: str = Field(min_length=1)
    instructions: str | None = None
    max_output_tokens: int | None = Field(default=None, ge=1)
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
    schema_name: str
    json_schema: dict[str, Any]
    max_output_tokens: int = Field(ge=1)
    timeout_seconds: float = Field(gt=0)
    reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"
    metadata: dict[str, str] = Field(default_factory=dict)


class ProviderResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_request_id: str | None = None
    model_id: str
    output_text: str
    usage: TokenUsage
    latency_ms: int = Field(ge=0)


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
