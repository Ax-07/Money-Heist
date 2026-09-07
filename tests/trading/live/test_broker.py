import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from app.trading.live.activation import DenyAllLiveAuthorization, StaticLiveAuthorization
from app.trading.live.broker import KrakenSpotLiveBroker
from app.trading.live.errors import LiveAmbiguousSubmissionError, LiveExecutionDisabledError, LiveIntentValidationError, LiveReconciliationError
from app.trading.live.models import LiveOrderIntent, LiveOrderStatus, ReconciliationFinding
from app.trading.live.store import InMemoryLiveAuditSink, InMemoryLiveOrderStore
from app.trading.paper.models import OrderSide, OrderType
from app.trading.risk.models import MarketConstraints

NOW = datetime(2026, 9, 7, 19, 0, tzinfo=timezone.utc)
CONSTRAINTS = MarketConstraints(qty_step=Decimal("0.001"), min_qty=Decimal("0.001"), min_notional=Decimal("1"))


def intent(*, client="00000000-0000-0000-0000-000000000014", qty="0.01", created=None, expires=None):
    return LiveOrderIntent(
        order_intent_id=UUID("00000000-0000-0000-0000-000000000014"),
        risk_decision_id=UUID("00000000-0000-0000-0000-000000000005"),
        system_id="balanced_v1", symbol="BTC/EUR", side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=Decimal(qty), client_order_id=client, created_at=created or NOW,
        expires_at=expires or NOW + timedelta(minutes=1),
    )


class FakeApi:
    def __init__(self):
        self.add_calls = 0
        self.cancel_calls = 0
        self.open = {}
        self.closed = {}
        self.add_error = None
        self.permissions = []

    async def get_api_key_info(self): return {"permissions": self.permissions}
    async def get_balance(self): return {"ZEUR": "100"}
    async def get_open_orders(self, *, client_order_id=None): return {"open": self.open}
    async def get_closed_orders(self, *, client_order_id=None): return {"closed": self.closed, "count": len(self.closed)}
    async def get_trades_history(self): return {"trades": {}}
    async def add_order(self, payload):
        self.add_calls += 1
        if self.add_error: raise self.add_error
        return {"txid": ["OID-14"]}
    async def cancel_order(self, *, client_order_id):
        self.cancel_calls += 1
        return {"count": 1}


def broker(api, *, auth=True, cancellation=False):
    store, audit = InMemoryLiveOrderStore(), InMemoryLiveAuditSink()
    b = KrakenSpotLiveBroker(
        api=api,
        authorization=StaticLiveAuthorization(auth) if auth is not None else DenyAllLiveAuthorization(),
        store=store, audit=audit, allowed_system_ids=frozenset({"balanced_v1"}),
        cancellation_enabled=cancellation, now=lambda: NOW,
    )
    return b, store, audit


def test_batch14_default_authorization_is_fail_closed_even_with_broker_ready():
    api = FakeApi(); b, _, audit = broker(api, auth=None)
    with pytest.raises(LiveExecutionDisabledError):
        asyncio.run(b.submit_order(intent(), constraints=CONSTRAINTS, reference_price=Decimal("50000")))
    assert api.add_calls == 0
    assert audit.events[-1].event_type == "LIVE_SUBMISSION_BLOCKED"


def test_authorized_submission_calls_add_order_once_and_records_txid():
    api = FakeApi(); b, _, _ = broker(api)
    record = asyncio.run(b.submit_order(intent(), constraints=CONSTRAINTS, reference_price=Decimal("50000")))
    assert record.status is LiveOrderStatus.SUBMITTED
    assert record.external_order_id == "OID-14"
    assert api.add_calls == 1


def test_same_client_id_is_idempotent_locally():
    api = FakeApi(); b, _, _ = broker(api)
    first = asyncio.run(b.submit_order(intent(), constraints=CONSTRAINTS, reference_price=Decimal("50000")))
    second = asyncio.run(b.submit_order(intent(), constraints=CONSTRAINTS, reference_price=Decimal("50000")))
    assert first == second
    assert api.add_calls == 1


def test_ambiguous_submission_is_blocked_until_reconciliation_and_never_resubmitted():
    api = FakeApi(); api.add_error = LiveAmbiguousSubmissionError("timeout")
    b, store, _ = broker(api)
    with pytest.raises(LiveAmbiguousSubmissionError):
        asyncio.run(b.submit_order(intent(), constraints=CONSTRAINTS, reference_price=Decimal("50000")))
    assert store.get(intent().client_order_id).status is LiveOrderStatus.RECONCILIATION_REQUIRED
    with pytest.raises(LiveReconciliationError):
        asyncio.run(b.submit_order(intent(), constraints=CONSTRAINTS, reference_price=Decimal("50000")))
    assert api.add_calls == 1


def test_reconciliation_resolves_ambiguous_order_when_exchange_finds_cl_ord_id():
    api = FakeApi(); b, store, _ = broker(api)
    store.put(__import__("app.trading.live.models", fromlist=["LiveOrderRecord"]).LiveOrderRecord(intent(), LiveOrderStatus.RECONCILIATION_REQUIRED))
    api.open = {"OID-FOUND": {"status": "open", "vol": "0.01", "vol_exec": "0"}}
    result = asyncio.run(b.reconcile(intent().client_order_id))
    assert result.finding is ReconciliationFinding.CONSISTENT
    assert result.external_order_id == "OID-FOUND"
    assert store.get(intent().client_order_id).status is LiveOrderStatus.OPEN


def test_stale_intent_is_rejected_before_exchange_write():
    api = FakeApi(); b, _, _ = broker(api)
    stale = intent(created=NOW - timedelta(minutes=2), expires=NOW - timedelta(minutes=1))
    with pytest.raises(LiveIntentValidationError):
        asyncio.run(b.submit_order(stale, constraints=CONSTRAINTS, reference_price=Decimal("50000")))
    assert api.add_calls == 0


def test_market_constraints_are_enforced_before_exchange_write():
    api = FakeApi(); b, _, _ = broker(api)
    with pytest.raises(LiveIntentValidationError):
        asyncio.run(b.submit_order(intent(qty="0.0015"), constraints=CONSTRAINTS, reference_price=Decimal("50000")))
    assert api.add_calls == 0


def test_cancellation_is_independently_disabled_by_default():
    api = FakeApi(); b, _, _ = broker(api)
    with pytest.raises(LiveExecutionDisabledError):
        asyncio.run(b.cancel_order(intent().client_order_id))
    assert api.cancel_calls == 0


def test_withdrawal_permission_is_rejected_by_preflight():
    api = FakeApi(); api.permissions = ["query-funds", "withdraw-funds"]
    b, _, _ = broker(api)
    from app.trading.live.errors import LivePermissionError
    with pytest.raises(LivePermissionError):
        asyncio.run(b.verify_minimal_permissions())
