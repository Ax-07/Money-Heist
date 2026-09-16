from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_decision_paths_do_not_import_zigzag_or_analytics_structure() -> None:
    forbidden = ("app.analytics.zigzag", "app.analytics.structure")
    paths = (
        REPO_ROOT / "app/market/scanner",
        REPO_ROOT / "app/services/decision_context",
        REPO_ROOT / "app/agents",
        REPO_ROOT / "app/services/orchestration",
        REPO_ROOT / "app/services/paper_pipeline",
        REPO_ROOT / "app/trading/risk",
        REPO_ROOT / "app/trading/paper",
        REPO_ROOT / "app/trading/live",
    )
    violations = []
    for root in paths:
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else root.rglob("*.py")
        for path in candidates:
            text = path.read_text(encoding="utf-8")
            for prefix in forbidden:
                if prefix in text:
                    violations.append(f"{path.relative_to(REPO_ROOT)} -> {prefix}")
    assert not violations, "\n".join(violations)


def test_zigzag_does_not_import_outcomes_agents_risk_paper_or_live() -> None:
    root = REPO_ROOT / "app/analytics/zigzag"
    forbidden = (
        "app.evaluation.forward_outcomes",
        "app.evaluation.scanner_forward_outcomes",
        "app.evaluation.funnel_outcome_attribution",
        "app.agents",
        "app.trading.risk",
        "app.trading.paper",
        "app.trading.live",
        "app.market.scanner",
    )
    violations = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for prefix in forbidden:
            if prefix in text:
                violations.append(f"{path.relative_to(REPO_ROOT)} -> {prefix}")
    assert not violations, "\n".join(violations)
