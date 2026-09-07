from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.dashboard.projection import seeded_dashboard_snapshot
from app.dashboard.store import DashboardStore


NOW = datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc)


def test_store_returns_seeded_snapshot():
    snapshot = seeded_dashboard_snapshot(clock=lambda: NOW)
    store = DashboardStore(snapshot)
    assert store.get() is snapshot


def test_store_publish_replaces_snapshot():
    first = seeded_dashboard_snapshot(clock=lambda: NOW)
    second = first.model_copy(update={"system_state": "OBSERVABLE"})
    store = DashboardStore(first)
    store.publish(second)
    assert store.get().system_state == "OBSERVABLE"


def test_store_rejects_live_execution_flag():
    snapshot = seeded_dashboard_snapshot(clock=lambda: NOW).model_copy(
        update={"live_execution": True}
    )
    with pytest.raises(ValueError, match="LIVE"):
        DashboardStore(snapshot)


def test_store_rejects_non_shadow_system_mode():
    snapshot = seeded_dashboard_snapshot(clock=lambda: NOW)
    bad_system = snapshot.systems[0].model_copy(update={"mode": "LIVE"})
    bad = snapshot.model_copy(update={"systems": (bad_system, *snapshot.systems[1:])})
    with pytest.raises(ValueError, match="SHADOW"):
        DashboardStore(bad)


def test_store_rejects_non_paper_execution_mode():
    snapshot = seeded_dashboard_snapshot(clock=lambda: NOW)
    bad_system = snapshot.systems[0].model_copy(update={"execution_mode": "LIVE"})
    bad = snapshot.model_copy(update={"systems": (bad_system, *snapshot.systems[1:])})
    with pytest.raises(ValueError, match="PAPER"):
        DashboardStore(bad)


def test_store_rejects_wrong_execution_scope():
    snapshot = seeded_dashboard_snapshot(clock=lambda: NOW).model_copy(
        update={"execution_scope": "LIVE"}
    )
    with pytest.raises(ValueError, match="PAPER/SHADOW"):
        DashboardStore(snapshot)


def test_store_internal_publish_is_not_an_http_authority():
    """The store has no knowledge of trading/risk mutation commands."""
    store = DashboardStore(seeded_dashboard_snapshot(clock=lambda: NOW))
    assert not hasattr(store, "submit_order")
    assert not hasattr(store, "set_risk_profile")
    assert not hasattr(store, "promote_system")


def test_store_keeps_bounded_opportunity_and_decision_history():
    import asyncio

    from app.dashboard.projection import ShadowDashboardProjector

    from ._helpers import fake_fleet_result, fake_runner

    store = DashboardStore(seeded_dashboard_snapshot(clock=lambda: NOW), history_limit=4)
    projector = ShadowDashboardProjector(clock=lambda: NOW)
    first = asyncio.run(projector.capture(runner=fake_runner(), fleet_result=fake_fleet_result()))
    store.publish(first)

    second_fleet = fake_fleet_result()
    second_fleet.root_opportunity_id = "root-2"
    second_fleet.root_correlation_id = "corr-2"
    for index, result in enumerate(second_fleet.systems, start=1):
        result.context.derived_opportunity_id = f"derived-2-{index}"
        result.opportunity.opportunity_id = f"derived-2-{index}"
        result.paper_result.opportunity_id = f"derived-2-{index}"
    second = asyncio.run(projector.capture(runner=fake_runner(), fleet_result=second_fleet))
    store.publish(second)

    assert len(store.get().opportunities) == 4
    assert len(store.get().decisions) == 4
    assert store.get().root_opportunity_id == "root-2"
