from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.market.exchange import (
    MarketSidecarRefreshResult,
    MarketSidecarRefreshStatus,
    PaperShadowMarketInput,
)

NOW = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)


def test_market_input_exposes_one_sidecar_result_by_stable_id() -> None:
    refresh = MarketSidecarRefreshResult(
        refresher_id="rio.kraken_futures",
        status=MarketSidecarRefreshStatus.REFRESHED,
        symbol="BTC/EUR",
        observed_at=NOW,
    )
    market_input = PaperShadowMarketInput(
        market_snapshot=object(),
        market_context=object(),
        scan_result=object(),
        sidecar_refreshes=(refresh,),
    )

    assert market_input.sidecar_result("rio.kraken_futures") is refresh
    assert market_input.sidecar_result("denver.setup_stats") is None


def test_market_input_rejects_blank_sidecar_lookup_id() -> None:
    market_input = PaperShadowMarketInput(
        market_snapshot=object(),
        market_context=object(),
        scan_result=object(),
    )

    with pytest.raises(ValueError, match="refresher_id"):
        market_input.sidecar_result(" ")
