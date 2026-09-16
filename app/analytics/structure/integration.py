from __future__ import annotations

from app.market.structure import MarketStructureContextV1

from .models import AnalyticsMarketStructureObservation


def project_money_heist_structure(
    context: MarketStructureContextV1,
) -> AnalyticsMarketStructureObservation:
    """Read-only projection; never recomputes production structure rules."""
    return AnalyticsMarketStructureObservation.create(context)


__all__ = ["project_money_heist_structure"]
