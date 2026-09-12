from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.evaluation.models import ExecutionRecord
from app.services.backtest.setup_stats import observations_from_historical_replay
from app.services.backtest.splits import BacktestPeriodRole


def _market(snapshot_id: str, observed_at: datetime):
    return SimpleNamespace(
        symbol="BTC/USDC",
        timeframe="1h",
        snapshot_id=snapshot_id,
        feature_version="features-v1",
        regime="bullish_trend",
        observed_at=observed_at,
    )


def _opportunity(opportunity_id: str, snapshot_id: str, observed_at: datetime):
    return SimpleNamespace(
        opportunity_id=opportunity_id,
        system_id="balanced_v1",
        symbol="BTC/USDC",
        timeframe="1h",
        scanner_version="scanner-v1",
        snapshot_id=snapshot_id,
        triggers=("range_break",),
        created_at=observed_at,
    )


def _point(
    *,
    opportunity_id: str,
    snapshot_id: str,
    side: str,
    fill_id: str,
    price: str,
    quantity: str,
    filled_at: datetime,
):
    order_side = "BUY" if side == "LONG" else "SELL"
    return SimpleNamespace(
        opportunity=_opportunity(opportunity_id, snapshot_id, filled_at),
        feature_snapshot=_market(snapshot_id, filled_at),
        pipeline_result=SimpleNamespace(
            orchestration_result=SimpleNamespace(
                trade_proposal=SimpleNamespace(side=side)
            ),
            order=SimpleNamespace(side=order_side),
            fill=SimpleNamespace(
                fill_id=fill_id,
                price=Decimal(price),
                quantity=Decimal(quantity),
                filled_at=filled_at,
            ),
        ),
    )


def _execution(
    fill_id: str,
    side: str,
    quantity: str,
    price: str,
    filled_at: datetime,
) -> ExecutionRecord:
    return ExecutionRecord(
        fill_id=fill_id,
        broker_order_id=f"order-{fill_id}",
        system_id="balanced_v1",
        symbol="BTC/USDC",
        side=side,
        order_type="MARKET",
        quantity=Decimal(quantity),
        price=Decimal(price),
        fee=Decimal("0"),
        filled_at=filled_at,
        slippage_cost=Decimal("0"),
    )


def _trade(
    *,
    trade_id: str,
    exit_fill_id: str,
    side: str,
    quantity: str,
    opened_at: datetime,
    closed_at: datetime,
    net_pnl: str,
):
    return SimpleNamespace(
        trade_id=trade_id,
        exit_fill_id=exit_fill_id,
        system_id="balanced_v1",
        symbol="BTC/USDC",
        side=side,
        quantity=Decimal(quantity),
        entry_price=Decimal("0"),
        opened_at=opened_at,
        closed_at=closed_at,
        net_pnl=Decimal(net_pnl),
    )


def _bundle(points, executions, trades):
    run = SimpleNamespace(
        run_id="run-real-attribution",
        dataset=SimpleNamespace(dataset_id="dataset-real-attribution"),
        config=SimpleNamespace(
            canonical_payload=lambda: {
                "system_id": "balanced_v1",
                "code_version": "16.21r-test",
            }
        ),
    )
    replay = SimpleNamespace(
        backtest_result=SimpleNamespace(run=run),
        points=tuple(points),
    )
    evaluation = SimpleNamespace(
        source=SimpleNamespace(executions=tuple(executions)),
        report=SimpleNamespace(
            trading=SimpleNamespace(closed_trades=tuple(trades))
        ),
    )
    return replay, evaluation


def test_scaled_average_cost_trade_is_split_across_exact_entry_opportunities() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    points = (
        _point(
            opportunity_id="opp-a",
            snapshot_id="snap-a",
            side="LONG",
            fill_id="fill-a",
            price="100",
            quantity="1",
            filled_at=t0,
        ),
        _point(
            opportunity_id="opp-b",
            snapshot_id="snap-b",
            side="LONG",
            fill_id="fill-b",
            price="110",
            quantity="2",
            filled_at=t0 + timedelta(hours=1),
        ),
    )
    executions = (
        _execution("fill-a", "BUY", "1", "100", t0),
        _execution("fill-b", "BUY", "2", "110", t0 + timedelta(hours=1)),
        _execution("fill-close", "SELL", "3", "120", t0 + timedelta(hours=2)),
    )
    trades = (
        _trade(
            trade_id="closed:fill-close:1",
            exit_fill_id="fill-close",
            side="LONG",
            quantity="3",
            opened_at=t0,
            closed_at=t0 + timedelta(hours=2),
            net_pnl="30",
        ),
    )
    replay, evaluation = _bundle(points, executions, trades)

    observations = observations_from_historical_replay(
        replay,
        evaluation,
        period_role=BacktestPeriodRole.DESIGN,
    )

    assert {item.opportunity_id for item in observations} == {"opp-a", "opp-b"}
    pnl = {item.opportunity_id: item.net_pnl for item in observations}
    assert pnl == {"opp-a": Decimal("10"), "opp-b": Decimal("20")}
    assert sum((item.net_pnl for item in observations), Decimal("0")) == Decimal("30")


def test_partial_closes_accumulate_until_position_cycle_is_fully_closed() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    points = (
        _point(
            opportunity_id="opp-a",
            snapshot_id="snap-a",
            side="LONG",
            fill_id="fill-a",
            price="100",
            quantity="1",
            filled_at=t0,
        ),
        _point(
            opportunity_id="opp-b",
            snapshot_id="snap-b",
            side="LONG",
            fill_id="fill-b",
            price="110",
            quantity="1",
            filled_at=t0 + timedelta(hours=1),
        ),
    )
    executions = (
        _execution("fill-a", "BUY", "1", "100", t0),
        _execution("fill-b", "BUY", "1", "110", t0 + timedelta(hours=1)),
        _execution("fill-close-1", "SELL", "1", "115", t0 + timedelta(hours=2)),
        _execution("fill-close-2", "SELL", "1", "120", t0 + timedelta(hours=3)),
    )
    trades = (
        _trade(
            trade_id="closed:fill-close-1:1",
            exit_fill_id="fill-close-1",
            side="LONG",
            quantity="1",
            opened_at=t0,
            closed_at=t0 + timedelta(hours=2),
            net_pnl="10",
        ),
        _trade(
            trade_id="closed:fill-close-2:2",
            exit_fill_id="fill-close-2",
            side="LONG",
            quantity="1",
            opened_at=t0,
            closed_at=t0 + timedelta(hours=3),
            net_pnl="20",
        ),
    )
    replay, evaluation = _bundle(points, executions, trades)

    observations = observations_from_historical_replay(
        replay,
        evaluation,
        period_role=BacktestPeriodRole.VALIDATION,
    )

    assert len(observations) == 2
    assert all(item.net_pnl == Decimal("15") for item in observations)
    assert all(item.closed_at == t0 + timedelta(hours=3) for item in observations)
    assert sum((item.net_pnl for item in observations), Decimal("0")) == Decimal("30")


def test_reversal_fill_closes_old_setup_and_opens_residual_for_new_setup() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    points = (
        _point(
            opportunity_id="opp-long",
            snapshot_id="snap-long",
            side="LONG",
            fill_id="fill-long",
            price="100",
            quantity="1",
            filled_at=t0,
        ),
        _point(
            opportunity_id="opp-short",
            snapshot_id="snap-short",
            side="SHORT",
            fill_id="fill-reverse",
            price="105",
            quantity="2",
            filled_at=t0 + timedelta(hours=1),
        ),
    )
    executions = (
        _execution("fill-long", "BUY", "1", "100", t0),
        _execution("fill-reverse", "SELL", "2", "105", t0 + timedelta(hours=1)),
        _execution("fill-short-close", "BUY", "1", "101", t0 + timedelta(hours=2)),
    )
    trades = (
        _trade(
            trade_id="closed:fill-reverse:1",
            exit_fill_id="fill-reverse",
            side="LONG",
            quantity="1",
            opened_at=t0,
            closed_at=t0 + timedelta(hours=1),
            net_pnl="5",
        ),
        _trade(
            trade_id="closed:fill-short-close:2",
            exit_fill_id="fill-short-close",
            side="SHORT",
            quantity="1",
            opened_at=t0 + timedelta(hours=1),
            closed_at=t0 + timedelta(hours=2),
            net_pnl="4",
        ),
    )
    replay, evaluation = _bundle(points, executions, trades)

    observations = observations_from_historical_replay(
        replay,
        evaluation,
        period_role=BacktestPeriodRole.OOS,
    )

    assert {(item.opportunity_id, item.side, item.net_pnl) for item in observations} == {
        ("opp-long", "LONG", Decimal("5")),
        ("opp-short", "SHORT", Decimal("4")),
    }


def test_partially_realized_but_still_open_setup_is_not_promoted_to_denver() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    points = (
        _point(
            opportunity_id="opp-a",
            snapshot_id="snap-a",
            side="LONG",
            fill_id="fill-a",
            price="100",
            quantity="2",
            filled_at=t0,
        ),
    )
    executions = (
        _execution("fill-a", "BUY", "2", "100", t0),
        _execution("fill-partial", "SELL", "1", "110", t0 + timedelta(hours=1)),
    )
    trades = (
        _trade(
            trade_id="closed:fill-partial:1",
            exit_fill_id="fill-partial",
            side="LONG",
            quantity="1",
            opened_at=t0,
            closed_at=t0 + timedelta(hours=1),
            net_pnl="10",
        ),
    )
    replay, evaluation = _bundle(points, executions, trades)

    observations = observations_from_historical_replay(
        replay,
        evaluation,
        period_role=BacktestPeriodRole.DESIGN,
    )

    assert observations == ()
