from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Protocol

from .models import (
    MetricAvailability,
    ShadowComparison,
    ShadowEvaluationResult,
    ShadowEvaluationStatus,
    ShadowMetricComparison,
    ShadowMetricSnapshot,
    ShadowPairwiseDelta,
    ShadowSystemFailure,
)


@dataclass(frozen=True, slots=True)
class Batch10EvaluationInput:
    """Boundary from Batch 11 to the already-independent Batch 10 evaluator."""

    system_id: str
    root_opportunity_id: str
    derived_opportunity_id: str
    paper_history: tuple[Any, ...]
    ai_usage_records: tuple[Any, ...]


class Batch10EvaluationPort(Protocol):
    async def evaluate(self, evaluation_input: Batch10EvaluationInput) -> ShadowEvaluationResult: ...


class CallableBatch10EvaluationAdapter:
    """Adapter around the concrete Batch 10 service without coupling its internals.

    ``evaluate_fn`` receives the immutable ``Batch10EvaluationInput`` and returns
    the raw Batch 10 report. ``metrics_fn`` performs the explicit projection from
    that report to the five metrics Batch 11 is allowed to compare.
    """

    def __init__(
        self,
        *,
        evaluate_fn: Callable[[Batch10EvaluationInput], Any | Awaitable[Any]],
        metrics_fn: Callable[[Any], ShadowMetricSnapshot],
    ) -> None:
        self._evaluate_fn = evaluate_fn
        self._metrics_fn = metrics_fn

    async def evaluate(self, evaluation_input: Batch10EvaluationInput) -> ShadowEvaluationResult:
        try:
            report = self._evaluate_fn(evaluation_input)
            if inspect.isawaitable(report):
                report = await report
            metrics = self._metrics_fn(report)
            if not isinstance(metrics, ShadowMetricSnapshot):
                raise TypeError("metrics_fn must return ShadowMetricSnapshot")
            return ShadowEvaluationResult(
                status=ShadowEvaluationStatus.COMPLETED,
                metrics=metrics,
                report=report,
            )
        except Exception as exc:
            return ShadowEvaluationResult(
                status=ShadowEvaluationStatus.FAILED,
                failure=ShadowSystemFailure(
                    stage="evaluation",
                    error_type=type(exc).__name__,
                    message=str(exc),
                ),
            )


class MappingMetricProjector:
    """Small explicit helper for Batch 10 exports represented as mappings.

    Missing/unknown values remain ``None``. No value is inferred from another
    metric, so Trading Net and Economic Net remain strictly distinct.
    """

    def __init__(
        self,
        *,
        realized_pnl_key: str = "realized_pnl",
        trading_net_key: str = "trading_net",
        economic_net_key: str = "economic_net",
        ai_cost_key: str = "ai_cost",
        self_funding_ratio_key: str = "self_funding_ratio",
    ) -> None:
        self._keys = {
            "realized_pnl": realized_pnl_key,
            "trading_net": trading_net_key,
            "economic_net": economic_net_key,
            "ai_cost": ai_cost_key,
            "self_funding_ratio": self_funding_ratio_key,
        }

    def __call__(self, report: Mapping[str, Any]) -> ShadowMetricSnapshot:
        if not isinstance(report, Mapping):
            raise TypeError("MappingMetricProjector requires a mapping report")
        return ShadowMetricSnapshot(
            realized_pnl=self._decimal_or_none(report.get(self._keys["realized_pnl"])),
            trading_net=self._decimal_or_none(report.get(self._keys["trading_net"])),
            economic_net=self._decimal_or_none(report.get(self._keys["economic_net"])),
            ai_cost=self._decimal_or_none(report.get(self._keys["ai_cost"])),
            self_funding_ratio=self._decimal_or_none(
                report.get(self._keys["self_funding_ratio"])
            ),
        )

    @staticmethod
    def _decimal_or_none(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None
        if not decimal_value.is_finite():
            return None
        return decimal_value


class ShadowComparisonEngine:
    """Read-only deterministic comparison with no ranking/promotion authority."""

    METRICS = (
        "realized_pnl",
        "trading_net",
        "economic_net",
        "ai_cost",
        "self_funding_ratio",
    )

    def compare(
        self,
        *,
        system_order: Sequence[str],
        snapshots: Mapping[str, ShadowMetricSnapshot | None],
    ) -> ShadowComparison:
        comparisons: dict[str, ShadowMetricComparison] = {}
        for metric in self.METRICS:
            values = {
                system_id: (
                    getattr(snapshots.get(system_id), metric)
                    if snapshots.get(system_id) is not None
                    else None
                )
                for system_id in system_order
            }
            pairwise: list[ShadowPairwiseDelta] = []
            for left_index, left_system_id in enumerate(system_order):
                left_value = values[left_system_id]
                if left_value is None:
                    continue
                for right_system_id in system_order[left_index + 1 :]:
                    right_value = values[right_system_id]
                    if right_value is None:
                        continue
                    pairwise.append(
                        ShadowPairwiseDelta(
                            left_system_id=left_system_id,
                            right_system_id=right_system_id,
                            left_value=left_value,
                            right_value=right_value,
                            delta_right_minus_left=right_value - left_value,
                        )
                    )

            available_count = sum(value is not None for value in values.values())
            if available_count < 2:
                availability = MetricAvailability.UNAVAILABLE
            elif available_count == len(system_order):
                availability = MetricAvailability.AVAILABLE
            else:
                availability = MetricAvailability.PARTIAL

            comparisons[metric] = ShadowMetricComparison(
                metric=metric,
                availability=availability,
                values=MappingProxyType(values),
                pairwise_deltas=tuple(pairwise),
            )

        return ShadowComparison(metrics=MappingProxyType(comparisons))
