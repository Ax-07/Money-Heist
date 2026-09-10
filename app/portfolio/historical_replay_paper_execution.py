from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from app.services.backtest.dataset import canonical_candle_rows
from app.services.backtest.ids import ReplayIdFactory, stable_digest
from app.trading.paper import (
    OrderSide,
    OrderStatus,
    OrderType,
    PaperBroker,
    PaperBrokerConfig,
    PaperOrderRequest,
)

from .historical_replay import MasterHistoricalReplayPlan
from .historical_replay_coordinator import (
    MasterHistoricalReplayBarrierPhase,
    MasterHistoricalReplayTimeline,
)
from .historical_replay_preexecution import (
    MasterHistoricalCandidateSeed,
    MasterHistoricalDecisionBarrier,
)
from .historical_replay_reservation_arbitration import (
    MasterHistoricalReservationArbitrationResult,
)
from .models import MasterCapitalSnapshot, SnapshotDataStatus
from .reservation import (
    MasterReservationLedger,
    ReservationLedgerSnapshot,
    ReservationRecordStatus,
)
from .risk_gate import MasterRiskGateCandidate, MasterRiskGateDecisionStatus

ZERO = Decimal("0")
BPS_DENOMINATOR = Decimal("10000")


class MasterHistoricalPaperAttemptStatus(StrEnum):
    EXECUTED = "EXECUTED"
    RELEASED_INSUFFICIENT_MASTER_CASH = "RELEASED_INSUFFICIENT_MASTER_CASH"


class MasterHistoricalPaperReasonCode(StrEnum):
    EXECUTED = "EXECUTED"
    INSUFFICIENT_MASTER_CASH = "INSUFFICIENT_MASTER_CASH"


class MasterHistoricalPaperExecutionStatus(StrEnum):
    NO_ADMITTED_CANDIDATES = "NO_ADMITTED_CANDIDATES"
    EXECUTED = "EXECUTED"
    PARTIAL_EXECUTION = "PARTIAL_EXECUTION"
    NO_EXECUTION = "NO_EXECUTION"


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


def _runtime_identity_payload(
    identity: MasterHistoricalPaperRuntimeIdentity,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-paper-runtime.v1",
        "schema_version": identity.schema_version,
        "runtime_id": identity.runtime_id,
        "plan_id": identity.plan_id,
        "master_portfolio_id": identity.master_portfolio_id,
        "plan_fingerprint_sha256": identity.plan_fingerprint_sha256,
        "execution_model_version": identity.execution_model_version,
        "initial_balance": identity.initial_balance,
        "maker_fee_bps": identity.maker_fee_bps,
        "taker_fee_bps": identity.taker_fee_bps,
        "market_slippage_bps": identity.market_slippage_bps,
        "allow_short": identity.allow_short,
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalPaperRuntimeIdentity:
    runtime_id: str
    plan_id: str
    master_portfolio_id: str
    plan_fingerprint_sha256: str
    execution_model_version: str
    initial_balance: Decimal
    maker_fee_bps: Decimal
    taker_fee_bps: Decimal
    market_slippage_bps: Decimal
    allow_short: bool
    fingerprint_sha256: str
    single_master_account: bool = field(default=True, init=False)
    uses_branch_brokers: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in (
            "runtime_id",
            "plan_id",
            "master_portfolio_id",
            "execution_model_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "plan_fingerprint_sha256",
            _sha256(
                self.plan_fingerprint_sha256,
                field_name="plan_fingerprint_sha256",
            ),
        )
        for field_name in (
            "initial_balance",
            "maker_fee_bps",
            "taker_fee_bps",
            "market_slippage_bps",
        ):
            number = _non_negative_decimal(getattr(self, field_name), field_name=field_name)
            object.__setattr__(self, field_name, number)
        if self.initial_balance <= ZERO:
            raise ValueError("initial_balance must be > 0")
        if not self.allow_short:
            raise ValueError("Master historical PAPER V1 requires signed-position support")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical PAPER runtime schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(_runtime_identity_payload(self))
        if normalized != expected:
            raise ValueError("Master historical PAPER runtime fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)


@dataclass(frozen=True, slots=True)
class MasterHistoricalPaperProposalEvidence:
    system_id: str
    proposal: object

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "system_id",
            _required_text(self.system_id, field_name="system_id"),
        )
        if self.proposal is None:
            raise ValueError("historical PAPER proposal evidence requires proposal")


@dataclass(frozen=True, slots=True)
class MasterHistoricalPaperAccountSnapshot:
    master_portfolio_id: str
    observed_at: datetime
    initial_balance: Decimal
    cash_balance: Decimal
    equity: Decimal
    day_start_equity: Decimal
    equity_peak: Decimal
    daily_pnl: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees_paid: Decimal
    gross_exposure_amount: Decimal
    open_positions: int
    runtime_fingerprint_sha256: str
    fingerprint_sha256: str
    single_master_capital: bool = field(default=True, init=False)
    sums_branch_equities: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "master_portfolio_id",
            _required_text(self.master_portfolio_id, field_name="master_portfolio_id"),
        )
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, field_name="observed_at"),
        )
        for field_name in (
            "initial_balance",
            "cash_balance",
            "equity",
            "day_start_equity",
            "equity_peak",
            "daily_pnl",
            "realized_pnl",
            "unrealized_pnl",
            "fees_paid",
            "gross_exposure_amount",
        ):
            number = _decimal(getattr(self, field_name), field_name=field_name)
            object.__setattr__(self, field_name, number)
        if self.initial_balance <= ZERO:
            raise ValueError("historical PAPER initial_balance must be > 0")
        if self.fees_paid < ZERO or self.gross_exposure_amount < ZERO:
            raise ValueError("fees and gross exposure must be >= 0")
        if self.open_positions < 0:
            raise ValueError("open_positions must be >= 0")
        if self.daily_pnl != self.equity - self.day_start_equity:
            raise ValueError("daily_pnl must equal equity - day_start_equity")
        object.__setattr__(
            self,
            "runtime_fingerprint_sha256",
            _sha256(
                self.runtime_fingerprint_sha256,
                field_name="runtime_fingerprint_sha256",
            ),
        )
        if self.schema_version != "1.0":
            raise ValueError("unsupported historical PAPER account snapshot schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_paper_account_payload(self))
        if normalized != expected:
            raise ValueError("historical PAPER account snapshot fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def to_master_capital_snapshot(self) -> MasterCapitalSnapshot:
        return MasterCapitalSnapshot(
            master_portfolio_id=self.master_portfolio_id,
            observed_at=self.observed_at,
            status=SnapshotDataStatus.AVAILABLE,
            source="master-historical-paper-runtime",
            equity=self.equity,
            cash_balance=self.cash_balance,
            day_start_equity=self.day_start_equity,
            equity_peak=self.equity_peak,
            source_ref=self.fingerprint_sha256,
        )


def master_historical_paper_account_payload(
    snapshot: MasterHistoricalPaperAccountSnapshot,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-paper-account.v1",
        "schema_version": snapshot.schema_version,
        "master_portfolio_id": snapshot.master_portfolio_id,
        "observed_at": snapshot.observed_at,
        "initial_balance": snapshot.initial_balance,
        "cash_balance": snapshot.cash_balance,
        "equity": snapshot.equity,
        "day_start_equity": snapshot.day_start_equity,
        "equity_peak": snapshot.equity_peak,
        "daily_pnl": snapshot.daily_pnl,
        "realized_pnl": snapshot.realized_pnl,
        "unrealized_pnl": snapshot.unrealized_pnl,
        "fees_paid": snapshot.fees_paid,
        "gross_exposure_amount": snapshot.gross_exposure_amount,
        "open_positions": snapshot.open_positions,
        "runtime_fingerprint_sha256": snapshot.runtime_fingerprint_sha256,
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalPaperExecutionAttempt:
    rank: int
    source_system_id: str
    proposal_id: str
    reservation_id: str
    master_decision_id: str
    status: MasterHistoricalPaperAttemptStatus
    reason_code: MasterHistoricalPaperReasonCode
    candidate_fingerprint_sha256: str
    seed_fingerprint_sha256: str
    proposal_fingerprint_sha256: str
    side: str
    symbol: str
    quantity: Decimal
    execution_mark: Decimal
    client_order_id: str
    reservation_before_fingerprint_sha256: str
    reservation_after_fingerprint_sha256: str
    account_before_fingerprint_sha256: str
    account_after_fingerprint_sha256: str
    broker_order_id: str | None
    fill_id: str | None
    fill_price: Decimal | None
    fill_quantity: Decimal | None
    fill_fee: Decimal | None
    filled_at: datetime | None
    fingerprint_sha256: str
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError("historical PAPER attempt rank must be >= 1")
        for field_name in (
            "source_system_id",
            "proposal_id",
            "reservation_id",
            "master_decision_id",
            "side",
            "symbol",
            "client_order_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        if self.side not in {"LONG", "SHORT"}:
            raise ValueError("historical PAPER attempt side must be LONG or SHORT")
        for field_name in (
            "candidate_fingerprint_sha256",
            "seed_fingerprint_sha256",
            "proposal_fingerprint_sha256",
            "reservation_before_fingerprint_sha256",
            "reservation_after_fingerprint_sha256",
            "account_before_fingerprint_sha256",
            "account_after_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "quantity",
            _non_negative_decimal(self.quantity, field_name="quantity"),
        )
        object.__setattr__(
            self,
            "execution_mark",
            _non_negative_decimal(self.execution_mark, field_name="execution_mark"),
        )
        if self.quantity <= ZERO or self.execution_mark <= ZERO:
            raise ValueError("historical PAPER quantity and mark must be > 0")
        self._validate_shape()
        if self.schema_version != "1.0":
            raise ValueError("unsupported historical PAPER attempt schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_paper_attempt_payload(self))
        if normalized != expected:
            raise ValueError("historical PAPER attempt fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def _validate_shape(self) -> None:
        execution_values = (
            self.broker_order_id,
            self.fill_id,
            self.fill_price,
            self.fill_quantity,
            self.fill_fee,
            self.filled_at,
        )
        if self.status is MasterHistoricalPaperAttemptStatus.EXECUTED:
            if self.reason_code is not MasterHistoricalPaperReasonCode.EXECUTED:
                raise ValueError("executed historical PAPER attempt requires EXECUTED reason")
            if any(value is None for value in execution_values):
                raise ValueError("executed historical PAPER attempt requires order and fill")
            assert self.fill_price is not None
            assert self.fill_quantity is not None
            assert self.fill_fee is not None
            assert self.filled_at is not None
            object.__setattr__(
                self,
                "fill_price",
                _non_negative_decimal(self.fill_price, field_name="fill_price"),
            )
            object.__setattr__(
                self,
                "fill_quantity",
                _non_negative_decimal(self.fill_quantity, field_name="fill_quantity"),
            )
            object.__setattr__(
                self,
                "fill_fee",
                _non_negative_decimal(self.fill_fee, field_name="fill_fee"),
            )
            object.__setattr__(
                self,
                "filled_at",
                _utc(self.filled_at, field_name="filled_at"),
            )
            if self.fill_quantity != self.quantity:
                raise ValueError("historical PAPER fill quantity must equal authorized quantity")
            if self.fill_price <= ZERO:
                raise ValueError("historical PAPER fill price must be > 0")
            if (
                self.reservation_after_fingerprint_sha256
                != self.reservation_before_fingerprint_sha256
            ):
                raise ValueError("successful PAPER execution cannot mutate reservation")
            return
        if (
            self.status
            is MasterHistoricalPaperAttemptStatus.RELEASED_INSUFFICIENT_MASTER_CASH
        ):
            if self.reason_code is not MasterHistoricalPaperReasonCode.INSUFFICIENT_MASTER_CASH:
                raise ValueError("cash-blocked PAPER attempt requires insufficient-cash reason")
            if any(value is not None for value in execution_values):
                raise ValueError("cash-blocked PAPER attempt cannot carry order or fill")
            if (
                self.account_after_fingerprint_sha256
                != self.account_before_fingerprint_sha256
            ):
                raise ValueError("cash-blocked PAPER attempt cannot mutate broker account")
            if (
                self.reservation_after_fingerprint_sha256
                == self.reservation_before_fingerprint_sha256
            ):
                raise ValueError("cash-blocked PAPER attempt must release reservation")
            return
        raise ValueError(f"unsupported historical PAPER attempt status: {self.status}")

    @property
    def broker_called(self) -> bool:
        return self.status is MasterHistoricalPaperAttemptStatus.EXECUTED


def master_historical_paper_attempt_payload(
    attempt: MasterHistoricalPaperExecutionAttempt,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-paper-attempt.v1",
        "schema_version": attempt.schema_version,
        "rank": attempt.rank,
        "source_system_id": attempt.source_system_id,
        "proposal_id": attempt.proposal_id,
        "reservation_id": attempt.reservation_id,
        "master_decision_id": attempt.master_decision_id,
        "status": attempt.status,
        "reason_code": attempt.reason_code,
        "candidate_fingerprint_sha256": attempt.candidate_fingerprint_sha256,
        "seed_fingerprint_sha256": attempt.seed_fingerprint_sha256,
        "proposal_fingerprint_sha256": attempt.proposal_fingerprint_sha256,
        "side": attempt.side,
        "symbol": attempt.symbol,
        "quantity": attempt.quantity,
        "execution_mark": attempt.execution_mark,
        "client_order_id": attempt.client_order_id,
        "reservation_before_fingerprint_sha256": (
            attempt.reservation_before_fingerprint_sha256
        ),
        "reservation_after_fingerprint_sha256": (
            attempt.reservation_after_fingerprint_sha256
        ),
        "account_before_fingerprint_sha256": attempt.account_before_fingerprint_sha256,
        "account_after_fingerprint_sha256": attempt.account_after_fingerprint_sha256,
        "broker_order_id": attempt.broker_order_id,
        "fill_id": attempt.fill_id,
        "fill_price": attempt.fill_price,
        "fill_quantity": attempt.fill_quantity,
        "fill_fee": attempt.fill_fee,
        "filled_at": attempt.filled_at,
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalPaperExecutionResult:
    result_id: str
    master_portfolio_id: str
    plan_id: str
    timeline_id: str
    barrier_result_id: str
    reservation_arbitration_result_id: str
    observed_at: datetime
    status: MasterHistoricalPaperExecutionStatus
    plan_fingerprint_sha256: str
    timeline_fingerprint_sha256: str
    decision_barrier_fingerprint_sha256: str
    reservation_arbitration_fingerprint_sha256: str
    runtime_fingerprint_sha256: str
    candle_fingerprint_sha256: str
    initial_ledger_fingerprint_sha256: str
    final_ledger_fingerprint_sha256: str
    account_before: MasterHistoricalPaperAccountSnapshot
    account_after: MasterHistoricalPaperAccountSnapshot
    attempts: tuple[MasterHistoricalPaperExecutionAttempt, ...]
    market_mark_applied: bool
    reservation_release_mutation_applied: bool
    fingerprint_sha256: str
    single_master_capital: bool = field(default=True, init=False)
    sums_branch_equities: bool = field(default=False, init=False)
    uses_branch_brokers: bool = field(default=False, init=False)
    paper_broker_authority: bool = field(default=True, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in (
            "result_id",
            "master_portfolio_id",
            "plan_id",
            "timeline_id",
            "barrier_result_id",
            "reservation_arbitration_result_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, field_name="observed_at"),
        )
        for field_name in (
            "plan_fingerprint_sha256",
            "timeline_fingerprint_sha256",
            "decision_barrier_fingerprint_sha256",
            "reservation_arbitration_fingerprint_sha256",
            "runtime_fingerprint_sha256",
            "candle_fingerprint_sha256",
            "initial_ledger_fingerprint_sha256",
            "final_ledger_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        if not self.market_mark_applied:
            raise ValueError("historical PAPER result requires exact CLOSE mark application")
        if self.account_before.observed_at != self.observed_at:
            raise ValueError("historical PAPER account_before time mismatch")
        if self.account_after.observed_at != self.observed_at:
            raise ValueError("historical PAPER account_after time mismatch")
        expected_ranks = tuple(range(1, len(self.attempts) + 1))
        if tuple(item.rank for item in self.attempts) != expected_ranks:
            raise ValueError("historical PAPER attempt ranks must be contiguous")
        executed = self.executed_count
        blocked = self.released_count
        if self.status is MasterHistoricalPaperExecutionStatus.NO_ADMITTED_CANDIDATES:
            if self.attempts or self.reservation_release_mutation_applied:
                raise ValueError("NO_ADMITTED_CANDIDATES cannot carry attempts/releases")
        elif self.status is MasterHistoricalPaperExecutionStatus.EXECUTED:
            if not self.attempts or executed != len(self.attempts) or blocked:
                raise ValueError("EXECUTED requires every admitted candidate to execute")
            if self.reservation_release_mutation_applied:
                raise ValueError("EXECUTED cannot report reservation release")
        elif self.status is MasterHistoricalPaperExecutionStatus.PARTIAL_EXECUTION:
            if executed < 1 or blocked < 1:
                raise ValueError("PARTIAL_EXECUTION requires execution and release")
            if not self.reservation_release_mutation_applied:
                raise ValueError("PARTIAL_EXECUTION must report reservation release")
        elif self.status is MasterHistoricalPaperExecutionStatus.NO_EXECUTION:
            if not self.attempts or executed or blocked != len(self.attempts):
                raise ValueError("NO_EXECUTION requires every admitted candidate blocked")
            if not self.reservation_release_mutation_applied:
                raise ValueError("NO_EXECUTION must report reservation release")
        else:
            raise ValueError(f"unsupported historical PAPER result status: {self.status}")
        if self.schema_version != "1.0":
            raise ValueError("unsupported historical PAPER result schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_paper_execution_payload(self))
        if normalized != expected:
            raise ValueError("historical PAPER execution result fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    @property
    def executed_count(self) -> int:
        return sum(
            item.status is MasterHistoricalPaperAttemptStatus.EXECUTED
            for item in self.attempts
        )

    @property
    def released_count(self) -> int:
        return sum(
            item.status
            is MasterHistoricalPaperAttemptStatus.RELEASED_INSUFFICIENT_MASTER_CASH
            for item in self.attempts
        )

    @property
    def broker_order_count(self) -> int:
        return self.executed_count


def master_historical_paper_execution_payload(
    result: MasterHistoricalPaperExecutionResult,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-paper-execution.v1",
        "schema_version": result.schema_version,
        "result_id": result.result_id,
        "master_portfolio_id": result.master_portfolio_id,
        "plan_id": result.plan_id,
        "timeline_id": result.timeline_id,
        "barrier_result_id": result.barrier_result_id,
        "reservation_arbitration_result_id": result.reservation_arbitration_result_id,
        "observed_at": result.observed_at,
        "status": result.status,
        "plan_fingerprint_sha256": result.plan_fingerprint_sha256,
        "timeline_fingerprint_sha256": result.timeline_fingerprint_sha256,
        "decision_barrier_fingerprint_sha256": (
            result.decision_barrier_fingerprint_sha256
        ),
        "reservation_arbitration_fingerprint_sha256": (
            result.reservation_arbitration_fingerprint_sha256
        ),
        "runtime_fingerprint_sha256": result.runtime_fingerprint_sha256,
        "candle_fingerprint_sha256": result.candle_fingerprint_sha256,
        "initial_ledger_fingerprint_sha256": result.initial_ledger_fingerprint_sha256,
        "final_ledger_fingerprint_sha256": result.final_ledger_fingerprint_sha256,
        "account_before_fingerprint_sha256": result.account_before.fingerprint_sha256,
        "account_after_fingerprint_sha256": result.account_after.fingerprint_sha256,
        "attempts": [master_historical_paper_attempt_payload(item) for item in result.attempts],
        "market_mark_applied": result.market_mark_applied,
        "reservation_release_mutation_applied": (
            result.reservation_release_mutation_applied
        ),
    }


class _HistoricalClock:
    def __init__(self, value: datetime) -> None:
        self._value = _utc(value, field_name="historical clock")

    def set(self, value: datetime) -> None:
        self._value = _utc(value, field_name="historical clock")

    def __call__(self) -> datetime:
        return self._value


class MasterHistoricalPaperRuntime:
    """Own one deterministic existing PaperBroker for the physical Master account."""

    def __init__(self, *, plan: MasterHistoricalReplayPlan) -> None:
        self._plan = plan
        self._clock = _HistoricalClock(plan.period_start)
        config = PaperBrokerConfig(
            system_id=plan.master_portfolio_id,
            initial_balance=plan.master_initial_capital,
            maker_fee_bps=plan.maker_fee_bps,
            taker_fee_bps=plan.taker_fee_bps,
            market_slippage_bps=plan.market_slippage_bps,
            allow_short=True,
        )
        id_factory = ReplayIdFactory(
            plan.plan_id,
            namespace="master-historical-paper",
        )
        self.broker = PaperBroker(config, id_factory=id_factory, clock=self._clock)
        identity_body = {
            "plan_id": plan.plan_id,
            "master_portfolio_id": plan.master_portfolio_id,
            "plan_fingerprint_sha256": plan.fingerprint_sha256,
            "execution_model_version": plan.execution_model_version,
            "initial_balance": plan.master_initial_capital,
            "maker_fee_bps": plan.maker_fee_bps,
            "taker_fee_bps": plan.taker_fee_bps,
            "market_slippage_bps": plan.market_slippage_bps,
            "allow_short": True,
        }
        runtime_id = "master-historical-paper:" + stable_digest(
            {
                "schema": "money-heist.master-historical-paper-runtime-id.v1",
                **identity_body,
            }
        )
        identity_payload = {
            "schema": "money-heist.master-historical-paper-runtime.v1",
            "schema_version": "1.0",
            "runtime_id": runtime_id,
            **identity_body,
        }
        self.identity = MasterHistoricalPaperRuntimeIdentity(
            runtime_id=runtime_id,
            plan_id=plan.plan_id,
            master_portfolio_id=plan.master_portfolio_id,
            plan_fingerprint_sha256=plan.fingerprint_sha256,
            execution_model_version=plan.execution_model_version,
            initial_balance=plan.master_initial_capital,
            maker_fee_bps=plan.maker_fee_bps,
            taker_fee_bps=plan.taker_fee_bps,
            market_slippage_bps=plan.market_slippage_bps,
            allow_short=True,
            fingerprint_sha256=stable_digest(identity_payload),
        )
        self._current_day = None
        self._day_start_equity = plan.master_initial_capital
        self._equity_peak = plan.master_initial_capital
        self._last_equity = plan.master_initial_capital
        self._completed: dict[str, tuple[str, MasterHistoricalPaperExecutionResult]] = {}
        self.risk_authority = False
        self.admission_authority = False
        self.live_authority = False
        self.paper_broker_authority = True

    def set_time(self, observed_at: datetime) -> None:
        self._clock.set(observed_at)

    async def account_snapshot(
        self,
        *,
        observed_at: datetime,
    ) -> MasterHistoricalPaperAccountSnapshot:
        observed_at = _utc(observed_at, field_name="observed_at")
        account = await self.broker.get_account_state()
        if account.system_id != self.identity.master_portfolio_id:
            raise ValueError("PAPER broker account is not the Master account")
        initial_balance = _decimal(account.initial_balance, field_name="initial_balance")
        if initial_balance != self.identity.initial_balance:
            raise ValueError("PAPER broker initial balance changed from Master initial capital")
        equity = _decimal(account.equity, field_name="equity")
        observed_day = observed_at.date()
        if self._current_day is None:
            self._current_day = observed_day
        elif observed_day != self._current_day:
            self._day_start_equity = self._last_equity
            self._current_day = observed_day
        self._equity_peak = max(self._equity_peak, equity)
        self._last_equity = equity
        payload = {
            "schema": "money-heist.master-historical-paper-account.v1",
            "schema_version": "1.0",
            "master_portfolio_id": self.identity.master_portfolio_id,
            "observed_at": observed_at,
            "initial_balance": initial_balance,
            "cash_balance": _decimal(account.cash_balance, field_name="cash_balance"),
            "equity": equity,
            "day_start_equity": self._day_start_equity,
            "equity_peak": self._equity_peak,
            "daily_pnl": equity - self._day_start_equity,
            "realized_pnl": _decimal(account.realized_pnl, field_name="realized_pnl"),
            "unrealized_pnl": _decimal(account.unrealized_pnl, field_name="unrealized_pnl"),
            "fees_paid": _non_negative_decimal(account.fees_paid, field_name="fees_paid"),
            "gross_exposure_amount": _non_negative_decimal(
                account.gross_exposure,
                field_name="gross_exposure",
            ),
            "open_positions": int(account.open_positions),
            "runtime_fingerprint_sha256": self.identity.fingerprint_sha256,
        }
        return MasterHistoricalPaperAccountSnapshot(
            master_portfolio_id=self.identity.master_portfolio_id,
            observed_at=observed_at,
            initial_balance=initial_balance,
            cash_balance=payload["cash_balance"],
            equity=equity,
            day_start_equity=self._day_start_equity,
            equity_peak=self._equity_peak,
            daily_pnl=equity - self._day_start_equity,
            realized_pnl=payload["realized_pnl"],
            unrealized_pnl=payload["unrealized_pnl"],
            fees_paid=payload["fees_paid"],
            gross_exposure_amount=payload["gross_exposure_amount"],
            open_positions=int(account.open_positions),
            runtime_fingerprint_sha256=self.identity.fingerprint_sha256,
            fingerprint_sha256=stable_digest(payload),
        )


def build_master_historical_paper_runtime(
    *,
    plan: MasterHistoricalReplayPlan,
) -> MasterHistoricalPaperRuntime:
    return MasterHistoricalPaperRuntime(plan=plan)


def _validate_runtime(
    *,
    runtime: MasterHistoricalPaperRuntime,
    plan: MasterHistoricalReplayPlan,
) -> None:
    identity = runtime.identity
    if identity.plan_id != plan.plan_id:
        raise ValueError("historical PAPER runtime plan_id mismatch")
    if identity.plan_fingerprint_sha256 != plan.fingerprint_sha256:
        raise ValueError("historical PAPER runtime plan fingerprint mismatch")
    if identity.master_portfolio_id != plan.master_portfolio_id:
        raise ValueError("historical PAPER runtime Master Portfolio mismatch")
    config = runtime.broker.config
    actual = (
        config.system_id,
        config.initial_balance,
        config.maker_fee_bps,
        config.taker_fee_bps,
        config.market_slippage_bps,
        config.allow_short,
    )
    expected = (
        plan.master_portfolio_id,
        plan.master_initial_capital,
        plan.maker_fee_bps,
        plan.taker_fee_bps,
        plan.market_slippage_bps,
        True,
    )
    if actual != expected:
        raise ValueError("historical PAPER broker config diverged from replay plan")


def _validate_context(
    *,
    runtime: MasterHistoricalPaperRuntime,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    decision_barrier: MasterHistoricalDecisionBarrier,
    reservation_arbitration: MasterHistoricalReservationArbitrationResult,
    ledger: MasterReservationLedger,
) -> ReservationLedgerSnapshot:
    _validate_runtime(runtime=runtime, plan=plan)
    if timeline.plan_id != plan.plan_id:
        raise ValueError("historical PAPER timeline does not bind replay plan")
    if timeline.plan_fingerprint_sha256 != plan.fingerprint_sha256:
        raise ValueError("historical PAPER timeline plan fingerprint mismatch")
    if decision_barrier.plan_id != plan.plan_id:
        raise ValueError("historical PAPER decision barrier plan mismatch")
    if decision_barrier.timeline_id != timeline.timeline_id:
        raise ValueError("historical PAPER decision barrier timeline mismatch")
    if decision_barrier.plan_fingerprint_sha256 != plan.fingerprint_sha256:
        raise ValueError("historical PAPER decision barrier plan fingerprint mismatch")
    if decision_barrier.timeline_fingerprint_sha256 != timeline.fingerprint_sha256:
        raise ValueError("historical PAPER decision barrier timeline fingerprint mismatch")
    if reservation_arbitration.plan_id != plan.plan_id:
        raise ValueError("historical PAPER reservation result plan mismatch")
    if reservation_arbitration.timeline_id != timeline.timeline_id:
        raise ValueError("historical PAPER reservation result timeline mismatch")
    if (
        reservation_arbitration.decision_barrier_fingerprint_sha256
        != decision_barrier.fingerprint_sha256
    ):
        raise ValueError("historical PAPER reservation result decision barrier mismatch")
    if reservation_arbitration.observed_at != decision_barrier.observed_at:
        raise ValueError("historical PAPER reservation result time mismatch")
    if reservation_arbitration.master_portfolio_id != plan.master_portfolio_id:
        raise ValueError("historical PAPER reservation result Master Portfolio mismatch")
    if ledger.policy.master_portfolio_id != plan.master_portfolio_id:
        raise ValueError("historical PAPER ledger Master Portfolio mismatch")
    ledger_snapshot = ledger.snapshot()
    if (
        ledger_snapshot.fingerprint_sha256
        != reservation_arbitration.final_ledger_fingerprint_sha256
    ):
        raise ValueError("historical PAPER ledger is stale relative to reservation arbitration")
    return ledger_snapshot


def _canonical_close_row(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    decision_barrier: MasterHistoricalDecisionBarrier,
    candle: object,
) -> tuple[dict[str, object], Decimal]:
    source_barrier = timeline.barriers[decision_barrier.barrier_sequence - 1]
    if source_barrier.phase is not MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE:
        raise ValueError("historical PAPER execution requires CANDLE_CLOSE barrier")
    rows = canonical_candle_rows(
        (candle,),
        expected_symbol=plan.symbol,
        expected_timeframe=plan.timeframe,
    )
    row = rows[0]
    if stable_digest(row) != source_barrier.candle_fingerprint_sha256:
        raise ValueError("historical PAPER candle does not match timeline fingerprint")
    open_at = datetime.fromisoformat(str(row["open_time"]).replace("Z", "+00:00"))
    close_at = datetime.fromisoformat(str(row["close_time"]).replace("Z", "+00:00"))
    if _utc(open_at, field_name="candle open") != source_barrier.candle_open_at:
        raise ValueError("historical PAPER candle open time mismatch")
    if _utc(close_at, field_name="candle close") != decision_barrier.observed_at:
        raise ValueError("historical PAPER candle close time mismatch")
    mark = _decimal(row["close"], field_name="candle close")
    if mark <= ZERO:
        raise ValueError("historical PAPER close mark must be > 0")
    return row, mark


def _admitted_materials(
    *,
    decision_barrier: MasterHistoricalDecisionBarrier,
    reservation_arbitration: MasterHistoricalReservationArbitrationResult,
    proposal_evidence: tuple[MasterHistoricalPaperProposalEvidence, ...],
    plan: MasterHistoricalReplayPlan,
) -> tuple[tuple[object, MasterRiskGateCandidate, MasterHistoricalCandidateSeed, object, str], ...]:
    arbitration = reservation_arbitration.arbitration_result
    admitted = () if arbitration is None else tuple(
        item
        for item in arbitration.outcomes
        if item.decision_status is MasterRiskGateDecisionStatus.ADMIT
    )
    evidence_map: dict[tuple[str, str], MasterHistoricalPaperProposalEvidence] = {}
    for evidence in proposal_evidence:
        proposal_id = _required_text(
            getattr(evidence.proposal, "proposal_id", ""),
            field_name="proposal.proposal_id",
        )
        key = (evidence.system_id, proposal_id)
        if key in evidence_map:
            raise ValueError("historical PAPER proposal evidence cannot duplicate proposal")
        evidence_map[key] = evidence
    admitted_keys = {(item.system_id, item.proposal_id) for item in admitted}
    if set(evidence_map) != admitted_keys:
        raise ValueError(
            "historical PAPER proposal evidence must match admitted candidates exactly"
        )

    candidate_map = {
        candidate.fingerprint_sha256: candidate
        for candidate in reservation_arbitration.candidates
    }
    attempt_map = {
        (attempt.system_id, attempt.proposal_id): attempt
        for attempt in reservation_arbitration.attempts
    }
    seed_map = {
        (seed.system_id, seed.proposal_id): seed
        for seed in decision_barrier.candidate_seeds
    }
    materials = []
    for outcome in admitted:
        candidate = candidate_map.get(outcome.candidate_fingerprint_sha256)
        if candidate is None:
            raise ValueError("admitted historical PAPER candidate is missing")
        key = (outcome.system_id, outcome.proposal_id)
        attempt = attempt_map.get(key)
        seed = seed_map.get(key)
        evidence = evidence_map.get(key)
        if attempt is None or seed is None or evidence is None:
            raise ValueError("historical PAPER admitted provenance is incomplete")
        if attempt.candidate != candidate:
            raise ValueError("historical PAPER attempt candidate mismatch")
        if attempt.seed_fingerprint_sha256 != seed.fingerprint_sha256:
            raise ValueError("historical PAPER seed fingerprint mismatch")
        if candidate.local_risk_decision_fingerprint_sha256 != (
            seed.local_risk_decision_fingerprint_sha256
        ):
            raise ValueError("historical PAPER local Risk provenance mismatch")
        proposal = evidence.proposal
        proposal_fingerprint = _object_fingerprint(proposal, field_name="proposal")
        if proposal_fingerprint != seed.proposal_fingerprint_sha256:
            raise ValueError("historical PAPER proposal fingerprint mismatch")
        _validate_proposal(
            proposal=proposal,
            evidence=evidence,
            seed=seed,
            candidate=candidate,
            plan=plan,
        )
        materials.append((outcome, candidate, seed, proposal, proposal_fingerprint))
    return tuple(materials)


def _validate_proposal(
    *,
    proposal: object,
    evidence: MasterHistoricalPaperProposalEvidence,
    seed: MasterHistoricalCandidateSeed,
    candidate: MasterRiskGateCandidate,
    plan: MasterHistoricalReplayPlan,
) -> None:
    side = _enum_text(getattr(proposal, "side", ""), field_name="proposal.side")
    if side not in {"LONG", "SHORT"}:
        raise ValueError("historical PAPER proposal side must be LONG or SHORT")
    checks = (
        (str(getattr(proposal, "system_id", "")) == evidence.system_id, "system_id"),
        (str(getattr(proposal, "system_id", "")) == seed.system_id, "seed system_id"),
        (str(getattr(proposal, "proposal_id", "")) == seed.proposal_id, "proposal_id"),
        (str(getattr(proposal, "proposal_id", "")) == candidate.proposal_id, "candidate id"),
        (str(getattr(proposal, "opportunity_id", "")) == seed.opportunity_id, "opportunity_id"),
        (
            str(getattr(proposal, "source_snapshot_id", "")) == seed.source_snapshot_id,
            "source_snapshot_id",
        ),
        (str(getattr(proposal, "symbol", "")) == plan.symbol, "symbol"),
        (str(getattr(proposal, "timeframe", "")) == plan.timeframe, "timeframe"),
    )
    for valid, label in checks:
        if not valid:
            raise ValueError(f"historical PAPER proposal {label} mismatch")


def _client_order_id(
    *,
    plan: MasterHistoricalReplayPlan,
    reservation_arbitration: MasterHistoricalReservationArbitrationResult,
    candidate: MasterRiskGateCandidate,
) -> str:
    digest = stable_digest(
        {
            "schema": "money-heist.master-historical-paper-order-id.v1",
            "plan_fingerprint_sha256": plan.fingerprint_sha256,
            "reservation_arbitration_fingerprint_sha256": (
                reservation_arbitration.fingerprint_sha256
            ),
            "candidate_fingerprint_sha256": candidate.fingerprint_sha256,
            "reservation_id": candidate.reservation_id,
        }
    )
    return f"master-historical:{digest}"


def _expected_buy_debit(
    *,
    mark: Decimal,
    quantity: Decimal,
    slippage_bps: Decimal,
    taker_fee_bps: Decimal,
) -> Decimal:
    fill_price = mark * (Decimal("1") + slippage_bps / BPS_DENOMINATOR)
    notional = fill_price * quantity
    fee = notional * taker_fee_bps / BPS_DENOMINATOR
    return notional + fee


def _build_attempt(
    *,
    rank: int,
    source_system_id: str,
    proposal_id: str,
    reservation_id: str,
    master_decision_id: str,
    status: MasterHistoricalPaperAttemptStatus,
    reason_code: MasterHistoricalPaperReasonCode,
    candidate: MasterRiskGateCandidate,
    seed: MasterHistoricalCandidateSeed,
    proposal_fingerprint: str,
    side: str,
    symbol: str,
    quantity: Decimal,
    execution_mark: Decimal,
    client_order_id: str,
    reservation_before_fingerprint: str,
    reservation_after_fingerprint: str,
    account_before: MasterHistoricalPaperAccountSnapshot,
    account_after: MasterHistoricalPaperAccountSnapshot,
    order: object | None = None,
    fill: object | None = None,
) -> MasterHistoricalPaperExecutionAttempt:
    payload = {
        "schema": "money-heist.master-historical-paper-attempt.v1",
        "schema_version": "1.0",
        "rank": rank,
        "source_system_id": source_system_id,
        "proposal_id": proposal_id,
        "reservation_id": reservation_id,
        "master_decision_id": master_decision_id,
        "status": status,
        "reason_code": reason_code,
        "candidate_fingerprint_sha256": candidate.fingerprint_sha256,
        "seed_fingerprint_sha256": seed.fingerprint_sha256,
        "proposal_fingerprint_sha256": proposal_fingerprint,
        "side": side,
        "symbol": symbol,
        "quantity": quantity,
        "execution_mark": execution_mark,
        "client_order_id": client_order_id,
        "reservation_before_fingerprint_sha256": reservation_before_fingerprint,
        "reservation_after_fingerprint_sha256": reservation_after_fingerprint,
        "account_before_fingerprint_sha256": account_before.fingerprint_sha256,
        "account_after_fingerprint_sha256": account_after.fingerprint_sha256,
        "broker_order_id": getattr(order, "broker_order_id", None),
        "fill_id": getattr(fill, "fill_id", None),
        "fill_price": getattr(fill, "price", None),
        "fill_quantity": getattr(fill, "quantity", None),
        "fill_fee": getattr(fill, "fee", None),
        "filled_at": getattr(fill, "filled_at", None),
    }
    return MasterHistoricalPaperExecutionAttempt(
        rank=rank,
        source_system_id=source_system_id,
        proposal_id=proposal_id,
        reservation_id=reservation_id,
        master_decision_id=master_decision_id,
        status=status,
        reason_code=reason_code,
        candidate_fingerprint_sha256=candidate.fingerprint_sha256,
        seed_fingerprint_sha256=seed.fingerprint_sha256,
        proposal_fingerprint_sha256=proposal_fingerprint,
        side=side,
        symbol=symbol,
        quantity=quantity,
        execution_mark=execution_mark,
        client_order_id=client_order_id,
        reservation_before_fingerprint_sha256=reservation_before_fingerprint,
        reservation_after_fingerprint_sha256=reservation_after_fingerprint,
        account_before_fingerprint_sha256=account_before.fingerprint_sha256,
        account_after_fingerprint_sha256=account_after.fingerprint_sha256,
        broker_order_id=payload["broker_order_id"],
        fill_id=payload["fill_id"],
        fill_price=payload["fill_price"],
        fill_quantity=payload["fill_quantity"],
        fill_fee=payload["fill_fee"],
        filled_at=payload["filled_at"],
        fingerprint_sha256=stable_digest(payload),
    )


async def execute_master_historical_paper_admissions(
    *,
    runtime: MasterHistoricalPaperRuntime,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    decision_barrier: MasterHistoricalDecisionBarrier,
    reservation_arbitration: MasterHistoricalReservationArbitrationResult,
    ledger: MasterReservationLedger,
    candle: object,
    proposal_evidence: tuple[MasterHistoricalPaperProposalEvidence, ...],
) -> MasterHistoricalPaperExecutionResult:
    """Execute only Master-admitted historical entries on one physical PAPER account."""

    initial_ledger = _validate_context(
        runtime=runtime,
        plan=plan,
        timeline=timeline,
        decision_barrier=decision_barrier,
        reservation_arbitration=reservation_arbitration,
        ledger=ledger,
    )
    row, execution_mark = _canonical_close_row(
        plan=plan,
        timeline=timeline,
        decision_barrier=decision_barrier,
        candle=candle,
    )
    materials = _admitted_materials(
        decision_barrier=decision_barrier,
        reservation_arbitration=reservation_arbitration,
        proposal_evidence=proposal_evidence,
        plan=plan,
    )
    request_fingerprint = stable_digest(
        {
            "schema": "money-heist.master-historical-paper-call.v1",
            "reservation_arbitration_fingerprint_sha256": (
                reservation_arbitration.fingerprint_sha256
            ),
            "candle_fingerprint_sha256": stable_digest(row),
            "proposal_fingerprints": [item[4] for item in materials],
        }
    )
    previous = runtime._completed.get(reservation_arbitration.fingerprint_sha256)
    if previous is not None:
        previous_request, previous_result = previous
        if previous_request != request_fingerprint:
            raise ValueError("historical PAPER execution replay conflicts with prior call")
        if ledger.snapshot().fingerprint_sha256 != previous_result.final_ledger_fingerprint_sha256:
            raise ValueError("historical PAPER idempotent replay sees divergent ledger")
        return previous_result

    runtime.set_time(decision_barrier.observed_at)
    changed = await runtime.broker.process_price(
        plan.symbol,
        execution_mark,
        observed_at=decision_barrier.observed_at,
    )
    if tuple(changed):
        raise ValueError("historical PAPER runtime cannot carry pending orders or stop triggers")
    account_before = await runtime.account_snapshot(observed_at=decision_barrier.observed_at)
    attempts: list[MasterHistoricalPaperExecutionAttempt] = []

    for rank, material in enumerate(materials, start=1):
        outcome, candidate, seed, proposal, proposal_fingerprint = material
        assert candidate.reservation_id is not None
        reservation_before = ledger.get(candidate.reservation_id)
        if reservation_before.status is not ReservationRecordStatus.COMMITTED:
            raise ValueError("Master-admitted reservation must be COMMITTED before PAPER execution")
        if reservation_before.commit_ref != outcome.decision_id:
            raise ValueError("PAPER execution reservation commit does not bind Master decision")
        side = _enum_text(getattr(proposal, "side", ""), field_name="proposal.side")
        quantity = candidate.local_approved_quantity
        account_attempt_before = await runtime.account_snapshot(
            observed_at=decision_barrier.observed_at
        )
        client_order_id = _client_order_id(
            plan=plan,
            reservation_arbitration=reservation_arbitration,
            candidate=candidate,
        )

        if side == "LONG":
            required_cash = _expected_buy_debit(
                mark=execution_mark,
                quantity=quantity,
                slippage_bps=plan.market_slippage_bps,
                taker_fee_bps=plan.taker_fee_bps,
            )
            if account_attempt_before.cash_balance < required_cash:
                release_ref = "historical-paper-cash-release:" + stable_digest(
                    {
                        "schema": "money-heist.master-historical-paper-release.v1",
                        "candidate_fingerprint_sha256": candidate.fingerprint_sha256,
                        "account_fingerprint_sha256": account_attempt_before.fingerprint_sha256,
                        "reason": MasterHistoricalPaperReasonCode.INSUFFICIENT_MASTER_CASH,
                    }
                )
                reservation_after = ledger.release(
                    candidate.reservation_id,
                    released_at=decision_barrier.observed_at,
                    release_ref=release_ref,
                )
                account_attempt_after = await runtime.account_snapshot(
                    observed_at=decision_barrier.observed_at
                )
                attempts.append(
                    _build_attempt(
                        rank=rank,
                        source_system_id=outcome.system_id,
                        proposal_id=outcome.proposal_id,
                        reservation_id=candidate.reservation_id,
                        master_decision_id=outcome.decision_id,
                        status=(
                            MasterHistoricalPaperAttemptStatus.RELEASED_INSUFFICIENT_MASTER_CASH
                        ),
                        reason_code=MasterHistoricalPaperReasonCode.INSUFFICIENT_MASTER_CASH,
                        candidate=candidate,
                        seed=seed,
                        proposal_fingerprint=proposal_fingerprint,
                        side=side,
                        symbol=plan.symbol,
                        quantity=quantity,
                        execution_mark=execution_mark,
                        client_order_id=client_order_id,
                        reservation_before_fingerprint=(
                            reservation_before.fingerprint_sha256
                        ),
                        reservation_after_fingerprint=(
                            reservation_after.fingerprint_sha256
                        ),
                        account_before=account_attempt_before,
                        account_after=account_attempt_after,
                    )
                )
                continue

        request = PaperOrderRequest(
            system_id=plan.master_portfolio_id,
            symbol=plan.symbol,
            side=OrderSide.BUY if side == "LONG" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=quantity,
            client_order_id=client_order_id,
        )
        order = await runtime.broker.submit_order(
            request,
            trigger="MASTER_HISTORICAL_ADMISSION",
        )
        if order.status is not OrderStatus.FILLED:
            raise RuntimeError("Master historical PAPER market order did not fill atomically")
        fills = await runtime.broker.get_fills()
        matches = [fill for fill in fills if fill.broker_order_id == order.broker_order_id]
        if len(matches) != 1:
            raise RuntimeError("Master historical PAPER order must have exactly one fill")
        fill = matches[0]
        if order.system_id != plan.master_portfolio_id:
            raise RuntimeError("Master historical PAPER order escaped Master account")
        if fill.filled_at != decision_barrier.observed_at:
            raise RuntimeError("Master historical PAPER fill timestamp is not barrier time")
        if fill.quantity != quantity:
            raise RuntimeError("Master historical PAPER fill changed Risk-authorized quantity")
        reservation_after = ledger.get(candidate.reservation_id)
        if reservation_after.fingerprint_sha256 != reservation_before.fingerprint_sha256:
            raise RuntimeError("successful PAPER execution mutated committed reservation")
        account_attempt_after = await runtime.account_snapshot(
            observed_at=decision_barrier.observed_at
        )
        attempts.append(
            _build_attempt(
                rank=rank,
                source_system_id=outcome.system_id,
                proposal_id=outcome.proposal_id,
                reservation_id=candidate.reservation_id,
                master_decision_id=outcome.decision_id,
                status=MasterHistoricalPaperAttemptStatus.EXECUTED,
                reason_code=MasterHistoricalPaperReasonCode.EXECUTED,
                candidate=candidate,
                seed=seed,
                proposal_fingerprint=proposal_fingerprint,
                side=side,
                symbol=plan.symbol,
                quantity=quantity,
                execution_mark=execution_mark,
                client_order_id=client_order_id,
                reservation_before_fingerprint=reservation_before.fingerprint_sha256,
                reservation_after_fingerprint=reservation_after.fingerprint_sha256,
                account_before=account_attempt_before,
                account_after=account_attempt_after,
                order=order,
                fill=fill,
            )
        )

    account_after = await runtime.account_snapshot(observed_at=decision_barrier.observed_at)
    final_ledger = ledger.snapshot()
    executed_count = sum(
        item.status is MasterHistoricalPaperAttemptStatus.EXECUTED for item in attempts
    )
    released_count = len(attempts) - executed_count
    if not attempts:
        status = MasterHistoricalPaperExecutionStatus.NO_ADMITTED_CANDIDATES
    elif executed_count == len(attempts):
        status = MasterHistoricalPaperExecutionStatus.EXECUTED
    elif executed_count == 0:
        status = MasterHistoricalPaperExecutionStatus.NO_EXECUTION
    else:
        status = MasterHistoricalPaperExecutionStatus.PARTIAL_EXECUTION
    release_mutation = released_count > 0
    result_id = "historical-paper-execution:" + stable_digest(
        {
            "schema": "money-heist.master-historical-paper-execution-id.v1",
            "reservation_arbitration_fingerprint_sha256": (
                reservation_arbitration.fingerprint_sha256
            ),
            "runtime_fingerprint_sha256": runtime.identity.fingerprint_sha256,
            "candle_fingerprint_sha256": stable_digest(row),
            "attempt_fingerprints": [item.fingerprint_sha256 for item in attempts],
        }
    )
    payload = {
        "schema": "money-heist.master-historical-paper-execution.v1",
        "schema_version": "1.0",
        "result_id": result_id,
        "master_portfolio_id": plan.master_portfolio_id,
        "plan_id": plan.plan_id,
        "timeline_id": timeline.timeline_id,
        "barrier_result_id": decision_barrier.barrier_result_id,
        "reservation_arbitration_result_id": reservation_arbitration.result_id,
        "observed_at": decision_barrier.observed_at,
        "status": status,
        "plan_fingerprint_sha256": plan.fingerprint_sha256,
        "timeline_fingerprint_sha256": timeline.fingerprint_sha256,
        "decision_barrier_fingerprint_sha256": decision_barrier.fingerprint_sha256,
        "reservation_arbitration_fingerprint_sha256": (
            reservation_arbitration.fingerprint_sha256
        ),
        "runtime_fingerprint_sha256": runtime.identity.fingerprint_sha256,
        "candle_fingerprint_sha256": stable_digest(row),
        "initial_ledger_fingerprint_sha256": initial_ledger.fingerprint_sha256,
        "final_ledger_fingerprint_sha256": final_ledger.fingerprint_sha256,
        "account_before_fingerprint_sha256": account_before.fingerprint_sha256,
        "account_after_fingerprint_sha256": account_after.fingerprint_sha256,
        "attempts": [master_historical_paper_attempt_payload(item) for item in attempts],
        "market_mark_applied": True,
        "reservation_release_mutation_applied": release_mutation,
    }
    result = MasterHistoricalPaperExecutionResult(
        result_id=result_id,
        master_portfolio_id=plan.master_portfolio_id,
        plan_id=plan.plan_id,
        timeline_id=timeline.timeline_id,
        barrier_result_id=decision_barrier.barrier_result_id,
        reservation_arbitration_result_id=reservation_arbitration.result_id,
        observed_at=decision_barrier.observed_at,
        status=status,
        plan_fingerprint_sha256=plan.fingerprint_sha256,
        timeline_fingerprint_sha256=timeline.fingerprint_sha256,
        decision_barrier_fingerprint_sha256=decision_barrier.fingerprint_sha256,
        reservation_arbitration_fingerprint_sha256=reservation_arbitration.fingerprint_sha256,
        runtime_fingerprint_sha256=runtime.identity.fingerprint_sha256,
        candle_fingerprint_sha256=stable_digest(row),
        initial_ledger_fingerprint_sha256=initial_ledger.fingerprint_sha256,
        final_ledger_fingerprint_sha256=final_ledger.fingerprint_sha256,
        account_before=account_before,
        account_after=account_after,
        attempts=tuple(attempts),
        market_mark_applied=True,
        reservation_release_mutation_applied=release_mutation,
        fingerprint_sha256=stable_digest(payload),
    )
    runtime._completed[reservation_arbitration.fingerprint_sha256] = (
        request_fingerprint,
        result,
    )
    return result


__all__ = [
    "MasterHistoricalPaperAccountSnapshot",
    "MasterHistoricalPaperAttemptStatus",
    "MasterHistoricalPaperExecutionAttempt",
    "MasterHistoricalPaperExecutionResult",
    "MasterHistoricalPaperExecutionStatus",
    "MasterHistoricalPaperProposalEvidence",
    "MasterHistoricalPaperReasonCode",
    "MasterHistoricalPaperRuntime",
    "MasterHistoricalPaperRuntimeIdentity",
    "build_master_historical_paper_runtime",
    "execute_master_historical_paper_admissions",
    "master_historical_paper_account_payload",
    "master_historical_paper_execution_payload",
]
