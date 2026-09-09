from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.evaluation.task_force import task_force_report_fingerprint
from app.evaluation.task_force_replay import (
    TaskForceReplayExecutor,
    TaskForceReplayRuntime,
    TaskForceReplayVariantKind,
    build_task_force_replay_plan,
)
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.reports import BacktestMetricSnapshot, BacktestPeriodReport
from app.services.backtest.splits import BacktestPeriodRole
from app.task_force.aggregation import (
    TaskForceAggregatedFinding,
    TaskForceAggregatedMember,
    TaskForceReport,
    task_force_execution_fingerprint,
)
from app.task_force.execution import TaskForceMemberAnalysis, TaskForceMemberFinding
from app.task_force.execution_runtime import (
    TaskForceExecutionRunStatus,
    TaskForceExecutionUsageSnapshot,
    TaskForceMemberExecutionRecord,
    TaskForceMemberUsageSnapshot,
    TaskForceMultiMemberExecution,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _source_run(*, assumptions: dict[str, str] | None = None) -> BacktestRun:
    dataset = DatasetRef(
        dataset_id="btc-h1-2026",
        version="v1",
        content_sha256="d" * 64,
        symbol="BTCUSDT",
        timeframe="1h",
        source="fixture",
        candle_count=100,
        start_at=NOW - timedelta(days=30),
        end_at=NOW,
    )
    config = BacktestConfig(
        system_id="balanced_v1",
        risk_version="risk-v1",
        execution_assumptions=assumptions or {},
    )
    return BacktestRun.create(dataset=dataset, config=config)


def _task_force_artifacts(opportunity_id: str = "opp-1"):
    analysis = TaskForceMemberAnalysis(
        task_force_id="tf-1",
        execution_run_id="tf-run-1",
        member_id="member-1",
        agent_id="berlin",
        answer="trend remains constructive",
        findings=(
            TaskForceMemberFinding(
                finding_id="f-1",
                summary="trend evidence",
                evidence_refs=("market.close",),
            ),
        ),
        uncertainties=("regime may shift",),
        follow_up_questions=("confirm volume",),
        confidence=Decimal("0.70"),
    )
    record = TaskForceMemberExecutionRecord(
        member_id="member-1",
        agent_id="berlin",
        gateway_request_id="11111111-1111-4111-8111-111111111111",
        compute_quote_fingerprint_sha256=SHA_A,
        compute_gate_fingerprint_sha256=SHA_B,
        route_id="economy",
        model_id="mock-economy",
        attempts=1,
        usage_record_count=1,
        actual_cost_eur=Decimal("0.05"),
        latency_ms_total=10,
        analysis=analysis,
    )
    usage_before = TaskForceExecutionUsageSnapshot(
        task_force_id="tf-1",
        spent_total_eur=Decimal("0"),
        used_total_calls=0,
        members=(
            TaskForceMemberUsageSnapshot(
                member_id="member-1",
                agent_id="berlin",
                spent_eur=Decimal("0"),
                used_calls=0,
            ),
        ),
    )
    usage_after = TaskForceExecutionUsageSnapshot(
        task_force_id="tf-1",
        spent_total_eur=Decimal("0.05"),
        used_total_calls=1,
        members=(
            TaskForceMemberUsageSnapshot(
                member_id="member-1",
                agent_id="berlin",
                spent_eur=Decimal("0.05"),
                used_calls=1,
            ),
        ),
    )
    execution = TaskForceMultiMemberExecution(
        task_force_id="tf-1",
        execution_run_id="tf-run-1",
        execution_contract_fingerprint_sha256=SHA_C,
        started_at=NOW - timedelta(seconds=2),
        status=TaskForceExecutionRunStatus.COMPLETED,
        expected_member_count=1,
        completed_member_count=1,
        member_records=(record,),
        usage_before=usage_before,
        usage_after=usage_after,
        gateway_calls_performed=True,
        cost_accounting_complete=True,
        aggregation_ready=True,
    )
    member = TaskForceAggregatedMember(
        member_id="member-1",
        agent_id="berlin",
        task_role="analysis",
        answer=analysis.answer,
        confidence=analysis.confidence,
        finding_ids=("f-1",),
        uncertainties=analysis.uncertainties,
        follow_up_questions=analysis.follow_up_questions,
    )
    finding = TaskForceAggregatedFinding(
        member_id="member-1",
        agent_id="berlin",
        finding_id="f-1",
        summary="trend evidence",
        evidence_refs=("market.close",),
    )
    report = TaskForceReport(
        task_force_id="tf-1",
        execution_run_id="tf-run-1",
        request_id="request-1",
        system_id="balanced_v1",
        opportunity_id=opportunity_id,
        objective="deep analysis",
        question="what matters?",
        execution_contract_fingerprint_sha256=SHA_C,
        execution_fingerprint_sha256=task_force_execution_fingerprint(execution),
        members=(member,),
        findings=(finding,),
        uncertainties=analysis.uncertainties,
        follow_up_questions=analysis.follow_up_questions,
        red_team_required=False,
        red_team_present=False,
        member_actual_cost_eur=Decimal("0.05"),
        member_attempt_count=1,
        aggregated_at=NOW,
        report_fingerprint_sha256=SHA_A,
    )
    report = report.model_copy(
        update={"report_fingerprint_sha256": task_force_report_fingerprint(report)}
    )
    return report, execution


class FakeRunner:
    def __init__(self, *, processed_candles: int = 100, opportunity_count: int = 10):
        self.processed_candles = processed_candles
        self.opportunity_count = opportunity_count
        self.calls = []

    async def run(self, *, candles, run, cancel_check=None):
        self.calls.append((tuple(candles), run.run_id, cancel_check))
        result = SimpleNamespace(
            run=run,
            processed_candles=self.processed_candles,
            opportunity_count=self.opportunity_count,
            executed_order_count=1,
        )
        return SimpleNamespace(backtest_result=result)


async def _evaluation_fn(replay, **kwargs):
    return SimpleNamespace(tag=replay.backtest_result.run.run_id, kwargs=kwargs)


def _period_report(
    variant,
    role,
    *,
    trading: str,
    economic: str,
    drawdown: str,
    processed_candles: int = 100,
    opportunity_count: int = 10,
):
    return BacktestPeriodReport(
        role=role,
        run_id=variant.run.run_id,
        dataset_id=variant.run.dataset.dataset_id,
        period_start=variant.run.period_start,
        period_end=variant.run.period_end,
        processed_candles=processed_candles,
        opportunity_count=opportunity_count,
        executed_order_count=1,
        closed_trade_count=1,
        trading_net=BacktestMetricSnapshot(Decimal(trading), "AVAILABLE"),
        max_drawdown_pct=BacktestMetricSnapshot(Decimal(drawdown), "AVAILABLE"),
        ai_cost_eur=Decimal("0.10"),
        economic_net=BacktestMetricSnapshot(Decimal(economic), "AVAILABLE"),
        self_funding_ratio=None,
        self_funding_status="AVAILABLE",
        business_sha256="e" * 64,
    )


def _patch_reports(
    monkeypatch,
    plan,
    *,
    baseline=("10", "8", "0.12"),
    treatment=("13", "10", "0.09"),
    processed=(100, 100),
    opportunities=(10, 10),
):
    by_run = {
        plan.baseline.run.run_id: _period_report(
            plan.baseline,
            BacktestPeriodRole.OOS,
            trading=baseline[0],
            economic=baseline[1],
            drawdown=baseline[2],
            processed_candles=processed[0],
            opportunity_count=opportunities[0],
        ),
        plan.treatment.run.run_id: _period_report(
            plan.treatment,
            BacktestPeriodRole.OOS,
            trading=treatment[0],
            economic=treatment[1],
            drawdown=treatment[2],
            processed_candles=processed[1],
            opportunity_count=opportunities[1],
        ),
    }

    def fake_from_evaluation(cls, role, replay, evaluation):
        report = by_run[replay.backtest_result.run.run_id]
        assert report.role is role
        return report

    monkeypatch.setattr(
        BacktestPeriodReport,
        "from_evaluation",
        classmethod(fake_from_evaluation),
    )


def _factory(plan, *, report=None, execution=None, shared_runner=None, shared_broker=None):
    if report is None or execution is None:
        default_report, default_execution = _task_force_artifacts(plan.target_opportunity_id)
        report = report or default_report
        execution = execution or default_execution
    created = []

    def factory(*, variant):
        runner = shared_runner or FakeRunner()
        broker = shared_broker or object()
        if variant.kind is TaskForceReplayVariantKind.BASELINE:
            reports = ()
            executions = ()
        else:
            reports = (report,)
            executions = (execution,)
        runtime = TaskForceReplayRuntime(
            runner=runner,
            broker=broker,
            ai_usage_records=lambda: (),
            paper_events=lambda: (),
            task_force_reports=lambda: reports,
            task_force_executions=lambda: executions,
        )
        created.append(runtime)
        return runtime

    return factory, created


def test_plan_is_deterministic_and_creates_baseline_then_treatment_twins():
    source = _source_run()
    first = build_task_force_replay_plan(source, target_opportunity_id="opp-1")
    second = build_task_force_replay_plan(source, target_opportunity_id="opp-1")
    assert first == second
    assert first.baseline.kind is TaskForceReplayVariantKind.BASELINE
    assert first.treatment.kind is TaskForceReplayVariantKind.WITH_TASK_FORCE
    assert first.baseline.run.run_id != first.treatment.run.run_id
    assert len(first.comparison_fingerprint) == 64
    assert first.baseline.run.config.execution_assumptions["task_force_replay_enabled"] == "False"
    assert first.treatment.run.config.execution_assumptions["task_force_replay_enabled"] == "True"


def test_plan_rejects_reserved_execution_assumption_collision():
    source = _source_run(assumptions={"task_force_replay_variant": "foreign"})
    with pytest.raises(ValueError, match="reserved"):
        build_task_force_replay_plan(source, target_opportunity_id="opp-1")


def test_runtime_is_paper_only():
    with pytest.raises(ValueError, match="PAPER-only"):
        TaskForceReplayRuntime(
            runner=FakeRunner(),
            broker=object(),
            ai_usage_records=lambda: (),
            paper_events=lambda: (),
            task_force_reports=lambda: (),
            task_force_executions=lambda: (),
            execution_mode="LIVE",
        )


def test_executor_produces_comparison_and_task_force_evaluation(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan)
    factory, created = _factory(plan)
    result = asyncio.run(
        TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
            plan,
            candles=(object(),),
            role=BacktestPeriodRole.OOS,
        )
    )
    assert len(created) == 2
    assert result.comparison.marginal_trading_net.value == Decimal("3")
    assert result.comparison.marginal_economic_net.value == Decimal("2")
    assert result.comparison.drawdown_reduction_pct.value == Decimal("0.03")
    assert result.task_force_evaluation.total_actual_cost_eur == Decimal("0.05")
    assert result.task_force_evaluation.comparison_is_out_of_sample is True
    assert result.paper_only is True
    assert result.live_authority is False
    assert len(result.replay_fingerprint_sha256) == 64


def test_empty_candles_are_rejected_before_runtime_creation(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan)
    factory, created = _factory(plan)
    with pytest.raises(ValueError, match="requires candles"):
        asyncio.run(
            TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
                plan,
                candles=(),
                role=BacktestPeriodRole.OOS,
            )
        )
    assert created == []


def test_baseline_cannot_emit_task_force_artifacts(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan)
    report, execution = _task_force_artifacts("opp-1")

    def factory(*, variant):
        artifacts = (report,) if variant.kind is TaskForceReplayVariantKind.BASELINE else (report,)
        executions = (execution,)
        return TaskForceReplayRuntime(
            runner=FakeRunner(),
            broker=object(),
            ai_usage_records=lambda: (),
            paper_events=lambda: (),
            task_force_reports=lambda: artifacts,
            task_force_executions=lambda: executions,
        )

    with pytest.raises(ValueError, match="baseline replay must not produce"):
        asyncio.run(
            TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
            )
        )


def test_treatment_requires_exactly_one_report_and_execution(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan)

    def factory(*, variant):
        return TaskForceReplayRuntime(
            runner=FakeRunner(),
            broker=object(),
            ai_usage_records=lambda: (),
            paper_events=lambda: (),
            task_force_reports=lambda: (),
            task_force_executions=lambda: (),
        )

    with pytest.raises(ValueError, match="exactly one"):
        asyncio.run(
            TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
            )
        )


def test_treatment_report_must_target_planned_opportunity(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan)
    wrong_report, execution = _task_force_artifacts("opp-2")
    factory, _ = _factory(plan, report=wrong_report, execution=execution)
    with pytest.raises(ValueError, match="wrong opportunity"):
        asyncio.run(
            TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
            )
        )



def test_treatment_report_must_match_replay_system(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan)
    report, execution = _task_force_artifacts("opp-1")
    wrong = report.model_copy(update={"system_id": "other-system"})
    wrong = wrong.model_copy(
        update={"report_fingerprint_sha256": task_force_report_fingerprint(wrong)}
    )
    factory, _ = _factory(plan, report=wrong, execution=execution)
    with pytest.raises(ValueError, match="wrong system"):
        asyncio.run(
            TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
            )
        )


def test_treatment_report_must_stay_inside_replay_period(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan)
    report, execution = _task_force_artifacts("opp-1")
    late = report.model_copy(
        update={"aggregated_at": plan.treatment.run.period_end + timedelta(seconds=1)}
    )
    late = late.model_copy(
        update={"report_fingerprint_sha256": task_force_report_fingerprint(late)}
    )
    factory, _ = _factory(plan, report=late, execution=execution)
    with pytest.raises(ValueError, match="outside replay period"):
        asyncio.run(
            TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
            )
        )

def test_stale_treatment_report_fingerprint_is_rejected(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan)
    report, execution = _task_force_artifacts("opp-1")
    stale = report.model_copy(update={"report_fingerprint_sha256": "f" * 64})
    factory, _ = _factory(plan, report=stale, execution=execution)
    with pytest.raises(ValueError, match="fingerprint is stale"):
        asyncio.run(
            TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
            )
        )


def test_reused_runner_is_rejected(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan)
    factory, _ = _factory(plan, shared_runner=FakeRunner())
    with pytest.raises(ValueError, match="reused a replay runner"):
        asyncio.run(
            TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
            )
        )


def test_reused_paper_broker_is_rejected(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan)
    factory, _ = _factory(plan, shared_broker=object())
    with pytest.raises(ValueError, match="reused a PAPER broker"):
        asyncio.run(
            TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
            )
        )


def test_wrong_replay_run_is_rejected(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan)
    report, execution = _task_force_artifacts("opp-1")

    class WrongRunner(FakeRunner):
        async def run(self, *, candles, run, cancel_check=None):
            replay = await super().run(candles=candles, run=run, cancel_check=cancel_check)
            replay.backtest_result.run = _source_run()
            return replay

    def factory(*, variant):
        enabled = variant.kind is TaskForceReplayVariantKind.WITH_TASK_FORCE
        return TaskForceReplayRuntime(
            runner=WrongRunner(),
            broker=object(),
            ai_usage_records=lambda: (),
            paper_events=lambda: (),
            task_force_reports=lambda: (report,) if enabled else (),
            task_force_executions=lambda: (execution,) if enabled else (),
        )

    with pytest.raises(ValueError, match="wrong Task Force variant run"):
        asyncio.run(
            TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
            )
        )


def test_processed_candle_mismatch_fails_closed(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan, processed=(100, 99))
    factory, _ = _factory(plan)
    with pytest.raises(ValueError, match="processed_candles"):
        asyncio.run(
            TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
            )
        )


def test_opportunity_count_mismatch_fails_closed(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan, opportunities=(10, 11))
    factory, _ = _factory(plan)
    with pytest.raises(ValueError, match="opportunity_count"):
        asyncio.run(
            TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
            )
        )


def test_task_force_execution_binding_is_validated(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan)
    report, execution = _task_force_artifacts("opp-1")
    wrong_execution = execution.model_copy(update={"task_force_id": "tf-other"})
    factory, _ = _factory(plan, report=report, execution=wrong_execution)
    with pytest.raises(ValueError, match="task_force_id does not match report"):
        asyncio.run(
            TaskForceReplayExecutor(factory, evaluation_fn=_evaluation_fn).execute(
                plan,
                candles=(object(),),
                role=BacktestPeriodRole.OOS,
            )
        )


def test_report_fingerprint_is_stable_for_identical_campaign(monkeypatch):
    plan = build_task_force_replay_plan(_source_run(), target_opportunity_id="opp-1")
    _patch_reports(monkeypatch, plan)
    factory1, _ = _factory(plan)
    first = asyncio.run(
        TaskForceReplayExecutor(factory1, evaluation_fn=_evaluation_fn).execute(
            plan,
            candles=(object(),),
            role=BacktestPeriodRole.OOS,
        )
    )
    factory2, _ = _factory(plan)
    second = asyncio.run(
        TaskForceReplayExecutor(factory2, evaluation_fn=_evaluation_fn).execute(
            plan,
            candles=(object(),),
            role=BacktestPeriodRole.OOS,
        )
    )
    assert first.replay_fingerprint_sha256 == second.replay_fingerprint_sha256
    assert first.automatic_state_change is False
    assert first.trade_proposal_authority is False
    assert first.registry_mutation is False
    assert first.risk_authority is False
    assert first.live_authority is False
