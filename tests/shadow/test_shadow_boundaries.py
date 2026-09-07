from __future__ import annotations

from pathlib import Path

import pytest

from app.services.shadow import DEFAULT_SHADOW_SYSTEMS, ShadowFleetRunner, build_shadow_runtime
from app.trading.paper import PaperBrokerConfig

from ._helpers import (
    ScenarioOrchestration,
    market_constraints,
    portfolio_state,
    three_runtimes,
)


def test_batch11_source_contains_no_live_broker_exchange_recruitment_or_dashboard_surface():
    shadow_root = Path("app/services/shadow")
    source = "\n".join(path.read_text(encoding="utf-8") for path in shadow_root.rglob("*.py"))
    forbidden = (
        "LiveBroker",
        "LIVE Broker",
        "submit_live",
        "real exchange",
        "Rio",
        "Denver",
        "RecruitmentEngine",
        "Recruitment Engine",
        "Dashboard",
    )
    for token in forbidden:
        assert token not in source


def test_shadow_identity_cannot_be_built_with_mismatched_paper_system_id():
    identity = DEFAULT_SHADOW_SYSTEMS[0]
    with pytest.raises(ValueError, match="system_id"):
        build_shadow_runtime(
            identity=identity,
            orchestration=ScenarioOrchestration(),
            paper_broker_config=PaperBrokerConfig(system_id="wrong-system"),
            portfolio_state=portfolio_state(),
            market_constraints=market_constraints(),
            risk_profile=None,
        )


def test_fleet_exposes_no_automatic_promotion_or_risk_mutation_method():
    fleet = ShadowFleetRunner(three_runtimes())
    assert not hasattr(fleet, "promote")
    assert not hasattr(fleet, "set_live")
    assert not hasattr(fleet, "change_risk")
    assert not hasattr(fleet, "disable_agent")


def test_batch11_runtime_uses_only_paper_execution_pipeline():
    runtime = three_runtimes()[0]
    assert runtime.identity.mode == "SHADOW"
    assert runtime.paper_broker.__class__.__name__ == "PaperBroker"
    assert runtime.paper_pipeline.__class__.__name__ == "PaperTradingPipeline"
