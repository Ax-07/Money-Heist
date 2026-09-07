from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum


ZERO = Decimal("0")


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class Liquidity(str, Enum):
    MAKER = "MAKER"
    TAKER = "TAKER"


@dataclass(frozen=True, slots=True)
class PaperOrderRequest:
    system_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    client_order_id: str
    limit_price: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Fill:
    fill_id: str
    broker_order_id: str
    price: Decimal
    quantity: Decimal
    fee: Decimal
    fee_rate_bps: Decimal
    liquidity: Liquidity
    filled_at: datetime

    @property
    def notional(self) -> Decimal:
        return self.price * self.quantity


@dataclass(frozen=True, slots=True)
class BrokerOrder:
    broker_order_id: str
    client_order_id: str
    system_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    requested_quantity: Decimal
    filled_quantity: Decimal
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
    limit_price: Decimal | None = None
    average_fill_price: Decimal | None = None
    reject_reason: str | None = None
    trigger: str | None = None

    def with_update(self, **changes: object) -> "BrokerOrder":
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class Position:
    system_id: str
    symbol: str
    signed_quantity: Decimal
    average_entry: Decimal
    realized_pnl: Decimal = ZERO

    @property
    def is_open(self) -> bool:
        return self.signed_quantity != ZERO

    @property
    def side(self) -> PositionSide | None:
        if self.signed_quantity > ZERO:
            return PositionSide.LONG
        if self.signed_quantity < ZERO:
            return PositionSide.SHORT
        return None

    @property
    def quantity(self) -> Decimal:
        return abs(self.signed_quantity)

    def unrealized_pnl(self, mark_price: Decimal) -> Decimal:
        if self.signed_quantity > ZERO:
            return (mark_price - self.average_entry) * self.signed_quantity
        if self.signed_quantity < ZERO:
            return (self.average_entry - mark_price) * abs(self.signed_quantity)
        return ZERO


@dataclass(frozen=True, slots=True)
class StopLoss:
    stop_id: str
    system_id: str
    symbol: str
    stop_price: Decimal
    quantity: Decimal | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AccountState:
    system_id: str
    initial_balance: Decimal
    cash_balance: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees_paid: Decimal
    gross_exposure: Decimal
    open_positions: int
