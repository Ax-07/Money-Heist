from __future__ import annotations

import ast
from pathlib import Path


def test_campaign_plan_does_not_import_execution_live_risk_or_registry() -> None:
    path = Path("app/recruitment/campaign.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    forbidden_prefixes = (
        "app.trading.live",
        "app.trading.risk",
        "app.services.live",
        "app.agents.registry",
        "app.evaluation.ablation_campaign_execution",
        "app.services.backtest.runner",
    )
    assert not any(
        module == prefix or module.startswith(prefix + ".")
        for module in imports
        for prefix in forbidden_prefixes
    )


def test_campaign_module_has_no_registry_mutation_or_auto_promotion_calls() -> None:
    source = Path("app/recruitment/campaign.py").read_text(encoding="utf-8")
    forbidden_calls = (
        ".register(",
        ".set_state(",
        ".update_state(",
        "submit_order(",
        "arm_live(",
        "execute_live(",
    )
    assert not any(call in source for call in forbidden_calls)
