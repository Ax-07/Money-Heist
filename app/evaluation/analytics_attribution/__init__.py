"""Read-only post-hoc Decision and Scanner ↔ Analytics attribution contracts."""

from .index import AnalyticsSnapshotIndex
from .linker import (
    OpportunityAnalyticsLinker,
    build_opportunity_observations,
    link_replay_opportunities,
)
from .models import (
    OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION,
    AnalyticsSnapshotRef,
    DecisionObservationKey,
    LinkStatusCount,
    OpportunityAnalyticsLink,
    OpportunityAnalyticsLinkSet,
    OpportunityAnalyticsLinkStatus,
    OpportunityObservationRef,
)
from .resolver import AnalyticsResolution, AnalyticsSnapshotResolver
from .scanner_attribution import (
    SCANNER_ANALYTICS_ATTRIBUTION_PROJECTION_VERSION,
    SCANNER_ANALYTICS_ATTRIBUTION_SCHEMA_VERSION,
    SCANNER_ANALYTICS_ATTRIBUTION_SET_SCHEMA_VERSION,
    ScannerAnalyticsAttributionRecord,
    ScannerAnalyticsAttributionSet,
    ScannerAnalyticsRef,
    build_scanner_analytics_attribution,
)

__all__ = [
    "AnalyticsResolution",
    "AnalyticsSnapshotIndex",
    "AnalyticsSnapshotRef",
    "AnalyticsSnapshotResolver",
    "DecisionObservationKey",
    "LinkStatusCount",
    "OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION",
    "OpportunityAnalyticsLink",
    "OpportunityAnalyticsLinkSet",
    "OpportunityAnalyticsLinkStatus",
    "OpportunityAnalyticsLinker",
    "OpportunityObservationRef",
    "SCANNER_ANALYTICS_ATTRIBUTION_PROJECTION_VERSION",
    "SCANNER_ANALYTICS_ATTRIBUTION_SCHEMA_VERSION",
    "SCANNER_ANALYTICS_ATTRIBUTION_SET_SCHEMA_VERSION",
    "ScannerAnalyticsAttributionRecord",
    "ScannerAnalyticsAttributionSet",
    "ScannerAnalyticsRef",
    "build_opportunity_observations",
    "build_scanner_analytics_attribution",
    "link_replay_opportunities",
]
