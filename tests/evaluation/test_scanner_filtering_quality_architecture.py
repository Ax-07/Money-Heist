from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "app/evaluation/decision_quality/scanner_filtering.py"


def test_scanner_filtering_is_pure_research_projection() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    forbidden = (
        "app.analytics",
        "app.market.scanner",
        "app.market.features",
        "app.agents",
        "app.services.backtest",
        "app.services.decision_context",
        "app.trading.risk",
        "app.trading.paper",
        "app.trading.live",
        "compute_forward_outcomes",
        "compute_scanner_forward_outcomes",
        "OpenAI",
        "httpx",
        "sqlalchemy",
    )
    violations = [token for token in forbidden if token in source]
    assert not violations, f"24D.2 purity regression: {violations}"


def test_scanner_filtering_does_not_introduce_direction_or_threshold_tuning_contracts() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    forbidden = (
        "recommended_threshold",
        "optimal_threshold",
        "MISSED_OPPORTUNITY",
        "hypothetical_pnl",
        "quality_score",
        "winner =",
    )
    violations = [token for token in forbidden if token in source]
    assert not violations, f"24D.2 methodology regression: {violations}"
