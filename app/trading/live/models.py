from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Mapping
from uuid import UUID

from app.trading.paper.models import OrderSide, OrderType


class LiveOrderStatus(StrEnum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ReconciliationFinding(StrEnum):
    CONSISTENT = "CONSISTENT"
    ORDER_UNKNOWN = "ORDER_UNKNOWN"
    UNEXPECTED_FILL = "UNEXPECTED_FILL"
    QUANTITY_DIVERGENCE = "QUANTITY_DIVERGENCE"
    STATE_DIVERGENCE = "STATE_DIVERGENCE"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class LiveOrderIntent:
    order_intent_id: UUID
    risk_decision_id: UUID
    system_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    client_order_id: str
    created_at: datetime
    expires_at: datetime
    limit_price: Decimal | None = None
    mode: str = field(default="LIVE", init=False)

    def __post_init__(self) -> None:
        if not self.system_id.strip():
            raise ValueError("system_id must not be blank")
        if not self.symbol.strip():
            raise ValueError("symbol must not be blank")
        if self.quantity <= 0 or not self.quantity.is_finite():
            raise ValueError("quantity must be finite and > 0")
        if not self.client_order_id.strip():
            raise ValueError("client_order_id must not be blank")
        for name, value in (("created_at", self.created_at), ("expires_at", self.expires_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        if self.order_type is OrderType.LIMIT:
            if self.limit_price is None or self.limit_price <= 0 or not self.limit_price.is_finite():
                raise ValueError("LIMIT intent requires a finite positive limit_price")
        elif self.limit_price is not None:
            raise ValueError("MARKET intent must not carry limit_price")

    def is_stale(self, now: datetime) -> bool:
        if now.tzinfo is None or now.utcoffset() is None:
            return True
        return self.expires_at <= now.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class LiveOrderRecord:
    intent: LiveOrderIntent
    status: LiveOrderStatus
    external_order_id: str | None = None
    exchange_status: str | None = None
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    last_error_code: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class LiveBalance:
    asset: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class LiveFill:
    trade_id: str
    external_order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    fee: Decimal
    filled_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    client_order_id: str
    finding: ReconciliationFinding
    local: LiveOrderRecord | None
    exchange_status: str | None = None
    external_order_id: str | None = None
    exchange_filled_quantity: Decimal = Decimal("0")
    details: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LiveAuditEvent:
    event_type: str
    severity: str
    system_id: str
    client_order_id: str | None
    created_at: datetime
    details: Mapping[str, str] = field(default_factory=dict)
