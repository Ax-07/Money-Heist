"""Observation-only Technical Events built exclusively from Analytics Indicator snapshots."""

from .engine import TechnicalEventEngine, TechnicalEventInputError
from .integration import (
    ANALYTICS_24A3_BUNDLE_VERSION,
    build_analytics_snapshot_with_indicators_and_events,
    compute_technical_event_component,
    technical_event_component_versions,
)
from .models import (
    TECHNICAL_EVENT_OBSERVATION_SCHEMA_VERSION,
    TechnicalEventEvidence,
    TechnicalEventObservation,
)
from .registry import (
    ANALYTICS_TECHNICAL_EVENT_REGISTRY_FINGERPRINT,
    ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY,
    ANALYTICS_TECHNICAL_EVENT_REGISTRY_VERSION,
    TECHNICAL_EVENT_BY_TYPE,
    TECHNICAL_EVENT_REGISTRY,
    TECHNICAL_EVENT_TYPES,
    TechnicalEventCondition,
    TechnicalEventDefinition,
    TechnicalEventDirection,
    TechnicalEventFamily,
    registry_payload,
)

__all__ = [
    "ANALYTICS_24A3_BUNDLE_VERSION",
    "ANALYTICS_TECHNICAL_EVENT_REGISTRY_FINGERPRINT",
    "ANALYTICS_TECHNICAL_EVENT_REGISTRY_IDENTITY",
    "ANALYTICS_TECHNICAL_EVENT_REGISTRY_VERSION",
    "TECHNICAL_EVENT_BY_TYPE",
    "TECHNICAL_EVENT_OBSERVATION_SCHEMA_VERSION",
    "TECHNICAL_EVENT_REGISTRY",
    "TECHNICAL_EVENT_TYPES",
    "TechnicalEventCondition",
    "TechnicalEventDefinition",
    "TechnicalEventDirection",
    "TechnicalEventEngine",
    "TechnicalEventEvidence",
    "TechnicalEventFamily",
    "TechnicalEventInputError",
    "TechnicalEventObservation",
    "build_analytics_snapshot_with_indicators_and_events",
    "compute_technical_event_component",
    "registry_payload",
    "technical_event_component_versions",
]
