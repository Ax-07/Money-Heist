from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.services.backtest import (
    BacktestMetricSnapshot,
    BacktestPeriodReport,
    BacktestPeriodRole,
    BacktestSplitReport,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def period_report(role, start_minute, end_minute):
    return BacktestPeriodReport(
        role=role,
        run_id=f"run-{role.value.lower()}",
        dataset_id="dataset-1",
        period_start=NOW + timedelta(minutes=start_minute),
        period_end=NOW + timedelta(minutes=end_minute),
        processed_candles=10,
        opportunity_count=2,
        executed_order_count=1,
        closed_trade_count=1,
        trading_net=BacktestMetricSnapshot(Decimal("1"), "AVAILABLE"),
        max_drawdown_pct=BacktestMetricSnapshot(Decimal("0.02"), "AVAILABLE"),
        ai_cost_eur=Decimal("0.1"),
        economic_net=BacktestMetricSnapshot(Decimal("0.9"), "AVAILABLE"),
        self_funding_ratio=Decimal("10"),
        self_funding_status="AVAILABLE",
        business_sha256="a" * 64,
    )


def test_split_report_keeps_oos_explicit_and_separate() -> None:
    report = BacktestSplitReport(
        split_id="split-1",
        design=period_report(BacktestPeriodRole.DESIGN, 0, 10),
        validation=period_report(BacktestPeriodRole.VALIDATION, 15, 25),
        oos=period_report(BacktestPeriodRole.OOS, 30, 40),
    )

    assert report.out_of_sample is report.oos
    assert report.oos.is_out_of_sample is True
    assert report.design.is_out_of_sample is False


def test_metric_snapshot_preserves_unavailable_reason() -> None:
    metric = SimpleNamespace(value=None, status="UNAVAILABLE", reason="NO_CLOSED_TRADES")
    snapshot = BacktestMetricSnapshot.from_metric(metric)

    assert snapshot.value is None
    assert snapshot.status == "UNAVAILABLE"
    assert snapshot.reason == "NO_CLOSED_TRADES"
