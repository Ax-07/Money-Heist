from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
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
from app.services.backtest.runner import HistoricalReplayCancelledError

START = datetime(2026, 1, 1, tzinfo=UTC)


def csv_series(count: int = 180) -> str:
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


def request_for(service: BacktestDashboardService) -> CampaignRequest:
    dataset = DatasetInput(
        csv_text=csv_series(),
        symbol="BTC/EUR",
        timeframe="1m",
        source="controls_test",
    )
    preview = service.preview_dataset(dataset)
    assert preview.suggested_split is not None
    return CampaignRequest(
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
        execution=ExecutionInput(code_version="test-batch16.8"),
        walk_forward=WalkForwardInput(enabled=False),
    )


def test_ui_exposes_stop_progress_and_structured_agent_panel() -> None:
    app = FastAPI()
    app.state.backtest_dashboard_service = BacktestDashboardService()
    app.include_router(router)
    with TestClient(app) as api:
        page = api.get("/dashboard/backtest")
        js = api.get("/dashboard/assets/backtest.js")

    assert page.status_code == 200
    assert 'id="stop-button"' in page.text
    assert 'id="campaign-progress"' in page.text
    assert 'id="agent-traces"' in page.text
    assert "chaîne de pensée privée" in page.text
    assert "/progress" in js.text
    assert "/cancel" in js.text


def test_background_campaign_completes_and_exposes_progress_and_agent_traces() -> None:
    async def scenario() -> None:
        service = BacktestDashboardService(history_limit=5)
        request = request_for(service)
        started = await service.start_campaign(request)
        assert started.status in {"QUEUED", "RUNNING"}
        assert started.can_cancel is True

        for _ in range(1000):
            progress = service.get_campaign_progress(started.campaign_id)
            assert progress is not None
            if progress.status in {"COMPLETED", "FAILED", "CANCELLED"}:
                break
            await asyncio.sleep(0.002)
        else:
            pytest.fail("campaign did not finish")

        assert progress.status == "COMPLETED", progress.error
        assert progress.percent == 100
        assert progress.result_available is True
        assert progress.opportunity_count > 0
        assert len(progress.agent_traces) > 0
        assert any(trace.agent == "professor" for trace in progress.agent_traces)
        assert service.get_campaign(started.campaign_id) is not None

    asyncio.run(scenario())


def test_operator_cancel_is_cooperative(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow_run(
        self,
        *,
        candles,
        run,
        progress_callback=None,
        point_callback=None,
        cancel_check=None,
    ):
        for index in range(1, 500):
            if cancel_check is not None and cancel_check():
                raise HistoricalReplayCancelledError("cancelled in test")
            if progress_callback is not None:
                progress_callback(index, 500, run.period_start)
            await asyncio.sleep(0.001)
        raise AssertionError("test campaign should have been cancelled")

    monkeypatch.setattr(
        "app.dashboard.backtest.HistoricalReplayRunner.run",
        slow_run,
    )

    async def scenario() -> None:
        service = BacktestDashboardService(history_limit=5)
        request = request_for(service)
        started = await service.start_campaign(request)
        await asyncio.sleep(0.01)
        cancelled = service.cancel_campaign(started.campaign_id)
        assert cancelled is not None
        assert cancelled.status == "CANCEL_REQUESTED"

        for _ in range(200):
            progress = service.get_campaign_progress(started.campaign_id)
            assert progress is not None
            if progress.status == "CANCELLED":
                break
            await asyncio.sleep(0.002)
        else:
            pytest.fail("campaign did not cancel")

        assert progress.status == "CANCELLED"
        assert progress.result_available is False
        assert progress.can_cancel is False
        assert service.get_campaign(started.campaign_id) is None

    asyncio.run(scenario())
