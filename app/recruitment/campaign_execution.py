from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol, TypeVar

from app.services.backtest.evaluation import evaluate_historical_replay
from app.services.backtest.ids import stable_digest
from app.services.backtest.reports import BacktestPeriodReport
from app.services.backtest.splits import BacktestPeriodRole

from .campaign import (
    RecruitmentCampaignPlan,
    RecruitmentCampaignVariant,
    RecruitmentCampaignVariantKind,
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
class RecruitmentVariantRuntime:
    """Fresh Batch 16/PAPER runtime dedicated to one recruitment twin."""

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
    ) -> RecruitmentVariantRuntime:
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


class RecruitmentVariantRuntimeFactory(Protocol[T]):
    def __call__(
        self,
        *,
        variant: RecruitmentCampaignVariant,
        specialists: Mapping[str, T],
    ) -> RecruitmentVariantRuntime: ...


def _normalize_specialists(specialists: Mapping[str, T]) -> dict[str, T]:
    normalized: dict[str, T] = {}
    for raw_agent_id, specialist in specialists.items():
        agent_id = str(raw_agent_id).strip().lower()
        if not agent_id:
            raise ValueError("specialist mapping must not contain blank agent ids")
        if agent_id in normalized:
            raise ValueError("specialist mapping contains duplicate normalized agent ids")
        normalized[agent_id] = specialist
    return normalized


def build_recruitment_variant_specialists(
    variant: RecruitmentCampaignVariant,
    incumbent_specialists: Mapping[str, T],
    *,
    candidate_specialist: T,
) -> Mapping[str, T]:
    """Build the exact specialist roster for one twin without mutating incumbents.

    The baseline twin receives only the incumbent crew. WITH_CANDIDATE receives
    the same incumbents plus the evaluation-only candidate runtime identity.
    """

    normalized = _normalize_specialists(incumbent_specialists)
    actual = set(normalized)
    expected = set(variant.baseline_agents)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected))
        raise ValueError(
            "incumbent specialist mapping does not match recruitment baseline: "
            + "; ".join(details)
        )
    if variant.candidate_agent_id in normalized:
        raise ValueError("candidate runtime id must not already exist in incumbent specialists")
    if candidate_specialist is None:
        raise ValueError("candidate_specialist must not be None")

    selected = dict(normalized)
    if variant.kind is RecruitmentCampaignVariantKind.WITH_CANDIDATE:
        selected[variant.candidate_agent_id] = candidate_specialist
    elif variant.kind is not RecruitmentCampaignVariantKind.BASELINE:
        raise ValueError(f"unsupported recruitment variant kind: {variant.kind}")

    if set(selected) != set(variant.included_agents):
        raise ValueError("constructed specialist roster does not match campaign variant")
    return MappingProxyType(dict(sorted(selected.items())))


@dataclass(frozen=True, slots=True)
class RecruitmentVariantExecution:
    variant: RecruitmentCampaignVariant
    period_report: BacktestPeriodReport
    replay_result: Any
    evaluation_bundle: Any

    def __post_init__(self) -> None:
        if self.period_report.run_id != self.variant.run.run_id:
            raise ValueError("period_report run_id does not match recruitment variant")
        if self.period_report.dataset_id != self.variant.run.dataset.dataset_id:
            raise ValueError("period_report dataset_id does not match recruitment variant")
        if self.period_report.period_start != self.variant.run.period_start:
            raise ValueError("period_report period_start does not match recruitment variant")
        if self.period_report.period_end != self.variant.run.period_end:
            raise ValueError("period_report period_end does not match recruitment variant")
        if self.period_report.role is not self.variant.role:
            raise ValueError("period_report role does not match recruitment variant")

    @property
    def run_id(self) -> str:
        return self.variant.run.run_id


@dataclass(frozen=True, slots=True)
class RecruitmentCampaignExecutionReport:
    campaign_id: str
    comparison_fingerprint: str
    recruitment_id: str
    role: BacktestPeriodRole
    executions: tuple[RecruitmentVariantExecution, ...]
    execution_fingerprint: str
    auto_apply: bool = False
    registry_mutation: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "campaign_id",
            "comparison_fingerprint",
            "recruitment_id",
            "execution_fingerprint",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be blank")
        if self.auto_apply or self.registry_mutation or self.live_authority:
            raise ValueError("recruitment execution reports cannot mutate registry or go LIVE")
        if len(self.executions) != 2:
            raise ValueError("recruitment campaign execution requires exactly two twins")
        kinds = {item.variant.kind for item in self.executions}
        if kinds != {
            RecruitmentCampaignVariantKind.BASELINE,
            RecruitmentCampaignVariantKind.WITH_CANDIDATE,
        }:
            raise ValueError("execution requires BASELINE and WITH_CANDIDATE twins")
        if len({item.run_id for item in self.executions}) != 2:
            raise ValueError("recruitment execution run ids must be unique")
        if any(item.variant.campaign_id != self.campaign_id for item in self.executions):
            raise ValueError("all executions must belong to campaign_id")
        if any(
            item.variant.comparison_fingerprint != self.comparison_fingerprint
            for item in self.executions
        ):
            raise ValueError("all executions must share comparison_fingerprint")
        if any(item.period_report.role is not self.role for item in self.executions):
            raise ValueError("all period reports must match execution role")

    @property
    def baseline(self) -> RecruitmentVariantExecution:
        return next(
            item
            for item in self.executions
            if item.variant.kind is RecruitmentCampaignVariantKind.BASELINE
        )

    @property
    def with_candidate(self) -> RecruitmentVariantExecution:
        return next(
            item
            for item in self.executions
            if item.variant.kind is RecruitmentCampaignVariantKind.WITH_CANDIDATE
        )


def _execution_fingerprint(
    *,
    plan: RecruitmentCampaignPlan,
    executions: tuple[RecruitmentVariantExecution, ...],
) -> str:
    return stable_digest(
        {
            "schema": "money-heist.recruitment-campaign-execution.v1",
            "campaign_id": plan.campaign_id,
            "comparison_fingerprint": plan.comparison_fingerprint,
            "recruitment_id": plan.recruitment_id,
            "role": plan.role,
            "success_criteria_fingerprint": plan.success_criteria_fingerprint,
            "variant_reports": [
                {
                    "variant_id": item.variant.variant_id,
                    "kind": item.variant.kind,
                    "included_agents": item.variant.included_agents,
                    "period_report": item.period_report,
                }
                for item in executions
            ],
        }
    )


class RecruitmentCampaignExecutor:
    """Execute one planned candidate-vs-baseline campaign through Batch 16/PAPER.

    The runtime factory is intentionally injected and must create a fresh runner,
    broker, portfolio/journal and usage recorder per twin. The executor does not
    compare success criteria and does not emit any promotion decision; those are
    later evidence/advisory steps.
    """

    def __init__(
        self,
        runtime_factory: RecruitmentVariantRuntimeFactory[T],
        *,
        evaluation_fn: Callable[..., Any] = evaluate_historical_replay,
    ) -> None:
        self._runtime_factory = runtime_factory
        self._evaluation_fn = evaluation_fn

    async def execute(
        self,
        plan: RecruitmentCampaignPlan,
        *,
        candles: Sequence[Any],
        incumbent_specialists: Mapping[str, T],
        candidate_specialist: T,
        cancel_check: Callable[[], bool] | None = None,
    ) -> RecruitmentCampaignExecutionReport:
        if not candles:
            raise ValueError("recruitment campaign requires candles")

        executions: list[RecruitmentVariantExecution] = []
        used_runners: list[Any] = []
        used_brokers: list[Any] = []

        for variant in plan.variants:
            selected = build_recruitment_variant_specialists(
                variant,
                incumbent_specialists,
                candidate_specialist=candidate_specialist,
            )
            runtime = self._runtime_factory(variant=variant, specialists=selected)
            if any(runtime.runner is used for used in used_runners):
                raise ValueError("runtime_factory reused a replay runner across recruitment twins")
            if any(runtime.broker is used for used in used_brokers):
                raise ValueError("runtime_factory reused a PAPER broker across recruitment twins")
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
                raise ValueError("historical replay returned the wrong recruitment run")

            evaluation = await self._evaluation_fn(
                replay,
                broker=runtime.broker,
                ai_usage_records=tuple(runtime.ai_usage_records()),
                paper_events=tuple(runtime.paper_events()),
            )
            report = BacktestPeriodReport.from_evaluation(plan.role, replay, evaluation)
            executions.append(
                RecruitmentVariantExecution(
                    variant=variant,
                    period_report=report,
                    replay_result=replay,
                    evaluation_bundle=evaluation,
                )
            )

        ordered = tuple(executions)
        fingerprint = _execution_fingerprint(plan=plan, executions=ordered)
        return RecruitmentCampaignExecutionReport(
            campaign_id=plan.campaign_id,
            comparison_fingerprint=plan.comparison_fingerprint,
            recruitment_id=plan.recruitment_id,
            role=plan.role,
            executions=ordered,
            execution_fingerprint=fingerprint,
        )


__all__ = [
    "HistoricalReplayRunnerPort",
    "RecruitmentCampaignExecutionReport",
    "RecruitmentCampaignExecutor",
    "RecruitmentVariantExecution",
    "RecruitmentVariantRuntime",
    "RecruitmentVariantRuntimeFactory",
    "build_recruitment_variant_specialists",
]
