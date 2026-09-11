from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from pydantic import BaseModel, Field

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
from app.intelligence.ai_gateway.errors import AIConfigurationError
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


def test_professor_final_decimal_fields_are_openai_compatible_numbers() -> None:
    schema = build_strict_json_schema(ProfessorFinalDecision)
    trade = schema["$defs"]["ProfessorTradeParameters"]

    for field_name in ("entry_price", "stop_price", "expected_rr"):
        field_schema = trade["properties"][field_name]
        assert field_schema["type"] == "number"
        assert "pattern" not in field_schema

    target_schema = trade["properties"]["targets"]["items"]
    assert target_schema["type"] == "number"
    assert "pattern" not in target_schema


def test_real_gateway_output_schemas_have_no_regex_lookaround() -> None:
    unsupported = ("(?=", "(?!", "(?<=", "(?<!")

    for model in OUTPUT_MODELS:
        schema = build_strict_json_schema(model)
        for node in walk(schema):
            pattern = node.get("pattern")
            if isinstance(pattern, str):
                assert not any(marker in pattern for marker in unsupported)


def test_non_decimal_lookaround_fails_locally_before_provider_call() -> None:
    class UnsupportedPatternOutput(BaseModel):
        # Inject the unsupported construct only into JSON Schema. Using
        # Field(pattern=...) would be rejected earlier by pydantic-core itself,
        # so it would not exercise our OpenAI schema normalizer.
        value: str = Field(
            json_schema_extra={"pattern": r"^(?=A).+$"},
        )

    with pytest.raises(AIConfigurationError, match="regex lookaround"):
        build_strict_json_schema(UnsupportedPatternOutput)

