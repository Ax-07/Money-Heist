from pathlib import Path

FORBIDDEN_IN_PATTERNS = (
    "app.evaluation.forward_outcomes",
    "app.evaluation.scanner_forward_outcomes",
    "app.evaluation.funnel_outcome_attribution",
    "app.market.scanner",
    "app.services.decision_context",
    "app.services.paper_pipeline",
    "app.trading.live",
    "app.agents",
)


def test_patterns_do_not_import_decision_or_outcome_paths():
    root = Path("app/analytics/patterns")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for forbidden in FORBIDDEN_IN_PATTERNS:
        assert forbidden not in text


def test_decision_path_does_not_import_analytics_patterns():
    roots = [
        Path("app/agents"),
        Path("app/market/scanner"),
        Path("app/services/decision_context"),
        Path("app/services/orchestration"),
        Path("app/services/paper_pipeline"),
        Path("app/trading"),
    ]
    for root in roots:
        if not root.exists():
            continue
        text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
        assert "app.analytics.patterns" not in text
