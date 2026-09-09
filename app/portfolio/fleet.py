from __future__ import annotations

from dataclasses import dataclass

from .models import MasterCapitalSnapshot, MasterPortfolioSnapshot, PortfolioMemberRef
from .observation import CrewPortfolioStateSource, observe_crew_exposure
from .snapshot import build_master_portfolio_snapshot


@dataclass(frozen=True, slots=True)
class MasterPortfolioFleetObserver:
    """Reusable read-only orchestration for one explicitly configured crew fleet.

    The observer owns no capital, allocation, reservation, Risk, broker, or LIVE authority.
    It only freezes membership/source wiring, observes each source in canonical system order,
    then delegates aggregation and fingerprinting to the existing Master Portfolio builder.
    """

    members: tuple[PortfolioMemberRef, ...]
    crew_sources: tuple[CrewPortfolioStateSource, ...]

    def __post_init__(self) -> None:
        ordered_members = tuple(sorted(self.members, key=lambda item: item.system_id))
        ordered_sources = tuple(sorted(self.crew_sources, key=lambda item: item.system_id))

        member_ids = tuple(member.system_id for member in ordered_members)
        source_ids = tuple(source.system_id for source in ordered_sources)
        if not ordered_members:
            raise ValueError("Master Portfolio fleet observer requires at least one member")
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("Master Portfolio fleet member system_id values must be unique")
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("Master Portfolio fleet source system_id values must be unique")
        if set(member_ids) != set(source_ids):
            raise ValueError("every Master Portfolio fleet member requires exactly one source")

        object.__setattr__(self, "members", ordered_members)
        object.__setattr__(self, "crew_sources", ordered_sources)

    @property
    def system_ids(self) -> tuple[str, ...]:
        return tuple(member.system_id for member in self.members)

    def observe(self, *, master_capital: MasterCapitalSnapshot) -> MasterPortfolioSnapshot:
        """Observe each configured crew exactly once at the Master capital timestamp."""

        crew_exposures = tuple(
            observe_crew_exposure(source=source, observed_at=master_capital.observed_at)
            for source in self.crew_sources
        )
        return build_master_portfolio_snapshot(
            master_capital=master_capital,
            members=self.members,
            crew_exposures=crew_exposures,
        )


__all__ = ["MasterPortfolioFleetObserver"]
