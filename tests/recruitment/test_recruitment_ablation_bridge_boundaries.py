from __future__ import annotations

import ast
from pathlib import Path


def test_ablation_bridge_imports_no_registry_risk_or_live_execution_modules() -> None:
    path = Path("app/recruitment/ablation_bridge.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = (
        "app.agents",
        "app.trading.risk",
        "app.trading.live",
        "app.market_data.exchange",
    )
    assert not any(
        module == prefix or module.startswith(prefix + ".")
        for module in imported
        for prefix in forbidden
    )


def test_bridge_reuses_batch18_ablation_module_instead_of_copying_metric_math() -> None:
    source = Path("app/recruitment/ablation_bridge.py").read_text(encoding="utf-8")
    assert "from app.evaluation.ablation import" in source
    assert "compare_ablation" in source
    assert "marginal_economic_net=" not in source
    assert "drawdown_reduction_pct=" not in source
