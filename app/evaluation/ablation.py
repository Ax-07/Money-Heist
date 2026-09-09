from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.services.backtest.reports import BacktestMetricSnapshot, BacktestPeriodReport


class AblationMetricStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class AblationMetricDelta:
    value: Decimal | None
    status: AblationMetricStatus
    reason: str | None = None

    @classmethod
    def available(cls, value: Decimal) -> AblationMetricDelta:
        return cls(value=value, status=AblationMetricStatus.AVAILABLE)

    @classmethod
    def unavailable(cls, reason: str) -> AblationMetricDelta:
        return cls(
            value=None,
            status=AblationMetricStatus.UNAVAILABLE,
            reason=reason,
        )


@dataclass(frozen=True, slots=True)
class AblationRunDescriptor:
    report: BacktestPeriodReport
    comparison_fingerprint: str
    included_agents: tuple[str, ...]

    def __post_init__(self) -> None:
        fingerprint = self.comparison_fingerprint.strip()
        if not fingerprint:
            raise ValueError("comparison_fingerprint must not be blank")
        normalized = tuple(sorted(self.included_agents))
        if not normalized:
            raise ValueError("included_agents must not be empty")
        if any(not agent_id.strip() for agent_id in normalized):
            raise ValueError("included_agents must not contain blank agent ids")
        if len(set(normalized)) != len(normalized):
            raise ValueError("included_agents must not contain duplicates")
        object.__setattr__(self, "comparison_fingerprint", fingerprint)
        object.__setattr__(self, "included_agents", normalized)


@dataclass(frozen=True, slots=True)
class AblationComparison:
    agent_id: str
    comparison_fingerprint: str
    baseline_run_id: str
    ablated_run_id: str
    dataset_id: str
    role: str
    period_start: object
    period_end: object
    processed_candles: int
    opportunity_count: int
    closed_trade_count_delta: int
    marginal_trading_net: AblationMetricDelta
    marginal_economic_net: AblationMetricDelta
    drawdown_reduction_pct: AblationMetricDelta
    additional_ai_cost_eur: Decimal
    is_out_of_sample: bool


@dataclass(frozen=True, slots=True)
class AblationAggregate:
    agent_id: str
    comparison_count: int
    oos_comparison_count: int
    economic_metric_count: int
    positive_economic_count: int
    negative_economic_count: int
    zero_economic_count: int
    mean_marginal_trading_net: AblationMetricDelta
    mean_marginal_economic_net: AblationMetricDelta
    mean_drawdown_reduction_pct: AblationMetricDelta
    mean_additional_ai_cost_eur: Decimal


def _available_metric(metric: BacktestMetricSnapshot) -> Decimal | None:
    if metric.status != "AVAILABLE":
        return None
    return metric.value


def _difference(
    baseline: BacktestMetricSnapshot,
    ablated: BacktestMetricSnapshot,
    *,
    name: str,
) -> AblationMetricDelta:
    baseline_value = _available_metric(baseline)
    ablated_value = _available_metric(ablated)
    if baseline_value is None or ablated_value is None:
        return AblationMetricDelta.unavailable(f"{name}_UNAVAILABLE")
    return AblationMetricDelta.available(baseline_value - ablated_value)


def _drawdown_reduction(
    baseline: BacktestMetricSnapshot,
    ablated: BacktestMetricSnapshot,
) -> AblationMetricDelta:
    baseline_value = _available_metric(baseline)
    ablated_value = _available_metric(ablated)
    if baseline_value is None or ablated_value is None:
        return AblationMetricDelta.unavailable("MAX_DRAWDOWN_UNAVAILABLE")
    return AblationMetricDelta.available(ablated_value - baseline_value)


def _validate_comparable(
    baseline: AblationRunDescriptor,
    ablated: AblationRunDescriptor,
    *,
    agent_id: str,
) -> None:
    if not agent_id.strip():
        raise ValueError("agent_id must not be blank")
    if baseline.report.run_id == ablated.report.run_id:
        raise ValueError("baseline and ablated run ids must differ")
    if baseline.comparison_fingerprint != ablated.comparison_fingerprint:
        raise ValueError("ablation runs must share comparison_fingerprint")

    comparable = (
        ("dataset_id", baseline.report.dataset_id, ablated.report.dataset_id),
        ("role", baseline.report.role, ablated.report.role),
        ("period_start", baseline.report.period_start, ablated.report.period_start),
        ("period_end", baseline.report.period_end, ablated.report.period_end),
        (
            "processed_candles",
            baseline.report.processed_candles,
            ablated.report.processed_candles,
        ),
        (
            "opportunity_count",
            baseline.report.opportunity_count,
            ablated.report.opportunity_count,
        ),
    )
    for field_name, left, right in comparable:
        if left != right:
            raise ValueError(f"ablation runs differ on {field_name}")

    baseline_agents = set(baseline.included_agents)
    ablated_agents = set(ablated.included_agents)
    if agent_id not in baseline_agents:
        raise ValueError("ablated agent must be present in baseline run")
    if agent_id in ablated_agents:
        raise ValueError("ablated agent must be absent from ablated run")
    if baseline_agents - ablated_agents != {agent_id}:
        raise ValueError("baseline may differ by exactly the ablated agent")
    if ablated_agents - baseline_agents:
        raise ValueError("ablated run must not add agents")


def compare_ablation(
    baseline: AblationRunDescriptor,
    ablated: AblationRunDescriptor,
    *,
    agent_id: str,
) -> AblationComparison:
    """Compare one baseline run against the same run with one specialist removed."""

    _validate_comparable(baseline, ablated, agent_id=agent_id)
    baseline_report = baseline.report
    ablated_report = ablated.report

    return AblationComparison(
        agent_id=agent_id,
        comparison_fingerprint=baseline.comparison_fingerprint,
        baseline_run_id=baseline_report.run_id,
        ablated_run_id=ablated_report.run_id,
        dataset_id=baseline_report.dataset_id,
        role=baseline_report.role.value,
        period_start=baseline_report.period_start,
        period_end=baseline_report.period_end,
        processed_candles=baseline_report.processed_candles,
        opportunity_count=baseline_report.opportunity_count,
        closed_trade_count_delta=(
            baseline_report.closed_trade_count - ablated_report.closed_trade_count
        ),
        marginal_trading_net=_difference(
            baseline_report.trading_net,
            ablated_report.trading_net,
            name="TRADING_NET",
        ),
        marginal_economic_net=_difference(
            baseline_report.economic_net,
            ablated_report.economic_net,
            name="ECONOMIC_NET",
        ),
        drawdown_reduction_pct=_drawdown_reduction(
            baseline_report.max_drawdown_pct,
            ablated_report.max_drawdown_pct,
        ),
        additional_ai_cost_eur=(
            baseline_report.ai_cost_eur - ablated_report.ai_cost_eur
        ),
        is_out_of_sample=baseline_report.is_out_of_sample,
    )


def _mean(values: list[Decimal], *, reason: str) -> AblationMetricDelta:
    if not values:
        return AblationMetricDelta.unavailable(reason)
    return AblationMetricDelta.available(
        sum(values, Decimal("0")) / Decimal(len(values))
    )


def aggregate_ablation(
    comparisons: tuple[AblationComparison, ...],
) -> AblationAggregate:
    if not comparisons:
        raise ValueError("at least one ablation comparison is required")
    agent_ids = {comparison.agent_id for comparison in comparisons}
    if len(agent_ids) != 1:
        raise ValueError("all ablation comparisons must target the same agent")

    ordered = tuple(
        sorted(
            comparisons,
            key=lambda item: (
                item.dataset_id,
                item.role,
                str(item.period_start),
                item.baseline_run_id,
                item.ablated_run_id,
            ),
        )
    )
    economic_values = [
        item.marginal_economic_net.value
        for item in ordered
        if item.marginal_economic_net.value is not None
    ]
    trading_values = [
        item.marginal_trading_net.value
        for item in ordered
        if item.marginal_trading_net.value is not None
    ]
    drawdown_values = [
        item.drawdown_reduction_pct.value
        for item in ordered
        if item.drawdown_reduction_pct.value is not None
    ]
    additional_costs = [item.additional_ai_cost_eur for item in ordered]

    return AblationAggregate(
        agent_id=ordered[0].agent_id,
        comparison_count=len(ordered),
        oos_comparison_count=sum(item.is_out_of_sample for item in ordered),
        economic_metric_count=len(economic_values),
        positive_economic_count=sum(value > 0 for value in economic_values),
        negative_economic_count=sum(value < 0 for value in economic_values),
        zero_economic_count=sum(value == 0 for value in economic_values),
        mean_marginal_trading_net=_mean(
            trading_values,
            reason="NO_AVAILABLE_TRADING_NET_COMPARISONS",
        ),
        mean_marginal_economic_net=_mean(
            economic_values,
            reason="NO_AVAILABLE_ECONOMIC_NET_COMPARISONS",
        ),
        mean_drawdown_reduction_pct=_mean(
            drawdown_values,
            reason="NO_AVAILABLE_DRAWDOWN_COMPARISONS",
        ),
        mean_additional_ai_cost_eur=(
            sum(additional_costs, Decimal("0")) / Decimal(len(additional_costs))
        ),
    )
