from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.frontend_v2_research import router


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


def test_historical_run_without_research_sidecars_is_explicitly_unavailable() -> None:
    with _client() as client:
        response = client.get(
            "/api/frontend/v2/backtests/runs/old-run/research/decision-quality?role=OOS"
        )

    assert response.status_code == 200
    assert response.json()["research_available"] is False
    assert response.json()["unavailable_reason"] == "PRECOMPUTED_RESEARCH_UNAVAILABLE"


def test_missing_campaign_is_404() -> None:
    with _client() as client:
        response = client.get(
            "/api/frontend/v2/backtests/runs/missing/research/decision-quality?role=OOS"
        )
    assert response.status_code == 404


def test_missing_precomputed_evidence_is_404_and_never_computed_on_get() -> None:
    with _client() as client:
        response = client.get(
            "/api/frontend/v2/backtests/runs/old-run/research/evidence"
            "?role=OOS&report_type=SCANNER_FILTERING"
            "&dimension=CLASSIFICATION&key=CANDIDATE_OPPORTUNITY"
        )
    assert response.status_code == 404
