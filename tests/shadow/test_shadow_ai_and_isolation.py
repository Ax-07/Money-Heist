from __future__ import annotations

from decimal import Decimal

import pytest

from app.intelligence.ai_gateway.budget import AIBudgetLedger
from app.services.shadow import (
    DEFAULT_SHADOW_SYSTEMS,
    ImmutableMarketConstraintsProvider,
    ShadowFleetRunner,
    ShadowIsolationError,
)

from ._helpers import (
    FakeAIUsage,
    make_runtime,
    market_constraints,
    market_context,
    root_opportunity,
    run,
)


def test_ai_usage_records_are_scoped_to_correct_system_id():
    runtimes = tuple(make_runtime(identity) for identity in DEFAULT_SHADOW_SYSTEMS)
    for index, runtime in enumerate(runtimes, start=1):
        runtime.capture_ai_usage(
            [FakeAIUsage(runtime.identity.system_id, Decimal("0.1") * index)]
        )
    result = run(
        ShadowFleetRunner(runtimes).run(
            root_opportunity=root_opportunity(), market_context=market_context()
        )
    )
    for item in result.systems:
        assert len(item.ai_usage) == 1
        assert item.ai_usage[0].system_id == item.identity.system_id
        assert item.ai_usage[0].usage.system_id == item.identity.system_id


def test_ai_usage_ledger_rejects_cross_system_record():
    runtime = make_runtime(DEFAULT_SHADOW_SYSTEMS[0])
    with pytest.raises(ValueError, match="cannot be recorded"):
        runtime.capture_ai_usage(
            [FakeAIUsage(DEFAULT_SHADOW_SYSTEMS[1].system_id, Decimal("0.1"))]
        )


def test_shared_stateful_paper_broker_is_rejected_before_execution():
    runtimes = list(make_runtime(identity) for identity in DEFAULT_SHADOW_SYSTEMS)
    runtimes[1].paper_broker = runtimes[0].paper_broker
    with pytest.raises(ShadowIsolationError):
        ShadowFleetRunner(runtimes)


def test_shared_journal_is_rejected_before_execution():
    runtimes = list(make_runtime(identity) for identity in DEFAULT_SHADOW_SYSTEMS)
    runtimes[1].journal = runtimes[0].journal
    with pytest.raises(ShadowIsolationError, match="journal"):
        ShadowFleetRunner(runtimes)


def test_shared_orchestration_is_rejected_before_execution():
    runtimes = list(make_runtime(identity) for identity in DEFAULT_SHADOW_SYSTEMS)
    runtimes[1].orchestration = runtimes[0].orchestration
    with pytest.raises(ShadowIsolationError, match="orchestration"):
        ShadowFleetRunner(runtimes)


def test_shared_ai_hard_budget_is_rejected_when_contract_exposes_it():
    runtimes = list(make_runtime(identity) for identity in DEFAULT_SHADOW_SYSTEMS)
    shared_budget = AIBudgetLedger(Decimal("1"))
    for runtime in runtimes[:2]:
        runtime.orchestration._budget = shared_budget
    runtimes[2].orchestration._budget = AIBudgetLedger(Decimal("1"))
    with pytest.raises(ShadowIsolationError, match="budget"):
        ShadowFleetRunner(runtimes)


def test_distinct_ai_hard_budgets_are_accepted_when_contract_exposes_them():
    runtimes = list(make_runtime(identity) for identity in DEFAULT_SHADOW_SYSTEMS)
    for runtime in runtimes:
        runtime.orchestration._budget = AIBudgetLedger(Decimal("1"))
    ShadowFleetRunner(runtimes)
    assert len({id(runtime.orchestration._budget) for runtime in runtimes}) == 3


def test_explicit_immutable_market_constraints_may_be_shared():
    shared = ImmutableMarketConstraintsProvider(market_constraints())
    runtimes = tuple(
        make_runtime(identity, market_constraints_override=shared)
        for identity in DEFAULT_SHADOW_SYSTEMS
    )
    fleet = ShadowFleetRunner(runtimes)
    assert all(runtime.market_constraints_provider is shared for runtime in fleet.runtimes)


class MutableMarketProvider:
    def __init__(self):
        self.constraints = market_constraints()

    def get_market_constraints(self, *, symbol):
        return self.constraints.get(symbol)


def test_shared_mutable_market_constraints_provider_is_rejected():
    shared = MutableMarketProvider()
    runtimes = tuple(
        make_runtime(identity, market_constraints_override=shared)
        for identity in DEFAULT_SHADOW_SYSTEMS
    )
    with pytest.raises(ShadowIsolationError, match="immutable"):
        ShadowFleetRunner(runtimes)
