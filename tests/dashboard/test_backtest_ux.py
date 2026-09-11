from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

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
        opened = START + timedelta(hours=index)
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
        timeframe="1h",
        source="ux_test",
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
        execution=ExecutionInput(code_version="test-batch16.9"),
        walk_forward=WalkForwardInput(enabled=False),
    )


def test_preview_exposes_dataset_candle_axis_and_split_indices() -> None:
    service = BacktestDashboardService()
    preview = service.preview_dataset(
        DatasetInput(
            csv_text=csv_series(140),
            symbol="BTC/EUR",
            timeframe="1h",
            source="ux_test",
        )
    )

    assert preview.candle_count == 140
    assert len(preview.candle_close_ms) == 140
    assert list(preview.candle_close_ms) == sorted(preview.candle_close_ms)

    split = preview.suggested_split_indices
    assert split is not None
    assert split.design_start == 0
    assert split.design_end == 83
    assert split.validation_start == 84
    assert split.validation_end == 111
    assert split.oos_start == 112
    assert split.oos_end == 139

    assert preview.suggested_split is not None
    assert int(preview.suggested_split.design_start.timestamp() * 1000) == preview.candle_close_ms[0]
    assert int(preview.suggested_split.design_end.timestamp() * 1000) == preview.candle_close_ms[83]
    assert int(preview.suggested_split.validation_start.timestamp() * 1000) == preview.candle_close_ms[84]
    assert int(preview.suggested_split.oos_start.timestamp() * 1000) == preview.candle_close_ms[112]


def test_capabilities_expose_registry_agents_without_changing_paper_boundary() -> None:
    service = BacktestDashboardService()
    caps = service.capabilities()

    agents = {item.agent: item for item in caps.agents}
    assert {"professor", "palermo", "lisbon", "berlin", "tokyo", "nairobi", "rio", "denver"} <= set(agents)
    assert agents["professor"].core is True
    assert agents["berlin"].core is False
    assert caps.paper_only is True
    assert caps.live_trading is False
    assert caps.agent_activity is True


def test_agent_traces_expose_directional_targets() -> None:
    async def scenario() -> None:
        service = BacktestDashboardService(history_limit=5)
        started = await service.start_campaign(request_for(service))

        for _ in range(1200):
            progress = service.get_campaign_progress(started.campaign_id)
            assert progress is not None
            if progress.status in {"COMPLETED", "FAILED", "CANCELLED"}:
                break
            await asyncio.sleep(0.002)
        else:
            raise AssertionError("campaign did not finish")

        assert progress.status == "COMPLETED", progress.error
        assert progress.active_agents == ()
        assert progress.agent_traces

        professor_plans = [
            trace for trace in progress.agent_traces
            if trace.agent == "professor" and trace.phase == "PLAN"
        ]
        assert professor_plans
        assert "berlin" in professor_plans[-1].targets

        berlin = next(
            trace for trace in progress.agent_traces
            if trace.agent == "berlin" and trace.phase == "ANALYSIS"
        )
        assert berlin.targets == ("professor",)

        palermo = next(
            trace for trace in progress.agent_traces
            if trace.agent == "palermo" and trace.phase == "RED_TEAM"
        )
        assert palermo.targets == ("professor",)

    asyncio.run(scenario())


def test_frontend_uses_dataset_index_selector_and_keeps_secret_out() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "app/dashboard/static/backtest.html").read_text(encoding="utf-8")
    js = (root / "app/dashboard/static/backtest.js").read_text(encoding="utf-8")

    assert 'id="split-editor"' in html
    assert 'id="split-design-end"' in html
    assert 'id="split-validation-end"' in html
    assert 'type="datetime-local"' not in html
    assert 'id="agent-cards"' in html
    assert 'id="crew-links"' in html
    assert "candle_close_ms" in js
    assert "splitPayload()" in js
    assert "active_agents" in js
    assert "animateCommunication" in js
    assert "api_key" not in js.lower()
