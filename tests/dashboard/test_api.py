from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.dashboard import router
from app.dashboard.projection import seeded_dashboard_snapshot
from app.dashboard.store import DashboardStore


NOW = datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc)


def client() -> TestClient:
    app = FastAPI()
    app.state.dashboard_store = DashboardStore(seeded_dashboard_snapshot(clock=lambda: NOW))
    app.include_router(router)
    return TestClient(app)


def test_overview_is_get_only_read_model():
    with client() as api:
        response = api.get("/api/dashboard/overview")
        assert response.status_code == 200
        payload = response.json()
        assert payload["read_only"] is True
        assert payload["live_execution"] is False
        assert payload["execution_scope"] == "PAPER_SHADOW_ONLY"
        assert api.post("/api/dashboard/overview").status_code == 405


def test_systems_endpoint_lists_three_shadow_systems():
    with client() as api:
        response = api.get("/api/dashboard/systems")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 3
        assert all(item["mode"] == "SHADOW" for item in payload)
        assert all(item["execution_mode"] == "PAPER" for item in payload)


def test_system_detail_uses_stable_system_id():
    with client() as api:
        response = api.get("/api/dashboard/systems/shadow_balanced_v1")
        assert response.status_code == 200
        assert response.json()["display_name"] == "Balanced"


def test_unknown_system_returns_404():
    with client() as api:
        response = api.get("/api/dashboard/systems/not-a-system")
        assert response.status_code == 404



def test_seeded_opportunities_are_empty_not_fabricated():
    with client() as api:
        response = api.get("/api/dashboard/opportunities")
        assert response.status_code == 200
        assert response.json() == []


def test_seeded_decisions_are_empty_not_fabricated():
    with client() as api:
        response = api.get("/api/dashboard/decisions")
        assert response.status_code == 200
        assert response.json() == []


def test_comparison_endpoint_preserves_unavailable_values():
    with client() as api:
        response = api.get("/api/dashboard/comparison")
        metric = response.json()["metrics"]["economic_net"]
        assert metric["availability"] == "UNAVAILABLE"
        assert set(metric["values"].values()) == {None}


def test_events_limit_is_bounded():
    with client() as api:
        assert api.get("/api/dashboard/events?limit=1").status_code == 200
        assert api.get("/api/dashboard/events?limit=0").status_code == 422
        assert api.get("/api/dashboard/events?limit=501").status_code == 422


def test_dashboard_html_is_served():
    with client() as api:
        response = api.get("/dashboard")
        assert response.status_code == 200
        assert "Dashboard V1" in response.text
        assert "LIVE DÉSACTIVÉ" in response.text
        assert "READ-ONLY" in response.text


def test_dashboard_assets_are_served_without_frontend_dependency():
    with client() as api:
        css = api.get("/dashboard/assets/dashboard.css")
        js = api.get("/dashboard/assets/dashboard.js")
        assert css.status_code == 200
        assert js.status_code == 200
        assert "text/css" in css.headers["content-type"]
        assert "javascript" in js.headers["content-type"]
