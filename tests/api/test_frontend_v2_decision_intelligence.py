from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.frontend_v2 import FrontendV2Store
from app.api.routes.frontend_v2_decision_intelligence import router


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.frontend_v2_store = FrontendV2Store(storage_dir=tmp_path)
    app.include_router(router)
    return TestClient(app)


def test_missing_campaign_returns_404(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/frontend/v2/backtests/runs/missing/analytics?role=OOS")
    assert response.status_code == 404


def test_existing_old_campaign_returns_explicit_unavailable(tmp_path: Path) -> None:
    # Use a compatible store that represents a historical campaign with no 24A/24B bundle.
    class ExistingStore:
        def get(self, campaign_id: str) -> object | None:
            return object() if campaign_id == "old-run" else None

        def persisted_export(self, campaign_id: str, name: str) -> str | None:
            return None

    app = FastAPI()
    app.state.frontend_v2_store = ExistingStore()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get("/api/frontend/v2/backtests/runs/old-run/analytics?role=OOS")

    assert response.status_code == 200
    assert response.json()["analytics_available"] is False
    assert response.json()["unavailable_reason"] == "PRECOMPUTED_ANALYTICS_UNAVAILABLE"


def test_missing_precomputed_decision_intelligence_is_explicit(tmp_path: Path) -> None:
    class ExistingStore:
        def get(self, campaign_id: str) -> object | None:
            return object()

        def persisted_export(self, campaign_id: str, name: str) -> str | None:
            return None

    app = FastAPI()
    app.state.frontend_v2_store = ExistingStore()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get("/api/frontend/v2/backtests/runs/old-run/opportunities/opp-1/decision-intelligence?role=OOS")

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision_intelligence_available"] is False
    assert payload["opportunity_id"] == "opp-1"
