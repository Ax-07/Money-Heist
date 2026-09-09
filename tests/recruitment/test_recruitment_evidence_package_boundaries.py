from __future__ import annotations

import ast
from pathlib import Path


SOURCE = Path("app/recruitment/evidence_package.py")


def _imports() -> tuple[str, ...]:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return tuple(modules)


def test_evidence_package_has_no_agent_registry_or_live_execution_imports() -> None:
    imports = _imports()
    forbidden_prefixes = (
        "app.agents",
        "app.trading",
        "app.services.live",
        "app.market.live",
    )
    assert not any(
        module == prefix or module.startswith(prefix + ".")
        for module in imports
        for prefix in forbidden_prefixes
    )


def test_evidence_package_has_no_risk_engine_dependency() -> None:
    imports = _imports()
    assert not any("risk" in module.lower() for module in imports)


def test_evidence_package_source_contains_no_registry_write_api() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    forbidden_calls = (
        "register_agent(",
        "update_agent_state(",
        "set_agent_state(",
        "enable_live(",
    )
    assert not any(token in source for token in forbidden_calls)
