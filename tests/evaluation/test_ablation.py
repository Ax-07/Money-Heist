from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.evaluation import (
    AblationMetricStatus,
    AblationRunDescriptor,
    aggregate_ablation,
    compare_ablation,
)
from app.services.backtest import (
    BacktestMetricSnapshot,
    BacktestPeriodReport,
    BacktestPeriodRole,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def metric(value: str | None, status: str = "AVAILABLE") -> BacktestMetricSnapshot:
    return BacktestMetricSnapshot(
        value=None if value is None else Decimal(value),
        status=status,
        reason=None if value is not None else "missing",
    )


def report(
    *,
    run_id: str,
    role: BacktestPeriodRole = BacktestPeriodRole.OOS,
    dataset_id: str = "dataset-1",
    trading_net: str | None = "10",
    economic_net: str | None = "8",
    drawdown: str | None = "0.10",
    ai_cost: str = "2",
    closed_trades: int = 4,
    processed_candles: int = 100,
    opportunity_count: int = 12,
) -> BacktestPeriodReport:
    return BacktestPeriodReport(
        role=role,
        run_id=run_id,
        dataset_id=dataset_id,
        period_start=START,
        period_end=START + timedelta(days=1),
        processed_candles=processed_candles,
        opportunity_count=opportunity_count,
        executed_order_count=closed_trades,
        closed_trade_count=closed_trades,
        trading_net=metric(trading_net),
        max_drawdown_pct=metric(drawdown),
        ai_cost_eur=Decimal(ai_cost),
        economic_net=metric(economic_net),
        self_funding_ratio=None,
        self_funding_status="AVAILABLE",
        business_sha256=f"sha-{run_id}",
    )


def descriptor(
    value: BacktestPeriodReport,
    agents: tuple[str, ...],
    fingerprint: str = "experiment-1",
) -> AblationRunDescriptor:
    return AblationRunDescriptor(
        report=value,
        comparison_fingerprint=fingerprint,
        included_agents=agents,
    )


def test_compare_ablation_reports_positive_marginal_value_and_drawdown_reduction():
    baseline = descriptor(report(run_id="baseline"), ("berlin", "rio", "tokyo"))
    ablated = descriptor(
        report(
            run_id="without-rio",
            trading_net="7",
            economic_net="5",
            drawdown="0.14",
            ai_cost="1.5",
            closed_trades=3,
        ),
        ("berlin", "tokyo"),
    )

    result = compare_ablation(baseline, ablated, agent_id="rio")

    assert result.agent_id == "rio"
    assert result.marginal_trading_net.value == Decimal("3")
    assert result.marginal_economic_net.value == Decimal("3")
    assert result.drawdown_reduction_pct.value == Decimal("0.04")
    assert result.additional_ai_cost_eur == Decimal("0.5")
    assert result.closed_trade_count_delta == 1
    assert result.is_out_of_sample is True


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"dataset_id": "dataset-2"}, "dataset_id"),
        ({"processed_candles": 99}, "processed_candles"),
        ({"opportunity_count": 11}, "opportunity_count"),
    ],
)
def test_compare_ablation_rejects_non_comparable_market_exposure(change, message):
    baseline = descriptor(report(run_id="baseline"), ("berlin", "rio"))
    ablated = descriptor(
        report(run_id="without-rio", **change),
        ("berlin",),
    )

    with pytest.raises(ValueError, match=message):
        compare_ablation(baseline, ablated, agent_id="rio")


def test_compare_ablation_requires_exactly_one_removed_agent():
    baseline = descriptor(report(run_id="baseline"), ("berlin", "rio", "tokyo"))
    ablated = descriptor(report(run_id="ablated"), ("berlin",))

    with pytest.raises(ValueError, match="exactly"):
        compare_ablation(baseline, ablated, agent_id="rio")


def test_compare_ablation_requires_same_experiment_fingerprint():
    baseline = descriptor(report(run_id="baseline"), ("berlin", "rio"), "a")
    ablated = descriptor(report(run_id="ablated"), ("berlin",), "b")

    with pytest.raises(ValueError, match="comparison_fingerprint"):
        compare_ablation(baseline, ablated, agent_id="rio")


def test_unavailable_metrics_remain_unavailable_instead_of_being_invented():
    baseline = descriptor(
        report(run_id="baseline", economic_net=None),
        ("berlin", "rio"),
    )
    ablated = descriptor(
        report(run_id="ablated", economic_net=None),
        ("berlin",),
    )

    result = compare_ablation(baseline, ablated, agent_id="rio")

    assert result.marginal_economic_net.status is AblationMetricStatus.UNAVAILABLE
    assert result.marginal_economic_net.value is None


def test_aggregate_ablation_is_deterministic_and_tracks_oos_evidence():
    first = compare_ablation(
        descriptor(report(run_id="b1"), ("berlin", "rio")),
        descriptor(report(run_id="a1", economic_net="6"), ("berlin",)),
        agent_id="rio",
    )
    second = compare_ablation(
        descriptor(report(run_id="b2", economic_net="6"), ("berlin", "rio")),
        descriptor(report(run_id="a2", economic_net="8"), ("berlin",)),
        agent_id="rio",
    )

    aggregate = aggregate_ablation((second, first))

    assert aggregate.comparison_count == 2
    assert aggregate.oos_comparison_count == 2
    assert aggregate.mean_marginal_economic_net.value == Decimal("0")
    assert aggregate.positive_economic_count == 1
    assert aggregate.negative_economic_count == 1
