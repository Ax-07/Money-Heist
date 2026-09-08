from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.services.backtest import ReplayIdFactory, canonical_json, stable_digest


def test_canonical_json_is_order_independent_for_mappings() -> None:
    first = {
        "b": Decimal("1.00"),
        "a": datetime(2026, 1, 1, tzinfo=UTC),
    }
    second = {
        "a": datetime(2026, 1, 1, tzinfo=UTC),
        "b": Decimal("1.0"),
    }

    assert canonical_json(first) == canonical_json(second)
    assert stable_digest(first) == stable_digest(second)


def test_replay_id_factory_is_reproducible_and_broker_compatible() -> None:
    first = ReplayIdFactory("run-123")
    second = ReplayIdFactory("run-123")

    assert first.next("fill") == second.next("fill")
    assert first() == second()
    assert first.next("order") == second.next("order")


def test_replay_id_factory_rejects_empty_seed() -> None:
    with pytest.raises(ValueError, match="seed"):
        ReplayIdFactory(" ")
