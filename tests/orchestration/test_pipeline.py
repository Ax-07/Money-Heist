from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from app.intelligence.ai_gateway.budget import AIBudgetLedger
from app.intelligence.ai_gateway.gateway import AIGateway
from app.intelligence.ai_gateway.models import ProviderRequest, ProviderResponse, TokenUsage
from app.intelligence.ai_gateway.routing import ModelPricing, ModelRoute, ModelRouter
from app.market.features.models import FeatureQuality, FeatureSnapshot, MarketRegime
from app.market.scanner.models import CandidateOpportunity, ScannerTrigger
from app.services.orchestration import (
    ComputeGate,
    ComputeGatePolicy,
    OrchestrationPipeline,
    PipelineFailureCode,
    PipelineStatus,
)


def sync_test(func):
    """Run an async scenario without adding pytest-asyncio as a dependency."""

    def wrapper():
        return asyncio.run(func())

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


def _adapt_scripted_indexed_evidence(
    request: ProviderRequest,
    output: str,
) -> str:
    try:
        payload = json.loads(output)
        request_payload = json.loads(request.input_text)
    except json.JSONDecodeError:
        return output
    if not isinstance(payload, dict) or not isinstance(request_payload, dict):
        return output

    evidence = payload.get("evidence")
    catalog = request_payload.get("evidence_source_catalog")
    if not isinstance(evidence, list) or not isinstance(catalog, list):
        return output

    index_by_key = {
        entry["source_key"]: entry["source_index"]
        for entry in catalog
        if isinstance(entry, dict)
        and isinstance(entry.get("source_key"), str)
        and isinstance(entry.get("source_index"), int)
    }
    converted = []
    for item in evidence:
        if not isinstance(item, dict):
            return output
        if "source_index" in item:
            converted.append(dict(item))
            continue
        source_key = item.get("source_key")
        # Invalid scripted paths intentionally remain unadapted so the strict
        # provider schema rejects them before downstream grounding.
        if not isinstance(source_key, str) or source_key not in index_by_key:
            return output
        converted_item = {
            key: value for key, value in item.items() if key != "source_key"
        }
        converted_item["source_index"] = index_by_key[source_key]
        converted.append(converted_item)

    payload["evidence"] = converted
    return json.dumps(payload, separators=(",", ":"))


class ScriptedClient:
    provider_name = "mock"

    def __init__(self, scripted: dict[tuple[str, str], list[str]]):
        self.scripted = defaultdict(deque)
        for key, values in scripted.items():
            self.scripted[key].extend(values)
        self.requests: list[ProviderRequest] = []

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        key = (request.agent_id, request.metadata["phase"])
        if not self.scripted[key]:
            raise AssertionError(f"No scripted response for {key}")
        output = _adapt_scripted_indexed_evidence(
            request,
            self.scripted[key].popleft(),
        )
        return ProviderResponse(
            provider_request_id=f"mock-{len(self.requests)}",
            model_id=request.model_id,
            output_text=output,
            usage=TokenUsage(input_tokens=20, output_tokens=20),
            latency_ms=1,
        )


class BarrierScriptedClient(ScriptedClient):
    """Require all three specialists to enter the provider before any may finish."""

    def __init__(self, scripted):
        super().__init__(scripted)
        self.specialists_entered = 0
        self.release_specialists = asyncio.Event()

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        if request.metadata["phase"] == "specialist_independent_round_1":
            self.specialists_entered += 1
            if self.specialists_entered == 3:
                self.release_specialists.set()
            await asyncio.wait_for(self.release_specialists.wait(), timeout=0.5)
        return await super().complete(request)


def dumps(value) -> str:
    return json.dumps(value, separators=(",", ":"))


def berlin(*, source_key: str = "market_context.regime") -> str:
    return dumps(
        {
            "agent": "berlin",
            "stance": "LONG",
            "confidence": 0.75,
            "evidence": [{"source_key": source_key, "observation": "trend context"}],
            "risks": ["trend may fail"],
            "invalidation": ["regime transition"],
            "data_gaps": [],
            "regime": "BULLISH_TREND",
            "trend_maturity": "EARLY",
            "multi_timeframe_alignment": "UNKNOWN",
        }
    )


def tokyo() -> str:
    return dumps(
        {
            "agent": "tokyo",
            "stance": "LONG",
            "confidence": 0.70,
            "evidence": [
                {"source_key": "market_context.rsi_14", "observation": "momentum supplied"}
            ],
            "risks": ["over-extension"],
            "invalidation": ["momentum fades"],
            "data_gaps": [],
            "momentum": "BULLISH",
            "momentum_quality": "MODERATE",
            "breakout_quality": "UNCONFIRMED",
        }
    )


def nairobi() -> str:
    return dumps(
        {
            "agent": "nairobi",
            "stance": "LONG",
            "confidence": 0.68,
            "evidence": [
                {
                    "source_key": "market_context.prior_range_high_20",
                    "observation": "range reference supplied",
                }
            ],
            "risks": ["false breakout"],
            "invalidation": ["re-entry in range"],
            "data_gaps": [],
            "market_structure": "HH_HL",
            "liquidity_state": "AT_RISK",
            "breakout_state": "BREAKOUT",
        }
    )


def palermo() -> str:
    return dumps(
        {
            "verdict": "CAUTION",
            "severity": 0.45,
            "critical_objections": ["false breakout remains possible"],
            "missing_checks": [],
            "conditions_to_continue": ["respect invalidation"],
        }
    )


def final_long() -> str:
    return dumps(
        {
            "direction": "LONG",
            "confidence": 0.72,
            "thesis": ["independent analyses support a conditional long"],
            "counter_evidence": ["Palermo flags false-breakout risk"],
            "invalidation": ["price below 95"],
            "evidence": [
                {"source_key": "market_context.close", "observation": "close supplied at 100"}
            ],
            "trade": {
                "entry_price": "100",
                "stop_price": "95",
                "targets": ["110"],
                "expected_rr": "2.0",
            },
        }
    )


def final_no_trade() -> str:
    return dumps(
        {
            "direction": "NO_TRADE",
            "confidence": 0.82,
            "thesis": ["evidence is insufficient after red-team review"],
            "counter_evidence": ["false-breakout risk"],
            "invalidation": [],
            "evidence": [],
            "trade": None,
        }
    )


def make_context(*, rsi: float | None = 62.0) -> FeatureSnapshot:
    return FeatureSnapshot(
        feature_version="features-v1",
        snapshot_id="snapshot-1",
        source_snapshot_id="raw-1",
        symbol="BTCUSDT",
        timeframe="1m",
        observed_at=datetime.now(timezone.utc),
        candle_count=100,
        close=100.0,
        ema_fast=101.0,
        ema_slow=99.0,
        ema_spread_pct=2.0,
        rsi_14=rsi,
        adx_14=30.0,
        prior_range_high_20=99.0,
        prior_range_low_20=90.0,
        regime=MarketRegime.BULLISH_TREND,
        quality=FeatureQuality(
            warmup_complete=True,
            closed_candle_count=100,
            missing_features=() if rsi is not None else ("rsi_14",),
        ),
    )


def make_opportunity(*, priority: int = 80) -> CandidateOpportunity:
    now = datetime.now(timezone.utc)
    return CandidateOpportunity(
        scanner_version="scanner-v1",
        opportunity_id=str(uuid4()),
        snapshot_id="snapshot-1",
        system_id="balanced_v1",
        symbol="BTCUSDT",
        timeframe="1m",
        priority_score=priority,
        triggers=(ScannerTrigger.RANGE_BREAK, ScannerTrigger.VOLUME_EXPANSION),
        created_at=now,
        expires_at=now + timedelta(minutes=10),
    )


def make_pipeline(
    scripted,
    *,
    budget="1.00",
    max_attempts=1,
    gate_policy=None,
    client_cls=ScriptedClient,
):
    ledger = AIBudgetLedger(budget)
    client = client_cls(scripted)
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
        clients={"mock": client},
        budget=ledger,
        max_attempts=max_attempts,
        retry_backoff_seconds=0,
    )
    gate = ComputeGate(ledger, gate_policy) if gate_policy else ComputeGate(ledger)
    return OrchestrationPipeline(gateway=gateway, budget=ledger, compute_gate=gate), client, ledger


def nominal_script(plan=None, final=None):
    return {
        ("professor", "plan"): [
            plan
            or dumps(
                {
                    "decision": "FULL_CREW",
                    "selected_agents": ["berlin", "tokyo", "nairobi"],
                    "rationale": ["high-priority candidate"],
                    "request_more_analysis": False,
                }
            )
        ],
        ("berlin", "specialist_independent_round_1"): [berlin()],
        ("tokyo", "specialist_independent_round_1"): [tokyo()],
        ("nairobi", "specialist_independent_round_1"): [nairobi()],
        ("palermo", "red_team"): [palermo()],
        ("professor", "finalize"): [final or final_long()],
    }


@sync_test
async def test_nominal_pipeline_produces_strict_trade_proposal_and_audit():
    pipeline, client, ledger = make_pipeline(nominal_script())
    opportunity = make_opportunity()
    result = await pipeline.run(opportunity=opportunity, market_context=make_context())

    assert result.status is PipelineStatus.TRADE_PROPOSAL
    proposal = result.trade_proposal
    assert proposal is not None
    assert proposal.opportunity_id == opportunity.opportunity_id
    assert proposal.source_snapshot_id == opportunity.snapshot_id
    assert proposal.side == "LONG"
    assert proposal.entry_price == Decimal("100")
    assert proposal.stop_price == Decimal("95")
    assert proposal.specialist_request_ids == tuple(run.request_id for run in result.specialist_runs)
    assert proposal.palermo_request_id == result.palermo_run.request_id
    assert len(result.agent_calls) == 6
    assert sum(call.estimated_cost_eur for call in result.agent_calls) == ledger.snapshot().spent_eur
    assert ledger.snapshot().spent_eur <= ledger.snapshot().hard_limit_eur
    assert [event.sequence for event in result.audit_events] == list(
        range(1, len(result.audit_events) + 1)
    )
    assert len(client.requests) == 6
    specialist_schema_names = {
        request.schema_name
        for request in client.requests
        if request.metadata["phase"] == "specialist_independent_round_1"
    }
    assert specialist_schema_names == {
        "BerlinAnalysis",
        "TokyoAnalysis",
        "NairobiAnalysis",
    }


@sync_test
async def test_no_analysis_from_professor_stops_before_specialists():
    plan = dumps(
        {
            "decision": "NO_ANALYSIS",
            "selected_agents": [],
            "rationale": ["incremental information not justified"],
            "request_more_analysis": False,
        }
    )
    pipeline, client, _ = make_pipeline({("professor", "plan"): [plan]})
    result = await pipeline.run(opportunity=make_opportunity(), market_context=make_context())
    assert result.status is PipelineStatus.NO_ANALYSIS
    assert [request.agent_id for request in client.requests] == ["professor"]


@sync_test
async def test_compute_gate_no_analysis_uses_zero_ai_calls_when_budget_insufficient():
    pipeline, client, ledger = make_pipeline({}, budget="0.001")
    result = await pipeline.run(opportunity=make_opportunity(), market_context=make_context())
    assert result.status is PipelineStatus.NO_ANALYSIS
    assert result.compute_gate.reason.value == "BUDGET_INSUFFICIENT"
    assert client.requests == []
    assert ledger.snapshot().spent_eur == 0


@sync_test
async def test_no_trade_is_first_class_and_never_creates_proposal():
    script = nominal_script(
        plan=dumps(
            {
                "decision": "MINI_CREW",
                "selected_agents": ["berlin"],
                "rationale": [],
                "request_more_analysis": False,
            }
        ),
        final=final_no_trade(),
    )
    script.pop(("tokyo", "specialist_independent_round_1"))
    script.pop(("nairobi", "specialist_independent_round_1"))
    pipeline, _, _ = make_pipeline(script)
    result = await pipeline.run(opportunity=make_opportunity(), market_context=make_context())
    assert result.status is PipelineStatus.NO_TRADE
    assert result.trade_proposal is None
    assert result.professor_decision.direction == "NO_TRADE"


@sync_test
async def test_professor_specialist_selection_is_respected():
    plan = dumps(
        {
            "decision": "MINI_CREW",
            "selected_agents": ["berlin", "nairobi"],
            "rationale": ["trend plus structure"],
            "request_more_analysis": False,
        }
    )
    script = nominal_script(plan=plan)
    script.pop(("tokyo", "specialist_independent_round_1"))
    pipeline, client, _ = make_pipeline(script)
    result = await pipeline.run(opportunity=make_opportunity(), market_context=make_context())
    assert result.status is PipelineStatus.TRADE_PROPOSAL
    assert [run.agent_id for run in result.specialist_runs] == ["berlin", "nairobi"]
    assert all(request.agent_id != "tokyo" for request in client.requests)


@sync_test
async def test_independent_round_has_no_cross_specialist_contamination_and_palermo_runs_after():
    pipeline, client, _ = make_pipeline(nominal_script())
    result = await pipeline.run(opportunity=make_opportunity(), market_context=make_context())
    assert result.status is PipelineStatus.TRADE_PROPOSAL

    specialist_requests = [
        request
        for request in client.requests
        if request.metadata["phase"] == "specialist_independent_round_1"
    ]
    assert len(specialist_requests) == 3
    forbidden = (
        "specialist_analyses",
        "other_agent_analysis",
        "agent_conclusions",
        "crew_consensus",
        "palermo_review",
        "professor_decision",
        "provisional_thesis",
    )
    for request in specialist_requests:
        payload = json.loads(request.input_text)
        assert payload["analysis_round"] == "INDEPENDENT_1"
        assert all(key not in request.input_text for key in forbidden)
        assert payload["market_context"]["snapshot_id"] == "snapshot-1"

    palermo_index = next(
        index
        for index, request in enumerate(client.requests)
        if request.agent_id == "palermo"
    )
    specialist_indexes = [client.requests.index(request) for request in specialist_requests]
    assert max(specialist_indexes) < palermo_index
    palermo_payload = json.loads(client.requests[palermo_index].input_text)
    assert len(palermo_payload["specialist_analyses"]) == 3


@sync_test
async def test_invalid_specialist_output_fails_closed_before_palermo():
    plan = dumps(
        {
            "decision": "MINI_CREW",
            "selected_agents": ["tokyo"],
            "rationale": [],
            "request_more_analysis": False,
        }
    )
    pipeline, client, _ = make_pipeline(
        {
            ("professor", "plan"): [plan],
            ("tokyo", "specialist_independent_round_1"): ["{}"],
        }
    )
    result = await pipeline.run(opportunity=make_opportunity(), market_context=make_context())
    assert result.status is PipelineStatus.FAILED
    assert result.failure.code is PipelineFailureCode.INVALID_SPECIALIST_OUTPUT
    assert result.trade_proposal is None
    assert all(request.agent_id != "palermo" for request in client.requests)


@sync_test
async def test_invalid_professor_final_output_fails_closed():
    pipeline, client, _ = make_pipeline(nominal_script(final="{}"))
    result = await pipeline.run(opportunity=make_opportunity(), market_context=make_context())
    assert result.status is PipelineStatus.FAILED
    assert result.failure.code is PipelineFailureCode.INVALID_PROFESSOR_OUTPUT
    assert result.trade_proposal is None
    assert any(request.agent_id == "palermo" for request in client.requests)


@sync_test
async def test_missing_or_unavailable_evidence_cannot_be_invented():
    plan = dumps(
        {
            "decision": "MINI_CREW",
            "selected_agents": ["berlin"],
            "rationale": [],
            "request_more_analysis": False,
        }
    )
    pipeline, _, _ = make_pipeline(
        {
            ("professor", "plan"): [plan],
            ("berlin", "specialist_independent_round_1"): [
                berlin(source_key="market_context.open_interest")
            ],
        }
    )
    result = await pipeline.run(opportunity=make_opportunity(), market_context=make_context())
    assert result.status is PipelineStatus.FAILED
    # v3 rejects a non-allowed specialist path at provider schema validation,
    # before the legacy post-provider grounding validator can run.
    assert result.failure.code is PipelineFailureCode.INVALID_SPECIALIST_OUTPUT
    assert result.trade_proposal is None


@sync_test
async def test_none_market_field_is_omitted_and_cannot_be_cited_as_evidence():
    plan = dumps(
        {
            "decision": "MINI_CREW",
            "selected_agents": ["tokyo"],
            "rationale": [],
            "request_more_analysis": False,
        }
    )
    pipeline, client, _ = make_pipeline(
        {
            ("professor", "plan"): [plan],
            ("tokyo", "specialist_independent_round_1"): [tokyo()],
        }
    )
    result = await pipeline.run(
        opportunity=make_opportunity(),
        market_context=make_context(rsi=None),
    )
    specialist_request = next(request for request in client.requests if request.agent_id == "tokyo")
    assert "rsi_14" not in json.loads(specialist_request.input_text)["market_context"]
    assert result.status is PipelineStatus.FAILED
    assert result.failure.code is PipelineFailureCode.INVALID_SPECIALIST_OUTPUT


@sync_test
async def test_professor_cannot_select_unknown_specialist_or_exceed_compute_gate():
    unknown_plan = dumps(
        {
            "decision": "MINI_CREW",
            "selected_agents": ["rio"],
            "rationale": [],
            "request_more_analysis": False,
        }
    )
    pipeline, client, _ = make_pipeline({("professor", "plan"): [unknown_plan]})
    result = await pipeline.run(opportunity=make_opportunity(), market_context=make_context())
    assert result.status is PipelineStatus.FAILED
    assert result.failure.code is PipelineFailureCode.INVALID_PROFESSOR_PLAN
    assert [request.agent_id for request in client.requests] == ["professor"]

    policy = ComputeGatePolicy(
        full_crew_priority_score=70,
        minimum_analysis_budget_eur=Decimal("0.001"),
        full_crew_budget_eur=Decimal("0.50"),
    )
    full_plan = dumps(
        {
            "decision": "FULL_CREW",
            "selected_agents": ["berlin", "tokyo", "nairobi"],
            "rationale": [],
            "request_more_analysis": False,
        }
    )
    pipeline2, client2, _ = make_pipeline(
        {("professor", "plan"): [full_plan]},
        budget="0.10",
        gate_policy=policy,
    )
    result2 = await pipeline2.run(opportunity=make_opportunity(), market_context=make_context())
    assert result2.compute_gate.level.value == "LEVEL_2_MINI_CREW"

    plan_request = next(
        request
        for request in client2.requests
        if request.agent_id == "professor" and request.metadata["phase"] == "plan"
    )
    planning_constraints = json.loads(plan_request.input_text)["planning_constraints"]
    assert planning_constraints == {
        "allowed_decisions": ["NO_ANALYSIS", "MINI_CREW"],
        "compute_gate_level": "LEVEL_2_MINI_CREW",
        "full_crew_allowed": False,
        "max_specialists": 2,
    }

    # The deterministic fail-closed validator remains authoritative even if a provider ignores
    # the explicit gate constraints and still returns FULL_CREW.
    assert result2.status is PipelineStatus.FAILED
    assert result2.failure.code is PipelineFailureCode.INVALID_PROFESSOR_PLAN


@sync_test
async def test_hard_gateway_budget_cannot_be_bypassed_after_gate():
    policy = ComputeGatePolicy(
        minimum_analysis_budget_eur=Decimal("0.0001"),
        full_crew_budget_eur=Decimal("0.0001"),
    )
    plan = dumps(
        {
            "decision": "MINI_CREW",
            "selected_agents": ["berlin"],
            "rationale": [],
            "request_more_analysis": False,
        }
    )
    pipeline, client, ledger = make_pipeline(
        {("professor", "plan"): [plan]},
        budget="0.001",
        gate_policy=policy,
    )
    result = await pipeline.run(opportunity=make_opportunity(), market_context=make_context())
    assert result.compute_gate.allows_ai is True
    assert result.status is PipelineStatus.FAILED
    assert result.failure.code is PipelineFailureCode.BUDGET_EXHAUSTED
    assert result.trade_proposal is None
    assert client.requests == []
    assert ledger.snapshot().spent_eur == 0


@sync_test
async def test_snapshot_mismatch_fails_before_compute_or_ai():
    context = make_context().model_copy(update={"snapshot_id": "other-snapshot"})
    pipeline, client, _ = make_pipeline({})
    result = await pipeline.run(opportunity=make_opportunity(), market_context=context)
    assert result.status is PipelineStatus.FAILED
    assert result.failure.code is PipelineFailureCode.INVALID_CONTEXT
    assert result.compute_gate is None
    assert client.requests == []


@sync_test
async def test_specialists_are_scheduled_concurrently_not_serially():
    pipeline, client, _ = make_pipeline(
        nominal_script(),
        client_cls=BarrierScriptedClient,
    )
    result = await asyncio.wait_for(
        pipeline.run(opportunity=make_opportunity(), market_context=make_context()),
        timeout=1.0,
    )
    assert result.status is PipelineStatus.TRADE_PROPOSAL
    assert client.specialists_entered == 3


@sync_test
async def test_invalid_palermo_output_fails_closed_before_final_professor():
    script = nominal_script()
    script[("palermo", "red_team")] = ["{}"]
    pipeline, client, _ = make_pipeline(script)
    result = await pipeline.run(opportunity=make_opportunity(), market_context=make_context())
    assert result.status is PipelineStatus.FAILED
    assert result.failure.code is PipelineFailureCode.INVALID_PALERMO_OUTPUT
    assert result.trade_proposal is None
    assert not any(
        request.agent_id == "professor" and request.metadata["phase"] == "finalize"
        for request in client.requests
    )


@sync_test
async def test_professor_final_evidence_must_reference_supplied_context():
    invalid_final = dumps(
        {
            "direction": "LONG",
            "confidence": 0.72,
            "thesis": ["unsupported derivatives claim"],
            "counter_evidence": [],
            "invalidation": ["price below 95"],
            "evidence": [
                {
                    "source_key": "market_context.open_interest",
                    "observation": "not actually supplied",
                }
            ],
            "trade": {
                "entry_price": "100",
                "stop_price": "95",
                "targets": ["110"],
                "expected_rr": "2.0",
            },
        }
    )
    pipeline, _, _ = make_pipeline(nominal_script(final=invalid_final))
    result = await pipeline.run(opportunity=make_opportunity(), market_context=make_context())
    assert result.status is PipelineStatus.FAILED
    assert result.failure.code is PipelineFailureCode.INVALID_PROFESSOR_OUTPUT
    assert result.trade_proposal is None


def _decision_context_for_market(market_context):
    from app.market.features.multitimeframe import MultiTimeframeFeatureContext
    from app.services.decision_context import build_decision_context

    mtf = MultiTimeframeFeatureContext(
        symbol=market_context.symbol,
        observed_at=market_context.observed_at,
        decision_timeframe=market_context.timeframe,
        feature_version=market_context.feature_version,
        context_version="mtf-feature-context-v1",
        source_cursor_fingerprint="a" * 64,
        requested_timeframes=(market_context.timeframe,),
        snapshots={market_context.timeframe: market_context},
        missing_timeframes=(),
        warmup_incomplete_timeframes=(),
        context_fingerprint="b" * 64,
    )
    return build_decision_context(
        system_id="balanced_v1",
        as_of=market_context.observed_at,
        primary_timeframe=market_context.timeframe,
        timeframe_policy_version="mtf-utc-closed-v1",
        market=mtf,
    )


@sync_test
async def test_frozen_decision_context_is_identical_across_full_crew_requests():
    from app.services.decision_context import (
        AGENT_CONTEXT_BINDING_VERSION,
        decision_context_payload,
    )

    script = nominal_script()
    script[("berlin", "specialist_independent_round_1")] = [
        berlin(
            source_key=(
                "market_context.decision_context.market."
                "snapshots.1m.regime"
            )
        )
    ]
    pipeline, client, _ = make_pipeline(script)
    market_context = make_context()
    decision_context = _decision_context_for_market(market_context)
    expected = decision_context_payload(decision_context)

    result = await pipeline.run(
        opportunity=make_opportunity(),
        market_context=market_context,
        decision_context=decision_context,
    )

    assert result.status is PipelineStatus.TRADE_PROPOSAL
    assert len(client.requests) == 6
    phases = [
        (request.agent_id, request.metadata["phase"])
        for request in client.requests
    ]
    assert ("professor", "plan") in phases
    assert ("berlin", "specialist_independent_round_1") in phases
    assert ("tokyo", "specialist_independent_round_1") in phases
    assert ("nairobi", "specialist_independent_round_1") in phases
    assert ("palermo", "red_team") in phases
    assert ("professor", "finalize") in phases

    for request in client.requests:
        payload = json.loads(request.input_text)
        supplied = payload["market_context"]["decision_context"]
        assert supplied == expected
        assert supplied["context_id"] == decision_context.context_id
        assert supplied["context_fingerprint"] == decision_context.context_fingerprint
        assert request.metadata["decision_context_id"] == decision_context.context_id
        assert (
            request.metadata["decision_context_fingerprint"]
            == decision_context.context_fingerprint
        )
        assert (
            request.metadata["decision_context_binding_version"]
            == AGENT_CONTEXT_BINDING_VERSION
        )


@sync_test
async def test_incoherent_decision_context_fails_before_any_ai_call():
    from app.services.decision_context import build_decision_context

    market_context = make_context()
    decision_context = _decision_context_for_market(market_context)
    incompatible = build_decision_context(
        system_id="other_system",
        as_of=market_context.observed_at,
        primary_timeframe=market_context.timeframe,
        timeframe_policy_version="mtf-utc-closed-v1",
        market=decision_context.market,
    )

    pipeline, client, _ = make_pipeline(nominal_script())
    result = await pipeline.run(
        opportunity=make_opportunity(),
        market_context=market_context,
        decision_context=incompatible,
    )

    assert result.status is PipelineStatus.FAILED
    assert result.failure.code is PipelineFailureCode.INVALID_CONTEXT
    assert client.requests == []
