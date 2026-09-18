from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "app/evaluation/decision_quality/funnel_quality.py"


def test_funnel_quality_is_read_only_research_projection() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    forbidden = (
        "app.agents",
        "app.market.scanner",
        "app.services.decision_context",
        "app.services.backtest",
        "app.trading.risk",
        "app.trading.paper",
        "app.trading.live",
        "app.analytics",
        "compute_forward_outcomes",
        "compute_scanner_forward_outcomes",
        "OpenAI",
        "httpx",
        "sqlalchemy",
        "recommended_threshold",
        "optimal_threshold",
        "hypothetical_pnl",
        "quality_score",
        "winner =",
    )
    violations = [token for token in forbidden if token in source]
    assert not violations, f"24D.3 architecture/methodology regression: {violations}"


def test_stage_local_direction_boundary_is_explicit() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "_DIRECTION_AWARE_STAGES" in source
    assert "FunnelStage.PROFESSOR_FINAL" in source
    assert "FunnelStage.TRADE_PROPOSAL" in source
    assert "FunnelStage.RISK" in source
    assert "FunnelStage.PAPER" in source
    boundary = source.split("_DIRECTION_AWARE_STAGES: Final =", 1)[1].split("}", 1)[0]
    assert "COMPUTE_GATE" not in boundary
    assert "PROFESSOR_PLAN" not in boundary
    assert "SPECIALIST" not in boundary
    assert "PALERMO" not in boundary


def test_funnel_quality_consumes_canonical_bundle_and_stage_attribution_only() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "DecisionQualityResearchBundle" in source
    assert "FunnelStageAnalyticsAttributionSet" in source
    assert "ForwardOutcomeReport" not in source
    assert "ScannerForwardOutcomeReport" not in source
