from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

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


class HistoricalPositionLifecycle:
    """Future-candle lifecycle bridge around the existing PAPER broker.

    Batch 16.3 deliberately processes only candle OPEN/CLOSE marks. High/low
    target-vs-stop ambiguity belongs to Batch 16.4. A protection is installed
    only after the PAPER entry has executed, so the entry candle can never use
    its own high/low for position management.
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

    @property
    def protections(self) -> tuple[HistoricalTradeProtection, ...]:
        return tuple(self._protections[key] for key in sorted(self._protections))

    async def process_candle_open(
        self,
        row: dict[str, Any],
        *,
        observed_at: datetime,
    ) -> tuple[Any, ...]:
        return await self._process_mark(
            row,
            field_name="open",
            observed_at=observed_at,
        )

    async def process_candle_close(
        self,
        row: dict[str, Any],
        *,
        observed_at: datetime,
    ) -> tuple[Any, ...]:
        return await self._process_mark(
            row,
            field_name="close",
            observed_at=observed_at,
        )

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

        # An opposite proposal may merely reduce an existing position. In that
        # case the old protection remains authoritative and must not be replaced
        # by a stop designed for the opposite direction.
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

        # PaperBroker V1 exposes one stop per symbol. For same-direction adds,
        # the latest approved stop protects the complete resulting position.
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
                # PaperBroker clears a stop on direction flip. Do the same for
                # the historical metadata until the new execution registers its
                # own protection.
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


__all__ = ["HistoricalPositionLifecycle", "HistoricalTradeProtection"]
