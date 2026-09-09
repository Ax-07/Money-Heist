from pathlib import Path


def test_evidence_gate_has_no_live_risk_or_registry_authority() -> None:
    source = Path("app/recruitment/evidence_gate.py").read_text(encoding="utf-8")
    forbidden = (
        "app.trading.live",
        "KrakenSpotLiveBroker",
        "ControlledLiveExecutionService",
        "app.trading.risk",
        "AgentRegistryEntry",
        "AgentRegistry",
    )
    for fragment in forbidden:
        assert fragment not in source


def test_evidence_gate_does_not_score_success_criteria() -> None:
    source = Path("app/recruitment/evidence_gate.py").read_text(encoding="utf-8")
    forbidden = (
        "criterion.threshold <=",
        "criterion.threshold >=",
        "PROMOTION_RECOMMENDED",
        "record_recruitment_transition",
    )
    for fragment in forbidden:
        assert fragment not in source
