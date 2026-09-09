from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .allocation import MasterAllocationPolicy
from .audit import build_master_portfolio_audit_seal
from .models import MasterPortfolioSnapshot
from .reconciliation import (
    ReservationReconciliationReport,
    ReservationReconciliationStatus,
)
from .reservation import (
    PortfolioReservation,
    ReservationLedgerSnapshot,
    ReservationRecordStatus,
)


class ReservationClosureSealStatus(StrEnum):
    SEALED = "SEALED"


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


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _sha256(value: str, *, field_name: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return normalized


def _transition_path(record: PortfolioReservation) -> tuple[ReservationRecordStatus, ...]:
    if record.status is ReservationRecordStatus.RESERVED:
        return (ReservationRecordStatus.RESERVED,)
    if record.status is ReservationRecordStatus.COMMITTED:
        return (
            ReservationRecordStatus.RESERVED,
            ReservationRecordStatus.COMMITTED,
        )
    if record.committed_at is None:
        return (
            ReservationRecordStatus.RESERVED,
            ReservationRecordStatus.RELEASED,
        )
    return (
        ReservationRecordStatus.RESERVED,
        ReservationRecordStatus.COMMITTED,
        ReservationRecordStatus.RELEASED,
    )


@dataclass(frozen=True, slots=True)
class ReservationLifecycleAuditRecord:
    reservation_id: str
    request_id: str
    request_fingerprint_sha256: str
    system_id: str
    status: ReservationRecordStatus
    transition_path: tuple[ReservationRecordStatus, ...]
    requested_at: datetime
    request_ref: str | None
    committed_at: datetime | None
    commit_ref: str | None
    released_at: datetime | None
    release_ref: str | None
    reservation_fingerprint_sha256: str
    audit_fingerprint_sha256: str

    def __post_init__(self) -> None:
        for field_name in ("reservation_id", "request_id", "system_id"):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "request_ref",
            _optional_text(self.request_ref, field_name="request_ref"),
        )
        object.__setattr__(
            self,
            "commit_ref",
            _optional_text(self.commit_ref, field_name="commit_ref"),
        )
        object.__setattr__(
            self,
            "release_ref",
            _optional_text(self.release_ref, field_name="release_ref"),
        )
        object.__setattr__(
            self,
            "requested_at",
            _utc(self.requested_at, field_name="requested_at"),
        )
        if self.committed_at is not None:
            object.__setattr__(
                self,
                "committed_at",
                _utc(self.committed_at, field_name="committed_at"),
            )
        if self.released_at is not None:
            object.__setattr__(
                self,
                "released_at",
                _utc(self.released_at, field_name="released_at"),
            )
        object.__setattr__(
            self,
            "request_fingerprint_sha256",
            _sha256(
                self.request_fingerprint_sha256,
                field_name="request_fingerprint_sha256",
            ),
        )
        object.__setattr__(
            self,
            "reservation_fingerprint_sha256",
            _sha256(
                self.reservation_fingerprint_sha256,
                field_name="reservation_fingerprint_sha256",
            ),
        )
        expected_path = _expected_transition_path_from_audit_record(self)
        if self.transition_path != expected_path:
            raise ValueError("reservation transition_path does not match lifecycle metadata")
        expected_fingerprint = reservation_lifecycle_audit_fingerprint(self)
        normalized = _sha256(
            self.audit_fingerprint_sha256,
            field_name="audit_fingerprint_sha256",
        )
        if normalized != expected_fingerprint:
            raise ValueError("reservation lifecycle audit fingerprint does not match payload")
        object.__setattr__(self, "audit_fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return reservation_lifecycle_audit_payload(self)


def _expected_transition_path_from_audit_record(
    record: ReservationLifecycleAuditRecord,
) -> tuple[ReservationRecordStatus, ...]:
    if record.status is ReservationRecordStatus.RESERVED:
        if any(
            value is not None
            for value in (
                record.committed_at,
                record.commit_ref,
                record.released_at,
                record.release_ref,
            )
        ):
            raise ValueError("RESERVED audit record cannot carry transition metadata")
        return (ReservationRecordStatus.RESERVED,)
    if record.status is ReservationRecordStatus.COMMITTED:
        if record.committed_at is None or record.commit_ref is None:
            raise ValueError("COMMITTED audit record requires commit metadata")
        if record.released_at is not None or record.release_ref is not None:
            raise ValueError("COMMITTED audit record cannot carry release metadata")
        return (
            ReservationRecordStatus.RESERVED,
            ReservationRecordStatus.COMMITTED,
        )
    if record.status is ReservationRecordStatus.RELEASED:
        if record.released_at is None or record.release_ref is None:
            raise ValueError("RELEASED audit record requires release metadata")
        if record.committed_at is None:
            if record.commit_ref is not None:
                raise ValueError("direct release cannot carry commit_ref")
            return (
                ReservationRecordStatus.RESERVED,
                ReservationRecordStatus.RELEASED,
            )
        if record.commit_ref is None:
            raise ValueError("committed release audit record requires commit_ref")
        return (
            ReservationRecordStatus.RESERVED,
            ReservationRecordStatus.COMMITTED,
            ReservationRecordStatus.RELEASED,
        )
    raise ValueError(f"unsupported reservation status: {record.status}")


def reservation_lifecycle_audit_payload(
    record: ReservationLifecycleAuditRecord,
) -> dict[str, object]:
    return {
        "schema": "money-heist.reservation-lifecycle-audit.v1",
        "reservation_id": record.reservation_id,
        "request_id": record.request_id,
        "request_fingerprint_sha256": record.request_fingerprint_sha256,
        "system_id": record.system_id,
        "status": record.status,
        "transition_path": record.transition_path,
        "requested_at": record.requested_at,
        "request_ref": record.request_ref,
        "committed_at": record.committed_at,
        "commit_ref": record.commit_ref,
        "released_at": record.released_at,
        "release_ref": record.release_ref,
        "reservation_fingerprint_sha256": record.reservation_fingerprint_sha256,
    }


def reservation_lifecycle_audit_fingerprint(
    record: ReservationLifecycleAuditRecord,
) -> str:
    return stable_digest(reservation_lifecycle_audit_payload(record))


def _build_lifecycle_record(record: PortfolioReservation) -> ReservationLifecycleAuditRecord:
    payload = {
        "schema": "money-heist.reservation-lifecycle-audit.v1",
        "reservation_id": record.reservation_id,
        "request_id": record.request.request_id,
        "request_fingerprint_sha256": record.request.fingerprint_sha256,
        "system_id": record.request.system_id,
        "status": record.status,
        "transition_path": _transition_path(record),
        "requested_at": record.request.requested_at,
        "request_ref": record.request.request_ref,
        "committed_at": record.committed_at,
        "commit_ref": record.commit_ref,
        "released_at": record.released_at,
        "release_ref": record.release_ref,
        "reservation_fingerprint_sha256": record.fingerprint_sha256,
    }
    return ReservationLifecycleAuditRecord(
        reservation_id=record.reservation_id,
        request_id=record.request.request_id,
        request_fingerprint_sha256=record.request.fingerprint_sha256,
        system_id=record.request.system_id,
        status=record.status,
        transition_path=_transition_path(record),
        requested_at=record.request.requested_at,
        request_ref=record.request.request_ref,
        committed_at=record.committed_at,
        commit_ref=record.commit_ref,
        released_at=record.released_at,
        release_ref=record.release_ref,
        reservation_fingerprint_sha256=record.fingerprint_sha256,
        audit_fingerprint_sha256=stable_digest(payload),
    )


@dataclass(frozen=True, slots=True)
class ReservationClosureSeal:
    master_portfolio_id: str
    ledger_master_portfolio_id: str
    opening_master_portfolio_id: str
    portfolio_master_portfolio_id: str
    sealed_at: datetime
    status: ReservationClosureSealStatus
    reconciliation_status: ReservationReconciliationStatus
    policy_id: str
    policy_source_ref: str | None
    policy_fingerprint_sha256: str
    ledger_policy_fingerprint_sha256: str
    opening_snapshot_fingerprint_sha256: str
    opening_snapshot_audit_fingerprint_sha256: str
    portfolio_snapshot_fingerprint_sha256: str
    portfolio_snapshot_audit_fingerprint_sha256: str
    ledger_snapshot_fingerprint_sha256: str
    reconciliation_fingerprint_sha256: str
    reservation_records: tuple[ReservationLifecycleAuditRecord, ...]
    reserved_count: int
    committed_count: int
    released_count: int
    reason_codes: tuple[str, ...]
    closure_fingerprint_sha256: str
    mutation_applied: bool = field(default=False, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    allocation_mutation: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "master_portfolio_id",
            _required_text(self.master_portfolio_id, field_name="master_portfolio_id"),
        )
        for field_name in (
            "ledger_master_portfolio_id",
            "opening_master_portfolio_id",
            "portfolio_master_portfolio_id",
            "policy_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "policy_source_ref",
            _optional_text(self.policy_source_ref, field_name="policy_source_ref"),
        )
        object.__setattr__(self, "sealed_at", _utc(self.sealed_at, field_name="sealed_at"))
        if self.status is not ReservationClosureSealStatus.SEALED:
            raise ValueError("reservation closure seal status must be SEALED")
        if self.schema_version != "1.0":
            raise ValueError("unsupported reservation closure seal schema_version")
        expected_order = tuple(
            sorted(self.reservation_records, key=lambda item: item.reservation_id)
        )
        if self.reservation_records != expected_order:
            raise ValueError("reservation closure records must be sorted by reservation_id")
        reservation_ids = tuple(item.reservation_id for item in self.reservation_records)
        if len(set(reservation_ids)) != len(reservation_ids):
            raise ValueError("reservation closure reservation_id values must be unique")
        expected_counts = {
            ReservationRecordStatus.RESERVED: sum(
                item.status is ReservationRecordStatus.RESERVED
                for item in self.reservation_records
            ),
            ReservationRecordStatus.COMMITTED: sum(
                item.status is ReservationRecordStatus.COMMITTED
                for item in self.reservation_records
            ),
            ReservationRecordStatus.RELEASED: sum(
                item.status is ReservationRecordStatus.RELEASED
                for item in self.reservation_records
            ),
        }
        if self.reserved_count != expected_counts[ReservationRecordStatus.RESERVED]:
            raise ValueError("reserved_count does not match reservation records")
        if self.committed_count != expected_counts[ReservationRecordStatus.COMMITTED]:
            raise ValueError("committed_count does not match reservation records")
        if self.released_count != expected_counts[ReservationRecordStatus.RELEASED]:
            raise ValueError("released_count does not match reservation records")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("closure reason_codes must be sorted and unique")
        for field_name in (
            "policy_fingerprint_sha256",
            "ledger_policy_fingerprint_sha256",
            "opening_snapshot_fingerprint_sha256",
            "opening_snapshot_audit_fingerprint_sha256",
            "portfolio_snapshot_fingerprint_sha256",
            "portfolio_snapshot_audit_fingerprint_sha256",
            "ledger_snapshot_fingerprint_sha256",
            "reconciliation_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        expected = reservation_closure_fingerprint(self)
        normalized = _sha256(
            self.closure_fingerprint_sha256,
            field_name="closure_fingerprint_sha256",
        )
        if normalized != expected:
            raise ValueError("reservation closure fingerprint does not match payload")
        object.__setattr__(self, "closure_fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return reservation_closure_payload(self)


def reservation_closure_payload(seal: ReservationClosureSeal) -> dict[str, object]:
    return {
        "schema": "money-heist.master-reservation-closure.v1",
        "schema_version": seal.schema_version,
        "master_portfolio_id": seal.master_portfolio_id,
        "ledger_master_portfolio_id": seal.ledger_master_portfolio_id,
        "opening_master_portfolio_id": seal.opening_master_portfolio_id,
        "portfolio_master_portfolio_id": seal.portfolio_master_portfolio_id,
        "sealed_at": seal.sealed_at,
        "status": seal.status,
        "reconciliation_status": seal.reconciliation_status,
        "policy_id": seal.policy_id,
        "policy_source_ref": seal.policy_source_ref,
        "policy_fingerprint_sha256": seal.policy_fingerprint_sha256,
        "ledger_policy_fingerprint_sha256": seal.ledger_policy_fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": seal.opening_snapshot_fingerprint_sha256,
        "opening_snapshot_audit_fingerprint_sha256": (
            seal.opening_snapshot_audit_fingerprint_sha256
        ),
        "portfolio_snapshot_fingerprint_sha256": seal.portfolio_snapshot_fingerprint_sha256,
        "portfolio_snapshot_audit_fingerprint_sha256": (
            seal.portfolio_snapshot_audit_fingerprint_sha256
        ),
        "ledger_snapshot_fingerprint_sha256": seal.ledger_snapshot_fingerprint_sha256,
        "reconciliation_fingerprint_sha256": seal.reconciliation_fingerprint_sha256,
        "reservation_records": [item.canonical_payload() for item in seal.reservation_records],
        "reserved_count": seal.reserved_count,
        "committed_count": seal.committed_count,
        "released_count": seal.released_count,
        "reason_codes": seal.reason_codes,
    }


def reservation_closure_fingerprint(seal: ReservationClosureSeal) -> str:
    return stable_digest(reservation_closure_payload(seal))


def _validate_closure_inputs(
    *,
    policy: MasterAllocationPolicy,
    opening_snapshot: MasterPortfolioSnapshot,
    portfolio_snapshot: MasterPortfolioSnapshot,
    ledger_snapshot: ReservationLedgerSnapshot,
    reconciliation_report: ReservationReconciliationReport,
) -> None:
    if opening_snapshot.fingerprint_sha256 != ledger_snapshot.opening_snapshot_fingerprint_sha256:
        raise ValueError("opening snapshot does not match ledger opening snapshot fingerprint")
    if reconciliation_report.policy_fingerprint_sha256 != policy.fingerprint_sha256:
        raise ValueError("reconciliation report does not match supplied policy fingerprint")
    if (
        reconciliation_report.ledger_snapshot_fingerprint_sha256
        != ledger_snapshot.fingerprint_sha256
    ):
        raise ValueError("reconciliation report does not match supplied ledger snapshot")
    if (
        reconciliation_report.portfolio_snapshot_fingerprint_sha256
        != portfolio_snapshot.fingerprint_sha256
    ):
        raise ValueError("reconciliation report does not match supplied portfolio snapshot")
    if (
        reconciliation_report.opening_snapshot_fingerprint_sha256
        != opening_snapshot.fingerprint_sha256
    ):
        raise ValueError("reconciliation report does not match supplied opening snapshot")
    if reconciliation_report.observed_at != portfolio_snapshot.observed_at:
        raise ValueError("reconciliation observed_at does not match portfolio snapshot")
    for record in ledger_snapshot.reservations:
        if record.master_portfolio_id != ledger_snapshot.master_portfolio_id:
            raise ValueError("reservation record master_portfolio_id differs from ledger")
        if record.policy_fingerprint_sha256 != ledger_snapshot.policy_fingerprint_sha256:
            raise ValueError("reservation record policy fingerprint differs from ledger")
        if (
            record.opening_snapshot_fingerprint_sha256
            != ledger_snapshot.opening_snapshot_fingerprint_sha256
        ):
            raise ValueError("reservation record opening snapshot fingerprint differs from ledger")


def build_reservation_closure_seal(
    *,
    policy: MasterAllocationPolicy,
    opening_snapshot: MasterPortfolioSnapshot,
    portfolio_snapshot: MasterPortfolioSnapshot,
    ledger_snapshot: ReservationLedgerSnapshot,
    reconciliation_report: ReservationReconciliationReport,
) -> ReservationClosureSeal:
    """Seal reservation evidence without mutating reservations or re-reading providers."""

    _validate_closure_inputs(
        policy=policy,
        opening_snapshot=opening_snapshot,
        portfolio_snapshot=portfolio_snapshot,
        ledger_snapshot=ledger_snapshot,
        reconciliation_report=reconciliation_report,
    )
    opening_audit = build_master_portfolio_audit_seal(opening_snapshot)
    portfolio_audit = build_master_portfolio_audit_seal(portfolio_snapshot)
    records = tuple(_build_lifecycle_record(item) for item in ledger_snapshot.reservations)
    reserved_count = sum(
        item.status is ReservationRecordStatus.RESERVED for item in records
    )
    committed_count = sum(
        item.status is ReservationRecordStatus.COMMITTED for item in records
    )
    released_count = sum(
        item.status is ReservationRecordStatus.RELEASED for item in records
    )
    payload = {
        "schema": "money-heist.master-reservation-closure.v1",
        "schema_version": "1.0",
        "master_portfolio_id": reconciliation_report.master_portfolio_id,
        "ledger_master_portfolio_id": ledger_snapshot.master_portfolio_id,
        "opening_master_portfolio_id": opening_snapshot.master_portfolio_id,
        "portfolio_master_portfolio_id": portfolio_snapshot.master_portfolio_id,
        "sealed_at": reconciliation_report.observed_at,
        "status": ReservationClosureSealStatus.SEALED,
        "reconciliation_status": reconciliation_report.status,
        "policy_id": policy.policy_id,
        "policy_source_ref": policy.source_ref,
        "policy_fingerprint_sha256": policy.fingerprint_sha256,
        "ledger_policy_fingerprint_sha256": ledger_snapshot.policy_fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": opening_snapshot.fingerprint_sha256,
        "opening_snapshot_audit_fingerprint_sha256": (
            opening_audit.audit_fingerprint_sha256
        ),
        "portfolio_snapshot_fingerprint_sha256": portfolio_snapshot.fingerprint_sha256,
        "portfolio_snapshot_audit_fingerprint_sha256": (
            portfolio_audit.audit_fingerprint_sha256
        ),
        "ledger_snapshot_fingerprint_sha256": ledger_snapshot.fingerprint_sha256,
        "reconciliation_fingerprint_sha256": reconciliation_report.fingerprint_sha256,
        "reservation_records": [item.canonical_payload() for item in records],
        "reserved_count": reserved_count,
        "committed_count": committed_count,
        "released_count": released_count,
        "reason_codes": reconciliation_report.reason_codes,
    }
    return ReservationClosureSeal(
        master_portfolio_id=reconciliation_report.master_portfolio_id,
        ledger_master_portfolio_id=ledger_snapshot.master_portfolio_id,
        opening_master_portfolio_id=opening_snapshot.master_portfolio_id,
        portfolio_master_portfolio_id=portfolio_snapshot.master_portfolio_id,
        sealed_at=reconciliation_report.observed_at,
        status=ReservationClosureSealStatus.SEALED,
        reconciliation_status=reconciliation_report.status,
        policy_id=policy.policy_id,
        policy_source_ref=policy.source_ref,
        policy_fingerprint_sha256=policy.fingerprint_sha256,
        ledger_policy_fingerprint_sha256=ledger_snapshot.policy_fingerprint_sha256,
        opening_snapshot_fingerprint_sha256=opening_snapshot.fingerprint_sha256,
        opening_snapshot_audit_fingerprint_sha256=(
            opening_audit.audit_fingerprint_sha256
        ),
        portfolio_snapshot_fingerprint_sha256=portfolio_snapshot.fingerprint_sha256,
        portfolio_snapshot_audit_fingerprint_sha256=(
            portfolio_audit.audit_fingerprint_sha256
        ),
        ledger_snapshot_fingerprint_sha256=ledger_snapshot.fingerprint_sha256,
        reconciliation_fingerprint_sha256=reconciliation_report.fingerprint_sha256,
        reservation_records=records,
        reserved_count=reserved_count,
        committed_count=committed_count,
        released_count=released_count,
        reason_codes=reconciliation_report.reason_codes,
        closure_fingerprint_sha256=stable_digest(payload),
    )


__all__ = [
    "ReservationClosureSeal",
    "ReservationClosureSealStatus",
    "ReservationLifecycleAuditRecord",
    "build_reservation_closure_seal",
    "reservation_closure_fingerprint",
    "reservation_lifecycle_audit_fingerprint",
]
