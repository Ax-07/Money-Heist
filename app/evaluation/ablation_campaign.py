from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import TypeVar

from app.services.backtest.ids import stable_digest, stable_uuid
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.reports import BacktestPeriodReport

from .ablation import AblationRunDescriptor

_RESERVED_EXECUTION_KEYS = frozenset(
    {
        "ablation_campaign_id",
        "ablation_comparison_fingerprint",
        "ablation_variant",
        "ablation_excluded_agent",
        "ablation_included_agents",
    }
)

T = TypeVar("T")


class AblationCampaignVariantKind(StrEnum):
    BASELINE = "BASELINE"
    WITHOUT_AGENT = "WITHOUT_AGENT"


def _normalize_agent_ids(values: Sequence[str], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(sorted(str(value).strip().lower() for value in values))
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if any(not value for value in normalized):
        raise ValueError(f"{field_name} must not contain blank agent ids")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _base_campaign_payload(
    source_run: BacktestRun,
    *,
    baseline_agents: tuple[str, ...],
    target_agents: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema": "money-heist.ablation-campaign.v1",
        "source_run_id": source_run.run_id,
        "dataset": source_run.dataset.canonical_payload(),
        "config": source_run.config.canonical_payload(),
        "period_start": source_run.period_start,
        "period_end": source_run.period_end,
        "baseline_agents": baseline_agents,
        "target_agents": target_agents,
    }


def _variant_config(
    base_config: BacktestConfig,
    *,
    campaign_id: str,
    comparison_fingerprint: str,
    kind: AblationCampaignVariantKind,
    excluded_agent_id: str | None,
    included_agents: tuple[str, ...],
) -> BacktestConfig:
    assumptions = dict(base_config.execution_assumptions)
    collision = sorted(_RESERVED_EXECUTION_KEYS.intersection(assumptions))
    if collision:
        raise ValueError(
            "BacktestConfig.execution_assumptions already uses reserved ablation keys: "
            + ", ".join(collision)
        )
    assumptions.update(
        {
            "ablation_campaign_id": campaign_id,
            "ablation_comparison_fingerprint": comparison_fingerprint,
            "ablation_variant": kind.value,
            "ablation_excluded_agent": excluded_agent_id or "NONE",
            "ablation_included_agents": ",".join(included_agents),
        }
    )
    return replace(base_config, execution_assumptions=assumptions)


@dataclass(frozen=True, slots=True)
class AblationCampaignVariant:
    campaign_id: str
    variant_id: str
    kind: AblationCampaignVariantKind
    excluded_agent_id: str | None
    baseline_agents: tuple[str, ...]
    included_agents: tuple[str, ...]
    comparison_fingerprint: str
    run: BacktestRun

    def __post_init__(self) -> None:
        if not self.campaign_id.strip():
            raise ValueError("campaign_id must not be blank")
        if not self.variant_id.strip():
            raise ValueError("variant_id must not be blank")
        if not self.comparison_fingerprint.strip():
            raise ValueError("comparison_fingerprint must not be blank")
        baseline = _normalize_agent_ids(self.baseline_agents, field_name="baseline_agents")
        included = _normalize_agent_ids(self.included_agents, field_name="included_agents")
        if not set(included).issubset(baseline):
            raise ValueError("included_agents must be a subset of baseline_agents")
        object.__setattr__(self, "baseline_agents", baseline)
        object.__setattr__(self, "included_agents", included)

        if self.kind is AblationCampaignVariantKind.BASELINE:
            if self.excluded_agent_id is not None:
                raise ValueError("baseline variant cannot exclude an agent")
            if included != baseline:
                raise ValueError("baseline variant must include every baseline agent")
            return

        excluded = (self.excluded_agent_id or "").strip().lower()
        if not excluded:
            raise ValueError("WITHOUT_AGENT variant requires excluded_agent_id")
        if excluded not in baseline:
            raise ValueError("excluded agent must belong to baseline_agents")
        if excluded in included:
            raise ValueError("excluded agent must be absent from included_agents")
        if set(baseline) - set(included) != {excluded}:
            raise ValueError("WITHOUT_AGENT variant must remove exactly one agent")
        object.__setattr__(self, "excluded_agent_id", excluded)

    def to_descriptor(self, report: BacktestPeriodReport) -> AblationRunDescriptor:
        if report.run_id != self.run.run_id:
            raise ValueError("period report run_id does not match campaign variant")
        if report.dataset_id != self.run.dataset.dataset_id:
            raise ValueError("period report dataset_id does not match campaign variant")
        if report.period_start != self.run.period_start:
            raise ValueError("period report period_start does not match campaign variant")
        if report.period_end != self.run.period_end:
            raise ValueError("period report period_end does not match campaign variant")
        return AblationRunDescriptor(
            report=report,
            comparison_fingerprint=self.comparison_fingerprint,
            included_agents=self.included_agents,
        )


@dataclass(frozen=True, slots=True)
class AblationCampaignPlan:
    campaign_id: str
    comparison_fingerprint: str
    source_run_id: str
    baseline_agents: tuple[str, ...]
    target_agents: tuple[str, ...]
    variants: tuple[AblationCampaignVariant, ...]

    def __post_init__(self) -> None:
        if not self.campaign_id.strip():
            raise ValueError("campaign_id must not be blank")
        if not self.comparison_fingerprint.strip():
            raise ValueError("comparison_fingerprint must not be blank")
        if not self.source_run_id.strip():
            raise ValueError("source_run_id must not be blank")
        baseline = _normalize_agent_ids(self.baseline_agents, field_name="baseline_agents")
        targets = _normalize_agent_ids(self.target_agents, field_name="target_agents")
        if not set(targets).issubset(baseline):
            raise ValueError("target_agents must be a subset of baseline_agents")
        object.__setattr__(self, "baseline_agents", baseline)
        object.__setattr__(self, "target_agents", targets)

        if len(self.variants) != len(targets) + 1:
            raise ValueError("campaign must contain one baseline plus one variant per target")
        baseline_variants = [
            item for item in self.variants if item.kind is AblationCampaignVariantKind.BASELINE
        ]
        if len(baseline_variants) != 1:
            raise ValueError("campaign must contain exactly one baseline variant")
        excluded = tuple(
            sorted(
                item.excluded_agent_id
                for item in self.variants
                if item.kind is AblationCampaignVariantKind.WITHOUT_AGENT
                and item.excluded_agent_id is not None
            )
        )
        if excluded != targets:
            raise ValueError("campaign ablation variants must match target_agents exactly")
        if len({item.variant_id for item in self.variants}) != len(self.variants):
            raise ValueError("campaign variant ids must be unique")
        if len({item.run.run_id for item in self.variants}) != len(self.variants):
            raise ValueError("campaign run ids must be unique")
        if any(item.campaign_id != self.campaign_id for item in self.variants):
            raise ValueError("all variants must belong to the campaign")
        if any(
            item.comparison_fingerprint != self.comparison_fingerprint
            for item in self.variants
        ):
            raise ValueError("all variants must share comparison_fingerprint")

    @property
    def baseline(self) -> AblationCampaignVariant:
        return next(
            item for item in self.variants if item.kind is AblationCampaignVariantKind.BASELINE
        )

    @property
    def ablations(self) -> tuple[AblationCampaignVariant, ...]:
        return tuple(
            item
            for item in self.variants
            if item.kind is AblationCampaignVariantKind.WITHOUT_AGENT
        )

    def without_agent(self, agent_id: str) -> AblationCampaignVariant:
        normalized = agent_id.strip().lower()
        for variant in self.ablations:
            if variant.excluded_agent_id == normalized:
                return variant
        raise KeyError(f"agent is not an ablation target: {agent_id}")


def build_ablation_campaign(
    source_run: BacktestRun,
    *,
    included_agents: Sequence[str],
    target_agents: Sequence[str] | None = None,
) -> AblationCampaignPlan:
    baseline_agents = _normalize_agent_ids(included_agents, field_name="included_agents")
    targets = _normalize_agent_ids(
        target_agents if target_agents is not None else baseline_agents,
        field_name="target_agents",
    )
    if not set(targets).issubset(baseline_agents):
        raise ValueError("target_agents must be a subset of included_agents")

    collisions = sorted(
        _RESERVED_EXECUTION_KEYS.intersection(source_run.config.execution_assumptions)
    )
    if collisions:
        raise ValueError(
            "source run already contains reserved ablation execution assumptions: "
            + ", ".join(collisions)
        )

    payload = _base_campaign_payload(
        source_run,
        baseline_agents=baseline_agents,
        target_agents=targets,
    )
    campaign_id = stable_uuid("ablation-campaign", payload)
    comparison_fingerprint = stable_digest(
        {
            "schema": "money-heist.ablation-comparison.v1",
            "campaign_id": campaign_id,
            "payload": payload,
        }
    )

    variants: list[AblationCampaignVariant] = []
    specifications = [
        (AblationCampaignVariantKind.BASELINE, None, baseline_agents),
        *[
            (
                AblationCampaignVariantKind.WITHOUT_AGENT,
                agent_id,
                tuple(item for item in baseline_agents if item != agent_id),
            )
            for agent_id in targets
        ],
    ]
    for kind, excluded_agent_id, variant_agents in specifications:
        config = _variant_config(
            source_run.config,
            campaign_id=campaign_id,
            comparison_fingerprint=comparison_fingerprint,
            kind=kind,
            excluded_agent_id=excluded_agent_id,
            included_agents=variant_agents,
        )
        run = BacktestRun.create(
            dataset=source_run.dataset,
            config=config,
            period_start=source_run.period_start,
            period_end=source_run.period_end,
        )
        variant_id = stable_uuid(
            "ablation-campaign-variant",
            {
                "campaign_id": campaign_id,
                "kind": kind,
                "excluded_agent_id": excluded_agent_id,
                "included_agents": variant_agents,
                "run_id": run.run_id,
            },
        )
        variants.append(
            AblationCampaignVariant(
                campaign_id=campaign_id,
                variant_id=variant_id,
                kind=kind,
                excluded_agent_id=excluded_agent_id,
                baseline_agents=baseline_agents,
                included_agents=variant_agents,
                comparison_fingerprint=comparison_fingerprint,
                run=run,
            )
        )

    return AblationCampaignPlan(
        campaign_id=campaign_id,
        comparison_fingerprint=comparison_fingerprint,
        source_run_id=source_run.run_id,
        baseline_agents=baseline_agents,
        target_agents=targets,
        variants=tuple(variants),
    )


def build_variant_specialists(
    variant: AblationCampaignVariant,
    specialists: Mapping[str, T],
) -> Mapping[str, T]:
    normalized: dict[str, T] = {}
    for raw_agent_id, specialist in specialists.items():
        agent_id = str(raw_agent_id).strip().lower()
        if not agent_id:
            raise ValueError("specialist mapping must not contain blank agent ids")
        if agent_id in normalized:
            raise ValueError("specialist mapping contains duplicate normalized agent ids")
        normalized[agent_id] = specialist

    actual = set(normalized)
    expected = set(variant.baseline_agents)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected))
        message = "specialist mapping does not match campaign baseline: " + "; ".join(details)
        raise ValueError(message)

    selected = {agent_id: normalized[agent_id] for agent_id in variant.included_agents}
    return MappingProxyType(selected)


__all__ = [
    "AblationCampaignPlan",
    "AblationCampaignVariant",
    "AblationCampaignVariantKind",
    "build_ablation_campaign",
    "build_variant_specialists",
]
