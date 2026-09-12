import asyncio
import json
from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents import CORE_AGENT_REGISTRY, CORE_PROMPTS, Lisbon, Palermo, TheProfessor
from app.agents.models import LisbonReport, PalermoReview, ProfessorDecision, ProfessorPlan
from app.intelligence.ai_gateway.models import AIGatewayResult, AIUsageRecord


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


def test_professor_plan_and_finalize_are_structured_and_versioned():
    async def scenario():
        gateway = FakeGateway(
            [
                ProfessorPlan(decision="MINI_CREW", selected_agents=["berlin"]),
                ProfessorDecision(
                    direction="NO_TRADE",
                    confidence=0.8,
                    thesis=["mixed evidence"],
                ),
            ]
        )
        professor = TheProfessor(gateway)
        opportunity_id = uuid4()

        plan = await professor.plan(
            system_id="balanced_v1",
            opportunity={"symbol": "BTCUSDT"},
            market_context={"regime": "range"},
            available_agents=["berlin"],
            remaining_budget_eur=1.2,
            planning_constraints={
                "compute_gate_level": "LEVEL_2_MINI_CREW",
                "allowed_decisions": ["NO_ANALYSIS", "MINI_CREW"],
                "max_specialists": 1,
                "full_crew_allowed": False,
            },
            opportunity_id=opportunity_id,
        )
        final = await professor.finalize(
            system_id="balanced_v1",
            opportunity={"symbol": "BTCUSDT"},
            market_context={},
            specialist_analyses=[],
            palermo_review={"verdict": "CAUTION"},
            opportunity_id=opportunity_id,
        )

        assert plan.output.decision == "MINI_CREW"
        assert final.output.direction == "NO_TRADE"
        assert [request.prompt_version for request in gateway.requests] == ["v4", "v4"]
        assert all(request.agent_id == "professor" for request in gateway.requests)
        assert gateway.requests[0].opportunity_id == opportunity_id
        plan_payload = json.loads(gateway.requests[0].input_text)
        assert plan_payload["planning_constraints"]["compute_gate_level"] == "LEVEL_2_MINI_CREW"
        assert plan_payload["planning_constraints"]["allowed_decisions"] == [
            "NO_ANALYSIS",
            "MINI_CREW",
        ]
        assert plan_payload["planning_constraints"]["max_specialists"] == 1
        assert plan_payload["planning_constraints"]["full_crew_allowed"] is False

        final_payload = json.loads(gateway.requests[1].input_text)
        allowed = final_payload["allowed_evidence_source_keys"]
        assert allowed == sorted(allowed)
        assert "opportunity.symbol" in allowed
        assert "palermo_review.verdict" in allowed
        assert "allowed_evidence_source_keys" not in allowed

    asyncio.run(scenario())


def test_professor_finalize_allowed_paths_use_real_top_level_namespaces():
    async def scenario():
        gateway = FakeGateway(
            [
                ProfessorDecision(
                    direction="NO_TRADE",
                    confidence=0.75,
                    thesis=["grounded"],
                )
            ]
        )
        professor = TheProfessor(gateway)

        await professor.finalize(
            system_id="balanced_v1",
            opportunity={"symbol": "BTCUSDT", "triggers": ["RANGE_BREAK"]},
            market_context={
                "decision_context": {
                    "market": {
                        "snapshots": {
                            "1h": {"rsi_14": 61.0},
                            "4h": {"close": 101.0},
                        }
                    }
                }
            },
            specialist_analyses=[
                {
                    "agent": "berlin",
                    "stance": "LONG",
                    "evidence": [
                        {
                            "source_key": "market_context.decision_context.market.snapshots.1h.rsi_14",
                            "observation": "positive",
                        }
                    ],
                }
            ],
            palermo_review={
                "verdict": "CAUTION",
                "critical_objections": ["extension"],
            },
        )

        payload = json.loads(gateway.requests[0].input_text)
        allowed = payload["allowed_evidence_source_keys"]

        assert "market_context.decision_context.market.snapshots.1h.rsi_14" in allowed
        assert "specialist_analyses.0.stance" in allowed
        assert "specialist_analyses.0.evidence.0.source_key" in allowed
        assert "palermo_review.verdict" in allowed
        assert "palermo_review.critical_objections.0" in allowed

        # Regress the LIVE_EVAL failure mode observed before Batch 16.21u.
        assert "market_context.specialist_analyses.0.stance" not in allowed
        assert "market_context.palermo_review.verdict" not in allowed
        assert "specialist_analyses[0].stance" not in allowed
        assert "$.palermo_review.verdict" not in allowed
        assert "allowed_evidence_source_keys" not in allowed

    asyncio.run(scenario())


def test_palermo_and_lisbon_use_gateway_without_privileged_tools():
    async def scenario():
        gateway = FakeGateway(
            [
                PalermoReview(
                    verdict="REJECT",
                    severity=0.9,
                    critical_objections=["stale data"],
                ),
                LisbonReport(
                    total_ai_cost_eur=0.4,
                    cost_per_decision_eur=0.2,
                    additional_analysis_justified=False,
                ),
            ]
        )

        review = await Palermo(gateway).review(
            system_id="balanced_v1",
            market_context={},
            specialist_analyses=[],
            provisional_thesis={"direction": "LONG"},
            opportunity={"symbol": "BTCUSDT", "timeframe": "1h"},
        )
        report = await Lisbon(gateway).assess(
            system_id="balanced_v1",
            ai_metrics={"cost": 0.4},
            agent_metrics=[],
        )

        assert review.output.verdict == "REJECT"
        assert report.output.additional_analysis_justified is False
        assert all(
            CORE_AGENT_REGISTRY.get(request.agent_id).allowed_tools == ()
            for request in gateway.requests
        )

    asyncio.run(scenario())


def test_registry_core_roles_and_prompt_versions_are_safe():
    agent_ids = {entry.agent_id for entry in CORE_AGENT_REGISTRY.list()}
    assert agent_ids == {"professor", "palermo", "lisbon"}
    assert CORE_AGENT_REGISTRY.get("professor").state.value == "ACTIVE"
    assert CORE_AGENT_REGISTRY.get("palermo").state.value == "ACTIVE"

    expected_versions = {"professor": "v4", "palermo": "v3", "lisbon": "v1"}
    for entry in CORE_AGENT_REGISTRY.list():
        assert entry.core is True
        assert entry.allowed_tools == ()
        assert entry.prompt_version == expected_versions[entry.agent_id]
        assert CORE_PROMPTS.get(entry.agent_id, entry.prompt_version).version == entry.prompt_version


def test_prompt_registry_rejects_unknown_version():
    with pytest.raises(KeyError):
        CORE_PROMPTS.get("professor", "v999")


def test_decision_contract_v2_is_versioned_and_preserves_v1():
    assert CORE_PROMPTS.versions("professor") == ("v1", "v2", "v3", "v4")
    assert CORE_PROMPTS.versions("palermo") == ("v1", "v2", "v3")

    # Historical prompt versions remain immutable and addressable.
    assert CORE_PROMPTS.get("professor", "v3").version == "v3"
    assert CORE_PROMPTS.get("palermo", "v2").version == "v2"

    professor = CORE_PROMPTS.get("professor", "v4").instructions
    palermo = CORE_PROMPTS.get("palermo", "v3").instructions

    assert "planning_constraints" in professor
    assert "allowed_decisions" in professor
    assert "max_specialists" in professor
    assert "full_crew_allowed" in professor
    assert "future candles" in professor
    assert "entry_price" in professor
    assert "deterministic Risk Engine" in professor
    assert "allowed_evidence_source_keys" in professor
    assert "specialist_analyses and palermo_review are top-level" in professor
    assert "common decision as-of time" in professor
    assert "may legitimately differ" in professor
    assert "no trade" in professor.lower()

    assert "future candle" in palermo
    assert "Do not require entry" in palermo
    assert "optional missing context" in palermo
    assert "deterministic Risk Engine" in palermo
    assert "common decision as-of time" in palermo
    assert "may legitimately differ" in palermo
    assert "do not demand synchronized closes" in palermo.lower()


def test_palermo_payload_can_include_current_opportunity():
    async def scenario():
        gateway = FakeGateway([PalermoReview(verdict="CAUTION", severity=0.4)])
        await Palermo(gateway).review(
            system_id="balanced_v1",
            market_context={"regime": "range"},
            specialist_analyses=[],
            provisional_thesis={"direction": "LONG"},
            opportunity={"symbol": "BTCUSDT", "timeframe": "1h", "priority_score": 61},
        )
        payload = json.loads(gateway.requests[0].input_text)
        assert payload["opportunity"]["symbol"] == "BTCUSDT"
        assert payload["opportunity"]["priority_score"] == 61
        assert gateway.requests[0].prompt_version == "v3"

    asyncio.run(scenario())


def test_palermo_has_targeted_output_headroom_without_changing_lisbon() -> None:
    async def scenario():
        gateway = FakeGateway(
            [
                PalermoReview(
                    verdict="CAUTION",
                    severity=0.5,
                    critical_objections=["needs confirmation"],
                ),
                LisbonReport(
                    total_ai_cost_eur=0.1,
                    cost_per_decision_eur=0.1,
                    additional_analysis_justified=False,
                ),
            ]
        )

        await Palermo(gateway).review(
            system_id="balanced_v1",
            market_context={},
            specialist_analyses=[],
            provisional_thesis={"direction": "NO_TRADE"},
        )
        await Lisbon(gateway).assess(
            system_id="balanced_v1",
            ai_metrics={"cost": 0.1},
            agent_metrics=[],
        )

        assert gateway.requests[0].agent_id == "palermo"
        assert gateway.requests[0].max_output_tokens == 16384
        assert gateway.requests[0].timeout_seconds == 90.0
        assert gateway.requests[1].agent_id == "lisbon"
        assert gateway.requests[1].max_output_tokens is None
        assert gateway.requests[1].timeout_seconds is None

    asyncio.run(scenario())
