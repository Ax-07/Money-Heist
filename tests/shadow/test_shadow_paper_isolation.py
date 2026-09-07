from __future__ import annotations

from decimal import Decimal

from app.services.paper_pipeline import PaperPipelineStatus
from app.services.shadow import (
    DEFAULT_SHADOW_SYSTEMS,
    ShadowFleetRunner,
)
from app.trading.paper import PositionSide
from app.trading.risk import RiskDecisionStatus, RiskReasonCode

from ._helpers import (
    ScenarioOrchestration,
    explicit_test_profile,
    make_runtime,
    market_context,
    root_opportunity,
    run,
    three_runtimes,
)


def test_each_system_has_distinct_paper_broker_and_journal():
    runtimes = three_runtimes()
    assert len({id(item.paper_broker) for item in runtimes}) == 3
    assert len({id(item.journal) for item in runtimes}) == 3
    assert len({id(item.portfolio_provider) for item in runtimes}) == 3
    assert len({id(item.risk_profile_provider) for item in runtimes}) == 3


def test_cash_equity_fees_and_exposure_are_independent():
    runtimes = (
        make_runtime(DEFAULT_SHADOW_SYSTEMS[0], initial_balance="100", fee_bps="10"),
        make_runtime(DEFAULT_SHADOW_SYSTEMS[1], initial_balance="200", fee_bps="20"),
        make_runtime(DEFAULT_SHADOW_SYSTEMS[2], initial_balance="300", fee_bps="30"),
    )
    run(
        ShadowFleetRunner(runtimes).run(
            root_opportunity=root_opportunity(), market_context=market_context()
        )
    )
    accounts = [run(runtime.paper_broker.get_account_state()) for runtime in runtimes]

    assert [item.system_id for item in accounts] == [
        runtime.identity.system_id for runtime in runtimes
    ]
    assert [item.initial_balance for item in accounts] == [
        Decimal("100"),
        Decimal("200"),
        Decimal("300"),
    ]
    assert len({item.cash_balance for item in accounts}) == 3
    assert len({item.equity for item in accounts}) == 3
    assert [item.fees_paid for item in accounts] == [
        Decimal("0.0500"),
        Decimal("0.1000"),
        Decimal("0.1500"),
    ]
    assert all(item.gross_exposure == Decimal("50.0") for item in accounts)


def test_long_in_one_system_and_short_in_another_do_not_net_each_other():
    runtimes = three_runtimes(sides=("LONG", "SHORT", "LONG"))
    run(
        ShadowFleetRunner(runtimes).run(
            root_opportunity=root_opportunity(), market_context=market_context()
        )
    )
    positions = [run(runtime.paper_broker.get_positions()) for runtime in runtimes]
    assert positions[0][0].side is PositionSide.LONG
    assert positions[1][0].side is PositionSide.SHORT
    assert positions[2][0].side is PositionSide.LONG
    assert positions[0][0].system_id != positions[1][0].system_id
    assert positions[0][0].signed_quantity > 0
    assert positions[1][0].signed_quantity < 0


def test_risk_rejection_in_one_system_does_not_change_other_portfolios():
    conservative, balanced, aggressive = DEFAULT_SHADOW_SYSTEMS
    runtimes = (
        make_runtime(conservative),
        make_runtime(
            balanced,
            risk_profile=explicit_test_profile(balanced.system_id, max_positions=0),
        ),
        make_runtime(aggressive),
    )
    result = run(
        ShadowFleetRunner(runtimes).run(
            root_opportunity=root_opportunity(), market_context=market_context()
        )
    )
    assert [item.paper_result.status for item in result.systems] == [
        PaperPipelineStatus.EXECUTED,
        PaperPipelineStatus.RISK_REJECTED,
        PaperPipelineStatus.EXECUTED,
    ]
    rejected = result.systems[1].paper_result.risk_record.decision
    assert rejected.status is RiskDecisionStatus.REJECTED
    assert rejected.reason_codes == (RiskReasonCode.MAX_POSITIONS_LIMIT,)
    assert run(runtimes[1].paper_broker.get_positions()) == ()
    assert len(run(runtimes[0].paper_broker.get_positions())) == 1
    assert len(run(runtimes[2].paper_broker.get_positions())) == 1


def test_same_trade_can_be_accepted_and_rejected_by_explicitly_different_contexts():
    conservative, balanced, _ = DEFAULT_SHADOW_SYSTEMS
    accepted = make_runtime(conservative)
    rejected = make_runtime(
        balanced,
        risk_profile=explicit_test_profile(balanced.system_id, max_positions=0),
    )
    third = make_runtime(DEFAULT_SHADOW_SYSTEMS[2], orchestration=ScenarioOrchestration(outcome="NO_TRADE"))
    result = run(
        ShadowFleetRunner((accepted, rejected, third)).run(
            root_opportunity=root_opportunity(), market_context=market_context()
        )
    )
    assert result.systems[0].paper_result.risk_record.decision.is_authorized
    assert result.systems[1].paper_result.risk_record.decision.status is RiskDecisionStatus.REJECTED


def test_one_system_position_never_modifies_another_broker():
    runtimes = three_runtimes(outcomes=("TRADE", "NO_TRADE", "NO_ANALYSIS"))
    run(
        ShadowFleetRunner(runtimes).run(
            root_opportunity=root_opportunity(), market_context=market_context()
        )
    )
    assert len(run(runtimes[0].paper_broker.get_positions())) == 1
    assert run(runtimes[1].paper_broker.get_positions()) == ()
    assert run(runtimes[2].paper_broker.get_positions()) == ()
    second_account = run(runtimes[1].paper_broker.get_account_state())
    third_account = run(runtimes[2].paper_broker.get_account_state())
    assert second_account.cash_balance == second_account.initial_balance
    assert third_account.cash_balance == third_account.initial_balance
    assert second_account.fees_paid == Decimal("0")
    assert third_account.fees_paid == Decimal("0")
