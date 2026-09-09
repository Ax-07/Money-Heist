from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from .models import (
    CrewExposureSnapshot,
    MasterCapitalSnapshot,
    MasterPortfolioSnapshot,
    PortfolioMemberRef,
    SnapshotDataStatus,
)
from .snapshot import build_master_portfolio_snapshot


class PortfolioStateProvider(Protocol):
    def get_portfolio_state(self, *, system_id: str) -> object | None: ...


class PortfolioObservationReasonCode(StrEnum):
    PORTFOLIO_STATE_NOT_AVAILABLE = "PORTFOLIO_STATE_NOT_AVAILABLE"
    PORTFOLIO_STATE_READ_FAILED = "PORTFOLIO_STATE_READ_FAILED"
    PORTFOLIO_STATE_INVALID = "PORTFOLIO_STATE_INVALID"


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


@dataclass(frozen=True, slots=True)
class CrewPortfolioStateSource:
    """Read-only binding between one Master member and its local risk-state provider."""

    system_id: str
    provider: PortfolioStateProvider
    source: str
    source_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "system_id",
            _required_text(self.system_id, field_name="system_id"),
        )
        object.__setattr__(
            self,
            "source",
            _required_text(self.source, field_name="source"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _optional_text(self.source_ref, field_name="source_ref"),
        )
        if not callable(getattr(self.provider, "get_portfolio_state", None)):
            raise ValueError("provider must expose get_portfolio_state(system_id=...)")


def _unavailable_exposure(
    *,
    source: CrewPortfolioStateSource,
    observed_at: datetime,
    reason_code: PortfolioObservationReasonCode,
) -> CrewExposureSnapshot:
    return CrewExposureSnapshot(
        system_id=source.system_id,
        observed_at=observed_at,
        status=SnapshotDataStatus.UNAVAILABLE,
        source=source.source,
        source_ref=source.source_ref,
        reason_code=reason_code.value,
    )


def observe_crew_exposure(
    *,
    source: CrewPortfolioStateSource,
    observed_at: datetime,
) -> CrewExposureSnapshot:
    """Project one existing local PortfolioRiskState into exposure-only Master data.

    Local equity, day-start equity, equity peak, daily PnL and correlated-risk inputs are
    deliberately ignored. They are local/counterfactual state and cannot become Master capital.
    """

    scoped_system_id = getattr(source.provider, "system_id", None)
    if scoped_system_id is not None and str(scoped_system_id).strip() != source.system_id:
        raise ValueError("provider system_id does not match observation source system_id")

    try:
        state = source.provider.get_portfolio_state(system_id=source.system_id)
    except Exception:
        return _unavailable_exposure(
            source=source,
            observed_at=observed_at,
            reason_code=PortfolioObservationReasonCode.PORTFOLIO_STATE_READ_FAILED,
        )

    if state is None:
        return _unavailable_exposure(
            source=source,
            observed_at=observed_at,
            reason_code=PortfolioObservationReasonCode.PORTFOLIO_STATE_NOT_AVAILABLE,
        )

    open_positions = getattr(state, "open_positions", None)
    gross_exposure_amount = getattr(state, "gross_exposure_amount", None)
    open_risk_amount = getattr(state, "open_risk_amount", None)
    values_are_typed = (
        isinstance(open_positions, int)
        and not isinstance(open_positions, bool)
        and isinstance(gross_exposure_amount, Decimal)
        and isinstance(open_risk_amount, Decimal)
    )
    if not values_are_typed:
        return _unavailable_exposure(
            source=source,
            observed_at=observed_at,
            reason_code=PortfolioObservationReasonCode.PORTFOLIO_STATE_INVALID,
        )

    return CrewExposureSnapshot(
        system_id=source.system_id,
        observed_at=observed_at,
        status=SnapshotDataStatus.AVAILABLE,
        source=source.source,
        open_positions=open_positions,
        gross_exposure_amount=gross_exposure_amount,
        open_risk_amount=open_risk_amount,
        source_ref=source.source_ref,
    )


def build_observed_master_portfolio_snapshot(
    *,
    master_capital: MasterCapitalSnapshot,
    members: tuple[PortfolioMemberRef, ...],
    crew_sources: tuple[CrewPortfolioStateSource, ...],
) -> MasterPortfolioSnapshot:
    """Observe all local crew providers at one explicit Master observation timestamp."""

    member_ids = tuple(member.system_id for member in members)
    source_ids = tuple(source.system_id for source in crew_sources)
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("crew observation source system_id values must be unique")
    if set(member_ids) != set(source_ids):
        raise ValueError("every Master Portfolio member requires one crew observation source")

    ordered_sources = tuple(sorted(crew_sources, key=lambda item: item.system_id))
    crew_exposures = tuple(
        observe_crew_exposure(source=source, observed_at=master_capital.observed_at)
        for source in ordered_sources
    )
    return build_master_portfolio_snapshot(
        master_capital=master_capital,
        members=members,
        crew_exposures=crew_exposures,
    )


__all__ = [
    "CrewPortfolioStateSource",
    "PortfolioObservationReasonCode",
    "PortfolioStateProvider",
    "build_observed_master_portfolio_snapshot",
    "observe_crew_exposure",
]
