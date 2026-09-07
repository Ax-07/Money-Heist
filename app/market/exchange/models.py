from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.trading.risk.models import MarketConstraints


class ExchangeAdapterError(RuntimeError):
    """Base error for exchange market-data adapters."""


class ExchangeNetworkError(ExchangeAdapterError):
    """Network or transport failure after bounded retries."""


class ExchangeHttpError(ExchangeAdapterError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class ExchangeRateLimitError(ExchangeHttpError):
    """Rate limiting observed after bounded retries."""


class ExchangePayloadError(ExchangeAdapterError):
    """Malformed, incomplete or semantically invalid exchange payload."""


class UnsafeMarketDataError(ExchangeAdapterError):
    """Market data is unsuitable for feeding a new PAPER/SHADOW decision."""


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class PublicHttpResponse:
    status_code: int
    payload: Any
    headers: Mapping[str, str]
    received_at: datetime

    def __post_init__(self) -> None:
        if self.status_code < 100 or self.status_code > 599:
            raise ValueError("status_code must be a valid HTTP status")
        object.__setattr__(self, "received_at", as_utc(self.received_at))


class CurrentPrice(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    price: Decimal = Field(gt=0)
    observed_at: datetime
    received_at: datetime
    source: str = Field(min_length=1)

    @field_validator("observed_at", "received_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return as_utc(value)

    @model_validator(mode="after")
    def validate_clock_order(self) -> "CurrentPrice":
        if self.received_at < self.observed_at:
            raise ValueError("received_at must be >= observed_at")
        return self


class SymbolMetadata(BaseModel):
    """Exchange-independent symbol metadata derived from one exchange payload."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    exchange_symbol: str = Field(min_length=1)
    source: str = Field(min_length=1)
    base_asset: str = Field(min_length=1)
    quote_asset: str = Field(min_length=1)
    status: str = Field(min_length=1)
    tick_size: Decimal = Field(gt=0)
    qty_step: Decimal = Field(gt=0)
    min_qty: Decimal = Field(gt=0)
    min_notional: Decimal = Field(gt=0)
    price_precision: int = Field(ge=0)
    quantity_precision: int = Field(ge=0)
    received_at: datetime

    @field_validator("received_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return as_utc(value)

    def to_market_constraints(self) -> MarketConstraints:
        """Project only fields already represented by Batch 05 without changing Risk Engine."""

        return MarketConstraints(
            qty_step=self.qty_step,
            min_qty=self.min_qty,
            min_notional=self.min_notional,
            max_qty=None,
            max_leverage=None,
        )
