from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_scanner_attribution_has_no_forward_or_trading_dependency() -> None:
    forbidden = (
        "app.evaluation.forward_outcomes",
        "app.evaluation.scanner_forward_outcomes",
        "app.evaluation.funnel_outcome_attribution",
        "app.agents",
        "app.services.orchestration",
        "app.services.paper_pipeline",
        "app.trading.risk",
        "app.trading.paper",
        "app.trading.live",
    )
    paths = (
        REPO_ROOT / "app/evaluation/analytics_attribution/resolver.py",
        REPO_ROOT / "app/evaluation/analytics_attribution/scanner_attribution.py",
    )
    violations = [
        f"{path.relative_to(REPO_ROOT)} -> {target}"
        for path in paths
        for target in sorted(_imports(path))
        if any(target == prefix or target.startswith(f"{prefix}.") for prefix in forbidden)
    ]
    assert not violations, "forbidden imports:\n" + "\n".join(violations)


def test_neutral_scanner_observation_has_no_analytics_or_trading_dependency() -> None:
    path = REPO_ROOT / "app/evaluation/scanner_observations.py"
    forbidden = (
        "app.analytics",
        "app.evaluation.analytics_attribution",
        "app.evaluation.forward_outcomes",
        "app.evaluation.scanner_forward_outcomes",
        "app.trading",
    )
    violations = [
        target
        for target in sorted(_imports(path))
        if any(target == prefix or target.startswith(f"{prefix}.") for prefix in forbidden)
    ]
    assert not violations, "neutral Scanner observation imports forbidden modules: " + ", ".join(
        violations
    )
