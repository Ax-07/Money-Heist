from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.intelligence.ai_gateway.models import AIGatewayResult

from .core import CoreAgent, StructuredGateway
from .models import (
    BerlinAnalysis,
    DenverAnalysis,
    DenverContext,
    NairobiAnalysis,
    RioAnalysis,
    RioContext,
    SpecialistAnalysis,
    TokyoAnalysis,
)
from .prompts import SPECIALIST_PROMPTS, PromptRegistry
from .registry import SPECIALIST_AGENT_REGISTRY, AgentRegistry

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


class SpecialistContextUnavailableError(ValueError):
    """Raised when a context-gated specialist is called without usable grounded data."""


class SpecialistContextMismatchError(ValueError):
    """Raised when an advanced output contradicts immutable context provenance."""


class UngroundedEvidenceError(ValueError):
    """Raised when a specialist cites a field that was not present in its input."""


def _iter_mapping_keys(value: Any):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key).lower()
            yield from _iter_mapping_keys(nested)
    elif isinstance(value, BaseModel):
        yield from _iter_mapping_keys(value.model_dump(mode="python"))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _iter_mapping_keys(nested)


def _assert_independent_input(*values: Any) -> None:
    contaminated = sorted(
        key
        for value in values
        for key in _iter_mapping_keys(value)
        if key in _CONTAMINATION_KEYS
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
    elif isinstance(value, BaseModel):
        paths.update(
            _leaf_paths(value.model_dump(mode="json", exclude_none=True), prefix)
        )
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
    specialist_context: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "opportunity": opportunity,
        "market_context": market_context,
    }
    if specialist_context is not None:
        payload["specialist_context"] = specialist_context
    available_paths = _leaf_paths(payload)
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
    context_model: type[BaseModel] | None = None

    def __init__(
        self,
        gateway: StructuredGateway,
        *,
        registry: AgentRegistry = SPECIALIST_AGENT_REGISTRY,
        prompts: PromptRegistry = SPECIALIST_PROMPTS,
    ) -> None:
        super().__init__(gateway, registry=registry, prompts=prompts)

    def prepare_context(
        self,
        raw_context: BaseModel | dict[str, Any] | None,
        *,
        observed_at: datetime | None = None,
    ) -> BaseModel | None:
        if self.context_model is None:
            if raw_context is not None:
                raise ValueError(f"{self.agent_id} does not accept specialist_context")
            return None
        if raw_context is None:
            return None
        context = (
            raw_context
            if isinstance(raw_context, self.context_model)
            else self.context_model.model_validate(raw_context)
        )
        if observed_at is not None:
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise ValueError("market observed_at must be timezone-aware")
            self._validate_context_time(context, observed_at.astimezone(UTC))
        if not bool(getattr(context, "usable", False)):
            return None
        return context

    def _validate_context_time(self, context: BaseModel, observed_at: datetime) -> None:
        return None

    def _validate_analysis_against_context(
        self,
        analysis: SpecialistAnalysis,
        context: BaseModel | None,
    ) -> None:
        return None

    async def analyze(
        self,
        *,
        system_id: str,
        opportunity: dict[str, Any],
        market_context: dict[str, Any],
        specialist_context: BaseModel | dict[str, Any] | None = None,
        opportunity_id: UUID | None = None,
    ) -> AIGatewayResult:
        prepared_context = self.prepare_context(specialist_context)
        if self.context_model is not None and prepared_context is None:
            raise SpecialistContextUnavailableError(
                f"{self.agent_id} requires usable specialist_context"
            )

        _assert_independent_input(opportunity, market_context, prepared_context)
        payload: dict[str, Any] = {
            "opportunity": opportunity,
            "market_context": market_context,
            "analysis_round": "INDEPENDENT_1",
        }
        context_payload = None
        if prepared_context is not None:
            context_payload = prepared_context.model_dump(
                mode="json", exclude_none=True
            )
            if isinstance(prepared_context, DenverContext):
                context_payload["sample_size_band"] = prepared_context.sample_size_band
            payload["specialist_context"] = context_payload

        result = await self._run(
            system_id=system_id,
            payload=payload,
            output_model=self.output_model,
            opportunity_id=opportunity_id,
            phase="specialist_independent_round_1",
        )
        _assert_grounded_evidence(
            result.output,
            opportunity=opportunity,
            market_context=market_context,
            specialist_context=context_payload,
        )
        self._validate_analysis_against_context(result.output, prepared_context)
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


class Rio(SpecialistAgent):
    agent_id = "rio"
    output_model = RioAnalysis
    context_model = RioContext

    def _validate_context_time(self, context: BaseModel, observed_at: datetime) -> None:
        assert isinstance(context, RioContext)
        if context.observed_at > observed_at:
            raise ValueError(
                "RioContext observed_at cannot be later than market observed_at"
            )

    def _validate_analysis_against_context(
        self,
        analysis: SpecialistAnalysis,
        context: BaseModel | None,
    ) -> None:
        assert isinstance(analysis, RioAnalysis)
        assert isinstance(context, RioContext)
        if analysis.data_quality != context.data_quality:
            raise SpecialistContextMismatchError(
                "Rio analysis data_quality does not match specialist_context"
            )


class Denver(SpecialistAgent):
    agent_id = "denver"
    output_model = DenverAnalysis
    context_model = DenverContext

    def _validate_context_time(self, context: BaseModel, observed_at: datetime) -> None:
        assert isinstance(context, DenverContext)
        if context.as_of > observed_at:
            raise ValueError(
                "DenverContext as_of cannot be later than market observed_at"
            )

    def _validate_analysis_against_context(
        self,
        analysis: SpecialistAnalysis,
        context: BaseModel | None,
    ) -> None:
        assert isinstance(analysis, DenverAnalysis)
        assert isinstance(context, DenverContext)
        if analysis.source_stats_id != context.stats_id:
            raise SpecialistContextMismatchError(
                "Denver source_stats_id does not match specialist_context.stats_id"
            )
        if analysis.sample_size_band != context.sample_size_band:
            raise SpecialistContextMismatchError(
                "Denver sample_size_band does not match deterministic specialist_context"
            )
