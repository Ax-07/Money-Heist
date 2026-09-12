import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agents import (
    Denver,
    DenverAnalysis,
    DenverContext,
    EvidenceReference,
    Rio,
    RioAnalysis,
    RioContext,
    SpecialistContextMismatchError,
    SpecialistContextUnavailableError,
    UngroundedEvidenceError,
)
from app.intelligence.ai_gateway.models import AIGatewayResult, AIUsageRecord


class FakeGateway:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []

    async def generate_structured(self, request, output_model):
        self.requests.append(request)
        output = self.outputs.pop(0)
        assert isinstance(output, output_model) or issubclass(
            output_model,
            type(output),
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
            output=output,
            usage=usage,
            attempts=1,
        )


def rio_context(**updates):
    values = {
        "source": "derivatives-fixture",
        "instrument": "BTC-PERP",
        "observed_at": datetime(2026, 1, 1, tzinfo=UTC),
        "is_stale": False,
        "data_quality": "RELIABLE",
        "funding_rate": 0.0001,
        "open_interest": 1_000_000.0,
        "open_interest_change_pct": 3.5,
        "long_liquidations_notional": 10_000.0,
        "short_liquidations_notional": 35_000.0,
        "long_short_ratio": 1.2,
        "missing_fields": (),
    }
    values.update(updates)
    return RioContext(**values)


def denver_context(**updates):
    values = {
        "stats_id": "setup-stats-1",
        "setup_definition_version": "range-break-v1",
        "as_of": datetime(2026, 1, 1, tzinfo=UTC),
        "source_run_ids": ("run-design-1", "run-validation-1", "run-oos-1"),
        "source_dataset_ids": ("dataset-1",),
        "sample_count": 120,
        "oos_sample_count": 30,
        "win_rate": 0.58,
        "expectancy": 1.25,
        "profit_factor": 1.45,
        "max_drawdown_pct": 0.08,
        "regime": "bullish_trend",
        "notes": ("statistics computed outside the LLM",),
    }
    values.update(updates)
    if "sample_count" in updates and "oos_sample_count" not in updates:
        values["oos_sample_count"] = min(values["oos_sample_count"], values["sample_count"])
    return DenverContext(**values)


def rio_output(**updates):
    values = {
        "agent": "rio",
        "stance": "NEUTRAL",
        "confidence": 0.62,
        "evidence": [
            EvidenceReference(
                source_key="specialist_context.funding_rate",
                observation="funding input is explicitly supplied",
            )
        ],
        "risks": ["crowding can reverse"],
        "invalidation": ["positioning normalizes"],
        "data_gaps": [],
        "positioning_regime": "MIXED",
        "funding_state": "POSITIVE",
        "open_interest_state": "RISING",
        "liquidation_state": "SHORT_DOMINATED",
        "squeeze_risk": "SHORT_SQUEEZE",
        "data_quality": "RELIABLE",
    }
    values.update(updates)
    return RioAnalysis(**values)


def denver_output(**updates):
    values = {
        "agent": "denver",
        "stance": "LONG",
        "confidence": 0.67,
        "evidence": [
            EvidenceReference(
                source_key="specialist_context.expectancy",
                observation="positive expectancy is supplied by deterministic statistics",
            ),
            EvidenceReference(
                source_key="specialist_context.oos_sample_count",
                observation="out-of-sample sample count is explicitly supplied",
            ),
        ],
        "risks": ["historical edge may decay"],
        "invalidation": ["new OOS evidence becomes materially negative"],
        "data_gaps": [],
        "source_stats_id": "setup-stats-1",
        "historical_edge": "POSITIVE",
        "sample_size_band": "LARGE",
        "robustness": "MIXED",
        "oos_consistency": "CONSISTENT",
    }
    values.update(updates)
    return DenverAnalysis(**values)


def test_advanced_context_models_are_strict_and_derive_sample_band():
    assert rio_context().usable is True
    empty_stats = denver_context(
        sample_count=0,
        win_rate=None,
        expectancy=None,
        profit_factor=None,
        max_drawdown_pct=None,
    )
    assert empty_stats.usable is False
    assert denver_context(sample_count=29).sample_size_band == "SMALL"
    assert denver_context(sample_count=30).sample_size_band == "MEDIUM"
    assert denver_context(sample_count=100).sample_size_band == "LARGE"

    with pytest.raises(ValidationError):
        DenverContext.model_validate(
            {
                **denver_context().model_dump(mode="json"),
                "invented_probability": 0.99,
            }
        )


def test_rio_requires_usable_derivatives_context_before_ai_call():
    async def scenario():
        gateway = FakeGateway([])
        with pytest.raises(SpecialistContextUnavailableError):
            await Rio(gateway).analyze(
                system_id="balanced_v1",
                opportunity={"symbol": "BTCUSDT"},
                market_context={"close": 100.0},
                specialist_context=None,
            )
        assert gateway.requests == []

        stale = rio_context(is_stale=True, data_quality="DEGRADED")
        with pytest.raises(SpecialistContextUnavailableError):
            await Rio(gateway).analyze(
                system_id="balanced_v1",
                opportunity={"symbol": "BTCUSDT"},
                market_context={"close": 100.0},
                specialist_context=stale,
            )
        assert gateway.requests == []

    asyncio.run(scenario())


def test_rio_evidence_is_grounded_in_derivatives_context():
    async def scenario():
        gateway = FakeGateway([rio_output()])
        result = await Rio(gateway).analyze(
            system_id="balanced_v1",
            opportunity={"symbol": "BTCUSDT"},
            market_context={"close": 100.0},
            specialist_context=rio_context(),
        )
        payload = json.loads(gateway.requests[0].input_text)
        assert payload["specialist_context"]["funding_rate"] == 0.0001
        assert result.output.data_quality == "RELIABLE"

        bad = rio_output(
            evidence=[
                EvidenceReference(
                    source_key="specialist_context.social_sentiment",
                    observation="not supplied",
                )
            ]
        )
        gateway2 = FakeGateway([bad])
        with pytest.raises(UngroundedEvidenceError):
            await Rio(gateway2).analyze(
                system_id="balanced_v1",
                opportunity={"symbol": "BTCUSDT"},
                market_context={"close": 100.0},
                specialist_context=rio_context(),
            )

    asyncio.run(scenario())


def test_rio_cannot_upgrade_context_data_quality():
    async def scenario():
        gateway = FakeGateway([rio_output(data_quality="RELIABLE")])
        with pytest.raises(SpecialistContextMismatchError):
            await Rio(gateway).analyze(
                system_id="balanced_v1",
                opportunity={"symbol": "BTCUSDT"},
                market_context={"close": 100.0},
                specialist_context=rio_context(data_quality="DEGRADED"),
            )

    asyncio.run(scenario())


def test_denver_uses_only_precomputed_stats_and_keeps_provenance():
    async def scenario():
        gateway = FakeGateway([denver_output()])
        result = await Denver(gateway).analyze(
            system_id="balanced_v1",
            opportunity={"symbol": "BTCUSDT"},
            market_context={"close": 100.0},
            specialist_context=denver_context(),
        )
        payload = json.loads(gateway.requests[0].input_text)
        assert payload["specialist_context"]["stats_id"] == "setup-stats-1"
        assert payload["specialist_context"]["sample_count"] == 120
        assert result.output.source_stats_id == "setup-stats-1"

    asyncio.run(scenario())


def test_denver_rejects_invented_stats_reference_and_provenance_mismatch():
    async def scenario():
        invented = denver_output(
            evidence=[
                EvidenceReference(
                    source_key="specialist_context.sharpe_ratio",
                    observation="not supplied",
                )
            ]
        )
        gateway = FakeGateway([invented])
        with pytest.raises(UngroundedEvidenceError):
            await Denver(gateway).analyze(
                system_id="balanced_v1",
                opportunity={"symbol": "BTCUSDT"},
                market_context={"close": 100.0},
                specialist_context=denver_context(),
            )

        wrong_id = denver_output(source_stats_id="made-up-stats")
        gateway2 = FakeGateway([wrong_id])
        with pytest.raises(SpecialistContextMismatchError):
            await Denver(gateway2).analyze(
                system_id="balanced_v1",
                opportunity={"symbol": "BTCUSDT"},
                market_context={"close": 100.0},
                specialist_context=denver_context(),
            )

        wrong_band = denver_output(sample_size_band="SMALL")
        gateway3 = FakeGateway([wrong_band])
        with pytest.raises(SpecialistContextMismatchError):
            await Denver(gateway3).analyze(
                system_id="balanced_v1",
                opportunity={"symbol": "BTCUSDT"},
                market_context={"close": 100.0},
                specialist_context=denver_context(),
            )

    asyncio.run(scenario())
