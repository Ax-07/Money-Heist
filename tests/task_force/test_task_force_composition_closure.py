from __future__ import annotations

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
    TaskForceCompositionAudit,
    TaskForceCompositionAuditStatus,
    audit_task_force_composition,
    capture_task_force_composition_provenance,
)
from app.task_force.composition_closure import (
    close_task_force_composition,
    task_force_plan_fingerprint,
)
from app.task_force.models import (
    TaskForceInfluenceScope,
    TaskForceOperatorPolicy,
    TaskForceRequest,
    TaskForceState,
    TaskForceTrigger,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def _entry(agent_id: str, role: AgentRole, state: AgentState):
    return AgentRegistryEntry(
        agent_id=agent_id,
        role=role,
        state=state,
        prompt_version="v1",
        model_route="core_reasoning",
        allowed_tools=(),
        core=False,
    )


def _registry():
    return AgentRegistry(
        (
            _entry("berlin", AgentRole.TREND_REGIME, AgentState.ACTIVE),
            _entry("tokyo", AgentRole.MOMENTUM, AgentState.ACTIVE),
        )
    )


def _operator():
    return TaskForceOperatorPolicy(
        policy_id="tf-operator-v1",
        max_task_force_members=2,
        max_concurrent_task_forces=2,
        max_task_forces_per_period=5,
        max_total_budget_eur=Decimal("1"),
        max_budget_per_member_eur=Decimal("0.5"),
        max_total_calls=6,
        max_calls_per_member=3,
        max_retries_per_call=1,
        allowed_agent_states=(AgentState.ACTIVE,),
        allowed_core_agent_ids=(),
        blocked_agent_ids=(),
    )


def _composition(**updates):
    data = {
        "composition_policy_id": "tf-compose-v1",
        "target_member_count": 1,
        "member_budget_eur": Decimal("0.2"),
        "member_max_calls": 2,
        "state_preference": (AgentState.ACTIVE,),
        "reputation_priority": (TaskForceReputationDimension.OOS_EVIDENCE,),
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


def _fresh_bundle(*, request=None, composition=None):
    request = request or _request()
    operator = _operator()
    composition = composition or _composition()
    registry = _registry()
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
    return request, operator, composition, result, provenance, audit


def _close(**overrides):
    request, operator, _composition_policy, result, provenance, audit = _fresh_bundle()
    data = {
        "task_force_id": "tf-001",
        "request": request,
        "operator_policy": operator,
        "result": result,
        "provenance": provenance,
        "audit": audit,
        "created_at": NOW + timedelta(seconds=1),
        "expires_at": request.expires_at,
    }
    data.update(overrides)
    return close_task_force_composition(**data)


def test_fresh_complete_composition_closes_into_planned_plan():
    closure = _close()
    assert closure.plan.state is TaskForceState.PLANNED
    assert closure.plan.operator_authorization_required is True
    assert closure.manifest.composition_audit_status is TaskForceCompositionAuditStatus.FRESH
    assert closure.manifest.composition_complete is True


def test_closure_has_no_execution_registry_risk_or_live_authority():
    closure = _close()
    assert closure.execution_authorized is False
    assert closure.registry_mutation is False
    assert closure.risk_authority is False
    assert closure.live_authority is False
    assert closure.manifest.execution_authorized is False
    assert closure.manifest.live_authority is False


def test_closure_binds_exact_members_and_composition_fingerprints():
    closure = _close()
    assert closure.manifest.member_agent_ids == tuple(
        sorted(member.agent.agent_id for member in closure.plan.members)
    )
    assert closure.manifest.request_fingerprint_sha256 == (
        closure.plan.request_fingerprint_sha256
    )
    assert closure.manifest.operator_policy_fingerprint_sha256 == (
        closure.plan.policy_fingerprint_sha256
    )
    assert closure.manifest.plan_composition_fingerprint_sha256 == (
        closure.plan.composition_fingerprint_sha256
    )


def test_plan_fingerprint_is_deterministic_and_exact():
    first = _close()
    second = _close()
    assert first.manifest.plan_fingerprint_sha256 == second.manifest.plan_fingerprint_sha256
    assert first.manifest.plan_fingerprint_sha256 == task_force_plan_fingerprint(first.plan)
    assert first.manifest.integration_fingerprint_sha256 == (
        second.manifest.integration_fingerprint_sha256
    )


def test_task_force_id_changes_exact_plan_and_integration_fingerprint():
    first = _close()
    second = _close(task_force_id="tf-002")
    assert first.manifest.plan_fingerprint_sha256 != second.manifest.plan_fingerprint_sha256
    assert first.manifest.integration_fingerprint_sha256 != (
        second.manifest.integration_fingerprint_sha256
    )


def test_incomplete_composition_cannot_close():
    request = _request(required_roles=(AgentRole.RED_TEAM.value,))
    request, operator, _policy, result, provenance, audit = _fresh_bundle(request=request)
    assert result.complete is False
    with pytest.raises(ValueError, match="incomplete"):
        close_task_force_composition(
            task_force_id="tf-001",
            request=request,
            operator_policy=operator,
            result=result,
            provenance=provenance,
            audit=audit,
            created_at=NOW + timedelta(seconds=1),
            expires_at=request.expires_at,
        )


def test_stale_audit_cannot_close():
    request, operator, policy, result, provenance, _audit = _fresh_bundle()
    changed_request = TaskForceRequest(
        **{**request.model_dump(), "question": "A materially different question"}
    )
    audit = audit_task_force_composition(
        provenance,
        result,
        changed_request,
        operator,
        policy,
        registry=_registry(),
    )
    assert audit.status is TaskForceCompositionAuditStatus.STALE
    with pytest.raises(ValueError, match="stale"):
        close_task_force_composition(
            task_force_id="tf-001",
            request=request,
            operator_policy=operator,
            result=result,
            provenance=provenance,
            audit=audit,
            created_at=NOW + timedelta(seconds=1),
            expires_at=request.expires_at,
        )


def test_tampered_fresh_audit_source_bundle_is_rejected():
    request, operator, _policy, result, provenance, audit = _fresh_bundle()
    tampered = TaskForceCompositionAudit(
        **{
            **audit.model_dump(),
            "current_source_bundle_fingerprint_sha256": "a" * 64,
        }
    )
    with pytest.raises(ValueError, match="current source bundle"):
        close_task_force_composition(
            task_force_id="tf-001",
            request=request,
            operator_policy=operator,
            result=result,
            provenance=provenance,
            audit=tampered,
            created_at=NOW + timedelta(seconds=1),
            expires_at=request.expires_at,
        )


def test_closure_cannot_predate_request():
    request, operator, _policy, result, provenance, audit = _fresh_bundle()
    with pytest.raises(ValueError, match="predate"):
        close_task_force_composition(
            task_force_id="tf-001",
            request=request,
            operator_policy=operator,
            result=result,
            provenance=provenance,
            audit=audit,
            created_at=NOW - timedelta(seconds=1),
            expires_at=request.expires_at,
        )


def test_closure_expiry_cannot_exceed_request_expiry():
    request, operator, _policy, result, provenance, audit = _fresh_bundle()
    with pytest.raises(ValueError, match="cannot exceed request expiry"):
        close_task_force_composition(
            task_force_id="tf-001",
            request=request,
            operator_policy=operator,
            result=result,
            provenance=provenance,
            audit=audit,
            created_at=NOW + timedelta(seconds=1),
            expires_at=request.expires_at + timedelta(seconds=1),
        )


def test_manifest_is_frozen_and_rejects_extra_authority_fields():
    closure = _close()
    with pytest.raises(Exception):
        closure.manifest.live_authority = True
    with pytest.raises(Exception):
        closure.__class__(
            manifest=closure.manifest,
            plan=closure.plan,
            execution_authorized=False,
            broker_authority=True,
        )
