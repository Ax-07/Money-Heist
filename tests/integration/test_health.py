from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "Money Heist"
    assert body["version"] == "0.1.0"
    assert response.headers["x-correlation-id"]


def test_health_preserves_incoming_correlation_id(client: TestClient) -> None:
    response = client.get("/health", headers={"x-correlation-id": "test-correlation"})

    assert response.status_code == 200
    assert response.headers["x-correlation-id"] == "test-correlation"


def test_ready_endpoint(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["database"] == "ok"


def test_ready_returns_503_when_database_is_unavailable(client: TestClient, monkeypatch) -> None:
    def unavailable() -> bool:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(client.app.state.database, "ping", unavailable)
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "database_not_ready"
