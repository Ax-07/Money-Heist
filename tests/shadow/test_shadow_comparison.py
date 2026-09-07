from __future__ import annotations

from decimal import Decimal

from app.services.shadow import (
    DEFAULT_SHADOW_SYSTEMS,
    MappingMetricProjector,
    MetricAvailability,
    ShadowComparisonEngine,
    ShadowMetricSnapshot,
)


def system_ids():
    return [item.system_id for item in DEFAULT_SHADOW_SYSTEMS]


def test_mapping_projector_preserves_unavailable_values_as_none():
    projector = MappingMetricProjector()
    metrics = projector(
        {
            "realized_pnl": "2.5",
            "trading_net": None,
            "economic_net": "UNKNOWN",
            "ai_cost": "0.4",
        }
    )
    assert metrics.realized_pnl == Decimal("2.5")
    assert metrics.trading_net is None
    assert metrics.economic_net is None
    assert metrics.ai_cost == Decimal("0.4")
    assert metrics.self_funding_ratio is None


def test_comparison_calculates_only_available_pairwise_deltas():
    ids = system_ids()
    snapshots = {
        ids[0]: ShadowMetricSnapshot(trading_net=Decimal("1")),
        ids[1]: ShadowMetricSnapshot(trading_net=Decimal("3")),
        ids[2]: ShadowMetricSnapshot(trading_net=None),
    }
    comparison = ShadowComparisonEngine().compare(system_order=ids, snapshots=snapshots)
    metric = comparison.metrics["trading_net"]
    assert metric.availability is MetricAvailability.PARTIAL
    assert len(metric.pairwise_deltas) == 1
    delta = metric.pairwise_deltas[0]
    assert delta.left_system_id == ids[0]
    assert delta.right_system_id == ids[1]
    assert delta.delta_right_minus_left == Decimal("2")


def test_comparison_is_unavailable_with_less_than_two_values():
    ids = system_ids()
    comparison = ShadowComparisonEngine().compare(
        system_order=ids,
        snapshots={ids[0]: ShadowMetricSnapshot(economic_net=Decimal("1"))},
    )
    metric = comparison.metrics["economic_net"]
    assert metric.availability is MetricAvailability.UNAVAILABLE
    assert metric.pairwise_deltas == ()


def test_all_five_required_metrics_are_compared_when_available():
    ids = system_ids()
    snapshots = {
        system_id: ShadowMetricSnapshot(
            realized_pnl=Decimal(index),
            trading_net=Decimal(index) - Decimal("0.1"),
            economic_net=Decimal(index) - Decimal("0.2"),
            ai_cost=Decimal("0.1") * index,
            self_funding_ratio=Decimal(index) / Decimal("2"),
        )
        for index, system_id in enumerate(ids, start=1)
    }
    comparison = ShadowComparisonEngine().compare(system_order=ids, snapshots=snapshots)
    assert set(comparison.metrics) == {
        "realized_pnl",
        "trading_net",
        "economic_net",
        "ai_cost",
        "self_funding_ratio",
    }
    assert all(
        item.availability is MetricAvailability.AVAILABLE
        for item in comparison.metrics.values()
    )


def test_comparison_has_no_promotion_or_risk_change_authority():
    ids = system_ids()
    comparison = ShadowComparisonEngine().compare(
        system_order=ids,
        snapshots={
            system_id: ShadowMetricSnapshot(
                economic_net=Decimal("999") if index == 2 else Decimal("0"),
                self_funding_ratio=Decimal("999") if index == 2 else Decimal("0"),
            )
            for index, system_id in enumerate(ids)
        },
    )
    assert comparison.promotion_system_id is None
    assert comparison.risk_change is None
