from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.market.features.models import FeatureSnapshot
from app.market.scanner.models import CandidateOpportunity
from app.task_force.models import (
    TaskForceInfluenceScope,
    TaskForceRequest,
    TaskForceTrigger,
    task_force_request_fingerprint,
)


class TaskForceInvocationStatus(StrEnum):
    SKIPPED = "SKIPPED"
    PROPOSED = "PROPOSED"


def _ensure_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _canonical_values(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if any(not value for value in normalized):
        raise ValueError(f"{field_name} must not contain blanks")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return tuple(sorted(normalized))


def _validate_sha256(value: str) -> str:
    if len(value) != 64:
        raise ValueError("fingerprint must be a SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError("fingerprint must be a SHA-256 hex digest") from exc
    return value.lower()


def _canonical_sha256(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TaskForceTriggerSignal(BaseModel):
    """Explicit orchestration signal; no production threshold is inferred here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    signal_id: str = Field(min_length=1, max_length=200)
    trigger: TaskForceTrigger
    objective: str = Field(min_length=1, max_length=2000)
    question: str = Field(min_length=1, max_length=4000)
    reason_codes: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    context_refs: tuple[str, ...] = ()
    required_roles: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    red_team_required: bool = False
    observed_at: datetime

    @field_validator("signal_id", "objective", "question")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "reason_codes",
        "evidence_refs",
        "context_refs",
        "required_roles",
        "required_capabilities",
    )
    @classmethod
    def _canonical_tuple(cls, values: tuple[str, ...], info: Any) -> tuple[str, ...]:
        return _canonical_values(values, field_name=info.field_name)

    @field_validator("observed_at")
    @classmethod
    def _validate_observed_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value, field_name="observed_at")


class TaskForceInvocationPolicy(BaseModel):
    """Operator-owned trigger allowlist and lifetime bound."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    policy_id: str = Field(min_length=1, max_length=200)
    enabled_triggers: tuple[TaskForceTrigger, ...] = Field(min_length=1)
    max_request_lifetime_seconds: int = Field(ge=1)

    @field_validator("policy_id")
    @classmethod
    def _strip_policy_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("enabled_triggers")
    @classmethod
    def _canonical_triggers(
        cls,
        values: tuple[TaskForceTrigger, ...],
    ) -> tuple[TaskForceTrigger, ...]:
        if len(set(values)) != len(values):
            raise ValueError("enabled_triggers must not contain duplicates")
        return tuple(sorted(values, key=lambda item: item.value))


class TaskForceInvocationDecision(BaseModel):
    """Pure orchestration bridge result. A proposal is never an execution approval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["batch20d.task-force-invocation.v1"] = (
        "batch20d.task-force-invocation.v1"
    )
    decision_id: str = Field(min_length=64, max_length=64)
    status: TaskForceInvocationStatus
    policy_id: str = Field(min_length=1, max_length=200)
    signal_id: str = Field(min_length=1, max_length=200)
    trigger: TaskForceTrigger
    decision_reasons: tuple[str, ...] = Field(min_length=1)
    signal_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    policy_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    request: TaskForceRequest | None = None
    request_fingerprint_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    execute_task_force: Literal[False] = False
    operator_authorization_required: Literal[True] = True
    trade_proposal_authority: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator(
        "decision_id",
        "signal_fingerprint_sha256",
        "policy_fingerprint_sha256",
    )
    @classmethod
    def _validate_required_sha(cls, value: str) -> str:
        return _validate_sha256(value)

    @field_validator("request_fingerprint_sha256")
    @classmethod
    def _validate_optional_sha(cls, value: str | None) -> str | None:
        return None if value is None else _validate_sha256(value)

    @field_validator("decision_reasons")
    @classmethod
    def _validate_decision_reasons(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_values(values, field_name="decision_reasons")

    @model_validator(mode="after")
    def _coherent_status(self) -> TaskForceInvocationDecision:
        if self.status is TaskForceInvocationStatus.PROPOSED:
            if self.request is None or self.request_fingerprint_sha256 is None:
                raise ValueError("PROPOSED invocation requires a TaskForceRequest")
        elif self.request is not None or self.request_fingerprint_sha256 is not None:
            raise ValueError("SKIPPED invocation cannot carry a TaskForceRequest")
        return self


def task_force_trigger_signal_fingerprint(signal: TaskForceTriggerSignal) -> str:
    return _canonical_sha256(signal.model_dump(mode="json"))


def task_force_invocation_policy_fingerprint(policy: TaskForceInvocationPolicy) -> str:
    return _canonical_sha256(policy.model_dump(mode="json"))


def evaluate_task_force_trigger(
    *,
    policy: TaskForceInvocationPolicy,
    signal: TaskForceTriggerSignal,
    opportunity: CandidateOpportunity,
    market_context: FeatureSnapshot,
) -> TaskForceInvocationDecision:
    """Turn one explicit signal into a request proposal or deterministic skip."""

    _validate_orchestration_context(
        signal=signal,
        opportunity=opportunity,
        market_context=market_context,
    )
    signal_fingerprint = task_force_trigger_signal_fingerprint(signal)
    policy_fingerprint = task_force_invocation_policy_fingerprint(policy)

    if signal.trigger not in policy.enabled_triggers:
        return _build_decision(
            status=TaskForceInvocationStatus.SKIPPED,
            policy=policy,
            signal=signal,
            signal_fingerprint=signal_fingerprint,
            policy_fingerprint=policy_fingerprint,
            decision_reasons=("TRIGGER_DISABLED_BY_OPERATOR_POLICY",),
            request=None,
        )

    expires_at = min(
        opportunity.expires_at.astimezone(UTC),
        signal.observed_at + timedelta(seconds=policy.max_request_lifetime_seconds),
    )
    request_id = str(
        uuid5(
            NAMESPACE_URL,
            ":".join(
                (
                    "money-heist",
                    "task-force-request",
                    opportunity.system_id,
                    opportunity.opportunity_id,
                    signal_fingerprint,
                    policy_fingerprint,
                    expires_at.isoformat(),
                )
            ),
        )
    )
    context_refs = _canonical_values(
        (
            f"opportunity:{opportunity.opportunity_id}",
            f"market_snapshot:{market_context.snapshot_id}",
            *signal.context_refs,
            *signal.evidence_refs,
        ),
        field_name="request.context_refs",
    )
    request = TaskForceRequest(
        request_id=request_id,
        system_id=opportunity.system_id,
        opportunity_id=opportunity.opportunity_id,
        trigger=signal.trigger,
        influence_scope=TaskForceInfluenceScope.ORCHESTRATION_ADVISORY,
        objective=signal.objective,
        question=signal.question,
        requested_by="orchestration.task_force_trigger",
        context_refs=context_refs,
        required_roles=signal.required_roles,
        required_capabilities=signal.required_capabilities,
        red_team_required=signal.red_team_required,
        created_at=signal.observed_at,
        expires_at=expires_at,
    )
    return _build_decision(
        status=TaskForceInvocationStatus.PROPOSED,
        policy=policy,
        signal=signal,
        signal_fingerprint=signal_fingerprint,
        policy_fingerprint=policy_fingerprint,
        decision_reasons=("EXPLICIT_TRIGGER_ENABLED", *signal.reason_codes),
        request=request,
    )


def _validate_orchestration_context(
    *,
    signal: TaskForceTriggerSignal,
    opportunity: CandidateOpportunity,
    market_context: FeatureSnapshot,
) -> None:
    created_at = opportunity.created_at.astimezone(UTC)
    expires_at = opportunity.expires_at.astimezone(UTC)
    observed_at = market_context.observed_at.astimezone(UTC)
    if opportunity.snapshot_id != market_context.snapshot_id:
        raise ValueError("opportunity snapshot_id does not match market context")
    if opportunity.symbol != market_context.symbol:
        raise ValueError("opportunity symbol does not match market context")
    if opportunity.timeframe != market_context.timeframe:
        raise ValueError("opportunity timeframe does not match market context")
    if not market_context.quality.warmup_complete:
        raise ValueError("feature warmup is incomplete")
    if signal.observed_at < created_at:
        raise ValueError("Task Force trigger signal predates the opportunity")
    if signal.observed_at >= expires_at:
        raise PermissionError("expired opportunity cannot trigger a Task Force request")
    if observed_at > signal.observed_at:
        raise ValueError("Task Force trigger cannot use market context from the future")


def _build_decision(
    *,
    status: TaskForceInvocationStatus,
    policy: TaskForceInvocationPolicy,
    signal: TaskForceTriggerSignal,
    signal_fingerprint: str,
    policy_fingerprint: str,
    decision_reasons: tuple[str, ...],
    request: TaskForceRequest | None,
) -> TaskForceInvocationDecision:
    request_fingerprint = None if request is None else task_force_request_fingerprint(request)
    material = {
        "schema_version": "batch20d.task-force-invocation.v1",
        "status": status.value,
        "policy_id": policy.policy_id,
        "signal_id": signal.signal_id,
        "trigger": signal.trigger.value,
        "decision_reasons": tuple(sorted(set(decision_reasons))),
        "signal_fingerprint_sha256": signal_fingerprint,
        "policy_fingerprint_sha256": policy_fingerprint,
        "request_fingerprint_sha256": request_fingerprint,
        "execute_task_force": False,
        "operator_authorization_required": True,
        "trade_proposal_authority": False,
        "registry_mutation": False,
        "risk_authority": False,
        "live_authority": False,
    }
    decision_id = _canonical_sha256(material)
    return TaskForceInvocationDecision(
        decision_id=decision_id,
        status=status,
        policy_id=policy.policy_id,
        signal_id=signal.signal_id,
        trigger=signal.trigger,
        decision_reasons=material["decision_reasons"],
        signal_fingerprint_sha256=signal_fingerprint,
        policy_fingerprint_sha256=policy_fingerprint,
        request=request,
        request_fingerprint_sha256=request_fingerprint,
    )
