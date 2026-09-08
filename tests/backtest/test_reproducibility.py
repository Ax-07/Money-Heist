from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.backtest import (
    BacktestBusinessFingerprint,
    assert_reproducible,
    fingerprint_backtest,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Metric:
    value: Decimal | None
    status: str = "AVAILABLE"
    reason: str | None = None


def report():
    trading = SimpleNamespace(
        executed_fill_count=1,
        executed_order_count=1,
        closed_trade_count=0,
        open_position_count=1,
        winning_trades=0,
        losing_trades=0,
        breakeven_trades=0,
        execution_realized_pnl=Decimal("0"),
        fees_paid=Decimal("0.1"),
        realized_trading_net=Decimal("-0.1"),
        slippage_cost=Metric(Decimal("0.05")),
        gross_pnl_before_costs=Metric(Decimal("1")),
        unrealized_pnl=Metric(Decimal("2")),
        trading_net=Metric(Decimal("1.9")),
        gross_exposure=Metric(Decimal("50")),
        win_rate=Metric(None, "UNAVAILABLE", "NO_CLOSED_TRADES"),
        profit_factor=Metric(None, "UNAVAILABLE", "NO_CLOSED_TRADES"),
        expectancy=Metric(None, "UNAVAILABLE", "NO_CLOSED_TRADES"),
        max_drawdown_abs=Metric(Decimal("0")),
        max_drawdown_pct=Metric(Decimal("0")),
        closed_trades=(),
    )
    ai_costs = SimpleNamespace(
        total_cost_eur=Decimal("0.2"),
        by_agent={"professor": Decimal("0.2")},
        by_model={"model-v1": Decimal("0.2")},
        by_route={"route-v1": Decimal("0.2")},
    )
    return SimpleNamespace(
        report_version="batch10.evaluation.v1",
        trading=trading,
        ai_costs=ai_costs,
        agents=(),
        economic_net=Metric(Decimal("1.7")),
        self_funding_ratio=SimpleNamespace(
            value=Decimal("9.5"),
            status="AVAILABLE",
            basis="TRADING_NET/AI_COST",
        ),
    )


def replay(*, fill_id: str):
    run = SimpleNamespace(
        run_id="run-1",
        dataset=SimpleNamespace(dataset_id="dataset-1"),
        config=SimpleNamespace(ai_mode="MOCK"),
    )
    fill = SimpleNamespace(
        fill_id=fill_id,
        price=Decimal("100"),
        quantity=Decimal("0.5"),
        fee=Decimal("0.1"),
    )
    pipeline = SimpleNamespace(
        status="EXECUTED",
        risk_record=SimpleNamespace(
            decision=SimpleNamespace(
                status="APPROVED",
                reason_codes=("APPROVED",),
                approved_quantity=Decimal("0.5"),
                approved_risk_amount=Decimal("1"),
                approved_notional=Decimal("50"),
            )
        ),
        fill=fill,
    )
    point = SimpleNamespace(
        observed_at=NOW,
        visible_candle_count=40,
        feature_snapshot=SimpleNamespace(snapshot_id="snapshot-1"),
        opportunity=SimpleNamespace(opportunity_id="opp-1"),
        pipeline_result=pipeline,
        account_state=SimpleNamespace(
            cash_balance=Decimal("49.9"),
            equity=Decimal("101.9"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("2"),
            fees_paid=Decimal("0.1"),
            gross_exposure=Decimal("50"),
            open_positions=1,
        ),
        exit_events=(),
    )
    return SimpleNamespace(
        backtest_result=SimpleNamespace(
            run=run,
            processed_candles=1,
            opportunity_count=1,
            executed_order_count=1,
        ),
        points=(point,),
    )


def test_business_fingerprint_ignores_volatile_fill_identity() -> None:
    first = fingerprint_backtest(replay(fill_id="random-a"), report())
    second = fingerprint_backtest(replay(fill_id="random-b"), report())

    assert first == second
    assert_reproducible(first, second)


def test_assert_reproducible_detects_business_change() -> None:
    first = BacktestBusinessFingerprint("run-1", "dataset-1", "MOCK", "a" * 64)
    second = BacktestBusinessFingerprint("run-1", "dataset-1", "MOCK", "b" * 64)

    with pytest.raises(AssertionError, match="business outputs"):
        assert_reproducible(first, second)
