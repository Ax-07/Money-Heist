from __future__ import annotations

from typing import Any, Mapping, Protocol

from app.market.features.models import FeatureSnapshot
from app.market.scanner.models import CandidateOpportunity
from app.services.decision_context import DecisionContextV1
from app.services.orchestration.models import OrchestrationResult
from app.trading.risk.models import (
    KillSwitchState,
    MarketConstraints,
    PortfolioRiskState,
    RiskProfile,
)

from .models import PaperPipelineEvent


class OrchestrationPort(Protocol):
    async def run(
        self,
        *,
        opportunity: CandidateOpportunity,
        market_context: FeatureSnapshot,
        now=None,
        decision_context: DecisionContextV1 | None = None,
        specialist_contexts: Mapping[str, Any] | None = None,
    ) -> OrchestrationResult: ...


class PortfolioRiskStateProvider(Protocol):
    def get_portfolio_state(self, *, system_id: str) -> PortfolioRiskState | None: ...


class RiskProfileProvider(Protocol):
    def get_risk_profile(self, *, system_id: str) -> RiskProfile | None: ...


class MarketConstraintsProvider(Protocol):
    def get_market_constraints(self, *, symbol: str) -> MarketConstraints | None: ...


class KillSwitchStateProvider(Protocol):
    def get_kill_switch_state(self, *, system_id: str) -> KillSwitchState | None: ...


class PaperPipelineJournal(Protocol):
    """Minimal audit/idempotency contract for the PAPER execution boundary.

    ``preflight`` must fail before execution if subsequent journal writes cannot
    be guaranteed for the current run. ``claim_execution`` must atomically claim
    both opportunity and proposal identities so no second execution can occur.
    """

    def preflight(self) -> None: ...

    def append(self, event: PaperPipelineEvent) -> None: ...

    def claim_execution(
        self,
        *,
        opportunity_id: str,
        proposal_id: str,
        source_snapshot_id: str,
    ) -> bool: ...
