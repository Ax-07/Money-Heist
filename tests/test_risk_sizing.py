from decimal import Decimal

import pytest

from app.trading.risk import MarketConstraints, floor_to_step, quantity_from_risk
from app.trading.risk.sizing import cap_and_round_quantity
from app.trading.risk.models import RiskReasonCode


def test_quantity_from_risk_uses_stop_distance() -> None:
    assert quantity_from_risk(Decimal("1"), Decimal("100"), Decimal("98")) == Decimal("0.5")


def test_quantity_from_risk_returns_zero_for_zero_distance() -> None:
    assert quantity_from_risk(Decimal("1"), Decimal("100"), Decimal("100")) == Decimal("0")


def test_floor_to_step_never_rounds_up() -> None:
    assert floor_to_step(Decimal("1.2349"), Decimal("0.001")) == Decimal("1.234")


def test_floor_to_step_rejects_non_positive_step() -> None:
    with pytest.raises(ValueError):
        floor_to_step(Decimal("1"), Decimal("0"))


def test_market_max_qty_and_step_resize_are_reported() -> None:
    constraints = MarketConstraints(
        qty_step=Decimal("0.1"),
        min_qty=Decimal("0.1"),
        min_notional=Decimal("1"),
        max_qty=Decimal("2.05"),
    )
    qty, reason_codes = cap_and_round_quantity(Decimal("3"), constraints)
    assert qty == Decimal("2.0")
    assert RiskReasonCode.RESIZED_MARKET_MAX_QTY in reason_codes
    assert RiskReasonCode.RESIZED_QTY_STEP in reason_codes
