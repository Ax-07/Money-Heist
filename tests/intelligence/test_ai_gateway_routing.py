from decimal import Decimal

import pytest

from app.intelligence.ai_gateway import AIConfigurationError, ModelPricing, ModelRoute, ModelRouter


def route(route_id: str, fallback: str | None = None) -> ModelRoute:
    return ModelRoute(
        route_id=route_id,
        provider="mock",
        model_id=f"model-{route_id}",
        pricing=ModelPricing(
            input_per_million_eur=Decimal("1"),
            output_per_million_eur=Decimal("2"),
        ),
        fallback_route_id=fallback,
    )


def test_router_returns_configured_route():
    router = ModelRouter([route("primary")])
    assert router.get("primary").model_id == "model-primary"


def test_router_builds_fallback_chain():
    router = ModelRouter([route("primary", "cheap"), route("cheap")])
    assert [r.route_id for r in router.route_chain("primary")] == ["primary", "cheap"]


def test_router_rejects_unknown_fallback():
    with pytest.raises(AIConfigurationError):
        ModelRouter([route("primary", "missing")])


def test_router_rejects_cycle():
    with pytest.raises(AIConfigurationError):
        ModelRouter([route("a", "b"), route("b", "a")])


def test_router_rejects_duplicate_ids():
    with pytest.raises(AIConfigurationError):
        ModelRouter([route("same"), route("same")])
