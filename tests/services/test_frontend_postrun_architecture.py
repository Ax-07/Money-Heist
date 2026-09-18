from pathlib import Path

POSTRUN = Path("app/services/frontend_v2/postrun.py")
DASHBOARD = Path("app/dashboard/backtest.py")
ROUTES = Path("app/api/routes/frontend_v2_decision_intelligence.py")


def test_gate0_is_wired_to_completed_campaign_exports_not_get_routes() -> None:
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    routes = ROUTES.read_text(encoding="utf-8")

    assert "build_frontend_postrun_exports" in dashboard
    assert "exports.update(" in dashboard
    assert "build_frontend_postrun_exports" not in routes
    assert "build_frontend_postrun_projection" not in routes


def test_postrun_pipeline_never_reruns_business_authorities() -> None:
    source = POSTRUN.read_text(encoding="utf-8")
    forbidden = (
        "HistoricalReplayRunner(",
        ".scanner.scan(",
        "OrchestrationPipeline(",
        "RiskEngine(",
        "PaperTradingPipeline(",
        "LiveTrading",
    )
    for token in forbidden:
        assert token not in source


def test_postrun_pipeline_materializes_24a_24b_and_24c_chain() -> None:
    source = POSTRUN.read_text(encoding="utf-8")
    required = (
        "build_analytics_manifest",
        "link_replay_opportunities",
        "build_decision_intelligence_record_set",
        "build_scanner_analytics_attribution",
        "build_funnel_stage_analytics_attribution",
        "build_frontend_decision_intelligence_bundle",
        "build_frontend_analytics_geometry_projection",
    )
    for token in required:
        assert token in source
