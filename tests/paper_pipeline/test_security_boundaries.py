from __future__ import annotations

import ast
from pathlib import Path


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_agents_still_import_neither_risk_engine_nor_paper_broker():
    forbidden = ("app.trading.risk", "app.trading.paper")
    for path in Path("app/agents").glob("*.py"):
        imports = imported_modules(path)
        assert not any(module.startswith(forbidden) for module in imports), path


def test_batch08_orchestration_still_imports_neither_risk_nor_broker():
    forbidden = ("app.trading.risk", "app.trading.paper")
    for path in Path("app/services/orchestration").glob("*.py"):
        imports = imported_modules(path)
        assert not any(module.startswith(forbidden) for module in imports), path


def test_only_deterministic_paper_pipeline_joins_orchestration_risk_and_broker():
    pipeline = Path("app/services/paper_pipeline/pipeline.py")
    imports = imported_modules(pipeline)
    assert "app.trading.risk.engine" in imports
    assert "app.trading.paper.broker" in imports
    assert all("live" not in module.lower() for module in imports)
