from decimal import Decimal

import pytest

from app.intelligence.ai_gateway import AIBudgetLedger, BudgetExceededError


def test_budget_reservation_and_settlement():
    ledger = AIBudgetLedger("1.00")
    reservation = ledger.reserve(Decimal("0.40"))
    assert ledger.snapshot().remaining_eur == Decimal("0.60")
    ledger.settle(reservation, Decimal("0.25"))
    snapshot = ledger.snapshot()
    assert snapshot.spent_eur == Decimal("0.25")
    assert snapshot.reserved_eur == Decimal("0")
    assert snapshot.remaining_eur == Decimal("0.75")


def test_budget_release_restores_capacity():
    ledger = AIBudgetLedger("0.50")
    reservation = ledger.reserve(Decimal("0.50"))
    ledger.release(reservation)
    assert ledger.snapshot().remaining_eur == Decimal("0.50")


def test_budget_hard_limit_rejects_overspend():
    ledger = AIBudgetLedger("0.10")
    with pytest.raises(BudgetExceededError):
        ledger.reserve(Decimal("0.100001"))


def test_budget_can_reserve_is_non_mutating():
    ledger = AIBudgetLedger("0.10")
    assert ledger.can_reserve(Decimal("0.05")) is True
    assert ledger.snapshot().reserved_eur == Decimal("0")
