from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents.models import AgentRegistryEntry, AgentRole, AgentState
from app.agents.registry import AgentRegistry
from app.intelligence.ai_gateway.models import AIGatewayResult, AIUsageRecord
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
from app.task_force.execution import TaskForceMemberAnalysis, build_task_force_execution_contract
from app.task_force.execution_runtime import (
    TaskForceExecutionFailureStage,
    TaskForceExecutionRunStatus,
    TaskForceExecutionUsageSnapshot,
    TaskForceMemberComputeQuote,
    TaskForceMemberUsageSnapshot,
    execute_task_force_members,
    zero_task_force_execution_usage,
)
from app.task_force.gates import TaskForceCapacitySnapshot, evaluate_task_force_plan
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
    TaskForceTrigger,
)

NOW = datetime(2026, 9, 9, 14, 30, tzinfo=UTC)
Responder = Callable[[object], AIGatewayResult[TaskForceMemberAnalysis]]


class FakeGateway:
    def __init__(self, responders: list[Responder | Exception]):
        self.responders = list(responders)
        self.requests = []

    async def generate_structured(self, request, output_model):
        assert output_model is TaskForceMemberAnalysis
        self.requests.append(request)
        if not self.responders:
            raise AssertionError("unexpected gateway call")
        item = self.responders.pop(0)
        if isinstance(item, Exception):
            raise item
        return item(request)


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


def _request() -> TaskForceRequest:
    return TaskForceRequest(
        request_id="tf-request-020c-002",
        system_id="balanced_v1",
        opportunity_id="12345678-1234-5678-1234-567812345678",
        trigger=TaskForceTrigger.COMPLEX_OPPORTUNITY,
        influence_scope=TaskForceInfluenceScope.ORCHESTRATION_ADVISORY,
        objective="Resolve a complex market disagreement.",
        question="Which interpretation is best supported by supplied evidence?",
        requested_by="professor",
        context_refs=("snapshot:001", "features:001"),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=20),
    )


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


def _bundle(*, operator=None):
    request = _request()
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
        task_force_id="tf-020c-002",
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
        capacity=TaskForceCapacitySnapshot(
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
    contract = build_task_force_execution_contract(
        execution_run_id="run-020c-002",
        closure=closure,
        request=request,
        lifecycle=approved,
        plan_gate=plan_gate,
        max_output_tokens=512,
        prepared_at=NOW + timedelta(seconds=4),
    )
    return operator, closure.plan, contract


def _contexts(contract):
    return {
        spec.member_id: {"snapshot": "snapshot:001", "agent": spec.agent_id}
        for spec in contract.member_specs
    }


def _quotes(contract, *, requested=Decimal("0.20"), attempts=2):
    return tuple(
        TaskForceMemberComputeQuote(
            quote_id=f"quote-{spec.member_id}",
            member_id=spec.member_id,
            agent_id=spec.agent_id,
            requested_eur=requested,
            gateway_max_attempts=attempts,
            basis="Configured route estimate including bounded Gateway attempts.",
        )
        for spec in contract.member_specs
    )


def _response(
    contract,
    member_id: str,
    *,
    costs=(Decimal("0.05"),),
    attempts=1,
    wrong_agent=False,
    wrong_result_request=False,
):
    spec = next(item for item in contract.member_specs if item.member_id == member_id)

    def responder(request):
        records = tuple(
            AIUsageRecord(
                request_id=request.request_id,
                system_id=request.system_id,
                agent_id=request.agent_id,
                route_id="route-main",
                model_id="model-main",
                input_tokens=100,
                cached_input_tokens=0,
                output_tokens=50,
                estimated_cost=cost,
                latency_ms=10,
                attempt=index,
            )
            for index, cost in enumerate(costs, start=1)
        )
        analysis = TaskForceMemberAnalysis(
            task_force_id=contract.task_force_id,
            execution_run_id=contract.execution_run_id,
            member_id=member_id,
            agent_id="wrong-agent" if wrong_agent else spec.agent_id,
            answer=f"Grounded answer from {spec.agent_id}.",
            confidence=Decimal("0.7"),
        )
        return AIGatewayResult[TaskForceMemberAnalysis](
            request_id=uuid4() if wrong_result_request else request.request_id,
            route_id="route-main",
            model_id="model-main",
            output=analysis,
            usage=records[-1],
            usage_records=records,
            attempts=attempts,
            provider_request_id=f"provider-{member_id}",
        )

    return responder


def test_executes_all_members_sequentially_after_compute_gate():
    async def scenario():
        operator, plan, contract = _bundle()
        gateway = FakeGateway(
            [_response(contract, spec.member_id) for spec in contract.member_specs]
        )
        result = await execute_task_force_members(
            contract,
            plan,
            operator,
            gateway=gateway,
            context_payloads=_contexts(contract),
            compute_quotes=_quotes(contract),
            usage=zero_task_force_execution_usage(contract),
            started_at=NOW + timedelta(seconds=5),
        )
        assert result.status is TaskForceExecutionRunStatus.COMPLETED
        assert result.aggregation_ready is True
        assert result.completed_member_count == 2
        assert [request.agent_id for request in gateway.requests] == [
            spec.agent_id for spec in contract.member_specs
        ]
        assert result.usage_after.used_total_calls == 2
        assert result.usage_after.spent_total_eur == Decimal("0.10")

    asyncio.run(scenario())


def test_compute_gate_block_prevents_any_gateway_call():
    async def scenario():
        operator, plan, contract = _bundle()
        gateway = FakeGateway([])
        result = await execute_task_force_members(
            contract,
            plan,
            operator,
            gateway=gateway,
            context_payloads=_contexts(contract),
            compute_quotes=_quotes(contract, requested=Decimal("0.60")),
            usage=zero_task_force_execution_usage(contract),
            started_at=NOW + timedelta(seconds=5),
        )
        assert result.status is TaskForceExecutionRunStatus.BLOCKED
        assert result.failure.stage is TaskForceExecutionFailureStage.COMPUTE_GATE
        assert "MEMBER_COMPUTE_BUDGET_EXCEEDED" in result.failure.reason_codes
        assert gateway.requests == []
        assert result.gateway_calls_performed is False

    asyncio.run(scenario())


def test_retry_envelope_is_enforced_by_compute_gate_before_gateway():
    async def scenario():
        operator, plan, contract = _bundle()
        gateway = FakeGateway([])
        quotes = _quotes(contract, attempts=3)
        result = await execute_task_force_members(
            contract,
            plan,
            operator,
            gateway=gateway,
            context_payloads=_contexts(contract),
            compute_quotes=quotes,
            usage=zero_task_force_execution_usage(contract),
            started_at=NOW + timedelta(seconds=5),
        )
        assert result.status is TaskForceExecutionRunStatus.BLOCKED
        assert "RETRY_LIMIT_EXCEEDED" in result.failure.reason_codes
        assert gateway.requests == []

    asyncio.run(scenario())


def test_second_member_can_be_blocked_after_first_known_charge():
    async def scenario():
        operator, plan, contract = _bundle()
        first, second = contract.member_specs
        usage = TaskForceExecutionUsageSnapshot(
            task_force_id=contract.task_force_id,
            spent_total_eur=Decimal("0.40"),
            used_total_calls=2,
            members=(
                TaskForceMemberUsageSnapshot(
                    member_id=first.member_id,
                    agent_id=first.agent_id,
                    spent_eur=Decimal("0.10"),
                    used_calls=1,
                ),
                TaskForceMemberUsageSnapshot(
                    member_id=second.member_id,
                    agent_id=second.agent_id,
                    spent_eur=Decimal("0.30"),
                    used_calls=1,
                ),
            ),
        )
        quotes = (
            TaskForceMemberComputeQuote(
                quote_id="q-first",
                member_id=first.member_id,
                agent_id=first.agent_id,
                requested_eur=Decimal("0.05"),
                gateway_max_attempts=1,
                basis="bounded",
            ),
            TaskForceMemberComputeQuote(
                quote_id="q-second",
                member_id=second.member_id,
                agent_id=second.agent_id,
                requested_eur=Decimal("0.20"),
                gateway_max_attempts=1,
                basis="bounded",
            ),
        )
        gateway = FakeGateway([_response(contract, first.member_id, costs=(Decimal("0.04"),))])
        result = await execute_task_force_members(
            contract,
            plan,
            operator,
            gateway=gateway,
            context_payloads=_contexts(contract),
            compute_quotes=quotes,
            usage=usage,
            started_at=NOW + timedelta(seconds=5),
        )
        assert result.status is TaskForceExecutionRunStatus.BLOCKED
        assert result.completed_member_count == 1
        assert "MEMBER_COMPUTE_BUDGET_EXCEEDED" in result.failure.reason_codes
        assert len(gateway.requests) == 1
        assert result.usage_after.spent_total_eur == Decimal("0.44")

    asyncio.run(scenario())


def test_gateway_exception_stops_run_and_marks_cost_accounting_partial():
    async def scenario():
        operator, plan, contract = _bundle()
        gateway = FakeGateway([RuntimeError("provider failure")])
        result = await execute_task_force_members(
            contract,
            plan,
            operator,
            gateway=gateway,
            context_payloads=_contexts(contract),
            compute_quotes=_quotes(contract),
            usage=zero_task_force_execution_usage(contract),
            started_at=NOW + timedelta(seconds=5),
        )
        assert result.status is TaskForceExecutionRunStatus.FAILED
        assert result.failure.stage is TaskForceExecutionFailureStage.AI_GATEWAY
        assert result.failure.exception_type == "RuntimeError"
        assert result.cost_accounting_complete is False
        assert len(gateway.requests) == 1

    asyncio.run(scenario())


def test_gateway_result_request_identity_mismatch_fails_closed():
    async def scenario():
        operator, plan, contract = _bundle()
        first = contract.member_specs[0]
        gateway = FakeGateway(
            [_response(contract, first.member_id, wrong_result_request=True)]
        )
        result = await execute_task_force_members(
            contract,
            plan,
            operator,
            gateway=gateway,
            context_payloads=_contexts(contract),
            compute_quotes=_quotes(contract),
            usage=zero_task_force_execution_usage(contract),
            started_at=NOW + timedelta(seconds=5),
        )
        assert result.status is TaskForceExecutionRunStatus.FAILED
        assert result.failure.stage is TaskForceExecutionFailureStage.GATEWAY_RESULT
        assert result.cost_accounting_complete is False
        assert result.completed_member_count == 0

    asyncio.run(scenario())


def test_member_analysis_identity_mismatch_fails_after_accounting_charge():
    async def scenario():
        operator, plan, contract = _bundle()
        first = contract.member_specs[0]
        gateway = FakeGateway([_response(contract, first.member_id, wrong_agent=True)])
        result = await execute_task_force_members(
            contract,
            plan,
            operator,
            gateway=gateway,
            context_payloads=_contexts(contract),
            compute_quotes=_quotes(contract),
            usage=zero_task_force_execution_usage(contract),
            started_at=NOW + timedelta(seconds=5),
        )
        assert result.status is TaskForceExecutionRunStatus.FAILED
        assert result.failure.stage is TaskForceExecutionFailureStage.OUTPUT_VALIDATION
        assert result.cost_accounting_complete is True
        assert result.usage_after.spent_total_eur == Decimal("0.05")
        assert result.completed_member_count == 0

    asyncio.run(scenario())


def test_actual_cost_above_authorized_quote_fails_and_stops():
    async def scenario():
        operator, plan, contract = _bundle()
        first = contract.member_specs[0]
        gateway = FakeGateway([_response(contract, first.member_id, costs=(Decimal("0.06"),))])
        result = await execute_task_force_members(
            contract,
            plan,
            operator,
            gateway=gateway,
            context_payloads=_contexts(contract),
            compute_quotes=_quotes(contract, requested=Decimal("0.05"), attempts=1),
            usage=zero_task_force_execution_usage(contract),
            started_at=NOW + timedelta(seconds=5),
        )
        assert result.status is TaskForceExecutionRunStatus.FAILED
        assert result.failure.stage is TaskForceExecutionFailureStage.POST_GATE_ACCOUNTING
        assert "ACTUAL_COST_EXCEEDED_AUTHORIZED_QUOTE" in result.failure.reason_codes
        assert result.usage_after.spent_total_eur == Decimal("0.06")
        assert len(gateway.requests) == 1

    asyncio.run(scenario())


def test_gateway_attempts_above_declared_envelope_fail_after_call():
    async def scenario():
        operator, plan, contract = _bundle()
        first = contract.member_specs[0]
        gateway = FakeGateway([_response(contract, first.member_id, attempts=2)])
        result = await execute_task_force_members(
            contract,
            plan,
            operator,
            gateway=gateway,
            context_payloads=_contexts(contract),
            compute_quotes=_quotes(contract, attempts=1),
            usage=zero_task_force_execution_usage(contract),
            started_at=NOW + timedelta(seconds=5),
        )
        assert result.status is TaskForceExecutionRunStatus.FAILED
        assert "GATEWAY_ATTEMPTS_EXCEEDED_AUTHORIZED_QUOTE" in result.failure.reason_codes
        assert len(gateway.requests) == 1

    asyncio.run(scenario())


def test_all_usage_records_are_charged_for_one_logical_call():
    async def scenario():
        operator, plan, contract = _bundle()
        first = contract.member_specs[0]
        second = contract.member_specs[1]
        gateway = FakeGateway(
            [
                _response(
                    contract,
                    first.member_id,
                    costs=(Decimal("0.02"), Decimal("0.03")),
                    attempts=2,
                ),
                _response(contract, second.member_id, costs=(Decimal("0.01"),)),
            ]
        )
        result = await execute_task_force_members(
            contract,
            plan,
            operator,
            gateway=gateway,
            context_payloads=_contexts(contract),
            compute_quotes=_quotes(contract, requested=Decimal("0.10"), attempts=2),
            usage=zero_task_force_execution_usage(contract),
            started_at=NOW + timedelta(seconds=5),
        )
        assert result.status is TaskForceExecutionRunStatus.COMPLETED
        assert result.member_records[0].actual_cost_eur == Decimal("0.05")
        assert result.member_records[0].usage_record_count == 2
        assert result.member_records[0].latency_ms_total == 20
        assert result.usage_after.spent_total_eur == Decimal("0.06")

    asyncio.run(scenario())


def test_missing_context_is_rejected_before_gateway():
    async def scenario():
        operator, plan, contract = _bundle()
        gateway = FakeGateway([])
        contexts = _contexts(contract)
        contexts.pop(contract.member_specs[-1].member_id)
        with pytest.raises(ValueError, match="context_payloads must cover"):
            await execute_task_force_members(
                contract,
                plan,
                operator,
                gateway=gateway,
                context_payloads=contexts,
                compute_quotes=_quotes(contract),
                usage=zero_task_force_execution_usage(contract),
                started_at=NOW + timedelta(seconds=5),
            )
        assert gateway.requests == []

    asyncio.run(scenario())


def test_expired_contract_is_rejected_before_gateway():
    async def scenario():
        operator, plan, contract = _bundle()
        gateway = FakeGateway([])
        with pytest.raises(PermissionError, match="expired"):
            await execute_task_force_members(
                contract,
                plan,
                operator,
                gateway=gateway,
                context_payloads=_contexts(contract),
                compute_quotes=_quotes(contract),
                usage=zero_task_force_execution_usage(contract),
                started_at=contract.expires_at,
            )
        assert gateway.requests == []

    asyncio.run(scenario())


def test_completed_execution_has_no_trade_risk_registry_or_live_authority():
    async def scenario():
        operator, plan, contract = _bundle()
        gateway = FakeGateway(
            [_response(contract, spec.member_id) for spec in contract.member_specs]
        )
        result = await execute_task_force_members(
            contract,
            plan,
            operator,
            gateway=gateway,
            context_payloads=_contexts(contract),
            compute_quotes=_quotes(contract),
            usage=zero_task_force_execution_usage(contract),
            started_at=NOW + timedelta(seconds=5),
        )
        assert result.trade_proposal_authority is False
        assert result.registry_mutation is False
        assert result.risk_authority is False
        assert result.live_authority is False
        assert all(record.risk_authority is False for record in result.member_records)

    asyncio.run(scenario())
