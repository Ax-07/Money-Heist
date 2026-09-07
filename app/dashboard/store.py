from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import Any, TypeVar

from fastapi import Request

from .models import DashboardSnapshot
from .projection import seeded_dashboard_snapshot


T = TypeVar("T")


class DashboardStore:
    """In-memory, bounded read-model history for Dashboard V1.

    Publishing is an internal backend operation only. Batch 12 exposes no HTTP
    endpoint that calls ``publish``. The store rejects anything claiming LIVE
    execution or a non-SHADOW system mode, and only retains observational history.
    """

    def __init__(
        self,
        initial: DashboardSnapshot | None = None,
        *,
        history_limit: int = 100,
        event_limit: int = 500,
    ) -> None:
        if history_limit < 1 or event_limit < 1:
            raise ValueError("dashboard history limits must be >= 1")
        self._lock = RLock()
        self._history_limit = history_limit
        self._event_limit = event_limit
        self._snapshot = initial or seeded_dashboard_snapshot()
        self._validate_observation_only(self._snapshot)

    def get(self) -> DashboardSnapshot:
        with self._lock:
            return self._snapshot

    def publish(self, snapshot: DashboardSnapshot) -> None:
        self._validate_observation_only(snapshot)
        with self._lock:
            previous = self._snapshot
            merged = snapshot.model_copy(
                update={
                    "opportunities": self._merge_bounded(
                        previous.opportunities,
                        snapshot.opportunities,
                        key=lambda item: (item.system_id, item.opportunity_id),
                        limit=self._history_limit,
                    ),
                    "decisions": self._merge_bounded(
                        previous.decisions,
                        snapshot.decisions,
                        key=lambda item: (item.system_id, item.opportunity_id),
                        limit=self._history_limit,
                    ),
                    "events": self._merge_bounded(
                        previous.events,
                        snapshot.events,
                        key=lambda item: item.event_id,
                        limit=self._event_limit,
                    ),
                }
            )
            self._validate_observation_only(merged)
            self._snapshot = merged

    @staticmethod
    def _merge_bounded(
        previous: tuple[T, ...],
        current: tuple[T, ...],
        *,
        key: Callable[[T], object],
        limit: int,
    ) -> tuple[T, ...]:
        ordered: dict[object, T] = {}
        for item in (*previous, *current):
            item_key = key(item)
            # Reinsert duplicates so the newest observation also moves to the end.
            ordered.pop(item_key, None)
            ordered[item_key] = item
        return tuple(ordered.values())[-limit:]

    @staticmethod
    def _validate_observation_only(snapshot: DashboardSnapshot) -> None:
        if not snapshot.read_only:
            raise ValueError("Dashboard V1 snapshot must be read-only")
        if snapshot.live_execution:
            raise ValueError("Dashboard V1 cannot publish LIVE execution state")
        if snapshot.execution_scope != "PAPER_SHADOW_ONLY":
            raise ValueError("Dashboard V1 accepts PAPER/SHADOW observations only")
        for system in snapshot.systems:
            if system.mode != "SHADOW" or system.execution_mode != "PAPER":
                raise ValueError("Dashboard V1 systems must remain SHADOW over PAPER")
            if system.live_execution:
                raise ValueError("Dashboard V1 cannot expose a system as LIVE")


def get_dashboard_store(request: Request) -> DashboardStore:
    """Return the app-local store, creating an unavailable seeded view lazily."""

    store: Any = getattr(request.app.state, "dashboard_store", None)
    if store is None:
        store = DashboardStore()
        request.app.state.dashboard_store = store
    if not isinstance(store, DashboardStore):
        raise RuntimeError("app.state.dashboard_store must be a DashboardStore")
    return store
