from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.intelligence.ai_gateway.budget import AIBudgetLedger
from app.market.scanner.models import CandidateOpportunity

from .models import ComputeGateDecision, ComputeGateReason, ComputeLevel


@dataclass(frozen=True, slots=True)
class ComputeGatePolicy:
    """Deterministic preflight policy; the AI Gateway ledger remains the hard authority."""

    min_priority_score: int = 35
    full_crew_priority_score: int = 70
    minimum_analysis_budget_eur: Decimal = Decimal("0.005")
    full_crew_budget_eur: Decimal = Decimal("0.020")

    def __post_init__(self) -> None:
        if not 0 <= self.min_priority_score <= 100:
            raise ValueError("min_priority_score must be between 0 and 100")
        if not 0 <= self.full_crew_priority_score <= 100:
            raise ValueError("full_crew_priority_score must be between 0 and 100")
        if self.full_crew_priority_score < self.min_priority_score:
            raise ValueError("full_crew_priority_score cannot be below min_priority_score")
        if self.minimum_analysis_budget_eur < 0:
            raise ValueError("minimum_analysis_budget_eur must be non-negative")
        if self.full_crew_budget_eur < self.minimum_analysis_budget_eur:
            raise ValueError("full_crew_budget_eur cannot be below minimum_analysis_budget_eur")


class ComputeGate:
    def __init__(
        self,
        budget: AIBudgetLedger,
        policy: ComputeGatePolicy | None = None,
    ) -> None:
        self._budget = budget
        self.policy = policy or ComputeGatePolicy()

    def evaluate(
        self,
        opportunity: CandidateOpportunity,
        *,
        now: datetime | None = None,
    ) -> ComputeGateDecision:
        evaluated_at = now or datetime.now(timezone.utc)
        if evaluated_at.tzinfo is None:
            evaluated_at = evaluated_at.replace(tzinfo=timezone.utc)
        else:
            evaluated_at = evaluated_at.astimezone(timezone.utc)

        remaining = self._budget.snapshot().remaining_eur
        if opportunity.expires_at <= evaluated_at:
            return ComputeGateDecision(
                level=ComputeLevel.SKIP_AI,
                reason=ComputeGateReason.OPPORTUNITY_EXPIRED,
                priority_score=opportunity.priority_score,
                remaining_budget_eur=remaining,
                minimum_required_budget_eur=self.policy.minimum_analysis_budget_eur,
            )
        if opportunity.priority_score < self.policy.min_priority_score:
            return ComputeGateDecision(
                level=ComputeLevel.SKIP_AI,
                reason=ComputeGateReason.PRIORITY_TOO_LOW,
                priority_score=opportunity.priority_score,
                remaining_budget_eur=remaining,
                minimum_required_budget_eur=self.policy.minimum_analysis_budget_eur,
            )
        if remaining < self.policy.minimum_analysis_budget_eur:
            return ComputeGateDecision(
                level=ComputeLevel.SKIP_AI,
                reason=ComputeGateReason.BUDGET_INSUFFICIENT,
                priority_score=opportunity.priority_score,
                remaining_budget_eur=remaining,
                minimum_required_budget_eur=self.policy.minimum_analysis_budget_eur,
            )
        if (
            opportunity.priority_score >= self.policy.full_crew_priority_score
            and remaining >= self.policy.full_crew_budget_eur
        ):
            return ComputeGateDecision(
                level=ComputeLevel.LEVEL_3_FULL_CREW,
                reason=ComputeGateReason.ALLOWED_FULL_CREW,
                priority_score=opportunity.priority_score,
                remaining_budget_eur=remaining,
                minimum_required_budget_eur=self.policy.full_crew_budget_eur,
            )
        return ComputeGateDecision(
            level=ComputeLevel.LEVEL_2_MINI_CREW,
            reason=ComputeGateReason.ALLOWED_MINI_CREW,
            priority_score=opportunity.priority_score,
            remaining_budget_eur=remaining,
            minimum_required_budget_eur=self.policy.minimum_analysis_budget_eur,
        )
