from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.evaluation import MetricStatus
from app.services.backtest import (
    BacktestAIMode,
    BacktestConfig,
    BacktestRun,
    BacktestRunStatus,
    DatasetRef,
    evaluate_historical_replay,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def sync_test(func):
    def wrapper():
        return asyncio.run(func())

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


def make_run():
    candles = []
    for index, close in enumerate(("100", "110", "105")):
        open_at = START + timedelta(minutes=5 * index)
        price = Decimal(close)
        candles.append(
            {
                "open_time": open_at,
                "close_time": open_at + timedelta(minutes=5),
                "open": price,
                "high": price + Decimal("1"),
                "low": price - Decimal("1"),
                "close": price,
                "volume": Decimal("1000"),
                "is_closed": True,
            }
        )
    dataset = DatasetRef.from_candles(
        candles,
        symbol="BTC/EUR",
        timeframe="5m",
        source="fixture",
    )
    config = BacktestConfig(
        system_id="balanced_v1",
        risk_version="risk-v1",
        ai_mode=BacktestAIMode.MOCK,
        initial_balance=Decimal("100"),
    )
    return BacktestRun.create(dataset=dataset, config=config)


class FakeBroker:
    async def get_orders(self):
        return ()

    async def get_fills(self):
        return ()


def replay_result():
    run = make_run()
    points = (
        SimpleNamespace(
            observed_at=START + timedelta(minutes=5),
            account_state=SimpleNamespace(equity=Decimal("100")),
            feature_snapshot=SimpleNamespace(symbol="BTC/EUR", close=Decimal("100")),
            pipeline_result=None,
            opportunity=None,
            visible_candle_count=1,
            exit_events=(),
        ),
        SimpleNamespace(
            observed_at=START + timedelta(minutes=10),
            account_state=SimpleNamespace(equity=Decimal("110")),
            feature_snapshot=SimpleNamespace(symbol="BTC/EUR", close=Decimal("110")),
            pipeline_result=None,
            opportunity=None,
            visible_candle_count=2,
            exit_events=(),
        ),
        SimpleNamespace(
            observed_at=START + timedelta(minutes=15),
            account_state=SimpleNamespace(equity=Decimal("105")),
            feature_snapshot=SimpleNamespace(symbol="BTC/EUR", close=Decimal("105")),
            pipeline_result=None,
            opportunity=None,
            visible_candle_count=3,
            exit_events=(),
        ),
    )
    return SimpleNamespace(
        backtest_result=SimpleNamespace(
            run=run,
            status=BacktestRunStatus.COMPLETED,
            processed_candles=3,
            opportunity_count=0,
            executed_order_count=0,
        ),
        points=points,
        pipeline_results=(),
    )


@sync_test
async def test_evaluation_reuses_batch10_and_builds_equity_curve() -> None:
    bundle = await evaluate_historical_replay(
        replay_result(),
        broker=FakeBroker(),
    )

    assert [point.equity for point in bundle.equity_points] == [
        Decimal("100"),
        Decimal("100"),
        Decimal("110"),
        Decimal("105"),
    ]
    assert bundle.marks == {"BTC/EUR": Decimal("105")}
    assert bundle.report.trading.max_drawdown_abs.status is MetricStatus.AVAILABLE
    assert bundle.report.trading.max_drawdown_abs.value == Decimal("5")
    assert bundle.report.trading.max_drawdown_pct.value == Decimal("5") / Decimal("110")
    assert bundle.report.ai_costs.total_cost_eur == Decimal("0")
