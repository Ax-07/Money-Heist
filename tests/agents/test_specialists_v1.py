import asyncio
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents import (
    SPECIALIST_AGENT_REGISTRY,
    SPECIALIST_PROMPTS,
    V1_AGENT_REGISTRY,
    Berlin,
    Nairobi,
    SpecialistInputContaminationError,
    Tokyo,
    UngroundedEvidenceError,
)
from app.agents.models import (
    BerlinAnalysis,
    EvidenceReference,
    NairobiAnalysis,
    TokyoAnalysis,
)
from app.intelligence.ai_gateway.models import AIGatewayResult, AIUsageRecord
from app.intelligence.ai_gateway.strict_schema import build_strict_json_schema


class FakeGateway:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []
        self.output_models = []

    async def generate_structured(self, request, output_model):
        self.requests.append(request)
        self.output_models.append(output_model)
        output = self.outputs.pop(0)
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


def _berlin_output(source_key="market_context.features.adx"):
    return BerlinAnalysis(
        agent="berlin",
        stance="LONG",
        confidence=0.72,
        regime="BULLISH_TREND",
        trend_maturity="MATURE",
        multi_timeframe_alignment="BULLISH",
        evidence=[EvidenceReference(source_key=source_key, observation="ADX is elevated")],
        risks=["trend may be mature"],
        invalidation=["trend structure deteriorates"],
        data_gaps=[],
    )


def _tokyo_output():
    return TokyoAnalysis(
        agent="tokyo",
        stance="LONG",
        confidence=0.66,
        momentum="BULLISH",
        momentum_quality="MODERATE",
        breakout_quality="UNCONFIRMED",
        evidence=[
            EvidenceReference(
                source_key="market_context.features.rsi",
                observation="RSI is above its neutral zone",
            )
        ],
        risks=["breakout lacks confirmation"],
        invalidation=["momentum rolls over"],
        data_gaps=[],
    )


def _nairobi_output():
    return NairobiAnalysis(
        agent="nairobi",
        stance="NEUTRAL",
        confidence=0.61,
        market_structure="RANGE",
        liquidity_state="AT_RISK",
        breakout_state="NONE",
        evidence=[
            EvidenceReference(
                source_key="market_context.structure.state",
                observation="structure is range-bound",
            )
        ],
        risks=["liquidity sweep risk near range edge"],
        invalidation=["clean break and retest"],
        data_gaps=[],
    )


@pytest.mark.parametrize(
    ("agent_class", "output", "context", "expected_model"),
    [
        (Berlin, _berlin_output(), {"features": {"adx": 28.0}}, BerlinAnalysis),
        (Tokyo, _tokyo_output(), {"features": {"rsi": 61.0}}, TokyoAnalysis),
        (
            Nairobi,
            _nairobi_output(),
            {"structure": {"state": "range"}},
            NairobiAnalysis,
        ),
    ],
)
def test_specialists_use_versioned_gateway_contract(
    agent_class,
    output,
    context,
    expected_model,
):
    async def scenario():
        gateway = FakeGateway([output])
        opportunity_id = uuid4()
        result = await agent_class(gateway).analyze(
            system_id="balanced_v1",
            opportunity={"symbol": "BTCUSDT", "snapshot_id": "snapshot-1"},
            market_context=context,
            opportunity_id=opportunity_id,
        )

        request = gateway.requests[0]
        assert result.output == output
        assert request.agent_id == output.agent
        assert request.prompt_version == "v4"
        assert request.opportunity_id == opportunity_id
        assert request.metadata["phase"] == "specialist_independent_round_1"
        assert len(gateway.output_models) == 1
        assert issubclass(gateway.output_models[0], expected_model)
        assert gateway.output_models[0] is not expected_model

    asyncio.run(scenario())


class IndexedSchemaGateway:
    """Emulate the real Gateway by validating provider JSON against output_model."""

    def __init__(self, canonical_output):
        self.canonical_output = canonical_output
        self.requests = []
        self.output_models = []
        self.allowed_source_keys = []

    async def generate_structured(self, request, output_model):
        self.requests.append(request)
        self.output_models.append(output_model)

        request_payload = json.loads(request.input_text)
        catalog = request_payload["evidence_source_catalog"]
        self.allowed_source_keys = [
            entry["source_key"]
            for entry in catalog
        ]
        index_by_key = {
            entry["source_key"]: entry["source_index"]
            for entry in catalog
        }

        provider_payload = self.canonical_output.model_dump(mode="python")
        provider_payload["evidence"] = [
            {
                "source_index": index_by_key[item.source_key],
                "observation": item.observation,
            }
            for item in self.canonical_output.evidence
        ]
        output = output_model.model_validate(provider_payload)

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


def _find_schema_property(node, property_name):
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict) and property_name in properties:
            return properties[property_name]
        for value in node.values():
            found = _find_schema_property(value, property_name)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_schema_property(value, property_name)
            if found is not None:
                return found
    return None


def test_v4_strict_schema_bounds_atomic_source_index_and_canonicalizes():
    async def scenario():
        exact_key = "market_context.decision_context.market.snapshots.1h.rsi_14"
        gateway = IndexedSchemaGateway(_berlin_output(exact_key))

        result = await Berlin(gateway).analyze(
            system_id="balanced_v1",
            opportunity={"symbol": "BTCUSDT"},
            market_context={
                "decision_context": {
                    "market": {
                        "snapshots": {
                            "1h": {"rsi_14": 44.0},
                        }
                    },
                    "structure": {
                        "payload": {
                            "timeframes": {
                                "1h": {"breakout_state": "BREAKOUT_UP"},
                            }
                        }
                    },
                }
            },
        )

        assert result.output.__class__ is BerlinAnalysis
        assert result.output.evidence[0].source_key == exact_key

        provider_model = gateway.output_models[0]
        schema = build_strict_json_schema(provider_model)
        source_index_schema = _find_schema_property(schema, "source_index")
        assert source_index_schema is not None
        assert source_index_schema["minimum"] == 0
        assert source_index_schema["maximum"] == len(gateway.allowed_source_keys) - 1
        assert '"source_key"' not in json.dumps(schema, sort_keys=True)

        provider_payload = _berlin_output(exact_key).model_dump(mode="python")
        provider_payload["evidence"] = [
            {
                "source_index": len(gateway.allowed_source_keys),
                "observation": "out of range must fail",
            }
        ]
        with pytest.raises(ValidationError):
            provider_model.model_validate(provider_payload)

    asyncio.run(scenario())


def test_first_round_payload_contains_no_other_agent_conclusions():
    async def scenario():
        gateway = FakeGateway([_berlin_output()])
        await Berlin(gateway).analyze(
            system_id="balanced_v1",
            opportunity={"symbol": "BTCUSDT"},
            market_context={"features": {"adx": 28.0}},
        )

        payload = json.loads(gateway.requests[0].input_text)
        assert payload["analysis_round"] == "INDEPENDENT_1"
        assert set(payload) == {
            "opportunity",
            "market_context",
            "analysis_round",
            "evidence_source_catalog",
        }
        catalog = payload["evidence_source_catalog"]
        assert [entry["source_index"] for entry in catalog] == list(range(len(catalog)))
        assert [entry["source_key"] for entry in catalog] == sorted(
            entry["source_key"] for entry in catalog
        )
        keys = {entry["source_key"] for entry in catalog}
        assert "market_context.features.adx" in keys
        assert "market_context" not in keys
        assert "market_context.features" not in keys
        assert "specialist_analyses" not in gateway.requests[0].input_text
        assert "palermo_review" not in gateway.requests[0].input_text

    asyncio.run(scenario())


def test_contaminated_first_round_input_is_rejected_before_ai_call():
    async def scenario():
        gateway = FakeGateway([])
        with pytest.raises(SpecialistInputContaminationError):
            await Tokyo(gateway).analyze(
                system_id="balanced_v1",
                opportunity={"symbol": "BTCUSDT"},
                market_context={"specialist_analyses": [{"agent": "berlin"}]},
            )
        assert gateway.requests == []

    asyncio.run(scenario())


def test_evidence_must_reference_an_existing_input_field():
    async def scenario():
        gateway = FakeGateway([_berlin_output("market_context.features.nonexistent")])
        with pytest.raises(UngroundedEvidenceError):
            await Berlin(gateway).analyze(
                system_id="balanced_v1",
                opportunity={"symbol": "BTCUSDT"},
                market_context={"features": {"adx": 28.0}},
            )
        assert len(gateway.requests) == 1

    asyncio.run(scenario())


def test_v4_atomic_evidence_contract_exposes_exact_mtf_leaf_paths():
    async def scenario():
        exact_key = "market_context.decision_context.market.snapshots.1h.rsi_14"
        gateway = FakeGateway([_berlin_output(exact_key)])
        result = await Berlin(gateway).analyze(
            system_id="balanced_v1",
            opportunity={
                "symbol": "BTCUSDT",
                "triggers": ["BREAKOUT"],
            },
            market_context={
                "rsi_14": 48.0,
                "decision_context": {
                    "market": {
                        "snapshots": {
                            "1h": {
                                "rsi_14": 44.0,
                            }
                        }
                    },
                    "structure": {
                        "payload": {
                            "timeframes": {
                                "1h": {
                                    "breakout_state": "BREAKOUT_UP",
                                }
                            }
                        }
                    },
                },
            },
        )

        payload = json.loads(gateway.requests[0].input_text)
        catalog = payload["evidence_source_catalog"]
        allowed = {entry["source_key"] for entry in catalog}
        assert exact_key in allowed
        assert (
            "market_context.decision_context.structure.payload."
            "timeframes.1h.breakout_state"
        ) in allowed
        assert "market_context.decision_context.market.snapshots.1h" not in allowed
        assert "market_context.decision_context.market.snapshots" not in allowed
        assert "market_context" not in allowed
        assert "market_context.market.snapshots.1h.rsi_14" not in allowed
        assert "$.market_context.decision_context.market.snapshots.1h.rsi_14" not in allowed
        assert result.output.evidence[0].source_key == exact_key

    asyncio.run(scenario())


def test_v4_grounding_still_fails_closed_on_semantic_path_alias():
    async def scenario():
        gateway = FakeGateway(
            [_berlin_output("market_context.market.snapshots.1h.rsi_14")]
        )
        with pytest.raises(UngroundedEvidenceError):
            await Berlin(gateway).analyze(
                system_id="balanced_v1",
                opportunity={"symbol": "BTCUSDT"},
                market_context={
                    "decision_context": {
                        "market": {
                            "snapshots": {
                                "1h": {
                                    "rsi_14": 44.0,
                                }
                            }
                        }
                    }
                },
            )

        payload = json.loads(gateway.requests[0].input_text)
        allowed = {
            entry["source_key"]
            for entry in payload["evidence_source_catalog"]
        }
        assert (
            "market_context.decision_context.market.snapshots.1h.rsi_14"
            in allowed
        )
        assert "market_context.market.snapshots.1h.rsi_14" not in allowed

    asyncio.run(scenario())


def test_v4_evidence_rejects_container_path_even_when_container_exists():
    async def scenario():
        gateway = FakeGateway([_berlin_output("opportunity.triggers")])
        with pytest.raises(UngroundedEvidenceError):
            await Berlin(gateway).analyze(
                system_id="balanced_v1",
                opportunity={
                    "symbol": "BTCUSDT",
                    "triggers": ["BREAKOUT", "VOLUME_EXPANSION"],
                },
                market_context={"features": {"adx": 28.0}},
            )

        payload = json.loads(gateway.requests[0].input_text)
        keys = {
            entry["source_key"]
            for entry in payload["evidence_source_catalog"]
        }
        assert "opportunity.triggers" not in keys
        assert "opportunity.triggers.0" in keys
        assert "opportunity.triggers.1" in keys

    asyncio.run(scenario())


def test_container_grounding_does_not_allow_missing_sibling_path():
    async def scenario():
        gateway = FakeGateway([_berlin_output("opportunity.nonexistent")])
        with pytest.raises(UngroundedEvidenceError):
            await Berlin(gateway).analyze(
                system_id="balanced_v1",
                opportunity={
                    "symbol": "BTCUSDT",
                    "triggers": ["BREAKOUT"],
                },
                market_context={"features": {"adx": 28.0}},
            )

        assert len(gateway.requests) == 1

    asyncio.run(scenario())


def test_missing_data_can_be_reported_without_fabricated_evidence():
    async def scenario():
        output = TokyoAnalysis(
            agent="tokyo",
            stance="NEUTRAL",
            confidence=0.2,
            momentum="UNKNOWN",
            momentum_quality="UNKNOWN",
            breakout_quality="UNKNOWN",
            evidence=[],
            risks=["insufficient momentum data"],
            invalidation=[],
            data_gaps=["market_context.features.rsi", "market_context.features.macd"],
        )
        gateway = FakeGateway([output])
        result = await Tokyo(gateway).analyze(
            system_id="balanced_v1",
            opportunity={"symbol": "BTCUSDT"},
            market_context={},
        )
        assert result.output.momentum == "UNKNOWN"
        assert result.output.evidence == []
        assert result.output.data_gaps

    asyncio.run(scenario())


def test_specialist_models_are_strict_and_reject_extra_fields():
    with pytest.raises(ValidationError):
        BerlinAnalysis.model_validate(
            {
                **_berlin_output().model_dump(mode="json"),
                "recommended_order": {"side": "BUY"},
            }
        )


def test_specialists_cannot_emit_no_trade_decision():
    payload = _berlin_output().model_dump(mode="json")
    payload["stance"] = "NO_TRADE"
    with pytest.raises(ValidationError):
        BerlinAnalysis.model_validate(payload)


def test_specialist_registry_and_prompts_extend_core_without_privileges():
    specialist_ids = {entry.agent_id for entry in SPECIALIST_AGENT_REGISTRY.list()}
    v1_ids = {entry.agent_id for entry in V1_AGENT_REGISTRY.list()}

    assert specialist_ids == {"berlin", "tokyo", "nairobi", "rio", "denver"}
    assert v1_ids == {
        "professor",
        "palermo",
        "lisbon",
        "berlin",
        "tokyo",
        "nairobi",
        "rio",
        "denver",
    }

    for entry in SPECIALIST_AGENT_REGISTRY.list():
        assert entry.core is False
        assert entry.allowed_tools == ()
        assert entry.model_route == "core_reasoning"
        assert entry.prompt_version == "v4"
        assert SPECIALIST_PROMPTS.get(entry.agent_id, entry.prompt_version).version == "v4"
        # Historical prompt versions remain immutable and addressable.
        assert SPECIALIST_PROMPTS.get(entry.agent_id, "v1").version == "v1"
        assert SPECIALIST_PROMPTS.get(entry.agent_id, "v2").version == "v2"
        assert SPECIALIST_PROMPTS.get(entry.agent_id, "v3").version == "v3"
        instructions = SPECIALIST_PROMPTS.get(
            entry.agent_id,
            entry.prompt_version,
        ).instructions
        assert "evidence_source_catalog" in instructions
        assert "source_index" in instructions
        assert "atomic leaf" in instructions
        assert "MUST NOT emit source_key" in instructions
