from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from app.services.backtest.dataset import canonical_candle_rows
from app.services.backtest.ids import stable_digest
from app.services.backtest.intrabar import HistoricalExitReason, resolve_intrabar
from app.services.backtest.models import IntrabarPolicy
from app.trading.paper import OrderSide, OrderStatus, OrderType, PaperOrderRequest

from .allocation import MasterAllocationPolicy
from .historical_replay import MasterHistoricalReplayPlan
from .historical_replay_coordinator import (
    MasterHistoricalReplayBarrier,
    MasterHistoricalReplayBarrierPhase,
    MasterHistoricalReplayTimeline,
)
from .historical_replay_paper_execution import (
    MasterHistoricalPaperAttemptStatus,
    MasterHistoricalPaperExecutionResult,
    MasterHistoricalPaperProposalEvidence,
    MasterHistoricalPaperRuntime,
)
from .historical_replay_preexecution import MasterHistoricalDecisionBarrier
from .models import CrewExposureSnapshot, MasterPortfolioSnapshot, SnapshotDataStatus
from .reservation import MasterReservationLedger, ReservationRecordStatus
from .snapshot import build_master_portfolio_snapshot

ZERO = Decimal("0")


class MasterHistoricalVirtualLotStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class MasterHistoricalVirtualLotRegistrationStatus(StrEnum):
    REGISTERED = "REGISTERED"
    NO_EXECUTED_ENTRIES = "NO_EXECUTED_ENTRIES"


class MasterHistoricalLifecycleStatus(StrEnum):
    PROCESSED_NO_EXIT = "PROCESSED_NO_EXIT"
    PROCESSED_WITH_EXITS = "PROCESSED_WITH_EXITS"


def _required_text(value: object, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _sha256(value: str, *, field_name: str) -> str:
    normalized = str(value).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return normalized


def _decimal(value: object, *, field_name: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not number.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return number


def _positive_decimal(value: object, *, field_name: str) -> Decimal:
    number = _decimal(value, field_name=field_name)
    if number <= ZERO:
        raise ValueError(f"{field_name} must be > 0")
    return number


def _non_negative_decimal(value: object, *, field_name: str) -> Decimal:
    number = _decimal(value, field_name=field_name)
    if number < ZERO:
        raise ValueError(f"{field_name} must be >= 0")
    return number


def _object_payload(value: object, *, field_name: str) -> object:
    canonical = getattr(value, "canonical_payload", None)
    if callable(canonical):
        return canonical()
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="python")
    if hasattr(value, "__dataclass_fields__"):
        return value
    raise ValueError(
        f"{field_name} must be a dataclass or expose canonical_payload()/model_dump()"
    )


def _object_fingerprint(value: object, *, field_name: str) -> str:
    return stable_digest(_object_payload(value, field_name=field_name))


def _enum_text(value: object, *, field_name: str) -> str:
    raw = getattr(value, "value", value)
    return _required_text(raw, field_name=field_name)


def _targets(value: object) -> tuple[Decimal, ...]:
    raw = tuple(value) if value is not None else ()
    return tuple(_positive_decimal(item, field_name="target") for item in raw)


def master_historical_virtual_lot_payload(
    lot: MasterHistoricalVirtualLot,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-virtual-lot.v1",
        "schema_version": lot.schema_version,
        "lot_id": lot.lot_id,
        "runtime_fingerprint_sha256": lot.runtime_fingerprint_sha256,
        "plan_fingerprint_sha256": lot.plan_fingerprint_sha256,
        "source_system_id": lot.source_system_id,
        "proposal_id": lot.proposal_id,
        "reservation_id": lot.reservation_id,
        "execution_attempt_fingerprint_sha256": lot.execution_attempt_fingerprint_sha256,
        "proposal_fingerprint_sha256": lot.proposal_fingerprint_sha256,
        "side": lot.side,
        "symbol": lot.symbol,
        "quantity": lot.quantity,
        "entry_price": lot.entry_price,
        "entry_fee": lot.entry_fee,
        "opened_at": lot.opened_at,
        "opened_candle_index": lot.opened_candle_index,
        "stop_price": lot.stop_price,
        "targets": lot.targets,
        "reserved_open_risk_amount": lot.reserved_open_risk_amount,
        "reserved_gross_exposure_amount": lot.reserved_gross_exposure_amount,
        "status": lot.status,
        "closed_at": lot.closed_at,
        "exit_reason": lot.exit_reason,
        "exit_reference_price": lot.exit_reference_price,
        "exit_fill_price": lot.exit_fill_price,
        "exit_fee": lot.exit_fee,
        "exit_order_id": lot.exit_order_id,
        "exit_fill_id": lot.exit_fill_id,
        "reservation_release_ref": lot.reservation_release_ref,
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalVirtualLot:
    lot_id: str
    runtime_fingerprint_sha256: str
    plan_fingerprint_sha256: str
    source_system_id: str
    proposal_id: str
    reservation_id: str
    execution_attempt_fingerprint_sha256: str
    proposal_fingerprint_sha256: str
    side: str
    symbol: str
    quantity: Decimal
    entry_price: Decimal
    entry_fee: Decimal
    opened_at: datetime
    opened_candle_index: int
    stop_price: Decimal
    targets: tuple[Decimal, ...]
    reserved_open_risk_amount: Decimal
    reserved_gross_exposure_amount: Decimal
    status: MasterHistoricalVirtualLotStatus
    fingerprint_sha256: str
    closed_at: datetime | None = None
    exit_reason: HistoricalExitReason | None = None
    exit_reference_price: Decimal | None = None
    exit_fill_price: Decimal | None = None
    exit_fee: Decimal | None = None
    exit_order_id: str | None = None
    exit_fill_id: str | None = None
    reservation_release_ref: str | None = None
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in (
            "lot_id",
            "source_system_id",
            "proposal_id",
            "reservation_id",
            "side",
            "symbol",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "runtime_fingerprint_sha256",
            "plan_fingerprint_sha256",
            "execution_attempt_fingerprint_sha256",
            "proposal_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        if self.side not in {"LONG", "SHORT"}:
            raise ValueError("virtual lot side must be LONG or SHORT")
        for field_name in ("quantity", "entry_price", "stop_price"):
            object.__setattr__(
                self,
                field_name,
                _positive_decimal(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "entry_fee",
            "reserved_open_risk_amount",
            "reserved_gross_exposure_amount",
        ):
            object.__setattr__(
                self,
                field_name,
                _non_negative_decimal(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(self, "opened_at", _utc(self.opened_at, field_name="opened_at"))
        if self.opened_candle_index < 1:
            raise ValueError("opened_candle_index must be >= 1")
        normalized_targets = _targets(self.targets)
        object.__setattr__(self, "targets", normalized_targets)
        if self.side == "LONG":
            if self.stop_price >= self.entry_price:
                raise ValueError("LONG virtual lot stop must be below entry price")
            if any(target <= self.entry_price for target in self.targets):
                raise ValueError("LONG virtual lot targets must be above entry price")
        else:
            if self.stop_price <= self.entry_price:
                raise ValueError("SHORT virtual lot stop must be above entry price")
            if any(target >= self.entry_price for target in self.targets):
                raise ValueError("SHORT virtual lot targets must be below entry price")
        self._validate_close_shape()
        if self.schema_version != "1.0":
            raise ValueError("unsupported virtual lot schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_virtual_lot_payload(self))
        if normalized != expected:
            raise ValueError("virtual lot fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def _validate_close_shape(self) -> None:
        close_values = (
            self.closed_at,
            self.exit_reason,
            self.exit_reference_price,
            self.exit_fill_price,
            self.exit_fee,
            self.exit_order_id,
            self.exit_fill_id,
            self.reservation_release_ref,
        )
        if self.status is MasterHistoricalVirtualLotStatus.OPEN:
            if any(value is not None for value in close_values):
                raise ValueError("OPEN virtual lot cannot carry exit metadata")
            return
        if self.status is not MasterHistoricalVirtualLotStatus.CLOSED:
            raise ValueError(f"unsupported virtual lot status: {self.status}")
        if any(value is None for value in close_values):
            raise ValueError("CLOSED virtual lot requires complete exit metadata")
        assert self.closed_at is not None
        assert self.exit_reference_price is not None
        assert self.exit_fill_price is not None
        assert self.exit_fee is not None
        object.__setattr__(self, "closed_at", _utc(self.closed_at, field_name="closed_at"))
        if self.closed_at < self.opened_at:
            raise ValueError("virtual lot cannot close before it opens")
        object.__setattr__(
            self,
            "exit_reference_price",
            _positive_decimal(self.exit_reference_price, field_name="exit_reference_price"),
        )
        object.__setattr__(
            self,
            "exit_fill_price",
            _positive_decimal(self.exit_fill_price, field_name="exit_fill_price"),
        )
        object.__setattr__(
            self,
            "exit_fee",
            _non_negative_decimal(self.exit_fee, field_name="exit_fee"),
        )
        object.__setattr__(
            self,
            "exit_order_id",
            _required_text(self.exit_order_id, field_name="exit_order_id"),
        )
        object.__setattr__(
            self,
            "exit_fill_id",
            _required_text(self.exit_fill_id, field_name="exit_fill_id"),
        )
        object.__setattr__(
            self,
            "reservation_release_ref",
            _required_text(
                self.reservation_release_ref,
                field_name="reservation_release_ref",
            ),
        )

    @property
    def average_entry(self) -> Decimal:
        return self.entry_price

    @property
    def signed_quantity(self) -> Decimal:
        return self.quantity if self.side == "LONG" else -self.quantity

    @property
    def gross_realized_pnl(self) -> Decimal | None:
        if self.exit_fill_price is None:
            return None
        if self.side == "LONG":
            return (self.exit_fill_price - self.entry_price) * self.quantity
        return (self.entry_price - self.exit_fill_price) * self.quantity

    @property
    def net_realized_pnl(self) -> Decimal | None:
        gross = self.gross_realized_pnl
        if gross is None or self.exit_fee is None:
            return None
        return gross - self.entry_fee - self.exit_fee


@dataclass(frozen=True, slots=True)
class MasterHistoricalVirtualLotBookSnapshot:
    book_id: str
    master_portfolio_id: str
    runtime_fingerprint_sha256: str
    plan_fingerprint_sha256: str
    observed_at: datetime
    mark_price: Decimal
    last_processed_barrier_sequence: int
    open_lots: tuple[MasterHistoricalVirtualLot, ...]
    closed_lots: tuple[MasterHistoricalVirtualLot, ...]
    net_signed_quantity: Decimal
    virtual_gross_exposure_amount: Decimal
    committed_open_risk_amount: Decimal
    realized_virtual_pnl_net: Decimal
    fingerprint_sha256: str
    single_master_capital: bool = field(default=True, init=False)
    branch_equity_summable: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in ("book_id", "master_portfolio_id"):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        for field_name in ("runtime_fingerprint_sha256", "plan_fingerprint_sha256"):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(self, "observed_at", _utc(self.observed_at, field_name="observed_at"))
        object.__setattr__(
            self,
            "mark_price",
            _positive_decimal(self.mark_price, field_name="mark_price"),
        )
        if self.last_processed_barrier_sequence < 0:
            raise ValueError("last_processed_barrier_sequence must be >= 0")
        expected_open = tuple(sorted(self.open_lots, key=_lot_sort_key))
        expected_closed = tuple(sorted(self.closed_lots, key=_lot_sort_key))
        if self.open_lots != expected_open or self.closed_lots != expected_closed:
            raise ValueError("virtual lot snapshot lots must be canonically sorted")
        all_ids = [lot.lot_id for lot in self.open_lots + self.closed_lots]
        if len(set(all_ids)) != len(all_ids):
            raise ValueError("virtual lot snapshot lot_id values must be unique")
        if any(lot.status is not MasterHistoricalVirtualLotStatus.OPEN for lot in self.open_lots):
            raise ValueError("open_lots must contain only OPEN lots")
        if any(
            lot.status is not MasterHistoricalVirtualLotStatus.CLOSED
            for lot in self.closed_lots
        ):
            raise ValueError("closed_lots must contain only CLOSED lots")
        expected_net = sum((lot.signed_quantity for lot in self.open_lots), ZERO)
        if self.net_signed_quantity != expected_net:
            raise ValueError("virtual lot net quantity does not match open lots")
        expected_gross = sum(
            (lot.quantity * self.mark_price for lot in self.open_lots),
            ZERO,
        )
        if self.virtual_gross_exposure_amount != expected_gross:
            raise ValueError("virtual gross exposure does not match open lots and mark")
        expected_risk = sum(
            (lot.reserved_open_risk_amount for lot in self.open_lots),
            ZERO,
        )
        if self.committed_open_risk_amount != expected_risk:
            raise ValueError("virtual committed open risk does not match open lots")
        expected_realized = sum(
            (lot.net_realized_pnl or ZERO for lot in self.closed_lots),
            ZERO,
        )
        if self.realized_virtual_pnl_net != expected_realized:
            raise ValueError("virtual realized PnL does not match closed lots")
        if self.schema_version != "1.0":
            raise ValueError("unsupported virtual lot book snapshot schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_virtual_lot_book_snapshot_payload(self))
        if normalized != expected:
            raise ValueError("virtual lot book snapshot fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def master_historical_virtual_lot_book_snapshot_payload(
    snapshot: MasterHistoricalVirtualLotBookSnapshot,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-virtual-lot-book-snapshot.v1",
        "schema_version": snapshot.schema_version,
        "book_id": snapshot.book_id,
        "master_portfolio_id": snapshot.master_portfolio_id,
        "runtime_fingerprint_sha256": snapshot.runtime_fingerprint_sha256,
        "plan_fingerprint_sha256": snapshot.plan_fingerprint_sha256,
        "observed_at": snapshot.observed_at,
        "mark_price": snapshot.mark_price,
        "last_processed_barrier_sequence": snapshot.last_processed_barrier_sequence,
        "open_lots": [master_historical_virtual_lot_payload(lot) for lot in snapshot.open_lots],
        "closed_lots": [
            master_historical_virtual_lot_payload(lot) for lot in snapshot.closed_lots
        ],
        "net_signed_quantity": snapshot.net_signed_quantity,
        "virtual_gross_exposure_amount": snapshot.virtual_gross_exposure_amount,
        "committed_open_risk_amount": snapshot.committed_open_risk_amount,
        "realized_virtual_pnl_net": snapshot.realized_virtual_pnl_net,
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalVirtualLotRegistrationResult:
    registration_id: str
    execution_result_fingerprint_sha256: str
    decision_barrier_fingerprint_sha256: str
    status: MasterHistoricalVirtualLotRegistrationStatus
    registered_lot_fingerprints_sha256: tuple[str, ...]
    book_fingerprint_sha256: str
    ledger_fingerprint_sha256: str
    fingerprint_sha256: str
    mutation_applied: bool
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "registration_id",
            _required_text(self.registration_id, field_name="registration_id"),
        )
        for field_name in (
            "execution_result_fingerprint_sha256",
            "decision_barrier_fingerprint_sha256",
            "book_fingerprint_sha256",
            "ledger_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        normalized_lots = tuple(
            _sha256(value, field_name="registered_lot_fingerprints_sha256")
            for value in self.registered_lot_fingerprints_sha256
        )
        object.__setattr__(self, "registered_lot_fingerprints_sha256", normalized_lots)
        if self.status is MasterHistoricalVirtualLotRegistrationStatus.REGISTERED:
            if not normalized_lots or not self.mutation_applied:
                raise ValueError("REGISTERED virtual lot result requires lot mutation")
        elif self.status is MasterHistoricalVirtualLotRegistrationStatus.NO_EXECUTED_ENTRIES:
            if normalized_lots or self.mutation_applied:
                raise ValueError("NO_EXECUTED_ENTRIES cannot register lots")
        else:
            raise ValueError(f"unsupported virtual lot registration status: {self.status}")
        if self.schema_version != "1.0":
            raise ValueError("unsupported virtual lot registration schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_virtual_lot_registration_payload(self))
        if normalized != expected:
            raise ValueError("virtual lot registration fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def master_historical_virtual_lot_registration_payload(
    result: MasterHistoricalVirtualLotRegistrationResult,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-virtual-lot-registration.v1",
        "schema_version": result.schema_version,
        "registration_id": result.registration_id,
        "execution_result_fingerprint_sha256": result.execution_result_fingerprint_sha256,
        "decision_barrier_fingerprint_sha256": result.decision_barrier_fingerprint_sha256,
        "status": result.status,
        "registered_lot_fingerprints_sha256": result.registered_lot_fingerprints_sha256,
        "book_fingerprint_sha256": result.book_fingerprint_sha256,
        "ledger_fingerprint_sha256": result.ledger_fingerprint_sha256,
        "mutation_applied": result.mutation_applied,
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalVirtualLotExitEvent:
    rank: int
    lot_id: str
    source_system_id: str
    proposal_id: str
    reservation_id: str
    side: str
    reason: HistoricalExitReason
    reference_price: Decimal
    fill_price: Decimal
    quantity: Decimal
    exit_fee: Decimal
    gross_realized_pnl: Decimal
    net_realized_pnl: Decimal
    observed_at: datetime
    broker_order_id: str
    fill_id: str
    reservation_release_ref: str
    lot_before_fingerprint_sha256: str
    lot_after_fingerprint_sha256: str
    fingerprint_sha256: str
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError("virtual lot exit rank must be >= 1")
        for field_name in (
            "lot_id",
            "source_system_id",
            "proposal_id",
            "reservation_id",
            "side",
            "broker_order_id",
            "fill_id",
            "reservation_release_ref",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        for field_name in ("lot_before_fingerprint_sha256", "lot_after_fingerprint_sha256"):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        for field_name in ("reference_price", "fill_price", "quantity"):
            object.__setattr__(
                self,
                field_name,
                _positive_decimal(getattr(self, field_name), field_name=field_name),
            )
        for field_name in ("exit_fee",):
            object.__setattr__(
                self,
                field_name,
                _non_negative_decimal(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "gross_realized_pnl",
            _decimal(self.gross_realized_pnl, field_name="gross_realized_pnl"),
        )
        object.__setattr__(
            self,
            "net_realized_pnl",
            _decimal(self.net_realized_pnl, field_name="net_realized_pnl"),
        )
        object.__setattr__(self, "observed_at", _utc(self.observed_at, field_name="observed_at"))
        if self.side not in {"LONG", "SHORT"}:
            raise ValueError("virtual lot exit side must be LONG or SHORT")
        if self.schema_version != "1.0":
            raise ValueError("unsupported virtual lot exit event schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_virtual_lot_exit_event_payload(self))
        if normalized != expected:
            raise ValueError("virtual lot exit event fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def master_historical_virtual_lot_exit_event_payload(
    event: MasterHistoricalVirtualLotExitEvent,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-virtual-lot-exit.v1",
        "schema_version": event.schema_version,
        "rank": event.rank,
        "lot_id": event.lot_id,
        "source_system_id": event.source_system_id,
        "proposal_id": event.proposal_id,
        "reservation_id": event.reservation_id,
        "side": event.side,
        "reason": event.reason,
        "reference_price": event.reference_price,
        "fill_price": event.fill_price,
        "quantity": event.quantity,
        "exit_fee": event.exit_fee,
        "gross_realized_pnl": event.gross_realized_pnl,
        "net_realized_pnl": event.net_realized_pnl,
        "observed_at": event.observed_at,
        "broker_order_id": event.broker_order_id,
        "fill_id": event.fill_id,
        "reservation_release_ref": event.reservation_release_ref,
        "lot_before_fingerprint_sha256": event.lot_before_fingerprint_sha256,
        "lot_after_fingerprint_sha256": event.lot_after_fingerprint_sha256,
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalLifecycleResult:
    result_id: str
    book_id: str
    master_portfolio_id: str
    plan_fingerprint_sha256: str
    timeline_fingerprint_sha256: str
    barrier_fingerprint_sha256: str
    barrier_sequence: int
    candle_index: int
    phase: MasterHistoricalReplayBarrierPhase
    observed_at: datetime
    candle_fingerprint_sha256: str
    status: MasterHistoricalLifecycleStatus
    book_before_fingerprint_sha256: str
    book_after_fingerprint_sha256: str
    ledger_before_fingerprint_sha256: str
    ledger_after_fingerprint_sha256: str
    account_before_fingerprint_sha256: str
    account_after_fingerprint_sha256: str
    exit_events: tuple[MasterHistoricalVirtualLotExitEvent, ...]
    reservation_release_mutation_applied: bool
    fingerprint_sha256: str
    single_master_capital: bool = field(default=True, init=False)
    uses_branch_brokers: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    paper_broker_authority: bool = field(default=True, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in ("result_id", "book_id", "master_portfolio_id"):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "plan_fingerprint_sha256",
            "timeline_fingerprint_sha256",
            "barrier_fingerprint_sha256",
            "candle_fingerprint_sha256",
            "book_before_fingerprint_sha256",
            "book_after_fingerprint_sha256",
            "ledger_before_fingerprint_sha256",
            "ledger_after_fingerprint_sha256",
            "account_before_fingerprint_sha256",
            "account_after_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        if self.barrier_sequence < 1 or self.candle_index < 1:
            raise ValueError("historical lifecycle barrier indexes must be >= 1")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, field_name="observed_at"))
        if self.status is MasterHistoricalLifecycleStatus.PROCESSED_NO_EXIT:
            if self.exit_events or self.reservation_release_mutation_applied:
                raise ValueError("PROCESSED_NO_EXIT cannot carry exits or releases")
        elif self.status is MasterHistoricalLifecycleStatus.PROCESSED_WITH_EXITS:
            if not self.exit_events or not self.reservation_release_mutation_applied:
                raise ValueError("PROCESSED_WITH_EXITS requires exit events and releases")
        else:
            raise ValueError(f"unsupported historical lifecycle status: {self.status}")
        if tuple(event.rank for event in self.exit_events) != tuple(
            range(1, len(self.exit_events) + 1)
        ):
            raise ValueError("historical lifecycle exit ranks must be contiguous")
        if self.schema_version != "1.0":
            raise ValueError("unsupported historical lifecycle result schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_lifecycle_result_payload(self))
        if normalized != expected:
            raise ValueError("historical lifecycle result fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def master_historical_lifecycle_result_payload(
    result: MasterHistoricalLifecycleResult,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-virtual-lifecycle-result.v1",
        "schema_version": result.schema_version,
        "result_id": result.result_id,
        "book_id": result.book_id,
        "master_portfolio_id": result.master_portfolio_id,
        "plan_fingerprint_sha256": result.plan_fingerprint_sha256,
        "timeline_fingerprint_sha256": result.timeline_fingerprint_sha256,
        "barrier_fingerprint_sha256": result.barrier_fingerprint_sha256,
        "barrier_sequence": result.barrier_sequence,
        "candle_index": result.candle_index,
        "phase": result.phase,
        "observed_at": result.observed_at,
        "candle_fingerprint_sha256": result.candle_fingerprint_sha256,
        "status": result.status,
        "book_before_fingerprint_sha256": result.book_before_fingerprint_sha256,
        "book_after_fingerprint_sha256": result.book_after_fingerprint_sha256,
        "ledger_before_fingerprint_sha256": result.ledger_before_fingerprint_sha256,
        "ledger_after_fingerprint_sha256": result.ledger_after_fingerprint_sha256,
        "account_before_fingerprint_sha256": result.account_before_fingerprint_sha256,
        "account_after_fingerprint_sha256": result.account_after_fingerprint_sha256,
        "exit_events": [
            master_historical_virtual_lot_exit_event_payload(item)
            for item in result.exit_events
        ],
        "reservation_release_mutation_applied": (
            result.reservation_release_mutation_applied
        ),
    }


def _lot_sort_key(lot: MasterHistoricalVirtualLot) -> tuple[object, ...]:
    return (lot.opened_at, lot.source_system_id, lot.proposal_id, lot.lot_id)


class MasterHistoricalVirtualLotBook:
    """Logical per-crew lots over one physical Master PAPER broker account."""

    def __init__(
        self,
        *,
        plan: MasterHistoricalReplayPlan,
        runtime: MasterHistoricalPaperRuntime,
    ) -> None:
        if runtime.identity.plan_id != plan.plan_id:
            raise ValueError("virtual lot book runtime does not bind replay plan")
        if runtime.identity.plan_fingerprint_sha256 != plan.fingerprint_sha256:
            raise ValueError("virtual lot book runtime plan fingerprint mismatch")
        self.plan = plan
        self.runtime = runtime
        self.book_id = "master-historical-virtual-lots:" + stable_digest(
            {
                "schema": "money-heist.master-historical-virtual-lot-book-id.v1",
                "plan_fingerprint_sha256": plan.fingerprint_sha256,
                "runtime_fingerprint_sha256": runtime.identity.fingerprint_sha256,
            }
        )
        self._lots: dict[str, MasterHistoricalVirtualLot] = {}
        self._registered_reservations: set[str] = set()
        self._registrations: dict[
            str, tuple[str, MasterHistoricalVirtualLotRegistrationResult]
        ] = {}
        self._processed: dict[str, tuple[str, MasterHistoricalLifecycleResult]] = {}
        self._last_processed_barrier_sequence = 0
        self._last_mark: Decimal | None = None
        self.risk_authority = False
        self.admission_authority = False
        self.paper_broker_authority = True
        self.live_authority = False

    @property
    def lots(self) -> tuple[MasterHistoricalVirtualLot, ...]:
        return tuple(sorted(self._lots.values(), key=_lot_sort_key))

    @property
    def open_lots(self) -> tuple[MasterHistoricalVirtualLot, ...]:
        return tuple(
            lot for lot in self.lots if lot.status is MasterHistoricalVirtualLotStatus.OPEN
        )

    @property
    def closed_lots(self) -> tuple[MasterHistoricalVirtualLot, ...]:
        return tuple(
            lot for lot in self.lots if lot.status is MasterHistoricalVirtualLotStatus.CLOSED
        )

    @property
    def last_processed_barrier_sequence(self) -> int:
        return self._last_processed_barrier_sequence

    def snapshot(
        self,
        *,
        observed_at: datetime,
        mark_price: Decimal | None = None,
    ) -> MasterHistoricalVirtualLotBookSnapshot:
        observed = _utc(observed_at, field_name="observed_at")
        mark = mark_price if mark_price is not None else self._last_mark
        if mark is None:
            raise ValueError("virtual lot book snapshot requires an explicit or observed mark")
        mark = _positive_decimal(mark, field_name="mark_price")
        open_lots = self.open_lots
        closed_lots = self.closed_lots
        net_quantity = sum((lot.signed_quantity for lot in open_lots), ZERO)
        gross = sum((lot.quantity * mark for lot in open_lots), ZERO)
        open_risk = sum((lot.reserved_open_risk_amount for lot in open_lots), ZERO)
        realized = sum((lot.net_realized_pnl or ZERO for lot in closed_lots), ZERO)
        payload = {
            "schema": "money-heist.master-historical-virtual-lot-book-snapshot.v1",
            "schema_version": "1.0",
            "book_id": self.book_id,
            "master_portfolio_id": self.plan.master_portfolio_id,
            "runtime_fingerprint_sha256": self.runtime.identity.fingerprint_sha256,
            "plan_fingerprint_sha256": self.plan.fingerprint_sha256,
            "observed_at": observed,
            "mark_price": mark,
            "last_processed_barrier_sequence": self._last_processed_barrier_sequence,
            "open_lots": [master_historical_virtual_lot_payload(lot) for lot in open_lots],
            "closed_lots": [
                master_historical_virtual_lot_payload(lot) for lot in closed_lots
            ],
            "net_signed_quantity": net_quantity,
            "virtual_gross_exposure_amount": gross,
            "committed_open_risk_amount": open_risk,
            "realized_virtual_pnl_net": realized,
        }
        return MasterHistoricalVirtualLotBookSnapshot(
            book_id=self.book_id,
            master_portfolio_id=self.plan.master_portfolio_id,
            runtime_fingerprint_sha256=self.runtime.identity.fingerprint_sha256,
            plan_fingerprint_sha256=self.plan.fingerprint_sha256,
            observed_at=observed,
            mark_price=mark,
            last_processed_barrier_sequence=self._last_processed_barrier_sequence,
            open_lots=open_lots,
            closed_lots=closed_lots,
            net_signed_quantity=net_quantity,
            virtual_gross_exposure_amount=gross,
            committed_open_risk_amount=open_risk,
            realized_virtual_pnl_net=realized,
            fingerprint_sha256=stable_digest(payload),
        )


def build_master_historical_virtual_lot_book(
    *,
    plan: MasterHistoricalReplayPlan,
    runtime: MasterHistoricalPaperRuntime,
) -> MasterHistoricalVirtualLotBook:
    return MasterHistoricalVirtualLotBook(plan=plan, runtime=runtime)


def _timeline_barrier(
    *,
    timeline: MasterHistoricalReplayTimeline,
    sequence: int,
) -> MasterHistoricalReplayBarrier:
    if sequence < 1 or sequence > len(timeline.barriers):
        raise ValueError("historical lifecycle barrier sequence is absent from timeline")
    return timeline.barriers[sequence - 1]


def _canonical_barrier_row(
    *,
    plan: MasterHistoricalReplayPlan,
    barrier: MasterHistoricalReplayBarrier,
    candle: object,
) -> dict[str, object]:
    row = canonical_candle_rows(
        (candle,),
        expected_symbol=plan.symbol,
        expected_timeframe=plan.timeframe,
    )[0]
    if stable_digest(row) != barrier.candle_fingerprint_sha256:
        raise ValueError("historical lifecycle candle does not match timeline fingerprint")
    return row


async def _physical_signed_quantity(
    *,
    runtime: MasterHistoricalPaperRuntime,
    symbol: str,
) -> Decimal:
    positions = await runtime.broker.get_positions()
    matches = [position for position in positions if position.symbol == symbol and position.is_open]
    if len(matches) > 1:
        raise RuntimeError("Master PAPER broker exposed duplicate positions for one symbol")
    if not matches:
        return ZERO
    return _decimal(matches[0].signed_quantity, field_name="physical signed quantity")


async def _assert_net_invariant(
    *,
    book: MasterHistoricalVirtualLotBook,
) -> None:
    logical = sum((lot.signed_quantity for lot in book.open_lots), ZERO)
    physical = await _physical_signed_quantity(
        runtime=book.runtime,
        symbol=book.plan.symbol,
    )
    if physical != logical:
        raise RuntimeError(
            "physical Master position does not equal net signed open virtual lots"
        )


def _registration_evidence_map(
    evidence: tuple[MasterHistoricalPaperProposalEvidence, ...],
) -> dict[tuple[str, str], MasterHistoricalPaperProposalEvidence]:
    mapped: dict[tuple[str, str], MasterHistoricalPaperProposalEvidence] = {}
    for item in evidence:
        proposal_id = _required_text(
            getattr(item.proposal, "proposal_id", ""),
            field_name="proposal.proposal_id",
        )
        key = (item.system_id, proposal_id)
        if key in mapped:
            raise ValueError("virtual lot proposal evidence cannot duplicate system/proposal")
        mapped[key] = item
    return mapped


def _validate_registration_context(
    *,
    book: MasterHistoricalVirtualLotBook,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    decision_barrier: MasterHistoricalDecisionBarrier,
    execution_result: MasterHistoricalPaperExecutionResult,
    ledger: MasterReservationLedger,
) -> MasterHistoricalReplayBarrier:
    if book.plan.fingerprint_sha256 != plan.fingerprint_sha256:
        raise ValueError("virtual lot book plan mismatch")
    if book.runtime.identity.fingerprint_sha256 != execution_result.runtime_fingerprint_sha256:
        raise ValueError("virtual lot registration runtime mismatch")
    if execution_result.plan_fingerprint_sha256 != plan.fingerprint_sha256:
        raise ValueError("virtual lot registration execution plan mismatch")
    if execution_result.timeline_fingerprint_sha256 != timeline.fingerprint_sha256:
        raise ValueError("virtual lot registration timeline mismatch")
    if execution_result.decision_barrier_fingerprint_sha256 != decision_barrier.fingerprint_sha256:
        raise ValueError("virtual lot registration decision barrier mismatch")
    if execution_result.barrier_result_id != decision_barrier.barrier_result_id:
        raise ValueError("virtual lot registration barrier result mismatch")
    source_barrier = _timeline_barrier(
        timeline=timeline,
        sequence=decision_barrier.barrier_sequence,
    )
    if source_barrier.phase is not MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE:
        raise ValueError("virtual lots may register only from a CLOSE execution barrier")
    if source_barrier.fingerprint_sha256 != decision_barrier.barrier_fingerprint_sha256:
        raise ValueError("virtual lot registration source barrier mismatch")
    if execution_result.observed_at != source_barrier.observed_at:
        raise ValueError("virtual lot registration execution time mismatch")
    if ledger.snapshot().fingerprint_sha256 != execution_result.final_ledger_fingerprint_sha256:
        raise ValueError("virtual lot registration requires exact Step 5 final ledger")
    if book.last_processed_barrier_sequence not in {0, source_barrier.sequence}:
        raise ValueError(
            "virtual lot registration requires lifecycle positioned at execution CLOSE barrier"
        )
    return source_barrier


def _build_open_lot(
    *,
    book: MasterHistoricalVirtualLotBook,
    plan: MasterHistoricalReplayPlan,
    attempt,
    proposal: object,
    reservation,
    opened_candle_index: int,
) -> MasterHistoricalVirtualLot:
    if attempt.fill_price is None or attempt.fill_fee is None or attempt.filled_at is None:
        raise ValueError("executed Step 5 attempt requires complete fill evidence")
    proposal_fingerprint = _object_fingerprint(proposal, field_name="proposal")
    if proposal_fingerprint != attempt.proposal_fingerprint_sha256:
        raise ValueError("virtual lot proposal fingerprint mismatch")
    side = _enum_text(getattr(proposal, "side", ""), field_name="proposal.side")
    stop_price = _positive_decimal(getattr(proposal, "stop_price", None), field_name="stop_price")
    targets = _targets(getattr(proposal, "targets", ()))
    lot_id = "virtual-lot:" + stable_digest(
        {
            "schema": "money-heist.master-historical-virtual-lot-id.v1",
            "execution_attempt_fingerprint_sha256": attempt.fingerprint_sha256,
            "reservation_id": attempt.reservation_id,
        }
    )
    payload = {
        "schema": "money-heist.master-historical-virtual-lot.v1",
        "schema_version": "1.0",
        "lot_id": lot_id,
        "runtime_fingerprint_sha256": book.runtime.identity.fingerprint_sha256,
        "plan_fingerprint_sha256": plan.fingerprint_sha256,
        "source_system_id": attempt.source_system_id,
        "proposal_id": attempt.proposal_id,
        "reservation_id": attempt.reservation_id,
        "execution_attempt_fingerprint_sha256": attempt.fingerprint_sha256,
        "proposal_fingerprint_sha256": proposal_fingerprint,
        "side": side,
        "symbol": attempt.symbol,
        "quantity": attempt.quantity,
        "entry_price": attempt.fill_price,
        "entry_fee": attempt.fill_fee,
        "opened_at": attempt.filled_at,
        "opened_candle_index": opened_candle_index,
        "stop_price": stop_price,
        "targets": targets,
        "reserved_open_risk_amount": reservation.request.open_risk_amount,
        "reserved_gross_exposure_amount": reservation.request.gross_exposure_amount,
        "status": MasterHistoricalVirtualLotStatus.OPEN,
        "closed_at": None,
        "exit_reason": None,
        "exit_reference_price": None,
        "exit_fill_price": None,
        "exit_fee": None,
        "exit_order_id": None,
        "exit_fill_id": None,
        "reservation_release_ref": None,
    }
    return MasterHistoricalVirtualLot(
        lot_id=lot_id,
        runtime_fingerprint_sha256=book.runtime.identity.fingerprint_sha256,
        plan_fingerprint_sha256=plan.fingerprint_sha256,
        source_system_id=attempt.source_system_id,
        proposal_id=attempt.proposal_id,
        reservation_id=attempt.reservation_id,
        execution_attempt_fingerprint_sha256=attempt.fingerprint_sha256,
        proposal_fingerprint_sha256=proposal_fingerprint,
        side=side,
        symbol=attempt.symbol,
        quantity=attempt.quantity,
        entry_price=attempt.fill_price,
        entry_fee=attempt.fill_fee,
        opened_at=attempt.filled_at,
        opened_candle_index=opened_candle_index,
        stop_price=stop_price,
        targets=targets,
        reserved_open_risk_amount=reservation.request.open_risk_amount,
        reserved_gross_exposure_amount=reservation.request.gross_exposure_amount,
        status=MasterHistoricalVirtualLotStatus.OPEN,
        fingerprint_sha256=stable_digest(payload),
    )


async def register_master_historical_virtual_lots(
    *,
    book: MasterHistoricalVirtualLotBook,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    decision_barrier: MasterHistoricalDecisionBarrier,
    execution_result: MasterHistoricalPaperExecutionResult,
    ledger: MasterReservationLedger,
    candle: object,
    proposal_evidence: tuple[MasterHistoricalPaperProposalEvidence, ...],
) -> MasterHistoricalVirtualLotRegistrationResult:
    source_barrier = _validate_registration_context(
        book=book,
        plan=plan,
        timeline=timeline,
        decision_barrier=decision_barrier,
        execution_result=execution_result,
        ledger=ledger,
    )
    row = _canonical_barrier_row(plan=plan, barrier=source_barrier, candle=candle)
    registration_mark = _positive_decimal(row["close"], field_name="registration close mark")
    executed = tuple(
        attempt
        for attempt in execution_result.attempts
        if attempt.status is MasterHistoricalPaperAttemptStatus.EXECUTED
    )
    evidence_map = _registration_evidence_map(proposal_evidence)
    expected_keys = {(attempt.source_system_id, attempt.proposal_id) for attempt in executed}
    if set(evidence_map) != expected_keys:
        raise ValueError("virtual lot proposal evidence must match executed Step 5 entries exactly")
    request_fingerprint = stable_digest(
        {
            "schema": "money-heist.master-historical-virtual-lot-registration-call.v1",
            "execution_result_fingerprint_sha256": execution_result.fingerprint_sha256,
            "decision_barrier_fingerprint_sha256": decision_barrier.fingerprint_sha256,
            "candle_fingerprint_sha256": stable_digest(row),
            "proposal_fingerprints": [
                _object_fingerprint(evidence_map[key].proposal, field_name="proposal")
                for key in sorted(evidence_map)
            ],
        }
    )
    previous = book._registrations.get(execution_result.fingerprint_sha256)
    if previous is not None:
        previous_request, previous_result = previous
        if previous_request != request_fingerprint:
            raise ValueError("virtual lot registration conflicts with prior Step 5 registration")
        return previous_result

    new_lots: list[MasterHistoricalVirtualLot] = []
    for attempt in executed:
        if attempt.reservation_id in book._registered_reservations:
            raise ValueError("virtual lot reservation was already registered by another execution")
        reservation = ledger.get(attempt.reservation_id)
        if reservation.status is not ReservationRecordStatus.COMMITTED:
            raise ValueError("executed virtual lot requires a COMMITTED reservation")
        if reservation.request.system_id != attempt.source_system_id:
            raise ValueError("virtual lot reservation source system mismatch")
        if reservation.request.request_ref != attempt.proposal_id:
            raise ValueError("virtual lot reservation proposal mismatch")
        evidence = evidence_map[(attempt.source_system_id, attempt.proposal_id)]
        lot = _build_open_lot(
            book=book,
            plan=plan,
            attempt=attempt,
            proposal=evidence.proposal,
            reservation=reservation,
            opened_candle_index=source_barrier.candle_index,
        )
        new_lots.append(lot)

    for lot in new_lots:
        book._lots[lot.lot_id] = lot
        book._registered_reservations.add(lot.reservation_id)
    if book._last_processed_barrier_sequence == 0:
        book._last_processed_barrier_sequence = source_barrier.sequence
    book._last_mark = registration_mark
    await _assert_net_invariant(book=book)
    snapshot = book.snapshot(
        observed_at=execution_result.observed_at,
        mark_price=book._last_mark,
    )
    status = (
        MasterHistoricalVirtualLotRegistrationStatus.REGISTERED
        if new_lots
        else MasterHistoricalVirtualLotRegistrationStatus.NO_EXECUTED_ENTRIES
    )
    registration_id = "virtual-lot-registration:" + stable_digest(
        {
            "schema": "money-heist.master-historical-virtual-lot-registration-id.v1",
            "execution_result_fingerprint_sha256": execution_result.fingerprint_sha256,
            "lot_fingerprints": [lot.fingerprint_sha256 for lot in new_lots],
        }
    )
    payload = {
        "schema": "money-heist.master-historical-virtual-lot-registration.v1",
        "schema_version": "1.0",
        "registration_id": registration_id,
        "execution_result_fingerprint_sha256": execution_result.fingerprint_sha256,
        "decision_barrier_fingerprint_sha256": decision_barrier.fingerprint_sha256,
        "status": status,
        "registered_lot_fingerprints_sha256": tuple(
            lot.fingerprint_sha256 for lot in new_lots
        ),
        "book_fingerprint_sha256": snapshot.fingerprint_sha256,
        "ledger_fingerprint_sha256": ledger.snapshot().fingerprint_sha256,
        "mutation_applied": bool(new_lots),
    }
    result = MasterHistoricalVirtualLotRegistrationResult(
        registration_id=registration_id,
        execution_result_fingerprint_sha256=execution_result.fingerprint_sha256,
        decision_barrier_fingerprint_sha256=decision_barrier.fingerprint_sha256,
        status=status,
        registered_lot_fingerprints_sha256=tuple(
            lot.fingerprint_sha256 for lot in new_lots
        ),
        book_fingerprint_sha256=snapshot.fingerprint_sha256,
        ledger_fingerprint_sha256=ledger.snapshot().fingerprint_sha256,
        mutation_applied=bool(new_lots),
        fingerprint_sha256=stable_digest(payload),
    )
    book._registrations[execution_result.fingerprint_sha256] = (
        request_fingerprint,
        result,
    )
    return result


def _phase_mark(
    *,
    barrier: MasterHistoricalReplayBarrier,
    row: dict[str, object],
) -> Decimal:
    field_name = (
        "open"
        if barrier.phase is MasterHistoricalReplayBarrierPhase.CANDLE_OPEN
        else "close"
    )
    return _positive_decimal(row[field_name], field_name=f"candle {field_name}")


def _eligible_resolution(
    *,
    lot: MasterHistoricalVirtualLot,
    barrier: MasterHistoricalReplayBarrier,
    row: dict[str, object],
    policy: IntrabarPolicy,
):
    if barrier.candle_index <= lot.opened_candle_index:
        return None
    resolution = resolve_intrabar(lot, row, policy=policy)
    if barrier.phase is MasterHistoricalReplayBarrierPhase.CANDLE_OPEN:
        return resolution if resolution is not None and resolution.is_gap else None
    if resolution is not None and resolution.is_gap:
        raise RuntimeError("historical gap exit must be processed at CANDLE_OPEN")
    return resolution


def _exit_client_order_id(
    *,
    book: MasterHistoricalVirtualLotBook,
    lot: MasterHistoricalVirtualLot,
    barrier: MasterHistoricalReplayBarrier,
    reason: HistoricalExitReason,
) -> str:
    digest = stable_digest(
        {
            "schema": "money-heist.master-historical-virtual-lot-exit-order-id.v1",
            "book_id": book.book_id,
            "lot_fingerprint_sha256": lot.fingerprint_sha256,
            "barrier_fingerprint_sha256": barrier.fingerprint_sha256,
            "reason": reason,
        }
    )
    return f"master-historical-exit:{digest}"


async def _execute_virtual_lot_exit(
    *,
    book: MasterHistoricalVirtualLotBook,
    ledger: MasterReservationLedger,
    barrier: MasterHistoricalReplayBarrier,
    lot: MasterHistoricalVirtualLot,
    resolution,
    rank: int,
) -> MasterHistoricalVirtualLotExitEvent:
    reservation = ledger.get(lot.reservation_id)
    if reservation.status is not ReservationRecordStatus.COMMITTED:
        raise RuntimeError("OPEN virtual lot requires its reservation to remain COMMITTED")
    runtime = book.runtime
    runtime.set_time(barrier.observed_at)
    reference = _positive_decimal(
        resolution.reference_price,
        field_name="exit reference price",
    )
    changed = await runtime.broker.process_price(
        lot.symbol,
        reference,
        observed_at=barrier.observed_at,
    )
    if tuple(changed):
        raise RuntimeError("virtual lifecycle cannot coexist with pending broker orders/stops")
    side = OrderSide.SELL if lot.side == "LONG" else OrderSide.BUY
    client_order_id = _exit_client_order_id(
        book=book,
        lot=lot,
        barrier=barrier,
        reason=resolution.reason,
    )
    is_target = resolution.reason in {
        HistoricalExitReason.TARGET_GAP,
        HistoricalExitReason.TARGET_INTRABAR,
    }
    request = PaperOrderRequest(
        system_id=book.plan.master_portfolio_id,
        symbol=lot.symbol,
        side=side,
        order_type=OrderType.LIMIT if is_target else OrderType.MARKET,
        quantity=lot.quantity,
        client_order_id=client_order_id,
        limit_price=reference if is_target else None,
    )
    order = await runtime.broker.submit_order(
        request,
        trigger=f"MASTER_HISTORICAL_{resolution.reason.value}",
    )
    if order.status is not OrderStatus.FILLED:
        raise RuntimeError("historical virtual lot exit did not fill atomically")
    fills = await runtime.broker.get_fills()
    matches = [fill for fill in fills if fill.broker_order_id == order.broker_order_id]
    if len(matches) != 1:
        raise RuntimeError("historical virtual lot exit requires exactly one fill")
    fill = matches[0]
    release_ref = "historical-virtual-lot-release:" + stable_digest(
        {
            "schema": "money-heist.master-historical-virtual-lot-release.v1",
            "lot_fingerprint_sha256": lot.fingerprint_sha256,
            "barrier_fingerprint_sha256": barrier.fingerprint_sha256,
            "fill_id": fill.fill_id,
        }
    )
    ledger.release(
        lot.reservation_id,
        released_at=barrier.observed_at,
        release_ref=release_ref,
    )
    gross = (
        (fill.price - lot.entry_price) * lot.quantity
        if lot.side == "LONG"
        else (lot.entry_price - fill.price) * lot.quantity
    )
    net = gross - lot.entry_fee - fill.fee
    updated_payload = {
        **master_historical_virtual_lot_payload(lot),
        "status": MasterHistoricalVirtualLotStatus.CLOSED,
        "closed_at": barrier.observed_at,
        "exit_reason": resolution.reason,
        "exit_reference_price": reference,
        "exit_fill_price": fill.price,
        "exit_fee": fill.fee,
        "exit_order_id": order.broker_order_id,
        "exit_fill_id": fill.fill_id,
        "reservation_release_ref": release_ref,
    }
    updated_payload.pop("fingerprint_sha256", None)
    updated = replace(
        lot,
        status=MasterHistoricalVirtualLotStatus.CLOSED,
        closed_at=barrier.observed_at,
        exit_reason=resolution.reason,
        exit_reference_price=reference,
        exit_fill_price=fill.price,
        exit_fee=fill.fee,
        exit_order_id=order.broker_order_id,
        exit_fill_id=fill.fill_id,
        reservation_release_ref=release_ref,
        fingerprint_sha256=stable_digest(updated_payload),
    )
    book._lots[lot.lot_id] = updated
    event_payload = {
        "schema": "money-heist.master-historical-virtual-lot-exit.v1",
        "schema_version": "1.0",
        "rank": rank,
        "lot_id": lot.lot_id,
        "source_system_id": lot.source_system_id,
        "proposal_id": lot.proposal_id,
        "reservation_id": lot.reservation_id,
        "side": lot.side,
        "reason": resolution.reason,
        "reference_price": reference,
        "fill_price": fill.price,
        "quantity": fill.quantity,
        "exit_fee": fill.fee,
        "gross_realized_pnl": gross,
        "net_realized_pnl": net,
        "observed_at": barrier.observed_at,
        "broker_order_id": order.broker_order_id,
        "fill_id": fill.fill_id,
        "reservation_release_ref": release_ref,
        "lot_before_fingerprint_sha256": lot.fingerprint_sha256,
        "lot_after_fingerprint_sha256": updated.fingerprint_sha256,
    }
    return MasterHistoricalVirtualLotExitEvent(
        rank=rank,
        lot_id=lot.lot_id,
        source_system_id=lot.source_system_id,
        proposal_id=lot.proposal_id,
        reservation_id=lot.reservation_id,
        side=lot.side,
        reason=resolution.reason,
        reference_price=reference,
        fill_price=fill.price,
        quantity=fill.quantity,
        exit_fee=fill.fee,
        gross_realized_pnl=gross,
        net_realized_pnl=net,
        observed_at=barrier.observed_at,
        broker_order_id=order.broker_order_id,
        fill_id=fill.fill_id,
        reservation_release_ref=release_ref,
        lot_before_fingerprint_sha256=lot.fingerprint_sha256,
        lot_after_fingerprint_sha256=updated.fingerprint_sha256,
        fingerprint_sha256=stable_digest(event_payload),
    )


def _validate_lifecycle_context(
    *,
    book: MasterHistoricalVirtualLotBook,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    barrier: MasterHistoricalReplayBarrier,
    ledger: MasterReservationLedger,
) -> None:
    if book.plan.fingerprint_sha256 != plan.fingerprint_sha256:
        raise ValueError("historical lifecycle book plan mismatch")
    if book.runtime.identity.plan_fingerprint_sha256 != plan.fingerprint_sha256:
        raise ValueError("historical lifecycle runtime plan mismatch")
    if timeline.plan_fingerprint_sha256 != plan.fingerprint_sha256:
        raise ValueError("historical lifecycle timeline plan mismatch")
    source = _timeline_barrier(timeline=timeline, sequence=barrier.sequence)
    if source.fingerprint_sha256 != barrier.fingerprint_sha256:
        raise ValueError("historical lifecycle barrier is not exact timeline barrier")
    if ledger.policy.master_portfolio_id != plan.master_portfolio_id:
        raise ValueError("historical lifecycle ledger Master Portfolio mismatch")
    expected_sequence = book.last_processed_barrier_sequence + 1
    if barrier.sequence != expected_sequence:
        raise ValueError("historical lifecycle barriers must be processed contiguously")
    for lot in book.open_lots:
        reservation = ledger.get(lot.reservation_id)
        if reservation.status is not ReservationRecordStatus.COMMITTED:
            raise ValueError("OPEN virtual lot lost its COMMITTED reservation")


async def process_master_historical_virtual_lot_barrier(
    *,
    book: MasterHistoricalVirtualLotBook,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    barrier: MasterHistoricalReplayBarrier,
    ledger: MasterReservationLedger,
    candle: object,
) -> MasterHistoricalLifecycleResult:
    row = _canonical_barrier_row(plan=plan, barrier=barrier, candle=candle)
    request_fingerprint = stable_digest(
        {
            "schema": "money-heist.master-historical-virtual-lifecycle-call.v1",
            "barrier_fingerprint_sha256": barrier.fingerprint_sha256,
            "candle_fingerprint_sha256": stable_digest(row),
        }
    )
    previous = book._processed.get(barrier.fingerprint_sha256)
    if previous is not None:
        previous_request, previous_result = previous
        if previous_request != request_fingerprint:
            raise ValueError("historical lifecycle replay conflicts with prior barrier call")
        if book.last_processed_barrier_sequence != barrier.sequence:
            raise ValueError("historical lifecycle cannot replay a stale processed barrier")
        if ledger.snapshot().fingerprint_sha256 != previous_result.ledger_after_fingerprint_sha256:
            raise ValueError("historical lifecycle idempotent replay sees divergent ledger")
        return previous_result

    _validate_lifecycle_context(
        book=book,
        plan=plan,
        timeline=timeline,
        barrier=barrier,
        ledger=ledger,
    )
    runtime = book.runtime
    runtime.set_time(barrier.observed_at)
    phase_mark = _phase_mark(barrier=barrier, row=row)
    changed = await runtime.broker.process_price(
        plan.symbol,
        phase_mark,
        observed_at=barrier.observed_at,
    )
    if tuple(changed):
        raise RuntimeError("historical virtual lifecycle cannot carry pending orders/stops")
    book._last_mark = phase_mark
    await _assert_net_invariant(book=book)
    book_before = book.snapshot(observed_at=barrier.observed_at, mark_price=phase_mark)
    ledger_before = ledger.snapshot()
    account_before = await runtime.account_snapshot(observed_at=barrier.observed_at)
    policy = IntrabarPolicy(plan.intrabar_policy)
    exits: list[MasterHistoricalVirtualLotExitEvent] = []
    eligible: list[tuple[MasterHistoricalVirtualLot, object]] = []
    for lot in book.open_lots:
        resolution = _eligible_resolution(
            lot=lot,
            barrier=barrier,
            row=row,
            policy=policy,
        )
        if resolution is not None:
            eligible.append((lot, resolution))
    eligible.sort(key=lambda pair: _lot_sort_key(pair[0]))
    for rank, (lot, resolution) in enumerate(eligible, start=1):
        exits.append(
            await _execute_virtual_lot_exit(
                book=book,
                ledger=ledger,
                barrier=barrier,
                lot=lot,
                resolution=resolution,
                rank=rank,
            )
        )
        await _assert_net_invariant(book=book)

    runtime.set_time(barrier.observed_at)
    changed = await runtime.broker.process_price(
        plan.symbol,
        phase_mark,
        observed_at=barrier.observed_at,
    )
    if tuple(changed):
        raise RuntimeError("historical virtual lifecycle left pending broker state")
    book._last_mark = phase_mark
    book._last_processed_barrier_sequence = barrier.sequence
    await _assert_net_invariant(book=book)
    book_after = book.snapshot(observed_at=barrier.observed_at, mark_price=phase_mark)
    ledger_after = ledger.snapshot()
    account_after = await runtime.account_snapshot(observed_at=barrier.observed_at)
    status = (
        MasterHistoricalLifecycleStatus.PROCESSED_WITH_EXITS
        if exits
        else MasterHistoricalLifecycleStatus.PROCESSED_NO_EXIT
    )
    result_id = "historical-virtual-lifecycle:" + stable_digest(
        {
            "schema": "money-heist.master-historical-virtual-lifecycle-id.v1",
            "book_id": book.book_id,
            "barrier_fingerprint_sha256": barrier.fingerprint_sha256,
            "exit_fingerprints": [event.fingerprint_sha256 for event in exits],
        }
    )
    payload = {
        "schema": "money-heist.master-historical-virtual-lifecycle-result.v1",
        "schema_version": "1.0",
        "result_id": result_id,
        "book_id": book.book_id,
        "master_portfolio_id": plan.master_portfolio_id,
        "plan_fingerprint_sha256": plan.fingerprint_sha256,
        "timeline_fingerprint_sha256": timeline.fingerprint_sha256,
        "barrier_fingerprint_sha256": barrier.fingerprint_sha256,
        "barrier_sequence": barrier.sequence,
        "candle_index": barrier.candle_index,
        "phase": barrier.phase,
        "observed_at": barrier.observed_at,
        "candle_fingerprint_sha256": stable_digest(row),
        "status": status,
        "book_before_fingerprint_sha256": book_before.fingerprint_sha256,
        "book_after_fingerprint_sha256": book_after.fingerprint_sha256,
        "ledger_before_fingerprint_sha256": ledger_before.fingerprint_sha256,
        "ledger_after_fingerprint_sha256": ledger_after.fingerprint_sha256,
        "account_before_fingerprint_sha256": account_before.fingerprint_sha256,
        "account_after_fingerprint_sha256": account_after.fingerprint_sha256,
        "exit_events": [
            master_historical_virtual_lot_exit_event_payload(event) for event in exits
        ],
        "reservation_release_mutation_applied": bool(exits),
    }
    result = MasterHistoricalLifecycleResult(
        result_id=result_id,
        book_id=book.book_id,
        master_portfolio_id=plan.master_portfolio_id,
        plan_fingerprint_sha256=plan.fingerprint_sha256,
        timeline_fingerprint_sha256=timeline.fingerprint_sha256,
        barrier_fingerprint_sha256=barrier.fingerprint_sha256,
        barrier_sequence=barrier.sequence,
        candle_index=barrier.candle_index,
        phase=barrier.phase,
        observed_at=barrier.observed_at,
        candle_fingerprint_sha256=stable_digest(row),
        status=status,
        book_before_fingerprint_sha256=book_before.fingerprint_sha256,
        book_after_fingerprint_sha256=book_after.fingerprint_sha256,
        ledger_before_fingerprint_sha256=ledger_before.fingerprint_sha256,
        ledger_after_fingerprint_sha256=ledger_after.fingerprint_sha256,
        account_before_fingerprint_sha256=account_before.fingerprint_sha256,
        account_after_fingerprint_sha256=account_after.fingerprint_sha256,
        exit_events=tuple(exits),
        reservation_release_mutation_applied=bool(exits),
        fingerprint_sha256=stable_digest(payload),
    )
    book._processed[barrier.fingerprint_sha256] = (request_fingerprint, result)
    return result


async def build_master_historical_virtual_portfolio_snapshot(
    *,
    book: MasterHistoricalVirtualLotBook,
    allocation_policy: MasterAllocationPolicy,
    observed_at: datetime,
    mark_price: Decimal,
) -> MasterPortfolioSnapshot:
    """Project virtual-lot exposures plus the one physical Master capital snapshot.

    Gross exposure is marked from every open virtual lot, not from the broker's net position.
    This may intentionally exceed committed reservation notional after price moves;
    existing reconciliation then fails closed rather than inventing extra exposure capacity.
    """

    if allocation_policy.master_portfolio_id != book.plan.master_portfolio_id:
        raise ValueError("virtual portfolio allocation Master Portfolio mismatch")
    if allocation_policy.members != tuple(
        sorted(allocation_policy.members, key=lambda member: member.system_id)
    ):
        raise ValueError("virtual portfolio allocation members must be canonical")
    observed = _utc(observed_at, field_name="observed_at")
    mark = _positive_decimal(mark_price, field_name="mark_price")
    book.runtime.set_time(observed)
    changed = await book.runtime.broker.process_price(
        book.plan.symbol,
        mark,
        observed_at=observed,
    )
    if tuple(changed):
        raise RuntimeError("virtual portfolio snapshot cannot trigger pending broker state")
    book._last_mark = mark
    await _assert_net_invariant(book=book)
    account = await book.runtime.account_snapshot(observed_at=observed)
    capital = account.to_master_capital_snapshot()
    lots_by_system: dict[str, list[MasterHistoricalVirtualLot]] = {
        member.system_id: [] for member in allocation_policy.members
    }
    for lot in book.open_lots:
        if lot.source_system_id not in lots_by_system:
            raise ValueError("virtual lot source system is absent from allocation membership")
        lots_by_system[lot.source_system_id].append(lot)
    exposures = []
    for member in allocation_policy.members:
        lots = lots_by_system[member.system_id]
        exposures.append(
            CrewExposureSnapshot(
                system_id=member.system_id,
                observed_at=observed,
                status=SnapshotDataStatus.AVAILABLE,
                source="master-historical-virtual-lot-book",
                open_positions=len(lots),
                gross_exposure_amount=sum(
                    (lot.quantity * mark for lot in lots),
                    ZERO,
                ),
                open_risk_amount=sum(
                    (lot.reserved_open_risk_amount for lot in lots),
                    ZERO,
                ),
                source_ref=book.book_id,
            )
        )
    return build_master_portfolio_snapshot(
        master_capital=capital,
        members=allocation_policy.members,
        crew_exposures=tuple(exposures),
    )


__all__ = [
    "MasterHistoricalLifecycleResult",
    "MasterHistoricalLifecycleStatus",
    "MasterHistoricalVirtualLot",
    "MasterHistoricalVirtualLotBook",
    "MasterHistoricalVirtualLotBookSnapshot",
    "MasterHistoricalVirtualLotExitEvent",
    "MasterHistoricalVirtualLotRegistrationResult",
    "MasterHistoricalVirtualLotRegistrationStatus",
    "MasterHistoricalVirtualLotStatus",
    "build_master_historical_virtual_lot_book",
    "build_master_historical_virtual_portfolio_snapshot",
    "master_historical_lifecycle_result_payload",
    "master_historical_virtual_lot_book_snapshot_payload",
    "master_historical_virtual_lot_exit_event_payload",
    "master_historical_virtual_lot_payload",
    "master_historical_virtual_lot_registration_payload",
    "process_master_historical_virtual_lot_barrier",
    "register_master_historical_virtual_lots",
]
