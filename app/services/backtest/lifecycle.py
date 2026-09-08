from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .intrabar import HistoricalExitReason, resolve_intrabar
from .models import IntrabarPolicy

ZERO = Decimal("0")


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _decimal(value: Any, *, field_name: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not number.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return number


@dataclass(frozen=True, slots=True)
class HistoricalTradeProtection:
    symbol: str
    side: str
    quantity: Decimal
    average_entry: Decimal
    stop_price: Decimal
    targets: tuple[Decimal, ...]
    opened_at: datetime
    opportunity_id: str
    proposal_id: str

    @property
    def open_risk_amount(self) -> Decimal:
        return abs(self.average_entry - self.stop_price) * self.quantity


@dataclass(frozen=True, slots=True)
class HistoricalExitEvent:
    symbol: str
    reason: HistoricalExitReason
    reference_price: Decimal
    fill_price: Decimal
    quantity: Decimal
    observed_at: datetime
    broker_order_id: str
    fill_id: str
    opportunity_id: str
    proposal_id: str


class HistoricalPositionLifecycle:
    """Historical OHLC lifecycle around the existing deterministic PAPER broker.

    Protections are installed only after an entry execution. Consequently the
    entry candle is already complete and can never stop/target the position that
    it just created. Future candles use a deterministic STOP_FIRST intrabar
    resolver. Stop exits are market exits and inherit PaperBroker slippage;
    target exits are conservative limit exits at the first target, with no
    favorable gap improvement and no V1 partial scale-out.
    """

    def __init__(self, *, broker: Any, system_id: str) -> None:
        system_id = system_id.strip()
        if not system_id:
            raise ValueError("system_id must not be empty")
        broker_system_id = getattr(getattr(broker, "config", None), "system_id", None)
        if broker_system_id is not None and broker_system_id != system_id:
            raise ValueError("broker config system_id does not match lifecycle system_id")
        self.broker = broker
        self.system_id = system_id
        self._protections: dict[str, HistoricalTradeProtection] = {}
        self._exit_events: list[HistoricalExitEvent] = []

    @property
    def protections(self) -> tuple[HistoricalTradeProtection, ...]:
        return tuple(self._protections[key] for key in sorted(self._protections))

    @property
    def exit_events(self) -> tuple[HistoricalExitEvent, ...]:
        return tuple(self._exit_events)

    async def process_candle_open(
        self,
        row: dict[str, Any],
        *,
        observed_at: datetime,
        policy: IntrabarPolicy = IntrabarPolicy.STOP_FIRST,
    ) -> tuple[HistoricalExitEvent, ...]:
        """Process the candle open and resolve gap exits at the real open mark."""

        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            raise ValueError("historical candle must define symbol")
        await self._sync_positions()
        protection = self._protections.get(symbol)
        if protection is None:
            await self._process_mark(row, field_name="open", observed_at=observed_at)
            return ()

        resolution = resolve_intrabar(protection, row, policy=policy)
        event: HistoricalExitEvent | None = None
        if resolution is not None and resolution.reason is HistoricalExitReason.STOP_GAP:
            changed = await self.broker.process_price(
                symbol,
                resolution.reference_price,
                observed_at=observed_at,
            )
            event = await self._stop_event(
                protection,
                changed,
                reason=resolution.reason,
                reference_price=resolution.reference_price,
                observed_at=observed_at,
            )
        else:
            await self._process_mark(row, field_name="open", observed_at=observed_at)
            if resolution is not None and resolution.reason is HistoricalExitReason.TARGET_GAP:
                event = await self._target_event(
                    protection,
                    target_price=resolution.reference_price,
                    reason=resolution.reason,
                    observed_at=observed_at,
                )

        await self._sync_positions()
        if event is None:
            return ()
        self._exit_events.append(event)
        return (event,)

    async def process_candle_close(
        self,
        row: dict[str, Any],
        *,
        observed_at: datetime,
        policy: IntrabarPolicy = IntrabarPolicy.STOP_FIRST,
    ) -> tuple[HistoricalExitEvent, ...]:
        """Resolve non-gap OHLC touches, then mark the account to candle close."""

        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            raise ValueError("historical candle must define symbol")
        await self._sync_positions()
        protection = self._protections.get(symbol)
        event: HistoricalExitEvent | None = None

        if protection is not None:
            resolution = resolve_intrabar(protection, row, policy=policy)
            if resolution is not None and resolution.is_gap:
                raise RuntimeError("historical gap exit must be resolved at candle open")
            if resolution is not None and resolution.reason is HistoricalExitReason.STOP_INTRABAR:
                changed = await self.broker.process_price(
                    symbol,
                    resolution.reference_price,
                    observed_at=observed_at,
                )
                event = await self._stop_event(
                    protection,
                    changed,
                    reason=resolution.reason,
                    reference_price=resolution.reference_price,
                    observed_at=observed_at,
                )
            elif (
                resolution is not None
                and resolution.reason is HistoricalExitReason.TARGET_INTRABAR
            ):
                event = await self._target_event(
                    protection,
                    target_price=resolution.reference_price,
                    reason=resolution.reason,
                    observed_at=observed_at,
                )

        await self._process_mark(row, field_name="close", observed_at=observed_at)
        await self._sync_positions()
        if event is None:
            return ()
        self._exit_events.append(event)
        return (event,)

    async def register_execution(
        self,
        pipeline_result: Any,
        *,
        observed_at: datetime,
    ) -> HistoricalTradeProtection | None:
        del observed_at
        if _value(getattr(pipeline_result, "status", None)) != "EXECUTED":
            return None

        await self._sync_positions()
        position = getattr(pipeline_result, "position_after", None)
        risk_input = getattr(pipeline_result, "risk_input", None)
        if position is None or risk_input is None or not bool(getattr(position, "is_open", False)):
            return None

        symbol = str(getattr(position, "symbol", "")).strip()
        if not symbol:
            raise ValueError("executed position must define symbol")
        position_side = str(_value(getattr(position, "side", "")))
        proposal_side = str(_value(getattr(risk_input, "side", "")))
        if position_side != proposal_side:
            return self._protections.get(symbol)

        stop_value = getattr(risk_input, "stop_price", None)
        if stop_value is None:
            raise ValueError("executed historical position requires stop_price")
        stop_price = _decimal(stop_value, field_name="stop_price")
        if stop_price <= ZERO:
            raise ValueError("stop_price must be > 0")

        quantity = _decimal(getattr(position, "quantity", ZERO), field_name="quantity")
        average_entry = _decimal(
            getattr(position, "average_entry", ZERO),
            field_name="average_entry",
        )
        if quantity <= ZERO or average_entry <= ZERO:
            raise ValueError("executed position quantity and average_entry must be > 0")

        proposal = getattr(
            getattr(pipeline_result, "orchestration_result", None),
            "trade_proposal",
            None,
        )
        raw_targets = getattr(proposal, "targets", ()) if proposal is not None else ()
        targets = tuple(_decimal(target, field_name="target") for target in raw_targets)

        await self.broker.set_stop_loss(symbol, stop_price, quantity=quantity)
        protection = HistoricalTradeProtection(
            symbol=symbol,
            side=position_side,
            quantity=quantity,
            average_entry=average_entry,
            stop_price=stop_price,
            targets=targets,
            opened_at=pipeline_result.fill.filled_at,
            opportunity_id=str(getattr(pipeline_result, "opportunity_id", "")),
            proposal_id=str(getattr(risk_input, "proposal_id", "")),
        )
        self._protections[symbol] = protection
        return protection

    async def open_risk_amount(self) -> Decimal:
        await self._sync_positions()
        return sum(
            (protection.open_risk_amount for protection in self._protections.values()),
            start=ZERO,
        )

    async def _stop_event(
        self,
        protection: HistoricalTradeProtection,
        changed_orders: Any,
        *,
        reason: HistoricalExitReason,
        reference_price: Decimal,
        observed_at: datetime,
    ) -> HistoricalExitEvent:
        orders = tuple(changed_orders)
        stop_orders = [
            order
            for order in orders
            if _value(getattr(order, "trigger", None)) == "STOP_LOSS"
        ]
        if not stop_orders:
            raise RuntimeError("historical stop resolution did not produce a STOP_LOSS order")
        order = stop_orders[-1]
        fill = await self._fill_for_order(str(order.broker_order_id))
        return HistoricalExitEvent(
            symbol=protection.symbol,
            reason=reason,
            reference_price=reference_price,
            fill_price=_decimal(fill.price, field_name="fill_price"),
            quantity=_decimal(fill.quantity, field_name="fill_quantity"),
            observed_at=observed_at,
            broker_order_id=str(order.broker_order_id),
            fill_id=str(fill.fill_id),
            opportunity_id=protection.opportunity_id,
            proposal_id=protection.proposal_id,
        )

    async def _target_event(
        self,
        protection: HistoricalTradeProtection,
        *,
        target_price: Decimal,
        reason: HistoricalExitReason,
        observed_at: datetime,
    ) -> HistoricalExitEvent:
        try:
            from app.trading.paper import OrderSide, OrderType, PaperOrderRequest
        except ImportError as exc:  # pragma: no cover - full repo always provides this module.
            raise RuntimeError("PaperBroker order models are required for target exits") from exc

        positions = await self.broker.get_positions()
        position = next(
            (
                item
                for item in positions
                if str(getattr(item, "symbol", "")) == protection.symbol
                and bool(getattr(item, "is_open", False))
            ),
            None,
        )
        if position is None:
            raise RuntimeError("target resolution requires an open PAPER position")

        cancel_stop = getattr(self.broker, "cancel_stop_loss", None)
        if cancel_stop is None:
            raise RuntimeError("PaperBroker cancel_stop_loss is required for target exits")
        await cancel_stop(protection.symbol)

        # Set exactly the target mark. For favorable gaps this deliberately
        # suppresses price improvement: the historical target fill remains at
        # the configured target rather than an unknowable better opening price.
        await self.broker.process_price(
            protection.symbol,
            target_price,
            observed_at=observed_at,
        )
        side = OrderSide.SELL if protection.side == "LONG" else OrderSide.BUY
        quantity = _decimal(position.quantity, field_name="quantity")
        order = await self.broker.submit_order(
            PaperOrderRequest(
                system_id=self.system_id,
                symbol=protection.symbol,
                side=side,
                order_type=OrderType.LIMIT,
                quantity=quantity,
                client_order_id=(
                    f"target:{protection.proposal_id}:{format(target_price.normalize(), 'f')}"
                ),
                limit_price=target_price,
            ),
            trigger="TAKE_PROFIT",
        )
        fill = await self._fill_for_order(str(order.broker_order_id))
        return HistoricalExitEvent(
            symbol=protection.symbol,
            reason=reason,
            reference_price=target_price,
            fill_price=_decimal(fill.price, field_name="fill_price"),
            quantity=_decimal(fill.quantity, field_name="fill_quantity"),
            observed_at=observed_at,
            broker_order_id=str(order.broker_order_id),
            fill_id=str(fill.fill_id),
            opportunity_id=protection.opportunity_id,
            proposal_id=protection.proposal_id,
        )

    async def _fill_for_order(self, broker_order_id: str) -> Any:
        fills = await self.broker.get_fills()
        matches = [
            fill
            for fill in fills
            if str(getattr(fill, "broker_order_id", "")) == broker_order_id
        ]
        if not matches:
            raise RuntimeError("historical exit order has no matching PAPER fill")
        return matches[-1]

    async def _process_mark(
        self,
        row: dict[str, Any],
        *,
        field_name: str,
        observed_at: datetime,
    ) -> tuple[Any, ...]:
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            raise ValueError("historical candle must define symbol")
        price = _decimal(row[field_name], field_name=field_name)
        if price <= ZERO:
            raise ValueError(f"candle {field_name} must be > 0")
        changed = await self.broker.process_price(
            symbol,
            price,
            observed_at=observed_at,
        )
        await self._sync_positions()
        return tuple(changed)

    async def _sync_positions(self) -> None:
        positions = await self.broker.get_positions()
        open_positions = {
            str(position.symbol): position
            for position in positions
            if bool(getattr(position, "is_open", False))
        }
        for symbol, protection in tuple(self._protections.items()):
            position = open_positions.get(symbol)
            if position is None:
                self._protections.pop(symbol, None)
                continue
            side = str(_value(getattr(position, "side", "")))
            if side != protection.side:
                self._protections.pop(symbol, None)
                continue
            self._protections[symbol] = replace(
                protection,
                quantity=_decimal(position.quantity, field_name="quantity"),
                average_entry=_decimal(
                    position.average_entry,
                    field_name="average_entry",
                ),
            )


__all__ = [
    "HistoricalExitEvent",
    "HistoricalPositionLifecycle",
    "HistoricalTradeProtection",
]
