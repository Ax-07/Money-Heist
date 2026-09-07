from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from .identities import ShadowSystemIdentity
from .providers import (
    ImmutableMarketConstraintsProvider,
    MutableShadowPortfolioProvider,
    ShadowAIUsageLedger,
    ShadowKillSwitchProvider,
    ShadowRiskProfileProvider,
)
from .runtime import ShadowSystemRuntime


def _deterministic_id_factory(system_id: str) -> Callable[[], str]:
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return str(uuid5(NAMESPACE_URL, f"money-heist:shadow:paper:{system_id}:{counter}"))

    return next_id


def build_shadow_runtime(
    *,
    identity: ShadowSystemIdentity,
    orchestration: Any,
    paper_broker_config: Any,
    portfolio_state: Any,
    market_constraints: Mapping[str, Any] | Any,
    risk_profile: Any | None = None,
    kill_switch_state: Any | None = None,
    risk_engine: Any | None = None,
    clock: Callable[[], datetime] | None = None,
    ai_usage_ledger: ShadowAIUsageLedger | None = None,
) -> ShadowSystemRuntime:
    """Build one isolated Batch 09 PAPER pipeline for a SHADOW identity.

    ``paper_broker_config`` and ``portfolio_state`` are intentionally mandatory:
    Batch 11 does not invent account assumptions. ``risk_profile=None`` is the
    only special case and creates an explicitly unresolved profile that the
    existing Risk Engine rejects with ``PROFILE_INCOMPLETE``.
    """

    from app.services.paper_pipeline import InMemoryPaperPipelineJournal, PaperTradingPipeline
    from app.trading.paper import PaperBroker
    from app.trading.risk import KillSwitchState, RiskEngine, unresolved_profile

    if getattr(paper_broker_config, "system_id", None) != identity.system_id:
        raise ValueError("paper_broker_config.system_id must match SHADOW identity")
    if portfolio_state is None:
        raise ValueError("portfolio_state must be injected explicitly")

    if risk_profile is None:
        risk_profile = unresolved_profile(f"{identity.system_id}:unresolved")
    if kill_switch_state is None:
        kill_switch_state = KillSwitchState()
    if risk_engine is None:
        risk_engine = RiskEngine()

    if hasattr(market_constraints, "get_market_constraints"):
        market_constraints_provider = market_constraints
    else:
        market_constraints_provider = ImmutableMarketConstraintsProvider(market_constraints)

    portfolio_provider = MutableShadowPortfolioProvider(identity.system_id, portfolio_state)
    risk_profile_provider = ShadowRiskProfileProvider(identity.system_id, risk_profile)
    kill_switch_provider = ShadowKillSwitchProvider(identity.system_id, kill_switch_state)
    journal = InMemoryPaperPipelineJournal()
    broker = PaperBroker(
        paper_broker_config,
        id_factory=_deterministic_id_factory(identity.system_id),
        clock=clock,
    )
    pipeline = PaperTradingPipeline(
        orchestration=orchestration,
        risk_engine=risk_engine,
        paper_broker=broker,
        portfolio_provider=portfolio_provider,
        risk_profile_provider=risk_profile_provider,
        market_constraints_provider=market_constraints_provider,
        kill_switch_provider=kill_switch_provider,
        journal=journal,
        clock=clock,
    )
    ledger = ai_usage_ledger or ShadowAIUsageLedger(identity.system_id)

    return ShadowSystemRuntime(
        identity=identity,
        paper_pipeline=pipeline,
        paper_broker=broker,
        journal=journal,
        orchestration=orchestration,
        portfolio_provider=portfolio_provider,
        risk_profile_provider=risk_profile_provider,
        kill_switch_provider=kill_switch_provider,
        market_constraints_provider=market_constraints_provider,
        ai_usage_ledger=ledger,
    )
