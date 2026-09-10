from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.intelligence.ai_gateway.models import AIGatewayRequest, AIGatewayResult, AIUsageRecord
from app.services.backtest.ids import canonical_json, stable_digest, stable_uuid

from .allocation import (
    AllocationEnvelopeStatus,
    CrewAllocationEnvelope,
    MasterAllocationPolicy,
    master_allocation_policy_fingerprint,
)
from .allocation_advisory import (
    MasterAllocationAdvisoryAction,
    MasterAllocationAdvisoryEvidence,
    MasterAllocationAdvisoryReport,
    build_master_allocation_advisory_evidence,
    build_master_allocation_advisory_recommendation,
    build_master_allocation_advisory_report,
)
from .allocation_evidence_analysis import (
    MasterAllocationEvidenceAnalysisReport,
    master_allocation_evidence_analysis_payload,
)

ZERO = Decimal("0")
MASTER_PROFESSOR_AGENT_ID = "master-professor"


class MasterProfessorAllocationCandidateSource(StrEnum):
    OPERATOR_SCENARIO = "OPERATOR_SCENARIO"


class MasterProfessorShadowStatus(StrEnum):
    COMPLETED = "COMPLETED"


def _required_text(value: object, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank when provided")
    return normalized


def _sha256(value: str, *, field_name: str) -> str:
    normalized = str(value).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return normalized


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _non_negative_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < ZERO:
        raise ValueError(f"{field_name} must be a finite Decimal >= 0")
    return value


def _policy_fingerprint(policy: MasterAllocationPolicy) -> str:
    return master_allocation_policy_fingerprint(
        master_portfolio_id=policy.master_portfolio_id,
        policy_id=policy.policy_id,
        members=policy.members,
        envelopes=policy.envelopes,
        status=policy.status,
        reason_codes=policy.reason_codes,
        source=policy.source,
        source_ref=policy.source_ref,
        schema_version=policy.schema_version,
    )


def master_professor_allocation_candidate_payload(
    candidate: MasterProfessorAllocationCandidate,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-professor-allocation-candidate.v1",
        "schema_version": candidate.schema_version,
        "candidate_id": candidate.candidate_id,
        "source": candidate.source,
        "source_ref": candidate.source_ref,
        "proposed_envelopes": [
            envelope.canonical_payload() for envelope in candidate.proposed_envelopes
        ],
    }


@dataclass(frozen=True, slots=True)
class MasterProfessorAllocationCandidate:
    """One complete operator-owned allocation scenario selectable by the SHADOW advisor."""

    candidate_id: str
    proposed_envelopes: tuple[CrewAllocationEnvelope, ...]
    source_ref: str
    fingerprint_sha256: str
    source: MasterProfessorAllocationCandidateSource = field(
        default=MasterProfessorAllocationCandidateSource.OPERATOR_SCENARIO,
        init=False,
    )
    operator_owned_values: bool = field(default=True, init=False)
    advisory_only: bool = field(default=True, init=False)
    auto_apply: bool = field(default=False, init=False)
    policy_mutation: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _required_text(self.candidate_id, field_name="candidate_id"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _required_text(self.source_ref, field_name="source_ref"),
        )
        if not self.proposed_envelopes:
            raise ValueError("Master Professor candidate requires proposed_envelopes")
        system_ids = tuple(item.system_id for item in self.proposed_envelopes)
        if system_ids != tuple(sorted(system_ids)):
            raise ValueError("Master Professor candidate envelopes must be sorted by system_id")
        if len(set(system_ids)) != len(system_ids):
            raise ValueError(
                "Master Professor candidate envelopes must have unique system_id values"
            )
        if any(
            item.status is not AllocationEnvelopeStatus.CONFIGURED
            for item in self.proposed_envelopes
        ):
            raise ValueError("Master Professor candidate envelopes must all be CONFIGURED")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master Professor candidate schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_professor_allocation_candidate_payload(self))
        if normalized != expected:
            raise ValueError("Master Professor candidate fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_professor_allocation_candidate_payload(self)


def build_master_professor_allocation_candidate(
    *,
    candidate_id: str,
    proposed_envelopes: tuple[CrewAllocationEnvelope, ...],
    source_ref: str,
) -> MasterProfessorAllocationCandidate:
    ordered = tuple(sorted(proposed_envelopes, key=lambda item: item.system_id))
    provisional = MasterProfessorAllocationCandidate.__new__(MasterProfessorAllocationCandidate)
    object.__setattr__(
        provisional,
        "candidate_id",
        _required_text(candidate_id, field_name="candidate_id"),
    )
    object.__setattr__(provisional, "proposed_envelopes", ordered)
    object.__setattr__(
        provisional,
        "source_ref",
        _required_text(source_ref, field_name="source_ref"),
    )
    object.__setattr__(
        provisional,
        "source",
        MasterProfessorAllocationCandidateSource.OPERATOR_SCENARIO,
    )
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterProfessorAllocationCandidate(
        candidate_id=provisional.candidate_id,
        proposed_envelopes=ordered,
        source_ref=provisional.source_ref,
        fingerprint_sha256=stable_digest(
            master_professor_allocation_candidate_payload(provisional)
        ),
    )


def master_professor_shadow_config_payload(
    config: MasterProfessorShadowGatewayConfig,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-professor-shadow-gateway-config.v1",
        "schema_version": config.schema_version,
        "prompt_version": config.prompt_version,
        "model_route": config.model_route,
        "max_output_tokens": config.max_output_tokens,
        "source_ref": config.source_ref,
        "agent_id": config.agent_id,
        "mode": config.mode,
    }


@dataclass(frozen=True, slots=True)
class MasterProfessorShadowGatewayConfig:
    prompt_version: str
    model_route: str
    max_output_tokens: int
    source_ref: str
    fingerprint_sha256: str
    agent_id: str = field(default=MASTER_PROFESSOR_AGENT_ID, init=False)
    mode: str = field(default="SHADOW", init=False)
    provider_direct_access: bool = field(default=False, init=False)
    gateway_required: bool = field(default=True, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("prompt_version", "model_route", "source_ref"):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), field_name=name),
            )
        if isinstance(self.max_output_tokens, bool) or self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be an integer >= 1")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master Professor gateway config schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_professor_shadow_config_payload(self))
        if normalized != expected:
            raise ValueError("Master Professor gateway config fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def build_master_professor_shadow_gateway_config(
    *,
    prompt_version: str,
    model_route: str,
    max_output_tokens: int,
    source_ref: str,
) -> MasterProfessorShadowGatewayConfig:
    values = {
        "prompt_version": _required_text(prompt_version, field_name="prompt_version"),
        "model_route": _required_text(model_route, field_name="model_route"),
        "max_output_tokens": max_output_tokens,
        "source_ref": _required_text(source_ref, field_name="source_ref"),
    }
    if isinstance(max_output_tokens, bool) or max_output_tokens < 1:
        raise ValueError("max_output_tokens must be an integer >= 1")
    provisional = MasterProfessorShadowGatewayConfig.__new__(MasterProfessorShadowGatewayConfig)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "agent_id", MASTER_PROFESSOR_AGENT_ID)
    object.__setattr__(provisional, "mode", "SHADOW")
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterProfessorShadowGatewayConfig(
        **values,
        fingerprint_sha256=stable_digest(master_professor_shadow_config_payload(provisional)),
    )


def _canonical_text_values(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(_required_text(item, field_name=field_name) for item in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} values must be unique")
    return tuple(sorted(normalized))


def _canonical_sha_values(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(_sha256(item, field_name=field_name) for item in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} values must be unique")
    return tuple(sorted(normalized))


class MasterProfessorShadowOutput(BaseModel):
    """Strict AI output. It can select only operator-owned allocation scenarios."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    analysis_id: str = Field(min_length=1, max_length=200)
    analysis_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    current_policy_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    action: MasterAllocationAdvisoryAction
    selected_candidate_id: str | None = Field(default=None, max_length=200)
    rationale_codes: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=4000)
    uncertainties: tuple[str, ...] = ()
    advisory_only: Literal[True] = True
    operator_review_required: Literal[True] = True
    auto_apply: Literal[False] = False
    numeric_allocation_generation: Literal[False] = False
    policy_mutation: Literal[False] = False
    reservation_authority: Literal[False] = False
    risk_authority: Literal[False] = False
    admission_authority: Literal[False] = False
    local_risk_override: Literal[False] = False
    resize_authority: Literal[False] = False
    registry_mutation: Literal[False] = False
    broker_authority: Literal[False] = False
    live_authority: Literal[False] = False
    auto_execute: Literal[False] = False

    @field_validator("analysis_id", "summary")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        return value.strip()

    @field_validator("analysis_fingerprint_sha256", "current_policy_fingerprint_sha256")
    @classmethod
    def _validate_sha(cls, value: str) -> str:
        return _sha256(value, field_name="output_fingerprint")

    @field_validator("selected_candidate_id")
    @classmethod
    def _strip_candidate(cls, value: str | None) -> str | None:
        return _optional_text(value, field_name="selected_candidate_id")

    @field_validator("rationale_codes")
    @classmethod
    def _canonical_rationales(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_text_values(values, field_name="rationale_codes")

    @field_validator("evidence_refs")
    @classmethod
    def _canonical_evidence_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_sha_values(values, field_name="evidence_refs")

    @field_validator("uncertainties")
    @classmethod
    def _canonical_uncertainties(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_text_values(values, field_name="uncertainties")

    @model_validator(mode="after")
    def _validate_action_shape(self) -> MasterProfessorShadowOutput:
        if (
            self.action is MasterAllocationAdvisoryAction.PROPOSE_CHANGE
            and self.selected_candidate_id is None
        ):
            raise ValueError("PROPOSE_CHANGE requires selected_candidate_id")
        if (
            self.action is not MasterAllocationAdvisoryAction.PROPOSE_CHANGE
            and self.selected_candidate_id is not None
        ):
            raise ValueError("KEEP_CURRENT/ABSTAIN cannot carry selected_candidate_id")
        return self


class MasterProfessorStructuredGateway(Protocol):
    async def generate_structured(
        self,
        request: AIGatewayRequest,
        output_model: type[MasterProfessorShadowOutput],
    ) -> AIGatewayResult[MasterProfessorShadowOutput]: ...


def _candidate_context(
    candidate: MasterProfessorAllocationCandidate,
) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "source": candidate.source,
        "source_ref": candidate.source_ref,
        "fingerprint_sha256": candidate.fingerprint_sha256,
        "proposed_envelopes": [
            item.canonical_payload() for item in candidate.proposed_envelopes
        ],
    }


def _analysis_context(analysis: MasterAllocationEvidenceAnalysisReport) -> dict[str, object]:
    return {
        "analysis_id": analysis.analysis_id,
        "fingerprint_sha256": analysis.fingerprint_sha256,
        "evidence_through": analysis.evidence_through,
        "evidence_fingerprints_sha256": analysis.evidence_fingerprints_sha256,
        "reason_codes": analysis.reason_codes,
        "historical_allocation_policy_fingerprints_sha256": (
            analysis.historical_allocation_policy_fingerprints_sha256
        ),
        "regime_keys": analysis.regime_keys,
        "unlabeled_evidence_count": analysis.unlabeled_evidence_count,
        "crew_analyses": [item.canonical_payload() for item in analysis.crew_analyses],
        "pairwise_comparisons": [
            item.canonical_payload() for item in analysis.pairwise_comparisons
        ],
    }


def _allowed_evidence_refs(
    analysis: MasterAllocationEvidenceAnalysisReport,
) -> frozenset[str]:
    values = {
        analysis.fingerprint_sha256,
        *analysis.evidence_fingerprints_sha256,
        *(item.fingerprint_sha256 for item in analysis.crew_analyses),
        *(item.fingerprint_sha256 for item in analysis.pairwise_comparisons),
    }
    return frozenset(values)


def _validate_analysis_context(
    *,
    current_allocation_policy: MasterAllocationPolicy,
    evidence: tuple[MasterAllocationAdvisoryEvidence, ...],
    analysis: MasterAllocationEvidenceAnalysisReport,
    candidates: tuple[MasterProfessorAllocationCandidate, ...],
) -> tuple[MasterAllocationAdvisoryEvidence, ...]:
    if current_allocation_policy.status is not AllocationEnvelopeStatus.CONFIGURED:
        raise ValueError("Master Professor SHADOW requires CONFIGURED current allocation policy")
    if _policy_fingerprint(current_allocation_policy) != (
        current_allocation_policy.fingerprint_sha256
    ):
        raise ValueError("Master Professor current allocation policy fingerprint integrity failure")
    if stable_digest(master_allocation_evidence_analysis_payload(analysis)) != (
        analysis.fingerprint_sha256
    ):
        raise ValueError("Master Professor evidence analysis fingerprint integrity failure")
    if analysis.master_portfolio_id != current_allocation_policy.master_portfolio_id:
        raise ValueError("Master Professor analysis Master Portfolio mismatch")
    if analysis.current_policy_fingerprint_sha256 != (
        current_allocation_policy.fingerprint_sha256
    ):
        raise ValueError("Master Professor analysis does not bind current allocation policy")
    if not evidence:
        raise ValueError("Master Professor SHADOW requires sealed advisory evidence")
    ordered_evidence = tuple(sorted(evidence, key=lambda item: (item.sealed_at, item.evidence_id)))
    rebuilt_fingerprints = []
    for item in ordered_evidence:
        rebuilt = build_master_allocation_advisory_evidence(
            audit_report=item.audit_report,
            closure_seal=item.closure_seal,
            evaluation=item.evaluation,
            regime_label=item.regime_label,
            regime_source_ref=item.regime_source_ref,
        )
        if rebuilt.evidence_id != item.evidence_id or (
            rebuilt.fingerprint_sha256 != item.fingerprint_sha256
        ):
            raise ValueError("Master Professor source advisory evidence integrity failure")
        rebuilt_fingerprints.append(rebuilt.fingerprint_sha256)
    if tuple(rebuilt_fingerprints) != analysis.evidence_fingerprints_sha256:
        raise ValueError("Master Professor analysis/evidence provenance mismatch")
    policy_system_ids = tuple(member.system_id for member in current_allocation_policy.members)
    current_payloads = tuple(
        item.canonical_payload() for item in current_allocation_policy.envelopes
    )
    candidate_ids = tuple(item.candidate_id for item in candidates)
    if candidate_ids != tuple(sorted(candidate_ids)):
        raise ValueError("Master Professor candidates must be sorted by candidate_id")
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("Master Professor candidate_id values must be unique")
    candidate_fingerprints = tuple(item.fingerprint_sha256 for item in candidates)
    if len(set(candidate_fingerprints)) != len(candidate_fingerprints):
        raise ValueError("Master Professor candidate fingerprints must be unique")
    for candidate in candidates:
        if stable_digest(master_professor_allocation_candidate_payload(candidate)) != (
            candidate.fingerprint_sha256
        ):
            raise ValueError("Master Professor candidate fingerprint integrity failure")
        system_ids = tuple(item.system_id for item in candidate.proposed_envelopes)
        if system_ids != policy_system_ids:
            raise ValueError("Master Professor candidate must preserve exact crew membership")
        candidate_payloads = tuple(
            item.canonical_payload() for item in candidate.proposed_envelopes
        )
        if candidate_payloads == current_payloads:
            raise ValueError(
                "Master Professor candidate must differ from current allocation policy"
            )
    return ordered_evidence


def build_master_professor_shadow_gateway_request(
    *,
    current_allocation_policy: MasterAllocationPolicy,
    evidence: tuple[MasterAllocationAdvisoryEvidence, ...],
    analysis: MasterAllocationEvidenceAnalysisReport,
    candidates: tuple[MasterProfessorAllocationCandidate, ...],
    config: MasterProfessorShadowGatewayConfig,
) -> AIGatewayRequest:
    """Build one deterministic AI Gateway request; this function performs no provider call."""

    ordered_candidates = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    _validate_analysis_context(
        current_allocation_policy=current_allocation_policy,
        evidence=evidence,
        analysis=analysis,
        candidates=ordered_candidates,
    )
    if stable_digest(master_professor_shadow_config_payload(config)) != config.fingerprint_sha256:
        raise ValueError("Master Professor gateway config fingerprint integrity failure")
    request_material = {
        "schema": "money-heist.master-professor-shadow-gateway-request-id.v1",
        "master_portfolio_id": current_allocation_policy.master_portfolio_id,
        "analysis_fingerprint_sha256": analysis.fingerprint_sha256,
        "current_policy_fingerprint_sha256": current_allocation_policy.fingerprint_sha256,
        "candidate_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in ordered_candidates
        ),
        "gateway_config_fingerprint_sha256": config.fingerprint_sha256,
    }
    request_id = UUID(stable_uuid("master-professor-shadow-gateway-request", request_material))
    input_payload = {
        "schema": "money-heist.master-professor-shadow-input.v1",
        "master_portfolio_id": current_allocation_policy.master_portfolio_id,
        "current_allocation_policy": {
            "policy_id": current_allocation_policy.policy_id,
            "fingerprint_sha256": current_allocation_policy.fingerprint_sha256,
            "envelopes": [
                item.canonical_payload() for item in current_allocation_policy.envelopes
            ],
        },
        "evidence_analysis": _analysis_context(analysis),
        "operator_candidate_options": [
            _candidate_context(item) for item in ordered_candidates
        ],
        "allowed_evidence_refs": sorted(_allowed_evidence_refs(analysis)),
    }
    instructions = (
        "You are the Master Professor operating in SHADOW advisory mode. "
        "Use only the supplied deterministic evidence analysis and operator-owned "
        "candidate options. "
        "Return exactly one structured MasterProfessorShadowOutput. "
        "For PROPOSE_CHANGE, select exactly one supplied candidate_id; never invent, "
        "edit, interpolate, "
        "optimize, or calculate allocation amounts. KEEP_CURRENT and ABSTAIN select no candidate. "
        "Every evidence_refs value must be copied from allowed_evidence_refs. "
        "Do not create rankings, composite scores, Kelly sizing, statistical "
        "correlations, thresholds, "
        "orders, reservations, Risk decisions, registry changes, broker actions, or LIVE actions. "
        "The output is advisory only and always requires operator review. "
        f"Echo analysis_id={analysis.analysis_id}, "
        f"analysis_fingerprint_sha256={analysis.fingerprint_sha256}, "
        "and current_policy_fingerprint_sha256="
        f"{current_allocation_policy.fingerprint_sha256}."
    )
    return AIGatewayRequest(
        request_id=request_id,
        system_id=current_allocation_policy.master_portfolio_id,
        agent_id=MASTER_PROFESSOR_AGENT_ID,
        prompt_version=config.prompt_version,
        model_route=config.model_route,
        input_text=canonical_json(input_payload),
        instructions=instructions,
        max_output_tokens=config.max_output_tokens,
        metadata={
            "phase": "master_professor_allocation_advisory",
            "mode": "SHADOW",
            "analysis_id": analysis.analysis_id,
            "analysis_fingerprint_sha256": analysis.fingerprint_sha256,
            "current_policy_fingerprint_sha256": (
                current_allocation_policy.fingerprint_sha256
            ),
            "gateway_config_fingerprint_sha256": config.fingerprint_sha256,
        },
    )


def validate_master_professor_shadow_output(
    *,
    output: MasterProfessorShadowOutput,
    current_allocation_policy: MasterAllocationPolicy,
    analysis: MasterAllocationEvidenceAnalysisReport,
    candidates: tuple[MasterProfessorAllocationCandidate, ...],
) -> MasterProfessorShadowOutput:
    if output.analysis_id != analysis.analysis_id:
        raise ValueError("Master Professor output analysis_id mismatch")
    if output.analysis_fingerprint_sha256 != analysis.fingerprint_sha256:
        raise ValueError("Master Professor output analysis fingerprint mismatch")
    if output.current_policy_fingerprint_sha256 != current_allocation_policy.fingerprint_sha256:
        raise ValueError("Master Professor output current policy fingerprint mismatch")
    allowed_refs = _allowed_evidence_refs(analysis)
    if any(value not in allowed_refs for value in output.evidence_refs):
        raise ValueError("Master Professor output cites evidence outside supplied analysis")
    candidate_map = {item.candidate_id: item for item in candidates}
    if (
        output.action is MasterAllocationAdvisoryAction.PROPOSE_CHANGE
        and output.selected_candidate_id not in candidate_map
    ):
        raise ValueError("Master Professor output selected unknown operator candidate")
    return output


def master_professor_shadow_usage_payload(
    usage: MasterProfessorShadowUsageRecord,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-professor-shadow-usage.v1",
        "schema_version": usage.schema_version,
        "usage_id": usage.usage_id,
        "request_id": usage.request_id,
        "system_id": usage.system_id,
        "agent_id": usage.agent_id,
        "route_id": usage.route_id,
        "model_id": usage.model_id,
        "input_tokens": usage.input_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
        "output_tokens": usage.output_tokens,
        "estimated_cost_eur": usage.estimated_cost_eur,
        "latency_ms": usage.latency_ms,
        "attempt": usage.attempt,
        "created_at": usage.created_at,
    }


@dataclass(frozen=True, slots=True)
class MasterProfessorShadowUsageRecord:
    usage_id: str
    request_id: str
    system_id: str
    agent_id: str
    route_id: str
    model_id: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    estimated_cost_eur: Decimal
    latency_ms: int
    attempt: int
    created_at: datetime
    fingerprint_sha256: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("usage_id", "request_id", "system_id", "agent_id", "route_id", "model_id"):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), field_name=name),
            )
        for name in ("input_tokens", "cached_input_tokens", "output_tokens", "latency_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be an integer >= 0")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens cannot exceed input_tokens")
        if isinstance(self.attempt, bool) or self.attempt < 1:
            raise ValueError("attempt must be an integer >= 1")
        object.__setattr__(
            self,
            "estimated_cost_eur",
            _non_negative_decimal(self.estimated_cost_eur, field_name="estimated_cost_eur"),
        )
        object.__setattr__(self, "created_at", _utc(self.created_at, field_name="created_at"))
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master Professor usage schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        if normalized != stable_digest(master_professor_shadow_usage_payload(self)):
            raise ValueError("Master Professor usage fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def _usage_record(source: AIUsageRecord) -> MasterProfessorShadowUsageRecord:
    values = {
        "usage_id": str(source.usage_id),
        "request_id": str(source.request_id),
        "system_id": source.system_id,
        "agent_id": source.agent_id,
        "route_id": source.route_id,
        "model_id": source.model_id,
        "input_tokens": source.input_tokens,
        "cached_input_tokens": source.cached_input_tokens,
        "output_tokens": source.output_tokens,
        "estimated_cost_eur": source.estimated_cost,
        "latency_ms": source.latency_ms,
        "attempt": source.attempt,
        "created_at": source.created_at,
    }
    provisional = MasterProfessorShadowUsageRecord.__new__(MasterProfessorShadowUsageRecord)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterProfessorShadowUsageRecord(
        **values,
        fingerprint_sha256=stable_digest(master_professor_shadow_usage_payload(provisional)),
    )


def master_professor_shadow_result_payload(
    result: MasterProfessorShadowAdvisoryResult,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-professor-shadow-advisory-result.v1",
        "schema_version": result.schema_version,
        "status": result.status,
        "master_portfolio_id": result.master_portfolio_id,
        "analysis_id": result.analysis_id,
        "analysis_fingerprint_sha256": result.analysis_fingerprint_sha256,
        "current_policy_fingerprint_sha256": result.current_policy_fingerprint_sha256,
        "candidate_fingerprints_sha256": result.candidate_fingerprints_sha256,
        "gateway_config_fingerprint_sha256": result.gateway_config_fingerprint_sha256,
        "gateway_request_id": result.gateway_request_id,
        "gateway_route_id": result.gateway_route_id,
        "gateway_model_id": result.gateway_model_id,
        "provider_request_id": result.provider_request_id,
        "attempts": result.attempts,
        "usage_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in result.usage_records
        ),
        "total_ai_cost_eur": result.total_ai_cost_eur,
        "output_payload": result.output.model_dump(mode="json"),
        "recommendation_fingerprint_sha256": result.recommendation_fingerprint_sha256,
        "advisory_report_fingerprint_sha256": result.advisory_report.fingerprint_sha256,
    }


@dataclass(frozen=True, slots=True)
class MasterProfessorShadowAdvisoryResult:
    status: MasterProfessorShadowStatus
    master_portfolio_id: str
    analysis_id: str
    analysis_fingerprint_sha256: str
    current_policy_fingerprint_sha256: str
    candidate_fingerprints_sha256: tuple[str, ...]
    gateway_config_fingerprint_sha256: str
    gateway_request_id: str
    gateway_route_id: str
    gateway_model_id: str
    provider_request_id: str | None
    attempts: int
    usage_records: tuple[MasterProfessorShadowUsageRecord, ...]
    total_ai_cost_eur: Decimal
    output: MasterProfessorShadowOutput
    recommendation_fingerprint_sha256: str
    advisory_report: MasterAllocationAdvisoryReport
    fingerprint_sha256: str
    advisor_role: str = field(default="MASTER_PROFESSOR", init=False)
    mode: str = field(default="SHADOW", init=False)
    advisory_only: bool = field(default=True, init=False)
    operator_review_required: bool = field(default=True, init=False)
    auto_apply: bool = field(default=False, init=False)
    numeric_allocation_generation: bool = field(default=False, init=False)
    policy_mutation: bool = field(default=False, init=False)
    reservation_authority: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in (
            "master_portfolio_id",
            "analysis_id",
            "gateway_request_id",
            "gateway_route_id",
            "gateway_model_id",
        ):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), field_name=name),
            )
        object.__setattr__(
            self,
            "provider_request_id",
            _optional_text(self.provider_request_id, field_name="provider_request_id"),
        )
        for name in (
            "analysis_fingerprint_sha256",
            "current_policy_fingerprint_sha256",
            "gateway_config_fingerprint_sha256",
            "recommendation_fingerprint_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), field_name=name))
        object.__setattr__(
            self,
            "candidate_fingerprints_sha256",
            _canonical_sha_values(
                self.candidate_fingerprints_sha256,
                field_name="candidate_fingerprints_sha256",
            ),
        )
        if self.status is not MasterProfessorShadowStatus.COMPLETED:
            raise ValueError("Master Professor SHADOW result status must be COMPLETED")
        if isinstance(self.attempts, bool) or self.attempts < 1:
            raise ValueError("Master Professor attempts must be an integer >= 1")
        if not self.usage_records:
            raise ValueError("Master Professor SHADOW result requires AI usage evidence")
        if self.attempts != max(item.attempt for item in self.usage_records):
            raise ValueError("Master Professor attempts do not match usage evidence")
        expected_cost = sum((item.estimated_cost_eur for item in self.usage_records), ZERO)
        object.__setattr__(
            self,
            "total_ai_cost_eur",
            _non_negative_decimal(self.total_ai_cost_eur, field_name="total_ai_cost_eur"),
        )
        if self.total_ai_cost_eur != expected_cost:
            raise ValueError("Master Professor total AI cost does not match usage records")
        for usage in self.usage_records:
            if usage.request_id != self.gateway_request_id:
                raise ValueError("Master Professor usage request_id mismatch")
            if usage.system_id != self.master_portfolio_id:
                raise ValueError("Master Professor usage Master Portfolio mismatch")
            if usage.agent_id != MASTER_PROFESSOR_AGENT_ID:
                raise ValueError("Master Professor usage agent_id mismatch")
            if usage.route_id != self.gateway_route_id:
                raise ValueError("Master Professor usage route_id mismatch")
            if usage.model_id != self.gateway_model_id:
                raise ValueError("Master Professor usage model_id mismatch")
        if self.advisory_report.master_portfolio_id != self.master_portfolio_id:
            raise ValueError("Master Professor advisory report Master Portfolio mismatch")
        if self.advisory_report.current_allocation_policy.fingerprint_sha256 != (
            self.current_policy_fingerprint_sha256
        ):
            raise ValueError("Master Professor advisory report current policy mismatch")
        if self.advisory_report.recommendation.fingerprint_sha256 != (
            self.recommendation_fingerprint_sha256
        ):
            raise ValueError("Master Professor recommendation fingerprint mismatch")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master Professor SHADOW result schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        if normalized != stable_digest(master_professor_shadow_result_payload(self)):
            raise ValueError("Master Professor SHADOW result fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_professor_shadow_result_payload(self)


def _recommendation_from_output(
    *,
    output: MasterProfessorShadowOutput,
    current_allocation_policy: MasterAllocationPolicy,
    candidates: tuple[MasterProfessorAllocationCandidate, ...],
    source_ref: str,
):
    if output.action is MasterAllocationAdvisoryAction.KEEP_CURRENT:
        proposed = current_allocation_policy.envelopes
    elif output.action is MasterAllocationAdvisoryAction.PROPOSE_CHANGE:
        candidate_map = {item.candidate_id: item for item in candidates}
        selected = candidate_map[output.selected_candidate_id]
        proposed = selected.proposed_envelopes
    else:
        proposed = ()
    return build_master_allocation_advisory_recommendation(
        action=output.action,
        proposed_envelopes=proposed,
        rationale_codes=output.rationale_codes,
        source_ref=source_ref,
    )


async def run_master_professor_shadow_advisory(
    *,
    gateway: MasterProfessorStructuredGateway,
    current_allocation_policy: MasterAllocationPolicy,
    evidence: tuple[MasterAllocationAdvisoryEvidence, ...],
    analysis: MasterAllocationEvidenceAnalysisReport,
    candidates: tuple[MasterProfessorAllocationCandidate, ...],
    config: MasterProfessorShadowGatewayConfig,
) -> MasterProfessorShadowAdvisoryResult:
    """Call only the AI Gateway, validate the SHADOW choice, then build Step 1 advisory output."""

    ordered_candidates = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    ordered_evidence = _validate_analysis_context(
        current_allocation_policy=current_allocation_policy,
        evidence=evidence,
        analysis=analysis,
        candidates=ordered_candidates,
    )
    request = build_master_professor_shadow_gateway_request(
        current_allocation_policy=current_allocation_policy,
        evidence=ordered_evidence,
        analysis=analysis,
        candidates=ordered_candidates,
        config=config,
    )
    gateway_result = await gateway.generate_structured(request, MasterProfessorShadowOutput)
    if gateway_result.request_id != request.request_id:
        raise ValueError("Master Professor gateway result request_id mismatch")
    output = validate_master_professor_shadow_output(
        output=gateway_result.output,
        current_allocation_policy=current_allocation_policy,
        analysis=analysis,
        candidates=ordered_candidates,
    )
    source_ref = (
        f"ai-gateway:{gateway_result.request_id}:{gateway_result.route_id}:"
        f"{gateway_result.model_id}"
    )
    recommendation = _recommendation_from_output(
        output=output,
        current_allocation_policy=current_allocation_policy,
        candidates=ordered_candidates,
        source_ref=source_ref,
    )
    advisory_report = build_master_allocation_advisory_report(
        current_allocation_policy=current_allocation_policy,
        evidence=ordered_evidence,
        recommendation=recommendation,
    )
    source_usage = gateway_result.usage_records or (gateway_result.usage,)
    usage_records = tuple(_usage_record(item) for item in source_usage)
    total_cost = sum((item.estimated_cost_eur for item in usage_records), ZERO)
    values = {
        "status": MasterProfessorShadowStatus.COMPLETED,
        "master_portfolio_id": current_allocation_policy.master_portfolio_id,
        "analysis_id": analysis.analysis_id,
        "analysis_fingerprint_sha256": analysis.fingerprint_sha256,
        "current_policy_fingerprint_sha256": current_allocation_policy.fingerprint_sha256,
        "candidate_fingerprints_sha256": tuple(
            sorted(item.fingerprint_sha256 for item in ordered_candidates)
        ),
        "gateway_config_fingerprint_sha256": config.fingerprint_sha256,
        "gateway_request_id": str(gateway_result.request_id),
        "gateway_route_id": gateway_result.route_id,
        "gateway_model_id": gateway_result.model_id,
        "provider_request_id": gateway_result.provider_request_id,
        "attempts": gateway_result.attempts,
        "usage_records": usage_records,
        "total_ai_cost_eur": total_cost,
        "output": output,
        "recommendation_fingerprint_sha256": recommendation.fingerprint_sha256,
        "advisory_report": advisory_report,
    }
    provisional = MasterProfessorShadowAdvisoryResult.__new__(
        MasterProfessorShadowAdvisoryResult
    )
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterProfessorShadowAdvisoryResult(
        **values,
        fingerprint_sha256=stable_digest(master_professor_shadow_result_payload(provisional)),
    )


__all__ = [
    "MASTER_PROFESSOR_AGENT_ID",
    "MasterProfessorAllocationCandidate",
    "MasterProfessorAllocationCandidateSource",
    "MasterProfessorShadowAdvisoryResult",
    "MasterProfessorShadowGatewayConfig",
    "MasterProfessorShadowOutput",
    "MasterProfessorShadowStatus",
    "MasterProfessorShadowUsageRecord",
    "MasterProfessorStructuredGateway",
    "build_master_professor_allocation_candidate",
    "build_master_professor_shadow_gateway_config",
    "build_master_professor_shadow_gateway_request",
    "master_professor_allocation_candidate_payload",
    "master_professor_shadow_config_payload",
    "master_professor_shadow_result_payload",
    "run_master_professor_shadow_advisory",
    "validate_master_professor_shadow_output",
]
