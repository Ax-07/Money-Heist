from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.storage.models import (
    LiveAuditPersistenceRecord,
    LiveFillPersistenceRecord,
    LiveOrderPersistenceRecord,
    LiveReconciliationPersistenceRecord,
)
from app.trading.paper.models import OrderSide, OrderType

from .models import LiveAuditEvent, LiveFill, LiveOrderIntent, LiveOrderRecord, LiveOrderStatus


_UNRESOLVED_STATUSES = frozenset(
    {
        LiveOrderStatus.NEW,
        LiveOrderStatus.SUBMITTED,
        LiveOrderStatus.UNKNOWN,
        LiveOrderStatus.RECONCILIATION_REQUIRED,
    }
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class InMemoryLiveOrderStore:
    def __init__(self) -> None:
        self._records: dict[str, LiveOrderRecord] = {}
        self._fills: dict[str, LiveFill] = {}
        self._reconciliation_required: dict[str, bool] = {}
        self._last_reconciled_at: dict[str, datetime] = {}

    def get(self, client_order_id: str) -> LiveOrderRecord | None:
        return self._records.get(client_order_id)

    def put(self, record: LiveOrderRecord) -> None:
        self._records[record.intent.client_order_id] = record

    def list_records(self, *, system_id: str | None = None) -> tuple[LiveOrderRecord, ...]:
        records = tuple(self._records.values())
        if system_id is None:
            return records
        return tuple(r for r in records if r.intent.system_id == system_id)

    def unresolved_records(self, *, system_id: str) -> tuple[LiveOrderRecord, ...]:
        return tuple(
            r
            for r in self.list_records(system_id=system_id)
            if r.status in _UNRESOLVED_STATUSES
        )

    def put_fills(self, client_order_id: str, fills: Iterable[LiveFill]) -> None:
        del client_order_id
        for fill in fills:
            self._fills[fill.trade_id] = fill

    def list_fills(self, *, client_order_id: str) -> tuple[LiveFill, ...]:
        external = self.get(client_order_id)
        if external is None or external.external_order_id is None:
            return ()
        return tuple(
            fill
            for fill in self._fills.values()
            if fill.external_order_id == external.external_order_id
        )

    def mark_reconciliation_required(self, *, system_id: str, reason: str) -> None:
        del reason
        self._reconciliation_required[system_id] = True

    def mark_reconciled(
        self,
        *,
        system_id: str,
        at: datetime,
        details: dict[str, str] | None = None,
    ) -> None:
        del details
        self._reconciliation_required[system_id] = False
        self._last_reconciled_at[system_id] = _utc(at)

    def reconciliation_required(self, *, system_id: str) -> bool:
        return self._reconciliation_required.get(system_id, True)

    def healthcheck(self) -> bool:
        return True


class InMemoryLiveAuditSink:
    def __init__(self) -> None:
        self.events: list[LiveAuditEvent] = []

    def record(self, event: LiveAuditEvent) -> None:
        self.events.append(event)

    def healthcheck(self) -> bool:
        return True


class SqlAlchemyLiveOrderStore:
    """Durable LIVE state store.

    The broker writes ``NEW`` before AddOrder. With this store that write is a
    committed crash-recovery marker: after a process restart, ``NEW`` is treated
    as potentially ambiguous until an exchange reconciliation proves otherwise.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def healthcheck(self) -> bool:
        with self._session_factory() as session:
            session.execute(select(LiveOrderPersistenceRecord.client_order_id).limit(1))
            session.execute(select(LiveReconciliationPersistenceRecord.system_id).limit(1))
        return True

    def get(self, client_order_id: str) -> LiveOrderRecord | None:
        with self._session_factory() as session:
            row = session.get(LiveOrderPersistenceRecord, client_order_id)
            return None if row is None else self._to_domain(row)

    def put(self, record: LiveOrderRecord) -> None:
        client_order_id = record.intent.client_order_id
        with self._session_factory.begin() as session:
            row = session.get(LiveOrderPersistenceRecord, client_order_id)
            values = self._record_values(record)
            if row is None:
                row = LiveOrderPersistenceRecord(client_order_id=client_order_id, **values)
                session.add(row)
            else:
                for key, value in values.items():
                    setattr(row, key, value)

    def list_records(self, *, system_id: str | None = None) -> tuple[LiveOrderRecord, ...]:
        with self._session_factory() as session:
            stmt = select(LiveOrderPersistenceRecord).order_by(
                LiveOrderPersistenceRecord.intent_created_at,
                LiveOrderPersistenceRecord.client_order_id,
            )
            if system_id is not None:
                stmt = stmt.where(LiveOrderPersistenceRecord.system_id == system_id)
            rows = tuple(session.scalars(stmt))
            return tuple(self._to_domain(row) for row in rows)

    def unresolved_records(self, *, system_id: str) -> tuple[LiveOrderRecord, ...]:
        allowed = tuple(status.value for status in _UNRESOLVED_STATUSES)
        with self._session_factory() as session:
            rows = tuple(
                session.scalars(
                    select(LiveOrderPersistenceRecord)
                    .where(LiveOrderPersistenceRecord.system_id == system_id)
                    .where(LiveOrderPersistenceRecord.status.in_(allowed))
                    .order_by(LiveOrderPersistenceRecord.intent_created_at)
                )
            )
            return tuple(self._to_domain(row) for row in rows)

    def put_fills(self, client_order_id: str, fills: Iterable[LiveFill]) -> None:
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            for fill in fills:
                row = session.get(LiveFillPersistenceRecord, fill.trade_id)
                values = {
                    "client_order_id": client_order_id,
                    "external_order_id": fill.external_order_id,
                    "symbol": fill.symbol,
                    "side": fill.side.value,
                    "quantity": format(fill.quantity, "f"),
                    "price": format(fill.price, "f"),
                    "fee": format(fill.fee, "f"),
                    "filled_at": _utc(fill.filled_at) if fill.filled_at else None,
                    "observed_at": now,
                }
                if row is None:
                    session.add(LiveFillPersistenceRecord(trade_id=fill.trade_id, **values))
                else:
                    for key, value in values.items():
                        setattr(row, key, value)

    def list_fills(self, *, client_order_id: str) -> tuple[LiveFill, ...]:
        with self._session_factory() as session:
            rows = tuple(
                session.scalars(
                    select(LiveFillPersistenceRecord)
                    .where(LiveFillPersistenceRecord.client_order_id == client_order_id)
                    .order_by(
                        LiveFillPersistenceRecord.observed_at,
                        LiveFillPersistenceRecord.trade_id,
                    )
                )
            )
        return tuple(
            LiveFill(
                trade_id=row.trade_id,
                external_order_id=row.external_order_id,
                symbol=row.symbol,
                side=OrderSide(row.side),
                quantity=Decimal(row.quantity),
                price=Decimal(row.price),
                fee=Decimal(row.fee),
                filled_at=_utc(row.filled_at) if row.filled_at else None,
            )
            for row in rows
        )

    def mark_record_reconciled(self, *, client_order_id: str, at: datetime) -> None:
        with self._session_factory.begin() as session:
            row = session.get(LiveOrderPersistenceRecord, client_order_id)
            if row is not None:
                row.last_reconciled_at = _utc(at)

    def mark_reconciliation_required(self, *, system_id: str, reason: str) -> None:
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            row = session.get(LiveReconciliationPersistenceRecord, system_id)
            if row is None:
                session.add(
                    LiveReconciliationPersistenceRecord(
                        system_id=system_id,
                        reconciliation_required=True,
                        last_started_at=now,
                        last_success_at=None,
                        last_result="REQUIRED",
                        details_json=json.dumps({"reason": reason}, sort_keys=True),
                        updated_at=now,
                    )
                )
            else:
                row.reconciliation_required = True
                row.last_started_at = now
                row.last_result = "REQUIRED"
                row.details_json = json.dumps({"reason": reason}, sort_keys=True)
                row.updated_at = now

    def mark_reconciled(
        self,
        *,
        system_id: str,
        at: datetime,
        details: dict[str, str] | None = None,
    ) -> None:
        if self.unresolved_records(system_id=system_id):
            raise RuntimeError("cannot mark LIVE state reconciled while unresolved orders remain")
        at = _utc(at)
        with self._session_factory.begin() as session:
            row = session.get(LiveReconciliationPersistenceRecord, system_id)
            if row is None:
                row = LiveReconciliationPersistenceRecord(
                    system_id=system_id,
                    reconciliation_required=False,
                    last_started_at=at,
                    last_success_at=at,
                    last_result="CONSISTENT",
                    details_json=json.dumps(details or {}, sort_keys=True),
                    updated_at=at,
                )
                session.add(row)
            else:
                row.reconciliation_required = False
                row.last_success_at = at
                row.last_result = "CONSISTENT"
                row.details_json = json.dumps(details or {}, sort_keys=True)
                row.updated_at = at

    def reconciliation_required(self, *, system_id: str) -> bool:
        with self._session_factory() as session:
            row = session.get(LiveReconciliationPersistenceRecord, system_id)
            return True if row is None else bool(row.reconciliation_required)

    @staticmethod
    def _record_values(record: LiveOrderRecord) -> dict[str, object]:
        intent = record.intent
        return {
            "order_intent_id": str(intent.order_intent_id),
            "risk_decision_id": str(intent.risk_decision_id),
            "system_id": intent.system_id,
            "symbol": intent.symbol,
            "side": intent.side.value,
            "order_type": intent.order_type.value,
            "quantity": format(intent.quantity, "f"),
            "limit_price": (
                format(intent.limit_price, "f") if intent.limit_price is not None else None
            ),
            "intent_created_at": _utc(intent.created_at),
            "intent_expires_at": _utc(intent.expires_at),
            "status": record.status.value,
            "external_order_id": record.external_order_id,
            "exchange_status": record.exchange_status,
            "filled_quantity": format(record.filled_quantity, "f"),
            "average_fill_price": (
                format(record.average_fill_price, "f")
                if record.average_fill_price is not None
                else None
            ),
            "last_error_code": record.last_error_code,
            "updated_at": _utc(record.updated_at),
        }

    @staticmethod
    def _to_domain(row: LiveOrderPersistenceRecord) -> LiveOrderRecord:
        intent = LiveOrderIntent(
            order_intent_id=UUID(row.order_intent_id),
            risk_decision_id=UUID(row.risk_decision_id),
            system_id=row.system_id,
            symbol=row.symbol,
            side=OrderSide(row.side),
            order_type=OrderType(row.order_type),
            quantity=Decimal(row.quantity),
            client_order_id=row.client_order_id,
            created_at=_utc(row.intent_created_at),
            expires_at=_utc(row.intent_expires_at),
            limit_price=Decimal(row.limit_price) if row.limit_price is not None else None,
        )
        return LiveOrderRecord(
            intent=intent,
            status=LiveOrderStatus(row.status),
            external_order_id=row.external_order_id,
            exchange_status=row.exchange_status,
            filled_quantity=Decimal(row.filled_quantity),
            average_fill_price=(
                Decimal(row.average_fill_price) if row.average_fill_price is not None else None
            ),
            last_error_code=row.last_error_code,
            updated_at=_utc(row.updated_at),
        )


class SqlAlchemyLiveAuditSink:
    """Durable structured audit sink. Only redacted/allowlisted details belong here."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def healthcheck(self) -> bool:
        with self._session_factory() as session:
            session.execute(select(LiveAuditPersistenceRecord.event_id).limit(1))
        return True

    def record(self, event: LiveAuditEvent) -> None:
        # LiveAuditEvent deliberately has no credential field. Serialize only
        # caller-provided structured details, never exception request headers.
        payload = {str(key): str(value) for key, value in event.details.items()}
        with self._session_factory.begin() as session:
            session.add(
                LiveAuditPersistenceRecord(
                    event_id=str(uuid4()),
                    event_type=event.event_type,
                    severity=event.severity,
                    system_id=event.system_id,
                    client_order_id=event.client_order_id,
                    created_at=_utc(event.created_at),
                    details_json=json.dumps(
                        payload, sort_keys=True, separators=(",", ":")
                    ),
                )
            )
