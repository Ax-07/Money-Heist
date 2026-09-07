from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.trading.risk import (
    KillSwitchState,
    MarketConstraints,
    PortfolioRiskState,
    RiskDecisionStatus,
    RiskEngine,
    RiskReasonCode,
    TradeProposalRiskInput,
    TradeSide,
    demo_profile,
    unresolved_profile,
)


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine() -> RiskEngine:
    return RiskEngine()


@pytest.fixture
def proposal() -> TradeProposalRiskInput:
    return TradeProposalRiskInput(
        proposal_id="p-1",
        system_id="balanced_v1",
        symbol="BTCUSDT",
        side=TradeSide.LONG,
        entry_price=Decimal("100"),
        stop_price=Decimal("98"),
        expected_rr=Decimal("2"),
        expires_at=NOW + timedelta(minutes=5),
    )


@pytest.fixture
def portfolio() -> PortfolioRiskState:
    return PortfolioRiskState(
        equity=Decimal("100"),
        day_start_equity=Decimal("100"),
        equity_peak=Decimal("100"),
        daily_pnl=Decimal("0"),
        open_positions=0,
        open_risk_amount=Decimal("0"),
        correlated_risk_amount=Decimal("0"),
        gross_exposure_amount=Decimal("0"),
    )


@pytest.fixture
def market() -> MarketConstraints:
    return MarketConstraints(
        qty_step=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("1"),
        max_qty=Decimal("100"),
        max_leverage=Decimal("1"),
    )


def test_approves_valid_trade_and_sizes_from_risk(engine, proposal, portfolio, market) -> None:
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=portfolio,
        profile=demo_profile(),
        market=market,
        now=NOW,
    )
    assert decision.status is RiskDecisionStatus.APPROVED
    assert decision.reason_codes == (RiskReasonCode.APPROVED,)
    assert decision.approved_quantity == Decimal("0.500")
    assert decision.approved_risk_amount == Decimal("1.000")
    assert decision.approved_notional == Decimal("50.000")


def test_incomplete_profile_fails_closed(engine, proposal, portfolio, market) -> None:
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=portfolio,
        profile=unresolved_profile("balanced"),
        market=market,
        now=NOW,
    )
    assert decision.status is RiskDecisionStatus.REJECTED
    assert decision.reason_codes == (RiskReasonCode.PROFILE_INCOMPLETE,)
    assert "max_risk_per_trade_pct" in decision.details["missing"]



def test_invalid_profile_is_rejected_fail_safe(engine, proposal, portfolio, market) -> None:
    invalid_profile = replace(demo_profile(), max_risk_per_trade_pct=Decimal("1.5"))
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=portfolio,
        profile=invalid_profile,
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.PROFILE_INVALID,)


def test_rejects_missing_stop(engine, proposal, portfolio, market) -> None:
    decision = engine.evaluate(
        proposal=replace(proposal, stop_price=None),
        portfolio=portfolio,
        profile=demo_profile(),
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.INVALID_STOP,)


def test_rejects_long_stop_above_entry(engine, proposal, portfolio, market) -> None:
    decision = engine.evaluate(
        proposal=replace(proposal, stop_price=Decimal("101")),
        portfolio=portfolio,
        profile=demo_profile(),
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.STOP_ON_WRONG_SIDE,)


def test_rejects_short_stop_below_entry(engine, proposal, portfolio, market) -> None:
    short = replace(proposal, side=TradeSide.SHORT, stop_price=Decimal("99"))
    decision = engine.evaluate(
        proposal=short,
        portfolio=portfolio,
        profile=demo_profile(),
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.STOP_ON_WRONG_SIDE,)


def test_short_trade_with_stop_above_entry_is_valid(engine, proposal, portfolio, market) -> None:
    short = replace(proposal, side=TradeSide.SHORT, stop_price=Decimal("102"))
    decision = engine.evaluate(
        proposal=short,
        portfolio=portfolio,
        profile=demo_profile(),
        market=market,
        now=NOW,
    )
    assert decision.is_authorized is True


def test_rejects_expired_signal(engine, proposal, portfolio, market) -> None:
    decision = engine.evaluate(
        proposal=replace(proposal, expires_at=NOW),
        portfolio=portfolio,
        profile=demo_profile(),
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.SIGNAL_EXPIRED,)


def test_naive_expiry_is_rejected_fail_safe(engine, proposal, portfolio, market) -> None:
    naive = replace(proposal, expires_at=datetime(2026, 9, 7, 12, 5))
    decision = engine.evaluate(
        proposal=naive,
        portfolio=portfolio,
        profile=demo_profile(),
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.SIGNAL_EXPIRED,)


def test_kill_switch_rejects_new_trade(engine, proposal, portfolio, market) -> None:
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=portfolio,
        profile=demo_profile(),
        market=market,
        kill_switch=KillSwitchState(stop_new_trades=True),
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.KILL_SWITCH_ACTIVE,)


def test_stop_ai_alone_does_not_change_risk_authorization(engine, proposal, portfolio, market) -> None:
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=portfolio,
        profile=demo_profile(),
        market=market,
        kill_switch=KillSwitchState(stop_ai=True),
        now=NOW,
    )
    assert decision.is_authorized is True


def test_daily_loss_limit_rejects_at_threshold(engine, proposal, portfolio, market) -> None:
    state = replace(portfolio, daily_pnl=Decimal("-3"))
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=state,
        profile=demo_profile(max_daily_loss_pct="0.03"),
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.DAILY_LOSS_LIMIT,)


def test_drawdown_limit_rejects_at_threshold(engine, proposal, portfolio, market) -> None:
    state = replace(portfolio, equity=Decimal("90"), equity_peak=Decimal("100"))
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=state,
        profile=demo_profile(max_drawdown_pct="0.10"),
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.MAX_DRAWDOWN_LIMIT,)


def test_max_positions_rejects_at_threshold(engine, proposal, portfolio, market) -> None:
    state = replace(portfolio, open_positions=3)
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=state,
        profile=demo_profile(max_positions=3),
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.MAX_POSITIONS_LIMIT,)


def test_existing_portfolio_risk_can_resize_trade(engine, proposal, portfolio, market) -> None:
    state = replace(portfolio, open_risk_amount=Decimal("2.5"))
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=state,
        profile=demo_profile(max_portfolio_risk_pct="0.03"),
        market=market,
        now=NOW,
    )
    assert decision.status is RiskDecisionStatus.RESIZED
    assert RiskReasonCode.RESIZED_PORTFOLIO_RISK in decision.reason_codes
    assert decision.approved_risk_amount == Decimal("0.500")


def test_portfolio_risk_exhausted_rejects(engine, proposal, portfolio, market) -> None:
    state = replace(portfolio, open_risk_amount=Decimal("3"))
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=state,
        profile=demo_profile(max_portfolio_risk_pct="0.03"),
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.MAX_PORTFOLIO_RISK,)


def test_correlated_risk_can_resize_trade(engine, proposal, portfolio, market) -> None:
    state = replace(portfolio, correlated_risk_amount=Decimal("1.5"))
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=state,
        profile=demo_profile(max_correlated_exposure_pct="0.02"),
        market=market,
        now=NOW,
    )
    assert decision.status is RiskDecisionStatus.RESIZED
    assert RiskReasonCode.RESIZED_CORRELATED_RISK in decision.reason_codes
    assert decision.approved_risk_amount == Decimal("0.500")


def test_correlated_risk_exhausted_rejects(engine, proposal, portfolio, market) -> None:
    state = replace(portfolio, correlated_risk_amount=Decimal("2"))
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=state,
        profile=demo_profile(max_correlated_exposure_pct="0.02"),
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.MAX_CORRELATED_EXPOSURE,)


def test_gross_exposure_can_resize_trade(engine, proposal, portfolio, market) -> None:
    state = replace(portfolio, gross_exposure_amount=Decimal("75"))
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=state,
        profile=demo_profile(max_leverage="1"),
        market=market,
        now=NOW,
    )
    assert decision.status is RiskDecisionStatus.RESIZED
    assert RiskReasonCode.RESIZED_EXPOSURE in decision.reason_codes
    assert decision.approved_quantity == Decimal("0.250")


def test_requested_leverage_above_profile_rejects(engine, proposal, portfolio, market) -> None:
    decision = engine.evaluate(
        proposal=replace(proposal, requested_leverage=Decimal("2")),
        portfolio=portfolio,
        profile=demo_profile(max_leverage="1"),
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.MAX_LEVERAGE,)


def test_exchange_leverage_limit_is_also_authoritative(engine, proposal, portfolio, market) -> None:
    leveraged_market = replace(market, max_leverage=Decimal("1.5"))
    decision = engine.evaluate(
        proposal=replace(proposal, requested_leverage=Decimal("2")),
        portfolio=portfolio,
        profile=demo_profile(max_leverage="3"),
        market=leveraged_market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.MAX_LEVERAGE,)


def test_min_expected_rr_rejects(engine, proposal, portfolio, market) -> None:
    decision = engine.evaluate(
        proposal=replace(proposal, expected_rr=Decimal("1.49")),
        portfolio=portfolio,
        profile=demo_profile(min_expected_rr="1.5"),
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.MIN_EXPECTED_RR,)


def test_min_expected_rr_can_be_disabled(engine, proposal, portfolio, market) -> None:
    decision = engine.evaluate(
        proposal=replace(proposal, expected_rr=None),
        portfolio=portfolio,
        profile=demo_profile(min_expected_rr=None),
        market=market,
        now=NOW,
    )
    assert decision.is_authorized is True


def test_min_notional_never_causes_unsafe_upsize(engine, proposal, portfolio, market) -> None:
    expensive_min = replace(market, min_notional=Decimal("60"))
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=portfolio,
        profile=demo_profile(),
        market=expensive_min,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.MIN_NOTIONAL,)
    assert decision.approved_quantity == Decimal("0")


def test_quantity_step_rounding_never_exceeds_risk_budget(engine, proposal, portfolio, market) -> None:
    coarse = replace(market, qty_step=Decimal("0.3"))
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=portfolio,
        profile=demo_profile(),
        market=coarse,
        now=NOW,
    )
    assert decision.status is RiskDecisionStatus.RESIZED
    assert decision.approved_quantity == Decimal("0.3")
    assert decision.approved_risk_amount == Decimal("0.6")
    assert decision.approved_risk_amount <= Decimal("1")


def test_invalid_market_constraints_reject(engine, proposal, portfolio, market) -> None:
    invalid = replace(market, qty_step=Decimal("0"))
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=portfolio,
        profile=demo_profile(),
        market=invalid,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.INVALID_MARKET_CONSTRAINTS,)


def test_invalid_portfolio_state_rejects(engine, proposal, portfolio, market) -> None:
    invalid = replace(portfolio, equity=Decimal("0"))
    decision = engine.evaluate(
        proposal=proposal,
        portfolio=invalid,
        profile=demo_profile(),
        market=market,
        now=NOW,
    )
    assert decision.reason_codes == (RiskReasonCode.INVALID_PORTFOLIO_STATE,)
