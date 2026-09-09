from __future__ import annotations

import ast
from pathlib import Path


def test_advisory_audit_has_no_live_risk_registry_or_transition_recording_dependency() -> None:
    source_path = Path("app/recruitment/advisory_audit.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert not any(name.startswith("app.trading.live") for name in imports)
    assert not any(name.startswith("app.trading.risk") for name in imports)
    assert not any(name.startswith("app.agents") for name in imports)
    assert "record_recruitment_transition" not in source
    assert "AgentRegistryEntry" not in source
