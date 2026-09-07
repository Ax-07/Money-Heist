from __future__ import annotations

import asyncio
from app.dashboard.observer import DashboardShadowObserver
from app.dashboard.projection import ShadowDashboardProjector, seeded_dashboard_snapshot
from app.dashboard.store import DashboardStore

from ._helpers import NOW, fake_fleet_result, fake_runner


class Runner:
    def __init__(self):
        base = fake_runner()
        self.runtimes = base.runtimes
        self.result = fake_fleet_result()
        self.calls = 0

    async def run(self, **kwargs):
        self.calls += 1
        return self.result

    def paper_history(self, system_id):
        return (system_id,)


class BrokenProjector:
    async def capture(self, **kwargs):
        raise RuntimeError("dashboard unavailable")


def test_observer_publishes_snapshot_after_shadow_run():
    runner = Runner()
    store = DashboardStore(seeded_dashboard_snapshot(clock=lambda: NOW))
    observer = DashboardShadowObserver(
        runner,
        store,
        projector=ShadowDashboardProjector(clock=lambda: NOW),
    )
    result = asyncio.run(observer.run(root_opportunity=object(), market_context=object()))
    assert result is runner.result
    assert runner.calls == 1
    assert store.get().root_opportunity_id == "root-1"
    assert observer.last_projection_error is None


def test_observer_projection_failure_never_replaces_shadow_result():
    runner = Runner()
    seeded = seeded_dashboard_snapshot(clock=lambda: NOW)
    store = DashboardStore(seeded)
    observer = DashboardShadowObserver(runner, store, projector=BrokenProjector())
    result = asyncio.run(observer.run(root_opportunity=object(), market_context=object()))
    assert result is runner.result
    assert store.get() is seeded
    assert observer.last_projection_error == "RuntimeError: dashboard unavailable"


def test_observer_preserves_runner_read_interfaces():
    runner = Runner()
    observer = DashboardShadowObserver(runner, DashboardStore())
    assert observer.runtimes is runner.runtimes
    assert observer.paper_history("shadow_balanced_v1") == ("shadow_balanced_v1",)
