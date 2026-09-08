from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.services.backtest import (
    BacktestConfig,
    BacktestPeriodRole,
    BacktestSplitPlan,
    DatasetRef,
)

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


def dataset():
    return DatasetRef.from_candles(
        candles(),
        symbol="BTC/EUR",
        timeframe="5m",
        source="fixture",
    )


def close_at(index: int) -> datetime:
    return START + timedelta(minutes=5 * (index + 1))


def test_split_plan_creates_explicit_non_overlapping_runs() -> None:
    ref = dataset()
    plan = BacktestSplitPlan.create(
        dataset=ref,
        design_start=close_at(0),
        design_end=close_at(4),
        validation_start=close_at(5),
        validation_end=close_at(7),
        oos_start=close_at(8),
        oos_end=close_at(11),
    )
    config = BacktestConfig(system_id="balanced_v1", risk_version="risk-v1")
    runs = plan.runs(config)

    assert runs.design.period_start == close_at(0)
    assert runs.validation.period_start == close_at(5)
    assert runs.oos.period_start == close_at(8)
    assert plan.design.role is BacktestPeriodRole.DESIGN
    assert plan.validation.role is BacktestPeriodRole.VALIDATION
    assert plan.oos.role is BacktestPeriodRole.OOS
    assert len({runs.design.run_id, runs.validation.run_id, runs.oos.run_id}) == 3


def test_split_plan_rejects_overlap() -> None:
    ref = dataset()
    with pytest.raises(ValueError, match="must not overlap"):
        BacktestSplitPlan.create(
            dataset=ref,
            design_start=close_at(0),
            design_end=close_at(5),
            validation_start=close_at(5),
            validation_end=close_at(7),
            oos_start=close_at(8),
            oos_end=close_at(11),
        )


def test_run_id_tracks_code_execution_version_and_seed() -> None:
    ref = dataset()
    plan = BacktestSplitPlan.create(
        dataset=ref,
        design_start=close_at(0),
        design_end=close_at(4),
        validation_start=close_at(5),
        validation_end=close_at(7),
        oos_start=close_at(8),
        oos_end=close_at(11),
    )
    base = plan.runs(
        BacktestConfig(
            system_id="balanced_v1",
            risk_version="risk-v1",
            code_version="git:abc",
            execution_model_version="historical-ohlc-v1",
            random_seed=7,
        )
    ).oos
    code_changed = plan.runs(
        BacktestConfig(
            system_id="balanced_v1",
            risk_version="risk-v1",
            code_version="git:def",
            execution_model_version="historical-ohlc-v1",
            random_seed=7,
        )
    ).oos
    seed_changed = plan.runs(
        BacktestConfig(
            system_id="balanced_v1",
            risk_version="risk-v1",
            code_version="git:abc",
            execution_model_version="historical-ohlc-v1",
            random_seed=8,
        )
    ).oos

    assert base.run_id != code_changed.run_id
    assert base.run_id != seed_changed.run_id
