from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Iterable


ZERO = Decimal("0")
ONE = Decimal("1")


class TradeSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class RiskDecisionStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RESIZED = "RESIZED"


class RiskReasonCode(StrEnum):
    APPROVED = "APPROVED"
    RESIZED_PORTFOLIO_RISK = "RESIZED_PORTFOLIO_RISK"
    RESIZED_CORRELATED_RISK = "RESIZED_CORRELATED_RISK"
    RESIZED_EXPOSURE = "RESIZED_EXPOSURE"
    RESIZED_MARKET_MAX_QTY = "RESIZED_MARKET_MAX_QTY"
    RESIZED_QTY_STEP = "RESIZED_QTY_STEP"

    PROFILE_INCOMPLETE = "PROFILE_INCOMPLETE"
    PROFILE_INVALID = "PROFILE_INVALID"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    SIGNAL_EXPIRED = "SIGNAL_EXPIRED"
    INVALID_PORTFOLIO_STATE = "INVALID_PORTFOLIO_STATE"
    INVALID_ENTRY_PRICE = "INVALID_ENTRY_PRICE"
    INVALID_STOP = "INVALID_STOP"
    STOP_ON_WRONG_SIDE = "STOP_ON_WRONG_SIDE"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    MAX_DRAWDOWN_LIMIT = "MAX_DRAWDOWN_LIMIT"
    MAX_POSITIONS_LIMIT = "MAX_POSITIONS_LIMIT"
    MAX_PORTFOLIO_RISK = "MAX_PORTFOLIO_RISK"
    MAX_CORRELATED_EXPOSURE = "MAX_CORRELATED_EXPOSURE"
    MAX_LEVERAGE = "MAX_LEVERAGE"
    MIN_EXPECTED_RR = "MIN_EXPECTED_RR"
    INVALID_MARKET_CONSTRAINTS = "INVALID_MARKET_CONSTRAINTS"
    MIN_QUANTITY = "MIN_QUANTITY"
    MIN_NOTIONAL = "MIN_NOTIONAL"
    NO_RISK_BUDGET = "NO_RISK_BUDGET"


@dataclass(frozen=True, slots=True)
class RiskProfile:
    """Constitutional risk limits.

    Percentages are fractions: ``Decimal("0.01")`` means 1%.
    ``None`` is intentionally accepted so configuration may represent an
    unresolved limit, but an incomplete profile is never eligible for a new
    position.
    """

    risk_profile_id: str
    max_risk_per_trade_pct: Decimal | None
    max_daily_loss_pct: Decimal | None
    max_drawdown_pct: Decimal | None
    max_portfolio_risk_pct: Decimal | None
    max_positions: int | None
    max_leverage: Decimal | None
    max_correlated_exposure_pct: Decimal | None
    min_expected_rr: Decimal | None = None

    def missing_required_limits(self) -> tuple[str, ...]:
        required = {
            "max_risk_per_trade_pct": self.max_risk_per_trade_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_portfolio_risk_pct": self.max_portfolio_risk_pct,
            "max_positions": self.max_positions,
            "max_leverage": self.max_leverage,
            "max_correlated_exposure_pct": self.max_correlated_exposure_pct,
        }
        return tuple(name for name, value in required.items() if value is None)

    @property
    def is_complete(self) -> bool:
        return not self.missing_required_limits()


@dataclass(frozen=True, slots=True)
class TradeProposalRiskInput:
    proposal_id: str
    system_id: str
    symbol: str
    side: TradeSide
    entry_price: Decimal
    stop_price: Decimal | None
    expected_rr: Decimal | None
    expires_at: datetime
    requested_leverage: Decimal = ONE

    def is_expired(self, now: datetime) -> bool:
        if self.expires_at.tzinfo is None:
            # Naive timestamps are unsafe because persisted project timestamps
            # are specified as UTC.
            return True
        return self.expires_at <= now.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class PortfolioRiskState:
    equity: Decimal
    day_start_equity: Decimal
    equity_peak: Decimal
    daily_pnl: Decimal
    open_positions: int
    open_risk_amount: Decimal = ZERO
    correlated_risk_amount: Decimal = ZERO
    gross_exposure_amount: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class MarketConstraints:
    qty_step: Decimal
    min_qty: Decimal
    min_notional: Decimal
    max_qty: Decimal | None = None
    max_leverage: Decimal | None = None


@dataclass(frozen=True, slots=True)
class KillSwitchState:
    stop_new_trades: bool = False
    stop_ai: bool = False
    emergency_mode: bool = False
    reason: str | None = None
    activated_at: datetime | None = None

    @property
    def blocks_new_trades(self) -> bool:
        return self.stop_new_trades or self.emergency_mode


@dataclass(frozen=True, slots=True)
class RiskDecision:
    proposal_id: str
    status: RiskDecisionStatus
    reason_codes: tuple[RiskReasonCode, ...]
    approved_quantity: Decimal = ZERO
    approved_risk_amount: Decimal = ZERO
    approved_notional: Decimal = ZERO
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, str] = field(default_factory=dict)

    @property
    def is_authorized(self) -> bool:
        return self.status in {RiskDecisionStatus.APPROVED, RiskDecisionStatus.RESIZED}


def reasons(*codes: RiskReasonCode) -> tuple[RiskReasonCode, ...]:
    """Return unique reason codes while preserving deterministic order."""

    seen: set[RiskReasonCode] = set()
    ordered: list[RiskReasonCode] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return tuple(ordered)


def merge_reasons(groups: Iterable[Iterable[RiskReasonCode]]) -> tuple[RiskReasonCode, ...]:
    flattened: list[RiskReasonCode] = []
    for group in groups:
        flattened.extend(group)
    return reasons(*flattened)
