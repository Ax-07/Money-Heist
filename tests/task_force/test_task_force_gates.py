from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.agents.models import AgentRegistryEntry, AgentRole, AgentState
from app.task_force import (
    TaskForceCapacitySnapshot,
    TaskForceComputeRequest,
    TaskForceGateStatus,
    TaskForceInfluenceScope,
    TaskForceMemberAssignment,
    TaskForceOperatorPolicy,
    TaskForceRegistryAgentSnapshot,
    TaskForceRequest,
    TaskForceTrigger,
    build_task_force_plan,
    evaluate_task_force_compute,
    evaluate_task_force_plan,
)

NOW = datetime(2026, 9, 9, 12, tzinfo=UTC)


def _entry(
    agent_id: str = "berlin",
    *,
    role: AgentRole = AgentRole.TREND_REGIME,
    state: AgentState = AgentState.ACTIVE,
    core: bool = False,
) -> AgentRegistryEntry:
    return AgentRegistryEntry(
        agent_id=agent_id,
        role=role,
        state=state,
        prompt_version="v1",
        model_route="core_reasoning",
        allowed_tools=(),
        core=core,
    )


def _request(**updates) -> TaskForceRequest:
    payload = {
        "request_id": "tf-request-001",
        "system_id": "balanced_v1",
        "opportunity_id": "opp-001",
        "trigger": TaskForceTrigger.COMPLEX_OPPORTUNITY,
        "influence_scope": TaskForceInfluenceScope.ORCHESTRATION_ADVISORY,
        "objective": "Analyse a complex market situation.",
        "question": "Which risks deserve a deeper review?",
        "requested_by": "professor",
        "context_refs": ("snapshot:001",),
        "required_roles": ("trend_regime",),
        "required_capabilities": ("trend",),
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=1),
    }
    payload.update(updates)
    return TaskForceRequest(**payload)


def _policy(**updates) -> TaskForceOperatorPolicy:
    payload = {
        "policy_id": "tf-policy-001",
        "max_task_force_members": 3,
        "max_concurrent_task_forces": 2,
        "max_task_forces_per_period": 4,
        "max_total_budget_eur": Decimal("3"),
        "max_budget_per_member_eur": Decimal("1.5"),
        "max_total_calls": 6,
        "max_calls_per_member": 3,
        "max_retries_per_call": 1,
        "allowed_agent_states": (AgentState.ACTIVE, AgentState.ON_DEMAND),
        "allowed_core_agent_ids": ("palermo",),
        "blocked_agent_ids": (),
    }
    payload.update(updates)
    return TaskForceOperatorPolicy(**payload)


def _member(
    entry: AgentRegistryEntry | None = None,
    *,
    capabilities: tuple[str, ...] = ("trend",),
    budget: str = "1",
    max_calls: int = 2,
) -> TaskForceMemberAssignment:
    entry = entry or _entry()
    return TaskForceMemberAssignment(
        member_id=f"member:{entry.agent_id}",
        agent=TaskForceRegistryAgentSnapshot.from_registry_entry(entry),
        task_role="analyst",
        capabilities=capabilities,
        selection_reasons=("CAPABILITY_MATCH",),
        member_budget_eur=Decimal(budget),
        max_calls=max_calls,
    )


def _plan(request=None, policy=None, members=None):
    request = request or _request()
    policy = policy or _policy()
    members = members or (_member(),)
    return build_task_force_plan(
        task_force_id="tf-001",
        request=request,
        policy=policy,
        members=members,
        created_at=NOW + timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=45),
    )


def _capacity(**updates) -> TaskForceCapacitySnapshot:
    payload = {
        "period_id": "2026-W37",
        "concurrent_task_forces": 0,
        "task_forces_started": 0,
    }
    payload.update(updates)
    return TaskForceCapacitySnapshot(**payload)


def test_plan_gate_allows_plan_within_explicit_limits():
    request = _request()
    policy = _policy()
    plan = _plan(request, policy)

    decision = evaluate_task_force_plan(
        request,
        plan,
        policy,
        capacity=_capacity(),
        evaluated_at=NOW + timedelta(minutes=2),
    )

    assert decision.status is TaskForceGateStatus.ALLOW
    assert decision.reason_codes == ("WITHIN_EXPLICIT_TASK_FORCE_LIMITS",)
    assert decision.execute_task_force is False
    assert decision.operator_authorization_required is True
    assert decision.live_authority is False


def test_plan_gate_blocks_population_caps():
    request = _request()
    policy = _policy(max_concurrent_task_forces=1, max_task_forces_per_period=2)
    plan = _plan(request, policy)

    decision = evaluate_task_force_plan(
        request,
        plan,
        policy,
        capacity=_capacity(concurrent_task_forces=1, task_forces_started=2),
        evaluated_at=NOW + timedelta(minutes=2),
    )

    assert decision.status is TaskForceGateStatus.BLOCK
    assert "CONCURRENT_TASK_FORCE_CAP_REACHED" in decision.reason_codes
    assert "TASK_FORCE_FREQUENCY_CAP_REACHED" in decision.reason_codes


def test_plan_gate_blocks_agent_state_and_blocklist():
    request = _request()
    policy = _policy(blocked_agent_ids=("berlin",))
    plan = _plan(request, policy, (_member(_entry(state=AgentState.SHADOW)),))

    decision = evaluate_task_force_plan(
        request,
        plan,
        policy,
        capacity=_capacity(),
        evaluated_at=NOW + timedelta(minutes=2),
    )

    assert "AGENT_STATE_NOT_ALLOWED" in decision.reason_codes
    assert "BLOCKED_AGENT_SELECTED" in decision.reason_codes


def test_plan_gate_requires_explicit_core_allowlist():
    request = _request(required_roles=("red_team",), required_capabilities=("red_team",))
    policy = _policy(allowed_core_agent_ids=())
    palermo = _entry("palermo", role=AgentRole.RED_TEAM, core=True)
    plan = _plan(request, policy, (_member(palermo, capabilities=("red_team",)),))

    decision = evaluate_task_force_plan(
        request,
        plan,
        policy,
        capacity=_capacity(),
        evaluated_at=NOW + timedelta(minutes=2),
    )

    assert decision.status is TaskForceGateStatus.BLOCK
    assert "CORE_AGENT_NOT_ALLOWED" in decision.reason_codes


def test_plan_gate_reports_missing_role_capability_and_red_team():
    request = _request(
        required_roles=("trend_regime", "red_team"),
        required_capabilities=("trend", "contradiction"),
        red_team_required=True,
    )
    policy = _policy()
    plan = _plan(request, policy)

    decision = evaluate_task_force_plan(
        request,
        plan,
        policy,
        capacity=_capacity(),
        evaluated_at=NOW + timedelta(minutes=2),
    )

    assert decision.missing_roles == ("red_team",)
    assert decision.missing_capabilities == ("contradiction",)
    assert "RED_TEAM_REQUIRED_BUT_MISSING" in decision.reason_codes


def test_plan_gate_blocks_budget_and_call_limits():
    request = _request()
    policy = _policy(max_total_budget_eur=Decimal("0.5"), max_total_calls=1)
    plan = _plan(request, policy)

    decision = evaluate_task_force_plan(
        request,
        plan,
        policy,
        capacity=_capacity(),
        evaluated_at=NOW + timedelta(minutes=2),
    )

    assert "TASK_FORCE_TOTAL_BUDGET_EXCEEDED" in decision.reason_codes
    assert "TASK_FORCE_TOTAL_CALL_LIMIT_EXCEEDED" in decision.reason_codes


def test_plan_gate_fails_closed_on_stale_fingerprint():
    request = _request()
    original_policy = _policy()
    plan = _plan(request, original_policy)
    changed_policy = _policy(max_total_calls=5)

    decision = evaluate_task_force_plan(
        request,
        plan,
        changed_policy,
        capacity=_capacity(),
        evaluated_at=NOW + timedelta(minutes=2),
    )

    assert decision.status is TaskForceGateStatus.BLOCK
    assert "STALE_POLICY_FINGERPRINT" in decision.reason_codes
    assert "STALE_COMPOSITION_FINGERPRINT" in decision.reason_codes


def test_compute_gate_allows_within_task_force_scope_only():
    policy = _policy()
    plan = _plan(policy=policy)
    request = TaskForceComputeRequest(
        task_force_id=plan.task_force_id,
        agent_id="berlin",
        spent_total_eur=Decimal("0.2"),
        spent_member_eur=Decimal("0.2"),
        used_total_calls=0,
        used_member_calls=0,
        requested_eur=Decimal("0.3"),
        retry_index=0,
    )

    decision = evaluate_task_force_compute(plan, policy, request)

    assert decision.status is TaskForceGateStatus.ALLOW
    assert decision.gateway_budget_still_required is True
    assert decision.execute_compute is False


def test_compute_gate_blocks_member_and_total_budget_excess():
    policy = _policy(max_total_budget_eur=Decimal("1"), max_budget_per_member_eur=Decimal("1"))
    plan = _plan(policy=policy)
    request = TaskForceComputeRequest(
        task_force_id=plan.task_force_id,
        agent_id="berlin",
        spent_total_eur=Decimal("0.8"),
        spent_member_eur=Decimal("0.8"),
        used_total_calls=0,
        used_member_calls=0,
        requested_eur=Decimal("0.3"),
    )

    decision = evaluate_task_force_compute(plan, policy, request)

    assert "TASK_FORCE_COMPUTE_BUDGET_EXCEEDED" in decision.reason_codes
    assert "MEMBER_COMPUTE_BUDGET_EXCEEDED" in decision.reason_codes


def test_compute_gate_blocks_call_and_retry_limits():
    policy = _policy(max_total_calls=2, max_calls_per_member=2, max_retries_per_call=1)
    plan = _plan(policy=policy)
    request = TaskForceComputeRequest(
        task_force_id=plan.task_force_id,
        agent_id="berlin",
        spent_total_eur=Decimal("0"),
        spent_member_eur=Decimal("0"),
        used_total_calls=2,
        used_member_calls=2,
        requested_eur=Decimal("0.1"),
        retry_index=2,
    )

    decision = evaluate_task_force_compute(plan, policy, request)

    assert "TASK_FORCE_CALL_LIMIT_EXCEEDED" in decision.reason_codes
    assert "MEMBER_CALL_LIMIT_EXCEEDED" in decision.reason_codes
    assert "RETRY_LIMIT_EXCEEDED" in decision.reason_codes


def test_compute_gate_rejects_agent_outside_plan():
    policy = _policy()
    plan = _plan(policy=policy)
    request = TaskForceComputeRequest(
        task_force_id=plan.task_force_id,
        agent_id="tokyo",
        spent_total_eur=Decimal("0"),
        spent_member_eur=Decimal("0"),
        used_total_calls=0,
        used_member_calls=0,
        requested_eur=Decimal("0.1"),
    )

    try:
        evaluate_task_force_compute(plan, policy, request)
    except ValueError as exc:
        assert "outside the Task Force plan" in str(exc)
    else:
        raise AssertionError("agent outside plan should fail closed")


def test_gate_fingerprints_are_deterministic():
    request = _request()
    policy = _policy()
    plan = _plan(request, policy)
    kwargs = {
        "capacity": _capacity(),
        "evaluated_at": NOW + timedelta(minutes=2),
    }

    first = evaluate_task_force_plan(request, plan, policy, **kwargs)
    second = evaluate_task_force_plan(request, plan, policy, **kwargs)

    assert first.audit_fingerprint_sha256 == second.audit_fingerprint_sha256
    assert first.capacity_fingerprint_sha256 == second.capacity_fingerprint_sha256


def test_compute_gate_blocks_stale_policy_fingerprint():
    original_policy = _policy()
    plan = _plan(policy=original_policy)
    changed_policy = _policy(max_retries_per_call=2)
    request = TaskForceComputeRequest(
        task_force_id=plan.task_force_id,
        agent_id="berlin",
        spent_total_eur=Decimal("0"),
        spent_member_eur=Decimal("0"),
        used_total_calls=0,
        used_member_calls=0,
        requested_eur=Decimal("0.1"),
    )

    decision = evaluate_task_force_compute(plan, changed_policy, request)

    assert decision.status is TaskForceGateStatus.BLOCK
    assert "STALE_POLICY_FINGERPRINT" in decision.reason_codes
