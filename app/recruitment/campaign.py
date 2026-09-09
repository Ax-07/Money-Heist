from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Sequence

from app.services.backtest.ids import stable_digest, stable_uuid
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.splits import BacktestPeriodRole

from .models import RecruitmentCandidateSpec

_RESERVED_EXECUTION_KEYS = frozenset(
    {
        "recruitment_campaign_id",
        "recruitment_comparison_fingerprint",
        "recruitment_variant",
        "recruitment_candidate_agent_id",
        "recruitment_included_agents",
        "recruitment_period_role",
        "recruitment_baseline_id",
    }
)


class RecruitmentCampaignVariantKind(StrEnum):
    BASELINE = "BASELINE"
    WITH_CANDIDATE = "WITH_CANDIDATE"


def _normalize_agent_ids(values: Sequence[str], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(sorted(str(value).strip().lower() for value in values))
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if any(not value for value in normalized):
        raise ValueError(f"{field_name} must not contain blank agent ids")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def candidate_runtime_agent_id(candidate: RecruitmentCandidateSpec) -> str:
    """Stable evaluation-only identity; it is not an AgentRegistry entry."""

    normalized = candidate.recruitment_id.strip().lower()
    if not normalized:
        raise ValueError("recruitment_id must not be blank")
    return f"candidate:{normalized}"


def _candidate_payload(candidate: RecruitmentCandidateSpec) -> dict[str, object]:
    return candidate.model_dump(mode="json")


def _base_campaign_payload(
    source_run: BacktestRun,
    candidate: RecruitmentCandidateSpec,
    *,
    role: BacktestPeriodRole,
    baseline_agents: tuple[str, ...],
    runtime_agent_id: str,
) -> dict[str, object]:
    return {
        "schema": "money-heist.recruitment-campaign.v1",
        "source_run_id": source_run.run_id,
        "dataset": source_run.dataset.canonical_payload(),
        "config": source_run.config.canonical_payload(),
        "period_start": source_run.period_start,
        "period_end": source_run.period_end,
        "period_role": role,
        "candidate": _candidate_payload(candidate),
        "baseline_agents": baseline_agents,
        "candidate_runtime_agent_id": runtime_agent_id,
    }


def _variant_config(
    base_config: BacktestConfig,
    *,
    campaign_id: str,
    comparison_fingerprint: str,
    kind: RecruitmentCampaignVariantKind,
    candidate_agent_id: str,
    included_agents: tuple[str, ...],
    role: BacktestPeriodRole,
    baseline_id: str,
) -> BacktestConfig:
    assumptions = dict(base_config.execution_assumptions)
    collisions = sorted(_RESERVED_EXECUTION_KEYS.intersection(assumptions))
    if collisions:
        raise ValueError(
            "BacktestConfig.execution_assumptions already uses reserved recruitment keys: "
            + ", ".join(collisions)
        )
    assumptions.update(
        {
            "recruitment_campaign_id": campaign_id,
            "recruitment_comparison_fingerprint": comparison_fingerprint,
            "recruitment_variant": kind.value,
            "recruitment_candidate_agent_id": candidate_agent_id,
            "recruitment_included_agents": ",".join(included_agents),
            "recruitment_period_role": role.value,
            "recruitment_baseline_id": baseline_id,
        }
    )
    return replace(base_config, execution_assumptions=assumptions)


@dataclass(frozen=True, slots=True)
class RecruitmentCampaignVariant:
    campaign_id: str
    variant_id: str
    kind: RecruitmentCampaignVariantKind
    recruitment_id: str
    candidate_agent_id: str
    baseline_agents: tuple[str, ...]
    included_agents: tuple[str, ...]
    comparison_fingerprint: str
    role: BacktestPeriodRole
    run: BacktestRun
    execute: bool = False
    auto_apply: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "campaign_id",
            "variant_id",
            "recruitment_id",
            "candidate_agent_id",
            "comparison_fingerprint",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be blank")
        if self.execute or self.auto_apply or self.live_authority:
            raise ValueError("recruitment campaign variants are planning-only and non-LIVE")

        baseline = _normalize_agent_ids(self.baseline_agents, field_name="baseline_agents")
        included = _normalize_agent_ids(self.included_agents, field_name="included_agents")
        candidate_id = self.candidate_agent_id.strip().lower()
        object.__setattr__(self, "baseline_agents", baseline)
        object.__setattr__(self, "included_agents", included)
        object.__setattr__(self, "candidate_agent_id", candidate_id)

        if candidate_id in baseline:
            raise ValueError("candidate runtime id must not already belong to baseline_agents")
        if self.kind is RecruitmentCampaignVariantKind.BASELINE:
            if included != baseline:
                raise ValueError("baseline variant must include exactly baseline_agents")
            return
        expected = tuple(sorted((*baseline, candidate_id)))
        if included != expected:
            raise ValueError("WITH_CANDIDATE must add exactly the candidate to baseline_agents")


@dataclass(frozen=True, slots=True)
class RecruitmentCampaignPlan:
    campaign_id: str
    comparison_fingerprint: str
    recruitment_id: str
    baseline_id: str
    source_run_id: str
    candidate_agent_id: str
    role: BacktestPeriodRole
    baseline_agents: tuple[str, ...]
    variants: tuple[RecruitmentCampaignVariant, ...]
    success_criteria_fingerprint: str
    execute: bool = False
    auto_apply: bool = False
    registry_mutation: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        if self.execute or self.auto_apply or self.registry_mutation or self.live_authority:
            raise ValueError("recruitment campaign plans cannot execute, mutate registry, or go LIVE")
        for field_name in (
            "campaign_id",
            "comparison_fingerprint",
            "recruitment_id",
            "baseline_id",
            "source_run_id",
            "candidate_agent_id",
            "success_criteria_fingerprint",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be blank")
        baseline = _normalize_agent_ids(self.baseline_agents, field_name="baseline_agents")
        object.__setattr__(self, "baseline_agents", baseline)
        if len(self.variants) != 2:
            raise ValueError("recruitment campaign must contain exactly two variants")
        kinds = {variant.kind for variant in self.variants}
        if kinds != {
            RecruitmentCampaignVariantKind.BASELINE,
            RecruitmentCampaignVariantKind.WITH_CANDIDATE,
        }:
            raise ValueError("campaign requires BASELINE and WITH_CANDIDATE variants")
        if len({variant.variant_id for variant in self.variants}) != 2:
            raise ValueError("campaign variant ids must be unique")
        if len({variant.run.run_id for variant in self.variants}) != 2:
            raise ValueError("campaign run ids must be unique")
        if any(variant.campaign_id != self.campaign_id for variant in self.variants):
            raise ValueError("all variants must belong to the campaign")
        if any(
            variant.comparison_fingerprint != self.comparison_fingerprint
            for variant in self.variants
        ):
            raise ValueError("all variants must share comparison_fingerprint")
        if any(variant.role is not self.role for variant in self.variants):
            raise ValueError("all variants must share the campaign period role")
        if any(variant.baseline_agents != baseline for variant in self.variants):
            raise ValueError("all variants must share baseline_agents")

    @property
    def baseline(self) -> RecruitmentCampaignVariant:
        return next(
            variant
            for variant in self.variants
            if variant.kind is RecruitmentCampaignVariantKind.BASELINE
        )

    @property
    def with_candidate(self) -> RecruitmentCampaignVariant:
        return next(
            variant
            for variant in self.variants
            if variant.kind is RecruitmentCampaignVariantKind.WITH_CANDIDATE
        )


def build_recruitment_campaign(
    source_run: BacktestRun,
    candidate: RecruitmentCandidateSpec,
    *,
    role: BacktestPeriodRole,
    baseline_agents: Sequence[str],
) -> RecruitmentCampaignPlan:
    """Build a deterministic, non-executing twin plan for one candidate.

    Both variants reuse the same dataset, period and material BacktestConfig. They
    differ only through recruitment metadata and by adding the evaluation-only
    candidate identity to the WITH_CANDIDATE roster. Execution is a later step.
    """

    baseline = _normalize_agent_ids(baseline_agents, field_name="baseline_agents")
    runtime_agent_id = candidate_runtime_agent_id(candidate)
    if runtime_agent_id in baseline:
        raise ValueError("candidate runtime id must not already belong to baseline_agents")
    if candidate.baseline.system_id != source_run.config.system_id:
        raise ValueError("candidate baseline system_id must match source run system_id")

    collisions = sorted(
        _RESERVED_EXECUTION_KEYS.intersection(source_run.config.execution_assumptions)
    )
    if collisions:
        raise ValueError(
            "source run already contains reserved recruitment execution assumptions: "
            + ", ".join(collisions)
        )

    payload = _base_campaign_payload(
        source_run,
        candidate,
        role=role,
        baseline_agents=baseline,
        runtime_agent_id=runtime_agent_id,
    )
    campaign_id = stable_uuid("recruitment-campaign", payload)
    comparison_fingerprint = stable_digest(
        {
            "schema": "money-heist.recruitment-comparison.v1",
            "campaign_id": campaign_id,
            "payload": payload,
        }
    )
    success_criteria_fingerprint = stable_digest(
        {
            "schema": "money-heist.recruitment-success-criteria.v1",
            "recruitment_id": candidate.recruitment_id,
            "criteria": [
                criterion.model_dump(mode="json") for criterion in candidate.success_criteria
            ],
        }
    )

    specs = (
        (RecruitmentCampaignVariantKind.BASELINE, baseline),
        (
            RecruitmentCampaignVariantKind.WITH_CANDIDATE,
            tuple(sorted((*baseline, runtime_agent_id))),
        ),
    )
    variants: list[RecruitmentCampaignVariant] = []
    for kind, included_agents in specs:
        config = _variant_config(
            source_run.config,
            campaign_id=campaign_id,
            comparison_fingerprint=comparison_fingerprint,
            kind=kind,
            candidate_agent_id=runtime_agent_id,
            included_agents=included_agents,
            role=role,
            baseline_id=candidate.baseline.baseline_id,
        )
        run = BacktestRun.create(
            dataset=source_run.dataset,
            config=config,
            period_start=source_run.period_start,
            period_end=source_run.period_end,
        )
        variant_id = stable_uuid(
            "recruitment-campaign-variant",
            {
                "campaign_id": campaign_id,
                "kind": kind,
                "included_agents": included_agents,
                "run_id": run.run_id,
            },
        )
        variants.append(
            RecruitmentCampaignVariant(
                campaign_id=campaign_id,
                variant_id=variant_id,
                kind=kind,
                recruitment_id=candidate.recruitment_id,
                candidate_agent_id=runtime_agent_id,
                baseline_agents=baseline,
                included_agents=included_agents,
                comparison_fingerprint=comparison_fingerprint,
                role=role,
                run=run,
            )
        )

    return RecruitmentCampaignPlan(
        campaign_id=campaign_id,
        comparison_fingerprint=comparison_fingerprint,
        recruitment_id=candidate.recruitment_id,
        baseline_id=candidate.baseline.baseline_id,
        source_run_id=source_run.run_id,
        candidate_agent_id=runtime_agent_id,
        role=role,
        baseline_agents=baseline,
        variants=tuple(variants),
        success_criteria_fingerprint=success_criteria_fingerprint,
    )


__all__ = [
    "RecruitmentCampaignPlan",
    "RecruitmentCampaignVariant",
    "RecruitmentCampaignVariantKind",
    "build_recruitment_campaign",
    "candidate_runtime_agent_id",
]
