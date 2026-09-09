from __future__ import annotations

from collections.abc import Iterable, Mapping
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


class CompositeSpecialistContextProvider:
    """Deterministically merge independent specialist context providers.

    Duplicate specialist keys are rejected instead of relying on provider order. This
    allows Rio and Denver to coexist without silently overwriting provenance.
    """

    def __init__(self, providers: Iterable[SpecialistContextProvider]) -> None:
        self.providers = tuple(providers)
        if not self.providers:
            raise ValueError("at least one specialist context provider is required")

    def contexts_for(
        self,
        *,
        opportunity: CandidateOpportunity,
        market_context: FeatureSnapshot,
    ) -> dict[str, Any]:
        combined: dict[str, Any] = {}
        for provider in self.providers:
            contexts = provider.contexts_for(
                opportunity=opportunity,
                market_context=market_context,
            )
            if not isinstance(contexts, Mapping):
                raise TypeError("specialist context provider must return a mapping")
            duplicates = sorted(set(combined) & set(contexts))
            if duplicates:
                raise ValueError(
                    "duplicate specialist context providers for: " + ", ".join(duplicates)
                )
            combined.update(contexts)
        return combined
