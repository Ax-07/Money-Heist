from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agents.models import AgentRegistryEntry, AgentRole, AgentState
from app.task_force import (
    TaskForceInfluenceScope,
    TaskForceMemberAssignment,
    TaskForceOperatorPolicy,
    TaskForceRegistryAgentSnapshot,
    TaskForceRequest,
    TaskForceState,
    TaskForceTrigger,
    build_task_force_plan,
    task_force_composition_fingerprint,
    task_force_policy_fingerprint,
    task_force_request_fingerprint,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def _request(**overrides):
    payload = {
        "request_id": "tf-request-001",
        "system_id": "balanced_v1",
        "opportunity_id": "opp-001",
        "trigger": TaskForceTrigger.SPECIALIST_DISAGREEMENT,
        "influence_scope": TaskForceInfluenceScope.ORCHESTRATION_ADVISORY,
        "objective": "Resolve a material disagreement without granting trading authority.",
        "question": "Which evidence best explains the conflicting market interpretation?",
        "requested_by": "professor",
        "context_refs": ("snapshot:btc-eur:001", "orchestration:run:001"),
        "required_roles": ("trend", "statistics"),
        "required_capabilities": ("market_regime", "historical_statistics"),
        "red_team_required": True,
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=20),
    }
    payload.update(overrides)
    return TaskForceRequest(**payload)


def _policy(**overrides):
    payload = {
        "policy_id": "task-force-dev-policy",
        "max_task_force_members": 4,
        "max_concurrent_task_forces": 2,
        "max_task_forces_per_period": 8,
        "max_total_budget_eur": Decimal("1.50"),
        "max_budget_per_member_eur": Decimal("0.50"),
        "max_total_calls": 8,
        "max_calls_per_member": 2,
        "max_retries_per_call": 1,
        "allowed_agent_states": (AgentState.ACTIVE, AgentState.ON_DEMAND),
        "allowed_core_agent_ids": ("palermo",),
        "blocked_agent_ids": (),
    }
    payload.update(overrides)
    return TaskForceOperatorPolicy(**payload)


def _entry(*, agent_id="berlin", allowed_tools=()):
    return AgentRegistryEntry(
        agent_id=agent_id,
        role=AgentRole.TREND_REGIME,
        state=AgentState.ACTIVE,
        prompt_version="v1",
        model_route="core_reasoning",
        allowed_tools=allowed_tools,
        budget_policy_id="default",
        core=False,
    )


def _member(*, member_id="member-berlin", agent_id="berlin"):
    snapshot = TaskForceRegistryAgentSnapshot.from_registry_entry(_entry(agent_id=agent_id))
    return TaskForceMemberAssignment(
        member_id=member_id,
        agent=snapshot,
        task_role="regime_challenge",
        capabilities=("market_regime",),
        selection_reasons=("required role matched",),
        reputation_evidence_refs=("reputation:berlin:batch18",),
        tool_allowlist=(),
        member_budget_eur=Decimal("0.25"),
        max_calls=1,
    )


def test_request_is_explicit_frozen_and_has_no_authority():
    request = _request()

    assert request.auto_execute is False
    assert request.registry_mutation is False
    assert request.risk_authority is False
    assert request.live_authority is False
    assert request.created_at.tzinfo is UTC

    with pytest.raises(ValidationError):
        TaskForceRequest(**{**request.model_dump(), "live_authority": True})


def test_request_rejects_naive_or_invalid_expiry():
    with pytest.raises(ValidationError, match="timezone-aware"):
        _request(created_at=datetime(2026, 9, 9, 12, 0))

    with pytest.raises(ValidationError, match="later than created_at"):
        _request(expires_at=NOW)


def test_policy_requires_explicit_limits_and_forbids_disabled_state():
    with pytest.raises(ValidationError):
        TaskForceOperatorPolicy(policy_id="incomplete")

    with pytest.raises(ValidationError, match="DISABLED"):
        _policy(allowed_agent_states=(AgentState.ACTIVE, AgentState.DISABLED))


def test_snapshot_is_derived_from_registry_entry_only_and_preserves_permissions():
    entry = _entry(allowed_tools=("get_market_context",))
    snapshot = TaskForceRegistryAgentSnapshot.from_registry_entry(entry)

    assert snapshot.source == "AGENT_REGISTRY"
    assert snapshot.agent_id == entry.agent_id
    assert snapshot.allowed_tools == entry.allowed_tools
    assert snapshot.state is AgentState.ACTIVE


def test_task_force_adds_no_tool_permission():
    snapshot = TaskForceRegistryAgentSnapshot.from_registry_entry(
        _entry(allowed_tools=("get_market_context",))
    )

    with pytest.raises(ValidationError, match="cannot grant tools"):
        TaskForceMemberAssignment(
            member_id="member-1",
            agent=snapshot,
            task_role="analysis",
            capabilities=("market_regime",),
            selection_reasons=("matched capability",),
            tool_allowlist=("get_historical_setup_stats",),
            member_budget_eur=Decimal("0.10"),
            max_calls=1,
        )


def test_task_force_snapshot_rejects_permission_escalation_tool_even_if_registry_contract_allows_it(
):
    entry = _entry(allowed_tools=("permission_summary",))

    with pytest.raises(ValidationError, match="unsafe task-force tool"):
        TaskForceRegistryAgentSnapshot.from_registry_entry(entry)


def test_fingerprints_are_deterministic_and_material_changes_make_request_stale():
    request_a = _request(context_refs=("ctx-b", "ctx-a"))
    request_b = _request(
        request_id="another-request-id",
        created_at=NOW + timedelta(seconds=1),
        context_refs=("ctx-a", "ctx-b"),
    )

    assert task_force_request_fingerprint(request_a) == task_force_request_fingerprint(request_b)

    changed = _request(
        context_refs=("ctx-a", "ctx-b"),
        question="A materially different question",
    )
    assert task_force_request_fingerprint(request_a) != task_force_request_fingerprint(changed)


def test_policy_and_composition_fingerprints_are_order_stable():
    policy = _policy(
        allowed_agent_states=(AgentState.ON_DEMAND, AgentState.ACTIVE),
        allowed_core_agent_ids=("palermo", "lisbon"),
    )
    policy_reordered = _policy(
        allowed_agent_states=(AgentState.ACTIVE, AgentState.ON_DEMAND),
        allowed_core_agent_ids=("lisbon", "palermo"),
    )
    assert task_force_policy_fingerprint(policy) == task_force_policy_fingerprint(policy_reordered)

    request_fp = task_force_request_fingerprint(_request())
    policy_fp = task_force_policy_fingerprint(policy)
    berlin = _member()
    tokyo = _member(member_id="member-tokyo", agent_id="tokyo")
    assert task_force_composition_fingerprint(
        request_fingerprint_sha256=request_fp,
        policy_fingerprint_sha256=policy_fp,
        members=(berlin, tokyo),
    ) == task_force_composition_fingerprint(
        request_fingerprint_sha256=request_fp,
        policy_fingerprint_sha256=policy_fp,
        members=(tokyo, berlin),
    )


def test_plan_is_planned_only_and_contains_auditable_fingerprints():
    request = _request()
    policy = _policy()
    members = (_member(),)

    plan = build_task_force_plan(
        task_force_id="task-force-001",
        request=request,
        policy=policy,
        members=members,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )

    assert plan.state is TaskForceState.PLANNED
    assert plan.operator_authorization_required is True
    assert plan.auto_execute is False
    assert plan.registry_mutation is False
    assert plan.risk_authority is False
    assert plan.live_authority is False
    assert plan.request_fingerprint_sha256 == task_force_request_fingerprint(request)
    assert plan.policy_fingerprint_sha256 == task_force_policy_fingerprint(policy)
    assert plan.total_budget_eur == Decimal("0.25")
    assert plan.total_call_limit == 1


def test_plan_rejects_duplicate_agent_and_incoherent_totals():
    request = _request()
    policy = _policy()
    member_a = _member(member_id="member-a")
    member_b = _member(member_id="member-b")

    request_fp = task_force_request_fingerprint(request)
    policy_fp = task_force_policy_fingerprint(policy)
    composition_fp = task_force_composition_fingerprint(
        request_fingerprint_sha256=request_fp,
        policy_fingerprint_sha256=policy_fp,
        members=(member_a, member_b),
    )

    with pytest.raises(ValidationError, match="cannot appear twice"):
        from app.task_force import TaskForcePlan

        TaskForcePlan(
            task_force_id="task-force-dup",
            request_id=request.request_id,
            request_fingerprint_sha256=request_fp,
            policy_id=policy.policy_id,
            policy_fingerprint_sha256=policy_fp,
            members=(member_a, member_b),
            total_budget_eur=Decimal("0.50"),
            total_call_limit=2,
            composition_fingerprint_sha256=composition_fp,
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=10),
        )
