from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.frontend_v2_decision_intelligence import router


class ExistingStore:
    def get(self, campaign_id: str) -> object | None:
        return object() if campaign_id == "old-run" else None

    def persisted_export(self, campaign_id: str, name: str) -> str | None:
        return None


def _client() -> TestClient:
    app = FastAPI()
    app.state.frontend_v2_store = ExistingStore()
    app.include_router(router)
    return TestClient(app)


def test_old_run_without_analytics_degrades_cleanly() -> None:
    with _client() as client:
        response = client.get(
            "/api/frontend/v2/backtests/runs/old-run/analytics/overlays?role=OOS"
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["analytics_available"] is False
    assert payload["technical_events"] == []
    assert payload["zigzag_pivots"] == []
    assert payload["patterns"] == []


def test_unknown_campaign_remains_404() -> None:
    with _client() as client:
        response = client.get(
            "/api/frontend/v2/backtests/runs/missing/analytics/overlays?role=OOS"
        )
    assert response.status_code == 404
