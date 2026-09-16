from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module)
    return imported


def test_analytics_indicators_do_not_import_business_or_posthoc_paths() -> None:
    forbidden = (
        "app.market.scanner",
        "app.services.decision_context",
        "app.agents",
        "app.services.orchestration",
        "app.trading.risk",
        "app.trading.paper",
        "app.trading.live",
        "app.evaluation.forward_outcomes",
        "app.evaluation.scanner_forward_outcomes",
        "app.evaluation.funnel_outcome_attribution",
    )
    violations = []
    for path in sorted((REPO_ROOT / "app/analytics/indicators").rglob("*.py")):
        for target in _imports(path):
            if any(target == prefix or target.startswith(prefix + ".") for prefix in forbidden):
                violations.append(f"{path.relative_to(REPO_ROOT)} -> {target}")
    assert not violations, "forbidden imports:\n" + "\n".join(violations)


def test_no_business_module_imports_analytics_indicators() -> None:
    paths = (
        REPO_ROOT / "app/market/scanner",
        REPO_ROOT / "app/services/decision_context",
        REPO_ROOT / "app/agents",
        REPO_ROOT / "app/services/orchestration",
        REPO_ROOT / "app/trading/risk",
        REPO_ROOT / "app/trading/paper",
    )
    violations = []
    for root in paths:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")) if root.is_dir() else (root,):
            for target in _imports(path):
                if target == "app.analytics.indicators" or target.startswith(
                    "app.analytics.indicators."
                ):
                    violations.append(f"{path.relative_to(REPO_ROOT)} -> {target}")
    assert not violations, "business imports analytics indicators:\n" + "\n".join(violations)
