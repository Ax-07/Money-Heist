from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.agents.models import AgentRegistryEntry, AgentRole, AgentState
from app.agents.registry import AgentRegistry
from app.task_force.composition import (
    TaskForceCompositionPolicy,
    TaskForceReputationDimension,
    compose_task_force_members,
)
from app.task_force.composition_audit import (
    audit_task_force_composition,
    capture_task_force_composition_provenance,
)
from app.task_force.composition_closure import close_task_force_composition
from app.task_force.execution import (
    TaskForceMemberAnalysis,
    TaskForceMemberFinding,
    build_member_ai_gateway_request,
    build_task_force_execution_contract,
    validate_task_force_member_analysis,
)
from app.task_force.gates import (
    TaskForceCapacitySnapshot,
    TaskForceGateStatus,
    evaluate_task_force_plan,
)
from app.task_force.lifecycle import (
    TaskForceLifecycleAction,
    plan_task_force_transition,
    record_task_force_transition,
    start_task_force_lifecycle,
)
from app.task_force.models import (
    TaskForceInfluenceScope,
    TaskForceOperatorPolicy,
    TaskForceRequest,
    TaskForceState,
    TaskForceTrigger,
)

NOW = datetime(2026, 9, 9, 14, 0, tzinfo=UTC)


def _entry(agent_id: str, role: AgentRole) -> AgentRegistryEntry:
    return AgentRegistryEntry(
        agent_id=agent_id,
        role=role,
        state=AgentState.ACTIVE,
        prompt_version=f"{agent_id}-v1",
        model_route="core_reasoning",
        allowed_tools=(),
        core=False,
    )


def _registry() -> AgentRegistry:
    return AgentRegistry(
        (
            _entry("berlin", AgentRole.TREND_REGIME),
            _entry("tokyo", AgentRole.MOMENTUM),
        )
    )


def _request(**updates) -> TaskForceRequest:
    data = {
        "request_id": "tf-request-020c-001",
        "system_id": "balanced_v1",
        "opportunity_id": "12345678-1234-5678-1234-567812345678",
        "trigger": TaskForceTrigger.COMPLEX_OPPORTUNITY,
        "influence_scope": TaskForceInfluenceScope.ORCHESTRATION_ADVISORY,
        "objective": "Resolve a complex market disagreement.",
        "question": "Which interpretation is best supported by the supplied evidence?",
        "requested_by": "professor",
        "context_refs": ("snapshot:001", "features:001"),
        "required_roles": (),
        "required_capabilities": (),
        "red_team_required": False,
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=20),
    }
    data.update(updates)
    return TaskForceRequest(**data)


def _operator(**updates) -> TaskForceOperatorPolicy:
    data = {
        "policy_id": "tf-operator-v1",
        "max_task_force_members": 2,
        "max_concurrent_task_forces": 2,
        "max_task_forces_per_period": 5,
        "max_total_budget_eur": Decimal("1.0"),
        "max_budget_per_member_eur": Decimal("0.5"),
        "max_total_calls": 4,
        "max_calls_per_member": 2,
        "max_retries_per_call": 1,
        "allowed_agent_states": (AgentState.ACTIVE,),
        "allowed_core_agent_ids": (),
        "blocked_agent_ids": (),
    }
    data.update(updates)
    return TaskForceOperatorPolicy(**data)


def _composition() -> TaskForceCompositionPolicy:
    return TaskForceCompositionPolicy(
        composition_policy_id="tf-compose-v1",
        target_member_count=2,
        member_budget_eur=Decimal("0.4"),
        member_max_calls=2,
        state_preference=(AgentState.ACTIVE,),
        reputation_priority=(TaskForceReputationDimension.OOS_EVIDENCE,),
    )


def _prepared_bundle(*, request=None, operator=None, capacity=None):
    request = request or _request()
    operator = operator or _operator()
    registry = _registry()
    composition = _composition()
    result = compose_task_force_members(
        request,
        operator,
        composition,
        registry=registry,
    )
    provenance = capture_task_force_composition_provenance(
        result,
        request,
        operator,
        composition,
        registry=registry,
    )
    audit = audit_task_force_composition(
        provenance,
        result,
        request,
        operator,
        composition,
        registry=registry,
    )
    closure = close_task_force_composition(
        task_force_id="tf-020c-001",
        request=request,
        operator_policy=operator,
        result=result,
        provenance=provenance,
        audit=audit,
        created_at=NOW + timedelta(seconds=1),
        expires_at=request.expires_at,
    )
    plan_gate = evaluate_task_force_plan(
        request,
        closure.plan,
        operator,
        capacity=capacity
        or TaskForceCapacitySnapshot(
            period_id="2026-W37",
            concurrent_task_forces=0,
            task_forces_started=0,
        ),
        evaluated_at=NOW + timedelta(seconds=2),
    )
    lifecycle = start_task_force_lifecycle(closure.plan)
    approval = plan_task_force_transition(
        lifecycle,
        action=TaskForceLifecycleAction.APPROVE_EXECUTION,
        reason_codes=("OPERATOR_APPROVED",),
        evidence_refs=(plan_gate.audit_fingerprint_sha256,),
        planned_at=NOW + timedelta(seconds=3),
    )
    approved = record_task_force_transition(
        lifecycle,
        approval,
        operator_authorized=True,
    )
    return request, operator, closure, plan_gate, lifecycle, approved


def _contract(**updates):
    request, _operator_policy, closure, plan_gate, _planned, approved = _prepared_bundle()
    data = {
        "execution_run_id": "run-020c-001",
        "closure": closure,
        "request": request,
        "lifecycle": approved,
        "plan_gate": plan_gate,
        "max_output_tokens": 512,
        "prepared_at": NOW + timedelta(seconds=4),
    }
    data.update(updates)
    return build_task_force_execution_contract(**data)


def test_approved_allow_plan_builds_analysis_execution_contract():
    contract = _contract()
    assert contract.member_analysis_authorized is True
    assert contract.gateway_required is True
    assert contract.gateway_calls_performed is False
    assert len(contract.member_specs) == 2
    assert contract.lifecycle_revision == 1


def test_execution_contract_has_no_trading_registry_risk_or_live_authority():
    contract = _contract()
    assert contract.trade_proposal_authority is False
    assert contract.registry_mutation is False
    assert contract.risk_authority is False
    assert contract.live_authority is False
    assert all(spec.trade_proposal_authority is False for spec in contract.member_specs)
    assert all(spec.live_authority is False for spec in contract.member_specs)


def test_plan_gate_must_allow_before_execution_contract():
    request = _request()
    operator = _operator(max_concurrent_task_forces=1)
    capacity = TaskForceCapacitySnapshot(
        period_id="2026-W37",
        concurrent_task_forces=1,
        task_forces_started=0,
    )
    request, _operator_policy, closure, gate, _planned, approved = _prepared_bundle(
        request=request,
        operator=operator,
        capacity=capacity,
    )
    assert gate.status is TaskForceGateStatus.BLOCK
    with pytest.raises(PermissionError, match="must ALLOW"):
        build_task_force_execution_contract(
            execution_run_id="run-blocked",
            closure=closure,
            request=request,
            lifecycle=approved,
            plan_gate=gate,
            max_output_tokens=256,
            prepared_at=NOW + timedelta(seconds=4),
        )


def test_lifecycle_must_be_operator_approved():
    request, _operator, closure, gate, planned, _approved = _prepared_bundle()
    assert planned.current_state is TaskForceState.PLANNED
    with pytest.raises(PermissionError, match="APPROVED_FOR_EXECUTION"):
        build_task_force_execution_contract(
            execution_run_id="run-not-approved",
            closure=closure,
            request=request,
            lifecycle=planned,
            plan_gate=gate,
            max_output_tokens=256,
            prepared_at=NOW + timedelta(seconds=4),
        )


def test_stale_request_is_rejected_before_execution_contract():
    request, _operator, closure, gate, _planned, approved = _prepared_bundle()
    stale = TaskForceRequest(
        **{**request.model_dump(), "question": "A different material question"}
    )
    with pytest.raises(ValueError, match="request fingerprint is stale"):
        build_task_force_execution_contract(
            execution_run_id="run-stale",
            closure=closure,
            request=stale,
            lifecycle=approved,
            plan_gate=gate,
            max_output_tokens=256,
            prepared_at=NOW + timedelta(seconds=4),
        )


def test_expired_task_force_cannot_prepare_execution_contract():
    request, _operator, closure, gate, _planned, approved = _prepared_bundle()
    with pytest.raises(ValueError, match="expired"):
        build_task_force_execution_contract(
            execution_run_id="run-expired",
            closure=closure,
            request=request,
            lifecycle=approved,
            plan_gate=gate,
            max_output_tokens=256,
            prepared_at=request.expires_at,
        )


def test_gateway_request_ids_are_deterministic_per_execution_run():
    first = _contract()
    second = _contract()
    third = _contract(execution_run_id="run-020c-002")
    assert [item.gateway_request_id for item in first.member_specs] == [
        item.gateway_request_id for item in second.member_specs
    ]
    assert [item.gateway_request_id for item in first.member_specs] != [
        item.gateway_request_id for item in third.member_specs
    ]


def test_gateway_request_uses_registry_route_prompt_and_explicit_output_cap():
    contract = _contract()
    spec = contract.member_specs[0]
    gateway_request = build_member_ai_gateway_request(
        contract,
        member_id=spec.member_id,
        context_payload={"price": "62000", "regime": "volatile"},
    )
    assert gateway_request.agent_id == spec.agent_id
    assert gateway_request.prompt_version == spec.prompt_version
    assert gateway_request.model_route == spec.model_route
    assert gateway_request.max_output_tokens == 512
    assert gateway_request.request_id == spec.gateway_request_id
    assert gateway_request.opportunity_id is not None


def test_gateway_input_is_canonical_and_contains_grounding_context():
    contract = _contract()
    spec = contract.member_specs[0]
    first = build_member_ai_gateway_request(
        contract,
        member_id=spec.member_id,
        context_payload={"z": 2, "a": {"b": 1}},
    )
    second = build_member_ai_gateway_request(
        contract,
        member_id=spec.member_id,
        context_payload={"a": {"b": 1}, "z": 2},
    )
    assert first.input_text == second.input_text
    payload = json.loads(first.input_text)
    assert payload["context"] == {"a": {"b": 1}, "z": 2}
    assert payload["context_refs"] == list(contract.context_refs)
    assert "Do not create orders" in first.instructions


def test_gateway_request_requires_materialized_context_and_known_member():
    contract = _contract()
    spec = contract.member_specs[0]
    with pytest.raises(ValueError, match="must not be empty"):
        build_member_ai_gateway_request(contract, member_id=spec.member_id, context_payload={})
    with pytest.raises(ValueError, match="not part"):
        build_member_ai_gateway_request(
            contract,
            member_id="member:unknown",
            context_payload={"snapshot": "ok"},
        )


def test_member_analysis_identity_is_validated_fail_closed():
    contract = _contract()
    spec = contract.member_specs[0]
    analysis = TaskForceMemberAnalysis(
        task_force_id=contract.task_force_id,
        execution_run_id=contract.execution_run_id,
        member_id=spec.member_id,
        agent_id=spec.agent_id,
        answer="Evidence favors the stated regime hypothesis.",
        findings=(
            TaskForceMemberFinding(
                finding_id="finding-1",
                summary="Observed evidence is internally consistent.",
                evidence_refs=("snapshot:001",),
            ),
        ),
        confidence=Decimal("0.7"),
    )
    assert validate_task_force_member_analysis(contract, analysis) is analysis
    wrong = TaskForceMemberAnalysis(
        **{**analysis.model_dump(), "agent_id": "tokyo" if spec.agent_id != "tokyo" else "berlin"}
    )
    with pytest.raises(ValueError, match="agent_id"):
        validate_task_force_member_analysis(contract, wrong)


def test_member_analysis_rejects_authority_escalation_and_duplicate_findings():
    contract = _contract()
    spec = contract.member_specs[0]
    base = {
        "task_force_id": contract.task_force_id,
        "execution_run_id": contract.execution_run_id,
        "member_id": spec.member_id,
        "agent_id": spec.agent_id,
        "answer": "Grounded advisory answer.",
        "confidence": Decimal("0.5"),
    }
    with pytest.raises(Exception):
        TaskForceMemberAnalysis(**{**base, "live_authority": True})
    finding = TaskForceMemberFinding(
        finding_id="same",
        summary="Grounded finding.",
        evidence_refs=("snapshot:001",),
    )
    with pytest.raises(ValueError, match="unique finding_id"):
        TaskForceMemberAnalysis(**{**base, "findings": (finding, finding)})
