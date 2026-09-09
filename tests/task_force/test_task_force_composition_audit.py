from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.agents.models import AgentRegistryEntry, AgentRole, AgentState
from app.agents.registry import AgentRegistry
from app.task_force.composition import (
    TaskForceCapabilityProfile,
    TaskForceCompositionPolicy,
    TaskForceReputationDimension,
    compose_task_force_members,
)
from app.task_force.composition_audit import (
    TaskForceCompositionAuditStatus,
    audit_task_force_composition,
    capture_task_force_composition_provenance,
    task_force_capability_profiles_fingerprint,
    task_force_registry_fingerprint,
    task_force_reputation_evidence_fingerprint,
)
from app.task_force.models import (
    TaskForceInfluenceScope,
    TaskForceOperatorPolicy,
    TaskForceRequest,
    TaskForceTrigger,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def _entry(
    agent_id: str,
    role: AgentRole,
    state: AgentState,
    *,
    core: bool = False,
    prompt_version: str = "v1",
):
    return AgentRegistryEntry(
        agent_id=agent_id,
        role=role,
        state=state,
        prompt_version=prompt_version,
        model_route="core_reasoning",
        allowed_tools=(),
        core=core,
    )


def _registry(*, berlin_prompt: str = "v1", include_extra: bool = False):
    entries = [
        _entry(
            "berlin",
            AgentRole.TREND_REGIME,
            AgentState.ACTIVE,
            prompt_version=berlin_prompt,
        ),
        _entry("tokyo", AgentRole.MOMENTUM, AgentState.ACTIVE),
        _entry("rio", AgentRole.DERIVATIVES_POSITIONING, AgentState.ON_DEMAND),
    ]
    if include_extra:
        entries.append(_entry("nairobi", AgentRole.MARKET_STRUCTURE, AgentState.PROBATION))
    return AgentRegistry(tuple(entries))


def _operator(**updates):
    data = {
        "policy_id": "tf-operator-v1",
        "max_task_force_members": 3,
        "max_concurrent_task_forces": 2,
        "max_task_forces_per_period": 5,
        "max_total_budget_eur": Decimal("2"),
        "max_budget_per_member_eur": Decimal("0.5"),
        "max_total_calls": 9,
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
        "target_member_count": 1,
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


def _advisory(agent_id: str, *, oos: int, economic: str):
    reputation = SimpleNamespace(
        call_count=20,
        oos_ablation_comparison_count=oos,
        marginal_economic_net=_metric(economic),
        drawdown_reduction_pct=_metric("0.02"),
        average_cost_eur=_metric("0.01"),
        average_latency_ms=_metric("100"),
    )
    recommendation = SimpleNamespace(
        recommended_state=AgentState.ACTIVE,
        evidence_sufficiency=SimpleNamespace(value="SUFFICIENT"),
        action=SimpleNamespace(value="HOLD"),
    )
    material = f"{agent_id}:{oos}:{economic}"
    return SimpleNamespace(
        agent_id=agent_id,
        audit_fingerprint_sha256=hashlib.sha256(material.encode()).hexdigest(),
        reputation=reputation,
        recommendation=recommendation,
    )


def _capture(
    *,
    request=None,
    operator=None,
    composition=None,
    registry=None,
    capabilities=(),
    reports=(),
):
    request = request or _request()
    operator = operator or _operator()
    composition = composition or _composition()
    registry = registry or _registry()
    result = compose_task_force_members(
        request,
        operator,
        composition,
        registry=registry,
        capability_profiles=capabilities,
        reputation_reports=reports,
    )
    provenance = capture_task_force_composition_provenance(
        result,
        request,
        operator,
        composition,
        registry=registry,
        capability_profiles=capabilities,
        reputation_reports=reports,
    )
    return result, provenance, request, operator, composition, registry


def test_fresh_audit_reproduces_original_composition():
    result, provenance, request, operator, composition, registry = _capture()
    audit = audit_task_force_composition(
        provenance,
        result,
        request,
        operator,
        composition,
        registry=registry,
    )
    assert audit.status is TaskForceCompositionAuditStatus.FRESH
    assert audit.stale is False
    assert audit.reason_codes == ()
    assert audit.original_result_fingerprint_sha256 == audit.recomposed_result_fingerprint_sha256


def test_material_request_change_is_stale():
    result, provenance, request, operator, composition, registry = _capture()
    changed = TaskForceRequest(**{**request.model_dump(), "question": "Changed question"})
    audit = audit_task_force_composition(
        provenance,
        result,
        changed,
        operator,
        composition,
        registry=registry,
    )
    assert audit.status is TaskForceCompositionAuditStatus.STALE
    assert "REQUEST_CHANGED" in audit.reason_codes
    assert "RECOMPOSED_RESULT_CHANGED" in audit.reason_codes


def test_operator_policy_change_is_stale_even_if_members_stay_same():
    result, provenance, request, operator, composition, registry = _capture()
    changed = _operator(max_concurrent_task_forces=7)
    audit = audit_task_force_composition(
        provenance,
        result,
        request,
        changed,
        composition,
        registry=registry,
    )
    assert "OPERATOR_POLICY_CHANGED" in audit.reason_codes
    assert audit.stale is True


def test_composition_policy_change_is_stale():
    result, provenance, request, operator, composition, registry = _capture()
    changed = _composition(member_max_calls=1)
    audit = audit_task_force_composition(
        provenance,
        result,
        request,
        operator,
        changed,
        registry=registry,
    )
    assert "COMPOSITION_POLICY_CHANGED" in audit.reason_codes
    assert "RECOMPOSED_RESULT_CHANGED" in audit.reason_codes


def test_unselected_registry_agent_change_still_marks_stale():
    reports = (
        _advisory("berlin", oos=10, economic="2"),
        _advisory("tokyo", oos=1, economic="1"),
    )
    result, provenance, request, operator, composition, registry = _capture(
        reports=reports
    )
    assert result.members[0].agent.agent_id == "berlin"
    changed_registry = _registry(include_extra=True)
    audit = audit_task_force_composition(
        provenance,
        result,
        request,
        operator,
        composition,
        registry=changed_registry,
        reputation_reports=reports,
    )
    assert "REGISTRY_CHANGED" in audit.reason_codes
    assert audit.stale is True


def test_registry_contract_change_is_stale_even_when_agent_id_is_same():
    result, provenance, request, operator, composition, registry = _capture()
    changed_registry = _registry(berlin_prompt="v2")
    audit = audit_task_force_composition(
        provenance,
        result,
        request,
        operator,
        composition,
        registry=changed_registry,
    )
    assert "REGISTRY_CHANGED" in audit.reason_codes
    assert audit.stale is True


def test_capability_profile_change_is_stale():
    capabilities = (
        TaskForceCapabilityProfile(agent_id="rio", capabilities=("derivatives",)),
    )
    result, provenance, request, operator, composition, registry = _capture(
        capabilities=capabilities
    )
    changed = (
        TaskForceCapabilityProfile(
            agent_id="rio",
            capabilities=("derivatives", "liquidations"),
        ),
    )
    audit = audit_task_force_composition(
        provenance,
        result,
        request,
        operator,
        composition,
        registry=registry,
        capability_profiles=changed,
    )
    assert "CAPABILITY_PROFILES_CHANGED" in audit.reason_codes


def test_reputation_change_is_stale_and_can_change_member():
    reports = (
        _advisory("berlin", oos=10, economic="2"),
        _advisory("tokyo", oos=1, economic="1"),
    )
    result, provenance, request, operator, composition, registry = _capture(
        reports=reports
    )
    changed_reports = (
        _advisory("berlin", oos=1, economic="2"),
        _advisory("tokyo", oos=20, economic="1"),
    )
    audit = audit_task_force_composition(
        provenance,
        result,
        request,
        operator,
        composition,
        registry=registry,
        reputation_reports=changed_reports,
    )
    assert "REPUTATION_EVIDENCE_CHANGED" in audit.reason_codes
    assert "RECOMPOSED_RESULT_CHANGED" in audit.reason_codes
    assert audit.original_member_agent_ids != audit.recomposed_member_agent_ids


def test_source_fingerprints_are_order_independent_for_set_like_inputs():
    registry_a = AgentRegistry(
        (
            _entry("berlin", AgentRole.TREND_REGIME, AgentState.ACTIVE),
            _entry("tokyo", AgentRole.MOMENTUM, AgentState.ACTIVE),
        )
    )
    registry_b = AgentRegistry(tuple(reversed(registry_a.list())))
    assert task_force_registry_fingerprint(registry_a) == task_force_registry_fingerprint(
        registry_b
    )

    profiles_a = (
        TaskForceCapabilityProfile(agent_id="berlin", capabilities=("trend",)),
        TaskForceCapabilityProfile(agent_id="tokyo", capabilities=("momentum",)),
    )
    assert task_force_capability_profiles_fingerprint(
        profiles_a
    ) == task_force_capability_profiles_fingerprint(tuple(reversed(profiles_a)))

    reports_a = (
        _advisory("berlin", oos=2, economic="1"),
        _advisory("tokyo", oos=3, economic="2"),
    )
    assert task_force_reputation_evidence_fingerprint(
        reports_a
    ) == task_force_reputation_evidence_fingerprint(tuple(reversed(reports_a)))


def test_provenance_capture_rejects_result_from_different_sources():
    request = _request()
    operator = _operator()
    composition = _composition()
    registry = _registry()
    result = compose_task_force_members(
        request,
        operator,
        composition,
        registry=registry,
    )
    changed = _composition(member_max_calls=1)
    with pytest.raises(ValueError, match="cannot be reproduced"):
        capture_task_force_composition_provenance(
            result,
            request,
            operator,
            changed,
            registry=registry,
        )


def test_audit_rejects_original_result_not_bound_to_provenance():
    result, provenance, request, operator, composition, registry = _capture()
    other = compose_task_force_members(
        request,
        operator,
        _composition(member_max_calls=1),
        registry=registry,
    )
    with pytest.raises(ValueError, match="does not match captured provenance"):
        audit_task_force_composition(
            provenance,
            other,
            request,
            operator,
            composition,
            registry=registry,
        )


def test_audit_and_provenance_never_grant_execution_or_live_authority():
    result, provenance, request, operator, composition, registry = _capture()
    audit = audit_task_force_composition(
        provenance,
        result,
        request,
        operator,
        composition,
        registry=registry,
    )
    assert provenance.aggregate_reputation_score is None
    assert provenance.registry_mutation is False
    assert provenance.risk_authority is False
    assert provenance.live_authority is False
    assert audit.execution_authorized is False
    assert audit.registry_mutation is False
    assert audit.risk_authority is False
    assert audit.live_authority is False
