from __future__ import annotations

from decimal import Decimal

from .models import (
    AgentMetrics,
    LisbonEvaluationReport,
    LisbonRecommendation,
    Metric,
    SelfFundingRatio,
    SelfFundingStatus,
    TradingMetrics,
    ZERO,
)


def self_funding_ratio(
    trading_net: Metric,
    ai_cost_eur: Decimal,
    *,
    basis: str,
) -> SelfFundingRatio:
    if trading_net.value is None:
        return SelfFundingRatio(
            value=None,
            status=SelfFundingStatus.TRADING_NET_UNAVAILABLE,
            basis=basis,
        )
    if ai_cost_eur == ZERO:
        return SelfFundingRatio(
            value=None,
            status=SelfFundingStatus.ZERO_AI_COST,
            basis=basis,
        )
    return SelfFundingRatio(
        value=trading_net.value / ai_cost_eur,
        status=SelfFundingStatus.AVAILABLE,
        basis=basis,
    )


class DeterministicLisbonReporter:
    """Read-only economics reporter.

    It deliberately receives metrics only. It has no RiskEngine, budget controller,
    broker, registry mutation API, or agent-state mutation capability.
    """

    report_version = "batch10.lisbon.v1"

    def build(
        self,
        *,
        trading: TradingMetrics,
        total_ai_cost_eur: Decimal,
        agents: tuple[AgentMetrics, ...],
    ) -> LisbonEvaluationReport:
        trading_net, basis = _self_funding_basis(trading)
        ratio = self.self_funding_ratio_for(trading_net, total_ai_cost_eur, basis=basis)
        economic_net = (
            Metric.available(trading_net.value - total_ai_cost_eur)
            if trading_net.value is not None
            else Metric.unavailable("TRADING_NET_UNAVAILABLE")
        )

        observations = [
            f"PAPER fills executes: {trading.executed_fill_count}",
            f"Trades clos: {trading.closed_trade_count}",
            f"Cout IA total EUR: {total_ai_cost_eur}",
            f"Base SelfFundingRatio: {basis}",
        ]
        recommendations: list[LisbonRecommendation] = []

        if trading.closed_trade_count == 0:
            recommendations.append(
                LisbonRecommendation(
                    code="INSUFFICIENT_TRADING_HISTORY",
                    message=(
                        "Accumuler davantage de resultats PAPER avant toute conclusion "
                        "economique."
                    ),
                )
            )
        if ratio.status is SelfFundingStatus.AVAILABLE and ratio.value is not None:
            if ratio.value < Decimal("1"):
                recommendations.append(
                    LisbonRecommendation(
                        code="REVIEW_COMPUTE_EFFICIENCY",
                        message=(
                            "Le cout IA depasse la valeur nette de trading sur la base disponible; "
                            "revoir les appels redondants sans augmenter le risque."
                        ),
                    )
                )
            else:
                recommendations.append(
                    LisbonRecommendation(
                        code="MAINTAIN_RISK_GUARDRAILS",
                        message=(
                            "Le ratio est au-dessus de 1 sur la base disponible; conserver les "
                            "garde-fous et confirmer sur davantage d'historique."
                        ),
                    )
                )
        elif ratio.status is SelfFundingStatus.ZERO_AI_COST:
            observations.append("SelfFundingRatio indisponible: cout IA nul.")

        for agent in agents:
            if agent.call_count == 0:
                continue
            if agent.average_latency_ms.value is None:
                recommendations.append(
                    LisbonRecommendation(
                        code="IMPROVE_AGENT_OBSERVABILITY",
                        agent_id=agent.agent_id,
                        message="Latence indisponible; conserver la metrique comme inconnue.",
                    )
                )

        return LisbonEvaluationReport(
            report_version=self.report_version,
            data_scope="PAPER_EXECUTED_ONLY; COUNTERFACTUAL_EXCLUDED",
            trading_net=trading_net,
            ai_cost_eur=total_ai_cost_eur,
            economic_net=economic_net,
            self_funding_ratio=ratio,
            observations=tuple(observations),
            recommendations=tuple(recommendations),
        )

    @staticmethod
    def self_funding_ratio_for(
        trading_net: Metric,
        ai_cost_eur: Decimal,
        *,
        basis: str,
    ) -> SelfFundingRatio:
        return self_funding_ratio(trading_net, ai_cost_eur, basis=basis)


def _self_funding_basis(trading: TradingMetrics) -> tuple[Metric, str]:
    if trading.trading_net.value is not None:
        return trading.trading_net, "MARK_TO_MARKET"
    return Metric.available(trading.realized_trading_net), "REALIZED_ONLY"
