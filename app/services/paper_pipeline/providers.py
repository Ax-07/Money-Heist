from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.trading.risk.models import (
    KillSwitchState,
    MarketConstraints,
    PortfolioRiskState,
    RiskProfile,
)


@dataclass(frozen=True, slots=True)
class InMemoryPortfolioRiskStateProvider:
    states: Mapping[str, PortfolioRiskState]

    def get_portfolio_state(self, *, system_id: str) -> PortfolioRiskState | None:
        return self.states.get(system_id)


@dataclass(frozen=True, slots=True)
class InMemoryRiskProfileProvider:
    profiles: Mapping[str, RiskProfile]

    def get_risk_profile(self, *, system_id: str) -> RiskProfile | None:
        return self.profiles.get(system_id)


@dataclass(frozen=True, slots=True)
class InMemoryMarketConstraintsProvider:
    constraints: Mapping[str, MarketConstraints]

    def get_market_constraints(self, *, symbol: str) -> MarketConstraints | None:
        return self.constraints.get(symbol)


@dataclass(frozen=True, slots=True)
class InMemoryKillSwitchStateProvider:
    states: Mapping[str, KillSwitchState]

    def get_kill_switch_state(self, *, system_id: str) -> KillSwitchState | None:
        return self.states.get(system_id)
