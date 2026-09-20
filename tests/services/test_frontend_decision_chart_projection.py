from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.market.features import FeatureEngine
from app.market.models import Candle
from app.market.multitimeframe import resample_closed_candles
from app.services.frontend_v2.decision_chart import (
    DecisionChartUnavailableError,
    build_frontend_decision_chart_projection,
)


def _minute_candles(count: int = 180) -> tuple[Candle, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    output: list[Candle] = []
    for index in range(count):
        opened = start + timedelta(minutes=index)
        base = Decimal("100") + Decimal(index) / Decimal("100")
        output.append(
            Candle(
                symbol="BTC/USDC",
                timeframe="1m",
                open_time=opened,
                close_time=opened + timedelta(minutes=1),
                open=base,
                high=base + Decimal("0.20"),
                low=base - Decimal("0.20"),
                close=base + Decimal("0.05"),
                volume=Decimal("10") + Decimal(index % 7),
            )
        )
    return tuple(output)


def _bundle(candles: tuple[Candle, ...], *, corrupt_id: bool = False):
    decision = resample_closed_candles(
        candles,
        target_timeframe="1h",
        as_of=candles[-1].close_time,
    )
    engine = FeatureEngine()
    records = []
    for index, candle in enumerate(decision, start=1):
        snapshot = engine.compute(
            decision[:index],
            symbol="BTC/USDC",
            timeframe="1h",
            observed_at=candle.close_time,
        )
        records.append(
            SimpleNamespace(
                observed_at=candle.close_time,
                scanner_evaluation_id=(
                    "corrupt"
                    if corrupt_id and index == len(decision)
                    else snapshot.snapshot_id
                ),
                symbol="BTC/USDC",
                decision_timeframe="1h",
            )
        )
    run = SimpleNamespace(
        symbol="BTC/USDC",
        source_timeframe="1m",
        decision_timeframe="1h",
        period_start=decision[0].close_time,
        period_end=decision[-1].close_time,
    )
    return SimpleNamespace(
        campaign_id="campaign-1",
        role="OOS",
        analytics=SimpleNamespace(analytics_available=True, run=run),
        scanner=SimpleNamespace(analytics_available=True, records=tuple(records)),
    )


def test_decision_chart_uses_decision_timeframe_and_feature_snapshots() -> None:
    candles = _minute_candles()
    projection = build_frontend_decision_chart_projection(
        campaign_id="campaign-1",
        role="OOS",
        bundle=_bundle(candles),
        source_candles=candles,
    )

    assert projection.source_timeframe == "1m"
    assert projection.decision_timeframe == "1h"
    assert len(projection.candles) == 3
    assert len(projection.indicators) == 3
    assert all(point.snapshot_id for point in projection.indicators)
    assert "rsi_14" in projection.direct_scanner_features


def test_decision_chart_fails_closed_when_snapshot_identity_differs() -> None:
    candles = _minute_candles()
    with pytest.raises(
        DecisionChartUnavailableError,
        match="DECISION_CHART_FEATURE_SNAPSHOT_ID_MISMATCH",
    ):
        build_frontend_decision_chart_projection(
            campaign_id="campaign-1",
            role="OOS",
            bundle=_bundle(candles, corrupt_id=True),
            source_candles=candles,
        )
