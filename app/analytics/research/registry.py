from __future__ import annotations

from enum import StrEnum

ANALYTICS_CONTEXT_SCHEMA_VERSION = "money-heist.analytics-context-definition.v1"
ANALYTICS_CONTEXT_MATCH_SCHEMA_VERSION = "money-heist.analytics-context-match.v1"
ANALYTICS_SEQUENCE_SCHEMA_VERSION = "money-heist.analytics-sequence-definition.v1"
ANALYTICS_SEQUENCE_MATCH_SCHEMA_VERSION = "money-heist.analytics-sequence-match.v1"
ANALYTICS_RESEARCH_RUN_SCHEMA_VERSION = "money-heist.analytics-research-run.v1"
ANALYTICS_OBSERVATION_INDEX_VERSION = "money-heist.analytics-observation-index.v1"
CONTEXT_RESOLVER_VERSION = "money-heist.context-resolver.v1"
SEQUENCE_RESOLVER_VERSION = "money-heist.sequence-resolver.v1"


class AnalyticsAnchorType(StrEnum):
    TECHNICAL_EVENT = "TECHNICAL_EVENT"
    PATTERN_TRANSITION = "PATTERN_TRANSITION"
    ZIGZAG_PIVOT = "ZIGZAG_PIVOT"


class AnalyticsConditionType(StrEnum):
    INDICATOR = "INDICATOR"
    TECHNICAL_EVENT = "TECHNICAL_EVENT"
    PATTERN_TRANSITION = "PATTERN_TRANSITION"
    STRUCTURE = "STRUCTURE"
    ZIGZAG = "ZIGZAG"


class IndicatorOperator(StrEnum):
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    EQ = "EQ"
    BETWEEN = "BETWEEN"


class TemporalScope(StrEnum):
    AT_ANCHOR = "AT_ANCHOR"
    WITHIN_PREVIOUS_BARS = "WITHIN_PREVIOUS_BARS"


class PatternConditionMode(StrEnum):
    TRANSITION_OCCURRED = "TRANSITION_OCCURRED"
    CURRENT_STATUS = "CURRENT_STATUS"


class StructureField(StrEnum):
    SWING_STRUCTURE = "swing_structure"
    BREAKOUT_STATE = "breakout_state"
    RANGE_LOCATION = "range_location"


__all__ = [
    "ANALYTICS_CONTEXT_MATCH_SCHEMA_VERSION",
    "ANALYTICS_CONTEXT_SCHEMA_VERSION",
    "ANALYTICS_OBSERVATION_INDEX_VERSION",
    "ANALYTICS_RESEARCH_RUN_SCHEMA_VERSION",
    "ANALYTICS_SEQUENCE_MATCH_SCHEMA_VERSION",
    "ANALYTICS_SEQUENCE_SCHEMA_VERSION",
    "CONTEXT_RESOLVER_VERSION",
    "SEQUENCE_RESOLVER_VERSION",
    "AnalyticsAnchorType",
    "AnalyticsConditionType",
    "IndicatorOperator",
    "PatternConditionMode",
    "StructureField",
    "TemporalScope",
]
