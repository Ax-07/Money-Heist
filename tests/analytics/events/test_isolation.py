from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EVENTS_ROOT = REPO_ROOT / "app/analytics/events"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    relative = path.relative_to(REPO_ROOT).with_suffix("")
    package_parts = list(relative.parts[:-1])
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                keep = len(package_parts) - (node.level - 1)
                prefix = package_parts[: max(keep, 0)]
                suffix = node.module.split(".") if node.module else []
                base = ".".join([*prefix, *suffix])
            if base:
                imported.add(base)
    return imported


def test_events_package_has_no_decision_posthoc_or_live_dependencies() -> None:
    forbidden = (
        "app.market.scanner",
        "app.services.decision_context",
        "app.agents",
        "app.services.orchestration",
        "app.evaluation.forward_outcomes",
        "app.evaluation.scanner_forward_outcomes",
        "app.evaluation.funnel_outcome_attribution",
        "app.services.backtest.forward_outcomes",
        "app.services.backtest.scanner_forward_outcomes",
        "app.services.backtest.funnel_outcome_attribution",
        "app.trading",
    )
    violations = []
    for path in sorted(EVENTS_ROOT.glob("*.py")):
        for target in sorted(_imports(path)):
            if any(target == prefix or target.startswith(prefix + ".") for prefix in forbidden):
                violations.append(f"{path.relative_to(REPO_ROOT)} -> {target}")
    assert not violations, "forbidden imports:\n" + "\n".join(violations)


def test_business_paths_do_not_import_technical_events() -> None:
    business_roots = (
        REPO_ROOT / "app/market/scanner",
        REPO_ROOT / "app/services/decision_context",
        REPO_ROOT / "app/agents",
        REPO_ROOT / "app/services/orchestration",
        REPO_ROOT / "app/trading/risk",
        REPO_ROOT / "app/trading/paper",
        REPO_ROOT / "app/trading/live",
    )
    violations = []
    for root in business_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for target in sorted(_imports(path)):
                if target == "app.analytics.events" or target.startswith("app.analytics.events."):
                    violations.append(f"{path.relative_to(REPO_ROOT)} -> {target}")
    assert not violations, "business path imported Technical Events:\n" + "\n".join(violations)
