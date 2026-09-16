from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.frontend_v2 import (
    FrontendAIInput,
    FrontendV2Store,
    _dataset_upload_max_bytes,
    router,
)
from app.dashboard.backtest import (
    BacktestDashboardService,
    CampaignProgressView,
    DatasetInput,
    DatasetPreview,
)
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
    dataset_dir = first._dataset_dir(preview.dataset_id)
    assert (dataset_dir / "dataset.csv").read_text(encoding="utf-8") == dataset.csv_text
    assert "csv_text" not in (dataset_dir / "input.json").read_text(encoding="utf-8")


def test_openai_model_catalog_is_verified_usd_snapshot(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/frontend/v2/ai/openai/models")
    assert response.status_code == 200
    payload = response.json()
    assert payload["pricing_currency"] == "USD"
    assert payload["pricing_snapshot_at"] == "2026-09-13"
    models = {item["model_id"]: item for item in payload["models"]}
    assert set(models) == {
        "gpt-6-astra",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
    }
    assert models["gpt-5.6-terra"]["input_per_million_usd"] == "2.00"
    assert models["gpt-5.6-terra"]["cached_input_per_million_usd"] == "0.20"
    assert models["gpt-5.6-terra"]["output_per_million_usd"] == "12.00"
    assert models["gpt-5.6-sol"]["pricing_valid_until"] == "2026-11-21"


def test_frontend_live_eval_derives_legacy_pricing_from_usd_catalog() -> None:
    frontend = FrontendAIInput(
        mode="LIVE_EVAL",
        hard_budget_usd="5",
        model_id="gpt-5.6-luna",
        reasoning_effort="low",
    )
    legacy = frontend.to_legacy_ai_input()
    assert str(legacy.hard_budget_eur) == "5"
    assert str(legacy.input_per_million_eur) == "0.20"
    assert str(legacy.cached_input_per_million_eur) == "0.02"
    assert str(legacy.output_per_million_eur) == "1.20"


def test_frontend_live_eval_rejects_unknown_or_unsupported_model_configuration() -> None:
    try:
        FrontendAIInput(
            mode="LIVE_EVAL",
            hard_budget_usd="5",
            model_id="not-a-model",
            reasoning_effort="low",
        )
    except ValueError as exc:
        assert "verified OpenAI pricing catalog" in str(exc)
    else:
        raise AssertionError("unknown model must fail closed")

    try:
        FrontendAIInput(
            mode="LIVE_EVAL",
            hard_budget_usd="5",
            model_id="gpt-6-astra",
            reasoning_effort="none",
        )
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("unsupported reasoning effort must fail closed")


def test_dataset_upload_default_limit_allows_large_one_minute_csv(monkeypatch) -> None:
    monkeypatch.delenv("MONEY_HEIST_DATASET_UPLOAD_MAX_MB", raising=False)
    limit = _dataset_upload_max_bytes()
    assert limit is not None
    assert limit >= 50 * 1024 * 1024


def test_raw_dataset_upload_persists_without_json_wrapping(tmp_path: Path) -> None:
    rows = ["timestamp,open,high,low,close,volume"]
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(120):
        instant = datetime.fromtimestamp(base.timestamp() + index * 60, tz=UTC)
        rows.append(f"{instant.isoformat().replace('+00:00', 'Z')},100,101,99,100.5,1")
    csv_text = "\n".join(rows) + "\n"

    with _client(tmp_path) as client:
        response = client.post(
            "/api/frontend/v2/backtests/datasets/upload",
            params={
                "symbol": "BTC/USDC",
                "timeframe": "1m",
                "source": "unit-test:raw-upload.csv",
            },
            content=csv_text.encode("utf-8"),
            headers={"content-type": "text/csv"},
        )
    assert response.status_code == 201, response.text
    dataset_id = response.json()["dataset_id"]
    store = FrontendV2Store(storage_dir=tmp_path)
    restored = store.load_dataset(dataset_id)
    assert restored is not None
    assert restored.csv_text == csv_text

def test_frontend_v2_cancel_route_delegates_to_running_service(tmp_path: Path) -> None:
    campaign_id = "campaign-cancel-test"
    progress = CampaignProgressView(
        campaign_id=campaign_id,
        created_at=datetime(2026, 9, 16, tzinfo=UTC),
        status="CANCEL_REQUESTED",
        phase="CANCEL_REQUESTED",
        percent=12.5,
        work_done=125,
        total_work=1000,
        opportunity_count=3,
        executed_order_count=0,
        message="Arrêt demandé; attente du prochain checkpoint de replay.",
        can_cancel=False,
        result_available=False,
        elapsed_ms=1234,
        ai_call_count=7,
        ai_wall_time_ms=456,
    )
    with _client(tmp_path) as client:
        service = client.app.state.backtest_dashboard_service
        service.cancel_campaign = lambda value: progress if value == campaign_id else None
        response = client.post(f"/api/frontend/v2/backtests/runs/{campaign_id}/cancel")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "CANCEL_REQUESTED"
    assert payload["elapsed_ms"] == 1234
    persisted = FrontendV2Store(storage_dir=tmp_path).persisted_progress(campaign_id)
    assert persisted is not None
    assert persisted.status == "CANCEL_REQUESTED"
