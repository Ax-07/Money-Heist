import asyncio
from decimal import Decimal

import pytest
from pydantic import BaseModel

from app.intelligence.ai_gateway import (
    AIBudgetLedger,
    AIGateway,
    AIGatewayRequest,
    BudgetExceededError,
    IncompleteAIProviderError,
    ModelPricing,
    ModelRoute,
    ModelRouter,
    ProviderResponse,
    TokenUsage,
)


def test_budget_reservation_and_settlement():
    ledger = AIBudgetLedger("1.00")
    reservation = ledger.reserve(Decimal("0.40"))
    assert ledger.snapshot().remaining_eur == Decimal("0.60")
    ledger.settle(reservation, Decimal("0.25"))
    snapshot = ledger.snapshot()
    assert snapshot.spent_eur == Decimal("0.25")
    assert snapshot.reserved_eur == Decimal("0")
    assert snapshot.remaining_eur == Decimal("0.75")


def test_budget_release_restores_capacity():
    ledger = AIBudgetLedger("0.50")
    reservation = ledger.reserve(Decimal("0.50"))
    ledger.release(reservation)
    assert ledger.snapshot().remaining_eur == Decimal("0.50")


def test_budget_hard_limit_rejects_overspend():
    ledger = AIBudgetLedger("0.10")
    with pytest.raises(BudgetExceededError):
        ledger.reserve(Decimal("0.100001"))


def test_budget_can_reserve_is_non_mutating():
    ledger = AIBudgetLedger("0.10")
    assert ledger.can_reserve(Decimal("0.05")) is True
    assert ledger.snapshot().reserved_eur == Decimal("0")


class Decision(BaseModel):
    stance: str


class OverspendClient:
    provider_name = "mock"

    def __init__(self) -> None:
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ProviderResponse(
            provider_request_id="overspend",
            model_id=request.model_id,
            output_text='{"stance":"LONG"}',
            usage=TokenUsage(
                input_tokens=1_000_000,
                cached_input_tokens=0,
                output_tokens=0,
            ),
            latency_ms=1,
        )


def test_provider_overspend_is_recorded_and_never_triggers_fallback():
    ledger = AIBudgetLedger("1")
    client = OverspendClient()
    primary = ModelRoute(
        route_id="primary",
        provider="mock",
        model_id="primary-model",
        pricing=ModelPricing(
            input_per_million_eur=Decimal("2"),
            output_per_million_eur=Decimal("0"),
        ),
        max_output_tokens=1,
        fallback_route_id="fallback",
    )
    fallback = ModelRoute(
        route_id="fallback",
        provider="mock",
        model_id="fallback-model",
        pricing=ModelPricing(
            input_per_million_eur=Decimal("0"),
            output_per_million_eur=Decimal("0"),
        ),
        max_output_tokens=1,
    )
    gateway = AIGateway(
        router=ModelRouter([primary, fallback]),
        clients={"mock": client},
        budget=ledger,
        max_attempts=1,
        retry_backoff_seconds=0,
    )

    request = AIGatewayRequest(
        system_id="balanced_v1",
        agent_id="berlin",
        prompt_version="test",
        model_route="primary",
        input_text="x",
    )

    with pytest.raises(BudgetExceededError):
        asyncio.run(gateway.generate_structured(request, Decision))

    snapshot = ledger.snapshot()
    assert snapshot.spent_eur == Decimal("2")
    assert snapshot.remaining_eur == Decimal("0")
    assert len(client.requests) == 1


class BillableIncompleteClient:
    provider_name = "mock"

    def __init__(self) -> None:
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        raise IncompleteAIProviderError(
            "OpenAI response incomplete: max_output_tokens",
            input_tokens=100_000,
            cached_input_tokens=0,
            output_tokens=200_000,
            latency_ms=7,
            provider_request_id="resp_billable_incomplete",
            model_id=request.model_id,
        )


def test_billable_incomplete_provider_usage_is_settled_without_retry():
    ledger = AIBudgetLedger("1")
    client = BillableIncompleteClient()
    route = ModelRoute(
        route_id="primary",
        provider="mock",
        model_id="primary-model",
        pricing=ModelPricing(
            input_per_million_eur=Decimal("1"),
            output_per_million_eur=Decimal("2"),
        ),
        max_output_tokens=300_000,
    )
    gateway = AIGateway(
        router=ModelRouter([route]),
        clients={"mock": client},
        budget=ledger,
        max_attempts=2,
        retry_backoff_seconds=0,
    )

    request = AIGatewayRequest(
        system_id="balanced_v1",
        agent_id="palermo",
        prompt_version="test",
        model_route="primary",
        input_text="x",
    )

    with pytest.raises(IncompleteAIProviderError, match="max_output_tokens"):
        asyncio.run(gateway.generate_structured(request, Decision))

    snapshot = ledger.snapshot()
    assert snapshot.spent_eur == Decimal("0.5")
    assert snapshot.reserved_eur == Decimal("0")
    assert len(client.requests) == 1
