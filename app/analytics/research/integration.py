from __future__ import annotations

from app.analytics.events import ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY
from app.analytics.indicators import ANALYTICS_INDICATOR_REGISTRY_IDENTITY
from app.analytics.models import AnalyticsComponentVersions
from app.analytics.patterns import ANALYTICS_PATTERN_REGISTRY_IDENTITY
from app.analytics.structure import ANALYTICS_STRUCTURE_IDENTITY
from app.analytics.zigzag import CAUSAL_ZIGZAG_REGISTRY_IDENTITY

from .registry import CONTEXT_RESOLVER_VERSION, SEQUENCE_RESOLVER_VERSION

ANALYTICS_24A7_BUNDLE_VERSION = "analytics-lab-24a7-contexts-sequences-v1"


def causal_research_component_versions(
    *,
    structure_version: str = ANALYTICS_STRUCTURE_IDENTITY,
    analytics_bundle_version: str = ANALYTICS_24A7_BUNDLE_VERSION,
) -> AnalyticsComponentVersions:
    """Return the fully installed Analytics Lab component manifest for Batch 24A.7."""
    return AnalyticsComponentVersions(
        analytics_bundle_version=analytics_bundle_version,
        indicator_registry_version=ANALYTICS_INDICATOR_REGISTRY_IDENTITY,
        event_registry_version=ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY,
        structure_version=structure_version,
        zigzag_version=CAUSAL_ZIGZAG_REGISTRY_IDENTITY,
        pattern_registry_version=ANALYTICS_PATTERN_REGISTRY_IDENTITY,
        context_engine_version=CONTEXT_RESOLVER_VERSION,
        sequence_engine_version=SEQUENCE_RESOLVER_VERSION,
    )


__all__ = [
    "ANALYTICS_24A7_BUNDLE_VERSION",
    "causal_research_component_versions",
]
