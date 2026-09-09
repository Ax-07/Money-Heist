from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .advisory import RECRUITMENT_ADVISORY_METRIC_KEYS, RecruitmentAdvisoryAction
from .advisory_audit import RecruitmentAdvisoryAuditFreshness
from .advisory_transition import RecruitmentAdvisoryTransitionStatus
from .evidence_gate import RecruitmentEvidencePurpose
from .lifecycle import RecruitmentLifecycleAction
from .models import RecruitmentCandidateState


class RecruitmentApiContractVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)


class RecruitmentApiCapabilities(BaseModel):
    """Read-only public surface for the Batch 19 Recruitment Engine.

    This object advertises contracts and safety boundaries only. It never exposes
    an endpoint capable of applying lifecycle, registry, promotion, risk or LIVE changes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_version: Literal["batch19.recruitment-api.v1"] = "batch19.recruitment-api.v1"
    mode: Literal["ADVISORY_READ_ONLY"] = "ADVISORY_READ_ONLY"
    http_methods: tuple[Literal["GET"], ...] = ("GET",)
    candidate_states: tuple[str, ...]
    lifecycle_actions: tuple[str, ...]
    advisory_actions: tuple[str, ...]
    advisory_transition_statuses: tuple[str, ...]
    audit_freshness_states: tuple[str, ...]
    evidence_purposes: tuple[str, ...]
    advisory_metric_keys: tuple[str, ...]
    contract_versions: tuple[RecruitmentApiContractVersion, ...]
    operator_authorization_required: Literal[True] = True
    auto_apply: Literal[False] = False
    registry_mutation: Literal[False] = False
    lifecycle_transition_applied: Literal[False] = False
    promotion_applied: Literal[False] = False
    live_authority: Literal[False] = False


def get_recruitment_api_capabilities() -> RecruitmentApiCapabilities:
    return RecruitmentApiCapabilities(
        candidate_states=tuple(state.value for state in RecruitmentCandidateState),
        lifecycle_actions=tuple(action.value for action in RecruitmentLifecycleAction),
        advisory_actions=tuple(action.value for action in RecruitmentAdvisoryAction),
        advisory_transition_statuses=tuple(
            status.value for status in RecruitmentAdvisoryTransitionStatus
        ),
        audit_freshness_states=tuple(
            state.value for state in RecruitmentAdvisoryAuditFreshness
        ),
        evidence_purposes=tuple(purpose.value for purpose in RecruitmentEvidencePurpose),
        advisory_metric_keys=tuple(sorted(RECRUITMENT_ADVISORY_METRIC_KEYS)),
        contract_versions=(
            RecruitmentApiContractVersion(
                name="candidate_spec",
                version="money-heist.recruitment-candidate-spec.v1",
            ),
            RecruitmentApiContractVersion(
                name="candidate_evidence_package",
                version="batch19.candidate-evidence-package.v1",
            ),
            RecruitmentApiContractVersion(
                name="recruitment_advisory",
                version="batch19.recruitment-advisory.v1",
            ),
            RecruitmentApiContractVersion(
                name="advisory_transition_planning",
                version="batch19.recruitment-advisory-transition.v1",
            ),
            RecruitmentApiContractVersion(
                name="advisory_audit",
                version="batch19.recruitment-advisory-audit.v1",
            ),
        ),
    )


__all__ = [
    "RecruitmentApiCapabilities",
    "RecruitmentApiContractVersion",
    "get_recruitment_api_capabilities",
]
