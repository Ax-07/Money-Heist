from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Any, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, create_model

from app.intelligence.ai_gateway.models import AIGatewayRequest, AIGatewayResult

from .models import LisbonReport, PalermoReview, ProfessorDecision, ProfessorPlan
from .prompts import CORE_PROMPTS, PromptRegistry
from .registry import CORE_AGENT_REGISTRY, AgentRegistry

T = TypeVar("T", bound=BaseModel)


def _grounded_json_paths(value: Any, prefix: str = "") -> set[str]:
    """Return exact dot-paths present in a JSON-like payload, including containers."""
    paths: set[str] = set()
    if prefix:
        paths.add(prefix)

    if isinstance(value, Mapping):
        for key, nested in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            paths.update(_grounded_json_paths(nested, child))
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            child = f"{prefix}.{index}" if prefix else str(index)
            paths.update(_grounded_json_paths(nested, child))

    return paths


def _grounded_json_leaf_paths(value: Any, prefix: str = "") -> set[str]:
    """Return only concrete scalar/list-item JSON paths; never container paths."""

    if isinstance(value, BaseModel):
        return _grounded_json_leaf_paths(
            value.model_dump(mode="json", exclude_none=True),
            prefix,
        )

    if isinstance(value, Mapping):
        paths: set[str] = set()
        for key, nested in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            paths.update(_grounded_json_leaf_paths(nested, child))
        return paths

    if isinstance(value, (list, tuple)):
        paths: set[str] = set()
        for index, nested in enumerate(value):
            child = f"{prefix}.{index}" if prefix else str(index)
            paths.update(_grounded_json_leaf_paths(nested, child))
        return paths

    if value is None or not prefix:
        return set()
    return {prefix}


class _IndexedFinalEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_index: int = Field(ge=0)
    observation: str = Field(min_length=1, max_length=1000)


def _indexed_final_output_model(
    output_model: type[T],
    allowed_source_keys: tuple[str, ...],
) -> type[T]:
    if not allowed_source_keys:
        raise ValueError("FINALIZE atomic evidence catalogue must not be empty")

    bounded_index = Annotated[
        int,
        Field(ge=0, le=len(allowed_source_keys) - 1),
    ]
    evidence_model = create_model(
        f"{output_model.__name__}IndexedEvidenceV5",
        __base__=_IndexedFinalEvidenceReference,
        source_index=(bounded_index, ...),
    )
    return create_model(
        output_model.__name__,
        __base__=output_model,
        evidence=(list[evidence_model], ...),
    )


def _canonicalize_indexed_final_result(
    result: AIGatewayResult[T],
    *,
    output_model: type[T],
    allowed_source_keys: tuple[str, ...],
) -> AIGatewayResult[T]:
    payload = result.output.model_dump(mode="python")
    canonical_evidence: list[dict[str, Any]] = []
    for item in payload.get("evidence", []):
        source_index = item.get("source_index")
        if not isinstance(source_index, int):
            raise ValueError("FINALIZE evidence item has no integer source_index")
        if source_index < 0 or source_index >= len(allowed_source_keys):
            raise ValueError("FINALIZE evidence source_index is outside the allowed range")
        canonical_evidence.append(
            {
                "source_key": allowed_source_keys[source_index],
                "observation": item["observation"],
            }
        )

    payload["evidence"] = canonical_evidence
    canonical_output = output_model.model_validate(payload)
    return result.model_copy(update={"output": canonical_output})


PALERMO_MAX_OUTPUT_TOKENS = 16384
PALERMO_TIMEOUT_SECONDS = 90.0


class StructuredGateway(Protocol):
    async def generate_structured(
        self,
        request: AIGatewayRequest,
        output_model: type[T],
    ) -> AIGatewayResult[T]: ...


class CoreAgent:
    agent_id: str

    def __init__(
        self,
        gateway: StructuredGateway,
        *,
        registry: AgentRegistry = CORE_AGENT_REGISTRY,
        prompts: PromptRegistry = CORE_PROMPTS,
    ) -> None:
        self.gateway = gateway
        self.registry = registry
        self.prompts = prompts
        self.entry = registry.get(self.agent_id)
        self.prompt = prompts.get(self.agent_id, self.entry.prompt_version)

    async def _run(
        self,
        *,
        system_id: str,
        payload: dict[str, Any],
        output_model: type[T],
        phase: str,
        opportunity_id: UUID | None = None,
        max_output_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> AIGatewayResult[T]:
        metadata = {
            "agent_role": self.entry.role.value,
            "phase": phase,
        }
        market_context = payload.get("market_context")
        if isinstance(market_context, Mapping):
            decision_context = market_context.get("decision_context")
            if isinstance(decision_context, Mapping):
                from app.services.decision_context import (
                    AGENT_CONTEXT_BINDING_VERSION,
                )

                context_id = decision_context.get("context_id")
                fingerprint = decision_context.get("context_fingerprint")
                if context_id and fingerprint:
                    metadata.update(
                        {
                            "decision_context_id": str(context_id),
                            "decision_context_fingerprint": str(fingerprint),
                            "decision_context_binding_version": (
                                AGENT_CONTEXT_BINDING_VERSION
                            ),
                        }
                    )

        request = AIGatewayRequest(
            system_id=system_id,
            agent_id=self.agent_id,
            prompt_version=self.prompt.version,
            model_route=self.entry.model_route,
            input_text=json.dumps(payload, sort_keys=True, default=str),
            instructions=self.prompt.instructions,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
            opportunity_id=opportunity_id,
            metadata=metadata,
        )
        return await self.gateway.generate_structured(request, output_model)


class TheProfessor(CoreAgent):
    agent_id = "professor"

    async def plan(
        self,
        *,
        system_id: str,
        opportunity: dict[str, Any],
        market_context: dict[str, Any],
        available_agents: list[str],
        remaining_budget_eur: float,
        planning_constraints: dict[str, Any] | None = None,
        opportunity_id: UUID | None = None,
    ) -> AIGatewayResult[ProfessorPlan]:
        payload = {
            "opportunity": opportunity,
            "market_context": market_context,
            "available_agents": available_agents,
            "remaining_budget_eur": remaining_budget_eur,
        }
        if planning_constraints is not None:
            payload["planning_constraints"] = planning_constraints

        return await self._run(
            system_id=system_id,
            payload=payload,
            output_model=ProfessorPlan,
            opportunity_id=opportunity_id,
            phase="plan",
        )

    async def finalize_with_schema(
        self,
        *,
        system_id: str,
        opportunity: dict[str, Any],
        market_context: dict[str, Any],
        specialist_analyses: list[dict[str, Any]],
        palermo_review: dict[str, Any],
        output_model: type[T],
        task_force_report: dict[str, Any] | None = None,
        opportunity_id: UUID | None = None,
    ) -> AIGatewayResult[T]:
        """Finalize through an explicit strict schema while preserving the existing API."""

        payload = {
            "opportunity": opportunity,
            "market_context": market_context,
            "specialist_analyses": specialist_analyses,
            "palermo_review": palermo_review,
        }
        if task_force_report is not None:
            payload["task_force_report"] = task_force_report

        provider_output_model = output_model
        allowed_source_keys: tuple[str, ...] | None = None

        # Keep historical Professor v4 behavior addressable, while production
        # v5 exposes only atomic leaf paths with explicit index->path mapping.
        if self.prompt.version == "v5":
            allowed_source_keys = tuple(
                sorted(_grounded_json_leaf_paths(payload))
            )
            payload["evidence_source_catalog"] = [
                {
                    "source_index": index,
                    "source_key": source_key,
                }
                for index, source_key in enumerate(allowed_source_keys)
            ]
            if "evidence" in output_model.model_fields:
                provider_output_model = _indexed_final_output_model(
                    output_model,
                    allowed_source_keys,
                )
        else:
            payload["allowed_evidence_source_keys"] = sorted(
                _grounded_json_paths(payload)
            )

        result = await self._run(
            system_id=system_id,
            payload=payload,
            output_model=provider_output_model,
            opportunity_id=opportunity_id,
            phase="finalize",
        )

        # Real v5 Gateway results use the request-specific indexed schema.
        # Lightweight custom gateways used by older tests may return the
        # canonical model directly; the downstream grounding validator remains.
        if (
            self.prompt.version == "v5"
            and allowed_source_keys is not None
            and result is not None
            and result.output.__class__ is provider_output_model
        ):
            result = _canonicalize_indexed_final_result(
                result,
                output_model=output_model,
                allowed_source_keys=allowed_source_keys,
            )
        return result

    async def finalize(
        self,
        *,
        system_id: str,
        opportunity: dict[str, Any],
        market_context: dict[str, Any],
        specialist_analyses: list[dict[str, Any]],
        palermo_review: dict[str, Any],
        task_force_report: dict[str, Any] | None = None,
        opportunity_id: UUID | None = None,
    ) -> AIGatewayResult[ProfessorDecision]:
        return await self.finalize_with_schema(
            system_id=system_id,
            opportunity=opportunity,
            market_context=market_context,
            specialist_analyses=specialist_analyses,
            palermo_review=palermo_review,
            output_model=ProfessorDecision,
            task_force_report=task_force_report,
            opportunity_id=opportunity_id,
        )


class Palermo(CoreAgent):
    agent_id = "palermo"

    async def review(
        self,
        *,
        system_id: str,
        market_context: dict[str, Any],
        specialist_analyses: list[dict[str, Any]],
        provisional_thesis: dict[str, Any],
        opportunity: dict[str, Any] | None = None,
        opportunity_id: UUID | None = None,
    ) -> AIGatewayResult[PalermoReview]:
        payload = {
            "market_context": market_context,
            "specialist_analyses": specialist_analyses,
            "provisional_thesis": provisional_thesis,
        }
        if opportunity is not None:
            payload["opportunity"] = opportunity

        return await self._run(
            system_id=system_id,
            payload=payload,
            output_model=PalermoReview,
            opportunity_id=opportunity_id,
            phase="red_team",
            max_output_tokens=PALERMO_MAX_OUTPUT_TOKENS,
            timeout_seconds=PALERMO_TIMEOUT_SECONDS,
        )


class Lisbon(CoreAgent):
    agent_id = "lisbon"

    async def assess(
        self,
        *,
        system_id: str,
        ai_metrics: dict[str, Any],
        agent_metrics: list[dict[str, Any]],
        opportunity_economics: dict[str, Any] | None = None,
        opportunity_id: UUID | None = None,
    ) -> AIGatewayResult[LisbonReport]:
        return await self._run(
            system_id=system_id,
            payload={
                "ai_metrics": ai_metrics,
                "agent_metrics": agent_metrics,
                "opportunity_economics": opportunity_economics or {},
            },
            output_model=LisbonReport,
            opportunity_id=opportunity_id,
            phase="economics",
        )
