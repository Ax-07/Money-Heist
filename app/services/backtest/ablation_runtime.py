from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, TypeAlias

from app.agents.specialists import Berlin, Denver, Nairobi, Rio, Tokyo
from app.intelligence.ai_gateway.budget import AIBudgetLedger
from app.intelligence.ai_gateway.client import AIClient
from app.intelligence.ai_gateway.gateway import AIGateway
from app.intelligence.ai_gateway.routing import ModelPricing, ModelRoute, ModelRouter
from app.intelligence.ai_gateway.usage import InMemoryAIUsageRecorder
from app.services.backtest.mtf_runtime import mtf_runner_kwargs
from app.services.backtest.ai_modes import BacktestAIClient
from app.services.backtest.cache import BacktestResponseCache
from app.services.backtest.clock import ReplayClock
from app.services.backtest.ids import ReplayIdFactory
from app.services.backtest.lifecycle import HistoricalPositionLifecycle
from app.services.backtest.models import BacktestAIMode
from app.services.backtest.splits import BacktestPeriodRole
from app.services.backtest.portfolio import BacktestPortfolioStateProvider
from app.services.backtest.runner import HistoricalReplayRunner
from app.services.orchestration.pipeline import OrchestrationPipeline
from app.services.paper_pipeline.journal import InMemoryPaperPipelineJournal
from app.services.paper_pipeline.pipeline import PaperTradingPipeline
from app.services.paper_pipeline.providers import (
    InMemoryKillSwitchStateProvider,
    InMemoryMarketConstraintsProvider,
    InMemoryRiskProfileProvider,
)
from app.trading.paper import PaperBroker, PaperBrokerConfig
from app.trading.risk import KillSwitchState, MarketConstraints, RiskEngine, RiskProfile

from app.evaluation.ablation_campaign import AblationCampaignPlan, AblationCampaignVariant
from app.evaluation.ablation_campaign_execution import (
    AblationCampaignExecutionReport,
    AblationCampaignExecutor,
    AblationVariantRuntime,
)

SpecialistFactory: TypeAlias = Callable[[Any], Any]

_V1_FACTORIES: Mapping[str, SpecialistFactory] = MappingProxyType(
    {
        "berlin": Berlin,
        "denver": Denver,
        "nairobi": Nairobi,
        "rio": Rio,
        "tokyo": Tokyo,
    }
)


def _finite_non_negative(value: Decimal, *, field_name: str) -> Decimal:
    normalized = Decimal(str(value))
    if not normalized.is_finite() or normalized < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return normalized


def v1_specialist_factories(
    agent_ids: Sequence[str],
) -> Mapping[str, SpecialistFactory]:
    normalized = tuple(sorted(str(agent_id).strip().lower() for agent_id in agent_ids))
    if not normalized:
        raise ValueError("agent_ids must not be empty")
    if any(not agent_id for agent_id in normalized):
        raise ValueError("agent_ids must not contain blanks")
    if len(set(normalized)) != len(normalized):
        raise ValueError("agent_ids must not contain duplicates")

    unknown = tuple(agent_id for agent_id in normalized if agent_id not in _V1_FACTORIES)
    if unknown:
        raise ValueError("unknown V1 specialist factories: " + ", ".join(unknown))
    return MappingProxyType({agent_id: _V1_FACTORIES[agent_id] for agent_id in normalized})


@dataclass(frozen=True, slots=True)
class PaperAblationRuntimeSettings:
    risk_profile: RiskProfile
    market_constraints: MarketConstraints
    ai_hard_budget_eur: Decimal
    model_id: str
    pricing: ModelPricing
    cache: BacktestResponseCache | None = None
    mock_client: AIClient | None = None
    live_client: AIClient | None = None
    specialist_context_provider: Any | None = None
    core_max_output_tokens: int = 1200
    economy_max_output_tokens: int = 800

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ai_hard_budget_eur",
            _finite_non_negative(
                self.ai_hard_budget_eur,
                field_name="ai_hard_budget_eur",
            ),
        )
        model_id = self.model_id.strip()
        if not model_id:
            raise ValueError("model_id must not be blank")
        object.__setattr__(self, "model_id", model_id)
        if self.core_max_output_tokens <= 0:
            raise ValueError("core_max_output_tokens must be > 0")
        if self.economy_max_output_tokens <= 0:
            raise ValueError("economy_max_output_tokens must be > 0")


class PaperAblationRuntimeFactory:
    """Build one fresh PAPER/Batch 16 runtime for each ablation variant.

    Specialist factories, not specialist instances, are accepted deliberately. Every variant gets
    fresh agent instances bound to its own AI Gateway, hard budget, usage recorder and cache scope.
    Stateful PAPER components are never shared across variants.
    """

    def __init__(self, settings: PaperAblationRuntimeSettings) -> None:
        self.settings = settings

    def __call__(
        self,
        *,
        variant: AblationCampaignVariant,
        specialists: Mapping[str, SpecialistFactory],
    ) -> AblationVariantRuntime:
        self._validate_specialist_factories(variant, specialists)
        run = variant.run
        self._validate_ai_mode(run.config.ai_mode)
        self._validate_model_versions(variant)

        clock = ReplayClock.start(run.dataset.start_at)
        broker = PaperBroker(
            PaperBrokerConfig(
                system_id=run.config.system_id,
                initial_balance=run.config.initial_balance,
                maker_fee_bps=run.config.maker_fee_bps,
                taker_fee_bps=run.config.taker_fee_bps,
                market_slippage_bps=run.config.market_slippage_bps,
            ),
            id_factory=ReplayIdFactory(run.run_id),
            clock=clock,
        )
        portfolio = BacktestPortfolioStateProvider(
            system_id=run.config.system_id,
            initial_balance=run.config.initial_balance,
        )
        lifecycle = HistoricalPositionLifecycle(
            broker=broker,
            system_id=run.config.system_id,
        )
        journal = InMemoryPaperPipelineJournal()
        usage = InMemoryAIUsageRecorder()
        budget = AIBudgetLedger(self.settings.ai_hard_budget_eur)
        gateway = self._gateway(variant, budget=budget, usage=usage)

        specialist_instances = {
            agent_id: factory(gateway) for agent_id, factory in specialists.items()
        }
        orchestration = OrchestrationPipeline(
            gateway=gateway,
            budget=budget,
            specialists=specialist_instances,
            specialist_context_provider=self.settings.specialist_context_provider,
        )
        pipeline = PaperTradingPipeline(
            orchestration=orchestration,
            risk_engine=RiskEngine(),
            paper_broker=broker,
            portfolio_provider=portfolio,
            risk_profile_provider=InMemoryRiskProfileProvider(
                {run.config.system_id: self.settings.risk_profile}
            ),
            market_constraints_provider=InMemoryMarketConstraintsProvider(
                {run.dataset.symbol: self.settings.market_constraints}
            ),
            kill_switch_provider=InMemoryKillSwitchStateProvider(
                {run.config.system_id: KillSwitchState()}
            ),
            journal=journal,
            clock=clock,
        )
        runner = HistoricalReplayRunner(
            paper_pipeline=pipeline,
            clock=clock,
            portfolio_provider=portfolio,
            position_lifecycle=lifecycle,
            **mtf_runner_kwargs(run.config.execution_assumptions),
        )
        return AblationVariantRuntime.from_components(
            runner=runner,
            broker=broker,
            usage_recorder=usage,
            journal=journal,
        )

    def _gateway(
        self,
        variant: AblationCampaignVariant,
        *,
        budget: AIBudgetLedger,
        usage: InMemoryAIUsageRecorder,
    ) -> AIGateway[Any]:
        run = variant.run
        provider_name = (
            "mock" if run.config.ai_mode is BacktestAIMode.MOCK else "openai"
        )
        router = ModelRouter(
            [
                ModelRoute(
                    route_id="core_reasoning",
                    provider=provider_name,
                    model_id=self.settings.model_id,
                    pricing=self.settings.pricing,
                    max_output_tokens=self.settings.core_max_output_tokens,
                ),
                ModelRoute(
                    route_id="economy",
                    provider=provider_name,
                    model_id=self.settings.model_id,
                    pricing=self.settings.pricing,
                    max_output_tokens=self.settings.economy_max_output_tokens,
                ),
            ]
        )
        backtest_client = BacktestAIClient.from_run(
            run,
            cache=self.settings.cache,
            mock_client=(
                self.settings.mock_client
                if run.config.ai_mode is BacktestAIMode.MOCK
                else None
            ),
            live_client=(
                self.settings.live_client
                if run.config.ai_mode is BacktestAIMode.LIVE_EVAL
                else None
            ),
        )
        return AIGateway(
            router=router,
            clients={provider_name: backtest_client},
            budget=budget,
            max_attempts=1,
            retry_backoff_seconds=0,
            usage_recorder=usage,
        )

    def _validate_ai_mode(self, mode: BacktestAIMode) -> None:
        if mode is BacktestAIMode.MOCK and self.settings.mock_client is None:
            raise ValueError("MOCK ablation runtime requires mock_client")
        if mode is BacktestAIMode.CACHED and self.settings.cache is None:
            raise ValueError("CACHED ablation runtime requires BacktestResponseCache")
        if mode is BacktestAIMode.LIVE_EVAL and self.settings.live_client is None:
            raise ValueError("LIVE_EVAL ablation runtime requires live_client")

    def _validate_model_versions(self, variant: AblationCampaignVariant) -> None:
        versions = variant.run.config.model_versions
        relevant = {
            agent_id: versions[agent_id]
            for agent_id in variant.included_agents
            if agent_id in versions
        }
        mismatched = tuple(
            sorted(
                agent_id
                for agent_id, model_id in relevant.items()
                if model_id != self.settings.model_id
            )
        )
        if mismatched:
            raise ValueError(
                "runtime model_id disagrees with BacktestConfig.model_versions for: "
                + ", ".join(mismatched)
            )

    @staticmethod
    def _validate_specialist_factories(
        variant: AblationCampaignVariant,
        specialists: Mapping[str, SpecialistFactory],
    ) -> None:
        actual = tuple(sorted(specialists))
        if actual != variant.included_agents:
            raise ValueError("specialist factories must match variant.included_agents exactly")
        if any(not callable(factory) for factory in specialists.values()):
            raise TypeError("specialist factories must be callable")


def build_paper_ablation_executor(
    settings: PaperAblationRuntimeSettings,
) -> AblationCampaignExecutor:
    return AblationCampaignExecutor(PaperAblationRuntimeFactory(settings))


async def execute_paper_ablation_campaign(
    plan: AblationCampaignPlan,
    *,
    candles: Sequence[Any],
    role: BacktestPeriodRole,
    settings: PaperAblationRuntimeSettings,
    specialist_factories: Mapping[str, SpecialistFactory] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> AblationCampaignExecutionReport:
    factories = (
        v1_specialist_factories(plan.baseline_agents)
        if specialist_factories is None
        else specialist_factories
    )
    executor = build_paper_ablation_executor(settings)
    return await executor.execute(
        plan,
        candles=candles,
        role=role,
        specialists=factories,
        cancel_check=cancel_check,
    )


__all__ = [
    "PaperAblationRuntimeFactory",
    "PaperAblationRuntimeSettings",
    "SpecialistFactory",
    "build_paper_ablation_executor",
    "execute_paper_ablation_campaign",
    "v1_specialist_factories",
]
