import ast
from pathlib import Path


FORBIDDEN_PREFIXES = (
    "app.agents",
    "app.trading",
    "app.services.live",
    "app.services.activation",
)


def test_recruitment_lifecycle_does_not_import_operational_agent_or_trading_layers() -> None:
    source = Path("app/recruitment/lifecycle.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    for imported in imports:
        assert not imported.startswith(FORBIDDEN_PREFIXES)


def test_candidate_lifecycle_has_no_operational_agent_states() -> None:
    source = Path("app/recruitment/lifecycle.py").read_text(encoding="utf-8")

    assert '"ACTIVE"' not in source
    assert '"ON_DEMAND"' not in source
    assert "AgentRegistryEntry" not in source
