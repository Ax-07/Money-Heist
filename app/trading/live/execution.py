from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.services.orchestration.models import TradeProposal
from app.trading.risk.models import KillSwitchState, MarketConstraints, RiskDecision, RiskProfile

from .activation import LiveActivationController
from .errors import LiveExecutionDisabledError, LiveIntentValidationError
from .intent import authorized_live_order_intent
from .models import LiveAuditEvent, LiveOrderRecord
from .ports import LiveAuditSink, LiveBroker
from .preflight import (
    LiveCheckState,
    LiveOrderPreflight,
    LiveOrderPreflightContext,
    MarketReadiness,
)


class LiveSafetyStateProvider(Protocol):
    def snapshot(self, *, system_id: str) -> KillSwitchState | None: ...


class LiveReconciliationStateProvider(Protocol):
    def reconciliation_required(self, *, system_id: str) -> bool: ...


class ControlledLiveExecutionService:
    """Only Batch 15 application boundary allowed to feed the LiveBroker.

    Agents are intentionally absent from this API. Safety and reconciliation
    are read from durable operator-controlled state inside the service, so a
    caller cannot bypass either gate by passing an optimistic boolean/snapshot.
    """

    def __init__(
        self,
        *,
        broker: LiveBroker,
        activation: LiveActivationController,
        audit: LiveAuditSink,
        safety: LiveSafetyStateProvider,
        reconciliation: LiveReconciliationStateProvider,
        order_preflight: LiveOrderPreflight | None = None,
        now=lambda: datetime.now(timezone.utc),
    ) -> None:
        self._broker = broker
        self._activation = activation
        self._audit = audit
        self._safety = safety
        self._reconciliation = reconciliation
        self._preflight = order_preflight or LiveOrderPreflight(now=now)
        self._now = now

    async def submit_authorized(
        self,
        *,
        proposal: TradeProposal,
        risk_decision_id: UUID,
        decision: RiskDecision,
        risk_profile: RiskProfile,
        market: MarketReadiness,
        constraints: MarketConstraints,
        reference_price: Decimal,
    ) -> LiveOrderRecord:
        auth = self._activation.get_authorization(system_id=proposal.system_id)
        try:
            kill_switch = self._safety.snapshot(system_id=proposal.system_id)
        except Exception:
            kill_switch = None
        try:
            reconciliation_ready: bool | None = not self._reconciliation.reconciliation_required(
                system_id=proposal.system_id
            )
        except Exception:
            reconciliation_ready = None

        checks = self._preflight.evaluate(
            LiveOrderPreflightContext(
                system_id=proposal.system_id,
                proposal_id=str(proposal.proposal_id),
                proposal_side=str(proposal.side),
                proposal_expires_at=proposal.expires_at,
                risk_decision=decision,
                risk_profile=risk_profile,
                kill_switch=kill_switch,
                symbol=proposal.symbol,
                market=market,
                reconciliation_ready=reconciliation_ready,
                armed=auth.authorized,
            )
        )
        blocked = tuple(check for check in checks if check.state is not LiveCheckState.PASS)
        if blocked:
            self._audit.record(
                LiveAuditEvent(
                    event_type="LIVE_ORDER_PREFLIGHT_BLOCKED",
                    severity="CRITICAL",
                    system_id=proposal.system_id,
                    client_order_id=None,
                    created_at=self._utc_now(),
                    details={
                        "reason_codes": ",".join(
                            check.reason_code.value for check in blocked if check.reason_code
                        )
                    },
                )
            )
            raise LiveExecutionDisabledError(
                "LIVE order preflight blocked: "
                + ",".join(check.reason_code.value for check in blocked if check.reason_code)
            )

        intent = authorized_live_order_intent(
            proposal=proposal,
            risk_decision_id=risk_decision_id,
            decision=decision,
            created_at=self._utc_now(),
        )
        if intent.symbol != market.symbol:
            raise LiveIntentValidationError("market readiness belongs to another symbol")
        return await self._broker.submit_order(
            intent,
            constraints=constraints,
            reference_price=reference_price,
        )

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("clock must be timezone-aware")
        return value.astimezone(timezone.utc)
