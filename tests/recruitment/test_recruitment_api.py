from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.recruitment as recruitment
from app.api.routes.recruitment import router
from app.recruitment.api import get_recruitment_api_capabilities


def test_public_recruitment_exports_are_complete_and_unique() -> None:
    assert len(recruitment.__all__) == len(set(recruitment.__all__))
    for name in recruitment.__all__:
        assert hasattr(recruitment, name), name
    assert hasattr(recruitment, "RecruitmentApiCapabilities")
    assert hasattr(recruitment, "RecruitmentApiContractVersion")
    assert hasattr(recruitment, "get_recruitment_api_capabilities")


def test_capabilities_are_read_only_and_advisory() -> None:
    capabilities = get_recruitment_api_capabilities()

    assert capabilities.mode == "ADVISORY_READ_ONLY"
    assert capabilities.http_methods == ("GET",)
    assert "CANDIDATE" in capabilities.candidate_states
    assert "SHADOW" in capabilities.candidate_states
    assert "PROBATION" in capabilities.candidate_states
    assert "RECOMMEND_PROMOTION" in capabilities.advisory_actions
    assert capabilities.evidence_purposes == ("DIAGNOSTIC", "PROMOTION")
    assert "marginal_economic_net_eur" in capabilities.advisory_metric_keys
    assert capabilities.operator_authorization_required is True
    assert capabilities.auto_apply is False
    assert capabilities.registry_mutation is False
    assert capabilities.lifecycle_transition_applied is False
    assert capabilities.promotion_applied is False
    assert capabilities.live_authority is False


def test_capabilities_contract_versions_are_named_and_unique() -> None:
    capabilities = get_recruitment_api_capabilities()
    names = tuple(item.name for item in capabilities.contract_versions)
    versions = tuple(item.version for item in capabilities.contract_versions)

    assert len(names) == len(set(names))
    assert len(versions) == len(set(versions))
    assert "candidate_spec" in names
    assert "candidate_evidence_package" in names
    assert "recruitment_advisory" in names
    assert "advisory_audit" in names


def test_recruitment_http_surface_exposes_capabilities_only() -> None:
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.get("/api/recruitment/capabilities")
        post_response = client.post("/api/recruitment/capabilities", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "ADVISORY_READ_ONLY"
    assert payload["operator_authorization_required"] is True
    assert payload["auto_apply"] is False
    assert payload["registry_mutation"] is False
    assert payload["promotion_applied"] is False
    assert payload["live_authority"] is False
    assert post_response.status_code == 405


def test_recruitment_router_contains_no_mutating_http_methods() -> None:
    methods = {
        method
        for route_item in router.routes
        for method in (getattr(route_item, "methods", None) or set())
    }
    assert methods == {"GET"}
