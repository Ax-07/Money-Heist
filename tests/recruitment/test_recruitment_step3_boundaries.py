from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RECRUITMENT = ROOT / "app" / "recruitment"


def test_step3_recruitment_has_no_live_risk_or_registry_dependency() -> None:
    path = RECRUITMENT / "gates.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
            imported_names.extend(alias.name for alias in node.names)

    joined_imports = "\n".join(imports).lower()
    joined_names = "\n".join(imported_names).lower()
    forbidden_modules = (
        "app.trading.live",
        "app.trading.risk",
        "app.trading.kraken",
    )
    for fragment in forbidden_modules:
        assert fragment not in joined_imports
    assert "agentregistryentry" not in joined_names
    assert "agentregistry" not in joined_names


def test_step3_gate_cannot_execute_compute_or_apply_transitions() -> None:
    source = (RECRUITMENT / "gates.py").read_text(encoding="utf-8")
    assert 'execute_compute: Literal[False] = False' in source
    assert 'auto_apply: Literal[False] = False' in source
    assert 'registry_mutation: Literal[False] = False' in source
    assert 'live_authority: Literal[False] = False' in source
    assert "record_recruitment_transition(" not in source
