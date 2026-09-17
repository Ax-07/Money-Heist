from pathlib import Path

FORBIDDEN = (
    "app.evaluation.forward_outcomes",
    "app.evaluation.scanner_forward_outcomes",
    "app.evaluation.funnel_outcome_attribution",
    "app.services.backtest.forward_outcomes",
    "app.services.backtest.scanner_forward_outcomes",
    "app.services.backtest.funnel_outcome_attribution",
    "app.market.scanner",
    "app.services.decision_context",
    "app.services.paper_pipeline",
    "app.trading.risk",
    "app.trading.paper",
    "app.trading.live",
    "app.agents",
)


def test_pattern_calibration_is_observation_only() -> None:
    root = Path("app/analytics/pattern_calibration")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for forbidden in FORBIDDEN:
        assert forbidden not in text


def test_decision_paths_do_not_import_pattern_calibration() -> None:
    roots = (
        Path("app/market/scanner"),
        Path("app/services/decision_context"),
        Path("app/agents"),
        Path("app/services/orchestration"),
        Path("app/services/paper_pipeline"),
        Path("app/trading"),
    )
    for root in roots:
        if not root.exists():
            continue
        text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
        assert "app.analytics.pattern_calibration" not in text
