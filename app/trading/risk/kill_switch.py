from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from .models import KillSwitchState


class KillSwitch:
    """Small deterministic in-memory kill switch state holder.

    Persistence/API wiring is deliberately left to the surrounding service
    layer. The risk engine only consumes the immutable snapshot returned by
    :meth:`snapshot`.
    """

    def __init__(self) -> None:
        self._state = KillSwitchState()

    def snapshot(self) -> KillSwitchState:
        return self._state

    def stop_new_trades(self, *, reason: str) -> KillSwitchState:
        self._state = replace(
            self._state,
            stop_new_trades=True,
            reason=reason,
            activated_at=datetime.now(timezone.utc),
        )
        return self._state

    def stop_ai(self, *, reason: str) -> KillSwitchState:
        self._state = replace(
            self._state,
            stop_ai=True,
            reason=reason,
            activated_at=datetime.now(timezone.utc),
        )
        return self._state

    def emergency(self, *, reason: str) -> KillSwitchState:
        self._state = KillSwitchState(
            stop_new_trades=True,
            stop_ai=True,
            emergency_mode=True,
            reason=reason,
            activated_at=datetime.now(timezone.utc),
        )
        return self._state

    def reset(self) -> KillSwitchState:
        self._state = KillSwitchState()
        return self._state
