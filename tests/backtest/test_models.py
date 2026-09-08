from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.services.backtest import (
    BacktestAIMode,
    BacktestConfig,
    BacktestResult,
    BacktestRun,
    BacktestRunStatus,
    DatasetRef,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def dataset() -> DatasetRef:
    candles = []
    for index in range(3):
        open_time = START + timedelta(minutes=5 * index)
        price = Decimal("100") + index
        candles.append(
            {
                "symbol": "BTC/EUR",
                "timeframe": "5m",
                "open_time": open_time,
                "close_time": open_time + timedelta(minutes=5),
                "open": price,
                "high": price + 1,
                "low": price - 1,
                "close": price,
                "volume": 1000,
                "is_closed": True,
            }
        )
    return DatasetRef.from_candles(
        candles, symbol="BTC/EUR", timeframe="5m", source="fixture"
    )


def config(**overrides) -> BacktestConfig:
    values = {
        "system_id": "balanced_v1",
        "risk_version": "batch05-risk-v1",
        "ai_mode": BacktestAIMode.MOCK,
        "initial_balance": Decimal("100"),
        "prompt_versions": {"professor": "p1"},
        "model_versions": {"professor": "mock-v1"},
    }
    values.update(overrides)
    return BacktestConfig(**values)


def test_backtest_config_is_immutable_and_canonicalizes_version_maps() -> None:
    first = config(
        prompt_versions={"tokyo": "t1", "professor": "p1"},
        model_versions={"professor": "mock-v1", "tokyo": "mock-v1"},
    )
    second = config(
        prompt_versions={"professor": "p1", "tokyo": "t1"},
        model_versions={"tokyo": "mock-v1", "professor": "mock-v1"},
    )

    assert first.canonical_payload() == second.canonical_payload()
    with pytest.raises(TypeError):
        first.prompt_versions["professor"] = "changed"


def test_backtest_run_id_is_reproducible_and_sensitive_to_config() -> None:
    ref = dataset()
    first = BacktestRun.create(dataset=ref, config=config())
    second = BacktestRun.create(dataset=ref, config=config())
    changed = BacktestRun.create(
        dataset=ref,
        config=config(market_slippage_bps=Decimal("9")),
    )

    assert first.run_id == second.run_id
    assert changed.run_id != first.run_id
    assert first.period_start == ref.start_at
    assert first.period_end == ref.end_at


def test_backtest_run_id_changes_with_prompt_version() -> None:
    ref = dataset()
    first = BacktestRun.create(dataset=ref, config=config(prompt_versions={"professor": "p1"}))
    changed = BacktestRun.create(dataset=ref, config=config(prompt_versions={"professor": "p2"}))

    assert first.run_id != changed.run_id


def test_backtest_run_period_must_be_inside_dataset() -> None:
    ref = dataset()
    with pytest.raises(ValueError, match="dataset bounds"):
        BacktestRun.create(
            dataset=ref,
            config=config(),
            period_start=ref.start_at - timedelta(minutes=5),
        )


def test_backtest_result_enforces_failure_semantics() -> None:
    run = BacktestRun.create(dataset=dataset(), config=config())
    completed = BacktestResult(
        run=run,
        status=BacktestRunStatus.COMPLETED,
        processed_candles=3,
    )
    assert completed.processed_candles == 3

    with pytest.raises(ValueError, match="failure_reason"):
        BacktestResult(run=run, status=BacktestRunStatus.FAILED)


def test_backtest_config_rejects_invalid_execution_assumptions() -> None:
    with pytest.raises(ValueError, match="initial_balance"):
        config(initial_balance=Decimal("0"))
    with pytest.raises(ValueError, match="slippage"):
        config(market_slippage_bps=Decimal("-1"))
