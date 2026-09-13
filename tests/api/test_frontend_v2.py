from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.frontend_v2 import FrontendV2Store, router
from app.dashboard.backtest import BacktestDashboardService, DatasetInput, DatasetPreview
from app.domain.enums import SystemMode


def _client(storage_dir: Path | None = None) -> TestClient:
    app = FastAPI()
    app.state.settings = SimpleNamespace(
        runtime_mode=SystemMode.PAPER,
        app_env="test",
        default_system_id="balanced_v1",
        live_environment="disabled",
        live_system_id=None,
        live_timeframe_values=None,
    )
    app.state.backtest_dashboard_service = BacktestDashboardService()
    app.state.frontend_v2_store = FrontendV2Store(storage_dir=storage_dir)
    app.include_router(router)
    return TestClient(app)


def test_frontend_capabilities_are_read_only_and_backend_sourced(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/frontend/v2/capabilities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime_mode"] == "PAPER"
    assert payload["live_controls_exposed"] is False
    assert payload["live_operational_state"] == "UNAVAILABLE"
    assert payload["realtime_transport"] == "POLLING"
    assert "BTC/EUR" in payload["market_symbols"]


def test_market_candles_reject_unknown_symbol_without_network(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get(
            "/api/frontend/v2/market/candles",
            params={"symbol": "DOGE/EUR", "timeframe": "1h"},
        )
    assert response.status_code == 422


def test_replay_requires_v2_campaign_capture(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get(
            "/api/frontend/v2/backtests/runs/missing/replay",
            params={"role": "OOS"},
        )
    assert response.status_code == 409
    assert "persist the immutable input" in response.json()["detail"]


def test_market_constraints_reject_unknown_symbol_without_network(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get(
            "/api/frontend/v2/market/constraints",
            params={"symbol": "DOGE/EUR"},
        )
    assert response.status_code == 422


def test_dataset_library_survives_store_recreation(tmp_path: Path) -> None:
    dataset = DatasetInput(
        csv_text="timestamp,open,high,low,close,volume\n",
        symbol="BTC/EUR",
        timeframe="1h",
        source="unit-test",
    )
    observed_at = datetime(2026, 1, 1, 1, tzinfo=UTC)
    preview = DatasetPreview(
        dataset_id="BTC/EUR:1h:test",
        version="v1",
        content_sha256="abc123",
        symbol="BTC/EUR",
        timeframe="1h",
        source="unit-test",
        candle_count=1,
        start_at=observed_at,
        end_at=observed_at,
        is_valid=True,
        gap_count=0,
        has_duplicates=False,
        missing_fields=(),
    )
    first = FrontendV2Store(storage_dir=tmp_path)
    first.save_dataset(dataset, preview)

    second = FrontendV2Store(storage_dir=tmp_path)
    restored = second.load_dataset(preview.dataset_id)
    restored_preview = second.get_dataset_preview(preview.dataset_id)

    assert restored is not None
    assert restored.symbol == "BTC/EUR"
    assert restored_preview is not None
    assert restored_preview.content_sha256 == "abc123"
