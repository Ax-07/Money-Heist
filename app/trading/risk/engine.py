from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from .models import (
    KillSwitchState,
    MarketConstraints,
    PortfolioRiskState,
    RiskDecision,
    RiskDecisionStatus,
    RiskProfile,
    RiskReasonCode,
    TradeProposalRiskInput,
    TradeSide,
    ZERO,
    reasons,
)
from .sizing import cap_and_round_quantity, quantity_from_risk


class RiskEngine:
    """Deterministic authority for opening-risk decisions.

    The engine is deliberately pure with respect to broker/LLM infrastructure:
    all state needed for one decision is supplied as immutable inputs.
    """

    def evaluate(
        self,
        *,
        proposal: TradeProposalRiskInput,
        portfolio: PortfolioRiskState,
        profile: RiskProfile,
        market: MarketConstraints,
        kill_switch: KillSwitchState | None = None,
        now: datetime | None = None,
    ) -> RiskDecision:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        kill_switch = kill_switch or KillSwitchState()

        rejection = self._preflight_rejection(
            proposal=proposal,
            portfolio=portfolio,
            profile=profile,
            market=market,
            kill_switch=kill_switch,
            now=now,
        )
        if rejection is not None:
            return rejection

        assert profile.max_risk_per_trade_pct is not None
        assert profile.max_portfolio_risk_pct is not None
        assert profile.max_correlated_exposure_pct is not None
        assert profile.max_leverage is not None

        per_trade_budget = portfolio.equity * profile.max_risk_per_trade_pct
        portfolio_budget_remaining = (
            portfolio.equity * profile.max_portfolio_risk_pct - portfolio.open_risk_amount
        )
        correlated_budget_remaining = (
            portfolio.equity * profile.max_correlated_exposure_pct
            - portfolio.correlated_risk_amount
        )

        if portfolio_budget_remaining <= ZERO:
            return self._reject(proposal, RiskReasonCode.MAX_PORTFOLIO_RISK)
        if correlated_budget_remaining <= ZERO:
            return self._reject(proposal, RiskReasonCode.MAX_CORRELATED_EXPOSURE)

        allowed_risk = min(
            per_trade_budget,
            portfolio_budget_remaining,
            correlated_budget_remaining,
        )
        if allowed_risk <= ZERO:
            return self._reject(proposal, RiskReasonCode.NO_RISK_BUDGET)

        resize_reasons: list[RiskReasonCode] = []
        if allowed_risk < per_trade_budget:
            if portfolio_budget_remaining == allowed_risk:
                resize_reasons.append(RiskReasonCode.RESIZED_PORTFOLIO_RISK)
            if correlated_budget_remaining == allowed_risk:
                resize_reasons.append(RiskReasonCode.RESIZED_CORRELATED_RISK)

        raw_quantity = quantity_from_risk(
            allowed_risk,
            proposal.entry_price,
            proposal.stop_price,  # type: ignore[arg-type]
        )

        # Effective leverage acts as a notional exposure ceiling. Existing gross
        # exposure is deducted so multiple positions cannot each consume the full
        # leverage allowance independently.
        effective_max_leverage = profile.max_leverage
        if market.max_leverage is not None:
            effective_max_leverage = min(effective_max_leverage, market.max_leverage)

        max_total_notional = portfolio.equity * effective_max_leverage
        available_notional = max_total_notional - portfolio.gross_exposure_amount
        if available_notional <= ZERO:
            return self._reject(proposal, RiskReasonCode.MAX_LEVERAGE)

        exposure_capped_quantity = available_notional / proposal.entry_price
        if raw_quantity > exposure_capped_quantity:
            raw_quantity = exposure_capped_quantity
            resize_reasons.append(RiskReasonCode.RESIZED_EXPOSURE)

        quantity, market_resize_reasons = cap_and_round_quantity(raw_quantity, market)
        resize_reasons.extend(market_resize_reasons)

        if quantity <= ZERO or quantity < market.min_qty:
            return self._reject(proposal, RiskReasonCode.MIN_QUANTITY)

        approved_notional = quantity * proposal.entry_price
        if approved_notional < market.min_notional:
            return self._reject(proposal, RiskReasonCode.MIN_NOTIONAL)

        stop_distance = abs(proposal.entry_price - proposal.stop_price)  # type: ignore[operator]
        approved_risk = quantity * stop_distance
        if approved_risk <= ZERO:
            return self._reject(proposal, RiskReasonCode.NO_RISK_BUDGET)

        # Defensive invariant: rounding/capping must never increase risk beyond
        # any constitutional budget.
        if approved_risk > per_trade_budget:
            return self._reject(proposal, RiskReasonCode.NO_RISK_BUDGET)
        if approved_risk > portfolio_budget_remaining:
            return self._reject(proposal, RiskReasonCode.MAX_PORTFOLIO_RISK)
        if approved_risk > correlated_budget_remaining:
            return self._reject(proposal, RiskReasonCode.MAX_CORRELATED_EXPOSURE)

        status = RiskDecisionStatus.RESIZED if resize_reasons else RiskDecisionStatus.APPROVED
        final_reasons = reasons(*(resize_reasons or [RiskReasonCode.APPROVED]))
        return RiskDecision(
            proposal_id=proposal.proposal_id,
            status=status,
            reason_codes=final_reasons,
            approved_quantity=quantity,
            approved_risk_amount=approved_risk,
            approved_notional=approved_notional,
            created_at=now,
            details={
                "risk_profile_id": profile.risk_profile_id,
                "per_trade_budget": str(per_trade_budget),
                "portfolio_budget_remaining": str(portfolio_budget_remaining),
                "correlated_budget_remaining": str(correlated_budget_remaining),
            },
        )

    def _preflight_rejection(
        self,
        *,
        proposal: TradeProposalRiskInput,
        portfolio: PortfolioRiskState,
        profile: RiskProfile,
        market: MarketConstraints,
        kill_switch: KillSwitchState,
        now: datetime,
    ) -> RiskDecision | None:
        if not profile.is_complete:
            return self._reject(
                proposal,
                RiskReasonCode.PROFILE_INCOMPLETE,
                details={"missing": ",".join(profile.missing_required_limits())},
                now=now,
            )

        if not self._valid_profile(profile):
            return self._reject(proposal, RiskReasonCode.PROFILE_INVALID, now=now)

        if kill_switch.blocks_new_trades:
            return self._reject(proposal, RiskReasonCode.KILL_SWITCH_ACTIVE, now=now)

        if proposal.is_expired(now):
            return self._reject(proposal, RiskReasonCode.SIGNAL_EXPIRED, now=now)

        if not self._valid_portfolio(portfolio):
            return self._reject(proposal, RiskReasonCode.INVALID_PORTFOLIO_STATE, now=now)

        if not self._positive_decimal(proposal.entry_price):
            return self._reject(proposal, RiskReasonCode.INVALID_ENTRY_PRICE, now=now)

        if proposal.stop_price is None or not self._positive_decimal(proposal.stop_price):
            return self._reject(proposal, RiskReasonCode.INVALID_STOP, now=now)

        if proposal.stop_price == proposal.entry_price:
            return self._reject(proposal, RiskReasonCode.INVALID_STOP, now=now)

        if proposal.side is TradeSide.LONG and proposal.stop_price >= proposal.entry_price:
            return self._reject(proposal, RiskReasonCode.STOP_ON_WRONG_SIDE, now=now)
        if proposal.side is TradeSide.SHORT and proposal.stop_price <= proposal.entry_price:
            return self._reject(proposal, RiskReasonCode.STOP_ON_WRONG_SIDE, now=now)

        assert profile.max_daily_loss_pct is not None
        assert profile.max_drawdown_pct is not None
        assert profile.max_positions is not None
        assert profile.max_leverage is not None

        if not self._valid_market(market):
            return self._reject(proposal, RiskReasonCode.INVALID_MARKET_CONSTRAINTS, now=now)

        daily_loss_limit = portfolio.day_start_equity * profile.max_daily_loss_pct
        if portfolio.daily_pnl <= -daily_loss_limit:
            return self._reject(proposal, RiskReasonCode.DAILY_LOSS_LIMIT, now=now)

        drawdown = (portfolio.equity_peak - portfolio.equity) / portfolio.equity_peak
        if drawdown >= profile.max_drawdown_pct:
            return self._reject(proposal, RiskReasonCode.MAX_DRAWDOWN_LIMIT, now=now)

        if portfolio.open_positions >= profile.max_positions:
            return self._reject(proposal, RiskReasonCode.MAX_POSITIONS_LIMIT, now=now)

        if not self._positive_decimal(proposal.requested_leverage):
            return self._reject(proposal, RiskReasonCode.MAX_LEVERAGE, now=now)
        effective_leverage = profile.max_leverage
        if market.max_leverage is not None:
            effective_leverage = min(effective_leverage, market.max_leverage)
        if proposal.requested_leverage > effective_leverage:
            return self._reject(proposal, RiskReasonCode.MAX_LEVERAGE, now=now)

        if profile.min_expected_rr is not None:
            if (
                proposal.expected_rr is None
                or not self._non_negative_finite_decimal(proposal.expected_rr)
                or proposal.expected_rr < profile.min_expected_rr
            ):
                return self._reject(proposal, RiskReasonCode.MIN_EXPECTED_RR, now=now)

        return None

    @staticmethod
    def _positive_decimal(value: Decimal) -> bool:
        try:
            return value.is_finite() and value > ZERO
        except (AttributeError, InvalidOperation):
            return False

    @staticmethod
    def _non_negative_finite_decimal(value: Decimal) -> bool:
        try:
            return value.is_finite() and value >= ZERO
        except (AttributeError, InvalidOperation):
            return False

    @classmethod
    def _valid_profile(cls, profile: RiskProfile) -> bool:
        percentage_limits = (
            profile.max_risk_per_trade_pct,
            profile.max_daily_loss_pct,
            profile.max_drawdown_pct,
            profile.max_portfolio_risk_pct,
            profile.max_correlated_exposure_pct,
        )
        if any(
            value is None
            or not cls._non_negative_finite_decimal(value)
            or value > Decimal("1")
            for value in percentage_limits
        ):
            return False
        if profile.max_positions is None or profile.max_positions < 0:
            return False
        if profile.max_leverage is None or not cls._positive_decimal(profile.max_leverage):
            return False
        if profile.max_leverage < Decimal("1"):
            return False
        if profile.min_expected_rr is not None and not cls._non_negative_finite_decimal(
            profile.min_expected_rr
        ):
            return False
        return True

    @classmethod
    def _valid_portfolio(cls, state: PortfolioRiskState) -> bool:
        if not cls._positive_decimal(state.equity):
            return False
        if not cls._positive_decimal(state.day_start_equity):
            return False
        if not cls._positive_decimal(state.equity_peak):
            return False
        if state.open_positions < 0:
            return False
        if not cls._non_negative_finite_decimal(state.open_risk_amount):
            return False
        if not cls._non_negative_finite_decimal(state.correlated_risk_amount):
            return False
        if not cls._non_negative_finite_decimal(state.gross_exposure_amount):
            return False
        try:
            if not state.daily_pnl.is_finite():
                return False
        except AttributeError:
            return False
        return True

    @classmethod
    def _valid_market(cls, market: MarketConstraints) -> bool:
        if not cls._positive_decimal(market.qty_step):
            return False
        if not cls._non_negative_finite_decimal(market.min_qty):
            return False
        if not cls._non_negative_finite_decimal(market.min_notional):
            return False
        if market.max_qty is not None and not cls._positive_decimal(market.max_qty):
            return False
        if market.max_leverage is not None:
            if not cls._positive_decimal(market.max_leverage):
                return False
            if market.max_leverage < Decimal("1"):
                return False
        return True

    @staticmethod
    def _reject(
        proposal: TradeProposalRiskInput,
        code: RiskReasonCode,
        *,
        details: dict[str, str] | None = None,
        now: datetime | None = None,
    ) -> RiskDecision:
        return RiskDecision(
            proposal_id=proposal.proposal_id,
            status=RiskDecisionStatus.REJECTED,
            reason_codes=(code,),
            created_at=now or datetime.now(timezone.utc),
            details=details or {},
        )
