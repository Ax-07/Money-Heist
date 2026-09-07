"""Dashboard V1 read models and PAPER/SHADOW projection helpers."""

from .models import (
    DashboardAvailability,
    DashboardComparison,
    DashboardEvent,
    DashboardMetric,
    DashboardOpportunity,
    DashboardProvenance,
    DashboardSnapshot,
    DashboardSystem,
)
from .observer import DashboardShadowObserver
from .projection import ShadowDashboardProjector, seeded_dashboard_snapshot
from .store import DashboardStore

__all__ = [
    "DashboardAvailability",
    "DashboardComparison",
    "DashboardEvent",
    "DashboardMetric",
    "DashboardOpportunity",
    "DashboardProvenance",
    "DashboardShadowObserver",
    "DashboardSnapshot",
    "DashboardStore",
    "DashboardSystem",
    "ShadowDashboardProjector",
    "seeded_dashboard_snapshot",
]
