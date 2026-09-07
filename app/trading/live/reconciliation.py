from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping

from .models import LiveAuditEvent, LiveOrderStatus, ReconciliationFinding
from .ports import KrakenPrivateApi, LiveAuditSink, LiveBroker


@dataclass(frozen=True, slots=True)
class StartupReconciliationResult:
    ready: bool
    unresolved_client_order_ids: tuple[str, ...]
    unexpected_exchange_order_ids: tuple[str, ...]
    balance_assets_checked: tuple[str, ...]
    error_code: str | None = None


class StartupReconciliationCoordinator:
    """Read-only exchange recovery gate for process start/reconnect.

    It never calls AddOrder or CancelOrder. A process/session must call
    ``require_reconciliation`` before it can later become eligible for LIVE.
    """

    def __init__(
        self,
        *,
        system_id: str,
        broker: LiveBroker,
        api: KrakenPrivateApi,
        store,
        audit: LiveAuditSink,
        now=lambda: datetime.now(timezone.utc),
    ) -> None:
        self._system_id = system_id
        self._broker = broker
        self._api = api
        self._store = store
        self._audit = audit
        self._now = now

    def require_reconciliation(self, *, reason: str) -> None:
        self._store.mark_reconciliation_required(system_id=self._system_id, reason=reason)
        self._event("LIVE_RECONCILIATION_REQUIRED", "CRITICAL", reason=reason)

    async def reconcile(self) -> StartupReconciliationResult:
        self.require_reconciliation(reason="process_start_or_connection_recovery")
        unresolved: list[str] = []
        unexpected: list[str] = []
        assets: list[str] = []
        try:
            local_records = self._store.list_records(system_id=self._system_id)
            by_client = {record.intent.client_order_id: record for record in local_records}
            by_txid = {
                record.external_order_id: record
                for record in local_records
                if record.external_order_id
            }

            # Detect exchange-side open orders not represented in durable local state.
            open_result = await self._api.get_open_orders(client_order_id=None)
            open_orders = open_result.get("open", {})
            if not isinstance(open_orders, Mapping):
                raise RuntimeError("OPEN_ORDERS_INVALID")
            for txid, row in open_orders.items():
                if not isinstance(row, Mapping):
                    unexpected.append(str(txid))
                    continue
                cl_ord_id = str(row.get("cl_ord_id", "")).strip()
                if str(txid) in by_txid or (cl_ord_id and cl_ord_id in by_client):
                    continue
                unexpected.append(str(txid))

            for record in local_records:
                # Every non-terminal/crash-sensitive state must resolve through
                # the Batch 14 cl_ord_id reconciliation path before READY.
                if record.status in {
                    LiveOrderStatus.NEW,
                    LiveOrderStatus.SUBMITTED,
                    LiveOrderStatus.OPEN,
                    LiveOrderStatus.PARTIALLY_FILLED,
                    LiveOrderStatus.UNKNOWN,
                    LiveOrderStatus.RECONCILIATION_REQUIRED,
                }:
                    result = await self._broker.reconcile(record.intent.client_order_id)
                    if result.finding is not ReconciliationFinding.CONSISTENT:
                        unresolved.append(record.intent.client_order_id)
                    else:
                        marker = getattr(self._store, "mark_record_reconciled", None)
                        if marker is not None:
                            marker(
                            client_order_id=record.intent.client_order_id,
                            at=self._utc_now(),
                        )

                # Persist any known fills for all orders with a Kraken txid.
                current = self._store.get(record.intent.client_order_id)
                if current is not None and current.external_order_id is not None:
                    fills = await self._broker.get_fills(record.intent.client_order_id)
                    self._store.put_fills(record.intent.client_order_id, fills)

            balances = await self._broker.get_balances()
            for balance in balances:
                if not balance.amount.is_finite() or balance.amount < Decimal("0"):
                    raise RuntimeError("BALANCE_INVALID")
                assets.append(balance.asset)

            remaining = self._store.unresolved_records(system_id=self._system_id)
            unresolved.extend(record.intent.client_order_id for record in remaining)
            unresolved = sorted(set(unresolved))
            unexpected = sorted(set(unexpected))

            if unresolved or unexpected:
                self._event(
                    "LIVE_RECONCILIATION_BLOCKED",
                    "CRITICAL",
                    unresolved_count=str(len(unresolved)),
                    unexpected_open_order_count=str(len(unexpected)),
                )
                return StartupReconciliationResult(
                    ready=False,
                    unresolved_client_order_ids=tuple(unresolved),
                    unexpected_exchange_order_ids=tuple(unexpected),
                    balance_assets_checked=tuple(sorted(set(assets))),
                    error_code="UNRESOLVED_EXCHANGE_STATE",
                )

            at = self._utc_now()
            self._store.mark_reconciled(
                system_id=self._system_id,
                at=at,
                details={
                    "open_orders_checked": str(len(open_orders)),
                    "local_orders_checked": str(len(local_records)),
                    "balance_assets_checked": str(len(set(assets))),
                },
            )
            self._event(
                "LIVE_RECONCILIATION_READY",
                "INFO",
                open_orders_checked=str(len(open_orders)),
                local_orders_checked=str(len(local_records)),
            )
            return StartupReconciliationResult(
                ready=True,
                unresolved_client_order_ids=(),
                unexpected_exchange_order_ids=(),
                balance_assets_checked=tuple(sorted(set(assets))),
            )
        except Exception as exc:
            # Do not store raw remote payloads or request/auth data in audit.
            error_code = (
                exc.args[0]
                if exc.args and isinstance(exc.args[0], str)
                else type(exc).__name__
            )
            safe_code = str(error_code)[:100]
            self._event("LIVE_RECONCILIATION_FAILED", "CRITICAL", error_code=safe_code)
            return StartupReconciliationResult(
                ready=False,
                unresolved_client_order_ids=tuple(sorted(set(unresolved))),
                unexpected_exchange_order_ids=tuple(sorted(set(unexpected))),
                balance_assets_checked=tuple(sorted(set(assets))),
                error_code=safe_code,
            )

    def _event(self, event_type: str, severity: str, **details: str) -> None:
        self._audit.record(
            LiveAuditEvent(
                event_type=event_type,
                severity=severity,
                system_id=self._system_id,
                client_order_id=None,
                created_at=self._utc_now(),
                details=details,
            )
        )

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("clock must be timezone-aware")
        return value.astimezone(timezone.utc)
