from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .allocation import MasterAllocationPolicy
from .arbitration import (
    MasterArbitrationBatch,
    MasterArbitrationOrderStrategy,
    MasterArbitrationPolicy,
    MasterArbitrationPolicyStatus,
)
from .models import MasterPortfolioSnapshot
from .reservation import MasterReservationLedger, ReservationLedgerSnapshot
from .risk_gate import (
    MasterRiskGateCandidate,
    MasterRiskGateDecisionStatus,
    MasterRiskGatePolicy,
    MasterRiskGateReasonCode,
)
from .risk_gate_admission import apply_master_risk_gate_decision_to_reservation
from .risk_gate_closure import build_master_risk_gate_closure_seal
from .risk_gate_evaluator import evaluate_master_risk_gate


class MasterSequentialArbitrationStatus(StrEnum):
    COMPLETED = "COMPLETED"


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


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def master_sequential_arbitration_outcome_payload(
    outcome: MasterSequentialArbitrationOutcome,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-sequential-arbitration-outcome.v1",
        "schema_version": outcome.schema_version,
        "rank": outcome.rank,
        "system_id": outcome.system_id,
        "proposal_id": outcome.proposal_id,
        "reservation_id": outcome.reservation_id,
        "candidate_fingerprint_sha256": outcome.candidate_fingerprint_sha256,
        "ledger_before_fingerprint_sha256": outcome.ledger_before_fingerprint_sha256,
        "decision_id": outcome.decision_id,
        "decision_status": outcome.decision_status,
        "decision_reason_codes": outcome.decision_reason_codes,
        "decision_fingerprint_sha256": outcome.decision_fingerprint_sha256,
        "admission_receipt_fingerprint_sha256": (
            outcome.admission_receipt_fingerprint_sha256
        ),
        "gate_closure_fingerprint_sha256": outcome.gate_closure_fingerprint_sha256,
        "ledger_after_fingerprint_sha256": outcome.ledger_after_fingerprint_sha256,
    }


def master_sequential_arbitration_outcome_fingerprint(
    outcome: MasterSequentialArbitrationOutcome,
) -> str:
    return stable_digest(master_sequential_arbitration_outcome_payload(outcome))


@dataclass(frozen=True, slots=True)
class MasterSequentialArbitrationOutcome:
    rank: int
    system_id: str
    proposal_id: str
    reservation_id: str
    candidate_fingerprint_sha256: str
    ledger_before_fingerprint_sha256: str
    decision_id: str
    decision_status: MasterRiskGateDecisionStatus
    decision_reason_codes: tuple[MasterRiskGateReasonCode, ...]
    decision_fingerprint_sha256: str
    admission_receipt_fingerprint_sha256: str
    gate_closure_fingerprint_sha256: str
    ledger_after_fingerprint_sha256: str
    fingerprint_sha256: str
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError("sequential arbitration outcome rank must be >= 1")
        for field_name in (
            "system_id",
            "proposal_id",
            "reservation_id",
            "decision_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "candidate_fingerprint_sha256",
            "ledger_before_fingerprint_sha256",
            "decision_fingerprint_sha256",
            "admission_receipt_fingerprint_sha256",
            "gate_closure_fingerprint_sha256",
            "ledger_after_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        if not self.decision_reason_codes:
            raise ValueError("sequential arbitration outcome requires decision reason codes")
        if len(set(self.decision_reason_codes)) != len(self.decision_reason_codes):
            raise ValueError("sequential arbitration decision reason codes must be unique")
        if self.schema_version != "1.0":
            raise ValueError("unsupported sequential arbitration outcome schema_version")

        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_sequential_arbitration_outcome_fingerprint(self)
        if normalized != expected:
            raise ValueError("sequential arbitration outcome fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def master_sequential_arbitration_result_payload(
    result: MasterSequentialArbitrationResult,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-sequential-arbitration-result.v1",
        "schema_version": result.schema_version,
        "master_portfolio_id": result.master_portfolio_id,
        "run_id": result.run_id,
        "batch_id": result.batch_id,
        "evaluated_at": result.evaluated_at,
        "status": result.status,
        "order_strategy": result.order_strategy,
        "arbitration_policy_fingerprint_sha256": (
            result.arbitration_policy_fingerprint_sha256
        ),
        "allocation_policy_fingerprint_sha256": (
            result.allocation_policy_fingerprint_sha256
        ),
        "gate_policy_fingerprint_sha256": result.gate_policy_fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": result.opening_snapshot_fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": (
            result.portfolio_snapshot_fingerprint_sha256
        ),
        "initial_ledger_fingerprint_sha256": result.initial_ledger_fingerprint_sha256,
        "final_ledger_fingerprint_sha256": result.final_ledger_fingerprint_sha256,
        "outcomes": [
            master_sequential_arbitration_outcome_payload(outcome)
            for outcome in result.outcomes
        ],
    }


def master_sequential_arbitration_result_fingerprint(
    result: MasterSequentialArbitrationResult,
) -> str:
    return stable_digest(master_sequential_arbitration_result_payload(result))


@dataclass(frozen=True, slots=True)
class MasterSequentialArbitrationResult:
    """Immutable evidence for one completed sequential arbitration run."""

    master_portfolio_id: str
    run_id: str
    batch_id: str
    evaluated_at: datetime
    status: MasterSequentialArbitrationStatus
    order_strategy: MasterArbitrationOrderStrategy
    arbitration_policy_fingerprint_sha256: str
    allocation_policy_fingerprint_sha256: str
    gate_policy_fingerprint_sha256: str
    opening_snapshot_fingerprint_sha256: str
    portfolio_snapshot_fingerprint_sha256: str
    initial_ledger_fingerprint_sha256: str
    final_ledger_fingerprint_sha256: str
    outcomes: tuple[MasterSequentialArbitrationOutcome, ...]
    fingerprint_sha256: str
    mutation_applied: bool = field(default=True, init=False)
    reservation_mutation: bool = field(default=True, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in ("master_portfolio_id", "run_id", "batch_id"):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(self, "evaluated_at", _utc(self.evaluated_at, field_name="evaluated_at"))
        for field_name in (
            "arbitration_policy_fingerprint_sha256",
            "allocation_policy_fingerprint_sha256",
            "gate_policy_fingerprint_sha256",
            "opening_snapshot_fingerprint_sha256",
            "portfolio_snapshot_fingerprint_sha256",
            "initial_ledger_fingerprint_sha256",
            "final_ledger_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        if self.status is not MasterSequentialArbitrationStatus.COMPLETED:
            raise ValueError("sequential arbitration result status must be COMPLETED")
        if not self.outcomes:
            raise ValueError("sequential arbitration result requires at least one outcome")
        if tuple(outcome.rank for outcome in self.outcomes) != tuple(
            range(1, len(self.outcomes) + 1)
        ):
            raise ValueError("sequential arbitration outcome ranks must be contiguous from 1")
        for previous, current in zip(self.outcomes, self.outcomes[1:], strict=False):
            if previous.ledger_after_fingerprint_sha256 != current.ledger_before_fingerprint_sha256:
                raise ValueError("sequential arbitration ledger chain is not contiguous")
        if (
            self.initial_ledger_fingerprint_sha256
            != self.outcomes[0].ledger_before_fingerprint_sha256
        ):
            raise ValueError("initial ledger fingerprint does not match first arbitration outcome")
        if (
            self.final_ledger_fingerprint_sha256
            != self.outcomes[-1].ledger_after_fingerprint_sha256
        ):
            raise ValueError("final ledger fingerprint does not match last arbitration outcome")
        if self.schema_version != "1.0":
            raise ValueError("unsupported sequential arbitration result schema_version")

        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_sequential_arbitration_result_fingerprint(self)
        if normalized != expected:
            raise ValueError("sequential arbitration result fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def _validate_context(
    *,
    arbitration_policy: MasterArbitrationPolicy,
    batch: MasterArbitrationBatch,
    allocation_policy: MasterAllocationPolicy,
    gate_policy: MasterRiskGatePolicy,
    opening_snapshot: MasterPortfolioSnapshot,
    portfolio_snapshot: MasterPortfolioSnapshot,
    ledger: MasterReservationLedger,
    candidates: tuple[MasterRiskGateCandidate, ...],
    evaluated_at: datetime,
) -> tuple[ReservationLedgerSnapshot, dict[str, MasterRiskGateCandidate]]:
    if arbitration_policy.status is not MasterArbitrationPolicyStatus.CONFIGURED:
        raise ValueError("Master arbitration policy must be CONFIGURED")
    if (
        arbitration_policy.order_strategy
        is not MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST
    ):
        raise ValueError("unsupported Master arbitration order strategy")
    if evaluated_at < batch.created_at:
        raise ValueError("sequential arbitration cannot precede batch creation")
    if evaluated_at > portfolio_snapshot.observed_at:
        raise ValueError("sequential arbitration cannot postdate portfolio observation")

    master_portfolio_id = arbitration_policy.master_portfolio_id
    if any(
        item != master_portfolio_id
        for item in (
            batch.master_portfolio_id,
            allocation_policy.master_portfolio_id,
            gate_policy.master_portfolio_id,
            opening_snapshot.master_portfolio_id,
            portfolio_snapshot.master_portfolio_id,
            ledger.policy.master_portfolio_id,
        )
    ):
        raise ValueError("sequential arbitration context spans multiple Master Portfolios")
    if batch.arbitration_policy_fingerprint_sha256 != arbitration_policy.fingerprint_sha256:
        raise ValueError("arbitration batch does not bind to supplied arbitration policy")
    if batch.order_strategy is not arbitration_policy.order_strategy:
        raise ValueError("arbitration batch order strategy does not match policy")
    if any(
        fingerprint != allocation_policy.fingerprint_sha256
        for fingerprint in (
            arbitration_policy.allocation_policy_fingerprint_sha256,
            batch.allocation_policy_fingerprint_sha256,
            gate_policy.allocation_policy_fingerprint_sha256,
            ledger.policy.fingerprint_sha256,
        )
    ):
        raise ValueError("sequential arbitration allocation policy provenance mismatch")
    if ledger.opening_snapshot.fingerprint_sha256 != opening_snapshot.fingerprint_sha256:
        raise ValueError("sequential arbitration opening snapshot does not match ledger")

    current_ledger = ledger.snapshot()
    if current_ledger.fingerprint_sha256 != batch.source_ledger_fingerprint_sha256:
        raise ValueError("arbitration batch source ledger is stale")

    if len(candidates) != len(batch.entries):
        raise ValueError("candidate set must match arbitration batch exactly")
    candidate_map: dict[str, MasterRiskGateCandidate] = {}
    for candidate in candidates:
        if candidate.fingerprint_sha256 in candidate_map:
            raise ValueError("sequential arbitration candidates must be unique")
        candidate_map[candidate.fingerprint_sha256] = candidate
    if set(candidate_map) != {entry.candidate_fingerprint_sha256 for entry in batch.entries}:
        raise ValueError("candidate fingerprints do not match arbitration batch")

    reservation_map = {item.reservation_id: item for item in current_ledger.reservations}
    for entry in batch.entries:
        candidate = candidate_map[entry.candidate_fingerprint_sha256]
        if (
            candidate.system_id != entry.system_id
            or candidate.proposal_id != entry.proposal_id
            or candidate.reservation_id != entry.reservation_id
        ):
            raise ValueError("arbitration entry does not bind to supplied candidate")
        reservation = reservation_map.get(entry.reservation_id)
        if (
            reservation is None
            or reservation.fingerprint_sha256 != entry.reservation_fingerprint_sha256
        ):
            raise ValueError("arbitration entry reservation provenance mismatch")

    return current_ledger, candidate_map


def _build_outcome(
    *,
    rank: int,
    candidate: MasterRiskGateCandidate,
    ledger_before: ReservationLedgerSnapshot,
    decision,
    receipt,
    closure,
    ledger_after: ReservationLedgerSnapshot,
) -> MasterSequentialArbitrationOutcome:
    payload = {
        "schema": "money-heist.master-sequential-arbitration-outcome.v1",
        "schema_version": "1.0",
        "rank": rank,
        "system_id": candidate.system_id,
        "proposal_id": candidate.proposal_id,
        "reservation_id": candidate.reservation_id,
        "candidate_fingerprint_sha256": candidate.fingerprint_sha256,
        "ledger_before_fingerprint_sha256": ledger_before.fingerprint_sha256,
        "decision_id": decision.decision_id,
        "decision_status": decision.status,
        "decision_reason_codes": decision.reason_codes,
        "decision_fingerprint_sha256": decision.fingerprint_sha256,
        "admission_receipt_fingerprint_sha256": receipt.fingerprint_sha256,
        "gate_closure_fingerprint_sha256": closure.closure_fingerprint_sha256,
        "ledger_after_fingerprint_sha256": ledger_after.fingerprint_sha256,
    }
    assert candidate.reservation_id is not None
    return MasterSequentialArbitrationOutcome(
        rank=rank,
        system_id=candidate.system_id,
        proposal_id=candidate.proposal_id,
        reservation_id=candidate.reservation_id,
        candidate_fingerprint_sha256=candidate.fingerprint_sha256,
        ledger_before_fingerprint_sha256=ledger_before.fingerprint_sha256,
        decision_id=decision.decision_id,
        decision_status=decision.status,
        decision_reason_codes=decision.reason_codes,
        decision_fingerprint_sha256=decision.fingerprint_sha256,
        admission_receipt_fingerprint_sha256=receipt.fingerprint_sha256,
        gate_closure_fingerprint_sha256=closure.closure_fingerprint_sha256,
        ledger_after_fingerprint_sha256=ledger_after.fingerprint_sha256,
        fingerprint_sha256=stable_digest(payload),
    )


def arbitrate_master_batch_sequentially(
    *,
    arbitration_policy: MasterArbitrationPolicy,
    batch: MasterArbitrationBatch,
    allocation_policy: MasterAllocationPolicy,
    gate_policy: MasterRiskGatePolicy,
    opening_snapshot: MasterPortfolioSnapshot,
    portfolio_snapshot: MasterPortfolioSnapshot,
    ledger: MasterReservationLedger,
    candidates: tuple[MasterRiskGateCandidate, ...],
    evaluated_at: datetime,
) -> MasterSequentialArbitrationResult:
    """Evaluate and transition one ordered arbitration batch against an evolving ledger.

    FIFO is an evaluation order, not an invented economic priority rule. Every still-RESERVED
    candidate remains visible to the existing Master Risk Gate until its own turn transitions it.
    Each outcome is applied only through the existing Reservation-to-Admission Bridge and sealed
    with the existing Master Risk Gate closure contract. No broker or LIVE execution occurs here.
    """

    normalized_time = _utc(evaluated_at, field_name="evaluated_at")
    initial_ledger, candidate_map = _validate_context(
        arbitration_policy=arbitration_policy,
        batch=batch,
        allocation_policy=allocation_policy,
        gate_policy=gate_policy,
        opening_snapshot=opening_snapshot,
        portfolio_snapshot=portfolio_snapshot,
        ledger=ledger,
        candidates=candidates,
        evaluated_at=normalized_time,
    )

    outcomes: list[MasterSequentialArbitrationOutcome] = []
    for entry in batch.entries:
        candidate = candidate_map[entry.candidate_fingerprint_sha256]
        ledger_before = ledger.snapshot()
        decision = evaluate_master_risk_gate(
            gate_policy=gate_policy,
            allocation_policy=allocation_policy,
            candidate=candidate,
            portfolio_snapshot=portfolio_snapshot,
            ledger_snapshot=ledger_before,
            evaluated_at=normalized_time,
        )
        receipt = apply_master_risk_gate_decision_to_reservation(
            ledger=ledger,
            candidate=candidate,
            decision=decision,
        )
        ledger_after = ledger.snapshot()
        closure = build_master_risk_gate_closure_seal(
            gate_policy=gate_policy,
            allocation_policy=allocation_policy,
            opening_snapshot=opening_snapshot,
            portfolio_snapshot=portfolio_snapshot,
            ledger_before=ledger_before,
            ledger_after=ledger_after,
            candidate=candidate,
            decision=decision,
            receipt=receipt,
        )
        outcomes.append(
            _build_outcome(
                rank=entry.rank,
                candidate=candidate,
                ledger_before=ledger_before,
                decision=decision,
                receipt=receipt,
                closure=closure,
                ledger_after=ledger_after,
            )
        )

    final_ledger = ledger.snapshot()
    run_id = "master-arbitration-run:" + stable_digest(
        {
            "schema": "money-heist.master-sequential-arbitration-run-id.v1",
            "batch_fingerprint_sha256": batch.fingerprint_sha256,
            "gate_policy_fingerprint_sha256": gate_policy.fingerprint_sha256,
            "portfolio_snapshot_fingerprint_sha256": portfolio_snapshot.fingerprint_sha256,
            "evaluated_at": normalized_time,
            "outcome_fingerprints": [item.fingerprint_sha256 for item in outcomes],
        }
    )
    payload = {
        "schema": "money-heist.master-sequential-arbitration-result.v1",
        "schema_version": "1.0",
        "master_portfolio_id": arbitration_policy.master_portfolio_id,
        "run_id": run_id,
        "batch_id": batch.batch_id,
        "evaluated_at": normalized_time,
        "status": MasterSequentialArbitrationStatus.COMPLETED,
        "order_strategy": batch.order_strategy,
        "arbitration_policy_fingerprint_sha256": arbitration_policy.fingerprint_sha256,
        "allocation_policy_fingerprint_sha256": allocation_policy.fingerprint_sha256,
        "gate_policy_fingerprint_sha256": gate_policy.fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": opening_snapshot.fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": portfolio_snapshot.fingerprint_sha256,
        "initial_ledger_fingerprint_sha256": initial_ledger.fingerprint_sha256,
        "final_ledger_fingerprint_sha256": final_ledger.fingerprint_sha256,
        "outcomes": [master_sequential_arbitration_outcome_payload(item) for item in outcomes],
    }
    return MasterSequentialArbitrationResult(
        master_portfolio_id=arbitration_policy.master_portfolio_id,
        run_id=run_id,
        batch_id=batch.batch_id,
        evaluated_at=normalized_time,
        status=MasterSequentialArbitrationStatus.COMPLETED,
        order_strategy=batch.order_strategy,
        arbitration_policy_fingerprint_sha256=arbitration_policy.fingerprint_sha256,
        allocation_policy_fingerprint_sha256=allocation_policy.fingerprint_sha256,
        gate_policy_fingerprint_sha256=gate_policy.fingerprint_sha256,
        opening_snapshot_fingerprint_sha256=opening_snapshot.fingerprint_sha256,
        portfolio_snapshot_fingerprint_sha256=portfolio_snapshot.fingerprint_sha256,
        initial_ledger_fingerprint_sha256=initial_ledger.fingerprint_sha256,
        final_ledger_fingerprint_sha256=final_ledger.fingerprint_sha256,
        outcomes=tuple(outcomes),
        fingerprint_sha256=stable_digest(payload),
    )


__all__ = [
    "MasterSequentialArbitrationOutcome",
    "MasterSequentialArbitrationResult",
    "MasterSequentialArbitrationStatus",
    "arbitrate_master_batch_sequentially",
    "master_sequential_arbitration_outcome_fingerprint",
    "master_sequential_arbitration_result_fingerprint",
]
