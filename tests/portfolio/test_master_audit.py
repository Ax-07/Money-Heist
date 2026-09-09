from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.portfolio import (
    CrewExposureSnapshot,
    MasterCapitalSnapshot,
    MasterPortfolioAuditSeal,
    PortfolioAuditSourceKind,
    PortfolioMemberRef,
    PortfolioSourceAuditRecord,
    SnapshotDataStatus,
    build_master_portfolio_audit_seal,
    build_master_portfolio_snapshot,
)

NOW = datetime(2026, 9, 9, 22, 30, tzinfo=UTC)


def member(system_id: str, *, membership_ref: str | None = None) -> PortfolioMemberRef:
    return PortfolioMemberRef(
        system_id=system_id,
        membership_ref=membership_ref or f"member:{system_id}",
    )


def capital(
    *,
    source_ref: str = "master:account:main",
    status: SnapshotDataStatus = SnapshotDataStatus.AVAILABLE,
) -> MasterCapitalSnapshot:
    if status is SnapshotDataStatus.UNAVAILABLE:
        return MasterCapitalSnapshot(
            master_portfolio_id="master-main",
            observed_at=NOW,
            status=status,
            source="MASTER_ACCOUNT",
            source_ref=source_ref,
            reason_code="MASTER_STATE_UNAVAILABLE",
        )
    return MasterCapitalSnapshot(
        master_portfolio_id="master-main",
        observed_at=NOW,
        status=status,
        source="MASTER_ACCOUNT",
        equity=Decimal("100"),
        cash_balance=Decimal("80"),
        day_start_equity=Decimal("100"),
        equity_peak=Decimal("105"),
        source_ref=source_ref,
    )


def exposure(
    system_id: str,
    *,
    source_ref: str | None = None,
    status: SnapshotDataStatus = SnapshotDataStatus.AVAILABLE,
) -> CrewExposureSnapshot:
    if status is SnapshotDataStatus.UNAVAILABLE:
        return CrewExposureSnapshot(
            system_id=system_id,
            observed_at=NOW,
            status=status,
            source="PORTFOLIO_RISK_STATE",
            source_ref=source_ref or f"provider:{system_id}",
            reason_code="PORTFOLIO_STATE_NOT_AVAILABLE",
        )
    return CrewExposureSnapshot(
        system_id=system_id,
        observed_at=NOW,
        status=status,
        source="PORTFOLIO_RISK_STATE",
        open_positions=1,
        gross_exposure_amount=Decimal("10"),
        open_risk_amount=Decimal("1"),
        source_ref=source_ref or f"provider:{system_id}",
    )


def snapshot(
    *,
    master_capital: MasterCapitalSnapshot | None = None,
    crew_a: CrewExposureSnapshot | None = None,
    crew_b: CrewExposureSnapshot | None = None,
    reverse_input: bool = False,
):
    members = (member("crew-a"), member("crew-b"))
    exposures = (
        crew_a or exposure("crew-a"),
        crew_b or exposure("crew-b"),
    )
    if reverse_input:
        members = tuple(reversed(members))
        exposures = tuple(reversed(exposures))
    return build_master_portfolio_snapshot(
        master_capital=master_capital or capital(),
        members=members,
        crew_exposures=exposures,
    )


def test_audit_seal_records_exactly_one_master_source_and_each_crew() -> None:
    seal = build_master_portfolio_audit_seal(snapshot())

    assert tuple(record.kind for record in seal.source_records) == (
        PortfolioAuditSourceKind.MASTER_CAPITAL,
        PortfolioAuditSourceKind.CREW_EXPOSURE,
        PortfolioAuditSourceKind.CREW_EXPOSURE,
    )
    assert tuple(record.system_id for record in seal.source_records) == (
        None,
        "crew-a",
        "crew-b",
    )


def test_audit_seal_preserves_source_and_membership_provenance() -> None:
    seal = build_master_portfolio_audit_seal(
        snapshot(
            master_capital=capital(source_ref="master:ledger:42"),
            crew_a=exposure("crew-a", source_ref="shadow:runtime:a"),
            crew_b=exposure("crew-b", source_ref="paper:provider:b"),
        )
    )

    master_record, crew_a, crew_b = seal.source_records
    assert master_record.source_ref == "master:ledger:42"
    assert crew_a.source_ref == "shadow:runtime:a"
    assert crew_a.membership_ref == "member:crew-a"
    assert crew_b.source_ref == "paper:provider:b"
    assert crew_b.membership_ref == "member:crew-b"


def test_audit_seal_preserves_availability_without_inventing_values() -> None:
    seal = build_master_portfolio_audit_seal(
        snapshot(crew_b=exposure("crew-b", status=SnapshotDataStatus.UNAVAILABLE))
    )

    assert seal.snapshot_status is SnapshotDataStatus.UNAVAILABLE
    assert seal.aggregate_exposure_status is SnapshotDataStatus.UNAVAILABLE
    assert seal.available_system_ids == ("crew-a",)
    assert seal.unavailable_system_ids == ("crew-b",)
    assert seal.source_records[2].reason_code == "PORTFOLIO_STATE_NOT_AVAILABLE"


def test_master_capital_unavailability_is_explicitly_sealed() -> None:
    seal = build_master_portfolio_audit_seal(
        snapshot(master_capital=capital(status=SnapshotDataStatus.UNAVAILABLE))
    )

    master_record = seal.source_records[0]
    assert master_record.status is SnapshotDataStatus.UNAVAILABLE
    assert master_record.reason_code == "MASTER_STATE_UNAVAILABLE"
    assert seal.snapshot_status is SnapshotDataStatus.UNAVAILABLE


def test_equivalent_snapshot_input_order_produces_same_audit_fingerprint() -> None:
    first = build_master_portfolio_audit_seal(snapshot())
    second = build_master_portfolio_audit_seal(snapshot(reverse_input=True))

    assert first.snapshot_fingerprint_sha256 == second.snapshot_fingerprint_sha256
    assert first.audit_fingerprint_sha256 == second.audit_fingerprint_sha256


def test_material_source_provenance_change_changes_audit_fingerprint() -> None:
    first = build_master_portfolio_audit_seal(snapshot())
    second = build_master_portfolio_audit_seal(
        snapshot(crew_a=exposure("crew-a", source_ref="provider:crew-a:v2"))
    )

    assert first.audit_fingerprint_sha256 != second.audit_fingerprint_sha256


def test_material_membership_change_changes_audit_fingerprint() -> None:
    base = snapshot()
    changed = build_master_portfolio_snapshot(
        master_capital=base.master_capital,
        members=(
            member("crew-a", membership_ref="membership:crew-a:v2"),
            member("crew-b"),
        ),
        crew_exposures=base.crew_exposures,
    )

    first = build_master_portfolio_audit_seal(base)
    second = build_master_portfolio_audit_seal(changed)

    assert first.audit_fingerprint_sha256 != second.audit_fingerprint_sha256


def test_audit_seal_is_immutable() -> None:
    seal = build_master_portfolio_audit_seal(snapshot())

    with pytest.raises(FrozenInstanceError):
        seal.master_portfolio_id = "other"  # type: ignore[misc]


def test_tampered_audit_fingerprint_is_rejected() -> None:
    seal = build_master_portfolio_audit_seal(snapshot())

    with pytest.raises(ValueError, match="audit fingerprint does not match payload"):
        replace(seal, audit_fingerprint_sha256="0" * 64)


def test_audit_record_rejects_unavailable_source_without_reason() -> None:
    with pytest.raises(ValueError, match="UNAVAILABLE audit source requires reason_code"):
        PortfolioSourceAuditRecord(
            kind=PortfolioAuditSourceKind.CREW_EXPOSURE,
            source="PORTFOLIO_RISK_STATE",
            status=SnapshotDataStatus.UNAVAILABLE,
            system_id="crew-a",
        )


def test_audit_record_rejects_master_source_with_crew_identity() -> None:
    with pytest.raises(ValueError, match="cannot carry crew identity"):
        PortfolioSourceAuditRecord(
            kind=PortfolioAuditSourceKind.MASTER_CAPITAL,
            source="MASTER_ACCOUNT",
            status=SnapshotDataStatus.AVAILABLE,
            system_id="crew-a",
        )


def test_seal_rejects_noncanonical_source_record_order() -> None:
    seal = build_master_portfolio_audit_seal(snapshot())
    reversed_records = tuple(reversed(seal.source_records))

    with pytest.raises(ValueError, match="canonical order"):
        MasterPortfolioAuditSeal(
            master_portfolio_id=seal.master_portfolio_id,
            observed_at=seal.observed_at,
            snapshot_fingerprint_sha256=seal.snapshot_fingerprint_sha256,
            snapshot_status=seal.snapshot_status,
            aggregate_exposure_status=seal.aggregate_exposure_status,
            snapshot_reason_codes=seal.snapshot_reason_codes,
            source_records=reversed_records,
            available_system_ids=seal.available_system_ids,
            unavailable_system_ids=seal.unavailable_system_ids,
            audit_fingerprint_sha256=seal.audit_fingerprint_sha256,
        )


def test_seal_rejects_snapshot_status_inconsistent_with_sources() -> None:
    seal = build_master_portfolio_audit_seal(snapshot())

    with pytest.raises(ValueError, match="snapshot_status does not match audit source records"):
        replace(seal, snapshot_status=SnapshotDataStatus.UNAVAILABLE)


def test_seal_rejects_reason_codes_inconsistent_with_sources() -> None:
    seal = build_master_portfolio_audit_seal(
        snapshot(crew_b=exposure("crew-b", status=SnapshotDataStatus.UNAVAILABLE))
    )

    with pytest.raises(ValueError, match="reason_codes do not match audit source records"):
        replace(seal, snapshot_reason_codes=())
