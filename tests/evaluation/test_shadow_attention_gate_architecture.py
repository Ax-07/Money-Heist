from pathlib import Path

SERVICE = Path("app/evaluation/shadow_attention/service.py")
POSTRUN = Path("app/dashboard/analytics_postrun.py")


def test_shadow_attention_v0_has_no_trading_or_agent_authority() -> None:
    source = SERVICE.read_text(encoding="utf-8")
    forbidden = (
        "app.agents",
        "app.services.orchestration",
        "app.trading",
        "RiskEngine",
        "PaperTradingPipeline",
        "LiveTrading",
        ".scanner.scan(",
        "TradeProposal",
    )
    for token in forbidden:
        assert token not in source


def test_shadow_attention_v0_is_materialized_only_in_postrun() -> None:
    source = POSTRUN.read_text(encoding="utf-8")
    assert "build_shadow_attention_report" in source
    assert "shadow_attention_export_name" in source
    assert "shadow_attention=shadow_attention" in source
    assert "ShadowAttentionReport" in source


def test_shadow_attention_v0_does_not_use_structure_as_a_wake_reason() -> None:
    source = SERVICE.read_text(encoding="utf-8")
    assert "geometry.technical_events" in source
    assert "geometry.zigzag_pivots" in source
    assert "geometry.patterns" in source
    assert "geometry.structure" not in source
