from __future__ import annotations

import ast
import inspect

import app.recruitment.candidate_reputation as candidate_reputation
from app.recruitment import RecruitmentCandidateReputationDimensions


def _imports(source: str) -> tuple[tuple[str, str | None], ...]:
    tree = ast.parse(source)
    found: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, None) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            found.extend((module, alias.name) for alias in node.names)
    return tuple(found)


def test_candidate_reputation_module_does_not_import_operational_authority() -> None:
    imports = _imports(inspect.getsource(candidate_reputation))
    forbidden_modules = {
        "app.agents.models",
        "app.evaluation.reputation_advisory",
        "app.trading.live",
        "app.trading.risk",
    }
    forbidden_names = {
        "AgentRegistryEntry",
        "DeterministicAgentStateAdvisor",
        "ControlledLiveExecutionService",
        "KrakenSpotLiveBroker",
    }
    for module, name in imports:
        assert module not in forbidden_modules
        assert name not in forbidden_names


def test_candidate_reputation_public_dimensions_do_not_expose_agent_state_advice() -> None:
    fields = RecruitmentCandidateReputationDimensions.__dataclass_fields__
    assert "suggested_state" not in fields
    assert "state_reasons" not in fields
    assert "recommended_state" not in fields


def test_candidate_reputation_reuses_batch18_dimensions_and_ablation_aggregate() -> None:
    source = inspect.getsource(candidate_reputation)
    assert "build_agent_reputation" in source
    assert "aggregate_ablation" in source
    assert "operational_state_advisory_used" in source
