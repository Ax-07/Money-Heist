from pathlib import Path

POSTRUN = Path("app/dashboard/analytics_postrun.py")
DASHBOARD = Path("app/dashboard/backtest.py")
ROUTES = Path("app/api/routes/frontend_v2_decision_intelligence.py")
RESEARCH_ROUTES = Path("app/api/routes/frontend_v2_research.py")
OLD_POSTRUN = Path("app/services/frontend_v2/postrun.py")


def test_gate0_is_wired_to_completed_campaign_exports_not_get_routes() -> None:
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    routes = ROUTES.read_text(encoding="utf-8")
    research_routes = RESEARCH_ROUTES.read_text(encoding="utf-8")

    assert "from app.dashboard.analytics_postrun import (" in dashboard
    assert "build_frontend_postrun_exports" in dashboard
    assert "exports.update(" in dashboard
    assert "build_frontend_postrun_exports" not in routes
    assert "build_frontend_postrun_projection" not in routes
    assert "build_decision_quality_research_bundle" not in research_routes
    assert "build_scanner_filtering_quality_report" not in research_routes
    assert "build_funnel_decision_quality_report" not in research_routes
    assert "build_decision_quality_evidence_index" not in research_routes
    api_router = Path("app/api/router.py").read_text(encoding="utf-8")
    assert "from app.api.routes.frontend_v2_research import router as frontend_v2_research_router" in api_router
    assert "api_router.include_router(frontend_v2_research_router)" in api_router


def test_postrun_pipeline_lives_outside_decision_services() -> None:
    assert POSTRUN.exists()
    assert not OLD_POSTRUN.exists()


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
        "build_decision_quality_research_bundle",
        "build_scanner_filtering_quality_report",
        "build_funnel_decision_quality_report",
        "build_decision_quality_evidence_index",
    )
    for token in required:
        assert token in source


def test_24d4_uses_existing_23a_outcomes_and_role_scoped_exports() -> None:
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    source = POSTRUN.read_text(encoding="utf-8")

    assert "forward_outcomes=execution.forward_outcomes" in dashboard
    assert "scanner_forward_outcomes=execution.scanner_forward_outcomes" in dashboard
    assert "build_forward_outcomes_report(" not in source
    assert "build_scanner_forward_outcomes_report(" not in source
    for token in (
        "decision-quality-research-",
        "scanner-filtering-quality-",
        "funnel-decision-quality-",
        "decision-quality-evidence-",
    ):
        assert token in Path("app/evaluation/decision_quality/evidence.py").read_text(
            encoding="utf-8"
        )


def test_24d4_skips_research_when_scanner_attribution_is_empty() -> None:
    source = POSTRUN.read_text(encoding="utf-8")

    assert "if scanner_attribution.records:" in source
    assert "partial Decision Quality research material is invalid" in source
