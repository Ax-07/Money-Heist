from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.dashboard.models import DashboardAvailability, DashboardProvenance
from app.dashboard.projection import seeded_dashboard_snapshot
from app.services.shadow.identities import default_shadow_systems


FIXED = datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc)


def test_seeded_snapshot_is_read_only_paper_shadow_only():
    snapshot = seeded_dashboard_snapshot(clock=lambda: FIXED)
    assert snapshot.read_only is True
    assert snapshot.live_execution is False
    assert snapshot.execution_scope == "PAPER_SHADOW_ONLY"
    assert snapshot.system_state == "NO_OBSERVED_SHADOW_RUN"


def test_seeded_snapshot_contains_exact_batch11_system_ids():
    snapshot = seeded_dashboard_snapshot(clock=lambda: FIXED)
    assert [system.system_id for system in snapshot.systems] == [
        identity.system_id for identity in default_shadow_systems()
    ]


def test_seeded_systems_are_shadow_over_paper():
    snapshot = seeded_dashboard_snapshot(clock=lambda: FIXED)
    assert all(system.mode == "SHADOW" for system in snapshot.systems)
    assert all(system.execution_mode == "PAPER" for system in snapshot.systems)
    assert all(system.live_execution is False for system in snapshot.systems)


def test_seeded_account_is_unavailable_not_zero():
    snapshot = seeded_dashboard_snapshot(clock=lambda: FIXED)
    account = snapshot.systems[0].account
    assert account.availability is DashboardAvailability.UNAVAILABLE
    assert account.cash_balance is None
    assert account.equity is None


def test_seeded_comparison_is_unavailable_not_zero():
    snapshot = seeded_dashboard_snapshot(clock=lambda: FIXED)
    metric = snapshot.comparison.metrics["trading_net"]
    assert metric.availability is DashboardAvailability.UNAVAILABLE
    assert set(metric.values.values()) == {None}


def test_comparison_has_no_promotion_or_risk_authority():
    snapshot = seeded_dashboard_snapshot(clock=lambda: FIXED)
    assert snapshot.comparison.promotion_system_id is None
    assert snapshot.comparison.risk_change is None
    assert snapshot.comparison.authority == "OBSERVATION_ONLY"


def test_dashboard_model_is_frozen():
    snapshot = seeded_dashboard_snapshot(clock=lambda: FIXED)
    with pytest.raises(ValidationError):
        snapshot.live_execution = True


def test_counterfactual_and_shadow_are_distinct_provenances():
    assert DashboardProvenance.COUNTERFACTUAL != DashboardProvenance.SHADOW_PAPER
    assert DashboardProvenance.PAPER_EXECUTED != DashboardProvenance.COUNTERFACTUAL
