from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.orchestration import CompositeSpecialistContextProvider


class Provider:
    def __init__(self, payload) -> None:
        self.payload = payload
        self.calls = 0

    def contexts_for(self, *, opportunity, market_context):
        self.calls += 1
        return dict(self.payload)


def test_composite_merges_rio_and_denver_without_order_dependent_overwrite() -> None:
    rio = Provider({"rio": {"source": "real-derivatives"}})
    denver = Provider({"denver": {"stats_id": "stats-1"}})
    composite = CompositeSpecialistContextProvider((rio, denver))

    result = composite.contexts_for(
        opportunity=SimpleNamespace(),
        market_context=SimpleNamespace(),
    )

    assert result == {
        "rio": {"source": "real-derivatives"},
        "denver": {"stats_id": "stats-1"},
    }
    assert rio.calls == 1
    assert denver.calls == 1


def test_composite_rejects_duplicate_specialist_keys() -> None:
    composite = CompositeSpecialistContextProvider(
        (
            Provider({"rio": {"source": "one"}}),
            Provider({"rio": {"source": "two"}}),
        )
    )

    with pytest.raises(ValueError, match="duplicate specialist context"):
        composite.contexts_for(
            opportunity=SimpleNamespace(),
            market_context=SimpleNamespace(),
        )


def test_composite_rejects_empty_provider_set() -> None:
    with pytest.raises(ValueError, match="at least one"):
        CompositeSpecialistContextProvider(())
