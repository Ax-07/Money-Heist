"""Observation-only Analytics Lab contracts.

This package has no trading authority and must remain isolated from decision,
post-hoc forward-outcome, and LIVE execution paths during Batch 24A.
"""

from .manifest import AnalyticsLabManifest, build_analytics_manifest, manifest_to_json
from .models import (
    ANALYTICS_AUTHORITY_POLICY_VERSION,
    AnalyticsAsOfInput,
    AnalyticsComponentVersions,
    AnalyticsLabRun,
    AnalyticsPeriodRole,
    AnalyticsSnapshot,
)
from .provenance import AnalyticsObservationProvenance

__all__ = [
    "ANALYTICS_AUTHORITY_POLICY_VERSION",
    "AnalyticsAsOfInput",
    "AnalyticsComponentVersions",
    "AnalyticsLabManifest",
    "AnalyticsLabRun",
    "AnalyticsObservationProvenance",
    "AnalyticsPeriodRole",
    "AnalyticsSnapshot",
    "build_analytics_manifest",
    "manifest_to_json",
]
