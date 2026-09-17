from pathlib import Path

PROJECTION_MODULE = Path("app/services/frontend_v2/decision_intelligence.py")


def test_frontend_projection_has_no_recomputation_dependencies() -> None:
    source = PROJECTION_MODULE.read_text(encoding="utf-8")
    forbidden = (
        "HistoricalReplayRunner",
        "DeterministicScanner",
        "PaperTradingPipeline",
        "RiskEngine",
        "build_analytics_lab_run",
        "build_analytics_as_of_input",
        "build_scanner_analytics_attribution",
        "build_decision_intelligence_record",
        "build_decision_intelligence_record_set",
        "build_funnel_stage_analytics_attribution",
    )
    assert all(name not in source for name in forbidden)


def test_frontend_projection_routes_are_read_only() -> None:
    source = Path("app/api/routes/frontend_v2_decision_intelligence.py").read_text(encoding="utf-8")
    assert "@router.post" not in source
    assert "@router.put" not in source
    assert "@router.patch" not in source
    assert "@router.delete" not in source
