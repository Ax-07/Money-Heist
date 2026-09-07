from __future__ import annotations

from decimal import Decimal

from app.services.paper_pipeline import PaperPipelineStatus
from app.services.shadow import (
    CallableBatch10EvaluationAdapter,
    DEFAULT_SHADOW_SYSTEMS,
    MappingMetricProjector,
    MetricAvailability,
    ShadowEvaluationStatus,
    ShadowFleetRunner,
)

from ._helpers import FakeAIUsage, make_runtime, market_context, root_opportunity, run


def test_evaluation_is_called_independently_with_system_scoped_history_and_costs():
    runtimes = tuple(make_runtime(identity) for identity in DEFAULT_SHADOW_SYSTEMS)
    for index, runtime in enumerate(runtimes, start=1):
        runtime.capture_ai_usage(
            [FakeAIUsage(runtime.identity.system_id, Decimal("0.1") * index)]
        )

    seen_inputs = []

    def evaluate(evaluation_input):
        seen_inputs.append(evaluation_input)
        ai_cost = sum(
            (record.estimated_cost for record in evaluation_input.ai_usage_records),
            Decimal("0"),
        )
        return {
            "realized_pnl": Decimal("0"),
            "trading_net": Decimal("1"),
            "economic_net": Decimal("1") - ai_cost,
            "ai_cost": ai_cost,
            "self_funding_ratio": Decimal("10") if ai_cost > 0 else None,
        }

    evaluator = CallableBatch10EvaluationAdapter(
        evaluate_fn=evaluate,
        metrics_fn=MappingMetricProjector(),
    )
    result = run(
        ShadowFleetRunner(runtimes, evaluator=evaluator).run(
            root_opportunity=root_opportunity(), market_context=market_context()
        )
    )

    assert len(seen_inputs) == 3
    assert [item.system_id for item in seen_inputs] == [
        identity.system_id for identity in DEFAULT_SHADOW_SYSTEMS
    ]
    assert all(len(item.paper_history) == 1 for item in seen_inputs)
    assert all(
        all(record.system_id == item.system_id for record in item.ai_usage_records)
        for item in seen_inputs
    )
    assert all(
        item.evaluation.status is ShadowEvaluationStatus.COMPLETED
        for item in result.systems
    )


def test_evaluation_history_is_accumulated_per_system_not_globally():
    runtimes = tuple(make_runtime(identity) for identity in DEFAULT_SHADOW_SYSTEMS)
    seen_lengths: dict[str, list[int]] = {
        identity.system_id: [] for identity in DEFAULT_SHADOW_SYSTEMS
    }

    def evaluate(evaluation_input):
        seen_lengths[evaluation_input.system_id].append(len(evaluation_input.paper_history))
        return {"trading_net": "0"}

    fleet = ShadowFleetRunner(
        runtimes,
        evaluator=CallableBatch10EvaluationAdapter(
            evaluate_fn=evaluate,
            metrics_fn=MappingMetricProjector(),
        ),
    )
    run(fleet.run(root_opportunity=root_opportunity(), market_context=market_context()))
    run(fleet.run(root_opportunity=root_opportunity(), market_context=market_context()))
    assert all(lengths == [1, 2] for lengths in seen_lengths.values())


def test_evaluation_error_does_not_rollback_already_produced_paper_state():
    runtimes = tuple(make_runtime(identity) for identity in DEFAULT_SHADOW_SYSTEMS)
    failing_system = DEFAULT_SHADOW_SYSTEMS[1].system_id

    def evaluate(evaluation_input):
        if evaluation_input.system_id == failing_system:
            raise RuntimeError("injected Batch 10 evaluation failure")
        return {
            "realized_pnl": "0",
            "trading_net": "1",
            "economic_net": "0.9",
            "ai_cost": "0.1",
            "self_funding_ratio": "10",
        }

    result = run(
        ShadowFleetRunner(
            runtimes,
            evaluator=CallableBatch10EvaluationAdapter(
                evaluate_fn=evaluate,
                metrics_fn=MappingMetricProjector(),
            ),
        ).run(root_opportunity=root_opportunity(), market_context=market_context())
    )

    assert all(
        item.paper_result.status is PaperPipelineStatus.EXECUTED for item in result.systems
    )
    assert result.systems[1].evaluation.status is ShadowEvaluationStatus.FAILED
    assert len(run(runtimes[1].paper_broker.get_positions())) == 1
    assert result.systems[0].evaluation.status is ShadowEvaluationStatus.COMPLETED
    assert result.systems[2].evaluation.status is ShadowEvaluationStatus.COMPLETED


def test_comparison_uses_only_metrics_that_batch10_projection_reports_available():
    runtimes = tuple(make_runtime(identity) for identity in DEFAULT_SHADOW_SYSTEMS)

    def evaluate(evaluation_input):
        if evaluation_input.system_id == DEFAULT_SHADOW_SYSTEMS[0].system_id:
            return {"trading_net": "1", "ai_cost": "0.1"}
        if evaluation_input.system_id == DEFAULT_SHADOW_SYSTEMS[1].system_id:
            return {"trading_net": "2", "ai_cost": "0.2", "economic_net": "1.8"}
        return {"trading_net": None, "ai_cost": "0.3", "economic_net": None}

    result = run(
        ShadowFleetRunner(
            runtimes,
            evaluator=CallableBatch10EvaluationAdapter(
                evaluate_fn=evaluate,
                metrics_fn=MappingMetricProjector(),
            ),
        ).run(root_opportunity=root_opportunity(), market_context=market_context())
    )

    assert result.comparison.metrics["trading_net"].availability is MetricAvailability.PARTIAL
    assert result.comparison.metrics["economic_net"].availability is MetricAvailability.UNAVAILABLE
    assert result.comparison.metrics["ai_cost"].availability is MetricAvailability.AVAILABLE
    assert result.comparison.metrics["self_funding_ratio"].availability is MetricAvailability.UNAVAILABLE


def test_economic_net_and_trading_net_remain_distinct_in_comparison():
    runtimes = tuple(make_runtime(identity) for identity in DEFAULT_SHADOW_SYSTEMS)

    def evaluate(evaluation_input):
        index = [item.system_id for item in DEFAULT_SHADOW_SYSTEMS].index(
            evaluation_input.system_id
        )
        return {
            "trading_net": Decimal("10") + index,
            "economic_net": Decimal("1") + index,
            "ai_cost": Decimal("9"),
        }

    result = run(
        ShadowFleetRunner(
            runtimes,
            evaluator=CallableBatch10EvaluationAdapter(
                evaluate_fn=evaluate,
                metrics_fn=MappingMetricProjector(),
            ),
        ).run(root_opportunity=root_opportunity(), market_context=market_context())
    )
    assert result.comparison.metrics["trading_net"].values != result.comparison.metrics[
        "economic_net"
    ].values
    assert result.comparison.promotion_system_id is None
    assert result.comparison.risk_change is None
