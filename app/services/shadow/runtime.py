from __future__ import annotations

import inspect
from dataclasses import dataclass, is_dataclass, replace
from datetime import datetime
from typing import Any

from .evaluation import Batch10EvaluationInput, Batch10EvaluationPort, ShadowComparisonEngine
from .ids import branch_idempotency_key, derived_opportunity_id, root_correlation_id
from .identities import ShadowSystemIdentity
from .models import (
    ShadowBranchContext,
    ShadowBranchStatus,
    ShadowEvaluationResult,
    ShadowEvaluationStatus,
    ShadowFleetResult,
    ShadowMetricSnapshot,
    ShadowSystemFailure,
    ShadowSystemResult,
    SystemScopedAIUsage,
)
from .providers import ImmutableMarketConstraintsProvider, ShadowAIUsageLedger


class ShadowIsolationError(ValueError):
    pass


@dataclass(slots=True)
class ShadowSystemRuntime:
    identity: ShadowSystemIdentity
    paper_pipeline: Any
    paper_broker: Any
    journal: Any
    orchestration: Any
    portfolio_provider: Any
    risk_profile_provider: Any
    kill_switch_provider: Any
    market_constraints_provider: Any
    ai_usage_ledger: ShadowAIUsageLedger

    def __post_init__(self) -> None:
        if self.ai_usage_ledger.system_id != self.identity.system_id:
            raise ShadowIsolationError("AI usage ledger system_id does not match identity")
        broker_config = getattr(self.paper_broker, "config", None)
        if broker_config is not None:
            broker_system_id = getattr(broker_config, "system_id", None)
            if broker_system_id != self.identity.system_id:
                raise ShadowIsolationError("PAPER broker system_id does not match identity")
        pipeline_broker = getattr(self.paper_pipeline, "paper_broker", self.paper_broker)
        if pipeline_broker is not self.paper_broker:
            raise ShadowIsolationError("runtime PAPER broker differs from pipeline PAPER broker")
        pipeline_orchestration = getattr(
            self.paper_pipeline, "orchestration", self.orchestration
        )
        if pipeline_orchestration is not self.orchestration:
            raise ShadowIsolationError("runtime orchestration differs from pipeline orchestration")
        pipeline_market = getattr(
            self.paper_pipeline, "market_constraints_provider", self.market_constraints_provider
        )
        if pipeline_market is not self.market_constraints_provider:
            raise ShadowIsolationError(
                "runtime market constraints provider differs from pipeline provider"
            )

    def update_portfolio_state(self, state: Any) -> None:
        replace_state = getattr(self.portfolio_provider, "replace", None)
        if replace_state is None:
            raise ShadowIsolationError("portfolio provider is not explicitly mutable")
        replace_state(state)

    def capture_ai_usage(self, usage_records) -> None:
        self.ai_usage_ledger.extend(usage_records)


class ShadowFleetRunner:
    """Stable sequential fan-out over isolated PAPER-only SHADOW runtimes."""

    def __init__(
        self,
        runtimes,
        *,
        evaluator: Batch10EvaluationPort | None = None,
        comparison_engine: ShadowComparisonEngine | None = None,
    ) -> None:
        ordered = tuple(sorted(runtimes, key=lambda runtime: runtime.identity.execution_order))
        if not ordered:
            raise ValueError("at least one SHADOW runtime is required")
        self._runtimes = ordered
        self._evaluator = evaluator
        self._comparison_engine = comparison_engine or ShadowComparisonEngine()
        self._paper_history: dict[str, list[Any]] = {
            runtime.identity.system_id: [] for runtime in ordered
        }
        self._validate_isolation()

    @property
    def runtimes(self) -> tuple[ShadowSystemRuntime, ...]:
        return self._runtimes

    async def run(
        self,
        *,
        root_opportunity: Any,
        market_context: Any,
        now: datetime | None = None,
    ) -> ShadowFleetResult:
        root_opportunity_id = str(getattr(root_opportunity, "opportunity_id"))
        root_snapshot_id = str(getattr(root_opportunity, "snapshot_id"))
        market_snapshot_id = str(getattr(market_context, "snapshot_id"))
        if root_snapshot_id != market_snapshot_id:
            raise ValueError("root opportunity snapshot_id does not match market context")

        correlation_id = root_correlation_id(root_opportunity_id, root_snapshot_id)
        results: list[ShadowSystemResult] = []

        for runtime in self._runtimes:
            system_id = runtime.identity.system_id
            branch_opportunity_id = derived_opportunity_id(root_opportunity_id, system_id)
            context = ShadowBranchContext(
                root_correlation_id=correlation_id,
                root_opportunity_id=root_opportunity_id,
                root_snapshot_id=root_snapshot_id,
                system_id=system_id,
                derived_opportunity_id=branch_opportunity_id,
                idempotency_key=branch_idempotency_key(
                    root_opportunity_id=root_opportunity_id,
                    source_snapshot_id=root_snapshot_id,
                    system_id=system_id,
                ),
            )
            opportunity = self._derive_opportunity(
                root_opportunity,
                system_id=system_id,
                opportunity_id=branch_opportunity_id,
            )

            try:
                paper_result = await runtime.paper_pipeline.run(
                    opportunity=opportunity,
                    market_context=market_context,
                    now=now,
                )
                self._paper_history[system_id].append(paper_result)
                paper_status = getattr(getattr(paper_result, "status", None), "value", None)
                if paper_status == "FAILED":
                    failure = getattr(paper_result, "failure", None)
                    code = getattr(getattr(failure, "code", None), "value", None)
                    branch_status = ShadowBranchStatus.FAILED
                    branch_failure = ShadowSystemFailure(
                        stage=getattr(failure, "stage", "paper_pipeline"),
                        error_type=code or "PaperPipelineFailure",
                        message=getattr(failure, "message", "PAPER pipeline failed"),
                    )
                else:
                    branch_status = ShadowBranchStatus.COMPLETED
                    branch_failure = None
            except Exception as exc:
                paper_result = None
                branch_status = ShadowBranchStatus.FAILED
                branch_failure = ShadowSystemFailure(
                    stage="paper_pipeline",
                    error_type=type(exc).__name__,
                    message=str(exc),
                )

            usage, usage_failure = self._scoped_usage(runtime)
            if usage_failure is not None and branch_failure is None:
                branch_failure = usage_failure

            evaluation = ShadowEvaluationResult(
                status=ShadowEvaluationStatus.NOT_REQUESTED
            )
            if self._evaluator is not None and paper_result is not None:
                evaluation_input = Batch10EvaluationInput(
                    system_id=system_id,
                    root_opportunity_id=root_opportunity_id,
                    derived_opportunity_id=branch_opportunity_id,
                    paper_history=tuple(self._paper_history[system_id]),
                    ai_usage_records=tuple(item.usage for item in usage),
                )
                try:
                    evaluation = self._evaluator.evaluate(evaluation_input)
                    if inspect.isawaitable(evaluation):
                        evaluation = await evaluation
                    if not isinstance(evaluation, ShadowEvaluationResult):
                        raise TypeError(
                            "Batch10EvaluationPort.evaluate must return ShadowEvaluationResult"
                        )
                except Exception as exc:
                    evaluation = ShadowEvaluationResult(
                        status=ShadowEvaluationStatus.FAILED,
                        failure=ShadowSystemFailure(
                            stage="evaluation",
                            error_type=type(exc).__name__,
                            message=str(exc),
                        ),
                    )

            results.append(
                ShadowSystemResult(
                    identity=runtime.identity,
                    context=context,
                    status=branch_status,
                    opportunity=opportunity,
                    paper_result=paper_result,
                    ai_usage=usage,
                    evaluation=evaluation,
                    failure=branch_failure,
                )
            )

        metric_snapshots: dict[str, ShadowMetricSnapshot | None] = {}
        for result in results:
            if result.evaluation.status is ShadowEvaluationStatus.COMPLETED:
                metric_snapshots[result.identity.system_id] = result.evaluation.metrics
            else:
                metric_snapshots[result.identity.system_id] = None

        comparison = self._comparison_engine.compare(
            system_order=[runtime.identity.system_id for runtime in self._runtimes],
            snapshots=metric_snapshots,
        )
        return ShadowFleetResult(
            root_correlation_id=correlation_id,
            root_opportunity_id=root_opportunity_id,
            root_snapshot_id=root_snapshot_id,
            systems=tuple(results),
            comparison=comparison,
        )

    def paper_history(self, system_id: str) -> tuple[Any, ...]:
        try:
            return tuple(self._paper_history[system_id])
        except KeyError as exc:
            raise KeyError(f"unknown SHADOW system_id {system_id!r}") from exc

    def _validate_isolation(self) -> None:
        system_ids = [runtime.identity.system_id for runtime in self._runtimes]
        if len(system_ids) != len(set(system_ids)):
            raise ShadowIsolationError("SHADOW system_id values must be unique")

        stateful_boundaries = {
            "paper_broker": [runtime.paper_broker for runtime in self._runtimes],
            "journal": [runtime.journal for runtime in self._runtimes],
            "orchestration": [runtime.orchestration for runtime in self._runtimes],
            "portfolio_provider": [runtime.portfolio_provider for runtime in self._runtimes],
            "risk_profile_provider": [runtime.risk_profile_provider for runtime in self._runtimes],
            "kill_switch_provider": [runtime.kill_switch_provider for runtime in self._runtimes],
            "ai_usage_ledger": [runtime.ai_usage_ledger for runtime in self._runtimes],
        }
        for name, values in stateful_boundaries.items():
            if len({id(value) for value in values}) != len(values):
                raise ShadowIsolationError(f"{name} must not be shared between SHADOW systems")


        market_providers = [runtime.market_constraints_provider for runtime in self._runtimes]
        for index, provider in enumerate(market_providers):
            duplicates = [
                other for other in market_providers[index + 1 :] if other is provider
            ]
            if duplicates and not isinstance(provider, ImmutableMarketConstraintsProvider):
                raise ShadowIsolationError(
                    "shared market constraints provider must be explicitly immutable"
                )

        budgets = [getattr(runtime.orchestration, "_budget", None) for runtime in self._runtimes]
        present_budgets = [budget for budget in budgets if budget is not None]
        if len({id(budget) for budget in present_budgets}) != len(present_budgets):
            raise ShadowIsolationError(
                "AI hard-budget ledgers must not be shared between SHADOW systems"
            )

        gateways = []
        for runtime in self._runtimes:
            professor = getattr(runtime.orchestration, "professor", None)
            gateway = getattr(professor, "gateway", None)
            if gateway is not None:
                gateways.append(gateway)
        if len({id(gateway) for gateway in gateways}) != len(gateways):
            raise ShadowIsolationError(
                "stateful AI gateways must not be shared between SHADOW systems"
            )

    @staticmethod
    def _derive_opportunity(root_opportunity: Any, *, system_id: str, opportunity_id: str):
        updates = {"system_id": system_id, "opportunity_id": opportunity_id}
        model_copy = getattr(root_opportunity, "model_copy", None)
        if model_copy is not None:
            return model_copy(update=updates)
        if is_dataclass(root_opportunity):
            return replace(root_opportunity, **updates)
        raise TypeError("root opportunity must support model_copy() or be a dataclass")

    @staticmethod
    def _scoped_usage(
        runtime: ShadowSystemRuntime,
    ) -> tuple[tuple[SystemScopedAIUsage, ...], ShadowSystemFailure | None]:
        scoped: list[SystemScopedAIUsage] = []
        for usage in runtime.ai_usage_ledger.records():
            usage_system_id = getattr(usage, "system_id", runtime.identity.system_id)
            if usage_system_id != runtime.identity.system_id:
                return (), ShadowSystemFailure(
                    stage="ai_usage",
                    error_type="ShadowIsolationError",
                    message=(
                        f"AI usage belongs to {usage_system_id!r}, expected "
                        f"{runtime.identity.system_id!r}"
                    ),
                )
            scoped.append(
                SystemScopedAIUsage(
                    system_id=runtime.identity.system_id,
                    usage=usage,
                )
            )
        return tuple(scoped), None
