from __future__ import annotations

from decimal import Decimal

from .models import RiskProfile


# Source-of-truth note:
# The project documentation deliberately leaves the numeric risk limits open.
# Therefore Batch 05 does NOT ship an implicitly LIVE-authorized Balanced
# profile. Callers must provide explicit values through configuration.


def unresolved_profile(risk_profile_id: str) -> RiskProfile:
    """Create an intentionally incomplete profile that fails closed."""

    return RiskProfile(
        risk_profile_id=risk_profile_id,
        max_risk_per_trade_pct=None,
        max_daily_loss_pct=None,
        max_drawdown_pct=None,
        max_portfolio_risk_pct=None,
        max_positions=None,
        max_leverage=None,
        max_correlated_exposure_pct=None,
        min_expected_rr=None,
    )


def demo_profile(
    *,
    risk_profile_id: str = "test_balanced",
    max_risk_per_trade_pct: str = "0.01",
    max_daily_loss_pct: str = "0.03",
    max_drawdown_pct: str = "0.10",
    max_portfolio_risk_pct: str = "0.03",
    max_positions: int = 3,
    max_leverage: str = "1",
    max_correlated_exposure_pct: str = "0.02",
    min_expected_rr: str | None = "1.5",
) -> RiskProfile:
    """Explicit helper for tests/dev examples only; not a LIVE preset."""

    return RiskProfile(
        risk_profile_id=risk_profile_id,
        max_risk_per_trade_pct=Decimal(max_risk_per_trade_pct),
        max_daily_loss_pct=Decimal(max_daily_loss_pct),
        max_drawdown_pct=Decimal(max_drawdown_pct),
        max_portfolio_risk_pct=Decimal(max_portfolio_risk_pct),
        max_positions=max_positions,
        max_leverage=Decimal(max_leverage),
        max_correlated_exposure_pct=Decimal(max_correlated_exposure_pct),
        min_expected_rr=Decimal(min_expected_rr) if min_expected_rr is not None else None,
    )
