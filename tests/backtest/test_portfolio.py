from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.backtest import BacktestPortfolioStateProvider

START = datetime(2026, 1, 1, 23, 55, tzinfo=UTC)
SYSTEM_ID = "balanced_v1"


def sync_test(func):
    def wrapper():
        return asyncio.run(func())

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


class AccountBroker:
    def __init__(self, accounts):
        self.accounts = list(accounts)
        self.index = 0

    async def get_account_state(self):
        account = self.accounts[min(self.index, len(self.accounts) - 1)]
        self.index += 1
        return account


def account(
    *,
    equity: str,
    gross_exposure: str = "0",
    open_positions: int = 0,
    system_id: str = SYSTEM_ID,
):
    return SimpleNamespace(
        system_id=system_id,
        equity=Decimal(equity),
        gross_exposure=Decimal(gross_exposure),
        open_positions=open_positions,
    )


@sync_test
async def test_portfolio_provider_rebuilds_dynamic_risk_state_and_peak():
    broker = AccountBroker(
        [
            account(equity="100"),
            account(equity="110", gross_exposure="25", open_positions=1),
            account(equity="104", gross_exposure="20", open_positions=1),
        ]
    )
    provider = BacktestPortfolioStateProvider(SYSTEM_ID, Decimal("100"))

    first = await provider.refresh_from_broker(broker, observed_at=START)
    second = await provider.refresh_from_broker(
        broker,
        observed_at=START + timedelta(minutes=1),
        open_risk_amount=Decimal("2"),
    )
    third = await provider.refresh_from_broker(
        broker,
        observed_at=START + timedelta(minutes=2),
        open_risk_amount=Decimal("1.5"),
    )

    assert first.equity == Decimal("100")
    assert second.equity == Decimal("110")
    assert second.equity_peak == Decimal("110")
    assert second.daily_pnl == Decimal("10")
    assert second.open_positions == 1
    assert second.open_risk_amount == Decimal("2")
    assert second.correlated_risk_amount == Decimal("2")
    assert second.gross_exposure_amount == Decimal("25")
    assert third.equity == Decimal("104")
    assert third.equity_peak == Decimal("110")


@sync_test
async def test_portfolio_provider_rolls_utc_day_from_previous_equity():
    broker = AccountBroker(
        [
            account(equity="102"),
            account(equity="99"),
        ]
    )
    provider = BacktestPortfolioStateProvider(SYSTEM_ID, Decimal("100"))

    before_midnight = await provider.refresh_from_broker(broker, observed_at=START)
    after_midnight = await provider.refresh_from_broker(
        broker,
        observed_at=START + timedelta(minutes=10),
    )

    assert before_midnight.day_start_equity == Decimal("100")
    assert before_midnight.daily_pnl == Decimal("2")
    assert after_midnight.day_start_equity == Decimal("102")
    assert after_midnight.daily_pnl == Decimal("-3")
    assert after_midnight.equity_peak == Decimal("102")


@sync_test
async def test_portfolio_provider_rejects_cross_system_account():
    provider = BacktestPortfolioStateProvider(SYSTEM_ID, Decimal("100"))
    broker = AccountBroker([account(equity="100", system_id="other")])

    with pytest.raises(ValueError, match="system_id"):
        await provider.refresh_from_broker(broker, observed_at=START)

    assert provider.get_portfolio_state(system_id="other") is None
