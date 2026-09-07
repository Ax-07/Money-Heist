from __future__ import annotations

from .models import LiveAuditEvent, LiveOrderRecord


class InMemoryLiveOrderStore:
    def __init__(self) -> None:
        self._records: dict[str, LiveOrderRecord] = {}

    def get(self, client_order_id: str) -> LiveOrderRecord | None:
        return self._records.get(client_order_id)

    def put(self, record: LiveOrderRecord) -> None:
        self._records[record.intent.client_order_id] = record


class InMemoryLiveAuditSink:
    def __init__(self) -> None:
        self.events: list[LiveAuditEvent] = []

    def record(self, event: LiveAuditEvent) -> None:
        self.events.append(event)
