from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from .config import PaperBrokerConfig
from .models import (
    AccountState,
    BrokerOrder,
    Fill,
    Liquidity,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperOrderRequest,
    Position,
    PositionSide,
    StopLoss,
    ZERO,
)


BPS_DENOMINATOR = Decimal("10000")


class PaperBrokerError(RuntimeError):
    """Base error for deterministic paper execution failures."""


class ValidationError(PaperBrokerError):
    pass


class MarketPriceUnavailable(PaperBrokerError):
    pass


class UnknownOrder(PaperBrokerError):
    pass


class UnknownPosition(PaperBrokerError):
    pass


class IdempotencyConflict(PaperBrokerError):
    pass


class PaperBroker:
    """Deterministic in-memory paper broker.

    Accounting is spot-style mark-to-market and supports signed positions:
    buys reduce cash, sells increase cash, and equity is cash plus the marked
    market value of all signed positions. This also provides coherent short
    simulation when ``allow_short`` is enabled while spot/derivatives remains
    an explicit project decision for later batches.

    V1 assumptions:
    - market orders fill immediately at mark +/- configured slippage;
    - limit orders fill in full only after the mark crosses the limit;
    - limit fills use maker fees and no additional slippage;
    - stop losses are one-shot market exits;
    - no partial-fill microstructure model yet.
    """

    def __init__(
        self,
        config: PaperBrokerConfig | None = None,
        *,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config or PaperBrokerConfig()
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(timezone.utc))

        self._cash_balance = self.config.initial_balance
        self._fees_paid = ZERO
        self._realized_pnl = ZERO

        self._marks: dict[str, Decimal] = {}
        self._orders: dict[str, BrokerOrder] = {}
        self._client_order_index: dict[str, str] = {}
        self._request_fingerprints: dict[str, tuple[object, ...]] = {}
        self._fills: list[Fill] = []
        self._positions: dict[str, Position] = {}
        self._stops: dict[str, StopLoss] = {}

    async def submit_order(
        self,
        request: PaperOrderRequest,
        *,
        trigger: str | None = None,
    ) -> BrokerOrder:
        self._validate_request(request)
        fingerprint = self._fingerprint(request)

        existing_id = self._client_order_index.get(request.client_order_id)
        if existing_id is not None:
            if self._request_fingerprints[request.client_order_id] != fingerprint:
                raise IdempotencyConflict(
                    f"client_order_id {request.client_order_id!r} already exists with different payload"
                )
            return self._orders[existing_id]

        now = self._clock()
        order = BrokerOrder(
            broker_order_id=self._id_factory(),
            client_order_id=request.client_order_id,
            system_id=request.system_id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            requested_quantity=request.quantity,
            filled_quantity=ZERO,
            status=OrderStatus.PENDING,
            created_at=now,
            updated_at=now,
            limit_price=request.limit_price,
            trigger=trigger,
        )
        self._orders[order.broker_order_id] = order
        self._client_order_index[request.client_order_id] = order.broker_order_id
        self._request_fingerprints[request.client_order_id] = fingerprint

        if request.order_type is OrderType.MARKET:
            mark = self._require_mark(request.symbol)
            return self._fill_market_order(order, mark)

        mark = self._marks.get(request.symbol)
        if mark is not None and self._limit_is_crossed(order, mark):
            return self._fill_limit_order(order)
        return order

    async def cancel_order(self, order_id: str) -> BrokerOrder:
        order = self._orders.get(order_id)
        if order is None:
            raise UnknownOrder(order_id)
        if order.status is not OrderStatus.PENDING:
            return order
        canceled = order.with_update(status=OrderStatus.CANCELED, updated_at=self._clock())
        self._orders[order_id] = canceled
        return canceled

    async def get_order(self, order_id: str) -> BrokerOrder:
        try:
            return self._orders[order_id]
        except KeyError as exc:
            raise UnknownOrder(order_id) from exc

    async def get_orders(self) -> tuple[BrokerOrder, ...]:
        return tuple(self._orders.values())

    async def get_fills(self) -> tuple[Fill, ...]:
        return tuple(self._fills)

    async def get_positions(self) -> tuple[Position, ...]:
        return tuple(position for position in self._positions.values() if position.is_open)

    async def get_account_state(self) -> AccountState:
        unrealized = ZERO
        gross_exposure = ZERO
        marked_position_value = ZERO

        for symbol, position in self._positions.items():
            if not position.is_open:
                continue
            mark = self._require_mark(symbol)
            unrealized += position.unrealized_pnl(mark)
            gross_exposure += abs(position.signed_quantity * mark)
            marked_position_value += position.signed_quantity * mark

        return AccountState(
            system_id=self.config.system_id,
            initial_balance=self.config.initial_balance,
            cash_balance=self._cash_balance,
            equity=self._cash_balance + marked_position_value,
            realized_pnl=self._realized_pnl,
            unrealized_pnl=unrealized,
            fees_paid=self._fees_paid,
            gross_exposure=gross_exposure,
            open_positions=sum(position.is_open for position in self._positions.values()),
        )

    async def set_stop_loss(
        self,
        symbol: str,
        stop_price: Decimal,
        *,
        quantity: Decimal | None = None,
    ) -> StopLoss:
        position = self._positions.get(symbol)
        if position is None or not position.is_open:
            raise UnknownPosition(symbol)
        if stop_price <= ZERO:
            raise ValidationError("stop_price must be > 0")
        if quantity is not None and quantity <= ZERO:
            raise ValidationError("stop quantity must be > 0")
        if quantity is not None and quantity > position.quantity:
            raise ValidationError("stop quantity cannot exceed current position quantity")

        mark = self._require_mark(symbol)
        if position.side is PositionSide.LONG and stop_price >= mark:
            raise ValidationError("long stop must be below current mark")
        if position.side is PositionSide.SHORT and stop_price <= mark:
            raise ValidationError("short stop must be above current mark")

        stop = StopLoss(
            stop_id=self._id_factory(),
            system_id=self.config.system_id,
            symbol=symbol,
            stop_price=stop_price,
            quantity=quantity,
            created_at=self._clock(),
        )
        self._stops[symbol] = stop
        return stop

    async def cancel_stop_loss(self, symbol: str) -> StopLoss | None:
        return self._stops.pop(symbol, None)

    async def process_price(
        self,
        symbol: str,
        price: Decimal,
        *,
        observed_at: datetime | None = None,
    ) -> tuple[BrokerOrder, ...]:
        """Apply a mark, fill eligible limit orders, then trigger a stop if needed."""
        if price <= ZERO:
            raise ValidationError("price must be > 0")
        self._marks[symbol] = price

        changed_orders: list[BrokerOrder] = []
        pending = [
            order
            for order in self._orders.values()
            if order.symbol == symbol and order.status is OrderStatus.PENDING
        ]
        for order in pending:
            if order.order_type is OrderType.LIMIT and self._limit_is_crossed(order, price):
                changed_orders.append(self._fill_limit_order(order))

        stop = self._stops.get(symbol)
        position = self._positions.get(symbol)
        if stop is not None and position is not None and position.is_open:
            should_trigger = (
                position.side is PositionSide.LONG and price <= stop.stop_price
            ) or (
                position.side is PositionSide.SHORT and price >= stop.stop_price
            )
            if should_trigger:
                quantity = min(stop.quantity or position.quantity, position.quantity)
                side = OrderSide.SELL if position.side is PositionSide.LONG else OrderSide.BUY
                self._stops.pop(symbol, None)
                stop_order = await self.submit_order(
                    PaperOrderRequest(
                        system_id=self.config.system_id,
                        symbol=symbol,
                        side=side,
                        order_type=OrderType.MARKET,
                        quantity=quantity,
                        client_order_id=f"stop:{stop.stop_id}",
                    ),
                    trigger="STOP_LOSS",
                )
                changed_orders.append(stop_order)

        return tuple(changed_orders)

    async def replay_prices(self, ticks: Iterable[tuple[str, Decimal]]) -> AccountState:
        for symbol, price in ticks:
            await self.process_price(symbol, price)
        return await self.get_account_state()

    def _validate_request(self, request: PaperOrderRequest) -> None:
        if request.system_id != self.config.system_id:
            raise ValidationError(
                f"order system_id={request.system_id!r} does not match broker system_id={self.config.system_id!r}"
            )
        if not request.symbol.strip():
            raise ValidationError("symbol must not be empty")
        if not request.client_order_id.strip():
            raise ValidationError("client_order_id must not be empty")
        if request.quantity <= ZERO:
            raise ValidationError("quantity must be > 0")
        if request.order_type is OrderType.LIMIT:
            if request.limit_price is None or request.limit_price <= ZERO:
                raise ValidationError("limit orders require limit_price > 0")
        elif request.limit_price is not None:
            raise ValidationError("market orders must not define limit_price")

        if not self.config.allow_short and request.side is OrderSide.SELL:
            current = self._positions.get(request.symbol)
            available = current.quantity if current and current.signed_quantity > ZERO else ZERO
            if request.quantity > available:
                raise ValidationError("short positions are disabled for this paper broker")

    def _fingerprint(self, request: PaperOrderRequest) -> tuple[object, ...]:
        payload = asdict(request)
        return tuple(payload[key] for key in sorted(payload))

    def _require_mark(self, symbol: str) -> Decimal:
        try:
            return self._marks[symbol]
        except KeyError as exc:
            raise MarketPriceUnavailable(f"no market price available for {symbol}") from exc

    def _limit_is_crossed(self, order: BrokerOrder, mark: Decimal) -> bool:
        assert order.limit_price is not None
        if order.side is OrderSide.BUY:
            return mark <= order.limit_price
        return mark >= order.limit_price

    def _fill_market_order(self, order: BrokerOrder, mark: Decimal) -> BrokerOrder:
        slippage = self.config.market_slippage_bps / BPS_DENOMINATOR
        if order.side is OrderSide.BUY:
            fill_price = mark * (Decimal("1") + slippage)
        else:
            fill_price = mark * (Decimal("1") - slippage)
        return self._apply_full_fill(
            order,
            fill_price=fill_price,
            fee_rate_bps=self.config.taker_fee_bps,
            liquidity=Liquidity.TAKER,
        )

    def _fill_limit_order(self, order: BrokerOrder) -> BrokerOrder:
        assert order.limit_price is not None
        return self._apply_full_fill(
            order,
            fill_price=order.limit_price,
            fee_rate_bps=self.config.maker_fee_bps,
            liquidity=Liquidity.MAKER,
        )

    def _apply_full_fill(
        self,
        order: BrokerOrder,
        *,
        fill_price: Decimal,
        fee_rate_bps: Decimal,
        liquidity: Liquidity,
    ) -> BrokerOrder:
        if order.status is not OrderStatus.PENDING:
            return order

        quantity = order.requested_quantity
        notional = fill_price * quantity
        fee = notional * fee_rate_bps / BPS_DENOMINATOR
        now = self._clock()
        fill = Fill(
            fill_id=self._id_factory(),
            broker_order_id=order.broker_order_id,
            price=fill_price,
            quantity=quantity,
            fee=fee,
            fee_rate_bps=fee_rate_bps,
            liquidity=liquidity,
            filled_at=now,
        )
        self._fills.append(fill)

        if order.side is OrderSide.BUY:
            self._cash_balance -= notional + fee
            signed_fill = quantity
        else:
            self._cash_balance += notional - fee
            signed_fill = -quantity

        self._fees_paid += fee
        self._apply_position_fill(order.symbol, signed_fill, fill_price)

        filled = order.with_update(
            filled_quantity=quantity,
            status=OrderStatus.FILLED,
            average_fill_price=fill_price,
            updated_at=now,
        )
        self._orders[order.broker_order_id] = filled
        return filled

    def _apply_position_fill(self, symbol: str, signed_fill: Decimal, fill_price: Decimal) -> None:
        position = self._positions.get(
            symbol,
            Position(
                system_id=self.config.system_id,
                symbol=symbol,
                signed_quantity=ZERO,
                average_entry=ZERO,
                realized_pnl=ZERO,
            ),
        )
        old_qty = position.signed_quantity
        new_qty = old_qty + signed_fill
        realized_delta = ZERO

        if old_qty == ZERO or (old_qty > ZERO and signed_fill > ZERO) or (old_qty < ZERO and signed_fill < ZERO):
            total_abs = abs(old_qty) + abs(signed_fill)
            avg = (
                (position.average_entry * abs(old_qty)) + (fill_price * abs(signed_fill))
            ) / total_abs
        else:
            closing_qty = min(abs(old_qty), abs(signed_fill))
            if old_qty > ZERO:
                realized_delta = (fill_price - position.average_entry) * closing_qty
            else:
                realized_delta = (position.average_entry - fill_price) * closing_qty

            if new_qty == ZERO:
                avg = ZERO
            elif (old_qty > ZERO and new_qty > ZERO) or (old_qty < ZERO and new_qty < ZERO):
                avg = position.average_entry
            else:
                avg = fill_price

        updated = Position(
            system_id=self.config.system_id,
            symbol=symbol,
            signed_quantity=new_qty,
            average_entry=avg,
            realized_pnl=position.realized_pnl + realized_delta,
        )
        self._positions[symbol] = updated
        self._realized_pnl += realized_delta

        if new_qty == ZERO:
            self._stops.pop(symbol, None)
        elif old_qty != ZERO and (old_qty > ZERO) != (new_qty > ZERO):
            # A stop from the old direction must never survive a position flip.
            self._stops.pop(symbol, None)
