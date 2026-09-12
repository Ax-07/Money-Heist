from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.dashboard.backtest import (
    AIInput,
    DeterministicAgentCoverageMockProvider,
    DeterministicBacktestMockProvider,
)
from app.intelligence.ai_gateway.models import ProviderRequest
from app.services.backtest import BacktestAIMode


def professor_request(available_agents: list[str]) -> ProviderRequest:
    return ProviderRequest(
        request_id=uuid4(),
        system_id="balanced_v1",
        agent_id="professor",
        model_id="mock-backtest-v1",
        input_text=json.dumps(
            {
                "available_agents": available_agents,
                "market_context": {"close": "100"},
            },
            sort_keys=True,
        ),
        schema_name="ProfessorPlan",
        json_schema={},
        max_output_tokens=1200,
        timeout_seconds=5,
    )


def test_agent_coverage_rotates_singles_then_two_agent_crews() -> None:
    async def scenario() -> None:
        provider = DeterministicAgentCoverageMockProvider(
            DeterministicBacktestMockProvider()
        )
        request = professor_request(["tokyo", "berlin", "nairobi"])
        selections = []
        for _ in range(6):
            response = await provider.complete(request)
            selections.append(json.loads(response.output_text)["selected_agents"])

        assert selections == [
            ["berlin"],
            ["nairobi"],
            ["tokyo"],
            ["berlin", "nairobi"],
            ["berlin", "tokyo"],
            ["nairobi", "tokyo"],
        ]

    asyncio.run(scenario())


def test_agent_coverage_never_selects_an_unavailable_specialist() -> None:
    async def scenario() -> None:
        provider = DeterministicAgentCoverageMockProvider(
            DeterministicBacktestMockProvider()
        )
        request = professor_request(["berlin", "tokyo"])
        observed: set[str] = set()
        for _ in range(6):
            response = await provider.complete(request)
            selected = json.loads(response.output_text)["selected_agents"]
            assert 1 <= len(selected) <= 2
            observed.update(selected)
            assert set(selected) <= {"berlin", "tokyo"}

        assert observed == {"berlin", "tokyo"}

    asyncio.run(scenario())


def test_coverage_flag_is_mock_only() -> None:
    assert AIInput(mock_agent_coverage=True).mode is BacktestAIMode.MOCK

    with pytest.raises(ValidationError, match="mock_agent_coverage"):
        AIInput(
            mode=BacktestAIMode.CACHED,
            mock_agent_coverage=True,
        )


def test_quick_test_frontend_enables_coverage_only_for_mock() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    js = (root / "app/dashboard/static/backtest.js").read_text(encoding="utf-8")

    assert "let mockAgentCoverage = false;" in js
    assert "mockAgentCoverage = true;" in js
    assert "mock_agent_coverage:" in js
    assert 'mockAgentCoverage && $("ai-mode").value === "MOCK"' in js
    assert 'if ($("ai-mode").value !== "MOCK") mockAgentCoverage = false;' in js

def test_deterministic_mock_v3_uses_indexed_specialist_evidence() -> None:
    async def scenario() -> None:
        provider = DeterministicBacktestMockProvider()
        request = ProviderRequest(
            request_id=uuid4(),
            system_id="balanced_v1",
            agent_id="berlin",
            model_id="mock-backtest-v1",
            input_text=json.dumps(
                {
                    "allowed_evidence_source_keys": [
                        "market_context",
                        "market_context.close",
                    ],
                    "market_context": {
                        "close": 100.0,
                        "regime": "BULLISH_TREND",
                    },
                },
                sort_keys=True,
            ),
            schema_name="BerlinAnalysis",
            json_schema={},
            max_output_tokens=1200,
            timeout_seconds=5,
            metadata={
                "phase": "specialist_independent_round_1",
                "prompt_version": "v3",
            },
        )

        response = await provider.complete(request)
        payload = json.loads(response.output_text)
        assert payload["evidence"] == [
            {
                "observation": "deterministic MOCK close reference",
                "source_index": 1,
            }
        ]
        assert "source_key" not in response.output_text

    asyncio.run(scenario())

