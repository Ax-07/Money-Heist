import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from app.trading.live.readonly import ReadOnlyKrakenPrivateView
from app.trading.live.reconciliation import StartupReconciliationCoordinator
from app.trading.live.store import InMemoryLiveAuditSink, InMemoryLiveOrderStore

NOW = datetime(2026, 9, 7, 20, 0, tzinfo=timezone.utc)


class ReadClient:
    async def get_api_key_info(self): return {"permissions": []}
    async def get_balance(self): return {"ZEUR": "100"}
    async def get_open_orders(self, *, client_order_id=None): return {"open": {}}
    async def get_closed_orders(self, *, client_order_id=None): return {"closed": {}}
    async def get_trades_history(self): return {"trades": {}}
    async def add_order(self, payload): raise AssertionError("write must never be exposed")
    async def cancel_order(self, *, client_order_id):
        raise AssertionError("write must never be exposed")


class ReadOnlyBroker:
    async def get_balances(self):
        from app.trading.live.models import LiveBalance
        return (LiveBalance("ZEUR", Decimal("100")),)

    async def reconcile(self, client_order_id):
        raise AssertionError("no local orders expected")

    async def get_fills(self, client_order_id):
        return ()


def test_readonly_capability_has_no_write_methods():
    view = ReadOnlyKrakenPrivateView(ReadClient())
    assert not hasattr(view, "add_order")
    assert not hasattr(view, "cancel_order")


def test_clean_startup_reconciliation_becomes_ready_without_any_write():
    store = InMemoryLiveOrderStore()
    audit = InMemoryLiveAuditSink()
    api = ReadOnlyKrakenPrivateView(ReadClient())
    coordinator = StartupReconciliationCoordinator(
        system_id="balanced_v1",
        broker=ReadOnlyBroker(),
        api=api,
        store=store,
        audit=audit,
        now=lambda: NOW,
    )
    result = asyncio.run(coordinator.reconcile())
    assert result.ready
    assert not store.reconciliation_required(system_id="balanced_v1")
    assert audit.events[-1].event_type == "LIVE_RECONCILIATION_READY"


def test_unexpected_exchange_open_order_blocks_startup():
    class Api(ReadClient):
        async def get_open_orders(self, *, client_order_id=None):
            return {"open": {"UNEXPECTED-TXID": {"status": "open", "cl_ord_id": "other"}}}

    store = InMemoryLiveOrderStore()
    audit = InMemoryLiveAuditSink()
    coordinator = StartupReconciliationCoordinator(
        system_id="balanced_v1",
        broker=ReadOnlyBroker(),
        api=ReadOnlyKrakenPrivateView(Api()),
        store=store,
        audit=audit,
        now=lambda: NOW,
    )
    result = asyncio.run(coordinator.reconcile())
    assert not result.ready
    assert result.unexpected_exchange_order_ids == ("UNEXPECTED-TXID",)
    assert store.reconciliation_required(system_id="balanced_v1")
