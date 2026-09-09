from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .models import MasterPortfolioSnapshot, SnapshotDataStatus


class PortfolioAuditSourceKind(StrEnum):
    MASTER_CAPITAL = "MASTER_CAPITAL"
    CREW_EXPOSURE = "CREW_EXPOSURE"


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
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return normalized


@dataclass(frozen=True, slots=True)
class PortfolioSourceAuditRecord:
    """Immutable provenance record derived from one source already present in a snapshot."""

    kind: PortfolioAuditSourceKind
    source: str
    status: SnapshotDataStatus
    source_ref: str | None = None
    system_id: str | None = None
    membership_ref: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _required_text(self.source, field_name="source"))
        object.__setattr__(
            self,
            "source_ref",
            _optional_text(self.source_ref, field_name="source_ref"),
        )
        object.__setattr__(
            self,
            "system_id",
            _optional_text(self.system_id, field_name="system_id"),
        )
        object.__setattr__(
            self,
            "membership_ref",
            _optional_text(self.membership_ref, field_name="membership_ref"),
        )
        object.__setattr__(
            self,
            "reason_code",
            _optional_text(self.reason_code, field_name="reason_code"),
        )

        if self.kind is PortfolioAuditSourceKind.MASTER_CAPITAL:
            if self.system_id is not None or self.membership_ref is not None:
                raise ValueError("MASTER_CAPITAL audit record cannot carry crew identity")
        elif self.kind is PortfolioAuditSourceKind.CREW_EXPOSURE:
            if self.system_id is None:
                raise ValueError("CREW_EXPOSURE audit record requires system_id")
        else:
            raise ValueError(f"unsupported audit source kind: {self.kind}")

        if self.status is SnapshotDataStatus.AVAILABLE:
            if self.reason_code is not None:
                raise ValueError("AVAILABLE audit source cannot carry reason_code")
        elif self.status is SnapshotDataStatus.UNAVAILABLE:
            if self.reason_code is None:
                raise ValueError("UNAVAILABLE audit source requires reason_code")
        else:
            raise ValueError(f"unsupported audit source status: {self.status}")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "source": self.source,
            "status": self.status,
            "source_ref": self.source_ref,
            "system_id": self.system_id,
            "membership_ref": self.membership_ref,
            "reason_code": self.reason_code,
        }


def _record_sort_key(record: PortfolioSourceAuditRecord) -> tuple[int, str]:
    priority = 0 if record.kind is PortfolioAuditSourceKind.MASTER_CAPITAL else 1
    return (priority, record.system_id or "")


def master_portfolio_audit_payload(
    *,
    master_portfolio_id: str,
    observed_at: datetime,
    snapshot_fingerprint_sha256: str,
    snapshot_status: SnapshotDataStatus,
    aggregate_exposure_status: SnapshotDataStatus,
    snapshot_reason_codes: tuple[str, ...],
    source_records: tuple[PortfolioSourceAuditRecord, ...],
    available_system_ids: tuple[str, ...],
    unavailable_system_ids: tuple[str, ...],
    schema_version: str,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-portfolio-audit-seal.v1",
        "schema_version": schema_version,
        "master_portfolio_id": master_portfolio_id,
        "observed_at": observed_at,
        "snapshot_fingerprint_sha256": snapshot_fingerprint_sha256,
        "snapshot_status": snapshot_status,
        "aggregate_exposure_status": aggregate_exposure_status,
        "snapshot_reason_codes": snapshot_reason_codes,
        "source_records": [record.canonical_payload() for record in source_records],
        "available_system_ids": available_system_ids,
        "unavailable_system_ids": unavailable_system_ids,
    }


def master_portfolio_audit_fingerprint(
    *,
    master_portfolio_id: str,
    observed_at: datetime,
    snapshot_fingerprint_sha256: str,
    snapshot_status: SnapshotDataStatus,
    aggregate_exposure_status: SnapshotDataStatus,
    snapshot_reason_codes: tuple[str, ...],
    source_records: tuple[PortfolioSourceAuditRecord, ...],
    available_system_ids: tuple[str, ...],
    unavailable_system_ids: tuple[str, ...],
    schema_version: str,
) -> str:
    return stable_digest(
        master_portfolio_audit_payload(
            master_portfolio_id=master_portfolio_id,
            observed_at=observed_at,
            snapshot_fingerprint_sha256=snapshot_fingerprint_sha256,
            snapshot_status=snapshot_status,
            aggregate_exposure_status=aggregate_exposure_status,
            snapshot_reason_codes=snapshot_reason_codes,
            source_records=source_records,
            available_system_ids=available_system_ids,
            unavailable_system_ids=unavailable_system_ids,
            schema_version=schema_version,
        )
    )


@dataclass(frozen=True, slots=True)
class MasterPortfolioAuditSeal:
    """Reproducible provenance seal for one already-built Master Portfolio snapshot."""

    master_portfolio_id: str
    observed_at: datetime
    snapshot_fingerprint_sha256: str
    snapshot_status: SnapshotDataStatus
    aggregate_exposure_status: SnapshotDataStatus
    snapshot_reason_codes: tuple[str, ...]
    source_records: tuple[PortfolioSourceAuditRecord, ...]
    available_system_ids: tuple[str, ...]
    unavailable_system_ids: tuple[str, ...]
    audit_fingerprint_sha256: str
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
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master Portfolio audit seal schema_version")
        object.__setattr__(
            self,
            "snapshot_fingerprint_sha256",
            _sha256(
                self.snapshot_fingerprint_sha256,
                field_name="snapshot_fingerprint_sha256",
            ),
        )
        object.__setattr__(
            self,
            "audit_fingerprint_sha256",
            _sha256(self.audit_fingerprint_sha256, field_name="audit_fingerprint_sha256"),
        )

        expected_records = tuple(sorted(self.source_records, key=_record_sort_key))
        if self.source_records != expected_records:
            raise ValueError("audit source_records must be in canonical order")
        master_records = tuple(
            record
            for record in self.source_records
            if record.kind is PortfolioAuditSourceKind.MASTER_CAPITAL
        )
        crew_records = tuple(
            record
            for record in self.source_records
            if record.kind is PortfolioAuditSourceKind.CREW_EXPOSURE
        )
        if len(master_records) != 1:
            raise ValueError("audit seal requires exactly one MASTER_CAPITAL source record")
        if not crew_records:
            raise ValueError("audit seal requires at least one CREW_EXPOSURE source record")
        crew_ids = tuple(record.system_id for record in crew_records)
        if any(system_id is None for system_id in crew_ids):
            raise ValueError("crew audit source records require system_id")
        normalized_crew_ids = tuple(system_id for system_id in crew_ids if system_id is not None)
        if len(set(normalized_crew_ids)) != len(normalized_crew_ids):
            raise ValueError("crew audit source system_id values must be unique")

        expected_available = tuple(
            record.system_id
            for record in crew_records
            if record.status is SnapshotDataStatus.AVAILABLE and record.system_id is not None
        )
        expected_unavailable = tuple(
            record.system_id
            for record in crew_records
            if record.status is SnapshotDataStatus.UNAVAILABLE and record.system_id is not None
        )
        if self.available_system_ids != expected_available:
            raise ValueError("available_system_ids do not match audit source records")
        if self.unavailable_system_ids != expected_unavailable:
            raise ValueError("unavailable_system_ids do not match audit source records")

        exposures_available = not expected_unavailable
        expected_aggregate_status = (
            SnapshotDataStatus.AVAILABLE
            if exposures_available
            else SnapshotDataStatus.UNAVAILABLE
        )
        if self.aggregate_exposure_status is not expected_aggregate_status:
            raise ValueError("aggregate_exposure_status does not match audit source records")
        master_available = master_records[0].status is SnapshotDataStatus.AVAILABLE
        expected_snapshot_status = (
            SnapshotDataStatus.AVAILABLE
            if master_available and exposures_available
            else SnapshotDataStatus.UNAVAILABLE
        )
        if self.snapshot_status is not expected_snapshot_status:
            raise ValueError("snapshot_status does not match audit source records")

        expected_reasons: list[str] = []
        master_record = master_records[0]
        if master_record.status is SnapshotDataStatus.UNAVAILABLE:
            assert master_record.reason_code is not None
            expected_reasons.append(
                f"MASTER_CAPITAL_UNAVAILABLE:{master_record.reason_code}"
            )
        for record in crew_records:
            if record.status is SnapshotDataStatus.UNAVAILABLE:
                assert record.system_id is not None
                assert record.reason_code is not None
                expected_reasons.append(
                    "CREW_EXPOSURE_UNAVAILABLE:"
                    f"{record.system_id}:{record.reason_code}"
                )
        canonical_reasons = tuple(sorted(expected_reasons))
        if self.snapshot_reason_codes != canonical_reasons:
            raise ValueError("snapshot_reason_codes do not match audit source records")

        expected_fingerprint = master_portfolio_audit_fingerprint(
            master_portfolio_id=self.master_portfolio_id,
            observed_at=self.observed_at,
            snapshot_fingerprint_sha256=self.snapshot_fingerprint_sha256,
            snapshot_status=self.snapshot_status,
            aggregate_exposure_status=self.aggregate_exposure_status,
            snapshot_reason_codes=self.snapshot_reason_codes,
            source_records=self.source_records,
            available_system_ids=self.available_system_ids,
            unavailable_system_ids=self.unavailable_system_ids,
            schema_version=self.schema_version,
        )
        if self.audit_fingerprint_sha256 != expected_fingerprint:
            raise ValueError("Master Portfolio audit fingerprint does not match payload")


def build_master_portfolio_audit_seal(
    snapshot: MasterPortfolioSnapshot,
) -> MasterPortfolioAuditSeal:
    """Seal snapshot provenance without re-reading any underlying provider or broker."""

    members = {member.system_id: member for member in snapshot.members}
    master_record = PortfolioSourceAuditRecord(
        kind=PortfolioAuditSourceKind.MASTER_CAPITAL,
        source=snapshot.master_capital.source,
        status=snapshot.master_capital.status,
        source_ref=snapshot.master_capital.source_ref,
        reason_code=snapshot.master_capital.reason_code,
    )
    crew_records = tuple(
        PortfolioSourceAuditRecord(
            kind=PortfolioAuditSourceKind.CREW_EXPOSURE,
            source=exposure.source,
            status=exposure.status,
            source_ref=exposure.source_ref,
            system_id=exposure.system_id,
            membership_ref=members[exposure.system_id].membership_ref,
            reason_code=exposure.reason_code,
        )
        for exposure in snapshot.crew_exposures
    )
    source_records = (master_record, *crew_records)
    available_system_ids = tuple(
        record.system_id
        for record in crew_records
        if record.status is SnapshotDataStatus.AVAILABLE and record.system_id is not None
    )
    unavailable_system_ids = tuple(
        record.system_id
        for record in crew_records
        if record.status is SnapshotDataStatus.UNAVAILABLE and record.system_id is not None
    )
    fingerprint = master_portfolio_audit_fingerprint(
        master_portfolio_id=snapshot.master_portfolio_id,
        observed_at=snapshot.observed_at,
        snapshot_fingerprint_sha256=snapshot.fingerprint_sha256,
        snapshot_status=snapshot.status,
        aggregate_exposure_status=snapshot.aggregate_exposure_status,
        snapshot_reason_codes=snapshot.reason_codes,
        source_records=source_records,
        available_system_ids=available_system_ids,
        unavailable_system_ids=unavailable_system_ids,
        schema_version="1.0",
    )
    return MasterPortfolioAuditSeal(
        master_portfolio_id=snapshot.master_portfolio_id,
        observed_at=snapshot.observed_at,
        snapshot_fingerprint_sha256=snapshot.fingerprint_sha256,
        snapshot_status=snapshot.status,
        aggregate_exposure_status=snapshot.aggregate_exposure_status,
        snapshot_reason_codes=snapshot.reason_codes,
        source_records=source_records,
        available_system_ids=available_system_ids,
        unavailable_system_ids=unavailable_system_ids,
        audit_fingerprint_sha256=fingerprint,
    )


__all__ = [
    "MasterPortfolioAuditSeal",
    "PortfolioAuditSourceKind",
    "PortfolioSourceAuditRecord",
    "build_master_portfolio_audit_seal",
    "master_portfolio_audit_fingerprint",
    "master_portfolio_audit_payload",
]
