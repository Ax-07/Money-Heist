from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.dashboard.backtest import (
    BacktestDashboardService,
    CampaignRequest,
    DatasetInput,
    MarketConstraintsInput,
    RiskInput,
    SplitInput,
)


def _request(timeframe: str) -> CampaignRequest:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return CampaignRequest(
        dataset=DatasetInput(
            csv_text="timestamp,open,high,low,close,volume\n",
            symbol="BTC/USDC",
            timeframe=timeframe,
            source="fixture",
        ),
        split=SplitInput(
            design_start=start,
            design_end=start + timedelta(days=1),
            validation_start=start + timedelta(days=1),
            validation_end=start + timedelta(days=2),
            oos_start=start + timedelta(days=2),
            oos_end=start + timedelta(days=3),
        ),
        risk=RiskInput(),
        market=MarketConstraintsInput(
            qty_step=Decimal("0.00001"),
            min_qty=Decimal("0.0001"),
            min_notional=Decimal("10"),
            max_qty=Decimal("10"),
            max_leverage=Decimal("1"),
        ),
    )


def test_dashboard_1m_config_enables_versioned_mtf_runtime():
    service = BacktestDashboardService()
    config = service._backtest_config(_request("1m"))

    assumptions = config.execution_assumptions
    assert assumptions["mtf_runtime_version"] == "historical-mtf-runtime-v1"
    assert assumptions["historical_source_timeframe"] == "1m"
    assert assumptions["decision_timeframe"] == "1h"
    assert assumptions["mtf_timeframes"] == "15m,1h,4h,1d"
    assert assumptions["market_structure_version"] == "market-structure-v1"


def test_dashboard_1h_config_stays_legacy_without_fake_15m():
    service = BacktestDashboardService()
    config = service._backtest_config(_request("1h"))

    assumptions = config.execution_assumptions
    assert "mtf_runtime_version" not in assumptions
    assert "decision_timeframe" not in assumptions
    assert "mtf_timeframes" not in assumptions
