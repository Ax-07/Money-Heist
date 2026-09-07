from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from app.intelligence.ai_gateway.budget import AIBudgetLedger
from app.market.scanner.models import CandidateOpportunity, ScannerTrigger
from app.services.orchestration import ComputeGate, ComputeGatePolicy, ComputeLevel


def opportunity(*, priority: int, expires_delta: int = 300) -> CandidateOpportunity:
    now = datetime.now(timezone.utc)
    return CandidateOpportunity(
        scanner_version="scanner-v1",
        opportunity_id=str(uuid4()),
        snapshot_id="snapshot-1",
        system_id="balanced_v1",
        symbol="BTCUSDT",
        timeframe="1m",
        priority_score=priority,
        triggers=(ScannerTrigger.VOLUME_EXPANSION,),
        created_at=now,
        expires_at=now + timedelta(seconds=expires_delta),
    )


def test_compute_gate_skips_low_priority_before_ai():
    gate = ComputeGate(AIBudgetLedger("1.00"))
    decision = gate.evaluate(opportunity(priority=20))
    assert decision.level is ComputeLevel.SKIP_AI
    assert decision.reason.value == "PRIORITY_TOO_LOW"


def test_compute_gate_selects_mini_or_full_by_priority_and_budget():
    policy = ComputeGatePolicy(
        min_priority_score=35,
        full_crew_priority_score=70,
        minimum_analysis_budget_eur=Decimal("0.01"),
        full_crew_budget_eur=Decimal("0.10"),
    )
    mini = ComputeGate(AIBudgetLedger("0.05"), policy).evaluate(opportunity(priority=80))
    full = ComputeGate(AIBudgetLedger("1.00"), policy).evaluate(opportunity(priority=80))
    assert mini.level is ComputeLevel.LEVEL_2_MINI_CREW
    assert full.level is ComputeLevel.LEVEL_3_FULL_CREW


def test_compute_gate_blocks_insufficient_or_expired_opportunity():
    policy = ComputeGatePolicy(
        minimum_analysis_budget_eur=Decimal("0.50"),
        full_crew_budget_eur=Decimal("0.50"),
    )
    budget_blocked = ComputeGate(AIBudgetLedger("0.10"), policy).evaluate(
        opportunity(priority=60)
    )
    expired_opportunity = opportunity(priority=60, expires_delta=-1)
    expired = ComputeGate(AIBudgetLedger("1.00"), policy).evaluate(
        expired_opportunity,
        now=datetime.now(timezone.utc),
    )
    assert budget_blocked.level is ComputeLevel.SKIP_AI
    assert budget_blocked.reason.value == "BUDGET_INSUFFICIENT"
    assert expired.level is ComputeLevel.SKIP_AI
    assert expired.reason.value == "OPPORTUNITY_EXPIRED"
