from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from app.services.backtest.evaluation import evaluate_historical_replay
from app.services.backtest.ids import stable_digest
from app.services.backtest.reports import BacktestPeriodReport
from app.services.backtest.splits import BacktestPeriodRole

from .ablation import AblationComparison, compare_ablation
from .ablation_campaign import (
    AblationCampaignPlan,
    AblationCampaignVariant,
    AblationCampaignVariantKind,
    build_variant_specialists,
)

T = TypeVar("T")


class HistoricalReplayRunnerPort(Protocol):
    async def run(
        self,
        *,
        candles: Sequence[Any],
        run: Any,
        cancel_check: Callable[[], bool] | None = None,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class AblationVariantRuntime:
    """Isolated Batch 16/PAPER runtime for one campaign variant."""

    runner: HistoricalReplayRunnerPort
    broker: Any
    ai_usage_records: Callable[[], Sequence[Any]]
    paper_events: Callable[[], Sequence[Any]]

    def __post_init__(self) -> None:
        if not callable(self.ai_usage_records):
            raise TypeError("ai_usage_records must be callable")
        if not callable(self.paper_events):
            raise TypeError("paper_events must be callable")

    @classmethod
    def from_components(
        cls,
        *,
        runner: HistoricalReplayRunnerPort,
        broker: Any,
        usage_recorder: Any | None = None,
        journal: Any | None = None,
    ) -> AblationVariantRuntime:
        def usage() -> Sequence[Any]:
            if usage_recorder is None:
                return ()
            return tuple(getattr(usage_recorder, "records", ()))

        def events() -> Sequence[Any]:
            if journal is None:
                return ()
            method = getattr(journal, "events", None)
            if method is None or not callable(method):
                raise TypeError("journal must expose callable events()")
            return tuple(method())

        return cls(
            runner=runner,
            broker=broker,
            ai_usage_records=usage,
            paper_events=events,
        )


class AblationVariantRuntimeFactory(Protocol[T]):
    def __call__(
        self,
        *,
        variant: AblationCampaignVariant,
        specialists: Mapping[str, T],
    ) -> AblationVariantRuntime: ...


@dataclass(frozen=True, slots=True)
class AblationVariantExecution:
    variant: AblationCampaignVariant
    period_report: BacktestPeriodReport
    replay_result: Any
    evaluation_bundle: Any

    def __post_init__(self) -> None:
        if self.period_report.run_id != self.variant.run.run_id:
            raise ValueError("period_report run_id does not match campaign variant")
        if self.period_report.dataset_id != self.variant.run.dataset.dataset_id:
            raise ValueError("period_report dataset_id does not match campaign variant")
        if self.period_report.period_start != self.variant.run.period_start:
            raise ValueError("period_report period_start does not match campaign variant")
        if self.period_report.period_end != self.variant.run.period_end:
            raise ValueError("period_report period_end does not match campaign variant")

    @property
    def run_id(self) -> str:
        return self.variant.run.run_id

    @property
    def included_agents(self) -> tuple[str, ...]:
        return self.variant.included_agents


@dataclass(frozen=True, slots=True)
class AblationCampaignExecutionReport:
    campaign_id: str
    comparison_fingerprint: str
    role: BacktestPeriodRole
    executions: tuple[AblationVariantExecution, ...]
    comparisons: tuple[AblationComparison, ...]
    execution_fingerprint: str

    def __post_init__(self) -> None:
        if not self.campaign_id.strip():
            raise ValueError("campaign_id must not be blank")
        if not self.comparison_fingerprint.strip():
            raise ValueError("comparison_fingerprint must not be blank")
        if not self.execution_fingerprint.strip():
            raise ValueError("execution_fingerprint must not be blank")
        if not self.executions:
            raise ValueError("campaign execution requires at least one execution")
        if len({item.run_id for item in self.executions}) != len(self.executions):
            raise ValueError("campaign execution run ids must be unique")
        baseline_count = sum(
            item.variant.kind is AblationCampaignVariantKind.BASELINE
            for item in self.executions
        )
        if baseline_count != 1:
            raise ValueError("campaign execution requires exactly one baseline")
        if any(item.period_report.role is not self.role for item in self.executions):
            raise ValueError("all campaign period reports must match execution role")
        if any(
            item.variant.campaign_id != self.campaign_id for item in self.executions
        ):
            raise ValueError("all executions must belong to campaign_id")
        if len(self.comparisons) != len(self.executions) - 1:
            raise ValueError("campaign execution requires one comparison per ablation")
        if len({item.agent_id for item in self.comparisons}) != len(self.comparisons):
            raise ValueError("campaign comparison agent ids must be unique")
        if any(
            item.comparison_fingerprint != self.comparison_fingerprint
            for item in self.comparisons
        ):
            raise ValueError("all comparisons must share comparison_fingerprint")

    @property
    def baseline(self) -> AblationVariantExecution:
        return next(
            item
            for item in self.executions
            if item.variant.kind is AblationCampaignVariantKind.BASELINE
        )

    def without_agent(self, agent_id: str) -> AblationVariantExecution:
        normalized = agent_id.strip().lower()
        for item in self.executions:
            if item.variant.excluded_agent_id == normalized:
                return item
        raise KeyError(f"agent is not an executed ablation target: {agent_id}")

    def comparison_for(self, agent_id: str) -> AblationComparison:
        normalized = agent_id.strip().lower()
        for comparison in self.comparisons:
            if comparison.agent_id == normalized:
                return comparison
        raise KeyError(f"agent has no ablation comparison: {agent_id}")


def _execution_fingerprint(
    *,
    plan: AblationCampaignPlan,
    role: BacktestPeriodRole,
    executions: tuple[AblationVariantExecution, ...],
    comparisons: tuple[AblationComparison, ...],
) -> str:
    return stable_digest(
        {
            "schema": "money-heist.ablation-campaign-execution.v1",
            "campaign_id": plan.campaign_id,
            "comparison_fingerprint": plan.comparison_fingerprint,
            "role": role,
            "variant_reports": [
                {
                    "variant_id": item.variant.variant_id,
                    "kind": item.variant.kind,
                    "excluded_agent_id": item.variant.excluded_agent_id,
                    "included_agents": item.variant.included_agents,
                    "report": item.period_report,
                }
                for item in executions
            ],
            "comparisons": comparisons,
        }
    )


class AblationCampaignExecutor:
    """Execute a planned ablation campaign through isolated Batch 16 runtimes.

    Runtime construction stays injected because each variant must receive a fresh PAPER broker,
    portfolio, journal, AI budget/usage recorder and HistoricalReplayRunner. The executor owns the
    deterministic campaign order, replay invocation, Batch 16 evaluation and Batch 18a comparison.
    """

    def __init__(
        self,
        runtime_factory: AblationVariantRuntimeFactory[T],
        *,
        evaluation_fn: Callable[..., Any] = evaluate_historical_replay,
    ) -> None:
        self._runtime_factory = runtime_factory
        self._evaluation_fn = evaluation_fn

    async def execute(
        self,
        plan: AblationCampaignPlan,
        *,
        candles: Sequence[Any],
        role: BacktestPeriodRole,
        specialists: Mapping[str, T],
        cancel_check: Callable[[], bool] | None = None,
    ) -> AblationCampaignExecutionReport:
        if not candles:
            raise ValueError("ablation campaign requires candles")

        executions: list[AblationVariantExecution] = []
        used_runners: list[Any] = []
        used_brokers: list[Any] = []

        for variant in plan.variants:
            selected = build_variant_specialists(variant, specialists)
            runtime = self._runtime_factory(
                variant=variant,
                specialists=selected,
            )
            if any(runtime.runner is used for used in used_runners):
                raise ValueError("runtime_factory reused a replay runner across variants")
            if any(runtime.broker is used for used in used_brokers):
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
                raise ValueError("historical replay returned the wrong campaign run")

            evaluation = await self._evaluation_fn(
                replay,
                broker=runtime.broker,
                ai_usage_records=tuple(runtime.ai_usage_records()),
                paper_events=tuple(runtime.paper_events()),
            )
            report = BacktestPeriodReport.from_evaluation(role, replay, evaluation)
            executions.append(
                AblationVariantExecution(
                    variant=variant,
                    period_report=report,
                    replay_result=replay,
                    evaluation_bundle=evaluation,
                )
            )

        ordered = tuple(executions)
        baseline_execution = next(
            item
            for item in ordered
            if item.variant.kind is AblationCampaignVariantKind.BASELINE
        )
        baseline_descriptor = baseline_execution.variant.to_descriptor(
            baseline_execution.period_report
        )
        comparisons = tuple(
            compare_ablation(
                baseline_descriptor,
                execution.variant.to_descriptor(execution.period_report),
                agent_id=execution.variant.excluded_agent_id or "",
            )
            for execution in ordered
            if execution.variant.kind is AblationCampaignVariantKind.WITHOUT_AGENT
        )
        fingerprint = _execution_fingerprint(
            plan=plan,
            role=role,
            executions=ordered,
            comparisons=comparisons,
        )
        return AblationCampaignExecutionReport(
            campaign_id=plan.campaign_id,
            comparison_fingerprint=plan.comparison_fingerprint,
            role=role,
            executions=ordered,
            comparisons=comparisons,
            execution_fingerprint=fingerprint,
        )


__all__ = [
    "AblationCampaignExecutionReport",
    "AblationCampaignExecutor",
    "AblationVariantExecution",
    "AblationVariantRuntime",
    "AblationVariantRuntimeFactory",
    "HistoricalReplayRunnerPort",
]
