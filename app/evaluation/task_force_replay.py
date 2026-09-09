from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Protocol

from app.services.backtest.ids import stable_digest, stable_uuid
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.reports import BacktestMetricSnapshot, BacktestPeriodReport
from app.services.backtest.splits import BacktestPeriodRole
from app.task_force.aggregation import TaskForceReport
from app.task_force.execution_runtime import TaskForceMultiMemberExecution

from .models import Metric
from .task_force import (
    TaskForceEvaluationReport,
    TaskForceOutcomeComparison,
    TaskForceRunOutcome,
    compare_task_force_outcomes,
    evaluate_task_force,
    task_force_report_fingerprint,
)

_RESERVED_EXECUTION_KEYS = frozenset(
    {
        "task_force_replay_campaign_id",
        "task_force_replay_comparison_fingerprint",
        "task_force_replay_variant",
        "task_force_replay_target_opportunity_id",
        "task_force_replay_enabled",
    }
)


class TaskForceReplayVariantKind(StrEnum):
    BASELINE = "BASELINE"
    WITH_TASK_FORCE = "WITH_TASK_FORCE"


def _variant_config(
    config: BacktestConfig,
    *,
    campaign_id: str,
    comparison_fingerprint: str,
    kind: TaskForceReplayVariantKind,
    target_opportunity_id: str,
) -> BacktestConfig:
    assumptions = dict(config.execution_assumptions)
    collisions = sorted(_RESERVED_EXECUTION_KEYS.intersection(assumptions))
    if collisions:
        raise ValueError(
            "BacktestConfig.execution_assumptions already uses reserved Task Force replay keys: "
            + ", ".join(collisions)
        )
    assumptions.update(
        {
            "task_force_replay_campaign_id": campaign_id,
            "task_force_replay_comparison_fingerprint": comparison_fingerprint,
            "task_force_replay_variant": kind.value,
            "task_force_replay_target_opportunity_id": target_opportunity_id,
            "task_force_replay_enabled": str(kind is TaskForceReplayVariantKind.WITH_TASK_FORCE),
        }
    )
    return replace(config, execution_assumptions=assumptions)


@dataclass(frozen=True, slots=True)
class TaskForceReplayVariant:
    campaign_id: str
    variant_id: str
    kind: TaskForceReplayVariantKind
    target_opportunity_id: str
    comparison_fingerprint: str
    run: BacktestRun

    def __post_init__(self) -> None:
        for field_name in ("campaign_id", "variant_id", "target_opportunity_id"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be blank")
        _validate_sha256(self.comparison_fingerprint)

    @property
    def task_force_enabled(self) -> bool:
        return self.kind is TaskForceReplayVariantKind.WITH_TASK_FORCE


@dataclass(frozen=True, slots=True)
class TaskForceReplayPlan:
    campaign_id: str
    comparison_fingerprint: str
    source_run_id: str
    target_opportunity_id: str
    variants: tuple[TaskForceReplayVariant, TaskForceReplayVariant]

    def __post_init__(self) -> None:
        if not self.campaign_id.strip():
            raise ValueError("campaign_id must not be blank")
        _validate_sha256(self.comparison_fingerprint)
        if not self.source_run_id.strip():
            raise ValueError("source_run_id must not be blank")
        if not self.target_opportunity_id.strip():
            raise ValueError("target_opportunity_id must not be blank")
        if len(self.variants) != 2:
            raise ValueError("Task Force replay requires exactly two variants")
        if tuple(item.kind for item in self.variants) != (
            TaskForceReplayVariantKind.BASELINE,
            TaskForceReplayVariantKind.WITH_TASK_FORCE,
        ):
            raise ValueError("Task Force replay variants must be BASELINE then WITH_TASK_FORCE")
        if len({item.variant_id for item in self.variants}) != 2:
            raise ValueError("Task Force replay variant ids must be unique")
        if len({item.run.run_id for item in self.variants}) != 2:
            raise ValueError("Task Force replay run ids must be unique")
        for variant in self.variants:
            if variant.campaign_id != self.campaign_id:
                raise ValueError("all variants must belong to the campaign")
            if variant.comparison_fingerprint != self.comparison_fingerprint:
                raise ValueError("all variants must share comparison_fingerprint")
            if variant.target_opportunity_id != self.target_opportunity_id:
                raise ValueError("all variants must target the same opportunity")

    @property
    def baseline(self) -> TaskForceReplayVariant:
        return self.variants[0]

    @property
    def treatment(self) -> TaskForceReplayVariant:
        return self.variants[1]


def build_task_force_replay_plan(
    source_run: BacktestRun,
    *,
    target_opportunity_id: str,
) -> TaskForceReplayPlan:
    target = target_opportunity_id.strip()
    if not target:
        raise ValueError("target_opportunity_id must not be blank")
    collisions = sorted(
        _RESERVED_EXECUTION_KEYS.intersection(source_run.config.execution_assumptions)
    )
    if collisions:
        raise ValueError(
            "source run already contains reserved Task Force replay assumptions: "
            + ", ".join(collisions)
        )

    payload = {
        "schema": "money-heist.task-force-replay-plan.v1",
        "source_run_id": source_run.run_id,
        "dataset": source_run.dataset.canonical_payload(),
        "config": source_run.config.canonical_payload(),
        "period_start": source_run.period_start,
        "period_end": source_run.period_end,
        "target_opportunity_id": target,
    }
    campaign_id = stable_uuid("task-force-replay-campaign", payload)
    comparison_fingerprint = stable_digest(
        {
            "schema": "money-heist.task-force-replay-comparison.v1",
            "campaign_id": campaign_id,
            "payload": payload,
        }
    )

    variants: list[TaskForceReplayVariant] = []
    for kind in (
        TaskForceReplayVariantKind.BASELINE,
        TaskForceReplayVariantKind.WITH_TASK_FORCE,
    ):
        config = _variant_config(
            source_run.config,
            campaign_id=campaign_id,
            comparison_fingerprint=comparison_fingerprint,
            kind=kind,
            target_opportunity_id=target,
        )
        run = BacktestRun.create(
            dataset=source_run.dataset,
            config=config,
            period_start=source_run.period_start,
            period_end=source_run.period_end,
        )
        variant_id = stable_uuid(
            "task-force-replay-variant",
            {
                "campaign_id": campaign_id,
                "kind": kind,
                "target_opportunity_id": target,
                "run_id": run.run_id,
            },
        )
        variants.append(
            TaskForceReplayVariant(
                campaign_id=campaign_id,
                variant_id=variant_id,
                kind=kind,
                target_opportunity_id=target,
                comparison_fingerprint=comparison_fingerprint,
                run=run,
            )
        )

    return TaskForceReplayPlan(
        campaign_id=campaign_id,
        comparison_fingerprint=comparison_fingerprint,
        source_run_id=source_run.run_id,
        target_opportunity_id=target,
        variants=(variants[0], variants[1]),
    )


class HistoricalReplayRunnerPort(Protocol):
    async def run(
        self,
        *,
        candles: Sequence[Any],
        run: BacktestRun,
        cancel_check: Callable[[], bool] | None = None,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class TaskForceReplayRuntime:
    """Isolated PAPER replay runtime for one baseline/treatment variant."""

    runner: HistoricalReplayRunnerPort
    broker: Any
    ai_usage_records: Callable[[], Sequence[Any]]
    paper_events: Callable[[], Sequence[Any]]
    task_force_reports: Callable[[], Sequence[TaskForceReport]]
    task_force_executions: Callable[[], Sequence[TaskForceMultiMemberExecution]]
    execution_mode: str = "PAPER"
    live_authority: bool = False

    def __post_init__(self) -> None:
        if self.execution_mode != "PAPER":
            raise ValueError("Task Force historical replay is PAPER-only")
        if self.live_authority:
            raise ValueError("Task Force historical replay cannot hold LIVE authority")
        for field_name in (
            "ai_usage_records",
            "paper_events",
            "task_force_reports",
            "task_force_executions",
        ):
            if not callable(getattr(self, field_name)):
                raise TypeError(f"{field_name} must be callable")


class TaskForceReplayRuntimeFactory(Protocol):
    def __call__(self, *, variant: TaskForceReplayVariant) -> TaskForceReplayRuntime: ...


@dataclass(frozen=True, slots=True)
class TaskForceReplayVariantExecution:
    variant: TaskForceReplayVariant
    period_report: BacktestPeriodReport
    replay_result: Any
    evaluation_bundle: Any
    task_force_report: TaskForceReport | None
    task_force_execution: TaskForceMultiMemberExecution | None

    def __post_init__(self) -> None:
        if self.period_report.run_id != self.variant.run.run_id:
            raise ValueError("period_report run_id does not match replay variant")
        if self.period_report.dataset_id != self.variant.run.dataset.dataset_id:
            raise ValueError("period_report dataset_id does not match replay variant")
        if self.period_report.period_start != self.variant.run.period_start:
            raise ValueError("period_report period_start does not match replay variant")
        if self.period_report.period_end != self.variant.run.period_end:
            raise ValueError("period_report period_end does not match replay variant")
        if self.variant.kind is TaskForceReplayVariantKind.BASELINE:
            if self.task_force_report is not None or self.task_force_execution is not None:
                raise ValueError("baseline replay cannot contain Task Force artifacts")
        else:
            if self.task_force_report is None or self.task_force_execution is None:
                raise ValueError("treatment replay requires Task Force report and execution")


@dataclass(frozen=True, slots=True)
class TaskForceReplayCampaignReport:
    campaign_id: str
    comparison_fingerprint: str
    target_opportunity_id: str
    role: BacktestPeriodRole
    baseline: TaskForceReplayVariantExecution
    treatment: TaskForceReplayVariantExecution
    comparison: TaskForceOutcomeComparison
    task_force_evaluation: TaskForceEvaluationReport
    replay_fingerprint_sha256: str
    paper_only: bool = True
    advisory_only: bool = True
    automatic_state_change: bool = False
    trade_proposal_authority: bool = False
    registry_mutation: bool = False
    risk_authority: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        _validate_sha256(self.comparison_fingerprint)
        _validate_sha256(self.replay_fingerprint_sha256)
        if not self.paper_only or not self.advisory_only:
            raise ValueError("Task Force replay report must remain PAPER/advisory-only")
        if any(
            (
                self.automatic_state_change,
                self.trade_proposal_authority,
                self.registry_mutation,
                self.risk_authority,
                self.live_authority,
            )
        ):
            raise ValueError("Task Force replay report cannot hold operational authority")


class TaskForceReplayExecutor:
    """Execute isolated baseline/treatment twins and evaluate one Task Force intervention."""

    def __init__(
        self,
        runtime_factory: TaskForceReplayRuntimeFactory,
        *,
        evaluation_fn: Callable[..., Any] | None = None,
    ) -> None:
        self._runtime_factory = runtime_factory
        self._evaluation_fn = evaluation_fn

    async def execute(
        self,
        plan: TaskForceReplayPlan,
        *,
        candles: Sequence[Any],
        role: BacktestPeriodRole,
        cancel_check: Callable[[], bool] | None = None,
    ) -> TaskForceReplayCampaignReport:
        if not candles:
            raise ValueError("Task Force replay requires candles")

        evaluation_fn = self._evaluation_fn
        if evaluation_fn is None:
            from app.services.backtest.evaluation import evaluate_historical_replay

            evaluation_fn = evaluate_historical_replay

        executions: list[TaskForceReplayVariantExecution] = []
        used_runners: list[Any] = []
        used_brokers: list[Any] = []

        for variant in plan.variants:
            runtime = self._runtime_factory(variant=variant)
            if any(runtime.runner is item for item in used_runners):
                raise ValueError("runtime_factory reused a replay runner across variants")
            if any(runtime.broker is item for item in used_brokers):
                raise ValueError("runtime_factory reused a PAPER broker across variants")
            used_runners.append(runtime.runner)
            used_brokers.append(runtime.broker)

            replay = await runtime.runner.run(
                candles=candles,
                run=variant.run,
                cancel_check=cancel_check,
            )
            result = getattr(replay, "backtest_result", None)
            replay_run = getattr(result, "run", None)
            if replay_run is None or getattr(replay_run, "run_id", None) != variant.run.run_id:
                raise ValueError("historical replay returned the wrong Task Force variant run")

            evaluation = await evaluation_fn(
                replay,
                broker=runtime.broker,
                ai_usage_records=tuple(runtime.ai_usage_records()),
                paper_events=tuple(runtime.paper_events()),
            )
            period_report = BacktestPeriodReport.from_evaluation(role, replay, evaluation)
            reports = tuple(runtime.task_force_reports())
            task_force_executions = tuple(runtime.task_force_executions())
            report, tf_execution = _select_task_force_artifacts(
                variant,
                reports=reports,
                executions=task_force_executions,
            )
            executions.append(
                TaskForceReplayVariantExecution(
                    variant=variant,
                    period_report=period_report,
                    replay_result=replay,
                    evaluation_bundle=evaluation,
                    task_force_report=report,
                    task_force_execution=tf_execution,
                )
            )

        baseline, treatment = executions
        _validate_twin_reports(baseline.period_report, treatment.period_report)
        report = treatment.task_force_report
        tf_execution = treatment.task_force_execution
        assert report is not None and tf_execution is not None

        baseline_outcome = _run_outcome(
            baseline,
            comparison_fingerprint=plan.comparison_fingerprint,
            task_force_report=None,
        )
        treatment_outcome = _run_outcome(
            treatment,
            comparison_fingerprint=plan.comparison_fingerprint,
            task_force_report=report,
        )
        comparison = compare_task_force_outcomes(
            baseline_outcome,
            treatment_outcome,
            report=report,
        )
        task_force_evaluation = evaluate_task_force(
            report,
            tf_execution,
            comparison=comparison,
        )
        fingerprint = stable_digest(
            {
                "schema": "money-heist.task-force-replay-execution.v1",
                "campaign_id": plan.campaign_id,
                "comparison_fingerprint": plan.comparison_fingerprint,
                "target_opportunity_id": plan.target_opportunity_id,
                "role": role,
                "baseline_variant_id": baseline.variant.variant_id,
                "baseline_report": baseline.period_report,
                "treatment_variant_id": treatment.variant.variant_id,
                "treatment_report": treatment.period_report,
                "task_force_report_fingerprint": report.report_fingerprint_sha256,
                "task_force_evaluation_fingerprint": (
                    task_force_evaluation.evaluation_fingerprint_sha256
                ),
            }
        )
        return TaskForceReplayCampaignReport(
            campaign_id=plan.campaign_id,
            comparison_fingerprint=plan.comparison_fingerprint,
            target_opportunity_id=plan.target_opportunity_id,
            role=role,
            baseline=baseline,
            treatment=treatment,
            comparison=comparison,
            task_force_evaluation=task_force_evaluation,
            replay_fingerprint_sha256=fingerprint,
        )


def _select_task_force_artifacts(
    variant: TaskForceReplayVariant,
    *,
    reports: tuple[TaskForceReport, ...],
    executions: tuple[TaskForceMultiMemberExecution, ...],
) -> tuple[TaskForceReport | None, TaskForceMultiMemberExecution | None]:
    if variant.kind is TaskForceReplayVariantKind.BASELINE:
        if reports or executions:
            raise ValueError("baseline replay must not produce Task Force artifacts")
        return None, None
    if len(reports) != 1 or len(executions) != 1:
        raise ValueError("treatment replay must produce exactly one Task Force report/execution")
    report = reports[0]
    execution = executions[0]
    if report.opportunity_id != variant.target_opportunity_id:
        raise ValueError("treatment Task Force report targets the wrong opportunity")
    if report.system_id != variant.run.config.system_id:
        raise ValueError("treatment Task Force report targets the wrong system")
    if not (variant.run.period_start <= execution.started_at <= variant.run.period_end):
        raise ValueError("treatment Task Force execution lies outside replay period")
    if not (variant.run.period_start <= report.aggregated_at <= variant.run.period_end):
        raise ValueError("treatment Task Force report lies outside replay period")
    if task_force_report_fingerprint(report) != report.report_fingerprint_sha256:
        raise ValueError("treatment Task Force report fingerprint is stale")
    return report, execution


def _validate_twin_reports(
    baseline: BacktestPeriodReport,
    treatment: BacktestPeriodReport,
) -> None:
    comparable = (
        ("dataset_id", baseline.dataset_id, treatment.dataset_id),
        ("role", baseline.role, treatment.role),
        ("period_start", baseline.period_start, treatment.period_start),
        ("period_end", baseline.period_end, treatment.period_end),
        ("processed_candles", baseline.processed_candles, treatment.processed_candles),
        ("opportunity_count", baseline.opportunity_count, treatment.opportunity_count),
    )
    for field_name, left, right in comparable:
        if left != right:
            raise ValueError(f"Task Force replay twins differ on {field_name}")


def _run_outcome(
    execution: TaskForceReplayVariantExecution,
    *,
    comparison_fingerprint: str,
    task_force_report: TaskForceReport | None,
) -> TaskForceRunOutcome:
    period = execution.period_report
    return TaskForceRunOutcome(
        run_id=period.run_id,
        comparison_fingerprint=comparison_fingerprint,
        dataset_id=period.dataset_id,
        role=period.role.value,
        period_start=period.period_start,
        period_end=period.period_end,
        opportunity_count=period.opportunity_count,
        trading_net=_metric(period.trading_net, unavailable_reason="TRADING_NET_UNAVAILABLE"),
        economic_net=_metric(period.economic_net, unavailable_reason="ECONOMIC_NET_UNAVAILABLE"),
        max_drawdown_pct=_metric(
            period.max_drawdown_pct,
            unavailable_reason="MAX_DRAWDOWN_UNAVAILABLE",
        ),
        includes_task_force=task_force_report is not None,
        task_force_report_fingerprint_sha256=(
            task_force_report.report_fingerprint_sha256
            if task_force_report is not None
            else None
        ),
        is_out_of_sample=period.is_out_of_sample,
    )


def _metric(snapshot: BacktestMetricSnapshot, *, unavailable_reason: str) -> Metric:
    if snapshot.status == "AVAILABLE" and snapshot.value is not None:
        return Metric.available(snapshot.value)
    return Metric.unavailable(snapshot.reason or unavailable_reason)


def _validate_sha256(value: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise ValueError("fingerprint must be lowercase hexadecimal SHA-256")
    return normalized


__all__ = [
    "HistoricalReplayRunnerPort",
    "TaskForceReplayCampaignReport",
    "TaskForceReplayExecutor",
    "TaskForceReplayPlan",
    "TaskForceReplayRuntime",
    "TaskForceReplayRuntimeFactory",
    "TaskForceReplayVariant",
    "TaskForceReplayVariantExecution",
    "TaskForceReplayVariantKind",
    "build_task_force_replay_plan",
]
