import asyncio
import json
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.agents.models import (
    BerlinAnalysis,
    DenverAnalysis,
    DenverContext,
    EvidenceReference,
    NairobiAnalysis,
    PalermoReview,
    ProfessorPlan,
    RioAnalysis,
    RioContext,
    TokyoAnalysis,
)
from app.intelligence.ai_gateway.budget import AIBudgetLedger
from app.intelligence.ai_gateway.models import AIGatewayResult, AIUsageRecord
from app.market.features.models import FeatureQuality, FeatureSnapshot, MarketRegime
from app.market.scanner.models import CandidateOpportunity, ScannerTrigger
from app.services.backtest.setup_stats import (
    DenverSetupStatsContextProvider,
    HistoricalSetupKey,
    HistoricalSetupObservation,
    HistoricalSetupStatsCatalog,
)
from app.services.backtest.splits import BacktestPeriodRole
from app.services.orchestration import (
    OrchestrationPipeline,
    PipelineFailureCode,
    PipelineStatus,
)
from app.services.orchestration.models import ProfessorFinalDecision


class ScriptedGateway:
    def __init__(self, scripted):
        self.scripted = defaultdict(deque)
        for key, values in scripted.items():
            self.scripted[key].extend(values)
        self.requests = []

    async def generate_structured(self, request, output_model):
        self.requests.append(request)
        key = (request.agent_id, request.metadata["phase"])
        if not self.scripted[key]:
            raise AssertionError(f"no scripted response for {key}")
        item = self.scripted[key].popleft()
        if isinstance(item, BaseException):
            raise item
        # Specialist v3 uses a request-specific provider subclass while
        # integration fixtures intentionally script the canonical model.
        assert isinstance(item, output_model) or issubclass(
            output_model,
            type(item),
        )
        usage = AIUsageRecord(
            request_id=request.request_id,
            system_id=request.system_id,
            agent_id=request.agent_id,
            route_id=request.model_route,
            model_id="mock",
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            estimated_cost=Decimal("0"),
            latency_ms=0,
            attempt=1,
        )
        return AIGatewayResult(
            request_id=request.request_id,
            route_id=request.model_route,
            model_id="mock",
            output=item,
            usage=usage,
            attempts=1,
        )


class BarrierGateway(ScriptedGateway):
    def __init__(self, scripted, expected_specialists):
        super().__init__(scripted)
        self.expected_specialists = expected_specialists
        self.specialists_entered = 0
        self.release = asyncio.Event()

    async def generate_structured(self, request, output_model):
        if request.metadata["phase"] == "specialist_independent_round_1":
            self.specialists_entered += 1
            if self.specialists_entered == self.expected_specialists:
                self.release.set()
            await asyncio.wait_for(self.release.wait(), timeout=0.5)
        return await super().generate_structured(request, output_model)


def make_market_context():
    observed_at = datetime(2099, 1, 2, tzinfo=UTC)
    return FeatureSnapshot(
        feature_version="features-v1",
        snapshot_id="snapshot-1",
        source_snapshot_id="raw-1",
        symbol="BTCUSDT",
        timeframe="1h",
        observed_at=observed_at,
        candle_count=200,
        close=100.0,
        ema_fast=101.0,
        ema_slow=99.0,
        ema_spread_pct=2.0,
        rsi_14=62.0,
        atr_14=3.0,
        atr_pct=3.0,
        adx_14=30.0,
        volume_ratio=1.4,
        prior_range_high_20=99.0,
        prior_range_low_20=90.0,
        regime=MarketRegime.BULLISH_TREND,
        quality=FeatureQuality(
            warmup_complete=True,
            closed_candle_count=200,
            missing_features=(),
        ),
    )


def make_opportunity():
    created_at = datetime(2099, 1, 2, tzinfo=UTC)
    return CandidateOpportunity(
        scanner_version="scanner-v1",
        opportunity_id=str(uuid4()),
        snapshot_id="snapshot-1",
        system_id="balanced_v1",
        symbol="BTCUSDT",
        timeframe="1h",
        priority_score=80,
        triggers=(ScannerTrigger.RANGE_BREAK, ScannerTrigger.VOLUME_EXPANSION),
        created_at=created_at,
        expires_at=created_at + timedelta(hours=2),
    )


def rio_context(**updates):
    values = {
        "source": "derivatives-fixture",
        "instrument": "BTC-PERP",
        "observed_at": datetime(2099, 1, 2, tzinfo=UTC),
        "is_stale": False,
        "data_quality": "RELIABLE",
        "funding_rate": 0.0001,
        "open_interest": 1_000_000.0,
        "open_interest_change_pct": 3.5,
        "long_liquidations_notional": 10_000.0,
        "short_liquidations_notional": 35_000.0,
        "long_short_ratio": 1.2,
    }
    values.update(updates)
    return RioContext(**values)


def denver_context(**updates):
    values = {
        "stats_id": "setup-stats-1",
        "setup_definition_version": "range-break-v1",
        "as_of": datetime(2099, 1, 1, tzinfo=UTC),
        "source_run_ids": ("run-design-1", "run-validation-1", "run-oos-1"),
        "source_dataset_ids": ("dataset-1",),
        "sample_count": 120,
        "oos_sample_count": 30,
        "win_rate": 0.58,
        "expectancy": 1.25,
        "profit_factor": 1.45,
        "max_drawdown_pct": 0.08,
        "regime": "bullish_trend",
    }
    values.update(updates)
    return DenverContext(**values)


def berlin():
    return BerlinAnalysis(
        agent="berlin",
        stance="LONG",
        confidence=0.7,
        evidence=[
            EvidenceReference(
                source_key="market_context.adx_14",
                observation="ADX is supplied",
            )
        ],
        risks=["trend may fail"],
        invalidation=["regime changes"],
        data_gaps=[],
        regime="BULLISH_TREND",
        trend_maturity="EARLY",
        multi_timeframe_alignment="UNKNOWN",
    )


def tokyo():
    return TokyoAnalysis(
        agent="tokyo",
        stance="LONG",
        confidence=0.66,
        evidence=[
            EvidenceReference(
                source_key="market_context.rsi_14",
                observation="RSI is supplied",
            )
        ],
        risks=["momentum can fade"],
        invalidation=["RSI weakens"],
        data_gaps=[],
        momentum="BULLISH",
        momentum_quality="MODERATE",
        breakout_quality="UNCONFIRMED",
    )


def nairobi():
    return NairobiAnalysis(
        agent="nairobi",
        stance="LONG",
        confidence=0.64,
        evidence=[
            EvidenceReference(
                source_key="market_context.prior_range_high_20",
                observation="range high is supplied",
            )
        ],
        risks=["false breakout"],
        invalidation=["re-entry in range"],
        data_gaps=[],
        market_structure="HH_HL",
        liquidity_state="AT_RISK",
        breakout_state="BREAKOUT",
    )


def rio():
    return RioAnalysis(
        agent="rio",
        stance="NEUTRAL",
        confidence=0.55,
        evidence=[
            EvidenceReference(
                source_key="specialist_context.open_interest_change_pct",
                observation="open-interest change is supplied",
            )
        ],
        risks=["crowding can reverse"],
        invalidation=["positioning normalizes"],
        data_gaps=[],
        positioning_regime="MIXED",
        funding_state="POSITIVE",
        open_interest_state="RISING",
        liquidation_state="SHORT_DOMINATED",
        squeeze_risk="SHORT_SQUEEZE",
        data_quality="RELIABLE",
    )


def denver():
    return DenverAnalysis(
        agent="denver",
        stance="LONG",
        confidence=0.65,
        evidence=[
            EvidenceReference(
                source_key="specialist_context.expectancy",
                observation="expectancy is supplied",
            )
        ],
        risks=["historical edge can decay"],
        invalidation=["new OOS evidence degrades"],
        data_gaps=[],
        source_stats_id="setup-stats-1",
        historical_edge="POSITIVE",
        sample_size_band="LARGE",
        robustness="MIXED",
        oos_consistency="CONSISTENT",
    )


def palermo():
    return PalermoReview(
        verdict="CAUTION",
        severity=0.4,
        critical_objections=["historical relationships can change"],
        missing_checks=[],
        conditions_to_continue=["respect deterministic Risk Engine"],
    )


def final_no_trade():
    return ProfessorFinalDecision(
        direction="NO_TRADE",
        confidence=0.8,
        thesis=["advanced evidence does not justify execution in this fixture"],
        counter_evidence=[],
        invalidation=[],
        evidence=[],
        trade=None,
    )


def full_crew_script():
    return {
        ("professor", "plan"): [
            ProfessorPlan(
                decision="FULL_CREW",
                selected_agents=["berlin", "tokyo", "nairobi", "rio", "denver"],
                rationale=["all grounded contexts are available"],
            )
        ],
        ("berlin", "specialist_independent_round_1"): [berlin()],
        ("tokyo", "specialist_independent_round_1"): [tokyo()],
        ("nairobi", "specialist_independent_round_1"): [nairobi()],
        ("rio", "specialist_independent_round_1"): [rio()],
        ("denver", "specialist_independent_round_1"): [denver()],
        ("palermo", "red_team"): [palermo()],
        ("professor", "finalize"): [final_no_trade()],
    }


def make_pipeline(gateway):
    budget = AIBudgetLedger("1.00")
    return OrchestrationPipeline(gateway=gateway, budget=budget)


def test_advanced_specialists_are_context_gated_before_professor_selection():
    async def scenario():
        gateway = ScriptedGateway(
            {
                ("professor", "plan"): [
                    ProfessorPlan(decision="MINI_CREW", selected_agents=["denver"])
                ]
            }
        )
        result = await make_pipeline(gateway).run(
            opportunity=make_opportunity(),
            market_context=make_market_context(),
        )
        assert result.status is PipelineStatus.FAILED
        assert result.failure.code is PipelineFailureCode.INVALID_PROFESSOR_PLAN
        plan_payload = json.loads(gateway.requests[0].input_text)
        assert plan_payload["available_agents"] == ["berlin", "nairobi", "tokyo"]
        assert all(request.agent_id != "denver" for request in gateway.requests[1:])

    asyncio.run(scenario())


def test_denver_future_stats_are_rejected_before_any_ai_call():
    async def scenario():
        gateway = ScriptedGateway({})
        future = denver_context(as_of=datetime(2099, 1, 3, tzinfo=UTC))
        result = await make_pipeline(gateway).run(
            opportunity=make_opportunity(),
            market_context=make_market_context(),
            specialist_contexts={"denver": future},
        )
        assert result.status is PipelineStatus.FAILED
        assert result.failure.code is PipelineFailureCode.INVALID_CONTEXT
        assert result.failure.stage == "specialist_contexts"
        assert gateway.requests == []

    asyncio.run(scenario())


def test_full_crew_can_use_all_five_specialists_and_audits_advanced_calls():
    async def scenario():
        gateway = BarrierGateway(full_crew_script(), expected_specialists=5)
        result = await asyncio.wait_for(
            make_pipeline(gateway).run(
                opportunity=make_opportunity(),
                market_context=make_market_context(),
                specialist_contexts={
                    "rio": rio_context(),
                    "denver": denver_context(),
                },
            ),
            timeout=1.0,
        )
        assert result.status is PipelineStatus.NO_TRADE
        assert [run.agent_id for run in result.specialist_runs] == [
            "berlin",
            "tokyo",
            "nairobi",
            "rio",
            "denver",
        ]
        assert gateway.specialists_entered == 5
        assert len(result.agent_calls) == 8
        assert {call.agent_id for call in result.agent_calls} >= {"rio", "denver"}

        plan_payload = json.loads(gateway.requests[0].input_text)
        assert plan_payload["available_agents"] == [
            "berlin",
            "denver",
            "nairobi",
            "rio",
            "tokyo",
        ]

        rio_request = next(request for request in gateway.requests if request.agent_id == "rio")
        rio_payload = json.loads(rio_request.input_text)
        assert rio_payload["specialist_context"]["instrument"] == "BTC-PERP"

        denver_request = next(
            request for request in gateway.requests if request.agent_id == "denver"
        )
        denver_payload = json.loads(denver_request.input_text)
        assert denver_payload["specialist_context"]["stats_id"] == "setup-stats-1"

    asyncio.run(scenario())


def test_advanced_specialist_failure_fails_closed_before_palermo():
    async def scenario():
        script = {
            ("professor", "plan"): [
                ProfessorPlan(
                    decision="MINI_CREW",
                    selected_agents=["berlin", "denver"],
                )
            ],
            ("berlin", "specialist_independent_round_1"): [berlin()],
            ("denver", "specialist_independent_round_1"): [ValueError("denver failed")],
        }
        gateway = ScriptedGateway(script)
        result = await make_pipeline(gateway).run(
            opportunity=make_opportunity(),
            market_context=make_market_context(),
            specialist_contexts={"denver": denver_context()},
        )
        assert result.status is PipelineStatus.FAILED
        assert result.failure.code is PipelineFailureCode.INVALID_SPECIALIST_OUTPUT
        assert result.failure.agent_id == "denver"
        assert result.trade_proposal is None
        assert all(request.agent_id != "palermo" for request in gateway.requests)

    asyncio.run(scenario())


def test_rio_stale_context_is_not_advertised_to_professor():
    async def scenario():
        gateway = ScriptedGateway(
            {
                ("professor", "plan"): [
                    ProfessorPlan(
                        decision="NO_ANALYSIS",
                        selected_agents=[],
                        rationale=["no derivatives specialist available"],
                    )
                ]
            }
        )
        stale = rio_context(is_stale=True, data_quality="DEGRADED")
        result = await make_pipeline(gateway).run(
            opportunity=make_opportunity(),
            market_context=make_market_context(),
            specialist_contexts={"rio": stale},
        )
        assert result.status is PipelineStatus.NO_ANALYSIS
        plan_payload = json.loads(gateway.requests[0].input_text)
        assert "rio" not in plan_payload["available_agents"]

    asyncio.run(scenario())


def test_denver_catalog_provider_is_injected_before_professor_selection():
    async def scenario():
        market = make_market_context()
        opportunity = make_opportunity()
        setup = HistoricalSetupKey.from_market(opportunity, market)
        catalog = HistoricalSetupStatsCatalog(
            (
                HistoricalSetupObservation(
                    run_id="run-design-1",
                    dataset_id="dataset-1",
                    strategy_fingerprint="strategy-1",
                    period_role=BacktestPeriodRole.DESIGN,
                    opportunity_id="historical-opportunity-1",
                    trade_id="historical-trade-1",
                    setup=setup,
                    side="LONG",
                    opened_at=datetime(2098, 12, 31, 20, tzinfo=UTC),
                    closed_at=datetime(2098, 12, 31, 21, tzinfo=UTC),
                    net_pnl=Decimal("2.5"),
                ),
            )
        )
        stats = catalog.query(
            opportunity=opportunity,
            market_context=market,
            as_of=market.observed_at,
        )
        assert stats is not None
        denver_output = DenverAnalysis(
            agent="denver",
            stance="LONG",
            confidence=0.4,
            evidence=[
                EvidenceReference(
                    source_key="specialist_context.expectancy",
                    observation="historical expectancy is supplied",
                )
            ],
            risks=["single historical sample"],
            invalidation=["more samples contradict the edge"],
            data_gaps=["larger sample"],
            source_stats_id=stats.stats_id,
            historical_edge="INCONCLUSIVE",
            sample_size_band="SMALL",
            robustness="UNKNOWN",
            oos_consistency="UNAVAILABLE",
        )
        gateway = ScriptedGateway(
            {
                ("professor", "plan"): [
                    ProfessorPlan(decision="MINI_CREW", selected_agents=["denver"])
                ],
                ("denver", "specialist_independent_round_1"): [denver_output],
                ("palermo", "red_team"): [palermo()],
                ("professor", "finalize"): [final_no_trade()],
            }
        )
        pipeline = OrchestrationPipeline(
            gateway=gateway,
            budget=AIBudgetLedger("1.00"),
            specialist_context_provider=DenverSetupStatsContextProvider(catalog),
        )
        result = await pipeline.run(opportunity=opportunity, market_context=market)
        assert result.status is PipelineStatus.NO_TRADE
        plan_payload = json.loads(gateway.requests[0].input_text)
        assert "denver" in plan_payload["available_agents"]
        request = next(item for item in gateway.requests if item.agent_id == "denver")
        payload = json.loads(request.input_text)
        assert payload["specialist_context"]["stats_id"] == stats.stats_id
        assert payload["specialist_context"]["sample_count"] == 1
        assert payload["specialist_context"]["sample_size_band"] == "SMALL"

    asyncio.run(scenario())


def test_provider_and_explicit_context_collision_fails_before_ai_call():
    async def scenario():
        market = make_market_context()
        opportunity = make_opportunity()
        catalog = HistoricalSetupStatsCatalog(
            (
                HistoricalSetupObservation(
                    run_id="run-design-1",
                    dataset_id="dataset-1",
                    strategy_fingerprint="strategy-1",
                    period_role=BacktestPeriodRole.DESIGN,
                    opportunity_id="historical-opportunity-1",
                    trade_id="historical-trade-1",
                    setup=HistoricalSetupKey.from_market(opportunity, market),
                    side="LONG",
                    opened_at=datetime(2098, 12, 31, 20, tzinfo=UTC),
                    closed_at=datetime(2098, 12, 31, 21, tzinfo=UTC),
                    net_pnl=Decimal("2.5"),
                ),
            )
        )
        gateway = ScriptedGateway({})
        pipeline = OrchestrationPipeline(
            gateway=gateway,
            budget=AIBudgetLedger("1.00"),
            specialist_context_provider=DenverSetupStatsContextProvider(catalog),
        )
        result = await pipeline.run(
            opportunity=opportunity,
            market_context=market,
            specialist_contexts={"denver": denver_context()},
        )
        assert result.status is PipelineStatus.FAILED
        assert result.failure.code is PipelineFailureCode.INVALID_CONTEXT
        assert result.failure.stage == "specialist_contexts"
        assert gateway.requests == []

    asyncio.run(scenario())
