import asyncio
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
        assert [request.prompt_version for request in gateway.requests] == ["v1", "v1"]
        assert all(request.agent_id == "professor" for request in gateway.requests)
        assert gateway.requests[0].opportunity_id == opportunity_id

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

    for entry in CORE_AGENT_REGISTRY.list():
        assert entry.core is True
        assert entry.allowed_tools == ()
        assert CORE_PROMPTS.get(entry.agent_id, entry.prompt_version).version == "v1"


def test_prompt_registry_rejects_unknown_version():
    with pytest.raises(KeyError):
        CORE_PROMPTS.get("professor", "v999")


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
        assert gateway.requests[0].max_output_tokens == 8192
        assert gateway.requests[0].timeout_seconds == 90.0
        assert gateway.requests[1].agent_id == "lisbon"
        assert gateway.requests[1].max_output_tokens is None
        assert gateway.requests[1].timeout_seconds is None

    asyncio.run(scenario())
