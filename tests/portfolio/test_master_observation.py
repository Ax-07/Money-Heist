from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.portfolio import (
    CrewPortfolioStateSource,
    MasterCapitalSnapshot,
    PortfolioMemberRef,
    PortfolioObservationReasonCode,
    SnapshotDataStatus,
    build_observed_master_portfolio_snapshot,
    observe_crew_exposure,
)
from app.services.paper_pipeline.providers import InMemoryPortfolioRiskStateProvider
from app.services.shadow.providers import MutableShadowPortfolioProvider
from app.trading.risk.models import PortfolioRiskState

NOW = datetime(2026, 9, 9, 20, 30, tzinfo=UTC)


def risk_state(
    *,
    equity: str = "100",
    gross: str = "0",
    risk: str = "0",
    positions: int = 0,
) -> PortfolioRiskState:
    return PortfolioRiskState(
        equity=Decimal(equity),
        day_start_equity=Decimal(equity),
        equity_peak=Decimal(equity),
        daily_pnl=Decimal("0"),
        open_positions=positions,
        open_risk_amount=Decimal(risk),
        correlated_risk_amount=Decimal("999"),
        gross_exposure_amount=Decimal(gross),
    )


def master_capital(*, equity: str = "100") -> MasterCapitalSnapshot:
    value = Decimal(equity)
    return MasterCapitalSnapshot(
        master_portfolio_id="master-main",
        observed_at=NOW,
        status=SnapshotDataStatus.AVAILABLE,
        source="MASTER_CAPITAL_FIXTURE",
        equity=value,
        cash_balance=value,
        day_start_equity=value,
        equity_peak=value,
        source_ref="fixture:master-capital",
    )


def member(system_id: str) -> PortfolioMemberRef:
    return PortfolioMemberRef(system_id=system_id)


def test_paper_provider_projects_only_exposure_fields() -> None:
    provider = InMemoryPortfolioRiskStateProvider(
        {"crew-a": risk_state(equity="700", gross="30", risk="3", positions=2)}
    )

    exposure = observe_crew_exposure(
        source=CrewPortfolioStateSource(
            system_id="crew-a",
            provider=provider,
            source="PAPER_PORTFOLIO_RISK_STATE",
            source_ref="paper:crew-a",
        ),
        observed_at=NOW,
    )

    assert exposure.status is SnapshotDataStatus.AVAILABLE
    assert exposure.open_positions == 2
    assert exposure.gross_exposure_amount == Decimal("30")
    assert exposure.open_risk_amount == Decimal("3")
    assert not hasattr(exposure, "equity")
    assert not hasattr(exposure, "correlated_risk_amount")


def test_shadow_provider_is_observed_as_exposure_not_capital() -> None:
    provider = MutableShadowPortfolioProvider(
        system_id="shadow-a",
        _state=risk_state(equity="999", gross="40", risk="4", positions=1),
    )

    exposure = observe_crew_exposure(
        source=CrewPortfolioStateSource(
            system_id="shadow-a",
            provider=provider,
            source="SHADOW_PORTFOLIO_RISK_STATE",
        ),
        observed_at=NOW,
    )

    assert exposure.gross_exposure_amount == Decimal("40")
    assert exposure.open_risk_amount == Decimal("4")
    assert not hasattr(exposure, "equity")


def test_missing_local_state_becomes_unavailable_without_invented_zeroes() -> None:
    provider = InMemoryPortfolioRiskStateProvider({})

    exposure = observe_crew_exposure(
        source=CrewPortfolioStateSource(
            system_id="crew-a",
            provider=provider,
            source="PAPER_PORTFOLIO_RISK_STATE",
        ),
        observed_at=NOW,
    )

    assert exposure.status is SnapshotDataStatus.UNAVAILABLE
    assert exposure.reason_code == PortfolioObservationReasonCode.PORTFOLIO_STATE_NOT_AVAILABLE
    assert exposure.open_positions is None
    assert exposure.gross_exposure_amount is None
    assert exposure.open_risk_amount is None


def test_provider_read_failure_becomes_unavailable() -> None:
    class BrokenProvider:
        def get_portfolio_state(self, *, system_id: str) -> object | None:
            raise RuntimeError(system_id)

    exposure = observe_crew_exposure(
        source=CrewPortfolioStateSource(
            system_id="crew-a",
            provider=BrokenProvider(),
            source="BROKEN_FIXTURE",
        ),
        observed_at=NOW,
    )

    assert exposure.status is SnapshotDataStatus.UNAVAILABLE
    assert exposure.reason_code == PortfolioObservationReasonCode.PORTFOLIO_STATE_READ_FAILED


def test_malformed_local_state_becomes_unavailable() -> None:
    class InvalidProvider:
        def get_portfolio_state(self, *, system_id: str) -> object | None:
            return object()

    exposure = observe_crew_exposure(
        source=CrewPortfolioStateSource(
            system_id="crew-a",
            provider=InvalidProvider(),
            source="INVALID_FIXTURE",
        ),
        observed_at=NOW,
    )

    assert exposure.status is SnapshotDataStatus.UNAVAILABLE
    assert exposure.reason_code == PortfolioObservationReasonCode.PORTFOLIO_STATE_INVALID


def test_scoped_provider_system_id_mismatch_is_rejected() -> None:
    provider = MutableShadowPortfolioProvider(
        system_id="shadow-a",
        _state=risk_state(),
    )

    with pytest.raises(ValueError, match="provider system_id does not match"):
        observe_crew_exposure(
            source=CrewPortfolioStateSource(
                system_id="shadow-b",
                provider=provider,
                source="SHADOW_PORTFOLIO_RISK_STATE",
            ),
            observed_at=NOW,
        )


def test_master_capital_is_not_summed_from_shadow_counterfactual_equities() -> None:
    source_a = CrewPortfolioStateSource(
        system_id="shadow-a",
        provider=MutableShadowPortfolioProvider(
            system_id="shadow-a",
            _state=risk_state(equity="100", gross="30", risk="3"),
        ),
        source="SHADOW_PORTFOLIO_RISK_STATE",
    )
    source_b = CrewPortfolioStateSource(
        system_id="shadow-b",
        provider=MutableShadowPortfolioProvider(
            system_id="shadow-b",
            _state=risk_state(equity="100", gross="20", risk="2"),
        ),
        source="SHADOW_PORTFOLIO_RISK_STATE",
    )

    snapshot = build_observed_master_portfolio_snapshot(
        master_capital=master_capital(equity="100"),
        members=(member("shadow-a"), member("shadow-b")),
        crew_sources=(source_a, source_b),
    )

    assert snapshot.master_capital.equity == Decimal("100")
    assert snapshot.total_gross_exposure_amount == Decimal("50")
    assert snapshot.total_open_risk_amount == Decimal("5")
    assert all(not hasattr(exposure, "equity") for exposure in snapshot.crew_exposures)


def test_observed_snapshot_is_deterministic_across_source_order() -> None:
    source_a = CrewPortfolioStateSource(
        system_id="crew-a",
        provider=InMemoryPortfolioRiskStateProvider(
            {"crew-a": risk_state(gross="10", risk="1")}
        ),
        source="PAPER_PORTFOLIO_RISK_STATE",
    )
    source_b = CrewPortfolioStateSource(
        system_id="crew-b",
        provider=InMemoryPortfolioRiskStateProvider(
            {"crew-b": risk_state(gross="20", risk="2")}
        ),
        source="PAPER_PORTFOLIO_RISK_STATE",
    )

    first = build_observed_master_portfolio_snapshot(
        master_capital=master_capital(),
        members=(member("crew-b"), member("crew-a")),
        crew_sources=(source_b, source_a),
    )
    second = build_observed_master_portfolio_snapshot(
        master_capital=master_capital(),
        members=(member("crew-a"), member("crew-b")),
        crew_sources=(source_a, source_b),
    )

    assert first.fingerprint_sha256 == second.fingerprint_sha256


def test_observed_snapshot_requires_one_source_per_member() -> None:
    source = CrewPortfolioStateSource(
        system_id="crew-a",
        provider=InMemoryPortfolioRiskStateProvider({"crew-a": risk_state()}),
        source="PAPER_PORTFOLIO_RISK_STATE",
    )

    with pytest.raises(ValueError, match="requires one crew observation source"):
        build_observed_master_portfolio_snapshot(
            master_capital=master_capital(),
            members=(member("crew-a"), member("crew-b")),
            crew_sources=(source,),
        )


def test_observed_snapshot_rejects_duplicate_sources() -> None:
    source = CrewPortfolioStateSource(
        system_id="crew-a",
        provider=InMemoryPortfolioRiskStateProvider({"crew-a": risk_state()}),
        source="PAPER_PORTFOLIO_RISK_STATE",
    )

    with pytest.raises(ValueError, match="source system_id values must be unique"):
        build_observed_master_portfolio_snapshot(
            master_capital=master_capital(),
            members=(member("crew-a"),),
            crew_sources=(source, source),
        )
