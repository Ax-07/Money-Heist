from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents.models import AgentRole, AgentState
from app.task_force.aggregation import (
    aggregate_task_force_execution,
    task_force_execution_fingerprint,
)
from app.task_force.composition_closure import task_force_plan_fingerprint
from app.task_force.execution import (
    TaskForceExecutionContract,
    TaskForceMemberAnalysis,
    TaskForceMemberExecutionSpec,
    TaskForceMemberFinding,
)
from app.task_force.execution_runtime import (
    TaskForceExecutionRunStatus,
    TaskForceExecutionUsageSnapshot,
    TaskForceMemberExecutionRecord,
    TaskForceMemberUsageSnapshot,
    TaskForceMultiMemberExecution,
    zero_task_force_execution_usage,
)
from app.task_force.models import (
    TaskForceInfluenceScope,
    TaskForceMemberAssignment,
    TaskForcePlan,
    TaskForceRegistryAgentSnapshot,
    TaskForceRequest,
    TaskForceTrigger,
    task_force_request_fingerprint,
)


NOW = datetime(2026, 9, 9, 14, 0, tzinfo=UTC)


def _member(
    member_id: str,
    agent_id: str,
    role: AgentRole,
) -> TaskForceMemberAssignment:
    agent = TaskForceRegistryAgentSnapshot(
        agent_id=agent_id,
        role=role,
        state=AgentState.ACTIVE,
        prompt_version="v1",
        model_route="route-default",
        allowed_tools=(),
        budget_policy_id="default",
        core=role is AgentRole.RED_TEAM,
    )
    return TaskForceMemberAssignment(
        member_id=member_id,
        agent=agent,
        task_role=role.value,
        capabilities=(role.value,),
        selection_reasons=("ROLE_MATCH",),
        member_budget_eur=Decimal("1"),
        max_calls=1,
    )


def _bundle(
    *,
    red_team_required: bool = False,
    include_red_team: bool = False,
) -> tuple[
    TaskForceRequest,
    TaskForcePlan,
    TaskForceExecutionContract,
    TaskForceMultiMemberExecution,
]:
    request = TaskForceRequest(
        request_id="req-1",
        system_id="system-1",
        trigger=TaskForceTrigger.DEEP_DIVE,
        influence_scope=TaskForceInfluenceScope.ORCHESTRATION_ADVISORY,
        objective="Investigate the opportunity",
        question="What matters most?",
        requested_by="professor",
        context_refs=("snapshot:1",),
        red_team_required=red_team_required,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    members = [_member("m-berlin", "berlin", AgentRole.TREND_REGIME)]
    if include_red_team:
        members.append(_member("m-palermo", "palermo", AgentRole.RED_TEAM))
    plan = TaskForcePlan(
        task_force_id="tf-1",
        request_id=request.request_id,
        request_fingerprint_sha256=task_force_request_fingerprint(request),
        policy_id="policy-1",
        policy_fingerprint_sha256="a" * 64,
        members=tuple(members),
        total_budget_eur=Decimal(len(members)),
        total_call_limit=len(members),
        composition_fingerprint_sha256="b" * 64,
        created_at=NOW,
        expires_at=request.expires_at,
    )
    specs = tuple(
        TaskForceMemberExecutionSpec(
            member_id=member.member_id,
            agent_id=member.agent.agent_id,
            task_role=member.task_role,
            capabilities=member.capabilities,
            prompt_version=member.agent.prompt_version,
            model_route=member.agent.model_route,
            gateway_request_id=uuid4(),
            max_output_tokens=500,
            member_budget_eur=member.member_budget_eur,
            member_call_limit=member.max_calls,
        )
        for member in members
    )
    contract = TaskForceExecutionContract(
        execution_run_id="run-1",
        task_force_id=plan.task_force_id,
        request_id=request.request_id,
        system_id=request.system_id,
        opportunity_id=None,
        influence_scope=request.influence_scope,
        objective=request.objective,
        question=request.question,
        context_refs=request.context_refs,
        integration_fingerprint_sha256="c" * 64,
        plan_fingerprint_sha256=task_force_plan_fingerprint(plan),
        plan_gate_fingerprint_sha256="d" * 64,
        lifecycle_revision=1,
        approval_transition_id="e" * 64,
        member_specs=specs,
        prepared_at=NOW + timedelta(minutes=1),
        expires_at=request.expires_at,
        execution_contract_fingerprint_sha256="f" * 64,
    )
    records = tuple(_record(contract, spec, index) for index, spec in enumerate(specs))
    usage_before = zero_task_force_execution_usage(contract)
    usage_after = TaskForceExecutionUsageSnapshot(
        task_force_id=contract.task_force_id,
        spent_total_eur=Decimal("0.10") * len(specs),
        used_total_calls=len(specs),
        members=tuple(
            TaskForceMemberUsageSnapshot(
                member_id=spec.member_id,
                agent_id=spec.agent_id,
                spent_eur=Decimal("0.10"),
                used_calls=1,
            )
            for spec in specs
        ),
    )
    execution = TaskForceMultiMemberExecution(
        task_force_id=contract.task_force_id,
        execution_run_id=contract.execution_run_id,
        execution_contract_fingerprint_sha256=(
            contract.execution_contract_fingerprint_sha256
        ),
        started_at=NOW + timedelta(minutes=2),
        status=TaskForceExecutionRunStatus.COMPLETED,
        expected_member_count=len(specs),
        completed_member_count=len(records),
        member_records=records,
        usage_before=usage_before,
        usage_after=usage_after,
        gateway_calls_performed=True,
        cost_accounting_complete=True,
        aggregation_ready=True,
    )
    return request, plan, contract, execution


def _record(
    contract: TaskForceExecutionContract,
    spec: TaskForceMemberExecutionSpec,
    index: int,
) -> TaskForceMemberExecutionRecord:
    common_uncertainty = "Macro catalyst remains uncertain"
    analysis = TaskForceMemberAnalysis(
        task_force_id=contract.task_force_id,
        execution_run_id=contract.execution_run_id,
        member_id=spec.member_id,
        agent_id=spec.agent_id,
        answer=f"Answer from {spec.agent_id}",
        findings=(
            TaskForceMemberFinding(
                finding_id=f"finding-{index}",
                summary=f"Finding from {spec.agent_id}",
                evidence_refs=(f"snapshot:{index}",),
            ),
        ),
        uncertainties=(common_uncertainty,),
        follow_up_questions=(f"Follow up {index}?",),
        confidence=Decimal("0.7") + Decimal(index) / Decimal("10"),
    )
    return TaskForceMemberExecutionRecord(
        member_id=spec.member_id,
        agent_id=spec.agent_id,
        gateway_request_id=str(spec.gateway_request_id),
        compute_quote_fingerprint_sha256="1" * 64,
        compute_gate_fingerprint_sha256="2" * 64,
        route_id="route-default",
        model_id="mock-model",
        provider_request_id=f"provider-{index}",
        attempts=1,
        usage_record_count=1,
        actual_cost_eur=Decimal("0.10"),
        latency_ms_total=10,
        analysis=analysis,
    )


def _aggregate(
    bundle: tuple[
        TaskForceRequest,
        TaskForcePlan,
        TaskForceExecutionContract,
        TaskForceMultiMemberExecution,
    ],
    *,
    at: datetime | None = None,
):
    request, plan, contract, execution = bundle
    return aggregate_task_force_execution(
        contract,
        execution,
        plan,
        request,
        aggregated_at=at or NOW + timedelta(minutes=3),
    )


def test_aggregation_preserves_member_order_and_finding_provenance():
    report = _aggregate(_bundle(include_red_team=True))
    assert [member.member_id for member in report.members] == ["m-berlin", "m-palermo"]
    assert [finding.member_id for finding in report.findings] == ["m-berlin", "m-palermo"]
    assert report.findings[0].evidence_refs == ("snapshot:0",)


def test_aggregation_deduplicates_cross_member_uncertainty_without_semantic_vote():
    report = _aggregate(_bundle(include_red_team=True))
    assert report.uncertainties == ("Macro catalyst remains uncertain",)
    assert report.semantic_consensus_computed is False
    assert report.aggregate_confidence_computed is False


def test_optional_red_team_can_be_absent():
    report = _aggregate(_bundle(red_team_required=False, include_red_team=False))
    assert report.red_team_required is False
    assert report.red_team_present is False
    assert report.red_team_contributions == ()


def test_required_red_team_is_exposed_as_separate_contribution():
    report = _aggregate(_bundle(red_team_required=True, include_red_team=True))
    assert report.red_team_required is True
    assert report.red_team_present is True
    assert report.red_team_contributions[0].agent_id == "palermo"
    assert report.red_team_contributions[0].finding_ids == ("finding-1",)


def test_required_red_team_missing_fails_closed():
    with pytest.raises(ValueError, match="requires Red Team"):
        _aggregate(_bundle(red_team_required=True, include_red_team=False))


def test_non_completed_execution_cannot_be_aggregated():
    request, plan, contract, execution = _bundle()
    execution = execution.model_copy(
        update={
            "status": TaskForceExecutionRunStatus.BLOCKED,
            "aggregation_ready": False,
        }
    )
    with pytest.raises(PermissionError, match="only completed"):
        aggregate_task_force_execution(
            contract,
            execution,
            plan,
            request,
            aggregated_at=NOW + timedelta(minutes=3),
        )


def test_stale_execution_contract_fingerprint_is_rejected():
    request, plan, contract, execution = _bundle()
    execution = execution.model_copy(
        update={"execution_contract_fingerprint_sha256": "0" * 64}
    )
    with pytest.raises(ValueError, match="contract fingerprint is stale"):
        aggregate_task_force_execution(
            contract,
            execution,
            plan,
            request,
            aggregated_at=NOW + timedelta(minutes=3),
        )


def test_stale_plan_fingerprint_is_rejected():
    request, plan, contract, execution = _bundle()
    contract = contract.model_copy(update={"plan_fingerprint_sha256": "0" * 64})
    with pytest.raises(ValueError, match="plan fingerprint is stale"):
        aggregate_task_force_execution(
            contract,
            execution,
            plan,
            request,
            aggregated_at=NOW + timedelta(minutes=3),
        )


def test_stale_request_fingerprint_is_rejected():
    request, plan, contract, execution = _bundle()
    request = request.model_copy(update={"objective": "Changed objective"})
    with pytest.raises(ValueError, match="request fingerprint is stale"):
        aggregate_task_force_execution(
            contract,
            execution,
            plan,
            request,
            aggregated_at=NOW + timedelta(minutes=3),
        )


def test_member_order_change_is_rejected():
    request, plan, contract, execution = _bundle(include_red_team=True)
    execution = execution.model_copy(
        update={"member_records": tuple(reversed(execution.member_records))}
    )
    with pytest.raises(ValueError, match="member order or identity"):
        aggregate_task_force_execution(
            contract,
            execution,
            plan,
            request,
            aggregated_at=NOW + timedelta(minutes=3),
        )


def test_report_fingerprint_is_stable_across_aggregation_timestamps():
    bundle = _bundle(include_red_team=True)
    first = _aggregate(bundle, at=NOW + timedelta(minutes=3))
    second = _aggregate(bundle, at=NOW + timedelta(minutes=4))
    assert first.report_fingerprint_sha256 == second.report_fingerprint_sha256
    assert first.execution_fingerprint_sha256 == task_force_execution_fingerprint(bundle[3])


def test_expired_task_force_cannot_create_new_report():
    bundle = _bundle()
    with pytest.raises(PermissionError, match="expired Task Force"):
        _aggregate(bundle, at=NOW + timedelta(hours=1))


def test_report_remains_advisory_with_no_trade_risk_registry_or_live_authority():
    report = _aggregate(_bundle(include_red_team=True))
    assert report.advisory_only is True
    assert report.trade_proposal_authority is False
    assert report.registry_mutation is False
    assert report.risk_authority is False
    assert report.live_authority is False
    assert report.member_actual_cost_eur == Decimal("0.20")
    assert report.member_attempt_count == 2
