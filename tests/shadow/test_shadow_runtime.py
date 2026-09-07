from __future__ import annotations

from app.services.paper_pipeline import PaperPipelineStatus
from app.services.shadow import (
    DEFAULT_SHADOW_SYSTEMS,
    ShadowBranchStatus,
    ShadowFleetRunner,
    derived_opportunity_id,
)

from ._helpers import market_context, root_opportunity, run, three_runtimes


def test_three_systems_receive_same_immutable_market_context():
    context = market_context()
    runtimes = three_runtimes()
    fleet = ShadowFleetRunner(runtimes)
    result = run(fleet.run(root_opportunity=root_opportunity(), market_context=context))

    assert len(result.systems) == 3
    for runtime in runtimes:
        assert runtime.orchestration.received_market_contexts == [context]
        assert runtime.orchestration.received_market_contexts[0] is context


def test_root_opportunity_is_not_mutated_and_common_correlation_is_preserved():
    root = root_opportunity()
    original_id = root.opportunity_id
    original_system_id = root.system_id
    result = run(
        ShadowFleetRunner(three_runtimes()).run(
            root_opportunity=root,
            market_context=market_context(),
        )
    )
    assert root.opportunity_id == original_id
    assert root.system_id == original_system_id
    assert len({item.context.root_correlation_id for item in result.systems}) == 1
    assert all(item.context.root_opportunity_id == original_id for item in result.systems)


def test_each_system_receives_distinct_deterministic_opportunity_clone():
    root = root_opportunity()
    runtimes = three_runtimes()
    result = run(
        ShadowFleetRunner(runtimes).run(
            root_opportunity=root,
            market_context=market_context(),
        )
    )
    derived = [item.opportunity.opportunity_id for item in result.systems]
    assert len(set(derived)) == 3
    for item in result.systems:
        assert item.opportunity.system_id == item.identity.system_id
        assert item.opportunity.snapshot_id == root.snapshot_id
        assert item.opportunity.opportunity_id == derived_opportunity_id(
            root.opportunity_id, item.identity.system_id
        )


def test_system_execution_order_is_stable_even_when_runtimes_are_reversed():
    runtimes = tuple(reversed(three_runtimes()))
    fleet = ShadowFleetRunner(runtimes)
    assert tuple(runtime.identity for runtime in fleet.runtimes) == DEFAULT_SHADOW_SYSTEMS


def test_independent_idempotence_allows_same_root_event_once_per_system():
    fleet = ShadowFleetRunner(three_runtimes())
    first = run(
        fleet.run(root_opportunity=root_opportunity(), market_context=market_context())
    )
    assert all(
        item.paper_result.status is PaperPipelineStatus.EXECUTED for item in first.systems
    )

    second = run(
        fleet.run(root_opportunity=root_opportunity(), market_context=market_context())
    )
    assert all(
        item.paper_result.status is PaperPipelineStatus.DUPLICATE_BLOCKED
        for item in second.systems
    )
    assert all(len(fleet.paper_history(item.identity.system_id)) == 2 for item in second.systems)


def test_no_analysis_in_one_system_does_not_stop_others():
    fleet = ShadowFleetRunner(
        three_runtimes(outcomes=("NO_ANALYSIS", "TRADE", "TRADE"))
    )
    result = run(fleet.run(root_opportunity=root_opportunity(), market_context=market_context()))
    statuses = [item.paper_result.status for item in result.systems]
    assert statuses == [
        PaperPipelineStatus.NO_ANALYSIS,
        PaperPipelineStatus.EXECUTED,
        PaperPipelineStatus.EXECUTED,
    ]


def test_no_trade_in_one_system_does_not_stop_others():
    fleet = ShadowFleetRunner(three_runtimes(outcomes=("TRADE", "NO_TRADE", "TRADE")))
    result = run(fleet.run(root_opportunity=root_opportunity(), market_context=market_context()))
    statuses = [item.paper_result.status for item in result.systems]
    assert statuses == [
        PaperPipelineStatus.EXECUTED,
        PaperPipelineStatus.NO_TRADE,
        PaperPipelineStatus.EXECUTED,
    ]


def test_orchestration_error_in_one_system_does_not_stop_others():
    runtimes = list(three_runtimes())
    runtimes[1].orchestration.fail_with = RuntimeError("injected orchestration failure")
    result = run(
        ShadowFleetRunner(runtimes).run(
            root_opportunity=root_opportunity(), market_context=market_context()
        )
    )
    assert result.systems[0].paper_result.status is PaperPipelineStatus.EXECUTED
    assert result.systems[1].paper_result.status is PaperPipelineStatus.FAILED
    assert result.systems[2].paper_result.status is PaperPipelineStatus.EXECUTED
    assert result.systems[0].status is ShadowBranchStatus.COMPLETED
    assert result.systems[1].status is ShadowBranchStatus.FAILED
    assert result.systems[2].status is ShadowBranchStatus.COMPLETED


def test_market_snapshot_mismatch_fails_before_any_system_runs():
    context = market_context().model_copy(update={"snapshot_id": "different-snapshot"})
    runtimes = three_runtimes()
    try:
        run(
            ShadowFleetRunner(runtimes).run(
                root_opportunity=root_opportunity(), market_context=context
            )
        )
    except ValueError as exc:
        assert "snapshot_id" in str(exc)
    else:
        raise AssertionError("snapshot mismatch must fail closed")
    assert all(runtime.orchestration.calls == 0 for runtime in runtimes)
