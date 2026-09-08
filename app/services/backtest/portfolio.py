from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.trading.risk.models import PortfolioRiskState

from .clock import as_utc

ZERO = Decimal("0")


def _finite_non_negative(value: Decimal, *, field_name: str) -> Decimal:
    if not value.is_finite() or value < ZERO:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


@dataclass(slots=True)
class BacktestPortfolioStateProvider:
    """Dynamic PortfolioRiskState rebuilt from one isolated PAPER broker.

    The provider is intentionally single-system. ``correlated_risk_amount``
    defaults to the complete open-risk amount, a conservative V1 assumption
    until Batch 21 provides a richer correlation-aware portfolio layer.
    """

    system_id: str
    initial_balance: Decimal
    _state: PortfolioRiskState = field(init=False, repr=False)
    _current_day: object | None = field(default=None, init=False, repr=False)
    _day_start_equity: Decimal = field(init=False, repr=False)
    _equity_peak: Decimal = field(init=False, repr=False)
    _last_equity: Decimal = field(init=False, repr=False)
    _last_account_state: Any | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.system_id = self.system_id.strip()
        if not self.system_id:
            raise ValueError("system_id must not be empty")
        if not self.initial_balance.is_finite() or self.initial_balance <= ZERO:
            raise ValueError("initial_balance must be finite and > 0")
        self._day_start_equity = self.initial_balance
        self._equity_peak = self.initial_balance
        self._last_equity = self.initial_balance
        self._state = PortfolioRiskState(
            equity=self.initial_balance,
            day_start_equity=self.initial_balance,
            equity_peak=self.initial_balance,
            daily_pnl=ZERO,
            open_positions=0,
            open_risk_amount=ZERO,
            correlated_risk_amount=ZERO,
            gross_exposure_amount=ZERO,
        )

    @property
    def state(self) -> PortfolioRiskState:
        return self._state

    @property
    def last_account_state(self) -> Any | None:
        return self._last_account_state

    def get_portfolio_state(self, *, system_id: str) -> PortfolioRiskState | None:
        if system_id != self.system_id:
            return None
        return self._state

    async def refresh_from_broker(
        self,
        broker: Any,
        *,
        observed_at: datetime,
        open_risk_amount: Decimal = ZERO,
        correlated_risk_amount: Decimal | None = None,
    ) -> PortfolioRiskState:
        observed_at = as_utc(observed_at, field="observed_at")
        open_risk_amount = _finite_non_negative(
            open_risk_amount,
            field_name="open_risk_amount",
        )
        if correlated_risk_amount is None:
            correlated_risk_amount = open_risk_amount
        correlated_risk_amount = _finite_non_negative(
            correlated_risk_amount,
            field_name="correlated_risk_amount",
        )

        account = await broker.get_account_state()
        if getattr(account, "system_id", None) != self.system_id:
            raise ValueError("broker account system_id does not match backtest portfolio")

        equity = Decimal(str(account.equity))
        gross_exposure = Decimal(str(account.gross_exposure))
        if not equity.is_finite():
            raise ValueError("broker equity must be finite")
        _finite_non_negative(gross_exposure, field_name="gross_exposure")

        observed_day = observed_at.date()
        if self._current_day is None:
            self._current_day = observed_day
        elif observed_day != self._current_day:
            # Preserve overnight PnL in the new day by anchoring the day to the
            # last equity observed on the previous UTC date.
            self._day_start_equity = self._last_equity
            self._current_day = observed_day

        self._equity_peak = max(self._equity_peak, equity)
        daily_pnl = equity - self._day_start_equity
        self._last_equity = equity
        self._last_account_state = account
        self._state = PortfolioRiskState(
            equity=equity,
            day_start_equity=self._day_start_equity,
            equity_peak=self._equity_peak,
            daily_pnl=daily_pnl,
            open_positions=int(account.open_positions),
            open_risk_amount=open_risk_amount,
            correlated_risk_amount=correlated_risk_amount,
            gross_exposure_amount=gross_exposure,
        )
        return self._state


__all__ = ["BacktestPortfolioStateProvider"]
