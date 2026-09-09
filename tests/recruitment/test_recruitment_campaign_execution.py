from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.recruitment.campaign_execution as execution_module
from app.recruitment import (
    RecruitmentBaselineSpec,
    RecruitmentCampaignExecutor,
    RecruitmentCampaignVariantKind,
    RecruitmentMetricDirection,
    RecruitmentProposal,
    RecruitmentSuccessCriterion,
    RecruitmentVariantRuntime,
    build_recruitment_campaign,
    build_recruitment_variant_specialists,
    specify_recruitment_candidate,
)
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.splits import BacktestPeriodRole


def _candidate():
    proposal = RecruitmentProposal(
        recruitment_id="recruitment-19b-002",
        proposed_name="Marseille",
        role="liquidation_specialist",
        problem="Liquidation context is not covered by the incumbent crew.",
        hypothesis="Adding a liquidation specialist improves OOS evidence net of AI cost.",
        trigger_evidence_refs=("eval:error-family:liquidation",),
    )
    return specify_recruitment_candidate(
        proposal,
        required_data=("liquidations",),
        allowed_tools=("get_liquidation_context",),
        model_class="specialist-small",
        budget_limit_eur=Decimal("5"),
        evaluation_window="frozen DESIGN/VALIDATION/OOS windows",
        baseline=RecruitmentBaselineSpec(
            baseline_id="balanced-v1-incumbent",
            system_id="balanced_v1",
            description="Existing crew without the candidate.",
        ),
        success_criteria=(
            RecruitmentSuccessCriterion(
                metric_key="marginal_economic_net_eur",
                direction=RecruitmentMetricDirection.AT_LEAST,
                threshold=Decimal("0"),
                primary=True,
                rationale="Primary criterion frozen before observing OOS.",
            ),
        ),
    )


def _source_run() -> BacktestRun:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = []
    for index in range(3):
        open_at = start + timedelta(hours=index)
        candles.append(
            {
                "open_time": open_at,
                "close_time": open_at + timedelta(minutes=59),
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100.5"),
                "volume": Decimal("1"),
            }
        )
    dataset = DatasetRef.from_candles(
        candles,
        symbol="BTC/EUR",
        timeframe="1h",
        source="test",
    )
    return BacktestRun.create(
        dataset=dataset,
        config=BacktestConfig(
            system_id="balanced_v1",
            risk_version="risk-v1",
            code_version="96b2288-test",
        ),
    )


def _plan():
    return build_recruitment_campaign(
        _source_run(),
        _candidate(),
        role=BacktestPeriodRole.OOS,
        baseline_agents=("berlin", "tokyo"),
    )


@dataclass(frozen=True)
class _FakePeriodReport:
    role: BacktestPeriodRole
    run_id: str
    dataset_id: str
    period_start: datetime
    period_end: datetime
    marker: str


class _FakePeriodReportFactory:
    @classmethod
    def from_evaluation(cls, role, replay, evaluation):
        run = replay.backtest_result.run
        return _FakePeriodReport(
            role=role,
            run_id=run.run_id,
            dataset_id=run.dataset.dataset_id,
            period_start=run.period_start,
            period_end=run.period_end,
            marker=evaluation.marker,
        )


class _Runner:
    def __init__(self, *, wrong_run: BacktestRun | None = None):
        self.calls = []
        self.wrong_run = wrong_run

    async def run(self, *, candles, run, cancel_check=None):
        self.calls.append((tuple(candles), run.run_id, cancel_check))
        replay_run = self.wrong_run or run
        return SimpleNamespace(backtest_result=SimpleNamespace(run=replay_run))


async def _evaluation_fn(replay, *, broker, ai_usage_records, paper_events):
    return SimpleNamespace(
        marker=f"{id(broker)}:{len(ai_usage_records)}:{len(paper_events)}"
    )


class _RuntimeFactory:
    def __init__(self):
        self.calls = []
        self.runners = []
        self.brokers = []

    def __call__(self, *, variant, specialists):
        runner = _Runner()
        broker = object()
        self.runners.append(runner)
        self.brokers.append(broker)
        self.calls.append((variant.kind, tuple(specialists)))
        return RecruitmentVariantRuntime(
            runner=runner,
            broker=broker,
            ai_usage_records=lambda: (),
            paper_events=lambda: (),
        )


def test_build_variant_specialists_adds_candidate_only_to_candidate_twin() -> None:
    plan = _plan()
    incumbents = {"Berlin": object(), "TOKYO": object()}
    candidate = object()

    baseline = build_recruitment_variant_specialists(
        plan.baseline,
        incumbents,
        candidate_specialist=candidate,
    )
    with_candidate = build_recruitment_variant_specialists(
        plan.with_candidate,
        incumbents,
        candidate_specialist=candidate,
    )

    assert tuple(baseline) == ("berlin", "tokyo")
    assert tuple(with_candidate) == (
        "berlin",
        plan.candidate_agent_id,
        "tokyo",
    )
    assert with_candidate[plan.candidate_agent_id] is candidate
    assert set(incumbents) == {"Berlin", "TOKYO"}
    with pytest.raises(TypeError):
        baseline["nairobi"] = object()  # type: ignore[index]


def test_build_variant_specialists_rejects_incumbent_roster_mismatch() -> None:
    plan = _plan()
    with pytest.raises(ValueError, match="does not match recruitment baseline"):
        build_recruitment_variant_specialists(
            plan.baseline,
            {"berlin": object()},
            candidate_specialist=object(),
        )


def test_executor_runs_isolated_baseline_and_candidate_twins(monkeypatch) -> None:
    monkeypatch.setattr(execution_module, "BacktestPeriodReport", _FakePeriodReportFactory)
    plan = _plan()
    factory = _RuntimeFactory()
    executor = RecruitmentCampaignExecutor(factory, evaluation_fn=_evaluation_fn)

    report = asyncio.run(
        executor.execute(
            plan,
            candles=({"candle": 1},),
            incumbent_specialists={"berlin": object(), "tokyo": object()},
            candidate_specialist=object(),
        )
    )

    assert [kind for kind, _ in factory.calls] == [
        RecruitmentCampaignVariantKind.BASELINE,
        RecruitmentCampaignVariantKind.WITH_CANDIDATE,
    ]
    assert factory.calls[0][1] == ("berlin", "tokyo")
    assert factory.calls[1][1] == ("berlin", plan.candidate_agent_id, "tokyo")
    assert factory.runners[0] is not factory.runners[1]
    assert factory.brokers[0] is not factory.brokers[1]
    assert report.baseline.run_id == plan.baseline.run.run_id
    assert report.with_candidate.run_id == plan.with_candidate.run.run_id
    assert report.role is BacktestPeriodRole.OOS
    assert report.auto_apply is False
    assert report.registry_mutation is False
    assert report.live_authority is False
    assert len(report.execution_fingerprint) == 64


def test_executor_rejects_runner_reuse_between_twins(monkeypatch) -> None:
    monkeypatch.setattr(execution_module, "BacktestPeriodReport", _FakePeriodReportFactory)
    plan = _plan()
    shared_runner = _Runner()

    def factory(*, variant, specialists):
        return RecruitmentVariantRuntime(
            runner=shared_runner,
            broker=object(),
            ai_usage_records=lambda: (),
            paper_events=lambda: (),
        )

    executor = RecruitmentCampaignExecutor(factory, evaluation_fn=_evaluation_fn)
    with pytest.raises(ValueError, match="reused a replay runner"):
        asyncio.run(
            executor.execute(
                plan,
                candles=({"candle": 1},),
                incumbent_specialists={"berlin": object(), "tokyo": object()},
                candidate_specialist=object(),
            )
        )


def test_executor_rejects_paper_broker_reuse_between_twins(monkeypatch) -> None:
    monkeypatch.setattr(execution_module, "BacktestPeriodReport", _FakePeriodReportFactory)
    plan = _plan()
    shared_broker = object()

    def factory(*, variant, specialists):
        return RecruitmentVariantRuntime(
            runner=_Runner(),
            broker=shared_broker,
            ai_usage_records=lambda: (),
            paper_events=lambda: (),
        )

    executor = RecruitmentCampaignExecutor(factory, evaluation_fn=_evaluation_fn)
    with pytest.raises(ValueError, match="reused a PAPER broker"):
        asyncio.run(
            executor.execute(
                plan,
                candles=({"candle": 1},),
                incumbent_specialists={"berlin": object(), "tokyo": object()},
                candidate_specialist=object(),
            )
        )


def test_executor_rejects_wrong_replay_run(monkeypatch) -> None:
    monkeypatch.setattr(execution_module, "BacktestPeriodReport", _FakePeriodReportFactory)
    plan = _plan()
    wrong_run = _source_run()

    def factory(*, variant, specialists):
        return RecruitmentVariantRuntime(
            runner=_Runner(wrong_run=wrong_run),
            broker=object(),
            ai_usage_records=lambda: (),
            paper_events=lambda: (),
        )

    executor = RecruitmentCampaignExecutor(factory, evaluation_fn=_evaluation_fn)
    with pytest.raises(ValueError, match="wrong recruitment run"):
        asyncio.run(
            executor.execute(
                plan,
                candles=({"candle": 1},),
                incumbent_specialists={"berlin": object(), "tokyo": object()},
                candidate_specialist=object(),
            )
        )


def test_executor_rejects_empty_candle_sequence(monkeypatch) -> None:
    monkeypatch.setattr(execution_module, "BacktestPeriodReport", _FakePeriodReportFactory)
    executor = RecruitmentCampaignExecutor(_RuntimeFactory(), evaluation_fn=_evaluation_fn)
    with pytest.raises(ValueError, match="requires candles"):
        asyncio.run(
            executor.execute(
                _plan(),
                candles=(),
                incumbent_specialists={"berlin": object(), "tokyo": object()},
                candidate_specialist=object(),
            )
        )
