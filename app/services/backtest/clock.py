from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


def as_utc(value: datetime, *, field: str = "datetime") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(slots=True)
class ReplayClock:
    """Monotonic UTC clock controlled exclusively by historical replay."""

    _current: datetime

    def __post_init__(self) -> None:
        self._current = as_utc(self._current, field="start_at")

    @classmethod
    def start(cls, start_at: datetime) -> ReplayClock:
        return cls(start_at)

    def now(self) -> datetime:
        return self._current

    def advance_to(self, observed_at: datetime) -> datetime:
        target = as_utc(observed_at, field="observed_at")
        if target < self._current:
            raise ValueError("ReplayClock cannot move backwards")
        self._current = target
        return self._current

    def __call__(self) -> datetime:
        """Callable form compatible with broker/pipeline clock injection."""
        return self.now()
