from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.intelligence.ai_gateway.models import AIGatewayRequest, AIGatewayResult, AIUsageRecord

from .composition_closure import task_force_plan_fingerprint
from .execution import (
    TaskForceExecutionContract,
    TaskForceMemberAnalysis,
    build_member_ai_gateway_request,
    validate_task_force_member_analysis,
)
from .gates import (
    TaskForceComputeDecision,
    TaskForceComputeRequest,
    TaskForceGateStatus,
    evaluate_task_force_compute,
)
from .models import TaskForceOperatorPolicy, TaskForcePlan, task_force_policy_fingerprint


ZERO = Decimal("0")


class TaskForceStructuredGateway(Protocol):
    """Minimal structural contract implemented by the real AIGateway."""

    async def generate_structured(
        self,
        request: AIGatewayRequest,
        output_model: type[TaskForceMemberAnalysis],
    ) -> AIGatewayResult[TaskForceMemberAnalysis]: ...


class TaskForceExecutionRunStatus(StrEnum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class TaskForceExecutionFailureStage(StrEnum):
    COMPUTE_GATE = "COMPUTE_GATE"
    AI_GATEWAY = "AI_GATEWAY"
    GATEWAY_RESULT = "GATEWAY_RESULT"
    OUTPUT_VALIDATION = "OUTPUT_VALIDATION"
    POST_GATE_ACCOUNTING = "POST_GATE_ACCOUNTING"


class TaskForceMemberComputeQuote(BaseModel):
    """Explicit pre-call envelope supplied from configured Gateway economics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    quote_version: Literal["batch20.task-force-compute-quote.v1"] = (
        "batch20.task-force-compute-quote.v1"
    )
    quote_id: str = Field(min_length=1, max_length=200)
    member_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=100)
    requested_eur: Decimal = Field(gt=0, allow_inf_nan=False)
    gateway_max_attempts: int = Field(ge=1)
    basis: str = Field(min_length=1, max_length=500)

    @field_validator("quote_id", "member_id", "agent_id", "basis")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class TaskForceMemberUsageSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    member_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=100)
    spent_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    used_calls: int = Field(ge=0)

    @field_validator("member_id", "agent_id")
    @classmethod
    def _strip_ids(cls, value: str) -> str:
        return value.strip()


class TaskForceExecutionUsageSnapshot(BaseModel):
    """Known Task Force spend/call state before or after a logical member call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_force_id: str = Field(min_length=1, max_length=200)
    spent_total_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    used_total_calls: int = Field(ge=0)
    members: tuple[TaskForceMemberUsageSnapshot, ...] = Field(min_length=1)

    @field_validator("task_force_id")
    @classmethod
    def _strip_task_force_id(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _coherent_totals(self) -> TaskForceExecutionUsageSnapshot:
        member_ids = [item.member_id for item in self.members]
        agent_ids = [item.agent_id for item in self.members]
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("usage members must have unique member_id values")
        if len(set(agent_ids)) != len(agent_ids):
            raise ValueError("usage members must have unique agent_id values")
        if sum((item.spent_eur for item in self.members), ZERO) != self.spent_total_eur:
            raise ValueError("spent_total_eur must equal the sum of member spend")
        if sum(item.used_calls for item in self.members) != self.used_total_calls:
            raise ValueError("used_total_calls must equal the sum of member calls")
        return self


class TaskForceMemberExecutionRecord(BaseModel):
    """Auditable successful logical call for one Task Force member."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    member_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=100)
    gateway_request_id: str = Field(min_length=36, max_length=36)
    compute_quote_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    compute_gate_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    route_id: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=200)
    provider_request_id: str | None = Field(default=None, max_length=500)
    attempts: int = Field(ge=1)
    usage_record_count: int = Field(ge=1)
    actual_cost_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    latency_ms_total: int = Field(ge=0)
    analysis: TaskForceMemberAnalysis
    trade_proposal_authority: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator(
        "compute_quote_fingerprint_sha256",
        "compute_gate_fingerprint_sha256",
    )
    @classmethod
    def _validate_sha(cls, value: str) -> str:
        return _validate_sha256(value)


class TaskForceExecutionFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: TaskForceExecutionFailureStage
    member_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=100)
    reason_codes: tuple[str, ...] = Field(min_length=1)
    compute_gate_fingerprint_sha256: str | None = Field(default=None, max_length=64)
    exception_type: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("member_id", "agent_id")
    @classmethod
    def _strip_ids(cls, value: str) -> str:
        return value.strip()

    @field_validator("reason_codes")
    @classmethod
    def _canonical_reasons(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("reason_codes must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("reason_codes must not contain duplicates")
        return tuple(sorted(normalized))

    @field_validator("compute_gate_fingerprint_sha256")
    @classmethod
    def _validate_optional_sha(cls, value: str | None) -> str | None:
        return None if value is None else _validate_sha256(value)


class TaskForceMultiMemberExecution(BaseModel):
    """Sequential, fail-closed member execution outcome. It cannot trade."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_version: Literal["batch20.task-force-multi-member-execution.v1"] = (
        "batch20.task-force-multi-member-execution.v1"
    )
    task_force_id: str = Field(min_length=1, max_length=200)
    execution_run_id: str = Field(min_length=1, max_length=200)
    execution_contract_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    started_at: datetime
    status: TaskForceExecutionRunStatus
    expected_member_count: int = Field(ge=1)
    completed_member_count: int = Field(ge=0)
    member_records: tuple[TaskForceMemberExecutionRecord, ...] = ()
    failure: TaskForceExecutionFailure | None = None
    usage_before: TaskForceExecutionUsageSnapshot
    usage_after: TaskForceExecutionUsageSnapshot
    remaining_member_ids: tuple[str, ...] = ()
    gateway_calls_performed: bool
    cost_accounting_complete: bool
    aggregation_ready: bool
    trade_proposal_authority: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("execution_contract_fingerprint_sha256")
    @classmethod
    def _validate_contract_sha(cls, value: str) -> str:
        return _validate_sha256(value)

    @field_validator("started_at")
    @classmethod
    def _validate_started_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value, field_name="started_at")

    @field_validator("remaining_member_ids")
    @classmethod
    def _canonical_remaining(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("remaining_member_ids must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("remaining_member_ids must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def _coherent_status(self) -> TaskForceMultiMemberExecution:
        if self.completed_member_count != len(self.member_records):
            raise ValueError("completed_member_count must equal member_records length")
        if self.completed_member_count > self.expected_member_count:
            raise ValueError("completed_member_count cannot exceed expected_member_count")
        if self.status is TaskForceExecutionRunStatus.COMPLETED:
            if self.failure is not None:
                raise ValueError("completed execution cannot contain failure")
            if self.completed_member_count != self.expected_member_count:
                raise ValueError("completed execution must contain every member")
            if self.remaining_member_ids:
                raise ValueError("completed execution cannot have remaining members")
            if not self.aggregation_ready or not self.cost_accounting_complete:
                raise ValueError("completed execution must be aggregation-ready and accounted")
        else:
            if self.failure is None:
                raise ValueError("blocked/failed execution must contain failure evidence")
            if self.aggregation_ready:
                raise ValueError("blocked/failed execution cannot be aggregation-ready")
        return self


def zero_task_force_execution_usage(
    contract: TaskForceExecutionContract,
) -> TaskForceExecutionUsageSnapshot:
    """Create a zeroed usage snapshot covering every member in the contract."""

    return TaskForceExecutionUsageSnapshot(
        task_force_id=contract.task_force_id,
        spent_total_eur=ZERO,
        used_total_calls=0,
        members=tuple(
            TaskForceMemberUsageSnapshot(
                member_id=spec.member_id,
                agent_id=spec.agent_id,
                spent_eur=ZERO,
                used_calls=0,
            )
            for spec in contract.member_specs
        ),
    )


def task_force_compute_quote_fingerprint(quote: TaskForceMemberComputeQuote) -> str:
    return _canonical_sha256(quote.model_dump(mode="json"))


async def execute_task_force_members(
    contract: TaskForceExecutionContract,
    plan: TaskForcePlan,
    policy: TaskForceOperatorPolicy,
    *,
    gateway: TaskForceStructuredGateway,
    context_payloads: Mapping[str, dict[str, Any]],
    compute_quotes: tuple[TaskForceMemberComputeQuote, ...],
    usage: TaskForceExecutionUsageSnapshot,
    started_at: datetime,
) -> TaskForceMultiMemberExecution:
    """Execute one logical structured AI call per member, sequentially and fail-closed.

    Every member call passes TaskForceComputeDecision before the real AI Gateway. The
    quote must cover all Gateway attempts for that logical call. The AI Gateway hard
    budget remains independently authoritative and is never bypassed by this runtime.
    """

    started_at = _ensure_utc(started_at, field_name="started_at")
    quote_by_member, context_by_member = _validate_runtime_inputs(
        contract=contract,
        plan=plan,
        policy=policy,
        compute_quotes=compute_quotes,
        context_payloads=context_payloads,
        usage=usage,
        started_at=started_at,
    )
    current_usage = usage
    records: list[TaskForceMemberExecutionRecord] = []

    for index, spec in enumerate(contract.member_specs):
        quote = quote_by_member[spec.member_id]
        member_usage = _member_usage(current_usage, spec.member_id)
        compute_request = TaskForceComputeRequest(
            task_force_id=contract.task_force_id,
            agent_id=spec.agent_id,
            spent_total_eur=current_usage.spent_total_eur,
            spent_member_eur=member_usage.spent_eur,
            used_total_calls=current_usage.used_total_calls,
            used_member_calls=member_usage.used_calls,
            requested_eur=quote.requested_eur,
            retry_index=quote.gateway_max_attempts - 1,
        )
        decision = evaluate_task_force_compute(plan, policy, compute_request)
        if decision.status is TaskForceGateStatus.BLOCK:
            return _stopped_run(
                contract=contract,
                started_at=started_at,
                usage_before=usage,
                usage_after=current_usage,
                records=records,
                failure=TaskForceExecutionFailure(
                    stage=TaskForceExecutionFailureStage.COMPUTE_GATE,
                    member_id=spec.member_id,
                    agent_id=spec.agent_id,
                    reason_codes=decision.reason_codes,
                    compute_gate_fingerprint_sha256=decision.audit_fingerprint_sha256,
                ),
                remaining_member_ids=_remaining_member_ids(contract, index),
                status=TaskForceExecutionRunStatus.BLOCKED,
                cost_accounting_complete=True,
            )

        request = build_member_ai_gateway_request(
            contract,
            member_id=spec.member_id,
            context_payload=context_by_member[spec.member_id],
        )
        try:
            gateway_result = await gateway.generate_structured(
                request,
                TaskForceMemberAnalysis,
            )
        except Exception as exc:
            return _stopped_run(
                contract=contract,
                started_at=started_at,
                usage_before=usage,
                usage_after=current_usage,
                records=records,
                failure=TaskForceExecutionFailure(
                    stage=TaskForceExecutionFailureStage.AI_GATEWAY,
                    member_id=spec.member_id,
                    agent_id=spec.agent_id,
                    reason_codes=("AI_GATEWAY_CALL_FAILED",),
                    compute_gate_fingerprint_sha256=decision.audit_fingerprint_sha256,
                    exception_type=type(exc).__name__,
                ),
                remaining_member_ids=_remaining_member_ids(contract, index),
                status=TaskForceExecutionRunStatus.FAILED,
                cost_accounting_complete=False,
            )

        normalized = _normalize_gateway_result(request, gateway_result)
        if normalized is None:
            return _stopped_run(
                contract=contract,
                started_at=started_at,
                usage_before=usage,
                usage_after=current_usage,
                records=records,
                failure=TaskForceExecutionFailure(
                    stage=TaskForceExecutionFailureStage.GATEWAY_RESULT,
                    member_id=spec.member_id,
                    agent_id=spec.agent_id,
                    reason_codes=("GATEWAY_RESULT_IDENTITY_MISMATCH",),
                    compute_gate_fingerprint_sha256=decision.audit_fingerprint_sha256,
                ),
                remaining_member_ids=_remaining_member_ids(contract, index),
                status=TaskForceExecutionRunStatus.FAILED,
                cost_accounting_complete=False,
            )

        usage_records, actual_cost, latency_total = normalized
        current_usage = _advance_usage(
            current_usage,
            member_id=spec.member_id,
            actual_cost_eur=actual_cost,
        )
        if gateway_result.attempts > quote.gateway_max_attempts:
            return _stopped_run(
                contract=contract,
                started_at=started_at,
                usage_before=usage,
                usage_after=current_usage,
                records=records,
                failure=TaskForceExecutionFailure(
                    stage=TaskForceExecutionFailureStage.POST_GATE_ACCOUNTING,
                    member_id=spec.member_id,
                    agent_id=spec.agent_id,
                    reason_codes=("GATEWAY_ATTEMPTS_EXCEEDED_AUTHORIZED_QUOTE",),
                    compute_gate_fingerprint_sha256=decision.audit_fingerprint_sha256,
                ),
                remaining_member_ids=_remaining_member_ids(contract, index),
                status=TaskForceExecutionRunStatus.FAILED,
                cost_accounting_complete=True,
            )
        if actual_cost > quote.requested_eur:
            return _stopped_run(
                contract=contract,
                started_at=started_at,
                usage_before=usage,
                usage_after=current_usage,
                records=records,
                failure=TaskForceExecutionFailure(
                    stage=TaskForceExecutionFailureStage.POST_GATE_ACCOUNTING,
                    member_id=spec.member_id,
                    agent_id=spec.agent_id,
                    reason_codes=("ACTUAL_COST_EXCEEDED_AUTHORIZED_QUOTE",),
                    compute_gate_fingerprint_sha256=decision.audit_fingerprint_sha256,
                ),
                remaining_member_ids=_remaining_member_ids(contract, index),
                status=TaskForceExecutionRunStatus.FAILED,
                cost_accounting_complete=True,
            )

        try:
            analysis = validate_task_force_member_analysis(contract, gateway_result.output)
        except ValueError:
            return _stopped_run(
                contract=contract,
                started_at=started_at,
                usage_before=usage,
                usage_after=current_usage,
                records=records,
                failure=TaskForceExecutionFailure(
                    stage=TaskForceExecutionFailureStage.OUTPUT_VALIDATION,
                    member_id=spec.member_id,
                    agent_id=spec.agent_id,
                    reason_codes=("TASK_FORCE_MEMBER_ANALYSIS_IDENTITY_MISMATCH",),
                    compute_gate_fingerprint_sha256=decision.audit_fingerprint_sha256,
                ),
                remaining_member_ids=_remaining_member_ids(contract, index),
                status=TaskForceExecutionRunStatus.FAILED,
                cost_accounting_complete=True,
            )

        records.append(
            TaskForceMemberExecutionRecord(
                member_id=spec.member_id,
                agent_id=spec.agent_id,
                gateway_request_id=str(request.request_id),
                compute_quote_fingerprint_sha256=task_force_compute_quote_fingerprint(quote),
                compute_gate_fingerprint_sha256=decision.audit_fingerprint_sha256,
                route_id=gateway_result.route_id,
                model_id=gateway_result.model_id,
                provider_request_id=gateway_result.provider_request_id,
                attempts=gateway_result.attempts,
                usage_record_count=len(usage_records),
                actual_cost_eur=actual_cost,
                latency_ms_total=latency_total,
                analysis=analysis,
            )
        )

    return TaskForceMultiMemberExecution(
        task_force_id=contract.task_force_id,
        execution_run_id=contract.execution_run_id,
        execution_contract_fingerprint_sha256=(
            contract.execution_contract_fingerprint_sha256
        ),
        started_at=started_at,
        status=TaskForceExecutionRunStatus.COMPLETED,
        expected_member_count=len(contract.member_specs),
        completed_member_count=len(records),
        member_records=tuple(records),
        failure=None,
        usage_before=usage,
        usage_after=current_usage,
        remaining_member_ids=(),
        gateway_calls_performed=True,
        cost_accounting_complete=True,
        aggregation_ready=True,
    )


def _validate_runtime_inputs(
    *,
    contract: TaskForceExecutionContract,
    plan: TaskForcePlan,
    policy: TaskForceOperatorPolicy,
    compute_quotes: tuple[TaskForceMemberComputeQuote, ...],
    context_payloads: Mapping[str, dict[str, Any]],
    usage: TaskForceExecutionUsageSnapshot,
    started_at: datetime,
) -> tuple[dict[str, TaskForceMemberComputeQuote], dict[str, dict[str, Any]]]:
    if started_at < contract.prepared_at:
        raise ValueError("multi-member execution cannot predate execution contract")
    if started_at >= contract.expires_at:
        raise PermissionError("expired Task Force execution contract cannot call AI Gateway")
    if task_force_plan_fingerprint(plan) != contract.plan_fingerprint_sha256:
        raise ValueError("execution plan fingerprint is stale")
    if plan.task_force_id != contract.task_force_id or plan.request_id != contract.request_id:
        raise ValueError("execution plan identity does not match contract")
    if policy.policy_id != plan.policy_id:
        raise ValueError("operator policy_id does not match execution plan")
    if task_force_policy_fingerprint(policy) != plan.policy_fingerprint_sha256:
        raise ValueError("operator policy fingerprint is stale")
    if usage.task_force_id != contract.task_force_id:
        raise ValueError("usage snapshot targets a different task_force_id")

    expected = {spec.member_id: spec.agent_id for spec in contract.member_specs}
    usage_map = {item.member_id: item.agent_id for item in usage.members}
    if usage_map != expected:
        raise ValueError("usage snapshot must cover the exact execution-contract members")

    quote_by_member: dict[str, TaskForceMemberComputeQuote] = {}
    for quote in compute_quotes:
        if quote.member_id in quote_by_member:
            raise ValueError("compute_quotes must not contain duplicate member_id values")
        quote_by_member[quote.member_id] = quote
    if set(quote_by_member) != set(expected):
        raise ValueError("compute_quotes must cover the exact execution-contract members")
    for member_id, agent_id in expected.items():
        if quote_by_member[member_id].agent_id != agent_id:
            raise ValueError("compute quote agent_id does not match member execution spec")

    context_by_member = dict(context_payloads)
    if set(context_by_member) != set(expected):
        raise ValueError("context_payloads must cover the exact execution-contract members")
    if any(not payload for payload in context_by_member.values()):
        raise ValueError("every member context payload must be non-empty")
    return quote_by_member, context_by_member


def _normalize_gateway_result(
    request: AIGatewayRequest,
    result: AIGatewayResult[TaskForceMemberAnalysis],
) -> tuple[tuple[AIUsageRecord, ...], Decimal, int] | None:
    if result.request_id != request.request_id:
        return None
    records = result.usage_records or (result.usage,)
    if not records:
        return None
    for usage in records:
        if usage.request_id != request.request_id:
            return None
        if usage.system_id != request.system_id or usage.agent_id != request.agent_id:
            return None
    if result.usage.request_id != request.request_id:
        return None
    if result.usage.system_id != request.system_id or result.usage.agent_id != request.agent_id:
        return None
    actual_cost = sum((item.estimated_cost for item in records), ZERO)
    latency_total = sum(item.latency_ms for item in records)
    return tuple(records), actual_cost, latency_total


def _advance_usage(
    usage: TaskForceExecutionUsageSnapshot,
    *,
    member_id: str,
    actual_cost_eur: Decimal,
) -> TaskForceExecutionUsageSnapshot:
    members = []
    for item in usage.members:
        if item.member_id == member_id:
            members.append(
                TaskForceMemberUsageSnapshot(
                    member_id=item.member_id,
                    agent_id=item.agent_id,
                    spent_eur=item.spent_eur + actual_cost_eur,
                    used_calls=item.used_calls + 1,
                )
            )
        else:
            members.append(item)
    return TaskForceExecutionUsageSnapshot(
        task_force_id=usage.task_force_id,
        spent_total_eur=usage.spent_total_eur + actual_cost_eur,
        used_total_calls=usage.used_total_calls + 1,
        members=tuple(members),
    )


def _member_usage(
    usage: TaskForceExecutionUsageSnapshot,
    member_id: str,
) -> TaskForceMemberUsageSnapshot:
    return next(item for item in usage.members if item.member_id == member_id)


def _remaining_member_ids(
    contract: TaskForceExecutionContract,
    failed_index: int,
) -> tuple[str, ...]:
    return tuple(spec.member_id for spec in contract.member_specs[failed_index:])


def _stopped_run(
    *,
    contract: TaskForceExecutionContract,
    started_at: datetime,
    usage_before: TaskForceExecutionUsageSnapshot,
    usage_after: TaskForceExecutionUsageSnapshot,
    records: list[TaskForceMemberExecutionRecord],
    failure: TaskForceExecutionFailure,
    remaining_member_ids: tuple[str, ...],
    status: TaskForceExecutionRunStatus,
    cost_accounting_complete: bool,
) -> TaskForceMultiMemberExecution:
    return TaskForceMultiMemberExecution(
        task_force_id=contract.task_force_id,
        execution_run_id=contract.execution_run_id,
        execution_contract_fingerprint_sha256=(
            contract.execution_contract_fingerprint_sha256
        ),
        started_at=started_at,
        status=status,
        expected_member_count=len(contract.member_specs),
        completed_member_count=len(records),
        member_records=tuple(records),
        failure=failure,
        usage_before=usage_before,
        usage_after=usage_after,
        remaining_member_ids=remaining_member_ids,
        gateway_calls_performed=(usage_after.used_total_calls > usage_before.used_total_calls),
        cost_accounting_complete=cost_accounting_complete,
        aggregation_ready=False,
    )


def _ensure_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _validate_sha256(value: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise ValueError("value must be a SHA-256 hexadecimal digest")
    return normalized


def _canonical_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
