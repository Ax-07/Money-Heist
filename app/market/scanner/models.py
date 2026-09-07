from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScannerTrigger(StrEnum):
    RANGE_BREAK = "range_break"
    VOLUME_EXPANSION = "volume_expansion"
    VOLATILITY_EXPANSION = "volatility_expansion"
    TREND_STRENGTH = "trend_strength"
    MOMENTUM_EXTREME = "momentum_extreme"
    REGIME_CHANGE = "regime_change"


class CandidateOpportunity(BaseModel):
    """Scanner output contract.

    It intentionally contains no side/direction field. The scanner detects market
    events worth inspecting; it does not decide whether to go LONG or SHORT.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    scanner_version: str
    opportunity_id: str
    snapshot_id: str
    system_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    priority_score: int = Field(ge=0, le=100)
    triggers: tuple[ScannerTrigger, ...]
    created_at: datetime
    expires_at: datetime

    @field_validator("created_at", "expires_at")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class ScanResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: int = Field(ge=0, le=100)
    triggers: tuple[ScannerTrigger, ...]
    opportunity: CandidateOpportunity | None = None
