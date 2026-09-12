from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.dashboard.backtest import (
    CampaignRequest,
    DatasetInput,
    FrozenDenverPriorInput,
    MarketConstraintsInput,
    RiskInput,
    SplitInput,
)
from app.services.backtest.denver_prior import freeze_denver_prior
from app.services.backtest.setup_stats import (
    HistoricalSetupKey,
    HistoricalSetupObservation,
    HistoricalSetupStatsCatalog,
)
from app.services.backtest.splits import BacktestPeriodRole


BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _prior():
    setup = HistoricalSetupKey(
        system_id="balanced_v1",
        symbol="BTC/USDC",
        timeframe="1h",
        scanner_version="scanner-v1",
        feature_version="feature-engine-v1",
        regime="BULLISH_TREND",
        triggers=("RANGE_BREAK",),
    )
    observation = HistoricalSetupObservation(
        run_id="source-run",
        dataset_id="source-dataset",
        strategy_fingerprint="strategy-v1",
        period_role=BacktestPeriodRole.DESIGN,
        opportunity_id="source-opportunity",
        trade_id="source-trade",
        setup=setup,
        side="LONG",
        opened_at=BASE - timedelta(days=2),
        closed_at=BASE - timedelta(days=1),
        net_pnl=Decimal("1"),
    )
    return freeze_denver_prior(
        HistoricalSetupStatsCatalog((observation,)),
        cutoff=BASE,
    )


def _request(timeframe: str):
    return {
        "dataset": DatasetInput(
            csv_text="timestamp,open,high,low,close,volume\n",
            symbol="BTC/USDC",
            timeframe=timeframe,
        ),
        "split": SplitInput(
            design_start=BASE + timedelta(days=1),
            design_end=BASE + timedelta(days=2),
            validation_start=BASE + timedelta(days=3),
            validation_end=BASE + timedelta(days=4),
            oos_start=BASE + timedelta(days=5),
            oos_end=BASE + timedelta(days=6),
        ),
        "risk": RiskInput(),
        "market": MarketConstraintsInput(
            qty_step=Decimal("0.00001"),
            min_qty=Decimal("0.00001"),
            min_notional=Decimal("5"),
            max_leverage=Decimal("1"),
        ),
        "denver_prior": FrozenDenverPriorInput(
            json_text=_prior().to_json(),
        ),
    }


def test_denver_prior_input_defaults_to_oos_only() -> None:
    payload = FrozenDenverPriorInput(json_text=_prior().to_json())
    assert payload.activation_mode == "OOS_ONLY"


def test_denver_activation_requires_full_mtf_source() -> None:
    with pytest.raises(ValidationError, match="Denver prior activation"):
        CampaignRequest(**_request("1h"))

    request = CampaignRequest(**_request("1m"))
    assert request.denver_prior is not None
    assert request.denver_prior.activation_mode == "OOS_ONLY"


def test_denver_dashboard_controls_are_explicit_and_off_by_default() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "app/dashboard/static/backtest.html").read_text(
        encoding="utf-8"
    )
    js = (root / "app/dashboard/static/backtest.js").read_text(
        encoding="utf-8"
    )

    assert 'id="denver-prior-enabled" type="checkbox"' in html
    assert 'id="denver-prior-file"' in html
    assert '<option value="OOS_ONLY" selected>OOS seulement</option>' in html
    assert "Denver historique désactivé." in html
    assert "denver_prior: denverPriorPayload()" in js
    assert 'if (!$("denver-prior-enabled").checked) return null;' in js
