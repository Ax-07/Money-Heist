from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(slots=True)
class MutableShadowPortfolioProvider:
    """Single-system portfolio risk context with explicit deterministic updates."""

    system_id: str
    _state: Any

    def get_portfolio_state(self, *, system_id: str):
        if system_id != self.system_id:
            return None
        return self._state

    def replace(self, state: Any) -> None:
        self._state = state


@dataclass(frozen=True, slots=True)
class ShadowRiskProfileProvider:
    system_id: str
    profile: Any

    def get_risk_profile(self, *, system_id: str):
        if system_id != self.system_id:
            return None
        return self.profile


@dataclass(frozen=True, slots=True)
class ShadowKillSwitchProvider:
    system_id: str
    state: Any

    def get_kill_switch_state(self, *, system_id: str):
        if system_id != self.system_id:
            return None
        return self.state


@dataclass(frozen=True, slots=True)
class ImmutableMarketConstraintsProvider:
    """Read-only market constraints that may be safely shared between SHADOW twins."""

    constraints: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "constraints", MappingProxyType(dict(self.constraints)))

    def get_market_constraints(self, *, symbol: str):
        return self.constraints.get(symbol)


class ShadowAIUsageLedger:
    """Logical system scope for AI usage records.

    Batch 06 usage records already carry ``system_id``. This ledger enforces that
    only records belonging to its own SHADOW system can be attached to it.
    """

    def __init__(self, system_id: str) -> None:
        if not system_id.strip():
            raise ValueError("system_id must not be empty")
        self.system_id = system_id
        self._records: list[Any] = []

    def record(self, usage: Any) -> None:
        usage_system_id = getattr(usage, "system_id", None)
        if usage_system_id is not None and usage_system_id != self.system_id:
            raise ValueError(
                f"AI usage for {usage_system_id!r} cannot be recorded in {self.system_id!r}"
            )
        self._records.append(usage)

    def extend(self, usages) -> None:
        for usage in usages:
            self.record(usage)

    def records(self) -> tuple[Any, ...]:
        return tuple(self._records)
