from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.trading.paper import (
    IdempotencyConflict,
    Liquidity,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperBroker,
    PaperBrokerConfig,
    PaperOrderRequest,
    PositionSide,
    ValidationError,
)


D = Decimal


def run(coro):
    return asyncio.run(coro)


class DeterministicIds:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return f"id-{self.value:04d}"


def fixed_clock() -> datetime:
    return datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def broker(**overrides) -> PaperBroker:
    config = PaperBrokerConfig(
        system_id="balanced_v1",
        initial_balance=D("100"),
        maker_fee_bps=D("10"),
        taker_fee_bps=D("10"),
        market_slippage_bps=D("100"),
        allow_short=True,
        **overrides,
    )
    return PaperBroker(config, id_factory=DeterministicIds(), clock=fixed_clock)


def market_order(side: OrderSide, qty: str, client_id: str, symbol: str = "BTCUSDT") -> PaperOrderRequest:
    return PaperOrderRequest(
        system_id="balanced_v1",
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=D(qty),
        client_order_id=client_id,
    )


def test_market_buy_applies_slippage_and_taker_fee() -> None:
    b = broker()
    run(b.process_price("BTCUSDT", D("10")))

    order = run(b.submit_order(market_order(OrderSide.BUY, "2", "mkt-1")))
    fills = run(b.get_fills())

    assert order.status is OrderStatus.FILLED
    assert order.average_fill_price == D("10.10")
    assert len(fills) == 1
    assert fills[0].liquidity is Liquidity.TAKER
    assert fills[0].fee == D("0.02020")


def test_limit_order_waits_for_cross_and_uses_maker_fee() -> None:
    b = broker()
    run(b.process_price("ETHUSDT", D("100")))
    request = PaperOrderRequest(
        system_id="balanced_v1",
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=D("1"),
        limit_price=D("95"),
        client_order_id="limit-1",
    )

    pending = run(b.submit_order(request))
    assert pending.status is OrderStatus.PENDING

    assert run(b.process_price("ETHUSDT", D("96"))) == ()
    changed = run(b.process_price("ETHUSDT", D("94")))

    assert len(changed) == 1
    assert changed[0].status is OrderStatus.FILLED
    assert changed[0].average_fill_price == D("95")
    fill = run(b.get_fills())[0]
    assert fill.liquidity is Liquidity.MAKER
    assert fill.fee == D("0.095")


def test_long_close_updates_realized_pnl_and_account_equity() -> None:
    b = broker()
    run(b.process_price("BTCUSDT", D("10")))
    run(b.submit_order(market_order(OrderSide.BUY, "2", "buy")))
    run(b.process_price("BTCUSDT", D("12")))
    run(b.submit_order(market_order(OrderSide.SELL, "2", "sell")))

    state = run(b.get_account_state())
    positions = run(b.get_positions())

    # Buy at 10.10, sell at 11.88 -> 1.78 * 2 = 3.56 gross realized PnL.
    assert state.realized_pnl == D("3.56")
    assert state.fees_paid == D("0.04396")
    assert state.equity == D("103.51604")
    assert state.unrealized_pnl == D("0")
    assert positions == ()


def test_short_position_and_cover_are_supported_when_enabled() -> None:
    b = broker()
    run(b.process_price("SOLUSDT", D("20")))
    run(b.submit_order(market_order(OrderSide.SELL, "1", "short", symbol="SOLUSDT")))

    position = run(b.get_positions())[0]
    assert position.side is PositionSide.SHORT

    run(b.process_price("SOLUSDT", D("15")))
    run(b.submit_order(market_order(OrderSide.BUY, "1", "cover", symbol="SOLUSDT")))
    state = run(b.get_account_state())

    # Sell at 19.80, buy at 15.15.
    assert state.realized_pnl == D("4.65")
    assert state.equity > D("104")


def test_short_can_be_disabled_for_spot_style_profile() -> None:
    config = PaperBrokerConfig(
        system_id="balanced_v1",
        initial_balance=D("100"),
        allow_short=False,
    )
    b = PaperBroker(config, id_factory=DeterministicIds(), clock=fixed_clock)
    run(b.process_price("BTCUSDT", D("10")))

    with pytest.raises(ValidationError, match="short positions are disabled"):
        run(b.submit_order(market_order(OrderSide.SELL, "1", "short-disabled")))


def test_stop_loss_triggers_one_shot_market_exit() -> None:
    b = broker()
    run(b.process_price("BTCUSDT", D("10")))
    run(b.submit_order(market_order(OrderSide.BUY, "1", "entry")))
    stop = run(b.set_stop_loss("BTCUSDT", D("9")))

    assert run(b.process_price("BTCUSDT", D("9.10"))) == ()
    changed = run(b.process_price("BTCUSDT", D("8.90")))

    assert len(changed) == 1
    assert changed[0].trigger == "STOP_LOSS"
    assert changed[0].side is OrderSide.SELL
    assert changed[0].status is OrderStatus.FILLED
    assert run(b.get_positions()) == ()
    assert stop.stop_id in changed[0].client_order_id


def test_invalid_stop_direction_is_rejected() -> None:
    b = broker()
    run(b.process_price("BTCUSDT", D("10")))
    run(b.submit_order(market_order(OrderSide.BUY, "1", "entry")))

    with pytest.raises(ValidationError, match="long stop must be below"):
        run(b.set_stop_loss("BTCUSDT", D("10.01")))


def test_same_client_order_id_is_idempotent() -> None:
    b = broker()
    run(b.process_price("BTCUSDT", D("10")))
    request = market_order(OrderSide.BUY, "1", "same-id")

    first = run(b.submit_order(request))
    second = run(b.submit_order(request))

    assert first == second
    assert len(run(b.get_fills())) == 1


def test_same_client_order_id_with_different_payload_is_rejected() -> None:
    b = broker()
    run(b.process_price("BTCUSDT", D("10")))
    run(b.submit_order(market_order(OrderSide.BUY, "1", "same-id")))

    with pytest.raises(IdempotencyConflict):
        run(b.submit_order(market_order(OrderSide.BUY, "2", "same-id")))


def test_pending_limit_can_be_canceled_without_fill() -> None:
    b = broker()
    run(b.process_price("BTCUSDT", D("10")))
    order = run(
        b.submit_order(
            PaperOrderRequest(
                system_id="balanced_v1",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=D("1"),
                limit_price=D("8"),
                client_order_id="cancel-me",
            )
        )
    )

    canceled = run(b.cancel_order(order.broker_order_id))
    run(b.process_price("BTCUSDT", D("7")))

    assert canceled.status is OrderStatus.CANCELED
    assert run(b.get_fills()) == ()


def test_broker_rejects_cross_system_order() -> None:
    b = broker()
    bad = PaperOrderRequest(
        system_id="shadow_aggressive",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=D("1"),
        client_order_id="cross-system",
    )

    with pytest.raises(ValidationError, match="does not match broker"):
        run(b.submit_order(bad))


def test_replay_is_reproducible_for_same_inputs() -> None:
    def scenario() -> tuple[Decimal, Decimal, Decimal]:
        b = broker()
        run(b.process_price("BTCUSDT", D("10")))
        run(b.submit_order(market_order(OrderSide.BUY, "1", "entry")))
        run(b.set_stop_loss("BTCUSDT", D("9")))
        run(b.replay_prices([("BTCUSDT", D("10.5")), ("BTCUSDT", D("8.8"))]))
        state = run(b.get_account_state())
        return state.equity, state.realized_pnl, state.fees_paid

    assert scenario() == scenario()
