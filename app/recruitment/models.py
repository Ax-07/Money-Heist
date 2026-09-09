from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RecruitmentCandidateState(StrEnum):
    """Recruitment-only lifecycle state.

    This enum is deliberately separate from ``app.agents.models.AgentState``.
    A recruitment candidate is not an operational AgentRegistry entry.
    """

    PROPOSED = "PROPOSED"
    CANDIDATE = "CANDIDATE"
    SHADOW = "SHADOW"
    PROBATION = "PROBATION"
    REJECTED = "REJECTED"
    PROMOTION_RECOMMENDED = "PROMOTION_RECOMMENDED"


class RecruitmentMetricDirection(StrEnum):
    AT_LEAST = "AT_LEAST"
    AT_MOST = "AT_MOST"


class RecruitmentSuccessCriterion(BaseModel):
    """One pre-registered numeric success criterion.

    The criterion says what will be judged; it does not decide whether a candidate
    is recruited. OOS is mandatory for criteria used by recruitment advisory.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_key: str = Field(min_length=1, max_length=120)
    direction: RecruitmentMetricDirection
    threshold: Decimal = Field(allow_inf_nan=False)
    primary: bool = False
    evidence_role: Literal["OOS"] = "OOS"
    rationale: str = Field(min_length=1, max_length=1000)

    @field_validator("metric_key", "rationale")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class RecruitmentBaselineSpec(BaseModel):
    """Pre-declared baseline against which a candidate must be compared."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_id: str = Field(min_length=1, max_length=200)
    system_id: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    comparison_method: Literal["TWIN_BASELINE_VS_CANDIDATE"] = (
        "TWIN_BASELINE_VS_CANDIDATE"
    )

    @field_validator("baseline_id", "system_id", "description")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class RecruitmentProposal(BaseModel):
    """Auditable hypothesis proposing a new specialist, without operational authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    recruitment_id: str = Field(min_length=1, max_length=200)
    proposed_name: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=120)
    problem: str = Field(min_length=1, max_length=2000)
    hypothesis: str = Field(min_length=1, max_length=2000)
    trigger_evidence_refs: tuple[str, ...] = Field(min_length=1)
    state: Literal[RecruitmentCandidateState.PROPOSED] = (
        RecruitmentCandidateState.PROPOSED
    )
    auto_apply: Literal[False] = False

    @field_validator(
        "recruitment_id",
        "proposed_name",
        "role",
        "problem",
        "hypothesis",
    )
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("trigger_evidence_refs")
    @classmethod
    def _validate_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("trigger_evidence_refs must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("trigger_evidence_refs must not contain duplicates")
        return normalized


class RecruitmentCandidateSpec(BaseModel):
    """Frozen candidate specification created before any evaluation campaign.

    It intentionally has no AgentRegistryEntry, broker, Risk Engine, LIVE mode, or
    permission mutation fields. Later steps may evaluate this specification, but
    cannot turn it into operational authority automatically.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    recruitment_id: str = Field(min_length=1, max_length=200)
    proposed_name: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=120)
    problem: str = Field(min_length=1, max_length=2000)
    hypothesis: str = Field(min_length=1, max_length=2000)
    required_data: tuple[str, ...] = Field(min_length=1)
    allowed_tools: tuple[str, ...] = ()
    model_class: str = Field(min_length=1, max_length=120)
    budget_limit_eur: Decimal = Field(gt=0, allow_inf_nan=False)
    evaluation_window: str = Field(min_length=1, max_length=500)
    baseline: RecruitmentBaselineSpec
    success_criteria: tuple[RecruitmentSuccessCriterion, ...] = Field(min_length=1)
    state: Literal[RecruitmentCandidateState.CANDIDATE] = (
        RecruitmentCandidateState.CANDIDATE
    )
    core_function: Literal[False] = False
    live_authority: Literal[False] = False
    auto_register: Literal[False] = False
    auto_promote: Literal[False] = False

    @field_validator(
        "recruitment_id",
        "proposed_name",
        "role",
        "problem",
        "hypothesis",
        "model_class",
        "evaluation_window",
    )
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("required_data", "allowed_tools")
    @classmethod
    def _normalize_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("list values must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("list values must not contain duplicates")
        return normalized

    @field_validator("allowed_tools")
    @classmethod
    def _secure_tools(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        forbidden_fragments = (
            "broker",
            "exchange",
            "secret",
            "risk_engine",
            "shell",
            "filesystem",
            "withdraw",
            "live_order",
            "permission",
        )
        for tool in values:
            normalized = tool.lower()
            if any(fragment in normalized for fragment in forbidden_fragments):
                raise ValueError(f"unsafe candidate tool: {tool}")
        return values

    @model_validator(mode="after")
    def _validate_success_criteria(self) -> RecruitmentCandidateSpec:
        keys = [criterion.metric_key for criterion in self.success_criteria]
        if len(set(keys)) != len(keys):
            raise ValueError("success_criteria metric_key values must be unique")
        primary_count = sum(criterion.primary for criterion in self.success_criteria)
        if primary_count != 1:
            raise ValueError("exactly one success criterion must be primary")
        return self


def specify_recruitment_candidate(
    proposal: RecruitmentProposal,
    *,
    required_data: tuple[str, ...],
    allowed_tools: tuple[str, ...],
    model_class: str,
    budget_limit_eur: Decimal,
    evaluation_window: str,
    baseline: RecruitmentBaselineSpec,
    success_criteria: tuple[RecruitmentSuccessCriterion, ...],
) -> RecruitmentCandidateSpec:
    """Deterministically turn an approved-for-specification proposal into a candidate spec.

    This is a pure constructor. It does not mutate AgentRegistry and does not perform
    a recruitment/promotion decision.
    """

    return RecruitmentCandidateSpec(
        recruitment_id=proposal.recruitment_id,
        proposed_name=proposal.proposed_name,
        role=proposal.role,
        problem=proposal.problem,
        hypothesis=proposal.hypothesis,
        required_data=required_data,
        allowed_tools=allowed_tools,
        model_class=model_class,
        budget_limit_eur=budget_limit_eur,
        evaluation_window=evaluation_window,
        baseline=baseline,
        success_criteria=success_criteria,
    )
