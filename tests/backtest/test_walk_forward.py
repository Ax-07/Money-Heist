from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.backtest import BacktestConfig, DatasetRef, build_walk_forward_plan

START = datetime(2026, 1, 1, tzinfo=UTC)


def candles(count: int = 12):
    items = []
    for index in range(count):
        open_at = START + timedelta(minutes=5 * index)
        price = Decimal("100") + index
        items.append(
            {
                "symbol": "BTC/EUR",
                "timeframe": "5m",
                "open_time": open_at,
                "close_time": open_at + timedelta(minutes=5),
                "open": price,
                "high": price + 1,
                "low": price - 1,
                "close": price,
                "volume": Decimal("1000"),
                "is_closed": True,
            }
        )
    return items


def test_walk_forward_builds_rolling_design_validation_oos_windows() -> None:
    data = candles()
    ref = DatasetRef.from_candles(
        data,
        symbol="BTC/EUR",
        timeframe="5m",
        source="fixture",
    )
    plan = build_walk_forward_plan(
        data,
        dataset=ref,
        design_bars=4,
        validation_bars=2,
        oos_bars=2,
        step_bars=2,
    )

    assert len(plan.windows) == 3
    assert plan.windows[0].split.oos.start_at == START + timedelta(minutes=35)
    assert plan.windows[1].split.oos.start_at == START + timedelta(minutes=45)
    assert plan.windows[2].split.oos.end_at == START + timedelta(minutes=60)
    assert len({window.window_id for window in plan.windows}) == 3


def test_walk_forward_v1_keeps_one_fixed_config_without_optimizer() -> None:
    data = candles()
    ref = DatasetRef.from_candles(
        data,
        symbol="BTC/EUR",
        timeframe="5m",
        source="fixture",
    )
    plan = build_walk_forward_plan(
        data,
        dataset=ref,
        design_bars=4,
        validation_bars=2,
        oos_bars=2,
    )
    config = BacktestConfig(
        system_id="balanced_v1",
        risk_version="risk-v1",
        code_version="git:8db98a4",
        random_seed=17,
    )

    run_sets = plan.run_sets(config)
    assert {item.design.config.canonical_payload()["random_seed"] for item in run_sets} == {17}
    assert {item.oos.config.code_version for item in run_sets} == {"git:8db98a4"}
    assert all(item.design.config == item.validation.config == item.oos.config for item in run_sets)


def test_execute_walk_forward_runs_windows_in_order_with_fixed_config() -> None:
    import asyncio

    from app.services.backtest import (
        BacktestMetricSnapshot,
        BacktestPeriodReport,
        BacktestPeriodRole,
        BacktestSplitReport,
        execute_walk_forward,
    )

    data = candles()
    ref = DatasetRef.from_candles(
        data,
        symbol="BTC/EUR",
        timeframe="5m",
        source="fixture",
    )
    plan = build_walk_forward_plan(
        data,
        dataset=ref,
        design_bars=4,
        validation_bars=2,
        oos_bars=2,
        step_bars=2,
    )
    config = BacktestConfig(system_id="balanced_v1", risk_version="risk-v1", random_seed=3)
    seen = []

    def report(role, run):
        return BacktestPeriodReport(
            role=role,
            run_id=run.run_id,
            dataset_id=run.dataset.dataset_id,
            period_start=run.period_start,
            period_end=run.period_end,
            processed_candles=1,
            opportunity_count=0,
            executed_order_count=0,
            closed_trade_count=0,
            trading_net=BacktestMetricSnapshot(None, "UNAVAILABLE", "NO_TRADES"),
            max_drawdown_pct=BacktestMetricSnapshot(None, "UNAVAILABLE", "NO_TRADES"),
            ai_cost_eur=Decimal("0"),
            economic_net=BacktestMetricSnapshot(None, "UNAVAILABLE", "NO_TRADES"),
            self_funding_ratio=None,
            self_funding_status="TRADING_NET_UNAVAILABLE",
            business_sha256="a" * 64,
        )

    async def execute_split(window, run_set):
        seen.append((window.index, run_set.design.config.random_seed))
        return BacktestSplitReport(
            split_id=window.split.split_id,
            design=report(BacktestPeriodRole.DESIGN, run_set.design),
            validation=report(BacktestPeriodRole.VALIDATION, run_set.validation),
            oos=report(BacktestPeriodRole.OOS, run_set.oos),
        )

    result = asyncio.run(execute_walk_forward(plan, config=config, execute_split=execute_split))

    assert [item[0] for item in seen] == [1, 2, 3]
    assert {item[1] for item in seen} == {3}
    assert len(result.oos_reports) == 3
