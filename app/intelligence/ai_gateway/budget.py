from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from threading import RLock
from uuid import UUID, uuid4

from .errors import BudgetExceededError


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    hard_limit_eur: Decimal
    spent_eur: Decimal
    reserved_eur: Decimal

    @property
    def remaining_eur(self) -> Decimal:
        return max(self.hard_limit_eur - self.spent_eur - self.reserved_eur, Decimal("0"))


class AIBudgetLedger:
    """Thread-safe in-memory hard budget ledger.

    Instantiate one ledger per logical system/budget scope. Persistence can be added by
    a later storage integration without changing the gateway contract.
    """

    def __init__(self, hard_limit_eur: Decimal | str | float):
        limit = Decimal(str(hard_limit_eur))
        if limit < 0:
            raise ValueError("hard_limit_eur must be non-negative")
        self._hard_limit = limit
        self._spent = Decimal("0")
        self._reservations: dict[UUID, Decimal] = {}
        self._lock = RLock()

    def snapshot(self) -> BudgetSnapshot:
        with self._lock:
            return BudgetSnapshot(
                hard_limit_eur=self._hard_limit,
                spent_eur=self._spent,
                reserved_eur=sum(self._reservations.values(), Decimal("0")),
            )

    def can_reserve(self, amount_eur: Decimal) -> bool:
        amount = Decimal(amount_eur)
        if amount < 0:
            return False
        return amount <= self.snapshot().remaining_eur

    def reserve(self, amount_eur: Decimal) -> UUID:
        amount = Decimal(amount_eur)
        if amount < 0:
            raise ValueError("Reservation amount must be non-negative")
        with self._lock:
            reserved = sum(self._reservations.values(), Decimal("0"))
            if self._spent + reserved + amount > self._hard_limit:
                raise BudgetExceededError(
                    f"AI hard budget exceeded: requested={amount} EUR, "
                    f"remaining={self._hard_limit - self._spent - reserved} EUR"
                )
            reservation_id = uuid4()
            self._reservations[reservation_id] = amount
            return reservation_id

    def settle(self, reservation_id: UUID, actual_cost_eur: Decimal) -> None:
        actual = Decimal(actual_cost_eur)
        if actual < 0:
            raise ValueError("actual_cost_eur must be non-negative")
        with self._lock:
            reserved = self._reservations.pop(reservation_id)
            remaining_after_release = self._hard_limit - self._spent
            if actual > reserved and actual > remaining_after_release:
                # This should not happen when the conservative reservation is configured correctly.
                raise BudgetExceededError(
                    "Provider cost exceeded both its reservation and the remaining hard budget"
                )
            self._spent += actual

    def release(self, reservation_id: UUID) -> None:
        with self._lock:
            self._reservations.pop(reservation_id, None)
