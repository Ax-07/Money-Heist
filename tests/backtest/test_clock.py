from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.services.backtest import ReplayClock


def test_replay_clock_is_utc_and_monotonic() -> None:
    paris = timezone(timedelta(hours=2))
    clock = ReplayClock.start(datetime(2026, 1, 1, 2, 0, tzinfo=paris))

    assert clock.now() == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert clock() == clock.now()

    advanced = clock.advance_to(datetime(2026, 1, 1, 0, 5, tzinfo=UTC))
    assert advanced == datetime(2026, 1, 1, 0, 5, tzinfo=UTC)

    with pytest.raises(ValueError, match="cannot move backwards"):
        clock.advance_to(datetime(2026, 1, 1, 0, 4, tzinfo=UTC))


def test_replay_clock_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ReplayClock.start(datetime(2026, 1, 1))
