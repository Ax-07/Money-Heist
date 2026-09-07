from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Mapping, Sequence

from app.trading.paper.models import OrderSide, OrderType
from app.trading.risk.models import MarketConstraints

from .activation import LiveAuthorizationProvider
from .errors import (
    LiveAmbiguousSubmissionError,
    LiveExecutionDisabledError,
    LiveIntentValidationError,
    LiveReconciliationError,
)
from .models import (
    LiveAuditEvent,
    LiveBalance,
    LiveFill,
    LiveOrderIntent,
    LiveOrderRecord,
    LiveOrderStatus,
    ReconciliationFinding,
    ReconciliationResult,
)
from .ports import KrakenPrivateApi, LiveAuditSink, LiveOrderStore


KRAKEN_SPOT_PAIR_BY_CANONICAL = {"BTC/EUR": "XBTEUR", "ETH/EUR": "ETHEUR", "SOL/EUR": "SOLEUR"}


class KrakenSpotLiveBroker:
    """Secure Spot broker boundary. Batch 14 remains disabled unless an external provider authorizes it."""

    def __init__(
        self,
        *,
        api: KrakenPrivateApi,
        authorization: LiveAuthorizationProvider,
        store: LiveOrderStore,
        audit: LiveAuditSink,
        allowed_system_ids: frozenset[str],
        allowed_symbols: frozenset[str] = frozenset(KRAKEN_SPOT_PAIR_BY_CANONICAL),
        cancellation_enabled: bool = False,
        now=lambda: datetime.now(timezone.utc),
    ) -> None:
        if not allowed_system_ids:
            raise ValueError("allowed_system_ids must not be empty")
        self._api = api
        self._authorization = authorization
        self._store = store
        self._audit = audit
        self._allowed_system_ids = allowed_system_ids
        self._allowed_symbols = allowed_symbols
        self._cancellation_enabled = cancellation_enabled
        self._now = now

    async def submit_order(self, intent: LiveOrderIntent, *, constraints: MarketConstraints, reference_price: Decimal) -> LiveOrderRecord:
        auth = self._authorization.get_authorization(system_id=intent.system_id)
        if not auth.authorized:
            self._event("LIVE_SUBMISSION_BLOCKED", "CRITICAL", intent, reason=auth.reason, source=auth.source)
            raise LiveExecutionDisabledError(auth.reason)
        self._validate_intent(intent, constraints=constraints, reference_price=reference_price)

        existing = self._store.get(intent.client_order_id)
        if existing is not None:
            if existing.status in {LiveOrderStatus.UNKNOWN, LiveOrderStatus.RECONCILIATION_REQUIRED}:
                raise LiveReconciliationError("equivalent order is blocked until reconciliation")
            return existing

        remote = await self._find_exchange_order(intent.client_order_id)
        if remote is not None:
            record = self._record_from_exchange(intent, remote)
            self._store.put(record)
            self._event("IDEMPOTENT_REMOTE_MATCH", "WARNING", intent, external_order_id=record.external_order_id or "")
            return record

        pending = LiveOrderRecord(intent=intent, status=LiveOrderStatus.NEW, updated_at=self._utc_now())
        self._store.put(pending)
        payload: dict[str, object] = {
            "ordertype": "market" if intent.order_type is OrderType.MARKET else "limit",
            "type": "buy" if intent.side is OrderSide.BUY else "sell",
            "volume": self._decimal_text(intent.quantity),
            "pair": KRAKEN_SPOT_PAIR_BY_CANONICAL[intent.symbol],
            "cl_ord_id": intent.client_order_id,
            "deadline": self._deadline(),
        }
        if intent.order_type is OrderType.LIMIT:
            payload["price"] = self._decimal_text(intent.limit_price)
        try:
            result = await self._api.add_order(payload)
        except LiveAmbiguousSubmissionError as exc:
            unknown = replace(
                pending,
                status=LiveOrderStatus.RECONCILIATION_REQUIRED,
                last_error_code="AMBIGUOUS_SUBMISSION",
                updated_at=self._utc_now(),
            )
            self._store.put(unknown)
            self._event("ORDER_SUBMISSION_AMBIGUOUS", "CRITICAL", intent)
            raise
        txids = result.get("txid")
        if not isinstance(txids, list) or len(txids) != 1 or not str(txids[0]).strip():
            unknown = replace(pending, status=LiveOrderStatus.RECONCILIATION_REQUIRED, last_error_code="INVALID_ADD_ORDER_RESULT", updated_at=self._utc_now())
            self._store.put(unknown)
            raise LiveReconciliationError("AddOrder returned no unique txid")
        record = replace(pending, status=LiveOrderStatus.SUBMITTED, external_order_id=str(txids[0]), updated_at=self._utc_now())
        self._store.put(record)
        self._event("ORDER_SUBMITTED", "INFO", intent, external_order_id=record.external_order_id or "")
        return record

    async def get_order(self, client_order_id: str) -> LiveOrderRecord | None:
        await self.reconcile(client_order_id)
        return self._store.get(client_order_id)

    async def get_balances(self) -> Sequence[LiveBalance]:
        result = await self._api.get_balance()
        balances: list[LiveBalance] = []
        for asset, value in result.items():
            try:
                amount = Decimal(str(value))
            except Exception as exc:
                raise LiveReconciliationError("invalid balance quantity from Kraken") from exc
            balances.append(LiveBalance(asset=str(asset), amount=amount))
        return tuple(balances)

    async def get_fills(self, client_order_id: str) -> Sequence[LiveFill]:
        local = self._store.get(client_order_id)
        if local is None:
            return ()
        if local.external_order_id is None:
            return ()
        result = await self._api.get_trades_history()
        trades = result.get("trades", {})
        if not isinstance(trades, Mapping):
            raise LiveReconciliationError("TradesHistory result is invalid")
        fills: list[LiveFill] = []
        for trade_id, row in trades.items():
            if not isinstance(row, Mapping):
                continue
            if local.external_order_id and str(row.get("ordertxid", "")) != local.external_order_id:
                continue
            try:
                fills.append(LiveFill(
                    trade_id=str(trade_id),
                    external_order_id=str(row.get("ordertxid", "")),
                    symbol=local.intent.symbol,
                    side=OrderSide.BUY if str(row.get("type", "")).lower() == "buy" else OrderSide.SELL,
                    quantity=Decimal(str(row.get("vol", "0"))),
                    price=Decimal(str(row.get("price", "0"))),
                    fee=Decimal(str(row.get("fee", "0"))),
                ))
            except Exception as exc:
                raise LiveReconciliationError("invalid trade row from Kraken") from exc
        return tuple(fills)

    async def cancel_order(self, client_order_id: str) -> LiveOrderRecord:
        if not self._cancellation_enabled:
            raise LiveExecutionDisabledError("LIVE cancellation is not authorized by Batch 14 configuration")
        local = self._store.get(client_order_id)
        if local is None:
            raise LiveReconciliationError("cannot cancel unknown local order")
        auth = self._authorization.get_authorization(system_id=local.intent.system_id)
        if not auth.authorized:
            raise LiveExecutionDisabledError(auth.reason)
        try:
            await self._api.cancel_order(client_order_id=client_order_id)
        except LiveAmbiguousSubmissionError:
            ambiguous = replace(local, status=LiveOrderStatus.RECONCILIATION_REQUIRED, last_error_code="AMBIGUOUS_CANCEL", updated_at=self._utc_now())
            self._store.put(ambiguous)
            raise
        await self.reconcile(client_order_id)
        return self._store.get(client_order_id) or local

    async def reconcile(self, client_order_id: str) -> ReconciliationResult:
        local = self._store.get(client_order_id)
        remote = await self._find_exchange_order(client_order_id)
        if remote is None:
            if local is None:
                return ReconciliationResult(client_order_id, ReconciliationFinding.ORDER_UNKNOWN, None)
            finding = ReconciliationFinding.AMBIGUOUS if local.status in {LiveOrderStatus.UNKNOWN, LiveOrderStatus.RECONCILIATION_REQUIRED, LiveOrderStatus.SUBMITTED} else ReconciliationFinding.ORDER_UNKNOWN
            if finding is ReconciliationFinding.AMBIGUOUS:
                blocked = replace(local, status=LiveOrderStatus.RECONCILIATION_REQUIRED, updated_at=self._utc_now())
                self._store.put(blocked)
            self._event("RECONCILIATION_ORDER_NOT_FOUND", "CRITICAL", local.intent)
            return ReconciliationResult(client_order_id, finding, self._store.get(client_order_id))
        if local is None:
            remote_filled = Decimal(str(remote.get("vol_exec", "0")))
            finding = ReconciliationFinding.UNEXPECTED_FILL if remote_filled > 0 else ReconciliationFinding.ORDER_UNKNOWN
            return ReconciliationResult(client_order_id, finding, None, exchange_status=str(remote.get("status", "")), external_order_id=str(remote.get("txid", "")), exchange_filled_quantity=remote_filled, details={"reason": "exchange order exists without local record"})

        record = self._record_from_exchange(local.intent, remote)
        finding = ReconciliationFinding.CONSISTENT
        remote_volume = Decimal(str(remote.get("vol", local.intent.quantity)))
        if remote_volume != local.intent.quantity or record.filled_quantity > local.intent.quantity:
            finding = ReconciliationFinding.QUANTITY_DIVERGENCE
            record = replace(record, status=LiveOrderStatus.RECONCILIATION_REQUIRED)
        elif local.external_order_id and record.external_order_id and local.external_order_id != record.external_order_id:
            finding = ReconciliationFinding.STATE_DIVERGENCE
            record = replace(record, status=LiveOrderStatus.RECONCILIATION_REQUIRED)
        self._store.put(record)
        if finding is not ReconciliationFinding.CONSISTENT:
            self._event("RECONCILIATION_DIVERGENCE", "CRITICAL", local.intent, finding=finding.value)
        return ReconciliationResult(client_order_id, finding, record, record.exchange_status, record.external_order_id, record.filled_quantity)

    async def verify_minimal_permissions(self) -> tuple[str, ...]:
        info = await self._api.get_api_key_info()
        permissions = tuple(str(item) for item in info.get("permissions", ()))
        dangerous = tuple(p for p in permissions if "withdraw" in p.lower())
        if dangerous:
            from .errors import LivePermissionError
            raise LivePermissionError("Kraken API key has withdrawal-related permissions")
        return permissions

    def _validate_intent(self, intent: LiveOrderIntent, *, constraints: MarketConstraints, reference_price: Decimal) -> None:
        if intent.mode != "LIVE": raise LiveIntentValidationError("intent mode must be LIVE")
        if intent.system_id not in self._allowed_system_ids: raise LiveIntentValidationError("system_id is not allowlisted")
        if intent.symbol not in self._allowed_symbols: raise LiveIntentValidationError("symbol is not allowlisted")
        if intent.side not in {OrderSide.BUY, OrderSide.SELL}: raise LiveIntentValidationError("side is invalid")
        if intent.order_type not in {OrderType.MARKET, OrderType.LIMIT}: raise LiveIntentValidationError("order_type is invalid")
        if intent.is_stale(self._utc_now()): raise LiveIntentValidationError("order intent is stale")
        if reference_price <= 0 or not reference_price.is_finite(): raise LiveIntentValidationError("reference_price must be finite and > 0")
        q = intent.quantity
        if q < constraints.min_qty: raise LiveIntentValidationError("quantity is below market minimum")
        if constraints.qty_step <= 0 or q % constraints.qty_step != 0: raise LiveIntentValidationError("quantity does not match market qty_step")
        if constraints.max_qty is not None and q > constraints.max_qty: raise LiveIntentValidationError("quantity exceeds market maximum")
        price = intent.limit_price if intent.limit_price is not None else reference_price
        if q * price < constraints.min_notional: raise LiveIntentValidationError("order notional is below market minimum")

    async def _find_exchange_order(self, client_order_id: str) -> Mapping[str, object] | None:
        for method, container in ((self._api.get_open_orders, "open"), (self._api.get_closed_orders, "closed")):
            result = await method(client_order_id=client_order_id)
            orders = result.get(container, {})
            if not isinstance(orders, Mapping):
                raise LiveReconciliationError(f"Kraken {container} orders response is invalid")
            if len(orders) > 1:
                raise LiveReconciliationError("multiple Kraken orders matched one cl_ord_id")
            if orders:
                txid, row = next(iter(orders.items()))
                if not isinstance(row, Mapping):
                    raise LiveReconciliationError("Kraken order row is invalid")
                return {"txid": str(txid), **row}
        return None

    def _record_from_exchange(self, intent: LiveOrderIntent, row: Mapping[str, object]) -> LiveOrderRecord:
        status = str(row.get("status", "unknown")).lower()
        vol = Decimal(str(row.get("vol", intent.quantity)))
        executed = Decimal(str(row.get("vol_exec", "0")))
        mapped = LiveOrderStatus.OPEN
        if status in {"closed", "filled"}: mapped = LiveOrderStatus.FILLED
        elif status in {"canceled", "cancelled", "expired"}: mapped = LiveOrderStatus.CANCELED
        elif executed > 0 and executed < vol: mapped = LiveOrderStatus.PARTIALLY_FILLED
        elif status not in {"open", "pending"}: mapped = LiveOrderStatus.UNKNOWN
        avg_price = Decimal(str(row.get("price", "0")))
        return LiveOrderRecord(intent, mapped, str(row.get("txid", "")) or None, status, executed, avg_price if avg_price > 0 else None, updated_at=self._utc_now())

    def _event(self, event_type: str, severity: str, intent: LiveOrderIntent, **details: str) -> None:
        self._audit.record(LiveAuditEvent(event_type, severity, intent.system_id, intent.client_order_id, self._utc_now(), details))

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None: raise RuntimeError("clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _deadline(self) -> str:
        # Safety deadline only; this is not a risk limit.
        return (self._utc_now() + timedelta(seconds=5)).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @staticmethod
    def _decimal_text(value: Decimal | None) -> str:
        if value is None: raise LiveIntentValidationError("missing decimal value")
        return format(value, "f")
