from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from .identities import ShadowSystemIdentity


class ShadowBranchStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ShadowEvaluationStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MetricAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ShadowBranchContext:
    root_correlation_id: str
    root_opportunity_id: str
    root_snapshot_id: str
    system_id: str
    derived_opportunity_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ShadowSystemFailure:
    stage: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class ShadowMetricSnapshot:
    """Normalized, read-only projection of Batch 10 metrics used for comparison.

    ``None`` means Batch 10 could not calculate the metric. Batch 11 never fills
    missing values with estimates and never turns absence into zero.
    """

    realized_pnl: Decimal | None = None
    trading_net: Decimal | None = None
    economic_net: Decimal | None = None
    ai_cost: Decimal | None = None
    self_funding_ratio: Decimal | None = None

    def as_mapping(self) -> Mapping[str, Decimal | None]:
        return MappingProxyType(
            {
                "realized_pnl": self.realized_pnl,
                "trading_net": self.trading_net,
                "economic_net": self.economic_net,
                "ai_cost": self.ai_cost,
                "self_funding_ratio": self.self_funding_ratio,
            }
        )


@dataclass(frozen=True, slots=True)
class ShadowEvaluationResult:
    status: ShadowEvaluationStatus
    metrics: ShadowMetricSnapshot | None = None
    report: Any | None = None
    failure: ShadowSystemFailure | None = None


@dataclass(frozen=True, slots=True)
class SystemScopedAIUsage:
    system_id: str
    usage: Any


@dataclass(frozen=True, slots=True)
class ShadowSystemResult:
    identity: ShadowSystemIdentity
    context: ShadowBranchContext
    status: ShadowBranchStatus
    opportunity: Any
    paper_result: Any | None
    ai_usage: tuple[SystemScopedAIUsage, ...] = ()
    evaluation: ShadowEvaluationResult = field(
        default_factory=lambda: ShadowEvaluationResult(
            status=ShadowEvaluationStatus.NOT_REQUESTED
        )
    )
    failure: ShadowSystemFailure | None = None


@dataclass(frozen=True, slots=True)
class ShadowPairwiseDelta:
    left_system_id: str
    right_system_id: str
    left_value: Decimal
    right_value: Decimal
    delta_right_minus_left: Decimal


@dataclass(frozen=True, slots=True)
class ShadowMetricComparison:
    metric: str
    availability: MetricAvailability
    values: Mapping[str, Decimal | None]
    pairwise_deltas: tuple[ShadowPairwiseDelta, ...]


@dataclass(frozen=True, slots=True)
class ShadowComparison:
    metrics: Mapping[str, ShadowMetricComparison]
    promotion_system_id: None = field(default=None, init=False)
    risk_change: None = field(default=None, init=False)


@dataclass(frozen=True, slots=True)
class ShadowFleetResult:
    root_correlation_id: str
    root_opportunity_id: str
    root_snapshot_id: str
    systems: tuple[ShadowSystemResult, ...]
    comparison: ShadowComparison

    def by_system_id(self) -> Mapping[str, ShadowSystemResult]:
        return MappingProxyType({item.identity.system_id: item for item in self.systems})
