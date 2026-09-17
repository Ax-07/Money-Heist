"""Read-only post-hoc Decision ↔ Analytics attribution contracts."""

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

__all__ = [
    "AnalyticsSnapshotIndex",
    "AnalyticsSnapshotRef",
    "DecisionObservationKey",
    "LinkStatusCount",
    "OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION",
    "OpportunityAnalyticsLink",
    "OpportunityAnalyticsLinkSet",
    "OpportunityAnalyticsLinkStatus",
    "OpportunityAnalyticsLinker",
    "OpportunityObservationRef",
    "build_opportunity_observations",
    "link_replay_opportunities",
]
