from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.evaluation.ablation_campaign import build_ablation_campaign
from app.evaluation.ablation_campaign_execution import (
    AblationCampaignExecutor,
    AblationVariantRuntime,
)
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.reports import BacktestMetricSnapshot, BacktestPeriodReport
from app.services.backtest.splits import BacktestPeriodRole


@dataclass
class FakeBroker:
    name: str


class FakeRunner:
    def __init__(self, *, trading_net: Decimal, economic_net: Decimal, drawdown: Decimal) -> None:
        self.trading_net = trading_net
        self.economic_net = economic_net
        self.drawdown = drawdown
        self.calls: list[tuple[object, str]] = []

    async def run(self, *, candles, run, cancel_check=None):
        self.calls.append((candles, run.run_id))
        if cancel_check is not None and cancel_check():
            raise RuntimeError("cancelled")
        return SimpleNamespace(
            backtest_result=SimpleNamespace(
                run=run,
                processed_candles=24,
                opportunity_count=5,
                executed_order_count=2,
            ),
            metric_fixture=(self.trading_net, self.economic_net, self.drawdown),
        )


@dataclass(frozen=True)
class FakeEvaluation:
    report: object


async def fake_evaluate(replay, *, broker, ai_usage_records, paper_events):
    assert isinstance(broker, FakeBroker)
    assert tuple(ai_usage_records) == ("usage",)
    assert tuple(paper_events) == ("event",)
    trading_net, economic_net, drawdown = replay.metric_fixture
    return FakeEvaluation(
        report=SimpleNamespace(
            trading=SimpleNamespace(
                closed_trade_count=2,
                trading_net=SimpleNamespace(value=trading_net, status="AVAILABLE", reason=None),
                max_drawdown_pct=SimpleNamespace(
                    value=drawdown,
                    status="AVAILABLE",
                    reason=None,
                ),
            ),
            ai_costs=SimpleNamespace(total_cost_eur=Decimal("1")),
            economic_net=SimpleNamespace(
                value=economic_net,
                status="AVAILABLE",
                reason=None,
            ),
            self_funding_ratio=SimpleNamespace(value=Decimal("2"), status="SELF_FUNDED"),
        )
    )


def _source_run() -> BacktestRun:
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
        ai_mode="MOCK",
        initial_balance=Decimal("1000"),
        execution_assumptions={"fixture": "true"},
    )
    return BacktestRun.create(
        dataset=dataset,
        config=config,
        period_start=datetime(2026, 1, 2, tzinfo=UTC),
        period_end=datetime(2026, 1, 4, tzinfo=UTC),
    )


def _patch_period_report(monkeypatch) -> None:
    def from_evaluation(cls, role, replay, evaluation):
        trading_net, economic_net, drawdown = replay.metric_fixture
        run = replay.backtest_result.run
        return BacktestPeriodReport(
            role=role,
            run_id=run.run_id,
            dataset_id=run.dataset.dataset_id,
            period_start=run.period_start,
            period_end=run.period_end,
            processed_candles=24,
            opportunity_count=5,
            executed_order_count=2,
            closed_trade_count=2,
            trading_net=BacktestMetricSnapshot(trading_net, "AVAILABLE"),
            max_drawdown_pct=BacktestMetricSnapshot(drawdown, "AVAILABLE"),
            ai_cost_eur=Decimal("1"),
            economic_net=BacktestMetricSnapshot(economic_net, "AVAILABLE"),
            self_funding_ratio=Decimal("2"),
            self_funding_status="SELF_FUNDED",
            business_sha256=(run.run_id.replace("-", "") + "0" * 64)[:64],
        )

    monkeypatch.setattr(
        BacktestPeriodReport,
        "from_evaluation",
        classmethod(from_evaluation),
        raising=False,
    )
    monkeypatch.setattr(
        BacktestPeriodReport,
        "is_out_of_sample",
        property(lambda self: self.role is BacktestPeriodRole.OOS),
        raising=False,
    )


def _factory_with_metrics(plan):
    metrics = {
        plan.baseline.variant_id: (Decimal("12"), Decimal("11"), Decimal("0.08")),
        plan.without_agent("berlin").variant_id: (
            Decimal("8"),
            Decimal("7"),
            Decimal("0.10"),
        ),
        plan.without_agent("tokyo").variant_id: (
            Decimal("13"),
            Decimal("12"),
            Decimal("0.07"),
        ),
    }
    seen_specialists: list[tuple[str, tuple[str, ...]]] = []

    def factory(*, variant, specialists):
        seen_specialists.append((variant.variant_id, tuple(specialists)))
        runner = FakeRunner(
            trading_net=metrics[variant.variant_id][0],
            economic_net=metrics[variant.variant_id][1],
            drawdown=metrics[variant.variant_id][2],
        )
        return AblationVariantRuntime(
            runner=runner,
            broker=FakeBroker(variant.variant_id),
            ai_usage_records=lambda: ("usage",),
            paper_events=lambda: ("event",),
        )

    return factory, seen_specialists


def test_executor_runs_baseline_and_twins_and_builds_comparisons(monkeypatch) -> None:
    async def scenario() -> None:
        _patch_period_report(monkeypatch)
        plan = build_ablation_campaign(
            _source_run(),
            included_agents=["berlin", "tokyo", "nairobi"],
            target_agents=["berlin", "tokyo"],
        )
        factory, seen = _factory_with_metrics(plan)
        executor = AblationCampaignExecutor(factory, evaluation_fn=fake_evaluate)

        result = await executor.execute(
            plan,
            candles=(object(),),
            role=BacktestPeriodRole.OOS,
            specialists={"berlin": object(), "tokyo": object(), "nairobi": object()},
        )

        assert len(result.executions) == 3
        assert tuple(item.agent_id for item in result.comparisons) == ("berlin", "tokyo")
        assert result.comparison_for("berlin").marginal_economic_net.value == Decimal("4")
        assert result.comparison_for("tokyo").marginal_economic_net.value == Decimal("-1")
        assert result.comparison_for("berlin").drawdown_reduction_pct.value == Decimal("0.02")
        assert seen == [
            (plan.baseline.variant_id, ("berlin", "nairobi", "tokyo")),
            (plan.without_agent("berlin").variant_id, ("nairobi", "tokyo")),
            (plan.without_agent("tokyo").variant_id, ("berlin", "nairobi")),
        ]

    asyncio.run(scenario())


def test_execution_fingerprint_is_deterministic(monkeypatch) -> None:
    async def scenario() -> None:
        _patch_period_report(monkeypatch)
        plan = build_ablation_campaign(
            _source_run(),
            included_agents=["berlin", "tokyo", "nairobi"],
            target_agents=["berlin", "tokyo"],
        )
        specialists = {"berlin": object(), "tokyo": object(), "nairobi": object()}

        first_factory, _ = _factory_with_metrics(plan)
        second_factory, _ = _factory_with_metrics(plan)
        first = await AblationCampaignExecutor(first_factory, evaluation_fn=fake_evaluate).execute(
            plan,
            candles=(object(),),
            role=BacktestPeriodRole.OOS,
            specialists=specialists,
        )
        second_executor = AblationCampaignExecutor(
            second_factory,
            evaluation_fn=fake_evaluate,
        )
        second = await second_executor.execute(
            plan,
            candles=(object(),),
            role=BacktestPeriodRole.OOS,
            specialists=specialists,
        )

        assert first.execution_fingerprint == second.execution_fingerprint
        assert len(first.execution_fingerprint) == 64

    asyncio.run(scenario())


def test_executor_rejects_reused_runner(monkeypatch) -> None:
    async def scenario() -> None:
        _patch_period_report(monkeypatch)
        plan = build_ablation_campaign(
            _source_run(),
            included_agents=["berlin", "tokyo"],
            target_agents=["berlin"],
        )
        shared_runner = FakeRunner(
            trading_net=Decimal("1"),
            economic_net=Decimal("1"),
            drawdown=Decimal("0.1"),
        )

        def factory(*, variant, specialists):
            return AblationVariantRuntime(
                runner=shared_runner,
                broker=FakeBroker(variant.variant_id),
                ai_usage_records=lambda: ("usage",),
                paper_events=lambda: ("event",),
            )

        with pytest.raises(ValueError, match="reused a replay runner"):
            await AblationCampaignExecutor(factory, evaluation_fn=fake_evaluate).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
                specialists={"berlin": object(), "tokyo": object()},
            )

    asyncio.run(scenario())


def test_executor_rejects_reused_broker(monkeypatch) -> None:
    async def scenario() -> None:
        _patch_period_report(monkeypatch)
        plan = build_ablation_campaign(
            _source_run(),
            included_agents=["berlin", "tokyo"],
            target_agents=["berlin"],
        )
        shared_broker = FakeBroker("shared")

        def factory(*, variant, specialists):
            return AblationVariantRuntime(
                runner=FakeRunner(
                    trading_net=Decimal("1"),
                    economic_net=Decimal("1"),
                    drawdown=Decimal("0.1"),
                ),
                broker=shared_broker,
                ai_usage_records=lambda: ("usage",),
                paper_events=lambda: ("event",),
            )

        with pytest.raises(ValueError, match="reused a PAPER broker"):
            await AblationCampaignExecutor(factory, evaluation_fn=fake_evaluate).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
                specialists={"berlin": object(), "tokyo": object()},
            )

    asyncio.run(scenario())


def test_executor_rejects_wrong_replay_run(monkeypatch) -> None:
    async def scenario() -> None:
        _patch_period_report(monkeypatch)
        plan = build_ablation_campaign(
            _source_run(),
            included_agents=["berlin", "tokyo"],
            target_agents=["berlin"],
        )

        class WrongRunner(FakeRunner):
            async def run(self, *, candles, run, cancel_check=None):
                replay = await super().run(candles=candles, run=run, cancel_check=cancel_check)
                replay.backtest_result.run = plan.baseline.run
                return replay

        def factory(*, variant, specialists):
            return AblationVariantRuntime(
                runner=WrongRunner(
                    trading_net=Decimal("1"),
                    economic_net=Decimal("1"),
                    drawdown=Decimal("0.1"),
                ),
                broker=FakeBroker(variant.variant_id),
                ai_usage_records=lambda: ("usage",),
                paper_events=lambda: ("event",),
            )

        with pytest.raises(ValueError, match="wrong campaign run"):
            await AblationCampaignExecutor(factory, evaluation_fn=fake_evaluate).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
                specialists={"berlin": object(), "tokyo": object()},
            )

    asyncio.run(scenario())


def test_executor_requires_candles(monkeypatch) -> None:
    async def scenario() -> None:
        _patch_period_report(monkeypatch)
        plan = build_ablation_campaign(
            _source_run(),
            included_agents=["berlin", "tokyo"],
            target_agents=["berlin"],
        )
        factory, _ = _factory_with_metrics(
            build_ablation_campaign(
                _source_run(),
                included_agents=["berlin", "tokyo", "nairobi"],
                target_agents=["berlin", "tokyo"],
            )
        )
        with pytest.raises(ValueError, match="requires candles"):
            await AblationCampaignExecutor(factory, evaluation_fn=fake_evaluate).execute(
                plan,
                candles=(),
                role=BacktestPeriodRole.OOS,
                specialists={"berlin": object(), "tokyo": object()},
            )

    asyncio.run(scenario())


def test_runtime_from_components_reads_usage_and_journal() -> None:
    class Usage:
        records = ["a", "b"]

    class Journal:
        def events(self):
            return ["x"]

    runtime = AblationVariantRuntime.from_components(
        runner=FakeRunner(
            trading_net=Decimal("1"),
            economic_net=Decimal("1"),
            drawdown=Decimal("0.1"),
        ),
        broker=FakeBroker("x"),
        usage_recorder=Usage(),
        journal=Journal(),
    )

    assert tuple(runtime.ai_usage_records()) == ("a", "b")
    assert tuple(runtime.paper_events()) == ("x",)


def test_runtime_from_components_rejects_invalid_journal() -> None:
    runtime = AblationVariantRuntime.from_components(
        runner=FakeRunner(
            trading_net=Decimal("1"),
            economic_net=Decimal("1"),
            drawdown=Decimal("0.1"),
        ),
        broker=FakeBroker("x"),
        journal=object(),
    )
    with pytest.raises(TypeError, match="events"):
        runtime.paper_events()
