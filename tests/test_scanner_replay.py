from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.market.replay import opportunities_from_replay, replay_scanner


def synthetic_history() -> list[dict[str, object]]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles: list[dict[str, object]] = []
    price = 100.0
    for index in range(80):
        drift = 0.08 if index < 60 else 0.35
        price += drift
        volume = 1000.0
        if index in (61, 67, 73):
            volume = 2600.0
        high = price + (0.4 if index < 60 else 1.0)
        low = price - (0.4 if index < 60 else 1.0)
        candles.append(
            {
                "timestamp": start + timedelta(minutes=5 * index),
                "open": price - 0.1,
                "high": high,
                "low": low,
                "close": price,
                "volume": volume,
                "is_closed": True,
            }
        )
    return candles


def test_replay_is_fully_reproducible() -> None:
    history = synthetic_history()
    first = replay_scanner(
        history, symbol="SOLUSDT", timeframe="5m", system_id="balanced_v1"
    )
    second = replay_scanner(
        history, symbol="SOLUSDT", timeframe="5m", system_id="balanced_v1"
    )
    assert [point.feature_snapshot.model_dump() for point in first] == [
        point.feature_snapshot.model_dump() for point in second
    ]
    assert [opportunity.model_dump() for opportunity in opportunities_from_replay(first)] == [
        opportunity.model_dump() for opportunity in opportunities_from_replay(second)
    ]


def test_replay_never_uses_future_candles_for_earlier_snapshot() -> None:
    history = synthetic_history()
    base = replay_scanner(
        history, symbol="BTCUSDT", timeframe="5m", system_id="balanced_v1"
    )
    mutated = list(history)
    mutated[-1] = {**mutated[-1], "close": 999.0, "high": 1000.0, "volume": 999999.0}
    changed = replay_scanner(
        mutated, symbol="BTCUSDT", timeframe="5m", system_id="balanced_v1"
    )

    assert [point.feature_snapshot.model_dump() for point in base[:-1]] == [
        point.feature_snapshot.model_dump() for point in changed[:-1]
    ]
    assert base[-1].feature_snapshot.model_dump() != changed[-1].feature_snapshot.model_dump()
