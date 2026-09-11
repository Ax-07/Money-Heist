from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

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
    assert assumptions["risk_context_binding_version"] == (
        "portfolio-market-constraints-v1"
    )


def test_dashboard_1h_config_stays_legacy_without_fake_15m():
    service = BacktestDashboardService()
    config = service._backtest_config(_request("1h"))

    assumptions = config.execution_assumptions
    assert "mtf_runtime_version" not in assumptions
    assert "decision_timeframe" not in assumptions
    assert "mtf_timeframes" not in assumptions


def _derivatives_csv() -> str:
    return "\n".join(
        [
            (
                "symbol,instrument,observed_at,available_at,funding_rate,"
                "open_interest,open_interest_change_pct,long_short_ratio"
            ),
            (
                "BTC/USDC,PF_XBTUSD,2026-01-01T00:00:00Z,"
                "2026-01-01T01:00:00Z,,1000,1,1.1"
            ),
            (
                "BTC/USDC,PF_XBTUSD,2026-01-01T01:00:00Z,"
                "2026-01-01T02:00:00Z,0.0001,1010,1,1.2"
            ),
        ]
    ) + "\n"


def test_dashboard_derivatives_activation_is_explicit_and_bound():
    from app.dashboard.backtest import HistoricalDerivativesInput
    from app.services.backtest.derivatives_runtime import (
        historical_derivatives_runner_kwargs,
    )

    service = BacktestDashboardService()
    derivatives = HistoricalDerivativesInput(
        csv_text=_derivatives_csv(),
        max_age_seconds=7200,
    )
    request = _request("1m").model_copy(
        update={"derivatives": derivatives}
    )
    archive = service._parse_historical_derivatives(derivatives)
    config = service._backtest_config(
        request,
        historical_derivatives_archive=archive,
    )

    assumptions = config.execution_assumptions
    assert assumptions["derivatives_runtime_version"] == (
        "historical-derivatives-runtime-v1"
    )
    assert assumptions["derivatives_context_binding_version"] == (
        "historical-derivatives-rio-v1"
    )
    assert assumptions["derivatives_archive_fingerprint"] == (
        archive.dataset_fingerprint
    )
    assert assumptions["derivatives_max_age_seconds"] == "7200"

    kwargs = historical_derivatives_runner_kwargs(assumptions, archive)
    assert kwargs["historical_derivatives_archive"] is archive
    assert int(kwargs["derivatives_max_age"].total_seconds()) == 7200


def test_dashboard_rejects_derivatives_for_native_1h_source():
    from app.dashboard.backtest import HistoricalDerivativesInput

    base = _request("1h")
    payload = base.model_dump(mode="python")
    payload["derivatives"] = HistoricalDerivativesInput(
        csv_text=_derivatives_csv(),
        max_age_seconds=7200,
    )

    with pytest.raises(ValueError, match="requires source timeframe"):
        CampaignRequest.model_validate(payload)
