from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.agents.models import AgentRegistryEntry, AgentRole, AgentState
from app.task_force import (
    TaskForceInfluenceScope,
    TaskForceLifecycleAction,
    TaskForceMemberAssignment,
    TaskForceOperatorPolicy,
    TaskForceRegistryAgentSnapshot,
    TaskForceRequest,
    TaskForceState,
    TaskForceTrigger,
    build_task_force_plan,
    plan_task_force_transition,
    record_task_force_transition,
    start_task_force_lifecycle,
)

NOW = datetime(2026, 9, 9, 13, 0, tzinfo=UTC)


def _task_force_plan():
    request = TaskForceRequest(
        request_id="tf-request-001",
        system_id="balanced_v1",
        opportunity_id="opp-001",
        trigger=TaskForceTrigger.SPECIALIST_DISAGREEMENT,
        influence_scope=TaskForceInfluenceScope.ORCHESTRATION_ADVISORY,
        objective="Resolve a material disagreement.",
        question="Which interpretation is best grounded?",
        requested_by="professor",
        context_refs=("snapshot:001",),
        required_roles=("trend",),
        required_capabilities=("market_regime",),
        red_team_required=False,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    policy = TaskForceOperatorPolicy(
        policy_id="task-force-dev-policy",
        max_task_force_members=3,
        max_concurrent_task_forces=2,
        max_task_forces_per_period=6,
        max_total_budget_eur=Decimal("1.00"),
        max_budget_per_member_eur=Decimal("0.50"),
        max_total_calls=6,
        max_calls_per_member=2,
        max_retries_per_call=1,
        allowed_agent_states=(AgentState.ACTIVE, AgentState.ON_DEMAND),
        allowed_core_agent_ids=("palermo",),
        blocked_agent_ids=(),
    )
    entry = AgentRegistryEntry(
        agent_id="berlin",
        role=AgentRole.TREND_REGIME,
        state=AgentState.ACTIVE,
        prompt_version="v1",
        model_route="core_reasoning",
        allowed_tools=(),
        budget_policy_id="default",
        core=False,
    )
    member = TaskForceMemberAssignment(
        member_id="member-berlin",
        agent=TaskForceRegistryAgentSnapshot.from_registry_entry(entry),
        task_role="regime_analysis",
        capabilities=("market_regime",),
        selection_reasons=("required capability matched",),
        reputation_evidence_refs=("reputation:berlin:batch18",),
        tool_allowlist=(),
        member_budget_eur=Decimal("0.25"),
        max_calls=1,
    )
    return build_task_force_plan(
        task_force_id="task-force-001",
        request=request,
        policy=policy,
        members=(member,),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=20),
    )


def _transition(record, action, *, minute=1, reasons=("TEST_REASON",)):
    return plan_task_force_transition(
        record,
        action=action,
        reason_codes=reasons,
        evidence_refs=("evidence:test",),
        planned_at=NOW + timedelta(minutes=minute),
    )


def test_lifecycle_starts_planned_and_preserves_plan_identity():
    plan = _task_force_plan()
    record = start_task_force_lifecycle(plan)

    assert record.current_state is TaskForceState.PLANNED
    assert record.revision == 0
    assert record.request_fingerprint_sha256 == plan.request_fingerprint_sha256
    assert record.policy_fingerprint_sha256 == plan.policy_fingerprint_sha256
    assert record.composition_fingerprint_sha256 == plan.composition_fingerprint_sha256
    assert record.auto_execute is False
    assert record.registry_mutation is False
    assert record.risk_authority is False
    assert record.live_authority is False


def test_execution_approval_requires_explicit_operator_authorization():
    record = start_task_force_lifecycle(_task_force_plan())
    transition = _transition(record, TaskForceLifecycleAction.APPROVE_EXECUTION)

    assert transition.operator_authorization_required is True
    with pytest.raises(PermissionError, match="operator authorization"):
        record_task_force_transition(record, transition)

    approved = record_task_force_transition(
        record,
        transition,
        operator_authorized=True,
    )
    assert approved.current_state is TaskForceState.APPROVED_FOR_EXECUTION


def test_happy_path_planned_to_completed_is_explicit_and_revisioned():
    record = start_task_force_lifecycle(_task_force_plan())
    approval = _transition(record, TaskForceLifecycleAction.APPROVE_EXECUTION, minute=1)
    record = record_task_force_transition(record, approval, operator_authorized=True)

    start = _transition(record, TaskForceLifecycleAction.START_EXECUTION, minute=2)
    assert start.operator_authorization_required is False
    record = record_task_force_transition(record, start)

    complete = _transition(record, TaskForceLifecycleAction.COMPLETE, minute=3)
    record = record_task_force_transition(record, complete)

    assert record.current_state is TaskForceState.COMPLETED
    assert record.revision == 3
    assert record.transition_ids == (
        approval.transition_id,
        start.transition_id,
        complete.transition_id,
    )


def test_cannot_skip_approval_and_start_directly_from_planned():
    record = start_task_force_lifecycle(_task_force_plan())

    with pytest.raises(ValueError, match="not allowed from PLANNED"):
        _transition(record, TaskForceLifecycleAction.START_EXECUTION)


def test_expired_task_force_cannot_be_approved_or_started():
    record = start_task_force_lifecycle(_task_force_plan())

    with pytest.raises(ValueError, match="expired Task Force"):
        plan_task_force_transition(
            record,
            action=TaskForceLifecycleAction.APPROVE_EXECUTION,
            reason_codes=("OPERATOR_APPROVED",),
            evidence_refs=("operator:approval",),
            planned_at=record.expires_at,
        )

    approval = _transition(record, TaskForceLifecycleAction.APPROVE_EXECUTION, minute=1)
    approved = record_task_force_transition(record, approval, operator_authorized=True)
    with pytest.raises(ValueError, match="expired Task Force"):
        plan_task_force_transition(
            approved,
            action=TaskForceLifecycleAction.START_EXECUTION,
            reason_codes=("START",),
            evidence_refs=("runtime:start",),
            planned_at=approved.expires_at,
        )


def test_block_and_cancel_are_fail_safe_terminal_paths():
    planned = start_task_force_lifecycle(_task_force_plan())
    blocked_plan = _transition(planned, TaskForceLifecycleAction.BLOCK)
    blocked = record_task_force_transition(planned, blocked_plan)
    assert blocked.current_state is TaskForceState.BLOCKED

    planned = start_task_force_lifecycle(_task_force_plan())
    cancel_plan = _transition(planned, TaskForceLifecycleAction.CANCEL)
    cancelled = record_task_force_transition(planned, cancel_plan)
    assert cancelled.current_state is TaskForceState.CANCELLED


def test_running_can_fail_without_creating_any_authority():
    record = start_task_force_lifecycle(_task_force_plan())
    approval = _transition(record, TaskForceLifecycleAction.APPROVE_EXECUTION, minute=1)
    record = record_task_force_transition(record, approval, operator_authorized=True)
    start = _transition(record, TaskForceLifecycleAction.START_EXECUTION, minute=2)
    record = record_task_force_transition(record, start)
    failure = _transition(record, TaskForceLifecycleAction.FAIL, minute=3)
    record = record_task_force_transition(record, failure)

    assert record.current_state is TaskForceState.FAILED
    assert record.auto_execute is False
    assert record.registry_mutation is False
    assert record.risk_authority is False
    assert record.live_authority is False


def test_terminal_state_rejects_additional_transitions():
    record = start_task_force_lifecycle(_task_force_plan())
    cancel = _transition(record, TaskForceLifecycleAction.CANCEL)
    record = record_task_force_transition(record, cancel)

    with pytest.raises(ValueError, match="not allowed from CANCELLED"):
        _transition(record, TaskForceLifecycleAction.APPROVE_EXECUTION, minute=2)


def test_stale_transition_revision_is_rejected_after_state_advances():
    record = start_task_force_lifecycle(_task_force_plan())
    approval = _transition(record, TaskForceLifecycleAction.APPROVE_EXECUTION, minute=1)
    cancel = _transition(record, TaskForceLifecycleAction.CANCEL, minute=1)
    record = record_task_force_transition(record, approval, operator_authorized=True)

    with pytest.raises(ValueError, match="stale Task Force transition plan revision"):
        record_task_force_transition(record, cancel)


def test_transition_fingerprint_is_order_stable_for_audit_references():
    record = start_task_force_lifecycle(_task_force_plan())
    first = plan_task_force_transition(
        record,
        action=TaskForceLifecycleAction.BLOCK,
        reason_codes=("SECOND", "FIRST"),
        evidence_refs=("evidence:b", "evidence:a"),
        planned_at=NOW + timedelta(minutes=1),
    )
    second = plan_task_force_transition(
        record,
        action=TaskForceLifecycleAction.BLOCK,
        reason_codes=("FIRST", "SECOND"),
        evidence_refs=("evidence:a", "evidence:b"),
        planned_at=NOW + timedelta(minutes=1),
    )

    assert first.transition_id == second.transition_id
    assert first.reason_codes == ("FIRST", "SECOND")
    assert first.evidence_refs == ("evidence:a", "evidence:b")
