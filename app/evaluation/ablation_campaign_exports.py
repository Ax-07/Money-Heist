from __future__ import annotations

import json
from typing import Any

from .ablation import AblationComparison, AblationMetricDelta
from .ablation_campaign_execution import AblationCampaignExecutionReport

_SCHEMA_VERSION = "money-heist.ablation-campaign-export.v1"


def _metric_delta(metric: AblationMetricDelta) -> dict[str, Any]:
    return {
        "value": None if metric.value is None else str(metric.value),
        "status": metric.status.value,
        "reason": metric.reason,
    }


def _period_metric(metric: Any) -> dict[str, Any]:
    return {
        "value": None if metric.value is None else str(metric.value),
        "status": str(metric.status),
        "reason": metric.reason,
    }


def _comparison(comparison: AblationComparison) -> dict[str, Any]:
    return {
        "agent_id": comparison.agent_id,
        "comparison_fingerprint": comparison.comparison_fingerprint,
        "baseline_run_id": comparison.baseline_run_id,
        "ablated_run_id": comparison.ablated_run_id,
        "dataset_id": comparison.dataset_id,
        "role": comparison.role,
        "period_start": comparison.period_start.isoformat(),
        "period_end": comparison.period_end.isoformat(),
        "processed_candles": comparison.processed_candles,
        "opportunity_count": comparison.opportunity_count,
        "closed_trade_count_delta": comparison.closed_trade_count_delta,
        "marginal_trading_net": _metric_delta(comparison.marginal_trading_net),
        "marginal_economic_net": _metric_delta(comparison.marginal_economic_net),
        "drawdown_reduction_pct": _metric_delta(comparison.drawdown_reduction_pct),
        "additional_ai_cost_eur": str(comparison.additional_ai_cost_eur),
        "is_out_of_sample": comparison.is_out_of_sample,
    }


def _execution(execution: Any) -> dict[str, Any]:
    variant = execution.variant
    report = execution.period_report
    return {
        "variant_id": variant.variant_id,
        "kind": variant.kind.value,
        "excluded_agent_id": variant.excluded_agent_id,
        "included_agents": list(variant.included_agents),
        "run_id": report.run_id,
        "dataset_id": report.dataset_id,
        "role": report.role.value,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "processed_candles": report.processed_candles,
        "opportunity_count": report.opportunity_count,
        "executed_order_count": report.executed_order_count,
        "closed_trade_count": report.closed_trade_count,
        "trading_net": _period_metric(report.trading_net),
        "economic_net": _period_metric(report.economic_net),
        "max_drawdown_pct": _period_metric(report.max_drawdown_pct),
        "ai_cost_eur": str(report.ai_cost_eur),
        "self_funding_ratio": (
            None if report.self_funding_ratio is None else str(report.self_funding_ratio)
        ),
        "self_funding_status": report.self_funding_status,
        "business_sha256": report.business_sha256,
    }


def ablation_campaign_execution_to_dict(
    report: AblationCampaignExecutionReport,
) -> dict[str, Any]:
    """Return a compact audit export without serializing runtime/replay internals."""

    return {
        "schema_version": _SCHEMA_VERSION,
        "campaign_id": report.campaign_id,
        "comparison_fingerprint": report.comparison_fingerprint,
        "role": report.role.value,
        "execution_fingerprint": report.execution_fingerprint,
        "executions": [_execution(item) for item in report.executions],
        "comparisons": [_comparison(item) for item in report.comparisons],
    }


def ablation_campaign_execution_to_json(
    report: AblationCampaignExecutionReport,
    *,
    indent: int = 2,
) -> str:
    return json.dumps(
        ablation_campaign_execution_to_dict(report),
        indent=indent,
        sort_keys=True,
        ensure_ascii=False,
    )


__all__ = [
    "ablation_campaign_execution_to_dict",
    "ablation_campaign_execution_to_json",
]
