from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
from types import SimpleNamespace

from app.agents.models import AgentRegistryEntry, AgentRole, AgentState
from app.agents.registry import AgentRegistry
from app.task_force.composition import (
    TaskForceCapabilityProfile,
    TaskForceCompositionPolicy,
    TaskForceReputationDimension,
    compose_task_force_members,
)
from app.task_force.models import (
    TaskForceInfluenceScope,
    TaskForceOperatorPolicy,
    TaskForceRequest,
    TaskForceTrigger,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def _entry(agent_id: str, role: AgentRole, state: AgentState, *, core: bool = False):
    return AgentRegistryEntry(
        agent_id=agent_id,
        role=role,
        state=state,
        prompt_version="v1",
        model_route="core_reasoning",
        allowed_tools=(),
        core=core,
    )


def _registry():
    return AgentRegistry(
        (
            _entry("berlin", AgentRole.TREND_REGIME, AgentState.ACTIVE),
            _entry("tokyo", AgentRole.MOMENTUM, AgentState.ACTIVE),
            _entry("nairobi", AgentRole.MARKET_STRUCTURE, AgentState.PROBATION),
            _entry("rio", AgentRole.DERIVATIVES_POSITIONING, AgentState.ON_DEMAND),
            _entry("denver", AgentRole.HISTORICAL_STATISTICS, AgentState.DISABLED),
            _entry("palermo", AgentRole.RED_TEAM, AgentState.ACTIVE, core=True),
        )
    )


def _operator(**updates):
    data = {
        "policy_id": "tf-operator-v1",
        "max_task_force_members": 4,
        "max_concurrent_task_forces": 2,
        "max_task_forces_per_period": 5,
        "max_total_budget_eur": Decimal("2"),
        "max_budget_per_member_eur": Decimal("0.5"),
        "max_total_calls": 12,
        "max_calls_per_member": 3,
        "max_retries_per_call": 1,
        "allowed_agent_states": (
            AgentState.ACTIVE,
            AgentState.ON_DEMAND,
            AgentState.PROBATION,
        ),
        "allowed_core_agent_ids": (),
        "blocked_agent_ids": (),
    }
    data.update(updates)
    return TaskForceOperatorPolicy(**data)


def _composition(**updates):
    data = {
        "composition_policy_id": "tf-compose-v1",
        "target_member_count": 2,
        "member_budget_eur": Decimal("0.2"),
        "member_max_calls": 2,
        "state_preference": (
            AgentState.ACTIVE,
            AgentState.ON_DEMAND,
            AgentState.PROBATION,
        ),
        "reputation_priority": (
            TaskForceReputationDimension.OOS_EVIDENCE,
            TaskForceReputationDimension.MARGINAL_ECONOMIC_NET,
            TaskForceReputationDimension.DRAWDOWN_REDUCTION,
            TaskForceReputationDimension.AVERAGE_COST,
        ),
    }
    data.update(updates)
    return TaskForceCompositionPolicy(**data)


def _request(**updates):
    data = {
        "request_id": "tf-request-001",
        "system_id": "balanced_v1",
        "trigger": TaskForceTrigger.DEEP_DIVE,
        "influence_scope": TaskForceInfluenceScope.ORCHESTRATION_ADVISORY,
        "objective": "Inspect a complex opportunity",
        "question": "Which grounded specialists are relevant?",
        "requested_by": "professor",
        "context_refs": ("snapshot:001",),
        "required_roles": (),
        "required_capabilities": (),
        "red_team_required": False,
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=15),
    }
    data.update(updates)
    return TaskForceRequest(**data)


def _metric(value):
    return SimpleNamespace(status=SimpleNamespace(value="AVAILABLE"), value=Decimal(value))


def _advisory(agent_id: str, *, oos: int, economic: str, cost: str = "0.01"):
    reputation = SimpleNamespace(
        call_count=20,
        oos_ablation_comparison_count=oos,
        marginal_economic_net=_metric(economic),
        drawdown_reduction_pct=_metric("0.02"),
        average_cost_eur=_metric(cost),
        average_latency_ms=_metric("100"),
    )
    recommendation = SimpleNamespace(
        recommended_state=AgentState.ACTIVE,
        evidence_sufficiency=SimpleNamespace(value="SUFFICIENT"),
        action=SimpleNamespace(value="HOLD"),
    )
    return SimpleNamespace(
        agent_id=agent_id,
        audit_fingerprint_sha256=hashlib.sha256(agent_id.encode()).hexdigest(),
        reputation=reputation,
        recommendation=recommendation,
    )


def test_required_role_is_covered_from_registry_role():
    result = compose_task_force_members(
        _request(required_roles=(AgentRole.MOMENTUM.value,)),
        _operator(),
        _composition(target_member_count=1),
        registry=_registry(),
    )
    assert result.complete is True
    assert [member.agent.agent_id for member in result.members] == ["tokyo"]


def test_required_capability_is_never_invented():
    result = compose_task_force_members(
        _request(required_capabilities=("liquidation_analysis",)),
        _operator(),
        _composition(target_member_count=1),
        registry=_registry(),
        capability_profiles=(
            TaskForceCapabilityProfile(
                agent_id="rio",
                capabilities=("liquidation_analysis",),
            ),
        ),
    )
    assert result.complete is True
    assert result.members[0].agent.agent_id == "rio"


def test_disabled_agent_is_never_selected():
    result = compose_task_force_members(
        _request(required_roles=(AgentRole.HISTORICAL_STATISTICS.value,)),
        _operator(),
        _composition(target_member_count=1),
        registry=_registry(),
    )
    assert result.complete is False
    assert result.uncovered_roles == (AgentRole.HISTORICAL_STATISTICS.value,)
    assert all(member.agent.agent_id != "denver" for member in result.members)


def test_core_agent_requires_explicit_allowlist():
    request = _request(red_team_required=True)
    blocked = compose_task_force_members(
        request,
        _operator(),
        _composition(target_member_count=1),
        registry=_registry(),
    )
    assert blocked.complete is False
    allowed = compose_task_force_members(
        request,
        _operator(allowed_core_agent_ids=("palermo",)),
        _composition(target_member_count=1),
        registry=_registry(),
    )
    assert allowed.complete is True
    assert allowed.members[0].agent.agent_id == "palermo"


def test_reputation_priority_is_lexicographic_without_magic_score():
    result = compose_task_force_members(
        _request(),
        _operator(),
        _composition(target_member_count=1),
        registry=_registry(),
        reputation_reports=(
            _advisory("berlin", oos=2, economic="10"),
            _advisory("tokyo", oos=5, economic="1"),
        ),
    )
    assert result.members[0].agent.agent_id == "tokyo"
    assert result.aggregate_reputation_score is None


def test_state_preference_precedes_reputation_dimensions():
    result = compose_task_force_members(
        _request(),
        _operator(),
        _composition(
            target_member_count=1,
            state_preference=(AgentState.ON_DEMAND, AgentState.ACTIVE, AgentState.PROBATION),
        ),
        registry=_registry(),
        reputation_reports=(
            _advisory("berlin", oos=100, economic="100"),
            _advisory("rio", oos=1, economic="0"),
        ),
    )
    assert result.members[0].agent.agent_id == "rio"


def test_reputation_can_be_required_fail_closed():
    result = compose_task_force_members(
        _request(),
        _operator(),
        _composition(target_member_count=1, require_reputation_evidence=True),
        registry=_registry(),
    )
    assert result.members == ()
    assert result.complete is False
    assert result.exclusions


def test_composition_is_deterministic():
    kwargs = dict(
        registry=_registry(),
        capability_profiles=(
            TaskForceCapabilityProfile(agent_id="rio", capabilities=("derivatives",)),
        ),
        reputation_reports=(
            _advisory("berlin", oos=2, economic="3"),
            _advisory("tokyo", oos=2, economic="3"),
        ),
    )
    first = compose_task_force_members(_request(), _operator(), _composition(), **kwargs)
    second = compose_task_force_members(_request(), _operator(), _composition(), **kwargs)
    assert first.composition_fingerprint_sha256 == second.composition_fingerprint_sha256
    assert [m.agent.agent_id for m in first.members] == [m.agent.agent_id for m in second.members]


def test_member_resources_cannot_exceed_operator_policy():
    try:
        compose_task_force_members(
            _request(),
            _operator(),
            _composition(member_budget_eur=Decimal("0.6")),
            registry=_registry(),
        )
    except ValueError as exc:
        assert "member_budget_eur" in str(exc)
    else:
        raise AssertionError("expected resource policy failure")


def test_registry_is_not_mutated():
    registry = _registry()
    before = registry.list()
    compose_task_force_members(
        _request(),
        _operator(),
        _composition(),
        registry=registry,
    )
    assert registry.list() == before
