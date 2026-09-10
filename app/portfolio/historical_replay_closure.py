from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .allocation import MasterAllocationPolicy, master_allocation_policy_fingerprint
from .arbitration import MasterArbitrationPolicy, master_arbitration_policy_fingerprint
from .historical_replay import (
    MasterHistoricalReplayPlan,
    master_historical_replay_plan_fingerprint,
)
from .historical_replay_coordinator import (
    MasterHistoricalReplayBarrierPhase,
    MasterHistoricalReplayTimeline,
    master_historical_replay_timeline_fingerprint,
)
from .historical_replay_master_runner import (
    MasterHistoricalCoordinatedReplayResult,
    MasterHistoricalCoordinatedReplayStatus,
    master_historical_barrier_input_payload,
    master_historical_crew_evaluation_payload,
    master_historical_decision_cycle_payload,
    master_historical_equity_point_payload,
    master_historical_evaluation_payload,
    master_historical_replay_result_payload,
)
from .historical_replay_paper_execution import master_historical_paper_execution_payload
from .historical_replay_preexecution import master_historical_decision_barrier_fingerprint
from .historical_replay_reservation_arbitration import (
    master_historical_reservation_arbitration_fingerprint,
)
from .historical_replay_virtual_lifecycle import (
    MasterHistoricalVirtualLotStatus,
    master_historical_lifecycle_result_payload,
    master_historical_virtual_lot_book_snapshot_payload,
    master_historical_virtual_lot_registration_payload,
)
from .models import MasterPortfolioSnapshot, master_portfolio_snapshot_fingerprint
from .reservation import (
    MasterReservationLedger,
    ReservationRecordStatus,
    reservation_ledger_snapshot_fingerprint,
)
from .risk_gate import MasterRiskGatePolicy, master_risk_gate_policy_fingerprint

ZERO = Decimal("0")


class MasterHistoricalReplayAuditStatus(StrEnum):
    VERIFIED = "VERIFIED"


class MasterHistoricalReplayClosureStatus(StrEnum):
    SEALED = "SEALED"


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


def _assert_equal(actual: object, expected: object, *, message: str) -> None:
    if actual != expected:
        raise ValueError(message)


def _assert_digest(actual: str, payload: object, *, label: str) -> None:
    expected = stable_digest(payload)
    if actual != expected:
        raise ValueError(f"{label} fingerprint integrity failure")


def _allocation_fingerprint(policy: MasterAllocationPolicy) -> str:
    return master_allocation_policy_fingerprint(
        master_portfolio_id=policy.master_portfolio_id,
        policy_id=policy.policy_id,
        members=policy.members,
        envelopes=policy.envelopes,
        status=policy.status,
        reason_codes=policy.reason_codes,
        source=policy.source,
        source_ref=policy.source_ref,
        schema_version=policy.schema_version,
    )


def _gate_fingerprint(policy: MasterRiskGatePolicy) -> str:
    return master_risk_gate_policy_fingerprint(
        master_portfolio_id=policy.master_portfolio_id,
        gate_policy_id=policy.gate_policy_id,
        allocation_policy_fingerprint_sha256=(
            policy.allocation_policy_fingerprint_sha256
        ),
        status=policy.status,
        max_total_open_risk_amount=policy.max_total_open_risk_amount,
        max_total_gross_exposure_amount=policy.max_total_gross_exposure_amount,
        reason_code=policy.reason_code,
        source=policy.source,
        source_ref=policy.source_ref,
        schema_version=policy.schema_version,
    )


def _arbitration_fingerprint(policy: MasterArbitrationPolicy) -> str:
    return master_arbitration_policy_fingerprint(
        master_portfolio_id=policy.master_portfolio_id,
        arbitration_policy_id=policy.arbitration_policy_id,
        allocation_policy_fingerprint_sha256=(
            policy.allocation_policy_fingerprint_sha256
        ),
        status=policy.status,
        order_strategy=policy.order_strategy,
        reason_code=policy.reason_code,
        source=policy.source,
        source_ref=policy.source_ref,
        schema_version=policy.schema_version,
    )


def _snapshot_fingerprint(snapshot: MasterPortfolioSnapshot) -> str:
    return master_portfolio_snapshot_fingerprint(
        master_portfolio_id=snapshot.master_portfolio_id,
        observed_at=snapshot.observed_at,
        members=snapshot.members,
        master_capital=snapshot.master_capital,
        crew_exposures=snapshot.crew_exposures,
        status=snapshot.status,
        aggregate_exposure_status=snapshot.aggregate_exposure_status,
        total_open_positions=snapshot.total_open_positions,
        total_gross_exposure_amount=snapshot.total_gross_exposure_amount,
        total_open_risk_amount=snapshot.total_open_risk_amount,
        reason_codes=snapshot.reason_codes,
        schema_version=snapshot.schema_version,
    )


def master_historical_replay_audit_payload(
    report: MasterHistoricalReplayAuditReport,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-replay-audit.v1",
        "schema_version": report.schema_version,
        "audit_id": report.audit_id,
        "status": report.status,
        "master_portfolio_id": report.master_portfolio_id,
        "plan_id": report.plan_id,
        "timeline_id": report.timeline_id,
        "result_id": report.result_id,
        "sealed_at": report.sealed_at,
        "plan_fingerprint_sha256": report.plan_fingerprint_sha256,
        "timeline_fingerprint_sha256": report.timeline_fingerprint_sha256,
        "allocation_policy_fingerprint_sha256": (
            report.allocation_policy_fingerprint_sha256
        ),
        "gate_policy_fingerprint_sha256": report.gate_policy_fingerprint_sha256,
        "arbitration_policy_fingerprint_sha256": (
            report.arbitration_policy_fingerprint_sha256
        ),
        "result_fingerprint_sha256": report.result_fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": (
            report.opening_snapshot_fingerprint_sha256
        ),
        "final_account_fingerprint_sha256": report.final_account_fingerprint_sha256,
        "final_book_fingerprint_sha256": report.final_book_fingerprint_sha256,
        "final_ledger_fingerprint_sha256": report.final_ledger_fingerprint_sha256,
        "evaluation_fingerprint_sha256": report.evaluation_fingerprint_sha256,
        "processed_barrier_count": report.processed_barrier_count,
        "decision_cycle_count": report.decision_cycle_count,
        "equity_point_count": report.equity_point_count,
        "paper_entry_count": report.paper_entry_count,
        "closed_lot_count": report.closed_lot_count,
        "open_lot_count": report.open_lot_count,
        "reserved_reservation_count": report.reserved_reservation_count,
        "committed_reservation_count": report.committed_reservation_count,
        "released_reservation_count": report.released_reservation_count,
        "final_equity": report.final_equity,
        "final_open_risk_amount": report.final_open_risk_amount,
        "final_virtual_gross_exposure_amount": (
            report.final_virtual_gross_exposure_amount
        ),
        "single_master_capital_verified": report.single_master_capital_verified,
        "full_barrier_chain_verified": report.full_barrier_chain_verified,
        "reservation_lifecycle_verified": report.reservation_lifecycle_verified,
        "virtual_lot_accounting_verified": report.virtual_lot_accounting_verified,
        "evaluation_accounting_verified": report.evaluation_accounting_verified,
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalReplayAuditReport:
    audit_id: str
    status: MasterHistoricalReplayAuditStatus
    master_portfolio_id: str
    plan_id: str
    timeline_id: str
    result_id: str
    sealed_at: datetime
    plan_fingerprint_sha256: str
    timeline_fingerprint_sha256: str
    allocation_policy_fingerprint_sha256: str
    gate_policy_fingerprint_sha256: str
    arbitration_policy_fingerprint_sha256: str
    result_fingerprint_sha256: str
    opening_snapshot_fingerprint_sha256: str
    final_account_fingerprint_sha256: str
    final_book_fingerprint_sha256: str
    final_ledger_fingerprint_sha256: str
    evaluation_fingerprint_sha256: str
    processed_barrier_count: int
    decision_cycle_count: int
    equity_point_count: int
    paper_entry_count: int
    closed_lot_count: int
    open_lot_count: int
    reserved_reservation_count: int
    committed_reservation_count: int
    released_reservation_count: int
    final_equity: Decimal
    final_open_risk_amount: Decimal
    final_virtual_gross_exposure_amount: Decimal
    single_master_capital_verified: bool
    full_barrier_chain_verified: bool
    reservation_lifecycle_verified: bool
    virtual_lot_accounting_verified: bool
    evaluation_accounting_verified: bool
    fingerprint_sha256: str
    audit_only: bool = field(default=True, init=False)
    mutation_applied: bool = field(default=False, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    broker_called: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in (
            "audit_id",
            "master_portfolio_id",
            "plan_id",
            "timeline_id",
            "result_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(self, "sealed_at", _utc(self.sealed_at, field_name="sealed_at"))
        for field_name in (
            "plan_fingerprint_sha256",
            "timeline_fingerprint_sha256",
            "allocation_policy_fingerprint_sha256",
            "gate_policy_fingerprint_sha256",
            "arbitration_policy_fingerprint_sha256",
            "result_fingerprint_sha256",
            "opening_snapshot_fingerprint_sha256",
            "final_account_fingerprint_sha256",
            "final_book_fingerprint_sha256",
            "final_ledger_fingerprint_sha256",
            "evaluation_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        if self.status is not MasterHistoricalReplayAuditStatus.VERIFIED:
            raise ValueError("Master historical replay audit status must be VERIFIED")
        for field_name in (
            "processed_barrier_count",
            "decision_cycle_count",
            "equity_point_count",
            "paper_entry_count",
            "closed_lot_count",
            "open_lot_count",
            "reserved_reservation_count",
            "committed_reservation_count",
            "released_reservation_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be an integer >= 0")
        if self.paper_entry_count != self.closed_lot_count + self.open_lot_count:
            raise ValueError("audit PAPER entry count must equal closed + open lots")
        if self.reserved_reservation_count != 0:
            raise ValueError("sealed historical replay cannot retain RESERVED reservations")
        if self.committed_reservation_count != self.open_lot_count:
            raise ValueError("sealed committed reservations must equal open virtual lots")
        for field_name in (
            "single_master_capital_verified",
            "full_barrier_chain_verified",
            "reservation_lifecycle_verified",
            "virtual_lot_accounting_verified",
            "evaluation_accounting_verified",
        ):
            if getattr(self, field_name) is not True:
                raise ValueError(f"{field_name} must be true for VERIFIED audit")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical replay audit schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        _assert_digest(
            normalized,
            master_historical_replay_audit_payload(self),
            label="Master historical replay audit",
        )
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_historical_replay_audit_payload(self)


def master_historical_replay_closure_payload(
    seal: MasterHistoricalReplayClosureSeal,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-replay-closure.v1",
        "schema_version": seal.schema_version,
        "closure_id": seal.closure_id,
        "status": seal.status,
        "master_portfolio_id": seal.master_portfolio_id,
        "plan_id": seal.plan_id,
        "timeline_id": seal.timeline_id,
        "result_id": seal.result_id,
        "sealed_at": seal.sealed_at,
        "audit_fingerprint_sha256": seal.audit_fingerprint_sha256,
        "result_fingerprint_sha256": seal.result_fingerprint_sha256,
        "final_account_fingerprint_sha256": seal.final_account_fingerprint_sha256,
        "final_book_fingerprint_sha256": seal.final_book_fingerprint_sha256,
        "final_ledger_fingerprint_sha256": seal.final_ledger_fingerprint_sha256,
        "evaluation_fingerprint_sha256": seal.evaluation_fingerprint_sha256,
    }


@dataclass(frozen=True, slots=True)
class MasterHistoricalReplayClosureSeal:
    closure_id: str
    status: MasterHistoricalReplayClosureStatus
    master_portfolio_id: str
    plan_id: str
    timeline_id: str
    result_id: str
    sealed_at: datetime
    audit_fingerprint_sha256: str
    result_fingerprint_sha256: str
    final_account_fingerprint_sha256: str
    final_book_fingerprint_sha256: str
    final_ledger_fingerprint_sha256: str
    evaluation_fingerprint_sha256: str
    closure_fingerprint_sha256: str
    audit_only: bool = field(default=True, init=False)
    mutation_applied: bool = field(default=False, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    broker_called: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in (
            "closure_id",
            "master_portfolio_id",
            "plan_id",
            "timeline_id",
            "result_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(self, "sealed_at", _utc(self.sealed_at, field_name="sealed_at"))
        if self.status is not MasterHistoricalReplayClosureStatus.SEALED:
            raise ValueError("Master historical replay closure status must be SEALED")
        for field_name in (
            "audit_fingerprint_sha256",
            "result_fingerprint_sha256",
            "final_account_fingerprint_sha256",
            "final_book_fingerprint_sha256",
            "final_ledger_fingerprint_sha256",
            "evaluation_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical replay closure schema_version")
        normalized = _sha256(
            self.closure_fingerprint_sha256,
            field_name="closure_fingerprint_sha256",
        )
        _assert_digest(
            normalized,
            master_historical_replay_closure_payload(self),
            label="Master historical replay closure",
        )
        object.__setattr__(self, "closure_fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_historical_replay_closure_payload(self)


def _verify_static_integrity(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    allocation_policy: MasterAllocationPolicy,
    gate_policy: MasterRiskGatePolicy,
    arbitration_policy: MasterArbitrationPolicy,
    result: MasterHistoricalCoordinatedReplayResult,
) -> None:
    _assert_equal(
        plan.fingerprint_sha256,
        master_historical_replay_plan_fingerprint(plan),
        message="historical closure plan fingerprint integrity failure",
    )
    _assert_equal(
        timeline.fingerprint_sha256,
        master_historical_replay_timeline_fingerprint(timeline),
        message="historical closure timeline fingerprint integrity failure",
    )
    _assert_equal(
        allocation_policy.fingerprint_sha256,
        _allocation_fingerprint(allocation_policy),
        message="historical closure allocation policy fingerprint integrity failure",
    )
    _assert_equal(
        gate_policy.fingerprint_sha256,
        _gate_fingerprint(gate_policy),
        message="historical closure gate policy fingerprint integrity failure",
    )
    _assert_equal(
        arbitration_policy.fingerprint_sha256,
        _arbitration_fingerprint(arbitration_policy),
        message="historical closure arbitration policy fingerprint integrity failure",
    )
    _assert_digest(
        result.fingerprint_sha256,
        master_historical_replay_result_payload(result),
        label="Master historical replay result",
    )
    expected_master = plan.master_portfolio_id
    for value in (
        timeline.master_portfolio_id,
        allocation_policy.master_portfolio_id,
        gate_policy.master_portfolio_id,
        arbitration_policy.master_portfolio_id,
        result.master_portfolio_id,
    ):
        _assert_equal(
            value,
            expected_master,
            message="historical closure spans multiple Master Portfolios",
        )
    _assert_equal(result.plan_id, plan.plan_id, message="historical closure plan_id mismatch")
    _assert_equal(
        result.timeline_id,
        timeline.timeline_id,
        message="historical closure timeline_id mismatch",
    )
    _assert_equal(
        timeline.plan_id,
        plan.plan_id,
        message="historical closure timeline does not bind plan",
    )
    bindings = (
        (timeline.plan_fingerprint_sha256, plan.fingerprint_sha256),
        (result.plan_fingerprint_sha256, plan.fingerprint_sha256),
        (result.timeline_fingerprint_sha256, timeline.fingerprint_sha256),
        (result.allocation_policy_fingerprint_sha256, allocation_policy.fingerprint_sha256),
        (result.gate_policy_fingerprint_sha256, gate_policy.fingerprint_sha256),
        (result.arbitration_policy_fingerprint_sha256, arbitration_policy.fingerprint_sha256),
        (plan.allocation_policy_fingerprint_sha256, allocation_policy.fingerprint_sha256),
        (plan.gate_policy_fingerprint_sha256, gate_policy.fingerprint_sha256),
        (plan.arbitration_policy_fingerprint_sha256, arbitration_policy.fingerprint_sha256),
        (gate_policy.allocation_policy_fingerprint_sha256, allocation_policy.fingerprint_sha256),
        (
            arbitration_policy.allocation_policy_fingerprint_sha256,
            allocation_policy.fingerprint_sha256,
        ),
    )
    if any(actual != expected for actual, expected in bindings):
        raise ValueError("historical closure static fingerprint provenance mismatch")
    plan_systems = tuple(crew.system_id for crew in plan.crews)
    timeline_systems = timeline.crew_system_ids
    allocation_systems = tuple(member.system_id for member in allocation_policy.members)
    if not (plan_systems == timeline_systems == allocation_systems):
        raise ValueError("historical closure crew membership mismatch")
    if result.status is not MasterHistoricalCoordinatedReplayStatus.COMPLETED:
        raise ValueError("historical closure requires COMPLETED replay")


def _verify_snapshot(snapshot: MasterPortfolioSnapshot, *, label: str) -> None:
    _assert_equal(
        snapshot.fingerprint_sha256,
        _snapshot_fingerprint(snapshot),
        message=f"{label} fingerprint integrity failure",
    )


def _verify_nested_integrity(result: MasterHistoricalCoordinatedReplayResult) -> None:
    _verify_snapshot(result.opening_snapshot, label="historical opening snapshot")
    _assert_digest(
        result.evaluation.fingerprint_sha256,
        master_historical_evaluation_payload(result.evaluation),
        label="Master historical evaluation",
    )
    for crew in result.evaluation.crew_evaluations:
        _assert_digest(
            crew.fingerprint_sha256,
            master_historical_crew_evaluation_payload(crew),
            label="Master historical crew evaluation",
        )
    for point in result.equity_curve:
        _assert_digest(
            point.fingerprint_sha256,
            master_historical_equity_point_payload(point),
            label="Master historical equity point",
        )
    for lifecycle in result.lifecycle_results:
        _assert_digest(
            lifecycle.fingerprint_sha256,
            master_historical_lifecycle_result_payload(lifecycle),
            label="Master historical lifecycle result",
        )
    for cycle in result.decision_cycles:
        _assert_digest(
            cycle.fingerprint_sha256,
            master_historical_decision_cycle_payload(cycle),
            label="Master historical decision cycle",
        )
        _assert_digest(
            cycle.barrier_input.fingerprint_sha256,
            master_historical_barrier_input_payload(cycle.barrier_input),
            label="Master historical barrier input",
        )
        _verify_snapshot(cycle.portfolio_before, label="historical cycle portfolio_before")
        _verify_snapshot(cycle.portfolio_after, label="historical cycle portfolio_after")
        _assert_equal(
            cycle.decision_barrier.fingerprint_sha256,
            master_historical_decision_barrier_fingerprint(cycle.decision_barrier),
            message="historical decision barrier fingerprint integrity failure",
        )
        _assert_equal(
            cycle.reservation_arbitration.fingerprint_sha256,
            master_historical_reservation_arbitration_fingerprint(
                cycle.reservation_arbitration
            ),
            message="historical reservation/arbitration fingerprint integrity failure",
        )
        _assert_digest(
            cycle.paper_execution.fingerprint_sha256,
            master_historical_paper_execution_payload(cycle.paper_execution),
            label="Master historical PAPER execution",
        )
        _assert_digest(
            cycle.lot_registration.fingerprint_sha256,
            master_historical_virtual_lot_registration_payload(cycle.lot_registration),
            label="Master historical virtual lot registration",
        )
    _assert_digest(
        result.final_book.fingerprint_sha256,
        master_historical_virtual_lot_book_snapshot_payload(result.final_book),
        label="Master historical final virtual lot book",
    )
    _assert_equal(
        result.final_ledger.fingerprint_sha256,
        reservation_ledger_snapshot_fingerprint(result.final_ledger),
        message="historical final reservation ledger fingerprint integrity failure",
    )


def _verify_barrier_chain(
    *,
    timeline: MasterHistoricalReplayTimeline,
    allocation_policy: MasterAllocationPolicy,
    result: MasterHistoricalCoordinatedReplayResult,
) -> None:
    if result.processed_barrier_count != len(timeline.barriers):
        raise ValueError("historical closure did not process every timeline barrier")
    if len(result.lifecycle_results) != len(timeline.barriers):
        raise ValueError("historical closure lifecycle count mismatch")
    if len(result.equity_curve) != len(timeline.barriers):
        raise ValueError("historical closure equity curve count mismatch")
    expected_cycle_sequences = tuple(
        barrier.sequence
        for barrier in timeline.barriers
        if barrier.phase is MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE
        and barrier.decision_eligible
    )
    actual_cycle_sequences = tuple(cycle.barrier_sequence for cycle in result.decision_cycles)
    if actual_cycle_sequences != expected_cycle_sequences:
        raise ValueError("historical closure decision cycles do not cover eligible CLOSE barriers")

    empty_ledger = MasterReservationLedger(
        policy=allocation_policy,
        opening_snapshot=result.opening_snapshot,
    ).snapshot()
    expected_ledger = empty_ledger.fingerprint_sha256
    cycle_map = {cycle.barrier_sequence: cycle for cycle in result.decision_cycles}

    for index, barrier in enumerate(timeline.barriers):
        lifecycle = result.lifecycle_results[index]
        point = result.equity_curve[index]
        if (
            lifecycle.barrier_sequence != barrier.sequence
            or lifecycle.candle_index != barrier.candle_index
            or lifecycle.phase is not barrier.phase
            or lifecycle.observed_at != barrier.observed_at
            or lifecycle.barrier_fingerprint_sha256 != barrier.fingerprint_sha256
        ):
            raise ValueError("historical closure lifecycle does not bind exact timeline barrier")
        if lifecycle.plan_fingerprint_sha256 != result.plan_fingerprint_sha256:
            raise ValueError("historical closure lifecycle plan provenance mismatch")
        if lifecycle.timeline_fingerprint_sha256 != result.timeline_fingerprint_sha256:
            raise ValueError("historical closure lifecycle timeline provenance mismatch")
        if lifecycle.book_id != result.book_id:
            raise ValueError("historical closure lifecycle book_id mismatch")
        if lifecycle.ledger_before_fingerprint_sha256 != expected_ledger:
            raise ValueError("historical closure ledger chain is discontinuous")
        expected_ledger = lifecycle.ledger_after_fingerprint_sha256

        cycle = cycle_map.get(barrier.sequence)
        if cycle is None:
            expected_account = lifecycle.account_after_fingerprint_sha256
        else:
            if cycle.barrier_input.barrier_fingerprint_sha256 != barrier.fingerprint_sha256:
                raise ValueError("historical closure cycle input barrier provenance mismatch")
            if cycle.decision_barrier.barrier_fingerprint_sha256 != barrier.fingerprint_sha256:
                raise ValueError("historical closure decision barrier timeline provenance mismatch")
            if cycle.reservation_arbitration.initial_ledger_fingerprint_sha256 != expected_ledger:
                raise ValueError("historical closure reservation stage ledger input mismatch")
            if cycle.reservation_arbitration.opening_snapshot_fingerprint_sha256 != (
                result.opening_snapshot.fingerprint_sha256
            ):
                raise ValueError("historical closure arbitration opening snapshot mismatch")
            if cycle.reservation_arbitration.portfolio_snapshot_fingerprint_sha256 != (
                cycle.portfolio_before.fingerprint_sha256
            ):
                raise ValueError("historical closure arbitration current snapshot mismatch")
            if cycle.paper_execution.initial_ledger_fingerprint_sha256 != (
                cycle.reservation_arbitration.final_ledger_fingerprint_sha256
            ):
                raise ValueError("historical closure PAPER ledger input mismatch")
            if cycle.paper_execution.reservation_arbitration_fingerprint_sha256 != (
                cycle.reservation_arbitration.fingerprint_sha256
            ):
                raise ValueError("historical closure PAPER arbitration provenance mismatch")
            if cycle.lot_registration.execution_result_fingerprint_sha256 != (
                cycle.paper_execution.fingerprint_sha256
            ):
                raise ValueError("historical closure registration PAPER provenance mismatch")
            if cycle.lot_registration.decision_barrier_fingerprint_sha256 != (
                cycle.decision_barrier.fingerprint_sha256
            ):
                raise ValueError("historical closure registration decision provenance mismatch")
            if cycle.lot_registration.ledger_fingerprint_sha256 != (
                cycle.paper_execution.final_ledger_fingerprint_sha256
            ):
                raise ValueError("historical closure registration ledger mismatch")
            expected_ledger = cycle.lot_registration.ledger_fingerprint_sha256
            expected_account = cycle.paper_execution.account_after.fingerprint_sha256
            if cycle.portfolio_before.observed_at != barrier.observed_at:
                raise ValueError("historical closure cycle portfolio_before time mismatch")
            if cycle.portfolio_after.observed_at != barrier.observed_at:
                raise ValueError("historical closure cycle portfolio_after time mismatch")

        if point.barrier_sequence != barrier.sequence or point.observed_at != barrier.observed_at:
            raise ValueError("historical closure equity point does not bind timeline barrier")
        if point.account_fingerprint_sha256 != expected_account:
            raise ValueError("historical closure equity point account provenance mismatch")

    final_cycle = cycle_map.get(timeline.barriers[-1].sequence)
    expected_final_book = (
        final_cycle.lot_registration.book_fingerprint_sha256
        if final_cycle is not None
        else result.lifecycle_results[-1].book_after_fingerprint_sha256
    )
    if expected_final_book != result.final_book.fingerprint_sha256:
        raise ValueError("historical closure final virtual lot book breaks final barrier")
    if expected_ledger != result.final_ledger.fingerprint_sha256:
        raise ValueError("historical closure final reservation ledger breaks chain")
    if result.final_book.last_processed_barrier_sequence != len(timeline.barriers):
        raise ValueError("historical closure final book did not reach final barrier")
    if result.final_book.observed_at != timeline.barriers[-1].observed_at:
        raise ValueError("historical closure final book time mismatch")
    if (
        result.final_account_fingerprint_sha256
        != result.equity_curve[-1].account_fingerprint_sha256
    ):
        raise ValueError("historical closure final account fingerprint mismatch")


def _verify_reservations_and_lots(result: MasterHistoricalCoordinatedReplayResult) -> None:
    reserved = tuple(
        item
        for item in result.final_ledger.reservations
        if item.status is ReservationRecordStatus.RESERVED
    )
    committed = tuple(
        item
        for item in result.final_ledger.reservations
        if item.status is ReservationRecordStatus.COMMITTED
    )
    if reserved:
        raise ValueError("historical closure found orphan RESERVED reservation")
    open_by_reservation = {lot.reservation_id: lot for lot in result.final_book.open_lots}
    committed_by_id = {item.reservation_id: item for item in committed}
    if set(open_by_reservation) != set(committed_by_id):
        raise ValueError("historical closure committed reservations do not match open virtual lots")
    for reservation_id, lot in open_by_reservation.items():
        reservation = committed_by_id[reservation_id]
        if reservation.request.system_id != lot.source_system_id:
            raise ValueError("historical closure open lot reservation system mismatch")
        if reservation.request.request_ref != lot.proposal_id:
            raise ValueError("historical closure open lot reservation proposal mismatch")
        if reservation.request.open_risk_amount != lot.reserved_open_risk_amount:
            raise ValueError("historical closure open lot reservation risk mismatch")
        if reservation.request.gross_exposure_amount != lot.reserved_gross_exposure_amount:
            raise ValueError("historical closure open lot reservation gross mismatch")
        if lot.status is not MasterHistoricalVirtualLotStatus.OPEN:
            raise ValueError("historical closure final open lot has non-OPEN status")
    if any(
        lot.status is not MasterHistoricalVirtualLotStatus.CLOSED
        for lot in result.final_book.closed_lots
    ):
        raise ValueError("historical closure final closed lot has non-CLOSED status")


def _verify_single_capital(
    *,
    plan: MasterHistoricalReplayPlan,
    result: MasterHistoricalCoordinatedReplayResult,
) -> None:
    if not plan.single_master_capital or plan.sums_branch_equities:
        raise ValueError("historical closure plan violates single Master capital invariant")
    if (
        not result.single_master_capital
        or result.sums_branch_equities
        or result.uses_branch_brokers
    ):
        raise ValueError("historical closure result violates single Master capital invariant")
    if result.opening_snapshot.master_capital.equity != plan.master_initial_capital:
        raise ValueError("historical closure opening equity is not Master initial capital")
    if result.opening_snapshot.master_capital.cash_balance != plan.master_initial_capital:
        raise ValueError("historical closure opening cash is not Master initial capital")
    if result.final_ledger.master_capital_capacity_amount != plan.master_initial_capital:
        raise ValueError("historical closure ledger capacity is not Master initial capital")
    if result.evaluation.initial_capital != plan.master_initial_capital:
        raise ValueError("historical closure evaluation initial capital mismatch")
    if any(crew.branch_equity_summable for crew in plan.crews):
        raise ValueError("historical closure source branch equity became summable")


def _verify_evaluation(result: MasterHistoricalCoordinatedReplayResult) -> None:
    evaluation = result.evaluation
    final_book = result.final_book
    final_point = result.equity_curve[-1]
    if evaluation.final_equity != final_point.equity:
        raise ValueError("historical closure final equity mismatch")
    if evaluation.closed_lot_count != len(final_book.closed_lots):
        raise ValueError("historical closure closed lot evaluation count mismatch")
    if evaluation.open_lot_count != len(final_book.open_lots):
        raise ValueError("historical closure open lot evaluation count mismatch")
    if evaluation.paper_entry_count != len(final_book.closed_lots) + len(final_book.open_lots):
        raise ValueError("historical closure PAPER entry accounting mismatch")
    if evaluation.final_open_risk_amount != final_book.committed_open_risk_amount:
        raise ValueError("historical closure final open risk mismatch")
    if evaluation.final_virtual_gross_exposure_amount != (
        final_book.virtual_gross_exposure_amount
    ):
        raise ValueError("historical closure final virtual gross exposure mismatch")
    if evaluation.closed_lot_realized_net_pnl != final_book.realized_virtual_pnl_net:
        raise ValueError("historical closure realized virtual PnL mismatch")
    expected_fees = sum(
        (lot.entry_fee for lot in final_book.open_lots + final_book.closed_lots),
        ZERO,
    ) + sum(
        (lot.exit_fee or ZERO for lot in final_book.closed_lots),
        ZERO,
    )
    if evaluation.fees_paid != expected_fees:
        raise ValueError("historical closure fee accounting mismatch")
    if evaluation.decision_cycle_count != len(result.decision_cycles):
        raise ValueError("historical closure decision cycle evaluation count mismatch")


def _verify_authority_boundaries(result: MasterHistoricalCoordinatedReplayResult) -> None:
    forbidden_true = (
        result.risk_authority,
        result.admission_authority,
        result.live_authority,
        result.auto_execute_live,
        result.evaluation.risk_authority,
        result.evaluation.admission_authority,
        result.evaluation.live_authority,
    )
    if any(forbidden_true):
        raise ValueError("historical closure detected forbidden replay authority")
    for cycle in result.decision_cycles:
        if any(
            (
                cycle.risk_authority,
                cycle.admission_authority,
                cycle.live_authority,
                cycle.barrier_input.risk_authority,
                cycle.barrier_input.admission_authority,
                cycle.barrier_input.broker_authority,
                cycle.barrier_input.live_authority,
                cycle.decision_barrier.risk_authority,
                cycle.decision_barrier.admission_authority,
                cycle.decision_barrier.broker_authority,
                cycle.decision_barrier.live_authority,
                cycle.reservation_arbitration.risk_authority,
                cycle.reservation_arbitration.admission_authority,
                cycle.reservation_arbitration.live_authority,
                cycle.paper_execution.risk_authority,
                cycle.paper_execution.admission_authority,
                cycle.paper_execution.live_authority,
                cycle.lot_registration.risk_authority,
                cycle.lot_registration.admission_authority,
                cycle.lot_registration.live_authority,
            )
        ):
            raise ValueError("historical closure detected forbidden decision-cycle authority")
    for lifecycle in result.lifecycle_results:
        if lifecycle.risk_authority or lifecycle.admission_authority or lifecycle.live_authority:
            raise ValueError("historical closure detected forbidden lifecycle authority")


def audit_master_historical_coordinated_replay(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    allocation_policy: MasterAllocationPolicy,
    gate_policy: MasterRiskGatePolicy,
    arbitration_policy: MasterArbitrationPolicy,
    result: MasterHistoricalCoordinatedReplayResult,
) -> MasterHistoricalReplayAuditReport:
    """Verify one completed Step 7 replay without mutating any supplied state."""

    _verify_static_integrity(
        plan=plan,
        timeline=timeline,
        allocation_policy=allocation_policy,
        gate_policy=gate_policy,
        arbitration_policy=arbitration_policy,
        result=result,
    )
    _verify_nested_integrity(result)
    _verify_barrier_chain(
        timeline=timeline,
        allocation_policy=allocation_policy,
        result=result,
    )
    _verify_reservations_and_lots(result)
    _verify_single_capital(plan=plan, result=result)
    _verify_evaluation(result)
    _verify_authority_boundaries(result)

    final_ledger = result.final_ledger
    reserved_count = sum(
        item.status is ReservationRecordStatus.RESERVED for item in final_ledger.reservations
    )
    committed_count = sum(
        item.status is ReservationRecordStatus.COMMITTED for item in final_ledger.reservations
    )
    released_count = sum(
        item.status is ReservationRecordStatus.RELEASED for item in final_ledger.reservations
    )
    sealed_at = timeline.barriers[-1].observed_at
    audit_id = "master-historical-audit:" + stable_digest(
        {
            "schema": "money-heist.master-historical-replay-audit-id.v1",
            "plan_fingerprint_sha256": plan.fingerprint_sha256,
            "timeline_fingerprint_sha256": timeline.fingerprint_sha256,
            "result_fingerprint_sha256": result.fingerprint_sha256,
        }
    )
    body = {
        "schema": "money-heist.master-historical-replay-audit.v1",
        "schema_version": "1.0",
        "audit_id": audit_id,
        "status": MasterHistoricalReplayAuditStatus.VERIFIED,
        "master_portfolio_id": plan.master_portfolio_id,
        "plan_id": plan.plan_id,
        "timeline_id": timeline.timeline_id,
        "result_id": result.result_id,
        "sealed_at": sealed_at,
        "plan_fingerprint_sha256": plan.fingerprint_sha256,
        "timeline_fingerprint_sha256": timeline.fingerprint_sha256,
        "allocation_policy_fingerprint_sha256": allocation_policy.fingerprint_sha256,
        "gate_policy_fingerprint_sha256": gate_policy.fingerprint_sha256,
        "arbitration_policy_fingerprint_sha256": arbitration_policy.fingerprint_sha256,
        "result_fingerprint_sha256": result.fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": result.opening_snapshot.fingerprint_sha256,
        "final_account_fingerprint_sha256": result.final_account_fingerprint_sha256,
        "final_book_fingerprint_sha256": result.final_book.fingerprint_sha256,
        "final_ledger_fingerprint_sha256": result.final_ledger.fingerprint_sha256,
        "evaluation_fingerprint_sha256": result.evaluation.fingerprint_sha256,
        "processed_barrier_count": result.processed_barrier_count,
        "decision_cycle_count": len(result.decision_cycles),
        "equity_point_count": len(result.equity_curve),
        "paper_entry_count": result.evaluation.paper_entry_count,
        "closed_lot_count": len(result.final_book.closed_lots),
        "open_lot_count": len(result.final_book.open_lots),
        "reserved_reservation_count": reserved_count,
        "committed_reservation_count": committed_count,
        "released_reservation_count": released_count,
        "final_equity": result.evaluation.final_equity,
        "final_open_risk_amount": result.evaluation.final_open_risk_amount,
        "final_virtual_gross_exposure_amount": (
            result.evaluation.final_virtual_gross_exposure_amount
        ),
        "single_master_capital_verified": True,
        "full_barrier_chain_verified": True,
        "reservation_lifecycle_verified": True,
        "virtual_lot_accounting_verified": True,
        "evaluation_accounting_verified": True,
    }
    return MasterHistoricalReplayAuditReport(
        audit_id=audit_id,
        status=MasterHistoricalReplayAuditStatus.VERIFIED,
        master_portfolio_id=plan.master_portfolio_id,
        plan_id=plan.plan_id,
        timeline_id=timeline.timeline_id,
        result_id=result.result_id,
        sealed_at=sealed_at,
        plan_fingerprint_sha256=plan.fingerprint_sha256,
        timeline_fingerprint_sha256=timeline.fingerprint_sha256,
        allocation_policy_fingerprint_sha256=allocation_policy.fingerprint_sha256,
        gate_policy_fingerprint_sha256=gate_policy.fingerprint_sha256,
        arbitration_policy_fingerprint_sha256=arbitration_policy.fingerprint_sha256,
        result_fingerprint_sha256=result.fingerprint_sha256,
        opening_snapshot_fingerprint_sha256=result.opening_snapshot.fingerprint_sha256,
        final_account_fingerprint_sha256=result.final_account_fingerprint_sha256,
        final_book_fingerprint_sha256=result.final_book.fingerprint_sha256,
        final_ledger_fingerprint_sha256=result.final_ledger.fingerprint_sha256,
        evaluation_fingerprint_sha256=result.evaluation.fingerprint_sha256,
        processed_barrier_count=result.processed_barrier_count,
        decision_cycle_count=len(result.decision_cycles),
        equity_point_count=len(result.equity_curve),
        paper_entry_count=result.evaluation.paper_entry_count,
        closed_lot_count=len(result.final_book.closed_lots),
        open_lot_count=len(result.final_book.open_lots),
        reserved_reservation_count=reserved_count,
        committed_reservation_count=committed_count,
        released_reservation_count=released_count,
        final_equity=result.evaluation.final_equity,
        final_open_risk_amount=result.evaluation.final_open_risk_amount,
        final_virtual_gross_exposure_amount=(
            result.evaluation.final_virtual_gross_exposure_amount
        ),
        single_master_capital_verified=True,
        full_barrier_chain_verified=True,
        reservation_lifecycle_verified=True,
        virtual_lot_accounting_verified=True,
        evaluation_accounting_verified=True,
        fingerprint_sha256=stable_digest(body),
    )


def seal_master_historical_coordinated_replay(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    allocation_policy: MasterAllocationPolicy,
    gate_policy: MasterRiskGatePolicy,
    arbitration_policy: MasterArbitrationPolicy,
    result: MasterHistoricalCoordinatedReplayResult,
) -> MasterHistoricalReplayClosureSeal:
    """Build a deterministic read-only closure seal for one fully audited replay."""

    audit = audit_master_historical_coordinated_replay(
        plan=plan,
        timeline=timeline,
        allocation_policy=allocation_policy,
        gate_policy=gate_policy,
        arbitration_policy=arbitration_policy,
        result=result,
    )
    closure_id = "master-historical-closure:" + stable_digest(
        {
            "schema": "money-heist.master-historical-replay-closure-id.v1",
            "audit_fingerprint_sha256": audit.fingerprint_sha256,
            "result_fingerprint_sha256": result.fingerprint_sha256,
        }
    )
    body = {
        "schema": "money-heist.master-historical-replay-closure.v1",
        "schema_version": "1.0",
        "closure_id": closure_id,
        "status": MasterHistoricalReplayClosureStatus.SEALED,
        "master_portfolio_id": plan.master_portfolio_id,
        "plan_id": plan.plan_id,
        "timeline_id": timeline.timeline_id,
        "result_id": result.result_id,
        "sealed_at": audit.sealed_at,
        "audit_fingerprint_sha256": audit.fingerprint_sha256,
        "result_fingerprint_sha256": result.fingerprint_sha256,
        "final_account_fingerprint_sha256": result.final_account_fingerprint_sha256,
        "final_book_fingerprint_sha256": result.final_book.fingerprint_sha256,
        "final_ledger_fingerprint_sha256": result.final_ledger.fingerprint_sha256,
        "evaluation_fingerprint_sha256": result.evaluation.fingerprint_sha256,
    }
    return MasterHistoricalReplayClosureSeal(
        closure_id=closure_id,
        status=MasterHistoricalReplayClosureStatus.SEALED,
        master_portfolio_id=plan.master_portfolio_id,
        plan_id=plan.plan_id,
        timeline_id=timeline.timeline_id,
        result_id=result.result_id,
        sealed_at=audit.sealed_at,
        audit_fingerprint_sha256=audit.fingerprint_sha256,
        result_fingerprint_sha256=result.fingerprint_sha256,
        final_account_fingerprint_sha256=result.final_account_fingerprint_sha256,
        final_book_fingerprint_sha256=result.final_book.fingerprint_sha256,
        final_ledger_fingerprint_sha256=result.final_ledger.fingerprint_sha256,
        evaluation_fingerprint_sha256=result.evaluation.fingerprint_sha256,
        closure_fingerprint_sha256=stable_digest(body),
    )


__all__ = [
    "MasterHistoricalReplayAuditReport",
    "MasterHistoricalReplayAuditStatus",
    "MasterHistoricalReplayClosureSeal",
    "MasterHistoricalReplayClosureStatus",
    "audit_master_historical_coordinated_replay",
    "master_historical_replay_audit_payload",
    "master_historical_replay_closure_payload",
    "seal_master_historical_coordinated_replay",
]
