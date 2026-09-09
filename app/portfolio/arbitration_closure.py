from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .allocation import MasterAllocationPolicy
from .arbitration import (
    MasterArbitrationBatch,
    MasterArbitrationOrderStrategy,
    MasterArbitrationPolicy,
)
from .arbitration_sequential import MasterSequentialArbitrationResult
from .models import MasterPortfolioSnapshot
from .reservation import (
    CrewReservationUsage,
    PortfolioReservation,
    ReservationLedgerSnapshot,
    ReservationRecordStatus,
)
from .risk_gate import (
    MasterRiskGateDecisionStatus,
    MasterRiskGatePolicy,
    MasterRiskGateReasonCode,
)


class MasterArbitrationClosureStatus(StrEnum):
    SEALED = "SEALED"


def _required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _sha256(value: str, *, field_name: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return normalized


def master_arbitration_closure_payload(
    seal: MasterArbitrationClosureSeal,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-arbitration-closure.v1",
        "schema_version": seal.schema_version,
        "closure_id": seal.closure_id,
        "master_portfolio_id": seal.master_portfolio_id,
        "run_id": seal.run_id,
        "batch_id": seal.batch_id,
        "status": seal.status,
        "order_strategy": seal.order_strategy,
        "arbitration_policy_id": seal.arbitration_policy_id,
        "arbitration_policy_fingerprint_sha256": (
            seal.arbitration_policy_fingerprint_sha256
        ),
        "allocation_policy_fingerprint_sha256": (
            seal.allocation_policy_fingerprint_sha256
        ),
        "gate_policy_id": seal.gate_policy_id,
        "gate_policy_fingerprint_sha256": seal.gate_policy_fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": seal.opening_snapshot_fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": (
            seal.portfolio_snapshot_fingerprint_sha256
        ),
        "initial_ledger_fingerprint_sha256": seal.initial_ledger_fingerprint_sha256,
        "final_ledger_fingerprint_sha256": seal.final_ledger_fingerprint_sha256,
        "result_fingerprint_sha256": seal.result_fingerprint_sha256,
        "outcome_fingerprints_sha256": seal.outcome_fingerprints_sha256,
        "gate_closure_fingerprints_sha256": seal.gate_closure_fingerprints_sha256,
        "admitted_count": seal.admitted_count,
        "rejected_count": seal.rejected_count,
    }


def master_arbitration_closure_fingerprint(seal: MasterArbitrationClosureSeal) -> str:
    return stable_digest(master_arbitration_closure_payload(seal))


@dataclass(frozen=True, slots=True)
class MasterArbitrationClosureSeal:
    """Immutable audit seal for one completed sequential arbitration run."""

    closure_id: str
    master_portfolio_id: str
    run_id: str
    batch_id: str
    status: MasterArbitrationClosureStatus
    order_strategy: MasterArbitrationOrderStrategy
    arbitration_policy_id: str
    arbitration_policy_fingerprint_sha256: str
    allocation_policy_fingerprint_sha256: str
    gate_policy_id: str
    gate_policy_fingerprint_sha256: str
    opening_snapshot_fingerprint_sha256: str
    portfolio_snapshot_fingerprint_sha256: str
    initial_ledger_fingerprint_sha256: str
    final_ledger_fingerprint_sha256: str
    result_fingerprint_sha256: str
    outcome_fingerprints_sha256: tuple[str, ...]
    gate_closure_fingerprints_sha256: tuple[str, ...]
    admitted_count: int
    rejected_count: int
    closure_fingerprint_sha256: str
    mutation_applied: bool = field(default=False, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    audit_only: bool = field(default=True, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in (
            "closure_id",
            "master_portfolio_id",
            "run_id",
            "batch_id",
            "arbitration_policy_id",
            "gate_policy_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        if self.status is not MasterArbitrationClosureStatus.SEALED:
            raise ValueError("Master arbitration closure status must be SEALED")
        if self.admitted_count < 0 or self.rejected_count < 0:
            raise ValueError("Master arbitration closure counts must be >= 0")
        if self.admitted_count + self.rejected_count != len(self.outcome_fingerprints_sha256):
            raise ValueError("Master arbitration closure counts must match outcome count")
        if len(self.gate_closure_fingerprints_sha256) != len(self.outcome_fingerprints_sha256):
            raise ValueError("every arbitration outcome requires one gate closure fingerprint")
        if not self.outcome_fingerprints_sha256:
            raise ValueError("Master arbitration closure requires at least one outcome")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master arbitration closure schema_version")

        for field_name in (
            "arbitration_policy_fingerprint_sha256",
            "allocation_policy_fingerprint_sha256",
            "gate_policy_fingerprint_sha256",
            "opening_snapshot_fingerprint_sha256",
            "portfolio_snapshot_fingerprint_sha256",
            "initial_ledger_fingerprint_sha256",
            "final_ledger_fingerprint_sha256",
            "result_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "outcome_fingerprints_sha256",
            tuple(
                _sha256(value, field_name="outcome_fingerprints_sha256")
                for value in self.outcome_fingerprints_sha256
            ),
        )
        object.__setattr__(
            self,
            "gate_closure_fingerprints_sha256",
            tuple(
                _sha256(value, field_name="gate_closure_fingerprints_sha256")
                for value in self.gate_closure_fingerprints_sha256
            ),
        )

        normalized = _sha256(
            self.closure_fingerprint_sha256,
            field_name="closure_fingerprint_sha256",
        )
        expected = master_arbitration_closure_fingerprint(self)
        if normalized != expected:
            raise ValueError("Master arbitration closure fingerprint does not match payload")
        object.__setattr__(self, "closure_fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_arbitration_closure_payload(self)


def _reservation_map(snapshot: ReservationLedgerSnapshot) -> dict[str, PortfolioReservation]:
    return {item.reservation_id: item for item in snapshot.reservations}


def _usage_map(snapshot: ReservationLedgerSnapshot) -> dict[str, CrewReservationUsage]:
    return {item.system_id: item for item in snapshot.crew_usage}


def _validate_snapshot_accounting(
    *,
    snapshot: ReservationLedgerSnapshot,
    allocation_policy: MasterAllocationPolicy,
) -> None:
    members = tuple(member.system_id for member in allocation_policy.members)
    if tuple(item.system_id for item in snapshot.crew_usage) != tuple(sorted(members)):
        raise ValueError("ledger crew usage membership does not match allocation policy")

    reserved_capital = sum(
        (
            item.request.capital_amount
            for item in snapshot.reservations
            if item.status is ReservationRecordStatus.RESERVED
        ),
        start=0,
    )
    committed_capital = sum(
        (
            item.request.capital_amount
            for item in snapshot.reservations
            if item.status is ReservationRecordStatus.COMMITTED
        ),
        start=0,
    )
    if snapshot.reserved_capital_amount != reserved_capital:
        raise ValueError("ledger reserved capital does not match reservation records")
    if snapshot.committed_capital_amount != committed_capital:
        raise ValueError("ledger committed capital does not match reservation records")

    usage_map = _usage_map(snapshot)
    for system_id in members:
        records = [
            item for item in snapshot.reservations if item.request.system_id == system_id
        ]
        usage = usage_map[system_id]
        expected = {
            "reserved_capital_amount": sum(
                (
                    item.request.capital_amount
                    for item in records
                    if item.status is ReservationRecordStatus.RESERVED
                ),
                start=0,
            ),
            "committed_capital_amount": sum(
                (
                    item.request.capital_amount
                    for item in records
                    if item.status is ReservationRecordStatus.COMMITTED
                ),
                start=0,
            ),
            "reserved_open_risk_amount": sum(
                (
                    item.request.open_risk_amount
                    for item in records
                    if item.status is ReservationRecordStatus.RESERVED
                ),
                start=0,
            ),
            "committed_open_risk_amount": sum(
                (
                    item.request.open_risk_amount
                    for item in records
                    if item.status is ReservationRecordStatus.COMMITTED
                ),
                start=0,
            ),
            "reserved_gross_exposure_amount": sum(
                (
                    item.request.gross_exposure_amount
                    for item in records
                    if item.status is ReservationRecordStatus.RESERVED
                ),
                start=0,
            ),
            "committed_gross_exposure_amount": sum(
                (
                    item.request.gross_exposure_amount
                    for item in records
                    if item.status is ReservationRecordStatus.COMMITTED
                ),
                start=0,
            ),
        }
        for field_name, expected_value in expected.items():
            if getattr(usage, field_name) != expected_value:
                raise ValueError(f"ledger crew usage {field_name} does not match reservations")


def _validate_context(
    *,
    arbitration_policy: MasterArbitrationPolicy,
    batch: MasterArbitrationBatch,
    allocation_policy: MasterAllocationPolicy,
    gate_policy: MasterRiskGatePolicy,
    opening_snapshot: MasterPortfolioSnapshot,
    portfolio_snapshot: MasterPortfolioSnapshot,
    initial_ledger: ReservationLedgerSnapshot,
    final_ledger: ReservationLedgerSnapshot,
    result: MasterSequentialArbitrationResult,
) -> None:
    master_id = result.master_portfolio_id
    if any(
        item != master_id
        for item in (
            arbitration_policy.master_portfolio_id,
            batch.master_portfolio_id,
            allocation_policy.master_portfolio_id,
            gate_policy.master_portfolio_id,
            opening_snapshot.master_portfolio_id,
            portfolio_snapshot.master_portfolio_id,
            initial_ledger.master_portfolio_id,
            final_ledger.master_portfolio_id,
        )
    ):
        raise ValueError("Master arbitration closure spans multiple Master Portfolios")

    if result.batch_id != batch.batch_id:
        raise ValueError("sequential arbitration result does not bind to supplied batch")
    if result.order_strategy is not batch.order_strategy:
        raise ValueError("sequential arbitration result order strategy does not match batch")
    if batch.arbitration_policy_fingerprint_sha256 != arbitration_policy.fingerprint_sha256:
        raise ValueError("arbitration batch policy provenance mismatch")
    if result.arbitration_policy_fingerprint_sha256 != arbitration_policy.fingerprint_sha256:
        raise ValueError("sequential arbitration result policy provenance mismatch")

    allocation_fingerprint = allocation_policy.fingerprint_sha256
    for value in (
        arbitration_policy.allocation_policy_fingerprint_sha256,
        batch.allocation_policy_fingerprint_sha256,
        gate_policy.allocation_policy_fingerprint_sha256,
        initial_ledger.policy_fingerprint_sha256,
        final_ledger.policy_fingerprint_sha256,
        result.allocation_policy_fingerprint_sha256,
    ):
        if value != allocation_fingerprint:
            raise ValueError("Master arbitration closure allocation provenance mismatch")

    if result.gate_policy_fingerprint_sha256 != gate_policy.fingerprint_sha256:
        raise ValueError("sequential arbitration result gate policy provenance mismatch")
    if result.opening_snapshot_fingerprint_sha256 != opening_snapshot.fingerprint_sha256:
        raise ValueError("sequential arbitration result opening snapshot mismatch")
    if result.portfolio_snapshot_fingerprint_sha256 != portfolio_snapshot.fingerprint_sha256:
        raise ValueError("sequential arbitration result portfolio snapshot mismatch")
    if initial_ledger.opening_snapshot_fingerprint_sha256 != opening_snapshot.fingerprint_sha256:
        raise ValueError("initial ledger opening snapshot provenance mismatch")
    if final_ledger.opening_snapshot_fingerprint_sha256 != opening_snapshot.fingerprint_sha256:
        raise ValueError("final ledger opening snapshot provenance mismatch")
    if batch.source_ledger_fingerprint_sha256 != initial_ledger.fingerprint_sha256:
        raise ValueError("arbitration batch source ledger does not match supplied initial ledger")
    if result.initial_ledger_fingerprint_sha256 != initial_ledger.fingerprint_sha256:
        raise ValueError("sequential arbitration result initial ledger mismatch")
    if result.final_ledger_fingerprint_sha256 != final_ledger.fingerprint_sha256:
        raise ValueError("sequential arbitration result final ledger mismatch")
    if result.evaluated_at > portfolio_snapshot.observed_at:
        raise ValueError("sequential arbitration result postdates portfolio observation")

    _validate_snapshot_accounting(snapshot=initial_ledger, allocation_policy=allocation_policy)
    _validate_snapshot_accounting(snapshot=final_ledger, allocation_policy=allocation_policy)


def _validate_outcome_chain(
    *,
    batch: MasterArbitrationBatch,
    initial_ledger: ReservationLedgerSnapshot,
    final_ledger: ReservationLedgerSnapshot,
    result: MasterSequentialArbitrationResult,
) -> tuple[int, int]:
    if len(batch.entries) != len(result.outcomes):
        raise ValueError("arbitration result outcome count does not match batch")

    initial_map = _reservation_map(initial_ledger)
    final_map = _reservation_map(final_ledger)
    if set(initial_map) != set(final_map):
        raise ValueError("arbitration run cannot add or remove reservation records")

    batch_ids = {entry.reservation_id for entry in batch.entries}
    for reservation_id in set(initial_map) - batch_ids:
        if (
            initial_map[reservation_id].fingerprint_sha256
            != final_map[reservation_id].fingerprint_sha256
        ):
            raise ValueError("arbitration run mutated a reservation outside the batch")

    admitted = 0
    rejected = 0
    for entry, outcome in zip(batch.entries, result.outcomes, strict=True):
        if (
            outcome.rank != entry.rank
            or outcome.system_id != entry.system_id
            or outcome.proposal_id != entry.proposal_id
            or outcome.reservation_id != entry.reservation_id
            or outcome.candidate_fingerprint_sha256 != entry.candidate_fingerprint_sha256
        ):
            raise ValueError("arbitration outcome does not bind to its ordered batch entry")

        initial_record = initial_map.get(entry.reservation_id)
        final_record = final_map.get(entry.reservation_id)
        if initial_record is None or final_record is None:
            raise ValueError("arbitration closure is missing a batch reservation")
        if initial_record.status is not ReservationRecordStatus.RESERVED:
            raise ValueError("every arbitration batch reservation must begin RESERVED")
        if initial_record.fingerprint_sha256 != entry.reservation_fingerprint_sha256:
            raise ValueError("batch reservation fingerprint does not match initial ledger")

        if outcome.decision_status is MasterRiskGateDecisionStatus.ADMIT:
            admitted += 1
            if outcome.decision_reason_codes != (MasterRiskGateReasonCode.ADMITTED,):
                raise ValueError("ADMIT arbitration outcome must carry only ADMITTED reason")
            if (
                final_record.status is not ReservationRecordStatus.COMMITTED
                or final_record.commit_ref != outcome.decision_id
                or final_record.released_at is not None
                or final_record.release_ref is not None
            ):
                raise ValueError("ADMIT arbitration outcome does not match final reservation state")
        elif outcome.decision_status is MasterRiskGateDecisionStatus.REJECT:
            rejected += 1
            if MasterRiskGateReasonCode.ADMITTED in outcome.decision_reason_codes:
                raise ValueError("REJECT arbitration outcome cannot carry ADMITTED reason")
            if (
                final_record.status is not ReservationRecordStatus.RELEASED
                or final_record.release_ref != outcome.decision_id
                or final_record.committed_at is not None
                or final_record.commit_ref is not None
            ):
                raise ValueError(
                    "REJECT arbitration outcome does not match final reservation state"
                )
        else:
            raise ValueError("unsupported arbitration decision status")

    return admitted, rejected


def build_master_arbitration_closure_seal(
    *,
    arbitration_policy: MasterArbitrationPolicy,
    batch: MasterArbitrationBatch,
    allocation_policy: MasterAllocationPolicy,
    gate_policy: MasterRiskGatePolicy,
    opening_snapshot: MasterPortfolioSnapshot,
    portfolio_snapshot: MasterPortfolioSnapshot,
    initial_ledger: ReservationLedgerSnapshot,
    final_ledger: ReservationLedgerSnapshot,
    result: MasterSequentialArbitrationResult,
) -> MasterArbitrationClosureSeal:
    """Seal one already-completed arbitration run without replaying or mutating it."""

    _validate_context(
        arbitration_policy=arbitration_policy,
        batch=batch,
        allocation_policy=allocation_policy,
        gate_policy=gate_policy,
        opening_snapshot=opening_snapshot,
        portfolio_snapshot=portfolio_snapshot,
        initial_ledger=initial_ledger,
        final_ledger=final_ledger,
        result=result,
    )
    admitted_count, rejected_count = _validate_outcome_chain(
        batch=batch,
        initial_ledger=initial_ledger,
        final_ledger=final_ledger,
        result=result,
    )

    outcome_fingerprints = tuple(item.fingerprint_sha256 for item in result.outcomes)
    gate_closure_fingerprints = tuple(
        item.gate_closure_fingerprint_sha256 for item in result.outcomes
    )
    closure_id = "master-arbitration-closure:" + stable_digest(
        {
            "schema": "money-heist.master-arbitration-closure-id.v1",
            "result_fingerprint_sha256": result.fingerprint_sha256,
            "initial_ledger_fingerprint_sha256": initial_ledger.fingerprint_sha256,
            "final_ledger_fingerprint_sha256": final_ledger.fingerprint_sha256,
        }
    )
    payload = {
        "schema": "money-heist.master-arbitration-closure.v1",
        "schema_version": "1.0",
        "closure_id": closure_id,
        "master_portfolio_id": result.master_portfolio_id,
        "run_id": result.run_id,
        "batch_id": result.batch_id,
        "status": MasterArbitrationClosureStatus.SEALED,
        "order_strategy": result.order_strategy,
        "arbitration_policy_id": arbitration_policy.arbitration_policy_id,
        "arbitration_policy_fingerprint_sha256": arbitration_policy.fingerprint_sha256,
        "allocation_policy_fingerprint_sha256": allocation_policy.fingerprint_sha256,
        "gate_policy_id": gate_policy.gate_policy_id,
        "gate_policy_fingerprint_sha256": gate_policy.fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": opening_snapshot.fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": portfolio_snapshot.fingerprint_sha256,
        "initial_ledger_fingerprint_sha256": initial_ledger.fingerprint_sha256,
        "final_ledger_fingerprint_sha256": final_ledger.fingerprint_sha256,
        "result_fingerprint_sha256": result.fingerprint_sha256,
        "outcome_fingerprints_sha256": outcome_fingerprints,
        "gate_closure_fingerprints_sha256": gate_closure_fingerprints,
        "admitted_count": admitted_count,
        "rejected_count": rejected_count,
    }
    return MasterArbitrationClosureSeal(
        closure_id=closure_id,
        master_portfolio_id=result.master_portfolio_id,
        run_id=result.run_id,
        batch_id=result.batch_id,
        status=MasterArbitrationClosureStatus.SEALED,
        order_strategy=result.order_strategy,
        arbitration_policy_id=arbitration_policy.arbitration_policy_id,
        arbitration_policy_fingerprint_sha256=arbitration_policy.fingerprint_sha256,
        allocation_policy_fingerprint_sha256=allocation_policy.fingerprint_sha256,
        gate_policy_id=gate_policy.gate_policy_id,
        gate_policy_fingerprint_sha256=gate_policy.fingerprint_sha256,
        opening_snapshot_fingerprint_sha256=opening_snapshot.fingerprint_sha256,
        portfolio_snapshot_fingerprint_sha256=portfolio_snapshot.fingerprint_sha256,
        initial_ledger_fingerprint_sha256=initial_ledger.fingerprint_sha256,
        final_ledger_fingerprint_sha256=final_ledger.fingerprint_sha256,
        result_fingerprint_sha256=result.fingerprint_sha256,
        outcome_fingerprints_sha256=outcome_fingerprints,
        gate_closure_fingerprints_sha256=gate_closure_fingerprints,
        admitted_count=admitted_count,
        rejected_count=rejected_count,
        closure_fingerprint_sha256=stable_digest(payload),
    )


__all__ = [
    "MasterArbitrationClosureSeal",
    "MasterArbitrationClosureStatus",
    "build_master_arbitration_closure_seal",
    "master_arbitration_closure_fingerprint",
]
