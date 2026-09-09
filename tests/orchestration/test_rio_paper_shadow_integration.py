from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.agents.models import (
    EvidenceReference,
    PalermoReview,
    ProfessorPlan,
    RioAnalysis,
)
from app.intelligence.ai_gateway.budget import AIBudgetLedger
from app.intelligence.ai_gateway.models import AIGatewayResult, AIUsageRecord
from app.market.exchange import (
    DerivativesPositioningSnapshot,
    MarketSidecarRefreshStatus,
    PaperShadowMarketFeed,
)
from app.market.features.models import FeatureQuality, FeatureSnapshot, MarketRegime
from app.market.models import Candle, MarketSnapshot, SnapshotQuality
from app.market.scanner.models import CandidateOpportunity, ScannerTrigger, ScanResult
from app.services.orchestration import (
    KrakenFuturesRioContextProvider,
    OrchestrationPipeline,
    PipelineStatus,
)
from app.services.orchestration.models import ProfessorFinalDecision

NOW = datetime(2026, 9, 9, 1, 30, tzinfo=UTC)


class ScriptedGateway:
    def __init__(self, scripted) -> None:
        self.scripted = defaultdict(deque)
        for key, values in scripted.items():
            self.scripted[key].extend(values)
        self.requests = []

    async def generate_structured(self, request, output_model):
        self.requests.append(request)
        key = (request.agent_id, request.metadata["phase"])
        if not self.scripted[key]:
            raise AssertionError(f"no scripted response for {key}")
        output = self.scripted[key].popleft()
        assert isinstance(output, output_model)
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
            output=output,
            usage=usage,
            attempts=1,
        )


class SpotProvider:
    async def get_snapshot(self, symbol: str) -> MarketSnapshot:
        assert symbol == "BTC/EUR"
        row = Candle(
            symbol="BTC/EUR",
            timeframe="5m",
            open_time=NOW - timedelta(minutes=5),
            close_time=NOW,
            open="100",
            high="102",
            low="99",
            close="101",
            volume="5",
            is_closed=True,
        )
        return MarketSnapshot(
            symbol="BTC/EUR",
            source="kraken_spot",
            observed_at=NOW - timedelta(seconds=5),
            received_at=NOW,
            last_price="101",
            candles={"5m": (row,)},
            quality=SnapshotQuality(),
        )

    async def get_candles(self, symbol: str, timeframe: str, limit: int):
        raise AssertionError("feed uses the normalized snapshot candle set")


class Features:
    def compute(self, candles, **kwargs) -> FeatureSnapshot:
        return FeatureSnapshot(
            feature_version="features-v1",
            snapshot_id="snapshot-rio-live-1",
            source_snapshot_id=kwargs["source_snapshot_id"],
            symbol=kwargs["symbol"],
            timeframe=kwargs["timeframe"],
            observed_at=kwargs["observed_at"],
            candle_count=100,
            close=101.0,
            ema_fast=101.0,
            ema_slow=99.0,
            ema_spread_pct=2.0,
            adx_14=30.0,
            regime=MarketRegime.BULLISH_TREND,
            quality=FeatureQuality(
                warmup_complete=True,
                closed_candle_count=100,
            ),
        )


class Scanner:
    def scan(self, current: FeatureSnapshot, **kwargs) -> ScanResult:
        opportunity = CandidateOpportunity(
            scanner_version="scanner-v1",
            opportunity_id="10000000-0000-0000-0000-000000000117",
            snapshot_id=current.snapshot_id,
            system_id=kwargs["system_id"],
            symbol=current.symbol,
            timeframe=current.timeframe,
            priority_score=80,
            triggers=(ScannerTrigger.TREND_STRENGTH,),
            created_at=current.observed_at,
            expires_at=current.observed_at + timedelta(minutes=15),
        )
        return ScanResult(
            score=80,
            triggers=opportunity.triggers,
            opportunity=opportunity,
        )


class Analytics:
    def __init__(self) -> None:
        self.calls = 0

    async def get_positioning_snapshot(self, symbol: str):
        self.calls += 1
        return DerivativesPositioningSnapshot(
            source="kraken_futures_analytics",
            symbol=symbol,
            instrument="PF_XBTUSD",
            observed_at=NOW - timedelta(minutes=5),
            received_at=NOW,
            funding_rate=Decimal("0.0002"),
            open_interest=Decimal("1000000"),
            open_interest_change_pct=Decimal("2.5"),
            long_short_ratio=Decimal("1.2"),
            missing_fields=(
                "long_liquidations_notional",
                "short_liquidations_notional",
            ),
        )


def rio_analysis() -> RioAnalysis:
    return RioAnalysis(
        agent="rio",
        stance="NEUTRAL",
        confidence=0.55,
        evidence=[
            EvidenceReference(
                source_key="specialist_context.open_interest_change_pct",
                observation="Kraken Futures open interest change is supplied",
            )
        ],
        risks=["crowding can reverse"],
        invalidation=["positioning normalizes"],
        data_gaps=["long/short liquidation split unavailable"],
        positioning_regime="MIXED",
        funding_state="POSITIVE",
        open_interest_state="RISING",
        liquidation_state="UNKNOWN",
        squeeze_risk="UNKNOWN",
        data_quality="RELIABLE",
    )


def test_real_rio_sidecar_becomes_selectable_before_paper_shadow_orchestration() -> None:
    async def scenario() -> None:
        analytics = Analytics()
        rio_provider = KrakenFuturesRioContextProvider(
            analytics,
            min_refresh_interval=timedelta(minutes=2),
            now=lambda: NOW,
        )
        feed = PaperShadowMarketFeed(
            SpotProvider(),
            feature_engine=Features(),
            scanner=Scanner(),
            root_system_id="balanced_v1",
            sidecar_refreshers=(rio_provider,),
        )
        market_input = await feed.build(symbol="BTC/EUR", timeframe="5m")
        assert market_input.opportunity is not None
        assert market_input.sidecar_refreshes[0].status is MarketSidecarRefreshStatus.REFRESHED
        assert analytics.calls == 1

        gateway = ScriptedGateway(
            {
                ("professor", "plan"): [
                    ProfessorPlan(
                        decision="MINI_CREW",
                        selected_agents=["rio"],
                        rationale=["real derivatives context is available"],
                    )
                ],
                ("rio", "specialist_independent_round_1"): [rio_analysis()],
                ("palermo", "red_team"): [
                    PalermoReview(
                        verdict="CAUTION",
                        severity=0.4,
                        critical_objections=["positioning can change quickly"],
                        missing_checks=[],
                        conditions_to_continue=["respect deterministic Risk Engine"],
                    )
                ],
                ("professor", "finalize"): [
                    ProfessorFinalDecision(
                        direction="NO_TRADE",
                        confidence=0.7,
                        thesis=["Rio context is informative but not decisive"],
                        counter_evidence=[],
                        invalidation=[],
                        evidence=[],
                        trade=None,
                    )
                ],
            }
        )
        orchestration = OrchestrationPipeline(
            gateway=gateway,
            budget=AIBudgetLedger("1.00"),
            specialist_context_provider=rio_provider,
        )
        result = await orchestration.run(
            opportunity=market_input.opportunity,
            market_context=market_input.market_context,
            now=market_input.market_context.observed_at,
        )

        assert result.status is PipelineStatus.NO_TRADE
        assert [run.agent_id for run in result.specialist_runs] == ["rio"]
        plan_payload = json.loads(gateway.requests[0].input_text)
        assert "rio" in plan_payload["available_agents"]
        rio_request = next(request for request in gateway.requests if request.agent_id == "rio")
        rio_payload = json.loads(rio_request.input_text)
        context = rio_payload["specialist_context"]
        assert context["source"] == "kraken_futures_analytics"
        assert context["instrument"] == "PF_XBTUSD"
        assert context["open_interest"] == 1_000_000.0
        assert "long_liquidations_notional" not in context
        assert "short_liquidations_notional" not in context

    asyncio.run(scenario())
