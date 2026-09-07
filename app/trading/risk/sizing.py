from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from .models import MarketConstraints, RiskReasonCode, ZERO


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= ZERO:
        raise ValueError("qty_step must be > 0")
    if value <= ZERO:
        return ZERO
    units = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step


def quantity_from_risk(risk_amount: Decimal, entry_price: Decimal, stop_price: Decimal) -> Decimal:
    distance = abs(entry_price - stop_price)
    if risk_amount <= ZERO or distance <= ZERO:
        return ZERO
    return risk_amount / distance


def cap_and_round_quantity(
    quantity: Decimal,
    constraints: MarketConstraints,
) -> tuple[Decimal, tuple[RiskReasonCode, ...]]:
    reasons: list[RiskReasonCode] = []
    capped = quantity

    if constraints.max_qty is not None and capped > constraints.max_qty:
        capped = constraints.max_qty
        reasons.append(RiskReasonCode.RESIZED_MARKET_MAX_QTY)

    rounded = floor_to_step(capped, constraints.qty_step)
    if rounded != capped:
        reasons.append(RiskReasonCode.RESIZED_QTY_STEP)

    return rounded, tuple(reasons)
