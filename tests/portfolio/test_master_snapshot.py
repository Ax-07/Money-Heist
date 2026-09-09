from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.portfolio import (
    CrewExposureSnapshot,
    MasterCapitalSnapshot,
    PortfolioMemberRef,
    SnapshotDataStatus,
    build_master_portfolio_snapshot,
)

NOW = datetime(2026, 9, 9, 18, 0, tzinfo=UTC)


def capital(*, equity: str = "100") -> MasterCapitalSnapshot:
    value = Decimal(equity)
    return MasterCapitalSnapshot(
        master_portfolio_id="master-main",
        observed_at=NOW,
        status=SnapshotDataStatus.AVAILABLE,
        source="MASTER_ACCOUNT_FIXTURE",
        equity=value,
        cash_balance=value,
        day_start_equity=value,
        equity_peak=value,
        source_ref="fixture:capital",
    )


def exposure(
    system_id: str,
    *,
    gross: str,
    risk: str,
    positions: int = 1,
) -> CrewExposureSnapshot:
    return CrewExposureSnapshot(
        system_id=system_id,
        observed_at=NOW,
        status=SnapshotDataStatus.AVAILABLE,
        source="SYSTEM_EXPOSURE_FIXTURE",
        open_positions=positions,
        gross_exposure_amount=Decimal(gross),
        open_risk_amount=Decimal(risk),
        source_ref=f"fixture:{system_id}",
    )


def members(*system_ids: str) -> tuple[PortfolioMemberRef, ...]:
    return tuple(PortfolioMemberRef(system_id=system_id) for system_id in system_ids)


def test_master_capital_is_counted_once_across_multiple_crews() -> None:
    snapshot = build_master_portfolio_snapshot(
        master_capital=capital(equity="100"),
        members=members("crew-a", "crew-b", "crew-c"),
        crew_exposures=(
            exposure("crew-a", gross="30", risk="3"),
            exposure("crew-b", gross="20", risk="2"),
            exposure("crew-c", gross="10", risk="1"),
        ),
    )

    assert snapshot.master_capital.equity == Decimal("100")
    assert snapshot.total_gross_exposure_amount == Decimal("60")
    assert snapshot.total_open_risk_amount == Decimal("6")
    assert snapshot.total_open_positions == 3
    assert all(not hasattr(item, "equity") for item in snapshot.crew_exposures)


def test_builder_rejects_duplicate_member_system_ids() -> None:
    with pytest.raises(ValueError, match="member system_id values must be unique"):
        build_master_portfolio_snapshot(
            master_capital=capital(),
            members=members("crew-a", "crew-a"),
            crew_exposures=(exposure("crew-a", gross="10", risk="1"),),
        )


def test_builder_requires_exactly_one_exposure_per_member() -> None:
    with pytest.raises(ValueError, match="exactly one crew exposure"):
        build_master_portfolio_snapshot(
            master_capital=capital(),
            members=members("crew-a", "crew-b"),
            crew_exposures=(exposure("crew-a", gross="10", risk="1"),),
        )


def test_fingerprint_is_independent_of_input_order() -> None:
    first = build_master_portfolio_snapshot(
        master_capital=capital(),
        members=members("crew-b", "crew-a"),
        crew_exposures=(
            exposure("crew-b", gross="20", risk="2"),
            exposure("crew-a", gross="10", risk="1"),
        ),
    )
    second = build_master_portfolio_snapshot(
        master_capital=capital(),
        members=members("crew-a", "crew-b"),
        crew_exposures=(
            exposure("crew-a", gross="10", risk="1"),
            exposure("crew-b", gross="20", risk="2"),
        ),
    )

    assert tuple(member.system_id for member in first.members) == ("crew-a", "crew-b")
    assert first.fingerprint_sha256 == second.fingerprint_sha256


def test_material_exposure_change_changes_fingerprint() -> None:
    baseline = build_master_portfolio_snapshot(
        master_capital=capital(),
        members=members("crew-a"),
        crew_exposures=(exposure("crew-a", gross="10", risk="1"),),
    )
    changed = build_master_portfolio_snapshot(
        master_capital=capital(),
        members=members("crew-a"),
        crew_exposures=(exposure("crew-a", gross="11", risk="1"),),
    )

    assert baseline.fingerprint_sha256 != changed.fingerprint_sha256


def test_unavailable_exposure_does_not_invent_aggregate_values() -> None:
    unavailable = CrewExposureSnapshot(
        system_id="crew-b",
        observed_at=NOW,
        status=SnapshotDataStatus.UNAVAILABLE,
        source="SYSTEM_EXPOSURE_FIXTURE",
        reason_code="SOURCE_NOT_CONFIGURED",
    )
    snapshot = build_master_portfolio_snapshot(
        master_capital=capital(),
        members=members("crew-a", "crew-b"),
        crew_exposures=(
            exposure("crew-a", gross="10", risk="1"),
            unavailable,
        ),
    )

    assert snapshot.status is SnapshotDataStatus.UNAVAILABLE
    assert snapshot.aggregate_exposure_status is SnapshotDataStatus.UNAVAILABLE
    assert snapshot.total_open_positions is None
    assert snapshot.total_gross_exposure_amount is None
    assert snapshot.total_open_risk_amount is None
    assert snapshot.reason_codes == (
        "CREW_EXPOSURE_UNAVAILABLE:crew-b:SOURCE_NOT_CONFIGURED",
    )


def test_unavailable_inputs_cannot_carry_numeric_values() -> None:
    with pytest.raises(ValueError, match="cannot carry numeric exposure values"):
        CrewExposureSnapshot(
            system_id="crew-a",
            observed_at=NOW,
            status=SnapshotDataStatus.UNAVAILABLE,
            source="SYSTEM_EXPOSURE_FIXTURE",
            open_positions=0,
            gross_exposure_amount=Decimal("0"),
            open_risk_amount=Decimal("0"),
            reason_code="SOURCE_NOT_CONFIGURED",
        )


def test_builder_rejects_mixed_observation_times() -> None:
    other_time = datetime(2026, 9, 9, 18, 1, tzinfo=UTC)
    other = CrewExposureSnapshot(
        system_id="crew-a",
        observed_at=other_time,
        status=SnapshotDataStatus.AVAILABLE,
        source="SYSTEM_EXPOSURE_FIXTURE",
        open_positions=0,
        gross_exposure_amount=Decimal("0"),
        open_risk_amount=Decimal("0"),
    )

    with pytest.raises(ValueError, match="share one observed_at"):
        build_master_portfolio_snapshot(
            master_capital=capital(),
            members=members("crew-a"),
            crew_exposures=(other,),
        )


def test_contracts_are_immutable() -> None:
    item = PortfolioMemberRef(system_id="crew-a")
    with pytest.raises(FrozenInstanceError):
        item.system_id = "crew-b"  # type: ignore[misc]


def test_unavailable_master_capital_preserves_missing_values() -> None:
    missing_capital = MasterCapitalSnapshot(
        master_portfolio_id="master-main",
        observed_at=NOW,
        status=SnapshotDataStatus.UNAVAILABLE,
        source="MASTER_ACCOUNT_FIXTURE",
        reason_code="ACCOUNT_STATE_NOT_CONFIGURED",
    )
    snapshot = build_master_portfolio_snapshot(
        master_capital=missing_capital,
        members=members("crew-a"),
        crew_exposures=(exposure("crew-a", gross="10", risk="1"),),
    )

    assert snapshot.status is SnapshotDataStatus.UNAVAILABLE
    assert snapshot.master_capital.equity is None
    assert snapshot.total_gross_exposure_amount == Decimal("10")
    assert snapshot.reason_codes == (
        "MASTER_CAPITAL_UNAVAILABLE:ACCOUNT_STATE_NOT_CONFIGURED",
    )
