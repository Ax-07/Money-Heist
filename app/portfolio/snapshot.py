from __future__ import annotations

from decimal import Decimal

from .models import (
    CrewExposureSnapshot,
    MasterCapitalSnapshot,
    MasterPortfolioSnapshot,
    PortfolioMemberRef,
    SnapshotDataStatus,
    _expected_reason_codes,
    master_portfolio_snapshot_fingerprint,
)


def build_master_portfolio_snapshot(
    *,
    master_capital: MasterCapitalSnapshot,
    members: tuple[PortfolioMemberRef, ...],
    crew_exposures: tuple[CrewExposureSnapshot, ...],
) -> MasterPortfolioSnapshot:
    """Build one canonical read-only snapshot without inventing missing portfolio data."""

    ordered_members = tuple(sorted(members, key=lambda item: item.system_id))
    ordered_exposures = tuple(sorted(crew_exposures, key=lambda item: item.system_id))

    member_ids = tuple(member.system_id for member in ordered_members)
    exposure_ids = tuple(exposure.system_id for exposure in ordered_exposures)
    if not ordered_members:
        raise ValueError("Master Portfolio requires at least one member")
    if len(set(member_ids)) != len(member_ids):
        raise ValueError("Master Portfolio member system_id values must be unique")
    if len(set(exposure_ids)) != len(exposure_ids):
        raise ValueError("crew exposure system_id values must be unique")
    if set(member_ids) != set(exposure_ids):
        raise ValueError("every Master Portfolio member requires exactly one crew exposure")
    if any(exposure.observed_at != master_capital.observed_at for exposure in ordered_exposures):
        raise ValueError("all Step 21a Step 1 inputs must share one observed_at")

    exposures_available = all(
        exposure.status is SnapshotDataStatus.AVAILABLE for exposure in ordered_exposures
    )
    aggregate_exposure_status = (
        SnapshotDataStatus.AVAILABLE if exposures_available else SnapshotDataStatus.UNAVAILABLE
    )

    if exposures_available:
        total_open_positions: int | None = sum(
            exposure.open_positions or 0 for exposure in ordered_exposures
        )
        total_gross_exposure_amount: Decimal | None = sum(
            (exposure.gross_exposure_amount or Decimal("0") for exposure in ordered_exposures),
            Decimal("0"),
        )
        total_open_risk_amount: Decimal | None = sum(
            (exposure.open_risk_amount or Decimal("0") for exposure in ordered_exposures),
            Decimal("0"),
        )
    else:
        total_open_positions = None
        total_gross_exposure_amount = None
        total_open_risk_amount = None

    status = (
        SnapshotDataStatus.AVAILABLE
        if master_capital.status is SnapshotDataStatus.AVAILABLE and exposures_available
        else SnapshotDataStatus.UNAVAILABLE
    )
    reason_codes = _expected_reason_codes(master_capital, ordered_exposures)

    fingerprint = master_portfolio_snapshot_fingerprint(
        master_portfolio_id=master_capital.master_portfolio_id,
        observed_at=master_capital.observed_at,
        members=ordered_members,
        master_capital=master_capital,
        crew_exposures=ordered_exposures,
        status=status,
        aggregate_exposure_status=aggregate_exposure_status,
        total_open_positions=total_open_positions,
        total_gross_exposure_amount=total_gross_exposure_amount,
        total_open_risk_amount=total_open_risk_amount,
        reason_codes=reason_codes,
        schema_version="1.0",
    )
    return MasterPortfolioSnapshot(
        master_portfolio_id=master_capital.master_portfolio_id,
        observed_at=master_capital.observed_at,
        members=ordered_members,
        master_capital=master_capital,
        crew_exposures=ordered_exposures,
        status=status,
        aggregate_exposure_status=aggregate_exposure_status,
        total_open_positions=total_open_positions,
        total_gross_exposure_amount=total_gross_exposure_amount,
        total_open_risk_amount=total_open_risk_amount,
        reason_codes=reason_codes,
        fingerprint_sha256=fingerprint,
    )
