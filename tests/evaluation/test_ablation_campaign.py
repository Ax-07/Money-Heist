from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.evaluation.ablation_campaign import (
    AblationCampaignVariantKind,
    build_ablation_campaign,
    build_variant_specialists,
)
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.reports import BacktestMetricSnapshot, BacktestPeriodReport
from app.services.backtest.splits import BacktestPeriodRole


def _source_run(*, assumptions: dict[str, str] | None = None) -> BacktestRun:
    dataset = DatasetRef(
        dataset_id="dataset-btc-h1",
        version="v1",
        content_sha256="a" * 64,
        symbol="BTC/USDC",
        timeframe="1h",
        source="fixture",
        candle_count=100,
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 1, 5, tzinfo=UTC),
    )
    config = BacktestConfig(
        system_id="money-heist",
        risk_version="risk-v1",
        random_seed=7,
        ai_mode="MOCK",
        initial_balance=Decimal("1000"),
        prompt_versions={"professor": "v1", "berlin": "v1"},
        execution_assumptions=assumptions or {"fixture": "true"},
    )
    return BacktestRun.create(
        dataset=dataset,
        config=config,
        period_start=datetime(2026, 1, 2, tzinfo=UTC),
        period_end=datetime(2026, 1, 4, tzinfo=UTC),
    )


def _report(run: BacktestRun) -> BacktestPeriodReport:
    return BacktestPeriodReport(
        role=BacktestPeriodRole.OOS,
        run_id=run.run_id,
        dataset_id=run.dataset.dataset_id,
        period_start=run.period_start,
        period_end=run.period_end,
        processed_candles=48,
        opportunity_count=4,
        executed_order_count=2,
        closed_trade_count=2,
        trading_net=BacktestMetricSnapshot(Decimal("12"), "AVAILABLE"),
        max_drawdown_pct=BacktestMetricSnapshot(Decimal("0.08"), "AVAILABLE"),
        ai_cost_eur=Decimal("1.2"),
        economic_net=BacktestMetricSnapshot(Decimal("10.8"), "AVAILABLE"),
        self_funding_ratio=Decimal("9"),
        self_funding_status="SELF_FUNDED",
        business_sha256="b" * 64,
    )


def test_campaign_is_deterministic_and_order_independent() -> None:
    source = _source_run()
    first = build_ablation_campaign(
        source,
        included_agents=["tokyo", "berlin", "nairobi"],
        target_agents=["nairobi", "berlin"],
    )
    second = build_ablation_campaign(
        source,
        included_agents=["nairobi", "berlin", "tokyo"],
        target_agents=["berlin", "nairobi"],
    )

    assert first == second
    assert first.baseline_agents == ("berlin", "nairobi", "tokyo")
    assert first.target_agents == ("berlin", "nairobi")


def test_campaign_builds_one_baseline_and_one_twin_per_target() -> None:
    plan = build_ablation_campaign(
        _source_run(),
        included_agents=["berlin", "tokyo", "nairobi", "rio", "denver"],
        target_agents=["berlin", "rio"],
    )

    assert len(plan.variants) == 3
    assert plan.baseline.kind is AblationCampaignVariantKind.BASELINE
    assert plan.baseline.included_agents == (
        "berlin",
        "denver",
        "nairobi",
        "rio",
        "tokyo",
    )
    assert plan.without_agent("berlin").included_agents == (
        "denver",
        "nairobi",
        "rio",
        "tokyo",
    )
    assert plan.without_agent("rio").included_agents == (
        "berlin",
        "denver",
        "nairobi",
        "tokyo",
    )


def test_campaign_generates_unique_run_ids_with_shared_comparison_fingerprint() -> None:
    plan = build_ablation_campaign(
        _source_run(),
        included_agents=["berlin", "tokyo", "nairobi"],
    )

    assert len({variant.run.run_id for variant in plan.variants}) == 4
    assert {
        variant.comparison_fingerprint for variant in plan.variants
    } == {plan.comparison_fingerprint}
    assert all(variant.run.run_id != plan.source_run_id for variant in plan.variants)


def test_variant_configs_preserve_base_config_and_add_audit_identity() -> None:
    source = _source_run(assumptions={"slippage_model": "fixed"})
    plan = build_ablation_campaign(
        source,
        included_agents=["berlin", "tokyo"],
        target_agents=["tokyo"],
    )
    variant = plan.without_agent("tokyo")

    assert variant.run.config.risk_version == source.config.risk_version
    assert variant.run.config.random_seed == source.config.random_seed
    assert variant.run.config.ai_mode == source.config.ai_mode
    assert variant.run.config.execution_assumptions["slippage_model"] == "fixed"
    assert variant.run.config.execution_assumptions["ablation_campaign_id"] == plan.campaign_id
    assert variant.run.config.execution_assumptions["ablation_excluded_agent"] == "tokyo"
    assert variant.run.config.execution_assumptions["ablation_included_agents"] == "berlin"


def test_campaign_rejects_unknown_targets_duplicates_and_reserved_keys() -> None:
    source = _source_run()
    with pytest.raises(ValueError, match="subset"):
        build_ablation_campaign(
            source,
            included_agents=["berlin", "tokyo"],
            target_agents=["rio"],
        )
    with pytest.raises(ValueError, match="duplicates"):
        build_ablation_campaign(
            source,
            included_agents=["berlin", "Berlin"],
        )

    reserved = _source_run(assumptions={"ablation_campaign_id": "existing"})
    with pytest.raises(ValueError, match="reserved"):
        build_ablation_campaign(reserved, included_agents=["berlin"])


def test_build_variant_specialists_is_non_mutating_and_removes_exact_target() -> None:
    plan = build_ablation_campaign(
        _source_run(),
        included_agents=["berlin", "tokyo", "nairobi"],
        target_agents=["tokyo"],
    )
    full = {"berlin": object(), "tokyo": object(), "nairobi": object()}
    selected = build_variant_specialists(plan.without_agent("tokyo"), full)

    assert tuple(selected) == ("berlin", "nairobi")
    assert set(full) == {"berlin", "tokyo", "nairobi"}
    with pytest.raises(TypeError):
        selected["tokyo"] = object()  # type: ignore[index]


def test_build_variant_specialists_rejects_mapping_drift() -> None:
    plan = build_ablation_campaign(
        _source_run(),
        included_agents=["berlin", "tokyo"],
        target_agents=["tokyo"],
    )
    with pytest.raises(ValueError, match="missing=tokyo"):
        build_variant_specialists(plan.baseline, {"berlin": object()})
    with pytest.raises(ValueError, match="unexpected=rio"):
        build_variant_specialists(
            plan.baseline,
            {"berlin": object(), "tokyo": object(), "rio": object()},
        )


def test_variant_descriptor_bridges_campaign_identity_to_batch18a() -> None:
    plan = build_ablation_campaign(
        _source_run(),
        included_agents=["berlin", "tokyo"],
        target_agents=["berlin"],
    )
    variant = plan.without_agent("berlin")
    descriptor = variant.to_descriptor(_report(variant.run))

    assert descriptor.comparison_fingerprint == plan.comparison_fingerprint
    assert descriptor.included_agents == ("tokyo",)
    assert descriptor.report.run_id == variant.run.run_id


def test_variant_descriptor_rejects_report_from_another_twin() -> None:
    plan = build_ablation_campaign(
        _source_run(),
        included_agents=["berlin", "tokyo"],
        target_agents=["berlin"],
    )
    with pytest.raises(ValueError, match="run_id"):
        plan.without_agent("berlin").to_descriptor(_report(plan.baseline.run))
