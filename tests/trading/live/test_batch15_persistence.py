from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.storage.base import Base
from app.storage.database import Database
from app.storage.models import LiveAuditPersistenceRecord
from app.trading.live.models import (
    LiveAuditEvent,
    LiveFill,
    LiveOrderIntent,
    LiveOrderRecord,
    LiveOrderStatus,
)
from app.trading.live.store import SqlAlchemyLiveAuditSink, SqlAlchemyLiveOrderStore
from app.trading.paper.models import OrderSide, OrderType

NOW = datetime(2026, 9, 7, 20, 0, tzinfo=timezone.utc)


def intent():
    return LiveOrderIntent(
        order_intent_id=UUID("00000000-0000-0000-0000-000000000015"),
        risk_decision_id=UUID("00000000-0000-0000-0000-000000000005"),
        system_id="balanced_v1",
        symbol="BTC/EUR",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.001"),
        client_order_id="00000000-0000-0000-0000-000000000015",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=1),
    )


def database(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'batch15.db'}")
    Base.metadata.create_all(db.engine)
    return db


def test_live_order_survives_store_reconstruction(tmp_path):
    db = database(tmp_path)
    first = SqlAlchemyLiveOrderStore(db.session_factory)
    first.put(LiveOrderRecord(intent=intent(), status=LiveOrderStatus.RECONCILIATION_REQUIRED))

    second = SqlAlchemyLiveOrderStore(db.session_factory)
    restored = second.get(intent().client_order_id)
    assert restored is not None
    assert restored.status is LiveOrderStatus.RECONCILIATION_REQUIRED
    assert restored.intent.risk_decision_id == intent().risk_decision_id


def test_known_fills_are_durable_and_idempotent(tmp_path):
    db = database(tmp_path)
    store = SqlAlchemyLiveOrderStore(db.session_factory)
    store.put(
        LiveOrderRecord(
            intent=intent(),
            status=LiveOrderStatus.FILLED,
            external_order_id="OID-15",
        )
    )
    fill = LiveFill(
        trade_id="T-15",
        external_order_id="OID-15",
        symbol="BTC/EUR",
        side=OrderSide.BUY,
        quantity=Decimal("0.001"),
        price=Decimal("50000"),
        fee=Decimal("0.10"),
        filled_at=NOW,
    )
    store.put_fills(intent().client_order_id, [fill])
    store.put_fills(intent().client_order_id, [fill])
    assert store.list_fills(client_order_id=intent().client_order_id) == (fill,)


def test_reconciliation_cannot_be_marked_ready_with_unresolved_order(tmp_path):
    db = database(tmp_path)
    store = SqlAlchemyLiveOrderStore(db.session_factory)
    store.put(LiveOrderRecord(intent=intent(), status=LiveOrderStatus.NEW))
    store.mark_reconciliation_required(system_id="balanced_v1", reason="startup")
    with pytest.raises(RuntimeError, match="unresolved orders"):
        store.mark_reconciled(system_id="balanced_v1", at=NOW)
    assert store.reconciliation_required(system_id="balanced_v1")


def test_durable_audit_roundtrip_has_no_credential_fields(tmp_path):
    db = database(tmp_path)
    audit = SqlAlchemyLiveAuditSink(db.session_factory)
    audit.record(
        LiveAuditEvent(
            event_type="LIVE_PREFLIGHT_RESULT",
            severity="CRITICAL",
            system_id="balanced_v1",
            client_order_id=None,
            created_at=NOW,
            details={"status": "BLOCKED", "reason_codes": "RISK_PROFILE_INCOMPLETE"},
        )
    )
    with db.session() as session:
        rows = tuple(session.scalars(select(LiveAuditPersistenceRecord)))
    assert len(rows) == 1
    assert "api_secret" not in rows[0].details_json.lower()
    assert "api-key" not in rows[0].details_json.lower()
