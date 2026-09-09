from pathlib import Path


def test_campaign_execution_has_no_live_or_risk_engine_imports() -> None:
    source = Path("app/recruitment/campaign_execution.py").read_text(encoding="utf-8")
    forbidden_import_fragments = (
        "from app.trading.live",
        "import app.trading.live",
        "from app.trading.risk",
        "import app.trading.risk",
        "KrakenSpotLiveBroker",
        "ControlledLiveExecutionService",
    )
    for fragment in forbidden_import_fragments:
        assert fragment not in source


def test_campaign_execution_does_not_create_operational_registry_entries() -> None:
    source = Path("app/recruitment/campaign_execution.py").read_text(encoding="utf-8")
    assert "AgentRegistryEntry(" not in source
    assert ".register(" not in source
    assert ".update_state(" not in source
    assert "PROMOTION_RECOMMENDED" not in source
