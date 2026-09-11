from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.backtest_dashboard import router
from app.dashboard.backtest import (
    AIInput,
    BacktestDashboardService,
    CampaignRequest,
    DatasetInput,
    ExecutionInput,
    MarketConstraintsInput,
    RiskInput,
    WalkForwardInput,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def csv_series(count: int = 140) -> str:
    rows = ["timestamp,open,high,low,close,volume"]
    price = Decimal("100")
    for index in range(count):
        opened = START + timedelta(minutes=index)
        drift = Decimal("0.35") if (index // 20) % 2 == 0 else Decimal("-0.25")
        close = price + drift
        high = max(price, close) + Decimal("0.20")
        low = min(price, close) - Decimal("0.20")
        rows.append(
            f"{opened.isoformat()},{price},{high},{low},{close},{1000 + index}"
        )
        price = close
    return "\n".join(rows) + "\n"


def service() -> BacktestDashboardService:
    return BacktestDashboardService(history_limit=5)


def client() -> TestClient:
    app = FastAPI()
    app.state.backtest_dashboard_service = service()
    app.include_router(router)
    return TestClient(app)


def test_backtest_page_and_assets_expose_paper_only_contract() -> None:
    with client() as api:
        page = api.get("/dashboard/backtest")
        css = api.get("/dashboard/assets/backtest.css")
        js = api.get("/dashboard/assets/backtest.js")

    assert page.status_code == 200
    assert "Backtest Dashboard" in page.text
    assert "PAPER ONLY" in page.text
    assert "OPENAI_API_KEY" in page.text
    assert 'type="password"' not in page.text
    assert "LIVE TRADING INTERDIT" in page.text
    assert css.status_code == 200
    assert js.status_code == 200


def test_dataset_preview_returns_hash_quality_and_suggested_split() -> None:
    payload = {
        "csv_text": csv_series(),
        "symbol": "BTC/EUR",
        "timeframe": "1m",
        "source": "test_csv",
    }
    with client() as api:
        response = api.post("/api/dashboard/backtest/dataset/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BTC/EUR"
    assert data["candle_count"] == 140
    assert data["is_valid"] is True
    assert data["gap_count"] == 0
    assert len(data["content_sha256"]) == 64
    assert data["suggested_split"] is not None


def test_api_never_accepts_openai_key_in_campaign_payload() -> None:
    preview = service().preview_dataset(
        DatasetInput(csv_text=csv_series(), symbol="BTC/EUR", timeframe="1m")
    )
    assert preview.suggested_split is not None
    payload = {
        "dataset": {
            "csv_text": csv_series(),
            "symbol": "BTC/EUR",
            "timeframe": "1m",
            "source": "test_csv",
        },
        "split": preview.suggested_split.model_dump(mode="json"),
        "risk": RiskInput().model_dump(mode="json"),
        "market": {
            "qty_step": "0.000001",
            "min_qty": "0.000001",
            "min_notional": "0.01",
            "max_leverage": "1",
        },
        "ai": {**AIInput().model_dump(mode="json"), "openai_api_key": "secret"},
        "execution": ExecutionInput().model_dump(mode="json"),
        "walk_forward": WalkForwardInput().model_dump(mode="json"),
    }
    with client() as api:
        response = api.post("/api/dashboard/backtest/runs", json=payload)
    assert response.status_code == 422


def test_mock_campaign_executes_real_batch16_stack_without_live_trading() -> None:
    svc = service()
    dataset = DatasetInput(
        csv_text=csv_series(),
        symbol="BTC/EUR",
        timeframe="1m",
        source="test_csv",
    )
    preview = svc.preview_dataset(dataset)
    assert preview.suggested_split is not None
    request = CampaignRequest(
        dataset=dataset,
        split=preview.suggested_split,
        risk=RiskInput(),
        market=MarketConstraintsInput(
            qty_step=Decimal("0.000001"),
            min_qty=Decimal("0.000001"),
            min_notional=Decimal("0.01"),
            max_leverage=Decimal("1"),
        ),
        ai=AIInput(),
        execution=ExecutionInput(),
        walk_forward=WalkForwardInput(enabled=False),
    )

    result = asyncio.run(svc.run_campaign(request))

    assert result.status == "COMPLETED"
    assert result.ai_mode.value == "MOCK"
    assert result.dataset.is_valid is True
    assert result.design.run_id != result.validation.run_id != result.oos.run_id
    assert result.oos.processed_candles > 0
    assert "oos-equity.csv" in result.exports
    assert "split-report.json" in result.exports
    assert svc.capabilities().live_trading is False


def test_mock_campaign_exports_denver_setup_stats_catalog() -> None:
    from app.services.backtest.setup_stats import HistoricalSetupStatsCatalog

    svc = service()
    dataset = DatasetInput(
        csv_text=csv_series(),
        symbol="BTC/EUR",
        timeframe="1m",
        source="test_csv",
    )
    preview = svc.preview_dataset(dataset)
    assert preview.suggested_split is not None
    request = CampaignRequest(
        dataset=dataset,
        split=preview.suggested_split,
        risk=RiskInput(),
        market=MarketConstraintsInput(
            qty_step=Decimal("0.000001"),
            min_qty=Decimal("0.000001"),
            min_notional=Decimal("0.01"),
            max_leverage=Decimal("1"),
        ),
        ai=AIInput(),
        execution=ExecutionInput(),
        walk_forward=WalkForwardInput(enabled=False),
    )

    result = asyncio.run(svc.run_campaign(request))
    name = "denver-setup-stats-catalog.json"

    assert name in result.exports
    exported = svc.get_export(result.campaign_id, name)
    assert exported is not None
    media_type, content = exported
    assert media_type == "application/json"

    catalog = HistoricalSetupStatsCatalog.from_json(content)
    assert catalog.to_json() == content
    assert all(
        item.period_role.value in {"DESIGN", "VALIDATION", "OOS"}
        for item in catalog.observations
    )


def test_denver_catalog_export_downloads_through_existing_api() -> None:
    from app.services.backtest.setup_stats import HistoricalSetupStatsCatalog

    svc = service()
    app = FastAPI()
    app.state.backtest_dashboard_service = svc
    app.include_router(router)

    dataset = DatasetInput(
        csv_text=csv_series(),
        symbol="BTC/EUR",
        timeframe="1m",
        source="test_csv",
    )
    preview = svc.preview_dataset(dataset)
    assert preview.suggested_split is not None
    request = CampaignRequest(
        dataset=dataset,
        split=preview.suggested_split,
        risk=RiskInput(),
        market=MarketConstraintsInput(
            qty_step=Decimal("0.000001"),
            min_qty=Decimal("0.000001"),
            min_notional=Decimal("0.01"),
            max_leverage=Decimal("1"),
        ),
        ai=AIInput(),
        execution=ExecutionInput(),
        walk_forward=WalkForwardInput(enabled=False),
    )
    result = asyncio.run(svc.run_campaign(request))

    with TestClient(app) as api:
        response = api.get(
            f"/api/dashboard/backtest/runs/{result.campaign_id}"
            "/exports/denver-setup-stats-catalog.json"
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "denver-setup-stats-catalog.json" in response.headers[
        "content-disposition"
    ]
    restored = HistoricalSetupStatsCatalog.from_json(response.text)
    assert restored.to_json() == response.text


def test_denver_catalog_attribution_failure_does_not_fail_campaign(monkeypatch) -> None:
    from app.services.backtest.setup_stats import (
        HistoricalSetupAttributionError,
    )

    svc = service()
    dataset = DatasetInput(
        csv_text=csv_series(),
        symbol="BTC/EUR",
        timeframe="1m",
        source="test_csv",
    )
    preview = svc.preview_dataset(dataset)
    assert preview.suggested_split is not None
    request = CampaignRequest(
        dataset=dataset,
        split=preview.suggested_split,
        risk=RiskInput(),
        market=MarketConstraintsInput(
            qty_step=Decimal("0.000001"),
            min_qty=Decimal("0.000001"),
            min_notional=Decimal("0.01"),
            max_leverage=Decimal("1"),
        ),
        ai=AIInput(),
        execution=ExecutionInput(),
        walk_forward=WalkForwardInput(enabled=False),
    )

    def fail_catalog(_sources):
        raise HistoricalSetupAttributionError(
            "closed trade cannot be attributed to exactly one setup entry"
        )

    monkeypatch.setattr(
        "app.dashboard.backtest.catalog_from_historical_runs",
        fail_catalog,
    )

    result = asyncio.run(svc.run_campaign(request))

    assert result.status == "COMPLETED"
    assert "denver-setup-stats-catalog.json" not in result.exports
    assert "denver-setup-stats-status.json" in result.exports

    exported = svc.get_export(
        result.campaign_id,
        "denver-setup-stats-status.json",
    )
    assert exported is not None
    media_type, content = exported
    assert media_type == "application/json"

    payload = json.loads(content)
    assert payload["status"] == "UNAVAILABLE"
    assert payload["reason"] == "AMBIGUOUS_TRADE_ATTRIBUTION"
