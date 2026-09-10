from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from pydantic import BaseModel

from app.agents.models import (
    BerlinAnalysis,
    DenverAnalysis,
    LisbonReport,
    NairobiAnalysis,
    PalermoReview,
    ProfessorDecision,
    ProfessorPlan,
    RioAnalysis,
    TokyoAnalysis,
)
from app.intelligence.ai_gateway.strict_schema import build_strict_json_schema
from app.portfolio.allocation_master_professor_shadow import MasterProfessorShadowOutput
from app.services.orchestration.models import ProfessorFinalDecision
from app.task_force.execution import TaskForceMemberAnalysis

OUTPUT_MODELS: tuple[type[BaseModel], ...] = (
    ProfessorPlan,
    ProfessorDecision,
    PalermoReview,
    LisbonReport,
    BerlinAnalysis,
    TokyoAnalysis,
    NairobiAnalysis,
    RioAnalysis,
    DenverAnalysis,
    ProfessorFinalDecision,
    TaskForceMemberAnalysis,
    MasterProfessorShadowOutput,
)


def walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


@pytest.mark.parametrize("model", OUTPUT_MODELS)
def test_real_gateway_output_schemas_are_openai_strict(model: type[BaseModel]) -> None:
    schema = build_strict_json_schema(model)

    for node in walk(schema):
        properties = node.get("properties")
        if isinstance(properties, dict):
            assert node.get("additionalProperties") is False
            assert node.get("required") == list(properties)

        assert not ("default" in node and node["default"] is None)


def test_professor_final_trade_is_required_but_nullable() -> None:
    schema = build_strict_json_schema(ProfessorFinalDecision)
    assert "trade" in schema["required"]
    trade = schema["properties"]["trade"]
    assert "anyOf" in trade
    assert any(option.get("type") == "null" for option in trade["anyOf"])
