from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.evaluation import DataKind, EquityPoint, ExecutionRecord, calculate_trading_metrics
from app.evaluation.models import MetricStatus


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def execution(
    *,
    fill_id: str,
    order_id: str,
    side: str,
    price: str,
    fee: str = "0",
    qty: str = "1",
    symbol: str = "BTCUSDT",
    minute: int = 0,
    slippage: str | None = "0",
) -> ExecutionRecord:
    return ExecutionRecord(
        fill_id=fill_id,
        broker_order_id=order_id,
        system_id="balanced_v1",
        symbol=symbol,
        side=side,
        order_type="MARKET",
        quantity=Decimal(qty),
        price=Decimal(price),
        fee=Decimal(fee),
        filled_at=NOW + timedelta(minutes=minute),
        slippage_cost=(Decimal(slippage) if slippage is not None else None),
    )


def test_no_trade_metrics_are_explicitly_unavailable() -> None:
    metrics = calculate_trading_metrics(())
    assert metrics.execution_realized_pnl == Decimal("0")
    assert metrics.fees_paid == Decimal("0")
    assert metrics.closed_trade_count == 0
    assert metrics.open_position_count == 0
    assert metrics.win_rate.status is MetricStatus.UNAVAILABLE
    assert metrics.profit_factor.status is MetricStatus.UNAVAILABLE
    assert metrics.expectancy.status is MetricStatus.UNAVAILABLE
    assert metrics.max_drawdown_abs.status is MetricStatus.UNAVAILABLE


def test_long_winner_fees_trading_net_win_rate_and_expectancy() -> None:
    metrics = calculate_trading_metrics(
        (
            execution(fill_id="f1", order_id="o1", side="BUY", price="100", fee="1"),
            execution(
                fill_id="f2", order_id="o2", side="SELL", price="120", fee="1", minute=1
            ),
        )
    )
    assert metrics.execution_realized_pnl == Decimal("20")
    assert metrics.fees_paid == Decimal("2")
    assert metrics.realized_trading_net == Decimal("18")
    assert metrics.slippage_cost.value == Decimal("0")
    assert metrics.gross_pnl_before_costs.value == Decimal("20")
    assert metrics.trading_net.value == Decimal("18")
    assert metrics.closed_trade_count == 1
    assert metrics.winning_trades == 1
    assert metrics.win_rate.value == Decimal("1")
    assert metrics.expectancy.value == Decimal("18")
    assert metrics.profit_factor.status is MetricStatus.UNBOUNDED
    assert metrics.closed_trades[0].side == "LONG"
    assert metrics.closed_trades[0].net_pnl == Decimal("18")


def test_short_loser_is_reconstructed() -> None:
    metrics = calculate_trading_metrics(
        (
            execution(fill_id="f1", order_id="o1", side="SELL", price="100", fee="1"),
            execution(fill_id="f2", order_id="o2", side="BUY", price="110", fee="1", minute=1),
        )
    )
    assert metrics.execution_realized_pnl == Decimal("-10")
    assert metrics.realized_trading_net == Decimal("-12")
    assert metrics.losing_trades == 1
    assert metrics.closed_trades[0].side == "SHORT"
    assert metrics.closed_trades[0].net_pnl == Decimal("-12")
    assert metrics.win_rate.value == Decimal("0")
    assert metrics.profit_factor.value == Decimal("0")


def test_multiple_trades_profit_factor_and_expectancy() -> None:
    metrics = calculate_trading_metrics(
        (
            execution(fill_id="f1", order_id="o1", side="BUY", price="100", fee="0"),
            execution(fill_id="f2", order_id="o2", side="SELL", price="110", fee="0", minute=1),
            execution(fill_id="f3", order_id="o3", side="SELL", price="100", fee="0", minute=2),
            execution(fill_id="f4", order_id="o4", side="BUY", price="105", fee="0", minute=3),
        )
    )
    assert metrics.closed_trade_count == 2
    assert metrics.win_rate.value == Decimal("0.5")
    assert metrics.profit_factor.value == Decimal("2")
    assert metrics.expectancy.value == Decimal("2.5")


def test_unrealized_pnl_and_exposure_require_marks() -> None:
    record = execution(fill_id="f1", order_id="o1", side="BUY", price="100", qty="2")
    marked = calculate_trading_metrics((record,), marks={"BTCUSDT": Decimal("110")})
    assert marked.unrealized_pnl.value == Decimal("20")
    assert marked.gross_exposure.value == Decimal("220")
    assert marked.trading_net.value == Decimal("20")

    unmarked = calculate_trading_metrics((record,))
    assert unmarked.unrealized_pnl.value is None
    assert unmarked.trading_net.value is None
    assert unmarked.gross_exposure.value is None


def test_drawdown_only_when_equity_series_is_sufficient() -> None:
    points = tuple(
        EquityPoint(NOW + timedelta(minutes=index), Decimal(value))
        for index, value in enumerate(("100", "120", "90", "95"))
    )
    metrics = calculate_trading_metrics((), equity_points=points)
    assert metrics.max_drawdown_abs.value == Decimal("30")
    assert metrics.max_drawdown_pct.value == Decimal("0.25")


def test_unknown_slippage_stays_unavailable_and_is_not_invented() -> None:
    metrics = calculate_trading_metrics(
        (
            execution(
                fill_id="f1", order_id="o1", side="BUY", price="100", slippage=None
            ),
            execution(
                fill_id="f2", order_id="o2", side="SELL", price="110", minute=1, slippage=None
            ),
        )
    )
    assert metrics.slippage_cost.value is None
    assert metrics.slippage_cost.status is MetricStatus.UNAVAILABLE
    assert metrics.gross_pnl_before_costs.value is None
    assert metrics.trading_net.value == Decimal("10")


def test_counterfactual_kind_cannot_enter_execution_records() -> None:
    try:
        ExecutionRecord(
            fill_id="x",
            broker_order_id="x",
            system_id="s",
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("1"),
            price=Decimal("1"),
            fee=Decimal("0"),
            filled_at=NOW,
            slippage_cost=Decimal("0"),
            data_kind=DataKind.COUNTERFACTUAL,
        )
    except ValueError as exc:
        assert "PAPER_EXECUTED" in str(exc)
    else:
        raise AssertionError("counterfactual execution was accepted as realized PAPER")


def test_positions_from_distinct_system_ids_never_net_against_each_other() -> None:
    first = execution(fill_id="f1", order_id="o1", side="BUY", price="100")
    second = ExecutionRecord(
        fill_id="f2",
        broker_order_id="o2",
        system_id="future_system",
        symbol="BTCUSDT",
        side="SELL",
        order_type="MARKET",
        quantity=Decimal("1"),
        price=Decimal("100"),
        fee=Decimal("0"),
        filled_at=NOW + timedelta(minutes=1),
        slippage_cost=Decimal("0"),
    )
    metrics = calculate_trading_metrics(
        (first, second),
        marks={"BTCUSDT": Decimal("100")},
    )
    assert metrics.closed_trade_count == 0
    assert metrics.open_position_count == 2
    assert {position.system_id for position in metrics.positions} == {
        "balanced_v1",
        "future_system",
    }
