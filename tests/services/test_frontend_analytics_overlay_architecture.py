from pathlib import Path

OVERLAY_MODULE = Path("app/services/frontend_v2/analytics_overlays.py")
ROUTE_MODULE = Path("app/api/routes/frontend_v2_decision_intelligence.py")


def test_analytics_overlay_projection_has_no_business_or_execution_dependencies() -> None:
    source = OVERLAY_MODULE.read_text(encoding="utf-8")
    forbidden = (
        "app.scanner",
        "app.agents",
        "app.risk",
        "app.trading.paper",
        "app.trading.live",
        "app.services.backtest",
    )
    for dependency in forbidden:
        assert dependency not in source
    assert "compute_" not in source
    assert "HistoricalReplayRunner" not in source


def test_analytics_overlay_route_remains_read_only() -> None:
    source = ROUTE_MODULE.read_text(encoding="utf-8")
    assert '"/backtests/runs/{campaign_id}/analytics/overlays"' in source
    assert "@router.post" not in source
    assert "@router.put" not in source
    assert "@router.patch" not in source
    assert "@router.delete" not in source
