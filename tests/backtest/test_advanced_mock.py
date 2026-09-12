from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from app.agents.models import DenverAnalysis, RioAnalysis
from app.intelligence.ai_gateway.models import ProviderRequest, ProviderResponse, TokenUsage
from app.services.backtest.advanced_mock import DeterministicAdvancedSpecialistMockProvider


class LegacyMock:
    def __init__(self) -> None:
        self.calls: list[ProviderRequest] = []

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        if request.schema_name == "ProfessorPlan":
            payload = {
                "decision": "MINI_CREW",
                "selected_agents": ["berlin"],
                "rationale": ["legacy deterministic MOCK replay"],
                "request_more_analysis": False,
            }
        else:
            payload = {"legacy_schema": request.schema_name}
        return ProviderResponse(
            provider_request_id=f"legacy-{request.request_id}",
            model_id=request.model_id,
            output_text=json.dumps(payload, separators=(",", ":"), sort_keys=True),
            usage=TokenUsage(input_tokens=0, cached_input_tokens=0, output_tokens=0),
            latency_ms=0,
        )


def provider_request(schema: str, payload: dict) -> ProviderRequest:
    return ProviderRequest(
        request_id=uuid4(),
        system_id="balanced_v1",
        agent_id=(
            "professor"
            if schema == "ProfessorPlan"
            else schema.removesuffix("Analysis").lower()
        ),
        model_id="mock-backtest-v1",
        input_text=json.dumps(payload, sort_keys=True),
        schema_name=schema,
        json_schema={},
        max_output_tokens=1200,
        timeout_seconds=5,
    )


def test_legacy_professor_plan_is_byte_identical_without_advanced_agents() -> None:
    async def scenario() -> None:
        fallback = LegacyMock()
        advanced = DeterministicAdvancedSpecialistMockProvider(fallback)
        request = provider_request(
            "ProfessorPlan",
            {"available_agents": ["berlin", "nairobi", "tokyo"]},
        )
        baseline = await fallback.complete(request)
        wrapped = await advanced.complete(request)
        assert wrapped.output_text == baseline.output_text
        assert wrapped.provider_request_id == baseline.provider_request_id

    asyncio.run(scenario())


def test_professor_adds_denver_only_when_denver_is_available() -> None:
    async def scenario() -> None:
        advanced = DeterministicAdvancedSpecialistMockProvider(LegacyMock())
        response = await advanced.complete(
            provider_request(
                "ProfessorPlan",
                {"available_agents": ["berlin", "denver", "nairobi", "tokyo"]},
            )
        )
        payload = json.loads(response.output_text)
        assert payload["decision"] == "MINI_CREW"
        assert payload["selected_agents"] == ["berlin", "denver"]

    asyncio.run(scenario())


def test_denver_mock_output_is_grounded_in_deterministic_stats() -> None:
    async def scenario() -> None:
        advanced = DeterministicAdvancedSpecialistMockProvider(LegacyMock())
        response = await advanced.complete(
            provider_request(
                "DenverAnalysis",
                {
                    "specialist_context": {
                        "stats_id": "stats-1",
                        "sample_count": 42,
                        "sample_size_band": "MEDIUM",
                        "expectancy": 1.25,
                    }
                },
            )
        )
        analysis = DenverAnalysis.model_validate_json(response.output_text)
        assert analysis.agent == "denver"
        assert analysis.stance.value == "NEUTRAL"
        assert analysis.historical_edge == "POSITIVE"
        assert analysis.sample_size_band == "MEDIUM"
        assert analysis.source_stats_id == "stats-1"
        assert {item.source_key for item in analysis.evidence} == {
            "specialist_context.expectancy",
            "specialist_context.sample_count",
        }

    asyncio.run(scenario())


def test_denver_mock_never_invents_directional_edge() -> None:
    async def scenario() -> None:
        advanced = DeterministicAdvancedSpecialistMockProvider(LegacyMock())
        response = await advanced.complete(
            provider_request(
                "DenverAnalysis",
                {
                    "specialist_context": {
                        "stats_id": "stats-negative",
                        "sample_count": 120,
                        "sample_size_band": "LARGE",
                        "expectancy": -0.5,
                    }
                },
            )
        )
        analysis = DenverAnalysis.model_validate_json(response.output_text)
        assert analysis.stance.value == "NEUTRAL"
        assert analysis.historical_edge == "NEGATIVE"
        assert analysis.robustness == "MIXED"
        assert analysis.oos_consistency == "UNAVAILABLE"

    asyncio.run(scenario())


def test_rio_mock_support_is_grounded_but_non_directional() -> None:
    async def scenario() -> None:
        advanced = DeterministicAdvancedSpecialistMockProvider(LegacyMock())
        response = await advanced.complete(
            provider_request(
                "RioAnalysis",
                {
                    "specialist_context": {
                        "funding_rate": 0.0001,
                        "open_interest_change_pct": 2.0,
                        "long_liquidations_notional": 1000.0,
                        "short_liquidations_notional": 250.0,
                        "data_quality": "RELIABLE",
                    }
                },
            )
        )
        analysis = RioAnalysis.model_validate_json(response.output_text)
        assert analysis.agent == "rio"
        assert analysis.stance.value == "NEUTRAL"
        assert analysis.funding_state == "POSITIVE"
        assert analysis.open_interest_state == "RISING"
        assert analysis.liquidation_state == "LONG_DOMINATED"
        assert analysis.data_quality == "RELIABLE"
        assert analysis.evidence[0].source_key == "specialist_context.funding_rate"

    asyncio.run(scenario())

def test_denver_mock_v3_uses_source_indexes_from_allowed_catalogue() -> None:
    async def scenario() -> None:
        advanced = DeterministicAdvancedSpecialistMockProvider(LegacyMock())
        request = provider_request(
            "DenverAnalysis",
            {
                "allowed_evidence_source_keys": [
                    "specialist_context.expectancy",
                    "specialist_context.sample_count",
                ],
                "specialist_context": {
                    "stats_id": "stats-v3",
                    "sample_count": 42,
                    "sample_size_band": "MEDIUM",
                    "expectancy": 1.25,
                },
            },
        ).model_copy(update={"metadata": {"prompt_version": "v3"}})

        response = await advanced.complete(request)
        payload = json.loads(response.output_text)
        assert payload["evidence"] == [
            {
                "observation": "deterministic historical expectancy supplied by Batch 16 stats",
                "source_index": 0,
            },
            {
                "observation": "deterministic historical sample count supplied by Batch 16 stats",
                "source_index": 1,
            },
        ]
        assert "source_key" not in response.output_text

    asyncio.run(scenario())

