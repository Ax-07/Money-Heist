from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


class Candle(BaseModel):
    """Bougie OHLCV normalisée, indépendante d'un exchange."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    open_time: datetime
    close_time: datetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(ge=0)
    is_closed: bool = True

    @field_validator("symbol", "timeframe")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("open_time", "close_time")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @model_validator(mode="after")
    def validate_ohlcv(self) -> Candle:
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be after open_time")

        highest_body_price = max(self.open, self.close, self.low)
        lowest_body_price = min(self.open, self.close, self.high)
        if self.high < highest_body_price:
            raise ValueError("high must be >= open, close and low")
        if self.low > lowest_body_price:
            raise ValueError("low must be <= open, close and high")
        return self


class SnapshotQuality(BaseModel):
    """Qualité des données associée à un snapshot."""

    model_config = ConfigDict(frozen=True)

    is_stale: bool = False
    missing_fields: tuple[str, ...] = ()
    gap_count: int = Field(default=0, ge=0)
    has_duplicates: bool = False
    is_valid: bool = True

    @model_validator(mode="after")
    def enforce_validity(self) -> SnapshotQuality:
        expected_validity = not (
            self.is_stale
            or self.missing_fields
            or self.gap_count > 0
            or self.has_duplicates
        )
        if self.is_valid != expected_validity:
            raise ValueError(
                "is_valid must reflect stale/missing/gap/duplicate quality flags"
            )
        return self


class MarketSnapshot(BaseModel):
    """Snapshot de marché normalisé utilisé comme référence reproductible."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: UUID = Field(default_factory=uuid4)
    schema_version: int = Field(default=1, ge=1)
    symbol: str = Field(min_length=1)
    source: str = Field(min_length=1)
    observed_at: datetime
    received_at: datetime
    last_price: Decimal | None = Field(default=None, gt=0)
    candles: dict[str, tuple[Candle, ...]] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    quality: SnapshotQuality = Field(default_factory=SnapshotQuality)

    @field_validator("symbol", "source")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("observed_at", "received_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @model_validator(mode="after")
    def validate_snapshot_consistency(self) -> MarketSnapshot:
        if self.received_at < self.observed_at:
            raise ValueError("received_at must be >= observed_at")

        for timeframe, series in self.candles.items():
            if not timeframe.strip():
                raise ValueError("candle timeframe keys must not be blank")
            for candle in series:
                if candle.symbol != self.symbol:
                    raise ValueError("all candles must match snapshot symbol")
                if candle.timeframe != timeframe:
                    raise ValueError("candle timeframe must match its snapshot key")
        return self


class HistoricalImportResult(BaseModel):
    """Résultat déterministe d'un import historique."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    source: str
    candles: tuple[Candle, ...]
    quality: SnapshotQuality
