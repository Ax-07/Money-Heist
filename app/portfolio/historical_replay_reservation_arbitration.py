from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .allocation import AllocationEnvelopeStatus, MasterAllocationPolicy
from .arbitration import (
    MasterArbitrationBatch,
    MasterArbitrationPolicy,
    MasterArbitrationPolicyStatus,
    build_master_arbitration_batch,
)
from .arbitration_closure import (
    MasterArbitrationClosureSeal,
    build_master_arbitration_closure_seal,
)
from .arbitration_sequential import (
    MasterSequentialArbitrationResult,
    arbitrate_master_batch_sequentially,
)
from .historical_replay import MasterHistoricalReplayPlan
from .historical_replay_coordinator import MasterHistoricalReplayTimeline
from .historical_replay_preexecution import (
    MasterHistoricalCandidateSeed,
    MasterHistoricalDecisionBarrier,
)
from .models import MasterPortfolioSnapshot
from .reservation import (
    MasterReservationLedger,
    ReservationLedgerSnapshot,
    ReservationOutcomeStatus,
    ReservationReasonCode,
    ReservationRequest,
    ReservationResult,
)
from .risk_gate import (
    MasterRiskGateCandidate,
    MasterRiskGateDecisionStatus,
    MasterRiskGatePolicy,
    MasterRiskGatePolicyStatus,
    build_master_risk_gate_candidate,
)

ZERO = Decimal("0")


class MasterHistoricalCapitalRequirementSource(StrEnum):
    OPERATOR_CONFIGURATION = "OPERATOR_CONFIGURATION"


class MasterHistoricalReservationAttemptStatus(StrEnum):
    RESERVED_FOR_ARBITRATION = "RESERVED_FOR_ARBITRATION"
    NOT_RESERVED = "NOT_RESERVED"


class MasterHistoricalReservationArbitrationStatus(StrEnum):
    NO_AUTHORIZED_CANDIDATES = "NO_AUTHORIZED_CANDIDATES"
    NO_RESERVATIONS = "NO_RESERVATIONS"
    ARBITRATED = "ARBITRATED"


def _required_text(value: object, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _optional_text(value: object | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name=field_name)


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


def _positive_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= ZERO:
        raise ValueError(f"{field_name} must be a finite Decimal > 0")
    return value


def master_historical_capital_requirement_payload(
    requirement: MasterHistoricalCapitalRequirement,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-capital-requirement.v1",
        "schema_version": requirement.schema_version,
        "system_id": requirement.system_id,
        "proposal_id": requirement.proposal_id,
        "capital_amount": requirement.capital_amount,
        "source": requirement.source,
        "source_ref": requirement.source_ref,
    }


def master_historical_capital_requirement_fingerprint(
    requirement: MasterHistoricalCapitalRequirement,
) -> str:
    return stable_digest(master_historical_capital_requirement_payload(requirement))


@dataclass(frozen=True, slots=True)
class MasterHistoricalCapitalRequirement:
    """Explicit physical-capital requirement; no notional-to-capital inference is allowed."""

    system_id: str
    proposal_id: str
    capital_amount: Decimal
    fingerprint_sha256: str
    source_ref: str | None = None
    source: MasterHistoricalCapitalRequirementSource = field(
        default=MasterHistoricalCapitalRequirementSource.OPERATOR_CONFIGURATION,
        init=False,
    )
    inferred_from_notional: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "system_id",
            _required_text(self.system_id, field_name="system_id"),
        )
        object.__setattr__(
            self,
            "proposal_id",
            _required_text(self.proposal_id, field_name="proposal_id"),
        )
        object.__setattr__(
            self,
            "capital_amount",
            _positive_decimal(self.capital_amount, field_name="capital_amount"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _optional_text(self.source_ref, field_name="source_ref"),
        )
        if self.schema_version != "1.0":
            raise ValueError("unsupported historical capital requirement schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_historical_capital_requirement_fingerprint(self)
        if normalized != expected:
            raise ValueError("historical capital requirement fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def build_master_historical_capital_requirement(
    *,
    system_id: str,
    proposal_id: str,
    capital_amount: Decimal,
    source_ref: str | None = None,
) -> MasterHistoricalCapitalRequirement:
    normalized_system = _required_text(system_id, field_name="system_id")
    normalized_proposal = _required_text(proposal_id, field_name="proposal_id")
    normalized_amount = _positive_decimal(capital_amount, field_name="capital_amount")
    normalized_source_ref = _optional_text(source_ref, field_name="source_ref")
    payload = {
        "schema": "money-heist.master-historical-capital-requirement.v1",
        "schema_version": "1.0",
        "system_id": normalized_system,
        "proposal_id": normalized_proposal,
        "capital_amount": normalized_amount,
        "source": MasterHistoricalCapitalRequirementSource.OPERATOR_CONFIGURATION,
        "source_ref": normalized_source_ref,
    }
    return MasterHistoricalCapitalRequirement(
        system_id=normalized_system,
        proposal_id=normalized_proposal,
        capital_amount=normalized_amount,
        source_ref=normalized_source_ref,
        fingerprint_sha256=stable_digest(payload),
    )


def master_historical_reservation_attempt_payload(
    attempt: MasterHistoricalReservationAttempt,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-reservation-attempt.v1",
        "schema_version": attempt.schema_version,
        "system_id": attempt.system_id,
        "proposal_id": attempt.proposal_id,
        "status": attempt.status,
        "seed_fingerprint_sha256": attempt.seed_fingerprint_sha256,
        "requirement_fingerprint_sha256": attempt.requirement.fingerprint_sha256,
        "request_fingerprint_sha256": attempt.request.fingerprint_sha256,
        "reservation_result_fingerprint_sha256": (
            attempt.reservation_result.fingerprint_sha256
        ),
        "reservation_id": attempt.reservation_id,
        "candidate_fingerprint_sha256": (
            attempt.candidate.fingerprint_sha256 if attempt.candidate is not None else None
        ),
    }


def master_historical_reservation_attempt_fingerprint(
    attempt: MasterHistoricalReservationAttempt,
) -> str:
    return stable_digest(master_historical_reservation_attempt_payload(attempt))


@dataclass(frozen=True, slots=True)
class MasterHistoricalReservationAttempt:
    system_id: str
    proposal_id: str
    status: MasterHistoricalReservationAttemptStatus
    seed_fingerprint_sha256: str
    requirement: MasterHistoricalCapitalRequirement
    request: ReservationRequest
    reservation_result: ReservationResult
    candidate: MasterRiskGateCandidate | None
    fingerprint_sha256: str
    broker_called: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in ("system_id", "proposal_id"):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "seed_fingerprint_sha256",
            _sha256(self.seed_fingerprint_sha256, field_name="seed_fingerprint_sha256"),
        )
        if self.requirement.system_id != self.system_id:
            raise ValueError("historical reservation requirement system_id mismatch")
        if self.requirement.proposal_id != self.proposal_id:
            raise ValueError("historical reservation requirement proposal_id mismatch")
        if self.request.system_id != self.system_id:
            raise ValueError("historical reservation request system_id mismatch")
        if self.request.request_ref != self.proposal_id:
            raise ValueError("historical reservation request_ref must equal proposal_id")
        if self.request.capital_amount != self.requirement.capital_amount:
            raise ValueError("historical reservation request capital does not match requirement")
        if self.reservation_result.request != self.request:
            raise ValueError("historical reservation result does not bind exact request")

        if self.status is MasterHistoricalReservationAttemptStatus.RESERVED_FOR_ARBITRATION:
            if self.reservation_result.status is not ReservationOutcomeStatus.RESERVED:
                raise ValueError("reserved historical attempt requires RESERVED result")
            if self.reservation_result.reservation is None or self.candidate is None:
                raise ValueError("reserved historical attempt requires reservation and candidate")
            if self.candidate.reservation_id != self.reservation_result.reservation.reservation_id:
                raise ValueError(
                    "historical candidate reservation does not match reservation result"
                )
            if self.candidate.system_id != self.system_id:
                raise ValueError("historical candidate system_id mismatch")
            if self.candidate.proposal_id != self.proposal_id:
                raise ValueError("historical candidate proposal_id mismatch")
        elif self.status is MasterHistoricalReservationAttemptStatus.NOT_RESERVED:
            if self.reservation_result.status is not ReservationOutcomeStatus.NOT_RESERVED:
                raise ValueError("NOT_RESERVED historical attempt requires NOT_RESERVED result")
            if self.reservation_result.reservation is not None or self.candidate is not None:
                raise ValueError(
                    "NOT_RESERVED historical attempt cannot carry candidate/reservation"
                )
        else:
            raise ValueError(f"unsupported historical reservation attempt status: {self.status}")

        if self.schema_version != "1.0":
            raise ValueError("unsupported historical reservation attempt schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_historical_reservation_attempt_fingerprint(self)
        if normalized != expected:
            raise ValueError("historical reservation attempt fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    @property
    def reservation_id(self) -> str | None:
        reservation = self.reservation_result.reservation
        return reservation.reservation_id if reservation is not None else None

    @property
    def reason_codes(self) -> tuple[ReservationReasonCode, ...]:
        return self.reservation_result.reason_codes


def master_historical_reservation_arbitration_payload(
    result: MasterHistoricalReservationArbitrationResult,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-reservation-arbitration.v1",
        "schema_version": result.schema_version,
        "result_id": result.result_id,
        "master_portfolio_id": result.master_portfolio_id,
        "plan_id": result.plan_id,
        "timeline_id": result.timeline_id,
        "barrier_result_id": result.barrier_result_id,
        "barrier_sequence": result.barrier_sequence,
        "observed_at": result.observed_at,
        "status": result.status,
        "plan_fingerprint_sha256": result.plan_fingerprint_sha256,
        "timeline_fingerprint_sha256": result.timeline_fingerprint_sha256,
        "decision_barrier_fingerprint_sha256": result.decision_barrier_fingerprint_sha256,
        "allocation_policy_fingerprint_sha256": (
            result.allocation_policy_fingerprint_sha256
        ),
        "gate_policy_fingerprint_sha256": result.gate_policy_fingerprint_sha256,
        "arbitration_policy_fingerprint_sha256": (
            result.arbitration_policy_fingerprint_sha256
        ),
        "opening_snapshot_fingerprint_sha256": result.opening_snapshot_fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": (
            result.portfolio_snapshot_fingerprint_sha256
        ),
        "initial_ledger_fingerprint_sha256": result.initial_ledger_fingerprint_sha256,
        "post_reservation_ledger_fingerprint_sha256": (
            result.post_reservation_ledger_fingerprint_sha256
        ),
        "final_ledger_fingerprint_sha256": result.final_ledger_fingerprint_sha256,
        "candidate_seed_fingerprints_sha256": result.candidate_seed_fingerprints_sha256,
        "attempts": [
            master_historical_reservation_attempt_payload(item)
            for item in result.attempts
        ],
        "candidate_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in result.candidates
        ),
        "arbitration_batch_fingerprint_sha256": (
            result.arbitration_batch.fingerprint_sha256
            if result.arbitration_batch is not None
            else None
        ),
        "arbitration_result_fingerprint_sha256": (
            result.arbitration_result.fingerprint_sha256
            if result.arbitration_result is not None
            else None
        ),
        "arbitration_closure_fingerprint_sha256": (
            result.arbitration_closure.closure_fingerprint_sha256
            if result.arbitration_closure is not None
            else None
        ),
        "reservation_mutation_applied": result.reservation_mutation_applied,
        "admission_transitions_applied": result.admission_transitions_applied,
    }


def master_historical_reservation_arbitration_fingerprint(
    result: MasterHistoricalReservationArbitrationResult,
) -> str:
    return stable_digest(master_historical_reservation_arbitration_payload(result))


@dataclass(frozen=True, slots=True)
class MasterHistoricalReservationArbitrationResult:
    """One CLOSE-barrier bridge through reservation and existing Master arbitration only."""

    result_id: str
    master_portfolio_id: str
    plan_id: str
    timeline_id: str
    barrier_result_id: str
    barrier_sequence: int
    observed_at: datetime
    status: MasterHistoricalReservationArbitrationStatus
    plan_fingerprint_sha256: str
    timeline_fingerprint_sha256: str
    decision_barrier_fingerprint_sha256: str
    allocation_policy_fingerprint_sha256: str
    gate_policy_fingerprint_sha256: str
    arbitration_policy_fingerprint_sha256: str
    opening_snapshot_fingerprint_sha256: str
    portfolio_snapshot_fingerprint_sha256: str
    initial_ledger_fingerprint_sha256: str
    post_reservation_ledger_fingerprint_sha256: str
    final_ledger_fingerprint_sha256: str
    candidate_seed_fingerprints_sha256: tuple[str, ...]
    attempts: tuple[MasterHistoricalReservationAttempt, ...]
    candidates: tuple[MasterRiskGateCandidate, ...]
    arbitration_batch: MasterArbitrationBatch | None
    arbitration_result: MasterSequentialArbitrationResult | None
    arbitration_closure: MasterArbitrationClosureSeal | None
    reservation_mutation_applied: bool
    admission_transitions_applied: bool
    fingerprint_sha256: str
    single_master_capital: bool = field(default=True, init=False)
    sums_branch_equities: bool = field(default=False, init=False)
    broker_called: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
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
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        if self.barrier_sequence < 1:
            raise ValueError("historical reservation/arbitration barrier_sequence must be >= 1")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, field_name="observed_at"))
        for field_name in (
            "plan_fingerprint_sha256",
            "timeline_fingerprint_sha256",
            "decision_barrier_fingerprint_sha256",
            "allocation_policy_fingerprint_sha256",
            "gate_policy_fingerprint_sha256",
            "arbitration_policy_fingerprint_sha256",
            "opening_snapshot_fingerprint_sha256",
            "portfolio_snapshot_fingerprint_sha256",
            "initial_ledger_fingerprint_sha256",
            "post_reservation_ledger_fingerprint_sha256",
            "final_ledger_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        normalized_seeds = tuple(
            _sha256(item, field_name="candidate_seed_fingerprints_sha256")
            for item in self.candidate_seed_fingerprints_sha256
        )
        if len(set(normalized_seeds)) != len(normalized_seeds):
            raise ValueError("historical reservation/arbitration seed fingerprints must be unique")
        object.__setattr__(self, "candidate_seed_fingerprints_sha256", normalized_seeds)

        expected_attempt_order = tuple(
            sorted(self.attempts, key=lambda item: (item.system_id, item.proposal_id))
        )
        if self.attempts != expected_attempt_order:
            raise ValueError("historical reservation attempts must be canonically sorted")
        if tuple(item.seed_fingerprint_sha256 for item in self.attempts) != normalized_seeds:
            raise ValueError("historical reservation attempts must bind every candidate seed")
        expected_candidates = tuple(
            item.candidate for item in self.attempts if item.candidate is not None
        )
        if self.candidates != expected_candidates:
            raise ValueError("historical candidates must match successful reservations exactly")

        if self.status is MasterHistoricalReservationArbitrationStatus.NO_AUTHORIZED_CANDIDATES:
            if self.attempts or self.candidates:
                raise ValueError("NO_AUTHORIZED_CANDIDATES cannot carry attempts/candidates")
            if any(
                item is not None
                for item in (
                    self.arbitration_batch,
                    self.arbitration_result,
                    self.arbitration_closure,
                )
            ):
                raise ValueError("NO_AUTHORIZED_CANDIDATES cannot carry arbitration")
            if self.reservation_mutation_applied or self.admission_transitions_applied:
                raise ValueError("NO_AUTHORIZED_CANDIDATES cannot report mutation")
        elif self.status is MasterHistoricalReservationArbitrationStatus.NO_RESERVATIONS:
            if not self.attempts or self.candidates:
                raise ValueError("NO_RESERVATIONS requires attempts and no candidates")
            if any(
                item.status is not MasterHistoricalReservationAttemptStatus.NOT_RESERVED
                for item in self.attempts
            ):
                raise ValueError("NO_RESERVATIONS requires every attempt to be NOT_RESERVED")
            if any(
                item is not None
                for item in (
                    self.arbitration_batch,
                    self.arbitration_result,
                    self.arbitration_closure,
                )
            ):
                raise ValueError("NO_RESERVATIONS cannot carry arbitration")
            if not self.reservation_mutation_applied:
                raise ValueError("NO_RESERVATIONS must report reservation-attempt mutation")
            if self.admission_transitions_applied:
                raise ValueError("NO_RESERVATIONS cannot report admission transitions")
        elif self.status is MasterHistoricalReservationArbitrationStatus.ARBITRATED:
            if not self.candidates:
                raise ValueError("ARBITRATED requires at least one Master candidate")
            if (
                self.arbitration_batch is None
                or self.arbitration_result is None
                or self.arbitration_closure is None
            ):
                raise ValueError("ARBITRATED requires batch, result and arbitration closure")
            if not self.reservation_mutation_applied or not self.admission_transitions_applied:
                raise ValueError("ARBITRATED requires reservation and admission transitions")
            if self.arbitration_batch.batch_id != self.arbitration_result.batch_id:
                raise ValueError("historical arbitration result does not bind arbitration batch")
            if self.arbitration_closure.batch_id != self.arbitration_batch.batch_id:
                raise ValueError("historical arbitration closure does not bind arbitration batch")
            if (
                self.arbitration_closure.result_fingerprint_sha256
                != self.arbitration_result.fingerprint_sha256
            ):
                raise ValueError("historical arbitration closure does not bind arbitration result")
            if self.arbitration_closure.run_id != self.arbitration_result.run_id:
                raise ValueError("historical arbitration closure does not bind arbitration run")
            if self.arbitration_closure.master_portfolio_id != self.master_portfolio_id:
                raise ValueError("historical arbitration closure Master Portfolio mismatch")
            closure_fingerprints = (
                self.arbitration_closure.arbitration_policy_fingerprint_sha256,
                self.arbitration_closure.allocation_policy_fingerprint_sha256,
                self.arbitration_closure.gate_policy_fingerprint_sha256,
                self.arbitration_closure.opening_snapshot_fingerprint_sha256,
                self.arbitration_closure.portfolio_snapshot_fingerprint_sha256,
            )
            expected_fingerprints = (
                self.arbitration_policy_fingerprint_sha256,
                self.allocation_policy_fingerprint_sha256,
                self.gate_policy_fingerprint_sha256,
                self.opening_snapshot_fingerprint_sha256,
                self.portfolio_snapshot_fingerprint_sha256,
            )
            if closure_fingerprints != expected_fingerprints:
                raise ValueError("historical arbitration closure provenance mismatch")
            if (
                self.arbitration_result.initial_ledger_fingerprint_sha256
                != self.post_reservation_ledger_fingerprint_sha256
            ):
                raise ValueError(
                    "historical arbitration did not start from post-reservation ledger"
                )
            if (
                self.arbitration_result.final_ledger_fingerprint_sha256
                != self.final_ledger_fingerprint_sha256
            ):
                raise ValueError("historical arbitration final ledger fingerprint mismatch")
            if (
                self.arbitration_closure.initial_ledger_fingerprint_sha256
                != self.post_reservation_ledger_fingerprint_sha256
            ):
                raise ValueError("historical arbitration closure initial ledger mismatch")
            if (
                self.arbitration_closure.final_ledger_fingerprint_sha256
                != self.final_ledger_fingerprint_sha256
            ):
                raise ValueError("historical arbitration closure final ledger mismatch")
        else:
            raise ValueError(
                f"unsupported historical reservation/arbitration status: {self.status}"
            )

        if (
            self.status is not MasterHistoricalReservationArbitrationStatus.ARBITRATED
            and self.final_ledger_fingerprint_sha256
            != self.post_reservation_ledger_fingerprint_sha256
        ):
            raise ValueError(
                "non-arbitrated result final ledger must equal post-reservation ledger"
            )
        if self.schema_version != "1.0":
            raise ValueError("unsupported historical reservation/arbitration schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_historical_reservation_arbitration_fingerprint(self)
        if normalized != expected:
            raise ValueError(
                "historical reservation/arbitration fingerprint does not match payload"
            )
        object.__setattr__(self, "fingerprint_sha256", normalized)

    @property
    def mutation_applied(self) -> bool:
        return self.reservation_mutation_applied or self.admission_transitions_applied

    @property
    def reserved_count(self) -> int:
        return len(self.candidates)

    @property
    def not_reserved_count(self) -> int:
        return sum(
            item.status is MasterHistoricalReservationAttemptStatus.NOT_RESERVED
            for item in self.attempts
        )

    @property
    def admitted_count(self) -> int:
        if self.arbitration_result is None:
            return 0
        return sum(
            item.decision_status is MasterRiskGateDecisionStatus.ADMIT
            for item in self.arbitration_result.outcomes
        )

    @property
    def master_rejected_count(self) -> int:
        if self.arbitration_result is None:
            return 0
        return sum(
            item.decision_status is MasterRiskGateDecisionStatus.REJECT
            for item in self.arbitration_result.outcomes
        )


def _validate_context(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    decision_barrier: MasterHistoricalDecisionBarrier,
    allocation_policy: MasterAllocationPolicy,
    gate_policy: MasterRiskGatePolicy,
    arbitration_policy: MasterArbitrationPolicy,
    opening_snapshot: MasterPortfolioSnapshot,
    portfolio_snapshot: MasterPortfolioSnapshot,
    ledger: MasterReservationLedger,
) -> ReservationLedgerSnapshot:
    observed_at = decision_barrier.observed_at
    if timeline.master_portfolio_id != plan.master_portfolio_id:
        raise ValueError("historical reservation timeline Master Portfolio does not match plan")
    if (
        timeline.plan_id != plan.plan_id
        or timeline.plan_fingerprint_sha256 != plan.fingerprint_sha256
    ):
        raise ValueError("historical reservation timeline does not bind exact replay plan")
    if decision_barrier.master_portfolio_id != plan.master_portfolio_id:
        raise ValueError("historical decision barrier Master Portfolio does not match plan")
    if (
        decision_barrier.plan_id != plan.plan_id
        or decision_barrier.timeline_id != timeline.timeline_id
    ):
        raise ValueError("historical decision barrier plan/timeline mismatch")
    if decision_barrier.plan_fingerprint_sha256 != plan.fingerprint_sha256:
        raise ValueError("historical decision barrier plan fingerprint mismatch")
    if decision_barrier.timeline_fingerprint_sha256 != timeline.fingerprint_sha256:
        raise ValueError("historical decision barrier timeline fingerprint mismatch")
    if decision_barrier.barrier_sequence > len(timeline.barriers):
        raise ValueError("historical decision barrier is absent from timeline")
    source_barrier = timeline.barriers[decision_barrier.barrier_sequence - 1]
    if source_barrier.fingerprint_sha256 != decision_barrier.barrier_fingerprint_sha256:
        raise ValueError("historical decision barrier does not bind exact timeline barrier")
    if source_barrier.observed_at != observed_at:
        raise ValueError("historical decision barrier time does not match timeline barrier")

    if allocation_policy.status is not AllocationEnvelopeStatus.CONFIGURED:
        raise ValueError("historical reservation requires CONFIGURED allocation policy")
    if gate_policy.status is not MasterRiskGatePolicyStatus.CONFIGURED:
        raise ValueError("historical arbitration requires CONFIGURED Master Risk Gate policy")
    if arbitration_policy.status is not MasterArbitrationPolicyStatus.CONFIGURED:
        raise ValueError("historical arbitration requires CONFIGURED arbitration policy")
    if any(
        value != plan.master_portfolio_id
        for value in (
            allocation_policy.master_portfolio_id,
            gate_policy.master_portfolio_id,
            arbitration_policy.master_portfolio_id,
            opening_snapshot.master_portfolio_id,
            portfolio_snapshot.master_portfolio_id,
            ledger.policy.master_portfolio_id,
        )
    ):
        raise ValueError("historical reservation/arbitration spans multiple Master Portfolios")
    if allocation_policy.fingerprint_sha256 != plan.allocation_policy_fingerprint_sha256:
        raise ValueError("historical allocation policy does not match replay plan")
    if gate_policy.fingerprint_sha256 != plan.gate_policy_fingerprint_sha256:
        raise ValueError("historical Master Risk Gate policy does not match replay plan")
    if arbitration_policy.fingerprint_sha256 != plan.arbitration_policy_fingerprint_sha256:
        raise ValueError("historical arbitration policy does not match replay plan")
    if gate_policy.allocation_policy_fingerprint_sha256 != allocation_policy.fingerprint_sha256:
        raise ValueError("historical Master Risk Gate allocation provenance mismatch")
    if (
        arbitration_policy.allocation_policy_fingerprint_sha256
        != allocation_policy.fingerprint_sha256
    ):
        raise ValueError("historical arbitration allocation provenance mismatch")
    if ledger.policy.fingerprint_sha256 != allocation_policy.fingerprint_sha256:
        raise ValueError("historical reservation ledger allocation provenance mismatch")
    if ledger.opening_snapshot.fingerprint_sha256 != opening_snapshot.fingerprint_sha256:
        raise ValueError("historical opening snapshot does not match reservation ledger")
    if opening_snapshot.master_capital.equity != plan.master_initial_capital:
        raise ValueError("historical opening equity must equal plan Master initial capital")
    if ledger.master_capital_capacity_amount != plan.master_initial_capital:
        raise ValueError("historical ledger capacity must equal plan Master initial capital")
    if opening_snapshot.observed_at > observed_at:
        raise ValueError("historical opening snapshot cannot postdate decision barrier")
    if portfolio_snapshot.observed_at != observed_at:
        raise ValueError("historical portfolio snapshot must use exact decision barrier time")
    if allocation_policy.members != opening_snapshot.members:
        raise ValueError("historical opening snapshot membership does not match allocation policy")
    if allocation_policy.members != portfolio_snapshot.members:
        raise ValueError(
            "historical portfolio snapshot membership does not match allocation policy"
        )

    ledger_snapshot = ledger.snapshot()
    for record in ledger_snapshot.reservations:
        if record.request.requested_at > observed_at:
            raise ValueError("historical ledger contains future reservation request")
        if record.committed_at is not None and record.committed_at > observed_at:
            raise ValueError("historical ledger contains future reservation commit")
        if record.released_at is not None and record.released_at > observed_at:
            raise ValueError("historical ledger contains future reservation release")
    return ledger_snapshot


def _requirements_for_seeds(
    *,
    seeds: tuple[MasterHistoricalCandidateSeed, ...],
    requirements: tuple[MasterHistoricalCapitalRequirement, ...],
) -> dict[tuple[str, str], MasterHistoricalCapitalRequirement]:
    requirement_map: dict[tuple[str, str], MasterHistoricalCapitalRequirement] = {}
    for requirement in requirements:
        key = (requirement.system_id, requirement.proposal_id)
        if key in requirement_map:
            raise ValueError("historical capital requirements cannot duplicate system/proposal")
        requirement_map[key] = requirement
    seed_keys = {(seed.system_id, seed.proposal_id) for seed in seeds}
    if set(requirement_map) != seed_keys:
        raise ValueError("historical capital requirements must match authorized seeds exactly")
    return requirement_map


def _reservation_request(
    *,
    seed: MasterHistoricalCandidateSeed,
    requirement: MasterHistoricalCapitalRequirement,
    requested_at: datetime,
) -> ReservationRequest:
    request_id = "historical-reservation:" + stable_digest(
        {
            "schema": "money-heist.master-historical-reservation-request-id.v1",
            "seed_fingerprint_sha256": seed.fingerprint_sha256,
            "requirement_fingerprint_sha256": requirement.fingerprint_sha256,
            "requested_at": requested_at,
        }
    )
    return ReservationRequest(
        request_id=request_id,
        system_id=seed.system_id,
        requested_at=requested_at,
        capital_amount=requirement.capital_amount,
        open_risk_amount=seed.local_approved_risk_amount,
        gross_exposure_amount=seed.local_approved_notional,
        request_ref=seed.proposal_id,
    )


def _attempt(
    *,
    seed: MasterHistoricalCandidateSeed,
    requirement: MasterHistoricalCapitalRequirement,
    request: ReservationRequest,
    reservation_result: ReservationResult,
    candidate: MasterRiskGateCandidate | None,
) -> MasterHistoricalReservationAttempt:
    status = (
        MasterHistoricalReservationAttemptStatus.RESERVED_FOR_ARBITRATION
        if reservation_result.status is ReservationOutcomeStatus.RESERVED
        else MasterHistoricalReservationAttemptStatus.NOT_RESERVED
    )
    payload = {
        "schema": "money-heist.master-historical-reservation-attempt.v1",
        "schema_version": "1.0",
        "system_id": seed.system_id,
        "proposal_id": seed.proposal_id,
        "status": status,
        "seed_fingerprint_sha256": seed.fingerprint_sha256,
        "requirement_fingerprint_sha256": requirement.fingerprint_sha256,
        "request_fingerprint_sha256": request.fingerprint_sha256,
        "reservation_result_fingerprint_sha256": reservation_result.fingerprint_sha256,
        "reservation_id": (
            reservation_result.reservation.reservation_id
            if reservation_result.reservation is not None
            else None
        ),
        "candidate_fingerprint_sha256": (
            candidate.fingerprint_sha256 if candidate is not None else None
        ),
    }
    return MasterHistoricalReservationAttempt(
        system_id=seed.system_id,
        proposal_id=seed.proposal_id,
        status=status,
        seed_fingerprint_sha256=seed.fingerprint_sha256,
        requirement=requirement,
        request=request,
        reservation_result=reservation_result,
        candidate=candidate,
        fingerprint_sha256=stable_digest(payload),
    )


def bridge_master_historical_reservation_and_arbitration(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    decision_barrier: MasterHistoricalDecisionBarrier,
    allocation_policy: MasterAllocationPolicy,
    gate_policy: MasterRiskGatePolicy,
    arbitration_policy: MasterArbitrationPolicy,
    opening_snapshot: MasterPortfolioSnapshot,
    portfolio_snapshot: MasterPortfolioSnapshot,
    ledger: MasterReservationLedger,
    capital_requirements: tuple[MasterHistoricalCapitalRequirement, ...],
) -> MasterHistoricalReservationArbitrationResult:
    """Reserve one historical CLOSE batch and run existing 21c/21d admission, never a broker."""

    initial_ledger = _validate_context(
        plan=plan,
        timeline=timeline,
        decision_barrier=decision_barrier,
        allocation_policy=allocation_policy,
        gate_policy=gate_policy,
        arbitration_policy=arbitration_policy,
        opening_snapshot=opening_snapshot,
        portfolio_snapshot=portfolio_snapshot,
        ledger=ledger,
    )
    seeds = decision_barrier.candidate_seeds
    requirement_map = _requirements_for_seeds(
        seeds=seeds,
        requirements=capital_requirements,
    )

    attempts: list[MasterHistoricalReservationAttempt] = []
    candidates: list[MasterRiskGateCandidate] = []
    for seed in sorted(seeds, key=lambda item: (item.system_id, item.proposal_id)):
        requirement = requirement_map[(seed.system_id, seed.proposal_id)]
        request = _reservation_request(
            seed=seed,
            requirement=requirement,
            requested_at=decision_barrier.observed_at,
        )
        reservation_result = ledger.reserve(request)
        candidate = None
        if reservation_result.status is ReservationOutcomeStatus.RESERVED:
            assert reservation_result.reservation is not None
            candidate = build_master_risk_gate_candidate(
                master_portfolio_id=plan.master_portfolio_id,
                system_id=seed.system_id,
                local_risk_decision=seed.to_local_risk_decision(),
                reservation_id=reservation_result.reservation.reservation_id,
            )
            if (
                candidate.local_risk_decision_fingerprint_sha256
                != seed.local_risk_decision_fingerprint_sha256
            ):
                raise ValueError("historical candidate changed local Risk decision provenance")
            candidates.append(candidate)
        attempts.append(
            _attempt(
                seed=seed,
                requirement=requirement,
                request=request,
                reservation_result=reservation_result,
                candidate=candidate,
            )
        )

    ordered_attempts = tuple(sorted(attempts, key=lambda item: (item.system_id, item.proposal_id)))
    ordered_candidates = tuple(
        item.candidate for item in ordered_attempts if item.candidate is not None
    )
    post_reservation = ledger.snapshot()
    arbitration_batch = None
    arbitration_result = None
    arbitration_closure = None

    if not seeds:
        status = MasterHistoricalReservationArbitrationStatus.NO_AUTHORIZED_CANDIDATES
        final_ledger = post_reservation
        reservation_mutation_applied = False
        admission_transitions_applied = False
    elif not ordered_candidates:
        status = MasterHistoricalReservationArbitrationStatus.NO_RESERVATIONS
        final_ledger = post_reservation
        reservation_mutation_applied = True
        admission_transitions_applied = False
    else:
        arbitration_batch = build_master_arbitration_batch(
            policy=arbitration_policy,
            candidates=ordered_candidates,
            ledger_snapshot=post_reservation,
            created_at=decision_barrier.observed_at,
        )
        arbitration_result = arbitrate_master_batch_sequentially(
            arbitration_policy=arbitration_policy,
            batch=arbitration_batch,
            allocation_policy=allocation_policy,
            gate_policy=gate_policy,
            opening_snapshot=opening_snapshot,
            portfolio_snapshot=portfolio_snapshot,
            ledger=ledger,
            candidates=ordered_candidates,
            evaluated_at=decision_barrier.observed_at,
        )
        final_ledger = ledger.snapshot()
        arbitration_closure = build_master_arbitration_closure_seal(
            arbitration_policy=arbitration_policy,
            batch=arbitration_batch,
            allocation_policy=allocation_policy,
            gate_policy=gate_policy,
            opening_snapshot=opening_snapshot,
            portfolio_snapshot=portfolio_snapshot,
            initial_ledger=post_reservation,
            final_ledger=final_ledger,
            result=arbitration_result,
        )
        status = MasterHistoricalReservationArbitrationStatus.ARBITRATED
        reservation_mutation_applied = True
        admission_transitions_applied = True

    seed_fingerprints = tuple(seed.fingerprint_sha256 for seed in seeds)
    result_id = "historical-reservation-arbitration:" + stable_digest(
        {
            "schema": "money-heist.master-historical-reservation-arbitration-id.v1",
            "decision_barrier_fingerprint_sha256": decision_barrier.fingerprint_sha256,
            "initial_ledger_fingerprint_sha256": initial_ledger.fingerprint_sha256,
            "attempt_fingerprints": [item.fingerprint_sha256 for item in ordered_attempts],
            "arbitration_result_fingerprint_sha256": (
                arbitration_result.fingerprint_sha256 if arbitration_result is not None else None
            ),
            "arbitration_closure_fingerprint_sha256": (
                arbitration_closure.closure_fingerprint_sha256
                if arbitration_closure is not None
                else None
            ),
        }
    )
    payload = {
        "schema": "money-heist.master-historical-reservation-arbitration.v1",
        "schema_version": "1.0",
        "result_id": result_id,
        "master_portfolio_id": plan.master_portfolio_id,
        "plan_id": plan.plan_id,
        "timeline_id": timeline.timeline_id,
        "barrier_result_id": decision_barrier.barrier_result_id,
        "barrier_sequence": decision_barrier.barrier_sequence,
        "observed_at": decision_barrier.observed_at,
        "status": status,
        "plan_fingerprint_sha256": plan.fingerprint_sha256,
        "timeline_fingerprint_sha256": timeline.fingerprint_sha256,
        "decision_barrier_fingerprint_sha256": decision_barrier.fingerprint_sha256,
        "allocation_policy_fingerprint_sha256": allocation_policy.fingerprint_sha256,
        "gate_policy_fingerprint_sha256": gate_policy.fingerprint_sha256,
        "arbitration_policy_fingerprint_sha256": arbitration_policy.fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": opening_snapshot.fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": portfolio_snapshot.fingerprint_sha256,
        "initial_ledger_fingerprint_sha256": initial_ledger.fingerprint_sha256,
        "post_reservation_ledger_fingerprint_sha256": post_reservation.fingerprint_sha256,
        "final_ledger_fingerprint_sha256": final_ledger.fingerprint_sha256,
        "candidate_seed_fingerprints_sha256": seed_fingerprints,
        "attempts": [
            master_historical_reservation_attempt_payload(item)
            for item in ordered_attempts
        ],
        "candidate_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in ordered_candidates
        ),
        "arbitration_batch_fingerprint_sha256": (
            arbitration_batch.fingerprint_sha256 if arbitration_batch is not None else None
        ),
        "arbitration_result_fingerprint_sha256": (
            arbitration_result.fingerprint_sha256 if arbitration_result is not None else None
        ),
        "arbitration_closure_fingerprint_sha256": (
            arbitration_closure.closure_fingerprint_sha256
            if arbitration_closure is not None
            else None
        ),
        "reservation_mutation_applied": reservation_mutation_applied,
        "admission_transitions_applied": admission_transitions_applied,
    }
    return MasterHistoricalReservationArbitrationResult(
        result_id=result_id,
        master_portfolio_id=plan.master_portfolio_id,
        plan_id=plan.plan_id,
        timeline_id=timeline.timeline_id,
        barrier_result_id=decision_barrier.barrier_result_id,
        barrier_sequence=decision_barrier.barrier_sequence,
        observed_at=decision_barrier.observed_at,
        status=status,
        plan_fingerprint_sha256=plan.fingerprint_sha256,
        timeline_fingerprint_sha256=timeline.fingerprint_sha256,
        decision_barrier_fingerprint_sha256=decision_barrier.fingerprint_sha256,
        allocation_policy_fingerprint_sha256=allocation_policy.fingerprint_sha256,
        gate_policy_fingerprint_sha256=gate_policy.fingerprint_sha256,
        arbitration_policy_fingerprint_sha256=arbitration_policy.fingerprint_sha256,
        opening_snapshot_fingerprint_sha256=opening_snapshot.fingerprint_sha256,
        portfolio_snapshot_fingerprint_sha256=portfolio_snapshot.fingerprint_sha256,
        initial_ledger_fingerprint_sha256=initial_ledger.fingerprint_sha256,
        post_reservation_ledger_fingerprint_sha256=post_reservation.fingerprint_sha256,
        final_ledger_fingerprint_sha256=final_ledger.fingerprint_sha256,
        candidate_seed_fingerprints_sha256=seed_fingerprints,
        attempts=ordered_attempts,
        candidates=ordered_candidates,
        arbitration_batch=arbitration_batch,
        arbitration_result=arbitration_result,
        arbitration_closure=arbitration_closure,
        reservation_mutation_applied=reservation_mutation_applied,
        admission_transitions_applied=admission_transitions_applied,
        fingerprint_sha256=stable_digest(payload),
    )


__all__ = [
    "MasterHistoricalCapitalRequirement",
    "MasterHistoricalCapitalRequirementSource",
    "MasterHistoricalReservationArbitrationResult",
    "MasterHistoricalReservationArbitrationStatus",
    "MasterHistoricalReservationAttempt",
    "MasterHistoricalReservationAttemptStatus",
    "bridge_master_historical_reservation_and_arbitration",
    "build_master_historical_capital_requirement",
    "master_historical_capital_requirement_fingerprint",
    "master_historical_reservation_arbitration_fingerprint",
    "master_historical_reservation_attempt_fingerprint",
]
