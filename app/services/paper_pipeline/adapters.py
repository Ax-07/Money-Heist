from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from app.services.orchestration.models import TradeProposal
from app.trading.paper.models import OrderSide, PaperOrderRequest
from app.trading.risk.models import RiskDecisionStatus, TradeProposalRiskInput, TradeSide

from .models import PaperOrderIntent, RiskDecisionRecord


def trade_proposal_to_risk_input(proposal: TradeProposal) -> TradeProposalRiskInput:
    """Lossless Batch 08 -> Batch 05 adapter for fields owned by Risk Engine."""

    return TradeProposalRiskInput(
        proposal_id=str(proposal.proposal_id),
        system_id=proposal.system_id,
        symbol=proposal.symbol,
        side=TradeSide(proposal.side),
        entry_price=proposal.entry_price,
        stop_price=proposal.stop_price,
        expected_rr=proposal.expected_rr,
        expires_at=proposal.expires_at,
    )


def risk_decision_record(proposal_id: str, decision) -> RiskDecisionRecord:
    reasons = ",".join(code.value for code in decision.reason_codes)
    stable = (
        f"money-heist:paper-risk:{proposal_id}:{decision.status.value}:"
        f"{reasons}:{decision.approved_quantity}:{decision.approved_risk_amount}"
    )
    return RiskDecisionRecord(risk_decision_id=uuid5(NAMESPACE_URL, stable), decision=decision)


def authorized_order_intent(
    proposal: TradeProposal,
    record: RiskDecisionRecord,
) -> PaperOrderIntent:
    decision = record.decision
    if decision.status not in {RiskDecisionStatus.APPROVED, RiskDecisionStatus.RESIZED}:
        raise ValueError("rejected risk decision cannot create an order intent")
    if decision.approved_quantity <= 0:
        raise ValueError("authorized risk decision must approve a positive quantity")

    side = OrderSide.BUY if proposal.side == "LONG" else OrderSide.SELL
    return PaperOrderIntent(
        risk_decision_id=record.risk_decision_id,
        system_id=proposal.system_id,
        symbol=proposal.symbol,
        side=side,
        quantity=decision.approved_quantity,
        client_order_id=f"paper:opportunity:{proposal.opportunity_id}",
    )


def intent_to_paper_request(intent: PaperOrderIntent) -> PaperOrderRequest:
    if intent.mode != "PAPER":
        raise ValueError("only PAPER execution is supported")
    return PaperOrderRequest(
        system_id=intent.system_id,
        symbol=intent.symbol,
        side=intent.side,
        order_type=intent.order_type,
        quantity=intent.quantity,
        client_order_id=intent.client_order_id,
    )
