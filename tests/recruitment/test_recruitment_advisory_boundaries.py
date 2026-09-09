from __future__ import annotations

import ast
import inspect

import app.recruitment.advisory as advisory


def test_recruitment_advisory_has_no_operational_or_live_imports() -> None:
    source = inspect.getsource(advisory)
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

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


def test_recruitment_advisory_cannot_apply_lifecycle_or_registry_changes() -> None:
    source = inspect.getsource(advisory)

    assert "record_recruitment_transition(" not in source
    assert "AgentRegistryEntry" not in source
    assert "KrakenSpotLiveBroker" not in source
    assert "ControlledLiveExecutionService" not in source
