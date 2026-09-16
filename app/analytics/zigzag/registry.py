from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.common.canonical import stable_digest

CAUSAL_ZIGZAG_VERSION = "money-heist.analytics-causal-zigzag.v1"
CAUSAL_ZIGZAG_ATR_INDICATOR_ID = "atr_14"
CAUSAL_ZIGZAG_ATR_PERIOD = 14
CAUSAL_ZIGZAG_REVERSAL_MULTIPLE = 2.0
CAUSAL_ZIGZAG_AMBIGUITY_POLICY = "conservative-no-intrabar-order-v1"
CAUSAL_ZIGZAG_INITIALIZATION_POLICY = "dual-candidate-after-atr-ready-v1"
CAUSAL_ZIGZAG_THRESHOLD_POLICY = "inclusive-gte-locked-at-candidate-v1"
CAUSAL_ZIGZAG_TIMESTAMP_POLICY = "closed-candle-close-time-v1"


@dataclass(frozen=True, slots=True)
class CausalZigZagDefinition:
    version: str = CAUSAL_ZIGZAG_VERSION
    atr_indicator_id: str = CAUSAL_ZIGZAG_ATR_INDICATOR_ID
    atr_period: int = CAUSAL_ZIGZAG_ATR_PERIOD
    reversal_multiple: float = CAUSAL_ZIGZAG_REVERSAL_MULTIPLE
    ambiguity_policy: str = CAUSAL_ZIGZAG_AMBIGUITY_POLICY
    initialization_policy: str = CAUSAL_ZIGZAG_INITIALIZATION_POLICY
    threshold_policy: str = CAUSAL_ZIGZAG_THRESHOLD_POLICY
    timestamp_policy: str = CAUSAL_ZIGZAG_TIMESTAMP_POLICY

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "atr_indicator_id": self.atr_indicator_id,
            "atr_period": self.atr_period,
            "reversal_multiple": self.reversal_multiple,
            "ambiguity_policy": self.ambiguity_policy,
            "initialization_policy": self.initialization_policy,
            "threshold_policy": self.threshold_policy,
            "timestamp_policy": self.timestamp_policy,
        }


CAUSAL_ZIGZAG_DEFINITION = CausalZigZagDefinition()
CAUSAL_ZIGZAG_REGISTRY_FINGERPRINT = stable_digest(
    CAUSAL_ZIGZAG_DEFINITION.canonical_payload()
)
CAUSAL_ZIGZAG_REGISTRY_IDENTITY = (
    f"{CAUSAL_ZIGZAG_VERSION}:{CAUSAL_ZIGZAG_REGISTRY_FINGERPRINT}"
)

__all__ = [
    "CAUSAL_ZIGZAG_AMBIGUITY_POLICY",
    "CAUSAL_ZIGZAG_ATR_INDICATOR_ID",
    "CAUSAL_ZIGZAG_ATR_PERIOD",
    "CAUSAL_ZIGZAG_DEFINITION",
    "CAUSAL_ZIGZAG_INITIALIZATION_POLICY",
    "CAUSAL_ZIGZAG_REGISTRY_FINGERPRINT",
    "CAUSAL_ZIGZAG_REGISTRY_IDENTITY",
    "CAUSAL_ZIGZAG_REVERSAL_MULTIPLE",
    "CAUSAL_ZIGZAG_THRESHOLD_POLICY",
    "CAUSAL_ZIGZAG_TIMESTAMP_POLICY",
    "CAUSAL_ZIGZAG_VERSION",
    "CausalZigZagDefinition",
]
