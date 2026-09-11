from __future__ import annotations

from collections.abc import Mapping

from app.market.structure import MARKET_STRUCTURE_VERSION
from app.services.decision_context import (
    AGENT_CONTEXT_BINDING_VERSION,
    RISK_CONTEXT_BINDING_VERSION,
)


MTF_RUNTIME_VERSION = "historical-mtf-runtime-v1"
MTF_DECISION_TIMEFRAME = "1h"
MTF_TIMEFRAMES = ("15m", "1h", "4h", "1d")
MTF_POLICY_VERSION = "mtf-utc-closed-v1"
MTF_FEATURE_CONTEXT_VERSION = "mtf-feature-context-v1"
DECISION_CONTEXT_VERSION = "decision-context-v1"

_SUPPORTED_FULL_MTF_SOURCES = frozenset({"1m", "5m", "15m"})


def supports_full_mtf_source(timeframe: str) -> bool:
    return timeframe.strip().lower() in _SUPPORTED_FULL_MTF_SOURCES


def mtf_execution_assumptions(source_timeframe: str) -> dict[str, str]:
    source = source_timeframe.strip().lower()
    if not supports_full_mtf_source(source):
        return {}

    return {
        "mtf_runtime_version": MTF_RUNTIME_VERSION,
        "historical_source_timeframe": source,
        "decision_timeframe": MTF_DECISION_TIMEFRAME,
        "mtf_timeframes": ",".join(MTF_TIMEFRAMES),
        "mtf_policy_version": MTF_POLICY_VERSION,
        "mtf_feature_context_version": MTF_FEATURE_CONTEXT_VERSION,
        "decision_context_version": DECISION_CONTEXT_VERSION,
        "agent_context_binding_version": AGENT_CONTEXT_BINDING_VERSION,
        "risk_context_binding_version": RISK_CONTEXT_BINDING_VERSION,
        "market_structure_version": MARKET_STRUCTURE_VERSION,
        "lifecycle_timeframe": source,
    }


def mtf_runner_kwargs(
    assumptions: Mapping[str, str],
) -> dict[str, object]:
    if assumptions.get("mtf_runtime_version") != MTF_RUNTIME_VERSION:
        return {}

    required = {
        "decision_timeframe": MTF_DECISION_TIMEFRAME,
        "mtf_timeframes": ",".join(MTF_TIMEFRAMES),
        "mtf_policy_version": MTF_POLICY_VERSION,
        "mtf_feature_context_version": MTF_FEATURE_CONTEXT_VERSION,
        "decision_context_version": DECISION_CONTEXT_VERSION,
        "agent_context_binding_version": AGENT_CONTEXT_BINDING_VERSION,
        "risk_context_binding_version": RISK_CONTEXT_BINDING_VERSION,
        "market_structure_version": MARKET_STRUCTURE_VERSION,
    }
    for key, expected in required.items():
        actual = assumptions.get(key)
        if actual != expected:
            raise ValueError(
                "MTF runtime assumptions are incoherent: "
                f"{key}={actual!r}, expected {expected!r}"
            )

    return {
        "decision_timeframe": MTF_DECISION_TIMEFRAME,
        "mtf_timeframes": MTF_TIMEFRAMES,
        "mtf_policy_version": MTF_POLICY_VERSION,
        "mtf_feature_context_version": MTF_FEATURE_CONTEXT_VERSION,
        "decision_context_version": DECISION_CONTEXT_VERSION,
        "agent_context_binding_version": AGENT_CONTEXT_BINDING_VERSION,
        "risk_context_binding_version": RISK_CONTEXT_BINDING_VERSION,
        "market_structure_version": MARKET_STRUCTURE_VERSION,
    }
