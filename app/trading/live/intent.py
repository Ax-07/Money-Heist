from __future__ import annotations

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from app.services.orchestration.models import TradeProposal
from app.trading.paper.models import OrderSide, OrderType
from app.trading.risk.models import RiskDecision

from .models import LiveOrderIntent


def authorized_live_order_intent(
    *,
    proposal: TradeProposal,
    risk_decision_id: UUID,
    decision: RiskDecision,
    created_at: datetime | None = None,
    order_type: OrderType = OrderType.MARKET,
    limit_price=None,
) -> LiveOrderIntent:
    """Create LIVE OrderIntent only from an already authorized RiskDecision."""

    if not decision.is_authorized:
        raise ValueError("rejected risk decision cannot create a LIVE OrderIntent")
    if decision.proposal_id != str(proposal.proposal_id):
        raise ValueError("risk decision does not belong to proposal")
    if decision.approved_quantity <= 0:
        raise ValueError("authorized risk decision must approve positive quantity")
    if proposal.side == "SHORT":
        raise ValueError("initial Kraken Spot LIVE does not support short-entry OrderIntent")
    now = created_at or datetime.now(timezone.utc)
    stable = uuid5(
        NAMESPACE_URL,
        f"money-heist:live-intent:{risk_decision_id}:{proposal.system_id}:{proposal.symbol}",
    )
    return LiveOrderIntent(
        order_intent_id=stable,
        risk_decision_id=risk_decision_id,
        system_id=proposal.system_id,
        symbol=proposal.symbol,
        side=OrderSide.BUY if proposal.side == "LONG" else OrderSide.SELL,
        order_type=order_type,
        quantity=decision.approved_quantity,
        client_order_id=str(stable),
        created_at=now,
        expires_at=proposal.expires_at,
        limit_price=limit_price,
    )
