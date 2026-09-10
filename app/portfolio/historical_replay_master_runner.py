from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from app.services.backtest.dataset import canonical_candle_rows
from app.services.backtest.ids import stable_digest

from .allocation import AllocationEnvelopeStatus, MasterAllocationPolicy
from .arbitration import MasterArbitrationPolicy, MasterArbitrationPolicyStatus
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
    build_master_historical_paper_runtime,
    execute_master_historical_paper_admissions,
)
from .historical_replay_preexecution import (
    HistoricalCrewPreExecutionEvidence,
    MasterHistoricalDecisionBarrier,
    build_master_historical_decision_barrier,
)
from .historical_replay_reservation_arbitration import (
    MasterHistoricalCapitalRequirement,
    MasterHistoricalReservationArbitrationResult,
    bridge_master_historical_reservation_and_arbitration,
)
from .historical_replay_virtual_lifecycle import (
    MasterHistoricalLifecycleResult,
    MasterHistoricalVirtualLot,
    MasterHistoricalVirtualLotBook,
    MasterHistoricalVirtualLotBookSnapshot,
    MasterHistoricalVirtualLotRegistrationResult,
    MasterHistoricalVirtualLotStatus,
    build_master_historical_virtual_lot_book,
    build_master_historical_virtual_portfolio_snapshot,
    process_master_historical_virtual_lot_barrier,
    register_master_historical_virtual_lots,
)
from .models import (
    CrewExposureSnapshot,
    MasterCapitalSnapshot,
    MasterPortfolioSnapshot,
    SnapshotDataStatus,
)
from .reservation import (
    MasterReservationLedger,
    ReservationLedgerSnapshot,
    ReservationRecordStatus,
)
from .risk_gate import (
    MasterRiskGateDecisionStatus,
    MasterRiskGatePolicy,
    MasterRiskGatePolicyStatus,
)
from .snapshot import build_master_portfolio_snapshot

if TYPE_CHECKING:
    from app.evaluation.models import Metric

ZERO = Decimal("0")


class MasterHistoricalCoordinatedReplayStatus(StrEnum):
    COMPLETED = "COMPLETED"


class MasterHistoricalBarrierInputSource(Protocol):
    async def input_for_barrier(
        self,
        *,
        barrier: MasterHistoricalReplayBarrier,
        portfolio_snapshot: MasterPortfolioSnapshot,
    ) -> MasterHistoricalBarrierInput: ...


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


def _object_payload(value: object | None, *, field_name: str) -> object | None:
    if value is None:
        return None
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


def _metric_payload(metric: Metric) -> dict[str, object]:
    return {
        "status": metric.status,
        "value": metric.value,
        "reason": metric.reason,
    }


def _trade_metrics(values: tuple[Decimal, ...]) -> tuple[int, int, int, Metric, Metric, Metric]:
    from app.evaluation.models import Metric

    wins = tuple(value for value in values if value > ZERO)
    losses = tuple(value for value in values if value < ZERO)
    breakeven = tuple(value for value in values if value == ZERO)
    count = len(values)
    if count == 0:
        unavailable = Metric.unavailable("NO_CLOSED_VIRTUAL_LOTS")
        return 0, 0, 0, unavailable, unavailable, unavailable
    win_rate = Metric.available(Decimal(len(wins)) / Decimal(count))
    expectancy = Metric.available(sum(values, ZERO) / Decimal(count))
    gross_profit = sum(wins, ZERO)
    gross_loss = abs(sum(losses, ZERO))
    if gross_loss == ZERO and gross_profit > ZERO:
        profit_factor = Metric.unbounded("NO_LOSING_VIRTUAL_LOTS")
    elif gross_loss == ZERO:
        profit_factor = Metric.unavailable("NO_PROFIT_OR_LOSS")
    else:
        profit_factor = Metric.available(gross_profit / gross_loss)
    return len(wins), len(losses), len(breakeven), win_rate, profit_factor, expectancy


def _crew_evidence_payload(item: HistoricalCrewPreExecutionEvidence) -> dict[str, object]:
    return {
        "system_id": item.system_id,
        "market_context": _object_payload(item.market_context, field_name="market_context"),
        "opportunity": _object_payload(item.opportunity, field_name="opportunity"),
        "orchestration_result": _object_payload(
            item.orchestration_result,
            field_name="orchestration_result",
        ),
        "local_risk_decision": _object_payload(
            item.local_risk_decision,
            field_name="local_risk_decision",
        ),
    }


def master_historical_barrier_input_payload(
    item: MasterHistoricalBarrierInput,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-barrier-input.v1",
        "schema_version": item.schema_version,
        "barrier_sequence": item.barrier_sequence,
        "barrier_fingerprint_sha256": item.barrier_fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": (
            item.portfolio_snapshot_fingerprint_sha256
        ),
        "crew_system_ids": item.crew_system_ids,
        "crew_evidence": [_crew_evidence_payload(value) for value in item.crew_evidence],
        "capital_requirement_fingerprints_sha256": tuple(
            value.fingerprint_sha256 for value in item.capital_requirements
        ),
        "source_ref": item.source_ref,
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalBarrierInput:
    barrier_sequence: int
    barrier_fingerprint_sha256: str
    portfolio_snapshot_fingerprint_sha256: str
    crew_system_ids: tuple[str, ...]
    crew_evidence: tuple[HistoricalCrewPreExecutionEvidence, ...]
    capital_requirements: tuple[MasterHistoricalCapitalRequirement, ...]
    source_ref: str
    fingerprint_sha256: str
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.barrier_sequence < 1:
            raise ValueError("barrier input sequence must be >= 1")
        for field_name in (
            "barrier_fingerprint_sha256",
            "portfolio_snapshot_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        systems = tuple(
            _required_text(system_id, field_name="crew_system_ids")
            for system_id in self.crew_system_ids
        )
        if systems != tuple(sorted(systems)) or len(set(systems)) != len(systems):
            raise ValueError("barrier input crew_system_ids must be sorted and unique")
        if not systems:
            raise ValueError("barrier input requires at least one crew")
        object.__setattr__(self, "crew_system_ids", systems)
        evidence_systems = tuple(item.system_id for item in self.crew_evidence)
        if evidence_systems != systems:
            raise ValueError("barrier input requires one ordered evidence item per crew")
        requirement_keys = tuple(
            (item.system_id, item.proposal_id) for item in self.capital_requirements
        )
        if requirement_keys != tuple(sorted(requirement_keys)):
            raise ValueError("barrier input capital requirements must be canonical")
        if len(set(requirement_keys)) != len(requirement_keys):
            raise ValueError("barrier input capital requirements must be unique")
        object.__setattr__(
            self,
            "source_ref",
            _required_text(self.source_ref, field_name="source_ref"),
        )
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical barrier input schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_barrier_input_payload(self))
        if normalized != expected:
            raise ValueError("Master historical barrier input fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def build_master_historical_barrier_input(
    *,
    barrier: MasterHistoricalReplayBarrier,
    portfolio_snapshot: MasterPortfolioSnapshot,
    crew_evidence: tuple[HistoricalCrewPreExecutionEvidence, ...],
    capital_requirements: tuple[MasterHistoricalCapitalRequirement, ...],
    source_ref: str,
) -> MasterHistoricalBarrierInput:
    ordered_evidence = tuple(sorted(crew_evidence, key=lambda item: item.system_id))
    ordered_requirements = tuple(
        sorted(capital_requirements, key=lambda item: (item.system_id, item.proposal_id))
    )
    body = {
        "schema": "money-heist.master-historical-barrier-input.v1",
        "schema_version": "1.0",
        "barrier_sequence": barrier.sequence,
        "barrier_fingerprint_sha256": barrier.fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": portfolio_snapshot.fingerprint_sha256,
        "crew_system_ids": tuple(item.system_id for item in ordered_evidence),
        "crew_evidence": [_crew_evidence_payload(value) for value in ordered_evidence],
        "capital_requirement_fingerprints_sha256": tuple(
            value.fingerprint_sha256 for value in ordered_requirements
        ),
        "source_ref": _required_text(source_ref, field_name="source_ref"),
    }
    return MasterHistoricalBarrierInput(
        barrier_sequence=barrier.sequence,
        barrier_fingerprint_sha256=barrier.fingerprint_sha256,
        portfolio_snapshot_fingerprint_sha256=portfolio_snapshot.fingerprint_sha256,
        crew_system_ids=tuple(item.system_id for item in ordered_evidence),
        crew_evidence=ordered_evidence,
        capital_requirements=ordered_requirements,
        source_ref=body["source_ref"],
        fingerprint_sha256=stable_digest(body),
    )


def master_historical_decision_cycle_payload(
    cycle: MasterHistoricalDecisionCycle,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-decision-cycle.v1",
        "schema_version": cycle.schema_version,
        "barrier_sequence": cycle.barrier_sequence,
        "input_fingerprint_sha256": cycle.barrier_input.fingerprint_sha256,
        "portfolio_before_fingerprint_sha256": (
            cycle.portfolio_before.fingerprint_sha256
        ),
        "decision_barrier_fingerprint_sha256": (
            cycle.decision_barrier.fingerprint_sha256
        ),
        "reservation_arbitration_fingerprint_sha256": (
            cycle.reservation_arbitration.fingerprint_sha256
        ),
        "paper_execution_fingerprint_sha256": cycle.paper_execution.fingerprint_sha256,
        "lot_registration_fingerprint_sha256": cycle.lot_registration.fingerprint_sha256,
        "portfolio_after_fingerprint_sha256": cycle.portfolio_after.fingerprint_sha256,
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalDecisionCycle:
    barrier_sequence: int
    barrier_input: MasterHistoricalBarrierInput
    portfolio_before: MasterPortfolioSnapshot
    decision_barrier: MasterHistoricalDecisionBarrier
    reservation_arbitration: MasterHistoricalReservationArbitrationResult
    paper_execution: MasterHistoricalPaperExecutionResult
    lot_registration: MasterHistoricalVirtualLotRegistrationResult
    portfolio_after: MasterPortfolioSnapshot
    fingerprint_sha256: str
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.barrier_sequence < 1:
            raise ValueError("decision cycle barrier_sequence must be >= 1")
        if self.barrier_input.barrier_sequence != self.barrier_sequence:
            raise ValueError("decision cycle input barrier mismatch")
        if self.decision_barrier.barrier_sequence != self.barrier_sequence:
            raise ValueError("decision cycle decision barrier mismatch")
        if self.portfolio_before.fingerprint_sha256 != (
            self.barrier_input.portfolio_snapshot_fingerprint_sha256
        ):
            raise ValueError("decision cycle input does not bind pre-admission portfolio")
        if self.reservation_arbitration.decision_barrier_fingerprint_sha256 != (
            self.decision_barrier.fingerprint_sha256
        ):
            raise ValueError("decision cycle reservation/arbitration provenance mismatch")
        if self.paper_execution.decision_barrier_fingerprint_sha256 != (
            self.decision_barrier.fingerprint_sha256
        ):
            raise ValueError("decision cycle PAPER provenance mismatch")
        if self.lot_registration.execution_result_fingerprint_sha256 != (
            self.paper_execution.fingerprint_sha256
        ):
            raise ValueError("decision cycle lot registration provenance mismatch")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical decision cycle schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_decision_cycle_payload(self))
        if normalized != expected:
            raise ValueError("Master historical decision cycle fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)


@dataclass(frozen=True, slots=True)
class MasterHistoricalEquityPoint:
    barrier_sequence: int
    observed_at: datetime
    equity: Decimal
    account_fingerprint_sha256: str
    fingerprint_sha256: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.barrier_sequence < 1:
            raise ValueError("equity point barrier_sequence must be >= 1")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, field_name="observed_at"))
        object.__setattr__(self, "equity", _decimal(self.equity, field_name="equity"))
        object.__setattr__(
            self,
            "account_fingerprint_sha256",
            _sha256(self.account_fingerprint_sha256, field_name="account_fingerprint_sha256"),
        )
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical equity point schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_equity_point_payload(self))
        if normalized != expected:
            raise ValueError("Master historical equity point fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def master_historical_equity_point_payload(
    point: MasterHistoricalEquityPoint,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-equity-point.v1",
        "schema_version": point.schema_version,
        "barrier_sequence": point.barrier_sequence,
        "observed_at": point.observed_at,
        "equity": point.equity,
        "account_fingerprint_sha256": point.account_fingerprint_sha256,
    }


def master_historical_crew_evaluation_payload(
    item: MasterHistoricalCrewEvaluation,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-crew-evaluation.v1",
        "schema_version": item.schema_version,
        "system_id": item.system_id,
        "entry_count": item.entry_count,
        "closed_lot_count": item.closed_lot_count,
        "open_lot_count": item.open_lot_count,
        "winning_lots": item.winning_lots,
        "losing_lots": item.losing_lots,
        "breakeven_lots": item.breakeven_lots,
        "realized_net_pnl": item.realized_net_pnl,
        "final_open_risk_amount": item.final_open_risk_amount,
        "final_gross_exposure_amount": item.final_gross_exposure_amount,
        "win_rate": _metric_payload(item.win_rate),
        "profit_factor": _metric_payload(item.profit_factor),
        "expectancy": _metric_payload(item.expectancy),
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalCrewEvaluation:
    system_id: str
    entry_count: int
    closed_lot_count: int
    open_lot_count: int
    winning_lots: int
    losing_lots: int
    breakeven_lots: int
    realized_net_pnl: Decimal
    final_open_risk_amount: Decimal
    final_gross_exposure_amount: Decimal
    win_rate: Metric
    profit_factor: Metric
    expectancy: Metric
    fingerprint_sha256: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "system_id",
            _required_text(self.system_id, field_name="system_id"),
        )
        for field_name in (
            "entry_count",
            "closed_lot_count",
            "open_lot_count",
            "winning_lots",
            "losing_lots",
            "breakeven_lots",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be an integer >= 0")
        if self.entry_count != self.closed_lot_count + self.open_lot_count:
            raise ValueError("crew entry_count must equal closed + open lots")
        if self.closed_lot_count != (
            self.winning_lots + self.losing_lots + self.breakeven_lots
        ):
            raise ValueError("crew closed-lot outcome counts are inconsistent")
        object.__setattr__(
            self,
            "realized_net_pnl",
            _decimal(self.realized_net_pnl, field_name="realized_net_pnl"),
        )
        for field_name in ("final_open_risk_amount", "final_gross_exposure_amount"):
            object.__setattr__(
                self,
                field_name,
                _non_negative_decimal(getattr(self, field_name), field_name=field_name),
            )
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical crew evaluation schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_crew_evaluation_payload(self))
        if normalized != expected:
            raise ValueError("Master historical crew evaluation fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def master_historical_evaluation_payload(
    item: MasterHistoricalEvaluation,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-evaluation.v1",
        "schema_version": item.schema_version,
        "master_portfolio_id": item.master_portfolio_id,
        "initial_capital": item.initial_capital,
        "final_equity": item.final_equity,
        "master_account_net_pnl": item.master_account_net_pnl,
        "return_pct": _metric_payload(item.return_pct),
        "max_drawdown_abs": _metric_payload(item.max_drawdown_abs),
        "max_drawdown_pct": _metric_payload(item.max_drawdown_pct),
        "decision_cycle_count": item.decision_cycle_count,
        "local_authorized_candidate_count": item.local_authorized_candidate_count,
        "not_reserved_count": item.not_reserved_count,
        "master_admitted_count": item.master_admitted_count,
        "master_rejected_count": item.master_rejected_count,
        "paper_entry_count": item.paper_entry_count,
        "paper_cash_blocked_count": item.paper_cash_blocked_count,
        "closed_lot_count": item.closed_lot_count,
        "open_lot_count": item.open_lot_count,
        "winning_lots": item.winning_lots,
        "losing_lots": item.losing_lots,
        "breakeven_lots": item.breakeven_lots,
        "closed_lot_realized_net_pnl": item.closed_lot_realized_net_pnl,
        "fees_paid": item.fees_paid,
        "final_open_risk_amount": item.final_open_risk_amount,
        "final_virtual_gross_exposure_amount": item.final_virtual_gross_exposure_amount,
        "win_rate": _metric_payload(item.win_rate),
        "profit_factor": _metric_payload(item.profit_factor),
        "expectancy": _metric_payload(item.expectancy),
        "ai_cost_eur": _metric_payload(item.ai_cost_eur),
        "economic_net": _metric_payload(item.economic_net),
        "crew_evaluations": [
            master_historical_crew_evaluation_payload(value)
            for value in item.crew_evaluations
        ],
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalEvaluation:
    master_portfolio_id: str
    initial_capital: Decimal
    final_equity: Decimal
    master_account_net_pnl: Decimal
    return_pct: Metric
    max_drawdown_abs: Metric
    max_drawdown_pct: Metric
    decision_cycle_count: int
    local_authorized_candidate_count: int
    not_reserved_count: int
    master_admitted_count: int
    master_rejected_count: int
    paper_entry_count: int
    paper_cash_blocked_count: int
    closed_lot_count: int
    open_lot_count: int
    winning_lots: int
    losing_lots: int
    breakeven_lots: int
    closed_lot_realized_net_pnl: Decimal
    fees_paid: Decimal
    final_open_risk_amount: Decimal
    final_virtual_gross_exposure_amount: Decimal
    win_rate: Metric
    profit_factor: Metric
    expectancy: Metric
    ai_cost_eur: Metric
    economic_net: Metric
    crew_evaluations: tuple[MasterHistoricalCrewEvaluation, ...]
    fingerprint_sha256: str
    single_master_capital: bool = field(default=True, init=False)
    branch_equities_summed: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "master_portfolio_id",
            _required_text(self.master_portfolio_id, field_name="master_portfolio_id"),
        )
        for field_name in (
            "initial_capital",
            "final_equity",
            "master_account_net_pnl",
            "closed_lot_realized_net_pnl",
            "fees_paid",
            "final_open_risk_amount",
            "final_virtual_gross_exposure_amount",
        ):
            object.__setattr__(
                self,
                field_name,
                _decimal(getattr(self, field_name), field_name=field_name),
            )
        if self.initial_capital <= ZERO:
            raise ValueError("Master historical initial_capital must be > 0")
        if self.master_account_net_pnl != self.final_equity - self.initial_capital:
            raise ValueError("Master historical net PnL must equal final equity - initial capital")
        if self.fees_paid < ZERO:
            raise ValueError("Master historical fees_paid must be >= 0")
        if self.final_open_risk_amount < ZERO or self.final_virtual_gross_exposure_amount < ZERO:
            raise ValueError("Master historical final exposures must be >= 0")
        for field_name in (
            "decision_cycle_count",
            "local_authorized_candidate_count",
            "not_reserved_count",
            "master_admitted_count",
            "master_rejected_count",
            "paper_entry_count",
            "paper_cash_blocked_count",
            "closed_lot_count",
            "open_lot_count",
            "winning_lots",
            "losing_lots",
            "breakeven_lots",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be an integer >= 0")
        if self.closed_lot_count != self.winning_lots + self.losing_lots + self.breakeven_lots:
            raise ValueError("Master historical closed-lot outcome counts are inconsistent")
        if self.paper_entry_count != self.closed_lot_count + self.open_lot_count:
            raise ValueError("Master historical PAPER entries must equal virtual lot count")
        if self.master_admitted_count != (
            self.paper_entry_count + self.paper_cash_blocked_count
        ):
            raise ValueError("every Master ADMIT must execute or be cash-blocked")
        if self.local_authorized_candidate_count != (
            self.not_reserved_count + self.master_admitted_count + self.master_rejected_count
        ):
            raise ValueError("local authorized candidate accounting is incomplete")
        crew_ids = tuple(item.system_id for item in self.crew_evaluations)
        if crew_ids != tuple(sorted(crew_ids)) or len(set(crew_ids)) != len(crew_ids):
            raise ValueError("Master historical crew evaluations must be sorted and unique")
        if sum(item.entry_count for item in self.crew_evaluations) != self.paper_entry_count:
            raise ValueError("crew entry counts must sum to Master PAPER entry count")
        if sum(item.closed_lot_count for item in self.crew_evaluations) != self.closed_lot_count:
            raise ValueError("crew closed-lot counts must sum to Master closed-lot count")
        if sum(item.open_lot_count for item in self.crew_evaluations) != self.open_lot_count:
            raise ValueError("crew open-lot counts must sum to Master open-lot count")
        if sum(
            (item.realized_net_pnl for item in self.crew_evaluations),
            ZERO,
        ) != self.closed_lot_realized_net_pnl:
            raise ValueError("crew realized PnL must sum to Master closed-lot PnL")
        if sum(
            (item.final_open_risk_amount for item in self.crew_evaluations),
            ZERO,
        ) != self.final_open_risk_amount:
            raise ValueError("crew open risk must sum to Master final open risk")
        if sum(
            (item.final_gross_exposure_amount for item in self.crew_evaluations),
            ZERO,
        ) != self.final_virtual_gross_exposure_amount:
            raise ValueError("crew gross exposure must sum to Master virtual gross exposure")
        from app.evaluation.models import MetricStatus

        if self.ai_cost_eur.status is not MetricStatus.UNAVAILABLE:
            raise ValueError("Step 7 cannot invent AI cost economics")
        if self.economic_net.status is not MetricStatus.UNAVAILABLE:
            raise ValueError("Step 7 cannot invent economic net without AI costs")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical evaluation schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_evaluation_payload(self))
        if normalized != expected:
            raise ValueError("Master historical evaluation fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def master_historical_replay_result_payload(
    result: MasterHistoricalCoordinatedReplayResult,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-coordinated-replay.v1",
        "schema_version": result.schema_version,
        "result_id": result.result_id,
        "status": result.status,
        "master_portfolio_id": result.master_portfolio_id,
        "plan_id": result.plan_id,
        "timeline_id": result.timeline_id,
        "plan_fingerprint_sha256": result.plan_fingerprint_sha256,
        "timeline_fingerprint_sha256": result.timeline_fingerprint_sha256,
        "allocation_policy_fingerprint_sha256": (
            result.allocation_policy_fingerprint_sha256
        ),
        "gate_policy_fingerprint_sha256": result.gate_policy_fingerprint_sha256,
        "arbitration_policy_fingerprint_sha256": (
            result.arbitration_policy_fingerprint_sha256
        ),
        "opening_snapshot_fingerprint_sha256": (
            result.opening_snapshot.fingerprint_sha256
        ),
        "runtime_fingerprint_sha256": result.runtime_fingerprint_sha256,
        "book_id": result.book_id,
        "processed_barrier_count": result.processed_barrier_count,
        "lifecycle_result_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in result.lifecycle_results
        ),
        "decision_cycle_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in result.decision_cycles
        ),
        "equity_curve_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in result.equity_curve
        ),
        "final_account_fingerprint_sha256": result.final_account_fingerprint_sha256,
        "final_book_fingerprint_sha256": result.final_book.fingerprint_sha256,
        "final_ledger_fingerprint_sha256": result.final_ledger.fingerprint_sha256,
        "evaluation_fingerprint_sha256": result.evaluation.fingerprint_sha256,
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalCoordinatedReplayResult:
    result_id: str
    status: MasterHistoricalCoordinatedReplayStatus
    master_portfolio_id: str
    plan_id: str
    timeline_id: str
    plan_fingerprint_sha256: str
    timeline_fingerprint_sha256: str
    allocation_policy_fingerprint_sha256: str
    gate_policy_fingerprint_sha256: str
    arbitration_policy_fingerprint_sha256: str
    opening_snapshot: MasterPortfolioSnapshot
    runtime_fingerprint_sha256: str
    book_id: str
    processed_barrier_count: int
    lifecycle_results: tuple[MasterHistoricalLifecycleResult, ...]
    decision_cycles: tuple[MasterHistoricalDecisionCycle, ...]
    equity_curve: tuple[MasterHistoricalEquityPoint, ...]
    final_account_fingerprint_sha256: str
    final_book: MasterHistoricalVirtualLotBookSnapshot
    final_ledger: ReservationLedgerSnapshot
    evaluation: MasterHistoricalEvaluation
    fingerprint_sha256: str
    single_master_capital: bool = field(default=True, init=False)
    sums_branch_equities: bool = field(default=False, init=False)
    uses_branch_brokers: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute_live: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in ("result_id", "master_portfolio_id", "plan_id", "timeline_id", "book_id"):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "plan_fingerprint_sha256",
            "timeline_fingerprint_sha256",
            "allocation_policy_fingerprint_sha256",
            "gate_policy_fingerprint_sha256",
            "arbitration_policy_fingerprint_sha256",
            "runtime_fingerprint_sha256",
            "final_account_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        if self.status is not MasterHistoricalCoordinatedReplayStatus.COMPLETED:
            raise ValueError("Master historical coordinated replay must be COMPLETED")
        if self.processed_barrier_count != len(self.lifecycle_results):
            raise ValueError("processed_barrier_count must equal lifecycle result count")
        if self.processed_barrier_count != len(self.equity_curve):
            raise ValueError("one equity point is required per processed barrier")
        if tuple(item.barrier_sequence for item in self.lifecycle_results) != tuple(
            range(1, self.processed_barrier_count + 1)
        ):
            raise ValueError("Master historical lifecycle results must cover contiguous barriers")
        if tuple(item.barrier_sequence for item in self.equity_curve) != tuple(
            range(1, self.processed_barrier_count + 1)
        ):
            raise ValueError("Master historical equity curve must cover contiguous barriers")
        if self.final_book.book_id != self.book_id:
            raise ValueError("Master historical final book mismatch")
        if self.evaluation.master_portfolio_id != self.master_portfolio_id:
            raise ValueError("Master historical evaluation portfolio mismatch")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical replay result schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_historical_replay_result_payload(self))
        if normalized != expected:
            raise ValueError("Master historical replay result fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def _validate_static_context(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    allocation_policy: MasterAllocationPolicy,
    gate_policy: MasterRiskGatePolicy,
    arbitration_policy: MasterArbitrationPolicy,
) -> None:
    if allocation_policy.status is not AllocationEnvelopeStatus.CONFIGURED:
        raise ValueError("Master historical replay requires CONFIGURED allocation policy")
    if gate_policy.status is not MasterRiskGatePolicyStatus.CONFIGURED:
        raise ValueError("Master historical replay requires CONFIGURED gate policy")
    if arbitration_policy.status is not MasterArbitrationPolicyStatus.CONFIGURED:
        raise ValueError("Master historical replay requires CONFIGURED arbitration policy")
    if any(
        value != plan.master_portfolio_id
        for value in (
            timeline.master_portfolio_id,
            allocation_policy.master_portfolio_id,
            gate_policy.master_portfolio_id,
            arbitration_policy.master_portfolio_id,
        )
    ):
        raise ValueError("Master historical replay spans multiple Master Portfolios")
    if (
        timeline.plan_id != plan.plan_id
        or timeline.plan_fingerprint_sha256 != plan.fingerprint_sha256
    ):
        raise ValueError("Master historical timeline does not bind replay plan")
    if plan.allocation_policy_fingerprint_sha256 != allocation_policy.fingerprint_sha256:
        raise ValueError("Master historical allocation policy changed after plan sealing")
    if plan.gate_policy_fingerprint_sha256 != gate_policy.fingerprint_sha256:
        raise ValueError("Master historical gate policy changed after plan sealing")
    if plan.arbitration_policy_fingerprint_sha256 != arbitration_policy.fingerprint_sha256:
        raise ValueError("Master historical arbitration policy changed after plan sealing")
    member_ids = tuple(member.system_id for member in allocation_policy.members)
    if timeline.crew_system_ids != member_ids:
        raise ValueError("Master historical timeline membership mismatch")


def _canonical_rows(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    candles: tuple[object, ...],
) -> tuple[dict[str, object], ...]:
    rows = canonical_candle_rows(
        candles,
        expected_symbol=plan.symbol,
        expected_timeframe=plan.timeframe,
    )
    if len(rows) != timeline.candle_count:
        raise ValueError("Master historical replay candle count does not match timeline")
    for index, row in enumerate(rows, start=1):
        open_barrier = timeline.barriers[(index - 1) * 2]
        close_barrier = timeline.barriers[(index - 1) * 2 + 1]
        digest = stable_digest(row)
        if open_barrier.candle_fingerprint_sha256 != digest:
            raise ValueError("Master historical OPEN candle fingerprint mismatch")
        if close_barrier.candle_fingerprint_sha256 != digest:
            raise ValueError("Master historical CLOSE candle fingerprint mismatch")
    return rows


def _opening_snapshot(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    allocation_policy: MasterAllocationPolicy,
) -> MasterPortfolioSnapshot:
    observed_at = timeline.barriers[0].observed_at
    capital = MasterCapitalSnapshot(
        master_portfolio_id=plan.master_portfolio_id,
        observed_at=observed_at,
        status=SnapshotDataStatus.AVAILABLE,
        source="master-historical-coordinated-replay",
        equity=plan.master_initial_capital,
        cash_balance=plan.master_initial_capital,
        day_start_equity=plan.master_initial_capital,
        equity_peak=plan.master_initial_capital,
        source_ref=plan.fingerprint_sha256,
    )
    exposures = tuple(
        CrewExposureSnapshot(
            system_id=member.system_id,
            observed_at=observed_at,
            status=SnapshotDataStatus.AVAILABLE,
            source="master-historical-coordinated-replay",
            open_positions=0,
            gross_exposure_amount=ZERO,
            open_risk_amount=ZERO,
            source_ref=plan.fingerprint_sha256,
        )
        for member in allocation_policy.members
    )
    return build_master_portfolio_snapshot(
        master_capital=capital,
        members=allocation_policy.members,
        crew_exposures=exposures,
    )


def _barrier_row(
    *,
    rows: tuple[dict[str, object], ...],
    barrier: MasterHistoricalReplayBarrier,
) -> dict[str, object]:
    return rows[barrier.candle_index - 1]


def _barrier_mark(
    *,
    row: dict[str, object],
    barrier: MasterHistoricalReplayBarrier,
) -> Decimal:
    field_name = (
        "open"
        if barrier.phase is MasterHistoricalReplayBarrierPhase.CANDLE_OPEN
        else "close"
    )
    value = _decimal(row[field_name], field_name=field_name)
    if value <= ZERO:
        raise ValueError("Master historical barrier mark must be > 0")
    return value


def _validate_barrier_input(
    *,
    supplied: MasterHistoricalBarrierInput,
    barrier: MasterHistoricalReplayBarrier,
    portfolio_snapshot: MasterPortfolioSnapshot,
    timeline: MasterHistoricalReplayTimeline,
) -> None:
    if supplied.barrier_sequence != barrier.sequence:
        raise ValueError("Master historical input barrier sequence mismatch")
    if supplied.barrier_fingerprint_sha256 != barrier.fingerprint_sha256:
        raise ValueError("Master historical input barrier fingerprint mismatch")
    if supplied.portfolio_snapshot_fingerprint_sha256 != portfolio_snapshot.fingerprint_sha256:
        raise ValueError("Master historical input did not bind current portfolio snapshot")
    if supplied.crew_system_ids != timeline.crew_system_ids:
        raise ValueError("Master historical input membership mismatch")


def _proposal_map(
    crew_evidence: tuple[HistoricalCrewPreExecutionEvidence, ...],
) -> dict[tuple[str, str], object]:
    result: dict[tuple[str, str], object] = {}
    for item in crew_evidence:
        orchestration = item.orchestration_result
        proposal = getattr(orchestration, "trade_proposal", None)
        if proposal is None:
            continue
        proposal_id = _required_text(
            getattr(proposal, "proposal_id", ""),
            field_name="proposal_id",
        )
        key = (item.system_id, proposal_id)
        if key in result:
            raise ValueError("Master historical input duplicated proposal evidence")
        result[key] = proposal
    return result


def _admitted_proposal_evidence(
    *,
    crew_evidence: tuple[HistoricalCrewPreExecutionEvidence, ...],
    reservation_arbitration: MasterHistoricalReservationArbitrationResult,
) -> tuple[MasterHistoricalPaperProposalEvidence, ...]:
    proposals = _proposal_map(crew_evidence)
    if reservation_arbitration.arbitration_result is None:
        return ()
    keys = tuple(
        (outcome.system_id, outcome.proposal_id)
        for outcome in reservation_arbitration.arbitration_result.outcomes
        if outcome.decision_status is MasterRiskGateDecisionStatus.ADMIT
    )
    evidence = []
    for key in keys:
        proposal = proposals.get(key)
        if proposal is None:
            raise ValueError("Master-admitted candidate has no exact proposal evidence")
        evidence.append(
            MasterHistoricalPaperProposalEvidence(
                system_id=key[0],
                proposal=proposal,
            )
        )
    return tuple(evidence)


def _executed_proposal_evidence(
    *,
    admitted: tuple[MasterHistoricalPaperProposalEvidence, ...],
    paper_execution: MasterHistoricalPaperExecutionResult,
) -> tuple[MasterHistoricalPaperProposalEvidence, ...]:
    executed = {
        (attempt.source_system_id, attempt.proposal_id)
        for attempt in paper_execution.attempts
        if attempt.status is MasterHistoricalPaperAttemptStatus.EXECUTED
    }
    return tuple(
        item
        for item in admitted
        if (item.system_id, str(getattr(item.proposal, "proposal_id", ""))) in executed
    )


def _equity_point(
    *,
    barrier: MasterHistoricalReplayBarrier,
    equity: Decimal,
    account_fingerprint_sha256: str,
) -> MasterHistoricalEquityPoint:
    payload = {
        "schema": "money-heist.master-historical-equity-point.v1",
        "schema_version": "1.0",
        "barrier_sequence": barrier.sequence,
        "observed_at": barrier.observed_at,
        "equity": equity,
        "account_fingerprint_sha256": account_fingerprint_sha256,
    }
    return MasterHistoricalEquityPoint(
        barrier_sequence=barrier.sequence,
        observed_at=barrier.observed_at,
        equity=equity,
        account_fingerprint_sha256=account_fingerprint_sha256,
        fingerprint_sha256=stable_digest(payload),
    )


def _crew_evaluation(
    *,
    system_id: str,
    lots: tuple[MasterHistoricalVirtualLot, ...],
    final_mark: Decimal,
) -> MasterHistoricalCrewEvaluation:
    crew_lots = tuple(lot for lot in lots if lot.source_system_id == system_id)
    closed = tuple(
        lot for lot in crew_lots if lot.status is MasterHistoricalVirtualLotStatus.CLOSED
    )
    open_lots = tuple(
        lot for lot in crew_lots if lot.status is MasterHistoricalVirtualLotStatus.OPEN
    )
    pnl_values = tuple(lot.net_realized_pnl or ZERO for lot in closed)
    wins, losses, breakeven, win_rate, profit_factor, expectancy = _trade_metrics(pnl_values)
    body = {
        "schema": "money-heist.master-historical-crew-evaluation.v1",
        "schema_version": "1.0",
        "system_id": system_id,
        "entry_count": len(crew_lots),
        "closed_lot_count": len(closed),
        "open_lot_count": len(open_lots),
        "winning_lots": wins,
        "losing_lots": losses,
        "breakeven_lots": breakeven,
        "realized_net_pnl": sum(pnl_values, ZERO),
        "final_open_risk_amount": sum(
            (lot.reserved_open_risk_amount for lot in open_lots),
            ZERO,
        ),
        "final_gross_exposure_amount": sum(
            (lot.quantity * final_mark for lot in open_lots),
            ZERO,
        ),
        "win_rate": _metric_payload(win_rate),
        "profit_factor": _metric_payload(profit_factor),
        "expectancy": _metric_payload(expectancy),
    }
    return MasterHistoricalCrewEvaluation(
        system_id=system_id,
        entry_count=len(crew_lots),
        closed_lot_count=len(closed),
        open_lot_count=len(open_lots),
        winning_lots=wins,
        losing_lots=losses,
        breakeven_lots=breakeven,
        realized_net_pnl=sum(pnl_values, ZERO),
        final_open_risk_amount=body["final_open_risk_amount"],
        final_gross_exposure_amount=body["final_gross_exposure_amount"],
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        fingerprint_sha256=stable_digest(body),
    )


def _build_evaluation(
    *,
    plan: MasterHistoricalReplayPlan,
    allocation_policy: MasterAllocationPolicy,
    decision_cycles: tuple[MasterHistoricalDecisionCycle, ...],
    equity_curve: tuple[MasterHistoricalEquityPoint, ...],
    book: MasterHistoricalVirtualLotBook,
    final_book: MasterHistoricalVirtualLotBookSnapshot,
    final_account,
) -> MasterHistoricalEvaluation:
    from app.evaluation.models import EquityPoint, Metric
    from app.evaluation.trading import calculate_trading_metrics

    equity_points = tuple(
        EquityPoint(observed_at=item.observed_at, equity=item.equity)
        for item in equity_curve
    )
    drawdown = calculate_trading_metrics((), equity_points=equity_points)
    closed = book.closed_lots
    open_lots = book.open_lots
    pnl_values = tuple(lot.net_realized_pnl or ZERO for lot in closed)
    wins, losses, breakeven, win_rate, profit_factor, expectancy = _trade_metrics(pnl_values)
    local_authorized = sum(
        len(cycle.decision_barrier.candidate_seeds) for cycle in decision_cycles
    )
    not_reserved = sum(
        cycle.reservation_arbitration.not_reserved_count for cycle in decision_cycles
    )
    admitted = sum(cycle.reservation_arbitration.admitted_count for cycle in decision_cycles)
    master_rejected = sum(
        cycle.reservation_arbitration.master_rejected_count for cycle in decision_cycles
    )
    paper_entries = sum(cycle.paper_execution.executed_count for cycle in decision_cycles)
    cash_blocked = sum(cycle.paper_execution.released_count for cycle in decision_cycles)
    final_mark = final_book.mark_price
    crews = tuple(
        _crew_evaluation(
            system_id=member.system_id,
            lots=book.lots,
            final_mark=final_mark,
        )
        for member in allocation_policy.members
    )
    final_equity = _decimal(final_account.equity, field_name="final_equity")
    net_pnl = final_equity - plan.master_initial_capital
    return_pct = Metric.available(net_pnl / plan.master_initial_capital)
    ai_cost = Metric.unavailable("AI_USAGE_NOT_SUPPLIED_BY_STEP7_INPUT_PORT")
    economic_net = Metric.unavailable("AI_COST_UNAVAILABLE")
    body = {
        "schema": "money-heist.master-historical-evaluation.v1",
        "schema_version": "1.0",
        "master_portfolio_id": plan.master_portfolio_id,
        "initial_capital": plan.master_initial_capital,
        "final_equity": final_equity,
        "master_account_net_pnl": net_pnl,
        "return_pct": _metric_payload(return_pct),
        "max_drawdown_abs": _metric_payload(drawdown.max_drawdown_abs),
        "max_drawdown_pct": _metric_payload(drawdown.max_drawdown_pct),
        "decision_cycle_count": len(decision_cycles),
        "local_authorized_candidate_count": local_authorized,
        "not_reserved_count": not_reserved,
        "master_admitted_count": admitted,
        "master_rejected_count": master_rejected,
        "paper_entry_count": paper_entries,
        "paper_cash_blocked_count": cash_blocked,
        "closed_lot_count": len(closed),
        "open_lot_count": len(open_lots),
        "winning_lots": wins,
        "losing_lots": losses,
        "breakeven_lots": breakeven,
        "closed_lot_realized_net_pnl": sum(pnl_values, ZERO),
        "fees_paid": _non_negative_decimal(final_account.fees_paid, field_name="fees_paid"),
        "final_open_risk_amount": final_book.committed_open_risk_amount,
        "final_virtual_gross_exposure_amount": (
            final_book.virtual_gross_exposure_amount
        ),
        "win_rate": _metric_payload(win_rate),
        "profit_factor": _metric_payload(profit_factor),
        "expectancy": _metric_payload(expectancy),
        "ai_cost_eur": _metric_payload(ai_cost),
        "economic_net": _metric_payload(economic_net),
        "crew_evaluations": [master_historical_crew_evaluation_payload(item) for item in crews],
    }
    return MasterHistoricalEvaluation(
        master_portfolio_id=plan.master_portfolio_id,
        initial_capital=plan.master_initial_capital,
        final_equity=final_equity,
        master_account_net_pnl=net_pnl,
        return_pct=return_pct,
        max_drawdown_abs=drawdown.max_drawdown_abs,
        max_drawdown_pct=drawdown.max_drawdown_pct,
        decision_cycle_count=len(decision_cycles),
        local_authorized_candidate_count=local_authorized,
        not_reserved_count=not_reserved,
        master_admitted_count=admitted,
        master_rejected_count=master_rejected,
        paper_entry_count=paper_entries,
        paper_cash_blocked_count=cash_blocked,
        closed_lot_count=len(closed),
        open_lot_count=len(open_lots),
        winning_lots=wins,
        losing_lots=losses,
        breakeven_lots=breakeven,
        closed_lot_realized_net_pnl=sum(pnl_values, ZERO),
        fees_paid=body["fees_paid"],
        final_open_risk_amount=final_book.committed_open_risk_amount,
        final_virtual_gross_exposure_amount=final_book.virtual_gross_exposure_amount,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        ai_cost_eur=ai_cost,
        economic_net=economic_net,
        crew_evaluations=crews,
        fingerprint_sha256=stable_digest(body),
    )


def _assert_final_reservations(
    *,
    book: MasterHistoricalVirtualLotBook,
    ledger: MasterReservationLedger,
) -> None:
    committed = {
        record.reservation_id
        for record in ledger.records()
        if record.status is ReservationRecordStatus.COMMITTED
    }
    open_reservations = {lot.reservation_id for lot in book.open_lots}
    if committed != open_reservations:
        raise RuntimeError("final COMMITTED reservations do not match open virtual lots")
    if any(record.status is ReservationRecordStatus.RESERVED for record in ledger.records()):
        raise RuntimeError("completed Master historical replay cannot leave RESERVED capacity")


async def run_master_historical_coordinated_replay(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    allocation_policy: MasterAllocationPolicy,
    gate_policy: MasterRiskGatePolicy,
    arbitration_policy: MasterArbitrationPolicy,
    candles: tuple[object, ...],
    input_source: MasterHistoricalBarrierInputSource,
) -> MasterHistoricalCoordinatedReplayResult:
    """Run the sealed Master historical loop over one physical PAPER account.

    The input source is called only at decision-eligible CLOSE barriers and must
    bind its output to the exact current Master portfolio snapshot. Step 7 does
    not call an AI provider, Risk Engine, broker-per-crew path, or LIVE path.
    """

    _validate_static_context(
        plan=plan,
        timeline=timeline,
        allocation_policy=allocation_policy,
        gate_policy=gate_policy,
        arbitration_policy=arbitration_policy,
    )
    rows = _canonical_rows(plan=plan, timeline=timeline, candles=candles)
    opening = _opening_snapshot(
        plan=plan,
        timeline=timeline,
        allocation_policy=allocation_policy,
    )
    ledger = MasterReservationLedger(policy=allocation_policy, opening_snapshot=opening)
    runtime: MasterHistoricalPaperRuntime = build_master_historical_paper_runtime(plan=plan)
    book = build_master_historical_virtual_lot_book(plan=plan, runtime=runtime)
    lifecycle_results: list[MasterHistoricalLifecycleResult] = []
    decision_cycles: list[MasterHistoricalDecisionCycle] = []
    equity_curve: list[MasterHistoricalEquityPoint] = []

    for barrier in timeline.barriers:
        row = _barrier_row(rows=rows, barrier=barrier)
        lifecycle = await process_master_historical_virtual_lot_barrier(
            book=book,
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            ledger=ledger,
            candle=row,
        )
        lifecycle_results.append(lifecycle)
        mark = _barrier_mark(row=row, barrier=barrier)
        portfolio_before = await build_master_historical_virtual_portfolio_snapshot(
            book=book,
            allocation_policy=allocation_policy,
            observed_at=barrier.observed_at,
            mark_price=mark,
        )

        if (
            barrier.phase is MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE
            and barrier.decision_eligible
        ):
            supplied = await input_source.input_for_barrier(
                barrier=barrier,
                portfolio_snapshot=portfolio_before,
            )
            _validate_barrier_input(
                supplied=supplied,
                barrier=barrier,
                portfolio_snapshot=portfolio_before,
                timeline=timeline,
            )
            decision_barrier = build_master_historical_decision_barrier(
                plan=plan,
                timeline=timeline,
                barrier=barrier,
                crew_evidence=supplied.crew_evidence,
            )
            reservation_arbitration = bridge_master_historical_reservation_and_arbitration(
                plan=plan,
                timeline=timeline,
                decision_barrier=decision_barrier,
                allocation_policy=allocation_policy,
                gate_policy=gate_policy,
                arbitration_policy=arbitration_policy,
                opening_snapshot=opening,
                portfolio_snapshot=portfolio_before,
                ledger=ledger,
                capital_requirements=supplied.capital_requirements,
            )
            admitted_evidence = _admitted_proposal_evidence(
                crew_evidence=supplied.crew_evidence,
                reservation_arbitration=reservation_arbitration,
            )
            paper_execution = await execute_master_historical_paper_admissions(
                runtime=runtime,
                plan=plan,
                timeline=timeline,
                decision_barrier=decision_barrier,
                reservation_arbitration=reservation_arbitration,
                ledger=ledger,
                candle=row,
                proposal_evidence=admitted_evidence,
            )
            registration_evidence = _executed_proposal_evidence(
                admitted=admitted_evidence,
                paper_execution=paper_execution,
            )
            registration = await register_master_historical_virtual_lots(
                book=book,
                plan=plan,
                timeline=timeline,
                decision_barrier=decision_barrier,
                execution_result=paper_execution,
                ledger=ledger,
                candle=row,
                proposal_evidence=registration_evidence,
            )
            portfolio_after = await build_master_historical_virtual_portfolio_snapshot(
                book=book,
                allocation_policy=allocation_policy,
                observed_at=barrier.observed_at,
                mark_price=mark,
            )
            cycle_body = {
                "schema": "money-heist.master-historical-decision-cycle.v1",
                "schema_version": "1.0",
                "barrier_sequence": barrier.sequence,
                "input_fingerprint_sha256": supplied.fingerprint_sha256,
                "portfolio_before_fingerprint_sha256": portfolio_before.fingerprint_sha256,
                "decision_barrier_fingerprint_sha256": decision_barrier.fingerprint_sha256,
                "reservation_arbitration_fingerprint_sha256": (
                    reservation_arbitration.fingerprint_sha256
                ),
                "paper_execution_fingerprint_sha256": paper_execution.fingerprint_sha256,
                "lot_registration_fingerprint_sha256": registration.fingerprint_sha256,
                "portfolio_after_fingerprint_sha256": portfolio_after.fingerprint_sha256,
            }
            decision_cycles.append(
                MasterHistoricalDecisionCycle(
                    barrier_sequence=barrier.sequence,
                    barrier_input=supplied,
                    portfolio_before=portfolio_before,
                    decision_barrier=decision_barrier,
                    reservation_arbitration=reservation_arbitration,
                    paper_execution=paper_execution,
                    lot_registration=registration,
                    portfolio_after=portfolio_after,
                    fingerprint_sha256=stable_digest(cycle_body),
                )
            )

        account = await runtime.account_snapshot(observed_at=barrier.observed_at)
        equity_curve.append(
            _equity_point(
                barrier=barrier,
                equity=account.equity,
                account_fingerprint_sha256=account.fingerprint_sha256,
            )
        )

    if len(decision_cycles) != timeline.evaluation_candle_count:
        raise RuntimeError("Master historical replay did not process every decision-eligible CLOSE")
    _assert_final_reservations(book=book, ledger=ledger)
    final_barrier = timeline.barriers[-1]
    final_row = _barrier_row(rows=rows, barrier=final_barrier)
    final_mark = _barrier_mark(row=final_row, barrier=final_barrier)
    final_account = await runtime.account_snapshot(observed_at=final_barrier.observed_at)
    final_book = book.snapshot(
        observed_at=final_barrier.observed_at,
        mark_price=final_mark,
    )
    final_ledger = ledger.snapshot()
    evaluation = _build_evaluation(
        plan=plan,
        allocation_policy=allocation_policy,
        decision_cycles=tuple(decision_cycles),
        equity_curve=tuple(equity_curve),
        book=book,
        final_book=final_book,
        final_account=final_account,
    )
    result_id = "master-historical-coordinated:" + stable_digest(
        {
            "schema": "money-heist.master-historical-coordinated-replay-id.v1",
            "plan_fingerprint_sha256": plan.fingerprint_sha256,
            "timeline_fingerprint_sha256": timeline.fingerprint_sha256,
            "decision_cycle_fingerprints": [
                item.fingerprint_sha256 for item in decision_cycles
            ],
            "final_book_fingerprint_sha256": final_book.fingerprint_sha256,
            "final_ledger_fingerprint_sha256": final_ledger.fingerprint_sha256,
            "evaluation_fingerprint_sha256": evaluation.fingerprint_sha256,
        }
    )
    body = {
        "schema": "money-heist.master-historical-coordinated-replay.v1",
        "schema_version": "1.0",
        "result_id": result_id,
        "status": MasterHistoricalCoordinatedReplayStatus.COMPLETED,
        "master_portfolio_id": plan.master_portfolio_id,
        "plan_id": plan.plan_id,
        "timeline_id": timeline.timeline_id,
        "plan_fingerprint_sha256": plan.fingerprint_sha256,
        "timeline_fingerprint_sha256": timeline.fingerprint_sha256,
        "allocation_policy_fingerprint_sha256": allocation_policy.fingerprint_sha256,
        "gate_policy_fingerprint_sha256": gate_policy.fingerprint_sha256,
        "arbitration_policy_fingerprint_sha256": arbitration_policy.fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": opening.fingerprint_sha256,
        "runtime_fingerprint_sha256": runtime.identity.fingerprint_sha256,
        "book_id": book.book_id,
        "processed_barrier_count": len(lifecycle_results),
        "lifecycle_result_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in lifecycle_results
        ),
        "decision_cycle_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in decision_cycles
        ),
        "equity_curve_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in equity_curve
        ),
        "final_account_fingerprint_sha256": final_account.fingerprint_sha256,
        "final_book_fingerprint_sha256": final_book.fingerprint_sha256,
        "final_ledger_fingerprint_sha256": final_ledger.fingerprint_sha256,
        "evaluation_fingerprint_sha256": evaluation.fingerprint_sha256,
    }
    return MasterHistoricalCoordinatedReplayResult(
        result_id=result_id,
        status=MasterHistoricalCoordinatedReplayStatus.COMPLETED,
        master_portfolio_id=plan.master_portfolio_id,
        plan_id=plan.plan_id,
        timeline_id=timeline.timeline_id,
        plan_fingerprint_sha256=plan.fingerprint_sha256,
        timeline_fingerprint_sha256=timeline.fingerprint_sha256,
        allocation_policy_fingerprint_sha256=allocation_policy.fingerprint_sha256,
        gate_policy_fingerprint_sha256=gate_policy.fingerprint_sha256,
        arbitration_policy_fingerprint_sha256=arbitration_policy.fingerprint_sha256,
        opening_snapshot=opening,
        runtime_fingerprint_sha256=runtime.identity.fingerprint_sha256,
        book_id=book.book_id,
        processed_barrier_count=len(lifecycle_results),
        lifecycle_results=tuple(lifecycle_results),
        decision_cycles=tuple(decision_cycles),
        equity_curve=tuple(equity_curve),
        final_account_fingerprint_sha256=final_account.fingerprint_sha256,
        final_book=final_book,
        final_ledger=final_ledger,
        evaluation=evaluation,
        fingerprint_sha256=stable_digest(body),
    )


__all__ = [
    "MasterHistoricalBarrierInput",
    "MasterHistoricalBarrierInputSource",
    "MasterHistoricalCoordinatedReplayResult",
    "MasterHistoricalCoordinatedReplayStatus",
    "MasterHistoricalCrewEvaluation",
    "MasterHistoricalDecisionCycle",
    "MasterHistoricalEquityPoint",
    "MasterHistoricalEvaluation",
    "build_master_historical_barrier_input",
    "master_historical_barrier_input_payload",
    "master_historical_crew_evaluation_payload",
    "master_historical_decision_cycle_payload",
    "master_historical_equity_point_payload",
    "master_historical_evaluation_payload",
    "master_historical_replay_result_payload",
    "run_master_historical_coordinated_replay",
]
