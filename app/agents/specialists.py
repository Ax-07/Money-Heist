from __future__ import annotations

from typing import Any
from uuid import UUID

from app.intelligence.ai_gateway.models import AIGatewayResult

from .core import CoreAgent, StructuredGateway
from .models import BerlinAnalysis, NairobiAnalysis, SpecialistAnalysis, TokyoAnalysis
from .prompts import SPECIALIST_PROMPTS, PromptRegistry
from .registry import AgentRegistry, SPECIALIST_AGENT_REGISTRY

_CONTAMINATION_KEYS = frozenset(
    {
        "specialist_analysis",
        "specialist_analyses",
        "other_agent_analysis",
        "other_agent_analyses",
        "agent_conclusions",
        "crew_consensus",
        "palermo_review",
        "professor_decision",
        "provisional_thesis",
    }
)


class SpecialistInputContaminationError(ValueError):
    """Raised before an independent first-round request sees another agent conclusion."""


class UngroundedEvidenceError(ValueError):
    """Raised when a specialist cites a field that was not present in its input."""


def _iter_mapping_keys(value: Any):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key).lower()
            yield from _iter_mapping_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _iter_mapping_keys(nested)


def _assert_independent_input(*values: Any) -> None:
    contaminated = sorted(
        key for value in values for key in _iter_mapping_keys(value) if key in _CONTAMINATION_KEYS
    )
    if contaminated:
        raise SpecialistInputContaminationError(
            f"independent round input contains agent conclusions: {', '.join(set(contaminated))}"
        )


def _leaf_paths(value: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            paths.update(_leaf_paths(nested, child))
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            child = f"{prefix}.{index}" if prefix else str(index)
            paths.update(_leaf_paths(nested, child))
    elif prefix:
        paths.add(prefix)
    return paths


def _assert_grounded_evidence(
    analysis: SpecialistAnalysis,
    *,
    opportunity: dict[str, Any],
    market_context: dict[str, Any],
) -> None:
    available_paths = _leaf_paths(
        {
            "opportunity": opportunity,
            "market_context": market_context,
        }
    )
    missing = sorted(
        evidence.source_key
        for evidence in analysis.evidence
        if evidence.source_key not in available_paths
    )
    if missing:
        raise UngroundedEvidenceError(
            f"specialist evidence references unavailable input fields: {', '.join(missing)}"
        )


class SpecialistAgent(CoreAgent):
    output_model: type[SpecialistAnalysis]

    def __init__(
        self,
        gateway: StructuredGateway,
        *,
        registry: AgentRegistry = SPECIALIST_AGENT_REGISTRY,
        prompts: PromptRegistry = SPECIALIST_PROMPTS,
    ) -> None:
        super().__init__(gateway, registry=registry, prompts=prompts)

    async def analyze(
        self,
        *,
        system_id: str,
        opportunity: dict[str, Any],
        market_context: dict[str, Any],
        opportunity_id: UUID | None = None,
    ) -> AIGatewayResult:
        _assert_independent_input(opportunity, market_context)
        result = await self._run(
            system_id=system_id,
            payload={
                "opportunity": opportunity,
                "market_context": market_context,
                "analysis_round": "INDEPENDENT_1",
            },
            output_model=self.output_model,
            opportunity_id=opportunity_id,
            phase="specialist_independent_round_1",
        )
        _assert_grounded_evidence(
            result.output,
            opportunity=opportunity,
            market_context=market_context,
        )
        return result


class Berlin(SpecialistAgent):
    agent_id = "berlin"
    output_model = BerlinAnalysis


class Tokyo(SpecialistAgent):
    agent_id = "tokyo"
    output_model = TokyoAnalysis


class Nairobi(SpecialistAgent):
    agent_id = "nairobi"
    output_model = NairobiAnalysis
