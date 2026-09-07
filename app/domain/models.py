from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import SystemMode


class DomainModel(BaseModel):
    """Base des modèles métier : stricts, sérialisables et indépendants du stockage."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SystemConfig(DomainModel):
    system_id: str = Field(min_length=1, max_length=100)
    mode: SystemMode
    risk_profile_id: str = Field(min_length=1, max_length=100)
    ai_budget_id: str = Field(min_length=1, max_length=100)
    symbols: tuple[str, ...] = ()

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(symbol.strip().upper() for symbol in value)
        if any(not symbol for symbol in normalized):
            raise ValueError("Un symbole ne peut pas être vide.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Les symboles doivent être uniques.")
        return normalized


class HealthResponse(DomainModel):
    status: str = "ok"
    service: str
    version: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReadinessResponse(DomainModel):
    status: str
    database: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
