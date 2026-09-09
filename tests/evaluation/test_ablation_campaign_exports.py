from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.evaluation.ablation import compare_ablation
from app.evaluation.ablation_campaign import build_ablation_campaign
from app.evaluation.ablation_campaign_execution import (
    AblationCampaignExecutionReport,
    AblationVariantExecution,
)
from app.evaluation.ablation_campaign_exports import (
    ablation_campaign_execution_to_dict,
    ablation_campaign_execution_to_json,
)
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.reports import BacktestMetricSnapshot, BacktestPeriodReport
from app.services.backtest.splits import BacktestPeriodRole


def _source_run() -> BacktestRun:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=10)
    dataset = DatasetRef(
        dataset_id="dataset-18b",
        version="v1",
        content_sha256="a" * 64,
        symbol="BTC/EUR",
        timeframe="1h",
        source="fixture",
        candle_count=10,
        start_at=start,
        end_at=end,
    )
    config = BacktestConfig(
        system_id="balanced_v1",
        risk_version="risk-v1",
        prompt_versions={"berlin": "v1", "tokyo": "v1"},
        model_versions={"berlin": "mock-v1", "tokyo": "mock-v1"},
    )
    return BacktestRun.create(dataset=dataset, config=config)


def _report(run: BacktestRun, *, economic: str, cost: str) -> BacktestPeriodReport:
    metric = lambda value: BacktestMetricSnapshot(Decimal(value), "AVAILABLE")
    return BacktestPeriodReport(
        role=BacktestPeriodRole.OOS,
        run_id=run.run_id,
        dataset_id=run.dataset.dataset_id,
        period_start=run.period_start,
        period_end=run.period_end,
        processed_candles=10,
        opportunity_count=3,
        executed_order_count=2,
        closed_trade_count=2,
        trading_net=metric(economic),
        max_drawdown_pct=metric("0.05"),
        ai_cost_eur=Decimal(cost),
        economic_net=metric(economic),
        self_funding_ratio=Decimal("2"),
        self_funding_status="SELF_FUNDED",
        business_sha256="b" * 64,
    )


def _campaign_report() -> AblationCampaignExecutionReport:
    plan = build_ablation_campaign(
        _source_run(),
        included_agents=("berlin", "tokyo"),
        target_agents=("berlin",),
    )
    baseline = plan.baseline
    twin = plan.without_agent("berlin")
    baseline_report = _report(baseline.run, economic="3", cost="0.2")
    twin_report = _report(twin.run, economic="1", cost="0.1")
    executions = (
        AblationVariantExecution(baseline, baseline_report, object(), object()),
        AblationVariantExecution(twin, twin_report, object(), object()),
    )
    comparison = compare_ablation(
        baseline.to_descriptor(baseline_report),
        twin.to_descriptor(twin_report),
        agent_id="berlin",
    )
    return AblationCampaignExecutionReport(
        campaign_id=plan.campaign_id,
        comparison_fingerprint=plan.comparison_fingerprint,
        role=BacktestPeriodRole.OOS,
        executions=executions,
        comparisons=(comparison,),
        execution_fingerprint="c" * 64,
    )


def test_campaign_export_is_compact_json_safe_and_auditable() -> None:
    report = _campaign_report()
    payload = ablation_campaign_execution_to_dict(report)

    assert payload["schema_version"] == "money-heist.ablation-campaign-export.v1"
    assert payload["campaign_id"] == report.campaign_id
    assert payload["role"] == "OOS"
    assert payload["executions"][0]["kind"] == "BASELINE"
    assert payload["executions"][1]["excluded_agent_id"] == "berlin"
    assert payload["comparisons"][0]["marginal_economic_net"]["value"] == "2"
    assert payload["comparisons"][0]["additional_ai_cost_eur"] == "0.1"
    assert "replay_result" not in json.dumps(payload)
    assert "evaluation_bundle" not in json.dumps(payload)


def test_campaign_json_export_is_deterministic() -> None:
    report = _campaign_report()
    first = ablation_campaign_execution_to_json(report)
    second = ablation_campaign_execution_to_json(report)
    assert first == second
    assert json.loads(first) == ablation_campaign_execution_to_dict(report)
