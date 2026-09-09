from __future__ import annotations

import ast
import inspect

import app.recruitment.advisory_transition as advisory_transition


def _imported_modules() -> set[str]:
    tree = ast.parse(inspect.getsource(advisory_transition))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_advisory_transition_planner_has_no_operational_live_or_registry_imports() -> None:
    imported = _imported_modules()
    forbidden_prefixes = (
        "app.agents",
        "app.trading",
        "app.services.live",
    )
    assert not any(
        name.startswith(prefix)
        for name in imported
        for prefix in forbidden_prefixes
    )


def test_advisory_transition_planner_cannot_apply_or_create_registry_authority() -> None:
    source = inspect.getsource(advisory_transition)

    assert "record_recruitment_transition(" not in source
    assert "AgentRegistryEntry" not in source
    assert "KrakenSpotLiveBroker" not in source
    assert "ControlledLiveExecutionService" not in source
