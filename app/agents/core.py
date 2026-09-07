from __future__ import annotations

import json
from typing import Any, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel

from app.intelligence.ai_gateway.models import AIGatewayRequest, AIGatewayResult

from .models import LisbonReport, PalermoReview, ProfessorDecision, ProfessorPlan
from .prompts import CORE_PROMPTS, PromptRegistry
from .registry import CORE_AGENT_REGISTRY, AgentRegistry

T = TypeVar("T", bound=BaseModel)


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
    ) -> AIGatewayResult[T]:
        request = AIGatewayRequest(
            system_id=system_id,
            agent_id=self.agent_id,
            prompt_version=self.prompt.version,
            model_route=self.entry.model_route,
            input_text=json.dumps(payload, sort_keys=True, default=str),
            instructions=self.prompt.instructions,
            opportunity_id=opportunity_id,
            metadata={
                "agent_role": self.entry.role.value,
                "phase": phase,
            },
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
        opportunity_id: UUID | None = None,
    ) -> AIGatewayResult[ProfessorPlan]:
        return await self._run(
            system_id=system_id,
            payload={
                "opportunity": opportunity,
                "market_context": market_context,
                "available_agents": available_agents,
                "remaining_budget_eur": remaining_budget_eur,
            },
            output_model=ProfessorPlan,
            opportunity_id=opportunity_id,
            phase="plan",
        )

    async def finalize(
        self,
        *,
        system_id: str,
        opportunity: dict[str, Any],
        market_context: dict[str, Any],
        specialist_analyses: list[dict[str, Any]],
        palermo_review: dict[str, Any],
        opportunity_id: UUID | None = None,
    ) -> AIGatewayResult[ProfessorDecision]:
        return await self._run(
            system_id=system_id,
            payload={
                "opportunity": opportunity,
                "market_context": market_context,
                "specialist_analyses": specialist_analyses,
                "palermo_review": palermo_review,
            },
            output_model=ProfessorDecision,
            opportunity_id=opportunity_id,
            phase="finalize",
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
        opportunity_id: UUID | None = None,
    ) -> AIGatewayResult[PalermoReview]:
        return await self._run(
            system_id=system_id,
            payload={
                "market_context": market_context,
                "specialist_analyses": specialist_analyses,
                "provisional_thesis": provisional_thesis,
            },
            output_model=PalermoReview,
            opportunity_id=opportunity_id,
            phase="red_team",
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
