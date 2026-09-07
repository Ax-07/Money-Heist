from __future__ import annotations

from decimal import Decimal

from .agents import calculate_agent_metrics
from .ai_costs import calculate_ai_cost_metrics
from .lisbon import DeterministicLisbonReporter
from .models import EvaluationReport, EvaluationSource, Metric
from .trading import calculate_trading_metrics


class EvaluationService:
    """Deterministic, rebuildable Batch 10 evaluation service."""

    report_version = "batch10.evaluation.v1"

    def __init__(self, *, lisbon: DeterministicLisbonReporter | None = None) -> None:
        self._lisbon = lisbon or DeterministicLisbonReporter()

    def evaluate(self, source: EvaluationSource) -> EvaluationReport:
        trading = calculate_trading_metrics(
            source.executions,
            marks=source.marks,
            equity_points=source.equity_points,
        )
        ai_costs = calculate_ai_cost_metrics(source.ai_usage, source.opportunity_traces)
        agents = calculate_agent_metrics(source.ai_usage, source.opportunity_traces)
        lisbon = self._lisbon.build(
            trading=trading,
            total_ai_cost_eur=ai_costs.total_cost_eur,
            agents=agents,
        )

        economic_net = lisbon.economic_net
        ratio = lisbon.self_funding_ratio
        return EvaluationReport(
            report_version=self.report_version,
            trading=trading,
            ai_costs=ai_costs,
            agents=agents,
            opportunity_traces=source.opportunity_traces,
            counterfactual_outcomes=source.counterfactual_outcomes,
            economic_net=economic_net,
            self_funding_ratio=ratio,
            lisbon=lisbon,
        )


def economic_net(trading_net: Metric, ai_cost_eur: Decimal) -> Metric:
    if trading_net.value is None:
        return Metric.unavailable("TRADING_NET_UNAVAILABLE")
    return Metric.available(trading_net.value - ai_cost_eur)
