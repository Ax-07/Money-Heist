from __future__ import annotations

import logging
from typing import Any

from .projection import ShadowDashboardProjector
from .store import DashboardStore


logger = logging.getLogger(__name__)


class DashboardShadowObserver:
    """Non-authoritative decorator for a Batch 11 ``ShadowFleetRunner``.

    The wrapped fleet result is always returned unchanged. A dashboard projection
    failure is logged and never turns a completed PAPER/SHADOW run into a failure.
    """

    def __init__(
        self,
        runner: Any,
        store: DashboardStore,
        *,
        projector: ShadowDashboardProjector | None = None,
    ) -> None:
        self._runner = runner
        self._store = store
        self._projector = projector or ShadowDashboardProjector()
        self.last_projection_error: str | None = None

    @property
    def runtimes(self):
        return self._runner.runtimes

    def paper_history(self, system_id: str):
        return self._runner.paper_history(system_id)

    async def run(self, **kwargs: Any):
        result = await self._runner.run(**kwargs)
        try:
            snapshot = await self._projector.capture(runner=self._runner, fleet_result=result)
            self._store.publish(snapshot)
            self.last_projection_error = None
        except Exception as exc:  # observability must not acquire business authority
            self.last_projection_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Dashboard projection failed after SHADOW run",
                extra={"event": "dashboard_projection_failed", "error_type": type(exc).__name__},
                exc_info=True,
            )
        return result
