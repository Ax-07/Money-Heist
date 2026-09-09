from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.agents.models import AgentState

from .ablation import AblationAggregate, AblationMetricDelta
from .models import AgentMetrics, Metric, MetricStatus


@dataclass(frozen=True, slots=True)
class ReputationPolicy:
    min_calls: int = 10
    min_oos_ablation_comparisons: int = 3
    max_allowed_drawdown_worsening_pct: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.min_calls < 1:
            raise ValueError("min_calls must be >= 1")
        if self.min_oos_ablation_comparisons < 1:
            raise ValueError("min_oos_ablation_comparisons must be >= 1")
        if self.max_allowed_drawdown_worsening_pct < 0:
            raise ValueError("max_allowed_drawdown_worsening_pct must be >= 0")


@dataclass(frozen=True, slots=True)
class AgentReputationProfile:
    agent_id: str
    call_count: int
    ablation_comparison_count: int
    oos_ablation_comparison_count: int
    participation_frequency: Metric
    directional_agreement: Metric
    average_confidence: Metric
    average_cost_eur: Metric
    average_latency_ms: Metric
    marginal_trading_net: Metric
    marginal_economic_net: Metric
    drawdown_reduction_pct: Metric
    suggested_state: AgentState
    state_reasons: tuple[str, ...]


def _as_metric(delta: AblationMetricDelta | None, *, reason: str) -> Metric:
    if delta is None or delta.value is None:
        return Metric.unavailable(reason)
    return Metric.available(delta.value)


def _directional_agreement(metrics: AgentMetrics) -> Metric:
    disagreement = metrics.disagreement_frequency
    if disagreement.status is not MetricStatus.AVAILABLE or disagreement.value is None:
        return Metric.unavailable(
            disagreement.reason or "DIRECTIONAL_DISAGREEMENT_UNAVAILABLE"
        )
    return Metric.available(Decimal("1") - disagreement.value)


def _suggest_state(
    metrics: AgentMetrics,
    ablation: AblationAggregate | None,
    policy: ReputationPolicy,
) -> tuple[AgentState, tuple[str, ...]]:
    reasons: list[str] = []
    if metrics.call_count < policy.min_calls:
        reasons.append("INSUFFICIENT_CALLS")
    if ablation is None:
        reasons.append("NO_ABLATION_EVIDENCE")
    elif ablation.oos_comparison_count < policy.min_oos_ablation_comparisons:
        reasons.append("INSUFFICIENT_OOS_ABLATION")

    if reasons:
        return AgentState.SHADOW, tuple(reasons)

    assert ablation is not None
    economic = ablation.mean_marginal_economic_net
    if economic.value is None:
        return AgentState.SHADOW, ("MARGINAL_ECONOMIC_NET_UNAVAILABLE",)

    drawdown = ablation.mean_drawdown_reduction_pct
    if (
        drawdown.value is not None
        and drawdown.value < -policy.max_allowed_drawdown_worsening_pct
    ):
        return AgentState.ON_DEMAND, ("DRAWDOWN_WORSENED_IN_ABLATION",)

    if economic.value > 0:
        return AgentState.PROBATION, ("POSITIVE_OOS_MARGINAL_ECONOMIC_NET",)
    if economic.value < 0:
        return AgentState.ON_DEMAND, ("NEGATIVE_OOS_MARGINAL_ECONOMIC_NET",)
    return AgentState.ON_DEMAND, ("ZERO_OOS_MARGINAL_ECONOMIC_NET",)


def build_agent_reputation(
    metrics: AgentMetrics,
    *,
    ablation: AblationAggregate | None = None,
    policy: ReputationPolicy | None = None,
) -> AgentReputationProfile:
    """Build an explainable profile; never mutates the runtime agent registry."""

    policy = policy or ReputationPolicy()
    if ablation is not None and ablation.agent_id != metrics.agent_id:
        raise ValueError("ablation agent_id does not match AgentMetrics")

    state, reasons = _suggest_state(metrics, ablation, policy)
    return AgentReputationProfile(
        agent_id=metrics.agent_id,
        call_count=metrics.call_count,
        ablation_comparison_count=0 if ablation is None else ablation.comparison_count,
        oos_ablation_comparison_count=(
            0 if ablation is None else ablation.oos_comparison_count
        ),
        participation_frequency=metrics.participation_frequency,
        directional_agreement=_directional_agreement(metrics),
        average_confidence=metrics.average_confidence,
        average_cost_eur=metrics.average_cost_eur,
        average_latency_ms=metrics.average_latency_ms,
        marginal_trading_net=_as_metric(
            None if ablation is None else ablation.mean_marginal_trading_net,
            reason="NO_ABLATION_EVIDENCE",
        ),
        marginal_economic_net=_as_metric(
            None if ablation is None else ablation.mean_marginal_economic_net,
            reason="NO_ABLATION_EVIDENCE",
        ),
        drawdown_reduction_pct=_as_metric(
            None if ablation is None else ablation.mean_drawdown_reduction_pct,
            reason="NO_ABLATION_EVIDENCE",
        ),
        suggested_state=state,
        state_reasons=reasons,
    )
