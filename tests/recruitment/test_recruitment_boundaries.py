from pathlib import Path


FORBIDDEN_IMPORTS = (
    "app.trading.live",
    "KrakenSpotLiveBroker",
    "ControlledLiveExecutionService",
    "app.trading.risk",
)


def test_recruitment_step1_has_no_live_or_risk_dependency() -> None:
    package = Path("app/recruitment")
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))

    for forbidden in FORBIDDEN_IMPORTS:
        assert forbidden not in source
