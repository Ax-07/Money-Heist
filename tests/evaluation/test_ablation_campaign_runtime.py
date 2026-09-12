from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.evaluation.ablation_campaign import build_ablation_campaign
from app.services.backtest.ablation_runtime import (
    PaperAblationRuntimeFactory,
    PaperAblationRuntimeSettings,
    execute_paper_ablation_campaign,
    v1_specialist_factories,
)
from app.intelligence.ai_gateway.routing import ModelPricing
from app.services.backtest.cache import BacktestResponseCache
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import BacktestAIMode, BacktestConfig, BacktestRun
from app.services.backtest.splits import BacktestPeriodRole
from app.trading.risk import MarketConstraints, RiskProfile


class DummyMockClient:
    provider_name = "mock"

    async def complete(self, request):  # pragma: no cover - factory tests do not call AI
        raise AssertionError("AI should not be called while constructing a runtime")


class DummyLiveClient:
    provider_name = "openai"

    async def complete(self, request):  # pragma: no cover - factory tests do not call AI
        raise AssertionError("AI should not be called while constructing a runtime")


def _run(
    *,
    ai_mode: BacktestAIMode = BacktestAIMode.MOCK,
    model_id: str = "mock-model-v1",
) -> BacktestRun:
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
        ai_mode=ai_mode,
        initial_balance=Decimal("1000"),
        prompt_versions={
            "professor": "v1",
            "palermo": "v1",
            "berlin": "v1",
            "tokyo": "v1",
        },
        model_versions={
            "professor": model_id,
            "palermo": model_id,
            "berlin": model_id,
            "tokyo": model_id,
        },
        execution_assumptions={"fixture": "true"},
    )
    return BacktestRun.create(
        dataset=dataset,
        config=config,
        period_start=datetime(2026, 1, 2, tzinfo=UTC),
        period_end=datetime(2026, 1, 4, tzinfo=UTC),
    )


def _settings(**overrides) -> PaperAblationRuntimeSettings:
    values = {
        "risk_profile": RiskProfile(
            risk_profile_id="fixture-risk",
            max_risk_per_trade_pct=Decimal("0.01"),
            max_daily_loss_pct=Decimal("0.03"),
            max_drawdown_pct=Decimal("0.10"),
            max_portfolio_risk_pct=Decimal("0.03"),
            max_positions=3,
            max_leverage=Decimal("1"),
            max_correlated_exposure_pct=Decimal("0.02"),
            min_expected_rr=Decimal("1.5"),
        ),
        "market_constraints": MarketConstraints(
            qty_step=Decimal("0.0001"),
            min_qty=Decimal("0.0001"),
            min_notional=Decimal("5"),
            max_qty=Decimal("10"),
            max_leverage=Decimal("1"),
        ),
        "ai_hard_budget_eur": Decimal("2"),
        "model_id": "mock-model-v1",
        "pricing": ModelPricing(
            input_per_million_eur=Decimal("0"),
            output_per_million_eur=Decimal("0"),
        ),
        "mock_client": DummyMockClient(),
    }
    values.update(overrides)
    return PaperAblationRuntimeSettings(**values)


def _plan(*, ai_mode: BacktestAIMode = BacktestAIMode.MOCK):
    return build_ablation_campaign(
        _run(ai_mode=ai_mode),
        included_agents=["berlin", "tokyo"],
        target_agents=["tokyo"],
    )


def test_v1_specialist_factories_are_normalized_filtered_and_immutable() -> None:
    factories = v1_specialist_factories(["Tokyo", "berlin"])

    assert tuple(factories) == ("berlin", "tokyo")
    assert all(callable(factory) for factory in factories.values())
    with pytest.raises(TypeError):
        factories["rio"] = object()  # type: ignore[index]

    with pytest.raises(ValueError, match="unknown"):
        v1_specialist_factories(["berlin", "unknown-agent"])


def test_settings_fail_closed_on_invalid_budget_model_or_tokens() -> None:
    with pytest.raises(ValueError, match="ai_hard_budget_eur"):
        _settings(ai_hard_budget_eur=Decimal("-1"))
    with pytest.raises(ValueError, match="model_id"):
        _settings(model_id="  ")
    with pytest.raises(ValueError, match="core_max_output_tokens"):
        _settings(core_max_output_tokens=0)


def test_factory_builds_fresh_paper_and_ai_state_for_each_variant() -> None:
    plan = _plan()
    factory = PaperAblationRuntimeFactory(_settings())
    factories = v1_specialist_factories(plan.baseline_agents)

    baseline_factories = {key: factories[key] for key in plan.baseline.included_agents}
    twin = plan.without_agent("tokyo")
    twin_factories = {key: factories[key] for key in twin.included_agents}
    baseline_runtime = factory(variant=plan.baseline, specialists=baseline_factories)
    twin_runtime = factory(variant=twin, specialists=twin_factories)

    assert baseline_runtime.runner is not twin_runtime.runner
    assert baseline_runtime.broker is not twin_runtime.broker

    baseline_pipeline = baseline_runtime.runner.paper_pipeline
    twin_pipeline = twin_runtime.runner.paper_pipeline
    assert baseline_pipeline.portfolio_provider is not twin_pipeline.portfolio_provider
    assert baseline_pipeline.journal is not twin_pipeline.journal
    assert baseline_pipeline.orchestration._budget is not twin_pipeline.orchestration._budget

    baseline_agents = baseline_pipeline.orchestration.specialists
    twin_agents = twin_pipeline.orchestration.specialists
    assert tuple(sorted(baseline_agents)) == ("berlin", "tokyo")
    assert tuple(sorted(twin_agents)) == ("berlin",)
    assert baseline_agents["berlin"] is not twin_agents["berlin"]
    assert baseline_agents["berlin"].gateway is not twin_agents["berlin"].gateway


def test_factory_mirrors_backtest_execution_config_into_paper_broker() -> None:
    plan = _plan()
    factory = PaperAblationRuntimeFactory(_settings())
    factories = v1_specialist_factories(plan.baseline_agents)
    runtime = factory(variant=plan.baseline, specialists=factories)

    config = runtime.broker.config
    run_config = plan.baseline.run.config
    assert config.system_id == run_config.system_id
    assert config.initial_balance == run_config.initial_balance
    assert config.maker_fee_bps == run_config.maker_fee_bps
    assert config.taker_fee_bps == run_config.taker_fee_bps
    assert config.market_slippage_bps == run_config.market_slippage_bps
    assert runtime.ai_usage_records() == ()
    assert runtime.paper_events() == ()


def test_factory_requires_mode_specific_ai_dependencies() -> None:
    mock_plan = _plan(ai_mode=BacktestAIMode.MOCK)
    with pytest.raises(ValueError, match="mock_client"):
        PaperAblationRuntimeFactory(_settings(mock_client=None))(
            variant=mock_plan.baseline,
            specialists=v1_specialist_factories(mock_plan.baseline_agents),
        )

    cached_plan = _plan(ai_mode=BacktestAIMode.CACHED)
    with pytest.raises(ValueError, match="BacktestResponseCache"):
        PaperAblationRuntimeFactory(_settings(mock_client=None))(
            variant=cached_plan.baseline,
            specialists=v1_specialist_factories(cached_plan.baseline_agents),
        )

    live_plan = _plan(ai_mode=BacktestAIMode.LIVE_EVAL)
    with pytest.raises(ValueError, match="live_client"):
        PaperAblationRuntimeFactory(_settings(mock_client=None))(
            variant=live_plan.baseline,
            specialists=v1_specialist_factories(live_plan.baseline_agents),
        )


def test_factory_accepts_cached_and_live_eval_when_dependencies_are_explicit() -> None:
    cached_plan = _plan(ai_mode=BacktestAIMode.CACHED)
    cached_factory = PaperAblationRuntimeFactory(
        _settings(mock_client=None, cache=BacktestResponseCache())
    )
    cached_runtime = cached_factory(
        variant=cached_plan.baseline,
        specialists=v1_specialist_factories(cached_plan.baseline_agents),
    )
    assert cached_runtime.runner is not None

    live_plan = _plan(ai_mode=BacktestAIMode.LIVE_EVAL)
    live_factory = PaperAblationRuntimeFactory(
        _settings(mock_client=None, live_client=DummyLiveClient())
    )
    live_runtime = live_factory(
        variant=live_plan.baseline,
        specialists=v1_specialist_factories(live_plan.baseline_agents),
    )
    assert live_runtime.runner is not None


def test_factory_rejects_specialist_mapping_drift_and_model_version_mismatch() -> None:
    plan = _plan()
    factory = PaperAblationRuntimeFactory(_settings())
    with pytest.raises(ValueError, match="included_agents"):
        factory(
            variant=plan.baseline,
            specialists={"berlin": v1_specialist_factories(["berlin"])["berlin"]},
        )

    mismatch_plan = build_ablation_campaign(
        _run(model_id="configured-model-v2"),
        included_agents=["berlin", "tokyo"],
        target_agents=["tokyo"],
    )
    with pytest.raises(ValueError, match="model_id disagrees"):
        PaperAblationRuntimeFactory(_settings())(
            variant=mismatch_plan.baseline,
            specialists=v1_specialist_factories(mismatch_plan.baseline_agents),
        )


def test_execute_helper_uses_plan_baseline_factories(monkeypatch) -> None:
    plan = _plan()
    captured = {}
    expected = object()

    class FakeExecutor:
        async def execute(self, plan_arg, **kwargs):
            captured["plan"] = plan_arg
            captured.update(kwargs)
            return expected

    monkeypatch.setattr(
        "app.services.backtest.ablation_runtime.build_paper_ablation_executor",
        lambda settings: FakeExecutor(),
    )
    result = asyncio.run(
        execute_paper_ablation_campaign(
            plan,
            candles=[object()],
            role=BacktestPeriodRole.OOS,
            settings=_settings(),
        )
    )

    assert result is expected
    assert captured["plan"] is plan
    assert tuple(captured["specialists"]) == plan.baseline_agents
    assert captured["role"] is BacktestPeriodRole.OOS


def test_ablation_runtime_reuses_exact_bound_derivatives_archive(tmp_path) -> None:
    from app.services.backtest.derivatives_runtime import (
        historical_derivatives_execution_assumptions,
    )
    from app.services.backtest.historical_derivatives_analytics import (
        HistoricalDerivativesAnalyticsArchive,
    )
    from app.services.backtest.mtf_runtime import mtf_execution_assumptions

    path = tmp_path / "derivatives.csv"
    path.write_text(
        "\n".join(
            [
                (
                    "symbol,instrument,observed_at,available_at,funding_rate,"
                    "open_interest,open_interest_change_pct,long_short_ratio"
                ),
                (
                    "BTC/USDC,PF_XBTUSD,2026-01-01T00:00:00Z,"
                    "2026-01-01T01:00:00Z,,1000,1,1.1"
                ),
                (
                    "BTC/USDC,PF_XBTUSD,2026-01-01T01:00:00Z,"
                    "2026-01-01T02:00:00Z,0.0001,1010,1,1.2"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    archive = HistoricalDerivativesAnalyticsArchive.from_canonical_csv(path)

    assumptions = mtf_execution_assumptions("1m")
    assumptions.update(
        historical_derivatives_execution_assumptions(
            archive,
            max_age_seconds=7200,
        )
    )
    dataset = DatasetRef(
        dataset_id="dataset-btc-m1",
        version="v1",
        content_sha256="b" * 64,
        symbol="BTC/USDC",
        timeframe="1m",
        source="fixture",
        candle_count=500,
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    config = BacktestConfig(
        system_id="money-heist",
        risk_version="risk-v1",
        random_seed=7,
        ai_mode=BacktestAIMode.MOCK,
        initial_balance=Decimal("1000"),
        prompt_versions={
            "professor": "v1",
            "palermo": "v1",
            "berlin": "v1",
            "rio": "v1",
        },
        model_versions={
            "professor": "mock-model-v1",
            "palermo": "mock-model-v1",
            "berlin": "mock-model-v1",
            "rio": "mock-model-v1",
        },
        execution_assumptions=assumptions,
    )
    run = BacktestRun.create(
        dataset=dataset,
        config=config,
        period_start=datetime(2026, 1, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 1, 1, 12, tzinfo=UTC),
    )
    plan = build_ablation_campaign(
        run,
        included_agents=["berlin", "rio"],
        target_agents=["rio"],
    )
    factory = PaperAblationRuntimeFactory(
        _settings(historical_derivatives_archive=archive)
    )
    runtime = factory(
        variant=plan.baseline,
        specialists=v1_specialist_factories(plan.baseline_agents),
    )

    assert runtime.runner.historical_derivatives_archive is archive
    assert runtime.runner.derivatives_max_age_seconds == 7200


def test_denver_ablation_role_requires_explicit_prior() -> None:
    with pytest.raises(ValueError, match="historical_denver_role"):
        _settings(
            historical_denver_role=BacktestPeriodRole.OOS,
        )
