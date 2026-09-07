from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping

from .models import (
    EquityPoint,
    ExecutionRecord,
    Metric,
    ReconstructedPosition,
    TradingMetrics,
    ZERO,
)


@dataclass(slots=True)
class _PositionState:
    signed_quantity: Decimal = ZERO
    average_entry: Decimal = ZERO
    entry_fees: Decimal = ZERO
    entry_slippage: Decimal = ZERO
    entry_slippage_known: bool = True
    opened_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class _ClosedTradeDraft:
    system_id: str
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    opened_at: datetime
    closed_at: datetime
    execution_gross_pnl: Decimal
    fees: Decimal
    slippage_cost: Decimal | None
    gross_pnl_before_costs: Decimal | None
    net_pnl: Decimal
    exit_fill_id: str


def _drawdown(points: tuple[EquityPoint, ...]) -> tuple[Metric, Metric]:
    if len(points) < 2:
        unavailable = Metric.unavailable("INSUFFICIENT_EQUITY_HISTORY")
        return unavailable, unavailable

    ordered = sorted(points, key=lambda point: point.observed_at)
    peak = ordered[0].equity
    max_abs = ZERO
    max_pct = ZERO
    pct_available = peak > ZERO

    for point in ordered:
        if point.equity > peak:
            peak = point.equity
        drawdown = peak - point.equity
        if drawdown > max_abs:
            max_abs = drawdown
        if peak > ZERO:
            pct = drawdown / peak
            if pct > max_pct:
                max_pct = pct
        else:
            pct_available = False

    pct_metric = (
        Metric.available(max_pct)
        if pct_available
        else Metric.unavailable("NON_POSITIVE_EQUITY_PEAK")
    )
    return Metric.available(max_abs), pct_metric


def calculate_trading_metrics(
    executions: tuple[ExecutionRecord, ...],
    *,
    marks: Mapping[str, Decimal] | None = None,
    equity_points: tuple[EquityPoint, ...] = (),
) -> TradingMetrics:
    marks = marks or {}
    ordered = sorted(executions, key=lambda item: (item.filled_at, item.fill_id))
    states: dict[tuple[str, str], _PositionState] = {}
    closed = []
    execution_realized = ZERO
    fees_paid = sum((item.fee for item in ordered), ZERO)
    slippage_known = all(item.slippage_cost is not None for item in ordered)
    total_slippage = (
        sum((item.slippage_cost or ZERO for item in ordered), ZERO) if slippage_known else None
    )

    for execution in ordered:
        position_key = (execution.system_id, execution.symbol)
        state = states.setdefault(position_key, _PositionState())
        signed_fill = execution.quantity if execution.side == "BUY" else -execution.quantity
        old_qty = state.signed_quantity
        old_abs = abs(old_qty)
        same_direction = (
            old_qty == ZERO
            or (old_qty > ZERO and signed_fill > ZERO)
            or (old_qty < ZERO and signed_fill < ZERO)
        )

        if same_direction:
            new_qty = old_qty + signed_fill
            total_abs = old_abs + abs(signed_fill)
            state.average_entry = (
                (state.average_entry * old_abs) + (execution.price * abs(signed_fill))
            ) / total_abs
            state.signed_quantity = new_qty
            state.entry_fees += execution.fee
            if execution.slippage_cost is None:
                state.entry_slippage_known = False
            else:
                state.entry_slippage += execution.slippage_cost
            if old_qty == ZERO:
                state.opened_at = execution.filled_at
            continue

        closing_qty = min(old_abs, abs(signed_fill))
        closing_fraction_of_fill = closing_qty / execution.quantity
        entry_fraction = closing_qty / old_abs
        entry_fee = state.entry_fees * entry_fraction
        exit_fee = execution.fee * closing_fraction_of_fill
        fees_for_trade = entry_fee + exit_fee

        if old_qty > ZERO:
            gross_execution = (execution.price - state.average_entry) * closing_qty
            closed_side = "LONG"
        else:
            gross_execution = (state.average_entry - execution.price) * closing_qty
            closed_side = "SHORT"

        entry_slippage = state.entry_slippage * entry_fraction
        if state.entry_slippage_known and execution.slippage_cost is not None:
            exit_slippage = execution.slippage_cost * closing_fraction_of_fill
            trade_slippage = entry_slippage + exit_slippage
            gross_before_costs = gross_execution + trade_slippage
        else:
            trade_slippage = None
            gross_before_costs = None

        net_trade = gross_execution - fees_for_trade
        execution_realized += gross_execution
        closed.append(
            _ClosedTradeDraft(
                system_id=execution.system_id,
                symbol=execution.symbol,
                side=closed_side,
                quantity=closing_qty,
                entry_price=state.average_entry,
                exit_price=execution.price,
                opened_at=state.opened_at or execution.filled_at,
                closed_at=execution.filled_at,
                execution_gross_pnl=gross_execution,
                fees=fees_for_trade,
                slippage_cost=trade_slippage,
                gross_pnl_before_costs=gross_before_costs,
                net_pnl=net_trade,
                exit_fill_id=execution.fill_id,
            )
        )

        state.entry_fees -= entry_fee
        if state.entry_slippage_known:
            state.entry_slippage -= entry_slippage

        new_qty = old_qty + signed_fill
        if new_qty == ZERO:
            state.signed_quantity = ZERO
            state.average_entry = ZERO
            state.entry_fees = ZERO
            state.entry_slippage = ZERO
            state.entry_slippage_known = True
            state.opened_at = None
        elif (old_qty > ZERO and new_qty > ZERO) or (old_qty < ZERO and new_qty < ZERO):
            state.signed_quantity = new_qty
        else:
            opening_qty = abs(new_qty)
            opening_fraction = opening_qty / execution.quantity
            state.signed_quantity = new_qty
            state.average_entry = execution.price
            state.entry_fees = execution.fee * opening_fraction
            if execution.slippage_cost is None:
                state.entry_slippage = ZERO
                state.entry_slippage_known = False
            else:
                state.entry_slippage = execution.slippage_cost * opening_fraction
                state.entry_slippage_known = True
            state.opened_at = execution.filled_at

    from .models import ClosedTrade

    closed_trades = tuple(
        ClosedTrade(
            trade_id=f"closed:{draft.exit_fill_id}:{index + 1}",
            system_id=draft.system_id,
            symbol=draft.symbol,
            side=draft.side,
            quantity=draft.quantity,
            entry_price=draft.entry_price,
            exit_price=draft.exit_price,
            opened_at=draft.opened_at,
            closed_at=draft.closed_at,
            execution_gross_pnl=draft.execution_gross_pnl,
            fees=draft.fees,
            slippage_cost=draft.slippage_cost,
            gross_pnl_before_costs=draft.gross_pnl_before_costs,
            net_pnl=draft.net_pnl,
            exit_fill_id=draft.exit_fill_id,
        )
        for index, draft in enumerate(closed)
    )

    positions = tuple(
        ReconstructedPosition(
            system_id=system_id,
            symbol=symbol,
            signed_quantity=state.signed_quantity,
            average_entry=state.average_entry,
            entry_fees=state.entry_fees,
            entry_slippage_cost=(state.entry_slippage if state.entry_slippage_known else None),
        )
        for (system_id, symbol), state in sorted(states.items())
        if state.signed_quantity != ZERO
    )

    unrealized_total = ZERO
    exposure_total = ZERO
    missing_marks = []
    for position in positions:
        mark = marks.get(position.symbol)
        if mark is None or mark <= ZERO:
            missing_marks.append(position.symbol)
            continue
        if position.signed_quantity > ZERO:
            unrealized_total += (mark - position.average_entry) * position.signed_quantity
        else:
            unrealized_total += (position.average_entry - mark) * abs(position.signed_quantity)
        exposure_total += abs(position.signed_quantity * mark)

    if missing_marks:
        unrealized_metric = Metric.unavailable(
            "MISSING_MARKS:" + ",".join(sorted(missing_marks))
        )
        exposure_metric = Metric.unavailable(
            "MISSING_MARKS:" + ",".join(sorted(missing_marks))
        )
        trading_net = Metric.unavailable("UNREALIZED_PNL_UNAVAILABLE")
    else:
        unrealized_metric = Metric.available(unrealized_total)
        exposure_metric = Metric.available(exposure_total)
        trading_net = Metric.available(execution_realized + unrealized_total - fees_paid)

    realized_trading_net = execution_realized - fees_paid
    slippage_metric = (
        Metric.available(total_slippage or ZERO)
        if total_slippage is not None
        else Metric.unavailable("SLIPPAGE_NOT_SEPARATELY_RECONSTRUCTIBLE")
    )
    if trading_net.value is not None and total_slippage is not None:
        gross_before_costs = Metric.available(trading_net.value + fees_paid + total_slippage)
    else:
        gross_before_costs = Metric.unavailable("GROSS_PNL_REQUIRES_MARKS_AND_SLIPPAGE")

    wins = [trade for trade in closed_trades if trade.net_pnl > ZERO]
    losses = [trade for trade in closed_trades if trade.net_pnl < ZERO]
    breakeven = [trade for trade in closed_trades if trade.net_pnl == ZERO]
    closed_count = len(closed_trades)

    if closed_count == 0:
        win_rate = Metric.unavailable("NO_CLOSED_TRADES")
        expectancy = Metric.unavailable("NO_CLOSED_TRADES")
        profit_factor = Metric.unavailable("NO_CLOSED_TRADES")
    else:
        win_rate = Metric.available(Decimal(len(wins)) / Decimal(closed_count))
        expectancy = Metric.available(
            sum((trade.net_pnl for trade in closed_trades), ZERO) / Decimal(closed_count)
        )
        gross_profit = sum((trade.net_pnl for trade in wins), ZERO)
        gross_loss = abs(sum((trade.net_pnl for trade in losses), ZERO))
        if gross_loss == ZERO and gross_profit > ZERO:
            profit_factor = Metric.unbounded("NO_LOSING_TRADES")
        elif gross_loss == ZERO:
            profit_factor = Metric.unavailable("NO_PROFIT_OR_LOSS")
        else:
            profit_factor = Metric.available(gross_profit / gross_loss)

    max_drawdown_abs, max_drawdown_pct = _drawdown(equity_points)

    return TradingMetrics(
        executed_fill_count=len(ordered),
        executed_order_count=len({item.broker_order_id for item in ordered}),
        closed_trade_count=closed_count,
        open_position_count=len(positions),
        winning_trades=len(wins),
        losing_trades=len(losses),
        breakeven_trades=len(breakeven),
        execution_realized_pnl=execution_realized,
        fees_paid=fees_paid,
        slippage_cost=slippage_metric,
        gross_pnl_before_costs=gross_before_costs,
        realized_trading_net=realized_trading_net,
        unrealized_pnl=unrealized_metric,
        trading_net=trading_net,
        gross_exposure=exposure_metric,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        max_drawdown_abs=max_drawdown_abs,
        max_drawdown_pct=max_drawdown_pct,
        positions=positions,
        closed_trades=closed_trades,
    )
