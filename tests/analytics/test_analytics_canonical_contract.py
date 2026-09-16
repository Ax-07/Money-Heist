from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from app.common.canonical import canonical_json, stable_digest, stable_uuid
from app.services.backtest.ids import (
    canonical_json as backtest_canonical_json,
)
from app.services.backtest.ids import (
    stable_digest as backtest_stable_digest,
)
from app.services.backtest.ids import (
    stable_uuid as backtest_stable_uuid,
)


def test_shared_canonicalization_preserves_backtest_golden_contract() -> None:
    payload = {
        "b": Decimal("1.2300"),
        "a": datetime(2026, 9, 16, 20, 0, tzinfo=timezone(timedelta(hours=2))),
        "nested": {"z": 0.0, "x": [True, None, "é"]},
    }

    expected_json = '{"a":"2026-09-16T18:00:00Z","b":"1.23","nested":{"x":[true,null,"é"],"z":"0"}}'
    expected_digest = "86ff78dee188e29a0548e29e3cf15a096c38cb6d19186f50360b44ce0b497851"
    expected_uuid = "29bac832-a2c4-5ad2-9f8f-5d1663b451b4"

    assert canonical_json(payload) == expected_json
    assert stable_digest(payload) == expected_digest
    assert stable_uuid("golden", payload) == expected_uuid
    assert backtest_canonical_json(payload) == expected_json
    assert backtest_stable_digest(payload) == expected_digest
    assert backtest_stable_uuid("golden", payload) == expected_uuid


def test_canonical_datetime_remains_utc_normalized() -> None:
    assert canonical_json(datetime(2026, 9, 16, 18, 0, tzinfo=UTC)) == ('"2026-09-16T18:00:00Z"')


def test_mapping_order_does_not_change_digest() -> None:
    assert stable_digest({"b": 2, "a": 1}) == stable_digest({"a": 1, "b": 2})
