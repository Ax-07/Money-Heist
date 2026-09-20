from pathlib import Path

SEMANTIC = Path("app/evaluation/shadow_attention/semantic_v1.py")
POSTRUN = Path("app/dashboard/analytics_postrun.py")


def test_semantic_v1_is_observation_only_and_does_not_import_business_authorities() -> None:
    source = SEMANTIC.read_text(encoding="utf-8")
    forbidden = (
        "ScannerConfig",
        "FeatureEngine",
        "OrchestrationPipeline",
        "RiskEngine",
        "PaperTradingPipeline",
        "LiveBroker",
        "TradeProposal",
        "ForwardOutcome",
    )
    for token in forbidden:
        assert token not in source


def test_postrun_semantic_v1_is_built_from_v0_report_not_replayed_market_data() -> None:
    source = POSTRUN.read_text(encoding="utf-8")
    assert "build_semantic_attention_v1_report(shadow_attention)" in source
    assert "semantic_attention_v1_export_name" in source
