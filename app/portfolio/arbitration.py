from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .reservation import (
    PortfolioReservation,
    ReservationLedgerSnapshot,
    ReservationRecordStatus,
)
from .risk_gate import MasterRiskGateCandidate


class MasterArbitrationPolicyStatus(StrEnum):
    CONFIGURED = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class MasterArbitrationOrderStrategy(StrEnum):
    FIFO_RESERVATION_REQUEST = "FIFO_RESERVATION_REQUEST"


class MasterArbitrationPolicySource(StrEnum):
    OPERATOR_CONFIGURATION = "OPERATOR_CONFIGURATION"


class MasterArbitrationBatchStatus(StrEnum):
    READY = "READY"


def _required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank when provided")
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


def master_arbitration_policy_payload(
    *,
    master_portfolio_id: str,
    arbitration_policy_id: str,
    allocation_policy_fingerprint_sha256: str,
    status: MasterArbitrationPolicyStatus,
    order_strategy: MasterArbitrationOrderStrategy | None,
    reason_code: str | None,
    source: MasterArbitrationPolicySource,
    source_ref: str | None,
    schema_version: str,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-arbitration-policy.v1",
        "schema_version": schema_version,
        "master_portfolio_id": master_portfolio_id,
        "arbitration_policy_id": arbitration_policy_id,
        "allocation_policy_fingerprint_sha256": allocation_policy_fingerprint_sha256,
        "status": status,
        "order_strategy": order_strategy,
        "reason_code": reason_code,
        "source": source,
        "source_ref": source_ref,
    }


def master_arbitration_policy_fingerprint(**kwargs: object) -> str:
    return stable_digest(master_arbitration_policy_payload(**kwargs))


@dataclass(frozen=True, slots=True)
class MasterArbitrationPolicy:
    """Operator-owned ordering policy with no risk or execution authority."""

    master_portfolio_id: str
    arbitration_policy_id: str
    allocation_policy_fingerprint_sha256: str
    status: MasterArbitrationPolicyStatus
    fingerprint_sha256: str
    order_strategy: MasterArbitrationOrderStrategy | None = None
    reason_code: str | None = None
    source_ref: str | None = None
    source: MasterArbitrationPolicySource = field(
        default=MasterArbitrationPolicySource.OPERATOR_CONFIGURATION,
        init=False,
    )
    adaptive_ranking: bool = field(default=False, init=False)
    agent_influence: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "master_portfolio_id",
            _required_text(self.master_portfolio_id, field_name="master_portfolio_id"),
        )
        object.__setattr__(
            self,
            "arbitration_policy_id",
            _required_text(self.arbitration_policy_id, field_name="arbitration_policy_id"),
        )
        object.__setattr__(
            self,
            "allocation_policy_fingerprint_sha256",
            _sha256(
                self.allocation_policy_fingerprint_sha256,
                field_name="allocation_policy_fingerprint_sha256",
            ),
        )
        object.__setattr__(
            self,
            "reason_code",
            _optional_text(self.reason_code, field_name="reason_code"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _optional_text(self.source_ref, field_name="source_ref"),
        )
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master arbitration policy schema_version")

        if self.status is MasterArbitrationPolicyStatus.CONFIGURED:
            if self.order_strategy is None:
                raise ValueError("CONFIGURED arbitration policy requires order_strategy")
            if self.reason_code is not None:
                raise ValueError("CONFIGURED arbitration policy cannot carry reason_code")
        elif self.status is MasterArbitrationPolicyStatus.NOT_CONFIGURED:
            if self.order_strategy is not None:
                raise ValueError("NOT_CONFIGURED arbitration policy cannot carry order_strategy")
            if self.reason_code is None:
                raise ValueError("NOT_CONFIGURED arbitration policy requires reason_code")
        else:
            raise ValueError(f"unsupported Master arbitration policy status: {self.status}")

        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_arbitration_policy_fingerprint(
            master_portfolio_id=self.master_portfolio_id,
            arbitration_policy_id=self.arbitration_policy_id,
            allocation_policy_fingerprint_sha256=self.allocation_policy_fingerprint_sha256,
            status=self.status,
            order_strategy=self.order_strategy,
            reason_code=self.reason_code,
            source=self.source,
            source_ref=self.source_ref,
            schema_version=self.schema_version,
        )
        if normalized != expected:
            raise ValueError("Master arbitration policy fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def build_master_arbitration_policy(
    *,
    master_portfolio_id: str,
    arbitration_policy_id: str,
    allocation_policy_fingerprint_sha256: str,
    order_strategy: MasterArbitrationOrderStrategy | None = None,
    reason_code: str | None = None,
    source_ref: str | None = None,
) -> MasterArbitrationPolicy:
    normalized_master_id = _required_text(
        master_portfolio_id,
        field_name="master_portfolio_id",
    )
    normalized_policy_id = _required_text(
        arbitration_policy_id,
        field_name="arbitration_policy_id",
    )
    normalized_allocation_fingerprint = _sha256(
        allocation_policy_fingerprint_sha256,
        field_name="allocation_policy_fingerprint_sha256",
    )
    normalized_reason = _optional_text(reason_code, field_name="reason_code")
    normalized_source_ref = _optional_text(source_ref, field_name="source_ref")

    if order_strategy is None:
        status = MasterArbitrationPolicyStatus.NOT_CONFIGURED
        if normalized_reason is None:
            raise ValueError("NOT_CONFIGURED arbitration policy requires reason_code")
    else:
        status = MasterArbitrationPolicyStatus.CONFIGURED
        if normalized_reason is not None:
            raise ValueError("CONFIGURED arbitration policy cannot carry reason_code")

    source = MasterArbitrationPolicySource.OPERATOR_CONFIGURATION
    fingerprint = master_arbitration_policy_fingerprint(
        master_portfolio_id=normalized_master_id,
        arbitration_policy_id=normalized_policy_id,
        allocation_policy_fingerprint_sha256=normalized_allocation_fingerprint,
        status=status,
        order_strategy=order_strategy,
        reason_code=normalized_reason,
        source=source,
        source_ref=normalized_source_ref,
        schema_version="1.0",
    )
    return MasterArbitrationPolicy(
        master_portfolio_id=normalized_master_id,
        arbitration_policy_id=normalized_policy_id,
        allocation_policy_fingerprint_sha256=normalized_allocation_fingerprint,
        status=status,
        order_strategy=order_strategy,
        reason_code=normalized_reason,
        source_ref=normalized_source_ref,
        fingerprint_sha256=fingerprint,
    )


def master_arbitration_entry_payload(entry: MasterArbitrationEntry) -> dict[str, object]:
    return {
        "schema": "money-heist.master-arbitration-entry.v1",
        "schema_version": entry.schema_version,
        "rank": entry.rank,
        "system_id": entry.system_id,
        "proposal_id": entry.proposal_id,
        "reservation_id": entry.reservation_id,
        "local_risk_created_at": entry.local_risk_created_at,
        "reservation_requested_at": entry.reservation_requested_at,
        "candidate_fingerprint_sha256": entry.candidate_fingerprint_sha256,
        "reservation_fingerprint_sha256": entry.reservation_fingerprint_sha256,
    }


def master_arbitration_entry_fingerprint(entry: MasterArbitrationEntry) -> str:
    return stable_digest(master_arbitration_entry_payload(entry))


@dataclass(frozen=True, slots=True)
class MasterArbitrationEntry:
    rank: int
    system_id: str
    proposal_id: str
    reservation_id: str
    local_risk_created_at: datetime
    reservation_requested_at: datetime
    candidate_fingerprint_sha256: str
    reservation_fingerprint_sha256: str
    fingerprint_sha256: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError("arbitration entry rank must be >= 1")
        for field_name in ("system_id", "proposal_id", "reservation_id"):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "candidate_fingerprint_sha256",
            "reservation_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "local_risk_created_at",
            _utc(self.local_risk_created_at, field_name="local_risk_created_at"),
        )
        object.__setattr__(
            self,
            "reservation_requested_at",
            _utc(self.reservation_requested_at, field_name="reservation_requested_at"),
        )
        if self.reservation_requested_at < self.local_risk_created_at:
            raise ValueError("reservation request cannot precede local Risk decision")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master arbitration entry schema_version")

        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_arbitration_entry_fingerprint(self)
        if normalized != expected:
            raise ValueError("Master arbitration entry fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def master_arbitration_batch_payload(batch: MasterArbitrationBatch) -> dict[str, object]:
    return {
        "schema": "money-heist.master-arbitration-batch.v1",
        "schema_version": batch.schema_version,
        "master_portfolio_id": batch.master_portfolio_id,
        "batch_id": batch.batch_id,
        "created_at": batch.created_at,
        "status": batch.status,
        "order_strategy": batch.order_strategy,
        "arbitration_policy_fingerprint_sha256": (
            batch.arbitration_policy_fingerprint_sha256
        ),
        "allocation_policy_fingerprint_sha256": (
            batch.allocation_policy_fingerprint_sha256
        ),
        "source_ledger_fingerprint_sha256": batch.source_ledger_fingerprint_sha256,
        "entries": [master_arbitration_entry_payload(entry) for entry in batch.entries],
    }


def master_arbitration_batch_fingerprint(batch: MasterArbitrationBatch) -> str:
    return stable_digest(master_arbitration_batch_payload(batch))


@dataclass(frozen=True, slots=True)
class MasterArbitrationBatch:
    """Immutable ordered view of explicitly supplied concurrent candidates."""

    master_portfolio_id: str
    batch_id: str
    created_at: datetime
    status: MasterArbitrationBatchStatus
    order_strategy: MasterArbitrationOrderStrategy
    arbitration_policy_fingerprint_sha256: str
    allocation_policy_fingerprint_sha256: str
    source_ledger_fingerprint_sha256: str
    entries: tuple[MasterArbitrationEntry, ...]
    fingerprint_sha256: str
    mutation_applied: bool = field(default=False, init=False)
    adaptive_ranking: bool = field(default=False, init=False)
    agent_influence: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "master_portfolio_id",
            _required_text(self.master_portfolio_id, field_name="master_portfolio_id"),
        )
        object.__setattr__(
            self,
            "batch_id",
            _required_text(self.batch_id, field_name="batch_id"),
        )
        object.__setattr__(self, "created_at", _utc(self.created_at, field_name="created_at"))
        for field_name in (
            "arbitration_policy_fingerprint_sha256",
            "allocation_policy_fingerprint_sha256",
            "source_ledger_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        if self.status is not MasterArbitrationBatchStatus.READY:
            raise ValueError("Master arbitration batch status must be READY")
        if not self.entries:
            raise ValueError("Master arbitration batch requires at least one entry")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master arbitration batch schema_version")

        expected_ranks = tuple(range(1, len(self.entries) + 1))
        actual_ranks = tuple(entry.rank for entry in self.entries)
        if actual_ranks != expected_ranks:
            raise ValueError("Master arbitration batch ranks must be contiguous from 1")
        if len({entry.reservation_id for entry in self.entries}) != len(self.entries):
            raise ValueError("Master arbitration batch reservation_id values must be unique")
        if len({entry.candidate_fingerprint_sha256 for entry in self.entries}) != len(
            self.entries
        ):
            raise ValueError("Master arbitration batch candidate fingerprints must be unique")
        proposal_keys = {(entry.system_id, entry.proposal_id) for entry in self.entries}
        if len(proposal_keys) != len(self.entries):
            raise ValueError("Master arbitration batch system/proposal keys must be unique")

        expected_order = tuple(sorted(self.entries, key=_entry_sort_key))
        if self.entries != expected_order:
            raise ValueError("Master arbitration batch entries do not match declared strategy")
        if self.created_at < max(entry.reservation_requested_at for entry in self.entries):
            raise ValueError("arbitration batch cannot precede a reservation request")

        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_arbitration_batch_fingerprint(self)
        if normalized != expected:
            raise ValueError("Master arbitration batch fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def _entry_sort_key(entry: MasterArbitrationEntry) -> tuple[object, ...]:
    return (
        entry.reservation_requested_at,
        entry.system_id,
        entry.proposal_id,
        entry.reservation_id,
    )


def _candidate_reservation(
    *,
    candidate: MasterRiskGateCandidate,
    ledger_snapshot: ReservationLedgerSnapshot,
) -> PortfolioReservation:
    if not candidate.local_risk_authorized or candidate.reservation_id is None:
        raise ValueError("arbitration batch accepts only locally authorized candidates")
    reservation = next(
        (
            item
            for item in ledger_snapshot.reservations
            if item.reservation_id == candidate.reservation_id
        ),
        None,
    )
    if reservation is None:
        raise ValueError("arbitration candidate reservation is missing from ledger snapshot")
    if reservation.status is not ReservationRecordStatus.RESERVED:
        raise ValueError("arbitration candidate reservation must still be RESERVED")
    request = reservation.request
    if (
        reservation.master_portfolio_id != candidate.master_portfolio_id
        or reservation.policy_fingerprint_sha256 != ledger_snapshot.policy_fingerprint_sha256
        or request.system_id != candidate.system_id
        or request.request_ref != candidate.proposal_id
        or request.requested_at < candidate.local_risk_created_at
        or request.open_risk_amount != candidate.local_approved_risk_amount
        or request.gross_exposure_amount != candidate.local_approved_notional
    ):
        raise ValueError("arbitration candidate does not match its reservation payload")
    return reservation


def build_master_arbitration_batch(
    *,
    policy: MasterArbitrationPolicy,
    candidates: tuple[MasterRiskGateCandidate, ...],
    ledger_snapshot: ReservationLedgerSnapshot,
    created_at: datetime,
) -> MasterArbitrationBatch:
    """Build a deterministic FIFO batch from an explicitly supplied candidate set.

    This function does not decide which requests are concurrent. The caller supplies that set.
    It only validates and orders the set according to the operator-owned policy.
    """

    normalized_time = _utc(created_at, field_name="created_at")
    if policy.status is not MasterArbitrationPolicyStatus.CONFIGURED:
        raise ValueError("Master arbitration policy must be CONFIGURED")
    if policy.order_strategy is not MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST:
        raise ValueError("unsupported Master arbitration order strategy")
    if not candidates:
        raise ValueError("Master arbitration batch requires at least one candidate")
    if policy.master_portfolio_id != ledger_snapshot.master_portfolio_id:
        raise ValueError("arbitration policy and ledger belong to different Master Portfolios")
    if (
        policy.allocation_policy_fingerprint_sha256
        != ledger_snapshot.policy_fingerprint_sha256
    ):
        raise ValueError("arbitration policy and ledger use different allocation policies")

    if any(candidate.master_portfolio_id != policy.master_portfolio_id for candidate in candidates):
        raise ValueError("all arbitration candidates must belong to the policy Master Portfolio")
    candidate_fingerprints = [candidate.fingerprint_sha256 for candidate in candidates]
    if len(set(candidate_fingerprints)) != len(candidate_fingerprints):
        raise ValueError("arbitration candidate fingerprints must be unique")

    pairs = [
        (
            candidate,
            _candidate_reservation(candidate=candidate, ledger_snapshot=ledger_snapshot),
        )
        for candidate in candidates
    ]
    reservation_ids = [reservation.reservation_id for _, reservation in pairs]
    if len(set(reservation_ids)) != len(reservation_ids):
        raise ValueError("arbitration candidates cannot share a reservation")
    proposal_keys = [(candidate.system_id, candidate.proposal_id) for candidate, _ in pairs]
    if len(set(proposal_keys)) != len(proposal_keys):
        raise ValueError("arbitration candidates cannot duplicate a system/proposal key")

    ordered_pairs = sorted(
        pairs,
        key=lambda pair: (
            pair[1].request.requested_at,
            pair[0].system_id,
            pair[0].proposal_id,
            pair[1].reservation_id,
        ),
    )
    entries: list[MasterArbitrationEntry] = []
    for rank, (candidate, reservation) in enumerate(ordered_pairs, start=1):
        payload = {
            "schema": "money-heist.master-arbitration-entry.v1",
            "schema_version": "1.0",
            "rank": rank,
            "system_id": candidate.system_id,
            "proposal_id": candidate.proposal_id,
            "reservation_id": reservation.reservation_id,
            "local_risk_created_at": candidate.local_risk_created_at,
            "reservation_requested_at": reservation.request.requested_at,
            "candidate_fingerprint_sha256": candidate.fingerprint_sha256,
            "reservation_fingerprint_sha256": reservation.fingerprint_sha256,
        }
        entries.append(
            MasterArbitrationEntry(
                rank=rank,
                system_id=candidate.system_id,
                proposal_id=candidate.proposal_id,
                reservation_id=reservation.reservation_id,
                local_risk_created_at=candidate.local_risk_created_at,
                reservation_requested_at=reservation.request.requested_at,
                candidate_fingerprint_sha256=candidate.fingerprint_sha256,
                reservation_fingerprint_sha256=reservation.fingerprint_sha256,
                fingerprint_sha256=stable_digest(payload),
            )
        )

    batch_id = "arbitration:" + stable_digest(
        {
            "schema": "money-heist.master-arbitration-batch-id.v1",
            "master_portfolio_id": policy.master_portfolio_id,
            "arbitration_policy_fingerprint_sha256": policy.fingerprint_sha256,
            "source_ledger_fingerprint_sha256": ledger_snapshot.fingerprint_sha256,
            "created_at": normalized_time,
            "entry_fingerprints": [entry.fingerprint_sha256 for entry in entries],
        }
    )
    batch_payload = {
        "schema": "money-heist.master-arbitration-batch.v1",
        "schema_version": "1.0",
        "master_portfolio_id": policy.master_portfolio_id,
        "batch_id": batch_id,
        "created_at": normalized_time,
        "status": MasterArbitrationBatchStatus.READY,
        "order_strategy": policy.order_strategy,
        "arbitration_policy_fingerprint_sha256": policy.fingerprint_sha256,
        "allocation_policy_fingerprint_sha256": (
            policy.allocation_policy_fingerprint_sha256
        ),
        "source_ledger_fingerprint_sha256": ledger_snapshot.fingerprint_sha256,
        "entries": [master_arbitration_entry_payload(entry) for entry in entries],
    }
    return MasterArbitrationBatch(
        master_portfolio_id=policy.master_portfolio_id,
        batch_id=batch_id,
        created_at=normalized_time,
        status=MasterArbitrationBatchStatus.READY,
        order_strategy=policy.order_strategy,
        arbitration_policy_fingerprint_sha256=policy.fingerprint_sha256,
        allocation_policy_fingerprint_sha256=policy.allocation_policy_fingerprint_sha256,
        source_ledger_fingerprint_sha256=ledger_snapshot.fingerprint_sha256,
        entries=tuple(entries),
        fingerprint_sha256=stable_digest(batch_payload),
    )


__all__ = [
    "MasterArbitrationBatch",
    "MasterArbitrationBatchStatus",
    "MasterArbitrationEntry",
    "MasterArbitrationOrderStrategy",
    "MasterArbitrationPolicy",
    "MasterArbitrationPolicySource",
    "MasterArbitrationPolicyStatus",
    "build_master_arbitration_batch",
    "build_master_arbitration_policy",
    "master_arbitration_batch_fingerprint",
    "master_arbitration_entry_fingerprint",
    "master_arbitration_policy_fingerprint",
]
