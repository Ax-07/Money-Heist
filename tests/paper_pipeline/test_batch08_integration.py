from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.intelligence.ai_gateway.budget import AIBudgetLedger
from app.intelligence.ai_gateway.gateway import AIGateway
from app.intelligence.ai_gateway.models import ProviderRequest, ProviderResponse, TokenUsage
from app.intelligence.ai_gateway.routing import ModelPricing, ModelRoute, ModelRouter
from app.market.features.models import FeatureQuality, FeatureSnapshot, MarketRegime
from app.market.scanner.models import CandidateOpportunity, ScannerTrigger
from app.services.orchestration import OrchestrationPipeline
from app.services.paper_pipeline import (
    InMemoryKillSwitchStateProvider,
    InMemoryMarketConstraintsProvider,
    InMemoryPaperPipelineJournal,
    InMemoryPortfolioRiskStateProvider,
    InMemoryRiskProfileProvider,
    PaperPipelineStatus,
    PaperTradingPipeline,
)
from app.trading.paper.broker import PaperBroker
from app.trading.paper.config import PaperBrokerConfig
from app.trading.risk.engine import RiskEngine
from app.trading.risk.models import KillSwitchState, MarketConstraints, PortfolioRiskState
from app.trading.risk.profiles import demo_profile


NOW = datetime(2026, 9, 7, 16, 0, tzinfo=timezone.utc)


def sync_test(func):
    def wrapper():
        return asyncio.run(func())

    wrapper.__name__ = func.__name__
    return wrapper


def _adapt_scripted_specialist_v3(
    request: ProviderRequest,
    output: str,
) -> str:
    if (
        request.metadata.get("phase") != "specialist_independent_round_1"
        or request.metadata.get("prompt_version") != "v3"
    ):
        return output

    try:
        payload = json.loads(output)
        request_payload = json.loads(request.input_text)
    except json.JSONDecodeError:
        return output
    if not isinstance(payload, dict) or not isinstance(request_payload, dict):
        return output

    evidence = payload.get("evidence")
    allowed = request_payload.get("allowed_evidence_source_keys")
    if not isinstance(evidence, list) or not isinstance(allowed, list):
        return output

    index_by_key = {
        key: index
        for index, key in enumerate(allowed)
        if isinstance(key, str)
    }
    converted = []
    for item in evidence:
        if not isinstance(item, dict):
            return output
        source_key = item.get("source_key")
        if not isinstance(source_key, str) or source_key not in index_by_key:
            return output
        converted.append(
            {
                "source_index": index_by_key[source_key],
                "observation": item["observation"],
            }
        )
    payload["evidence"] = converted
    return json.dumps(payload, separators=(",", ":"))


class ScriptedClient:
    provider_name = "mock"

    def __init__(self, scripted):
        self.scripted = defaultdict(deque)
        for key, values in scripted.items():
            self.scripted[key].extend(values)

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        key = (request.agent_id, request.metadata["phase"])
        if not self.scripted[key]:
            raise AssertionError(f"No scripted response for {key}")
        output = _adapt_scripted_specialist_v3(
            request,
            self.scripted[key].popleft(),
        )
        return ProviderResponse(
            provider_request_id=f"mock-{request.agent_id}-{request.metadata['phase']}",
            model_id=request.model_id,
            output_text=output,
            usage=TokenUsage(input_tokens=20, output_tokens=20),
            latency_ms=1,
        )


class CountingRiskEngine(RiskEngine):
    def __init__(self):
        self.calls = 0

    def evaluate(self, **kwargs):
        self.calls += 1
        return super().evaluate(**kwargs)


class CountingPaperBroker(PaperBroker):
    def __init__(self):
        super().__init__(PaperBrokerConfig(system_id="balanced_v1"))
        self.submit_calls = 0

    async def submit_order(self, request, *, trigger=None):
        self.submit_calls += 1
        return await super().submit_order(request, trigger=trigger)


def dumps(value) -> str:
    return json.dumps(value, separators=(",", ":"))


def long_script(*, final_output: str | None = None):
    return {
        ("professor", "plan"): [
            dumps(
                {
                    "decision": "MINI_CREW",
                    "selected_agents": ["berlin"],
                    "rationale": ["trend context is sufficient"],
                    "request_more_analysis": False,
                }
            )
        ],
        ("berlin", "specialist_independent_round_1"): [
            dumps(
                {
                    "agent": "berlin",
                    "stance": "LONG",
                    "confidence": 0.75,
                    "evidence": [
                        {"source_key": "market_context.regime", "observation": "trend context"}
                    ],
                    "risks": ["trend may fail"],
                    "invalidation": ["regime transition"],
                    "data_gaps": [],
                    "regime": "BULLISH_TREND",
                    "trend_maturity": "EARLY",
                    "multi_timeframe_alignment": "UNKNOWN",
                }
            )
        ],
        ("palermo", "red_team"): [
            dumps(
                {
                    "verdict": "CAUTION",
                    "severity": 0.4,
                    "critical_objections": ["false breakout remains possible"],
                    "missing_checks": [],
                    "conditions_to_continue": ["respect stop"],
                }
            )
        ],
        ("professor", "finalize"): [
            final_output
            or dumps(
                {
                    "direction": "LONG",
                    "confidence": 0.72,
                    "thesis": ["conditional long"],
                    "counter_evidence": ["false breakout risk"],
                    "invalidation": ["price below 98"],
                    "evidence": [
                        {"source_key": "market_context.close", "observation": "close supplied"}
                    ],
                    "trade": {
                        "entry_price": "100",
                        "stop_price": "98",
                        "targets": ["104"],
                        "expected_rr": "2",
                    },
                }
            )
        ],
    }


def make_orchestration(scripted, *, budget="1.00"):
    ledger = AIBudgetLedger(budget)
    pricing = ModelPricing(
        input_per_million_eur=Decimal("1"),
        output_per_million_eur=Decimal("1"),
    )
    router = ModelRouter(
        [
            ModelRoute(
                route_id="core_reasoning",
                provider="mock",
                model_id="mock-core",
                pricing=pricing,
                max_output_tokens=1200,
            ),
            ModelRoute(
                route_id="economy",
                provider="mock",
                model_id="mock-economy",
                pricing=pricing,
                max_output_tokens=800,
            ),
        ]
    )
    gateway = AIGateway(
        router=router,
        clients={"mock": ScriptedClient(scripted)},
        budget=ledger,
        max_attempts=1,
        retry_backoff_seconds=0,
    )
    return OrchestrationPipeline(gateway=gateway, budget=ledger)


def opportunity():
    return CandidateOpportunity(
        scanner_version="scanner-v1",
        opportunity_id="60000000-0000-0000-0000-000000000001",
        snapshot_id="snapshot-1",
        system_id="balanced_v1",
        symbol="BTCUSDT",
        timeframe="1m",
        priority_score=80,
        triggers=(ScannerTrigger.RANGE_BREAK,),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )


def context():
    return FeatureSnapshot(
        feature_version="features-v1",
        snapshot_id="snapshot-1",
        source_snapshot_id="raw-1",
        symbol="BTCUSDT",
        timeframe="1m",
        observed_at=NOW,
        candle_count=100,
        close=100.0,
        ema_fast=101.0,
        ema_slow=99.0,
        ema_spread_pct=2.0,
        rsi_14=62.0,
        adx_14=30.0,
        prior_range_high_20=99.0,
        prior_range_low_20=90.0,
        regime=MarketRegime.BULLISH_TREND,
        quality=FeatureQuality(
            warmup_complete=True,
            closed_candle_count=100,
            missing_features=(),
        ),
    )


def paper_service(orchestration):
    risk = CountingRiskEngine()
    broker = CountingPaperBroker()
    service = PaperTradingPipeline(
        orchestration=orchestration,
        risk_engine=risk,
        paper_broker=broker,
        portfolio_provider=InMemoryPortfolioRiskStateProvider(
            {
                "balanced_v1": PortfolioRiskState(
                    equity=Decimal("100"),
                    day_start_equity=Decimal("100"),
                    equity_peak=Decimal("100"),
                    daily_pnl=Decimal("0"),
                    open_positions=0,
                )
            }
        ),
        risk_profile_provider=InMemoryRiskProfileProvider({"balanced_v1": demo_profile()}),
        market_constraints_provider=InMemoryMarketConstraintsProvider(
            {
                "BTCUSDT": MarketConstraints(
                    qty_step=Decimal("0.001"),
                    min_qty=Decimal("0.001"),
                    min_notional=Decimal("1"),
                    max_qty=Decimal("100"),
                    max_leverage=Decimal("1"),
                )
            }
        ),
        kill_switch_provider=InMemoryKillSwitchStateProvider(
            {"balanced_v1": KillSwitchState()}
        ),
        journal=InMemoryPaperPipelineJournal(),
        clock=lambda: NOW,
    )
    return service, risk, broker


@sync_test
async def test_real_batch08_orchestration_flows_to_risk_and_paper_broker():
    service, risk, broker = paper_service(make_orchestration(long_script()))
    result = await service.run(opportunity=opportunity(), market_context=context(), now=NOW)
    assert result.status is PaperPipelineStatus.EXECUTED
    assert risk.calls == 1
    assert broker.submit_calls == 1
    assert result.orchestration_result.trade_proposal is not None
    assert result.fill is not None
    assert result.position_after is not None


@sync_test
async def test_real_batch08_invalid_final_output_never_reaches_risk_or_broker():
    service, risk, broker = paper_service(make_orchestration(long_script(final_output="{}")))
    result = await service.run(opportunity=opportunity(), market_context=context(), now=NOW)
    assert result.status is PaperPipelineStatus.FAILED
    assert risk.calls == 0
    assert broker.submit_calls == 0


@sync_test
async def test_real_batch08_budget_gate_no_analysis_never_reaches_risk_or_broker():
    service, risk, broker = paper_service(make_orchestration({}, budget="0.001"))
    result = await service.run(opportunity=opportunity(), market_context=context(), now=NOW)
    assert result.status is PaperPipelineStatus.NO_ANALYSIS
    assert risk.calls == 0
    assert broker.submit_calls == 0
