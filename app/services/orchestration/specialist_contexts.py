from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from app.market.features.models import FeatureSnapshot
from app.market.scanner.models import CandidateOpportunity


class SpecialistContextProvider(Protocol):
    """Read-only deterministic source of optional per-specialist grounded context."""

    def contexts_for(
        self,
        *,
        opportunity: CandidateOpportunity,
        market_context: FeatureSnapshot,
    ) -> Mapping[str, Any]: ...
