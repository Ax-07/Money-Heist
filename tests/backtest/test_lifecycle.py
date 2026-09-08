from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from types import SimpleNamespace

import pytest

from app.services.backtest import HistoricalPositionLifecycle

NOW = datetime(2026, 1, 1, tzinfo=UTC)
SYSTEM_ID = "balanced_v1"
SYMBOL = "BTC/EUR"


def sync_test(func):
    def wrapper():
        return asyncio.run(func())

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


class Side(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class FakePosition:
    symbol: str
    side: Side
    quantity: Decimal
    average_entry: Decimal

    @property
    def is_open(self) -> bool:
        return self.quantity > 0


class FakeBroker:
    def __init__(self):
        self.config = SimpleNamespace(system_id=SYSTEM_ID)
        self.positions = []
        self.price_calls = []
        self.stop_calls = []

    async def process_price(self, symbol, price, *, observed_at=None):
        self.price_calls.append((symbol, price, observed_at))
        return ()

    async def get_positions(self):
        return tuple(self.positions)

    async def set_stop_loss(self, symbol, stop_price, *, quantity=None):
        self.stop_calls.append((symbol, stop_price, quantity))
        return SimpleNamespace(symbol=symbol, stop_price=stop_price, quantity=quantity)


def executed_result(position, *, side=Side.LONG):
    return SimpleNamespace(
        status=SimpleNamespace(value="EXECUTED"),
        position_after=position,
        risk_input=SimpleNamespace(
            side=side,
            stop_price=Decimal("95") if side is Side.LONG else Decimal("105"),
            proposal_id="proposal-1",
        ),
        orchestration_result=SimpleNamespace(
            trade_proposal=SimpleNamespace(targets=(Decimal("110"), Decimal("115")))
        ),
        fill=SimpleNamespace(filled_at=NOW),
        opportunity_id="opp-1",
    )


@sync_test
async def test_lifecycle_registers_future_stop_and_open_risk():
    broker = FakeBroker()
    position = FakePosition(SYMBOL, Side.LONG, Decimal("2"), Decimal("100"))
    broker.positions = [position]
    lifecycle = HistoricalPositionLifecycle(broker=broker, system_id=SYSTEM_ID)

    protection = await lifecycle.register_execution(executed_result(position), observed_at=NOW)

    assert broker.stop_calls == [(SYMBOL, Decimal("95"), Decimal("2"))]
    assert protection is not None
    assert protection.targets == (Decimal("110"), Decimal("115"))
    assert await lifecycle.open_risk_amount() == Decimal("10")


@sync_test
async def test_lifecycle_processes_only_requested_open_close_marks():
    broker = FakeBroker()
    lifecycle = HistoricalPositionLifecycle(broker=broker, system_id=SYSTEM_ID)
    row = {
        "symbol": SYMBOL,
        "open": Decimal("100"),
        "high": Decimal("999"),
        "low": Decimal("1"),
        "close": Decimal("102"),
    }

    await lifecycle.process_candle_open(row, observed_at=NOW)
    await lifecycle.process_candle_close(row, observed_at=NOW)

    assert broker.price_calls == [
        (SYMBOL, Decimal("100"), NOW),
        (SYMBOL, Decimal("102"), NOW),
    ]


@sync_test
async def test_lifecycle_drops_protection_when_position_is_closed():
    broker = FakeBroker()
    position = FakePosition(SYMBOL, Side.LONG, Decimal("1"), Decimal("100"))
    broker.positions = [position]
    lifecycle = HistoricalPositionLifecycle(broker=broker, system_id=SYSTEM_ID)
    await lifecycle.register_execution(executed_result(position), observed_at=NOW)

    broker.positions = []
    assert await lifecycle.open_risk_amount() == Decimal("0")
    assert lifecycle.protections == ()


@sync_test
async def test_opposite_execution_does_not_replace_existing_direction_stop():
    broker = FakeBroker()
    long_position = FakePosition(SYMBOL, Side.LONG, Decimal("2"), Decimal("100"))
    broker.positions = [long_position]
    lifecycle = HistoricalPositionLifecycle(broker=broker, system_id=SYSTEM_ID)
    await lifecycle.register_execution(executed_result(long_position), observed_at=NOW)

    reduced_long = FakePosition(SYMBOL, Side.LONG, Decimal("1"), Decimal("100"))
    broker.positions = [reduced_long]
    await lifecycle.register_execution(
        executed_result(reduced_long, side=Side.SHORT),
        observed_at=NOW,
    )

    assert broker.stop_calls == [(SYMBOL, Decimal("95"), Decimal("2"))]
    assert lifecycle.protections[0].quantity == Decimal("1")
    assert lifecycle.protections[0].side == "LONG"


@sync_test
async def test_lifecycle_integrates_with_real_paper_broker_and_future_gap_stop():
    pytest.importorskip("app.trading.paper")
    from app.services.backtest import HistoricalExitReason, ReplayClock, ReplayIdFactory
    from app.trading.paper import (
        OrderSide,
        OrderType,
        PaperBroker,
        PaperBrokerConfig,
        PaperOrderRequest,
    )

    clock = ReplayClock.start(NOW)
    broker = PaperBroker(
        PaperBrokerConfig(
            system_id=SYSTEM_ID,
            initial_balance=Decimal("100"),
            taker_fee_bps=Decimal("20"),
            market_slippage_bps=Decimal("5"),
        ),
        id_factory=ReplayIdFactory("lifecycle-real-broker"),
        clock=clock,
    )
    lifecycle = HistoricalPositionLifecycle(broker=broker, system_id=SYSTEM_ID)
    await broker.process_price(SYMBOL, Decimal("100"), observed_at=NOW)
    order = await broker.submit_order(
        PaperOrderRequest(
            system_id=SYSTEM_ID,
            symbol=SYMBOL,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.5"),
            client_order_id="entry-1",
        )
    )
    positions = await broker.get_positions()
    fills = await broker.get_fills()
    position = positions[0]
    result = SimpleNamespace(
        status=SimpleNamespace(value="EXECUTED"),
        position_after=position,
        risk_input=SimpleNamespace(
            side="LONG",
            stop_price=Decimal("95"),
            proposal_id="proposal-real-1",
        ),
        orchestration_result=SimpleNamespace(
            trade_proposal=SimpleNamespace(targets=(Decimal("110"),))
        ),
        fill=fills[-1],
        order=order,
        opportunity_id="opp-real-1",
    )
    await lifecycle.register_execution(result, observed_at=NOW)
    assert await lifecycle.open_risk_amount() > Decimal("0")

    next_open = NOW.replace(minute=5)
    clock.advance_to(next_open)
    events = await lifecycle.process_candle_open(
        {
            "symbol": SYMBOL,
            "open": Decimal("94"),
            "high": Decimal("96"),
            "low": Decimal("93"),
            "close": Decimal("94"),
        },
        observed_at=next_open,
    )

    assert len(events) == 1
    assert events[0].reason is HistoricalExitReason.STOP_GAP
    assert events[0].reference_price == Decimal("94")
    assert events[0].fill_price == Decimal("93.9530")
    assert await broker.get_positions() == ()
    assert await lifecycle.open_risk_amount() == Decimal("0")
    assert any(item.trigger == "STOP_LOSS" for item in await broker.get_orders())


@sync_test
async def test_real_paper_broker_stop_wins_same_candle_and_keeps_market_slippage():
    pytest.importorskip("app.trading.paper")
    from app.services.backtest import HistoricalExitReason, ReplayClock, ReplayIdFactory
    from app.trading.paper import (
        OrderSide,
        OrderType,
        PaperBroker,
        PaperBrokerConfig,
        PaperOrderRequest,
    )

    clock = ReplayClock.start(NOW)
    broker = PaperBroker(
        PaperBrokerConfig(
            system_id=SYSTEM_ID,
            initial_balance=Decimal("100"),
            maker_fee_bps=Decimal("10"),
            taker_fee_bps=Decimal("20"),
            market_slippage_bps=Decimal("5"),
        ),
        id_factory=ReplayIdFactory("intrabar-stop-first"),
        clock=clock,
    )
    lifecycle = HistoricalPositionLifecycle(broker=broker, system_id=SYSTEM_ID)
    await broker.process_price(SYMBOL, Decimal("100"), observed_at=NOW)
    await broker.submit_order(
        PaperOrderRequest(
            system_id=SYSTEM_ID,
            symbol=SYMBOL,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.5"),
            client_order_id="entry-stop-first",
        )
    )
    position = (await broker.get_positions())[0]
    fill = (await broker.get_fills())[-1]
    await lifecycle.register_execution(
        SimpleNamespace(
            status=SimpleNamespace(value="EXECUTED"),
            position_after=position,
            risk_input=SimpleNamespace(
                side="LONG",
                stop_price=Decimal("95"),
                proposal_id="proposal-stop-first",
            ),
            orchestration_result=SimpleNamespace(
                trade_proposal=SimpleNamespace(targets=(Decimal("110"),))
            ),
            fill=fill,
            opportunity_id="opp-stop-first",
        ),
        observed_at=NOW,
    )

    open_at = NOW.replace(minute=5)
    close_at = NOW.replace(minute=10)
    row = {
        "symbol": SYMBOL,
        "open": Decimal("100"),
        "high": Decimal("112"),
        "low": Decimal("94"),
        "close": Decimal("105"),
    }
    clock.advance_to(open_at)
    assert await lifecycle.process_candle_open(row, observed_at=open_at) == ()
    clock.advance_to(close_at)
    events = await lifecycle.process_candle_close(row, observed_at=close_at)

    assert len(events) == 1
    event = events[0]
    assert event.reason is HistoricalExitReason.STOP_INTRABAR
    assert event.reference_price == Decimal("95")
    assert event.fill_price == Decimal("94.9525")
    assert await broker.get_positions() == ()
    assert not any(order.trigger == "TAKE_PROFIT" for order in await broker.get_orders())


@sync_test
async def test_real_paper_broker_target_gap_caps_fill_at_target():
    pytest.importorskip("app.trading.paper")
    from app.services.backtest import HistoricalExitReason, ReplayClock, ReplayIdFactory
    from app.trading.paper import (
        OrderSide,
        OrderType,
        PaperBroker,
        PaperBrokerConfig,
        PaperOrderRequest,
    )

    clock = ReplayClock.start(NOW)
    broker = PaperBroker(
        PaperBrokerConfig(
            system_id=SYSTEM_ID,
            initial_balance=Decimal("100"),
            maker_fee_bps=Decimal("10"),
            taker_fee_bps=Decimal("20"),
            market_slippage_bps=Decimal("5"),
        ),
        id_factory=ReplayIdFactory("intrabar-target-gap"),
        clock=clock,
    )
    lifecycle = HistoricalPositionLifecycle(broker=broker, system_id=SYSTEM_ID)
    await broker.process_price(SYMBOL, Decimal("100"), observed_at=NOW)
    await broker.submit_order(
        PaperOrderRequest(
            system_id=SYSTEM_ID,
            symbol=SYMBOL,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.5"),
            client_order_id="entry-target-gap",
        )
    )
    position = (await broker.get_positions())[0]
    fill = (await broker.get_fills())[-1]
    await lifecycle.register_execution(
        SimpleNamespace(
            status=SimpleNamespace(value="EXECUTED"),
            position_after=position,
            risk_input=SimpleNamespace(
                side="LONG",
                stop_price=Decimal("95"),
                proposal_id="proposal-target-gap",
            ),
            orchestration_result=SimpleNamespace(
                trade_proposal=SimpleNamespace(targets=(Decimal("110"), Decimal("115")))
            ),
            fill=fill,
            opportunity_id="opp-target-gap",
        ),
        observed_at=NOW,
    )

    open_at = NOW.replace(minute=5)
    row = {
        "symbol": SYMBOL,
        "open": Decimal("120"),
        "high": Decimal("122"),
        "low": Decimal("119"),
        "close": Decimal("121"),
    }
    clock.advance_to(open_at)
    events = await lifecycle.process_candle_open(row, observed_at=open_at)

    assert len(events) == 1
    event = events[0]
    assert event.reason is HistoricalExitReason.TARGET_GAP
    assert event.reference_price == Decimal("110")
    assert event.fill_price == Decimal("110")
    assert await broker.get_positions() == ()
    target_orders = [order for order in await broker.get_orders() if order.trigger == "TAKE_PROFIT"]
    assert len(target_orders) == 1
    assert target_orders[0].limit_price == Decimal("110")
