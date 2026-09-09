from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.portfolio import (
    CrewPortfolioStateSource,
    MasterCapitalSnapshot,
    MasterPortfolioFleetObserver,
    PortfolioMemberRef,
    PortfolioObservationReasonCode,
    SnapshotDataStatus,
)

NOW = datetime(2026, 9, 9, 21, 30, tzinfo=UTC)


class State:
    def __init__(
        self,
        *,
        positions: int = 1,
        gross: str = "10",
        risk: str = "1",
        local_equity: str = "100",
    ) -> None:
        self.open_positions = positions
        self.gross_exposure_amount = Decimal(gross)
        self.open_risk_amount = Decimal(risk)
        self.equity = Decimal(local_equity)


class RecordingProvider:
    def __init__(
        self,
        system_id: str,
        state: object | None,
        calls: list[str],
        *,
        fail: bool = False,
    ) -> None:
        self.system_id = system_id
        self.state = state
        self.calls = calls
        self.fail = fail

    def get_portfolio_state(self, *, system_id: str) -> object | None:
        self.calls.append(system_id)
        if self.fail:
            raise RuntimeError("synthetic read failure")
        return self.state


def member(system_id: str) -> PortfolioMemberRef:
    return PortfolioMemberRef(system_id=system_id, membership_ref=f"member:{system_id}")


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
        source_ref="fixture:master-capital",
    )


def source(
    system_id: str,
    provider: object,
    *,
    source_ref: str | None = None,
) -> CrewPortfolioStateSource:
    return CrewPortfolioStateSource(
        system_id=system_id,
        provider=provider,  # type: ignore[arg-type]
        source="PORTFOLIO_RISK_STATE",
        source_ref=source_ref or f"provider:{system_id}",
    )


def test_fleet_configuration_is_sorted_canonically() -> None:
    calls: list[str] = []
    observer = MasterPortfolioFleetObserver(
        members=(member("crew-c"), member("crew-a"), member("crew-b")),
        crew_sources=(
            source("crew-b", RecordingProvider("crew-b", State(), calls)),
            source("crew-c", RecordingProvider("crew-c", State(), calls)),
            source("crew-a", RecordingProvider("crew-a", State(), calls)),
        ),
    )

    assert observer.system_ids == ("crew-a", "crew-b", "crew-c")
    assert tuple(item.system_id for item in observer.crew_sources) == (
        "crew-a",
        "crew-b",
        "crew-c",
    )


def test_fleet_observes_sources_in_canonical_order_exactly_once() -> None:
    calls: list[str] = []
    observer = MasterPortfolioFleetObserver(
        members=(member("crew-b"), member("crew-a")),
        crew_sources=(
            source("crew-b", RecordingProvider("crew-b", State(), calls)),
            source("crew-a", RecordingProvider("crew-a", State(), calls)),
        ),
    )

    observer.observe(master_capital=capital())

    assert calls == ["crew-a", "crew-b"]


def test_one_failed_source_does_not_prevent_other_crew_observations() -> None:
    calls: list[str] = []
    observer = MasterPortfolioFleetObserver(
        members=(member("crew-a"), member("crew-b"), member("crew-c")),
        crew_sources=(
            source("crew-a", RecordingProvider("crew-a", State(gross="10"), calls)),
            source(
                "crew-b",
                RecordingProvider("crew-b", State(gross="20"), calls, fail=True),
            ),
            source("crew-c", RecordingProvider("crew-c", State(gross="30"), calls)),
        ),
    )

    snapshot = observer.observe(master_capital=capital())

    assert calls == ["crew-a", "crew-b", "crew-c"]
    assert snapshot.status is SnapshotDataStatus.UNAVAILABLE
    assert snapshot.total_gross_exposure_amount is None
    assert snapshot.crew_exposures[0].status is SnapshotDataStatus.AVAILABLE
    assert snapshot.crew_exposures[1].status is SnapshotDataStatus.UNAVAILABLE
    assert snapshot.crew_exposures[1].reason_code == (
        PortfolioObservationReasonCode.PORTFOLIO_STATE_READ_FAILED.value
    )
    assert snapshot.crew_exposures[2].status is SnapshotDataStatus.AVAILABLE


def test_missing_source_state_is_scoped_to_that_crew() -> None:
    calls: list[str] = []
    observer = MasterPortfolioFleetObserver(
        members=(member("crew-a"), member("crew-b")),
        crew_sources=(
            source("crew-a", RecordingProvider("crew-a", State(), calls)),
            source("crew-b", RecordingProvider("crew-b", None, calls)),
        ),
    )

    snapshot = observer.observe(master_capital=capital())

    unavailable = snapshot.crew_exposures[1]
    assert unavailable.system_id == "crew-b"
    assert unavailable.status is SnapshotDataStatus.UNAVAILABLE
    assert unavailable.reason_code == (
        PortfolioObservationReasonCode.PORTFOLIO_STATE_NOT_AVAILABLE.value
    )


def test_fleet_preserves_source_provenance_per_crew() -> None:
    calls: list[str] = []
    observer = MasterPortfolioFleetObserver(
        members=(member("crew-a"), member("crew-b")),
        crew_sources=(
            source(
                "crew-a",
                RecordingProvider("crew-a", State(), calls),
                source_ref="shadow:runtime:a",
            ),
            source(
                "crew-b",
                RecordingProvider("crew-b", State(), calls),
                source_ref="paper:provider:b",
            ),
        ),
    )

    snapshot = observer.observe(master_capital=capital())

    assert tuple(item.source_ref for item in snapshot.crew_exposures) == (
        "shadow:runtime:a",
        "paper:provider:b",
    )


def test_fleet_never_sums_local_crew_equities_into_master_capital() -> None:
    calls: list[str] = []
    observer = MasterPortfolioFleetObserver(
        members=(member("crew-a"), member("crew-b"), member("crew-c")),
        crew_sources=(
            source(
                "crew-a",
                RecordingProvider("crew-a", State(gross="30", local_equity="900"), calls),
            ),
            source(
                "crew-b",
                RecordingProvider("crew-b", State(gross="20", local_equity="800"), calls),
            ),
            source(
                "crew-c",
                RecordingProvider("crew-c", State(gross="10", local_equity="700"), calls),
            ),
        ),
    )

    snapshot = observer.observe(master_capital=capital(equity="100"))

    assert snapshot.master_capital.equity == Decimal("100")
    assert snapshot.total_gross_exposure_amount == Decimal("60")
    assert all(not hasattr(item, "equity") for item in snapshot.crew_exposures)


def test_fleet_observation_is_deterministic_across_configuration_input_order() -> None:
    first_calls: list[str] = []
    second_calls: list[str] = []
    first = MasterPortfolioFleetObserver(
        members=(member("crew-b"), member("crew-a")),
        crew_sources=(
            source(
                "crew-b",
                RecordingProvider("crew-b", State(gross="20", risk="2"), first_calls),
            ),
            source(
                "crew-a",
                RecordingProvider("crew-a", State(gross="10", risk="1"), first_calls),
            ),
        ),
    ).observe(master_capital=capital())
    second = MasterPortfolioFleetObserver(
        members=(member("crew-a"), member("crew-b")),
        crew_sources=(
            source(
                "crew-a",
                RecordingProvider("crew-a", State(gross="10", risk="1"), second_calls),
            ),
            source(
                "crew-b",
                RecordingProvider("crew-b", State(gross="20", risk="2"), second_calls),
            ),
        ),
    ).observe(master_capital=capital())

    assert first.fingerprint_sha256 == second.fingerprint_sha256
    assert first_calls == second_calls == ["crew-a", "crew-b"]


def test_fleet_rejects_duplicate_member_ids() -> None:
    calls: list[str] = []
    with pytest.raises(ValueError, match="fleet member system_id values must be unique"):
        MasterPortfolioFleetObserver(
            members=(member("crew-a"), member("crew-a")),
            crew_sources=(
                source("crew-a", RecordingProvider("crew-a", State(), calls)),
            ),
        )


def test_fleet_rejects_duplicate_source_ids() -> None:
    calls: list[str] = []
    first = source("crew-a", RecordingProvider("crew-a", State(), calls))
    second = source("crew-a", RecordingProvider("crew-a", State(), calls))
    with pytest.raises(ValueError, match="fleet source system_id values must be unique"):
        MasterPortfolioFleetObserver(
            members=(member("crew-a"),),
            crew_sources=(first, second),
        )


def test_fleet_requires_exactly_one_source_per_member() -> None:
    calls: list[str] = []
    with pytest.raises(ValueError, match="fleet member requires exactly one source"):
        MasterPortfolioFleetObserver(
            members=(member("crew-a"), member("crew-b")),
            crew_sources=(
                source("crew-a", RecordingProvider("crew-a", State(), calls)),
            ),
        )
