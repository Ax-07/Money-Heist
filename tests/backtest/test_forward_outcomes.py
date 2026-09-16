from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.market.models import Candle
from app.services.backtest.forward_outcomes import build_forward_outcomes_report


START = datetime(2026, 1, 1, tzinfo=UTC)


def minute_candles(count: int) -> tuple[Candle, ...]:
    candles = []
    for index in range(count):
        opened = START + timedelta(minutes=index)
        price = Decimal("100") + Decimal(index) / Decimal("100")
        candles.append(
            Candle(
                symbol="BTC/USDC",
                timeframe="1m",
                open_time=opened,
                close_time=opened + timedelta(minutes=1),
                open=price,
                high=price + Decimal("0.50"),
                low=price - Decimal("0.50"),
                close=price + Decimal("0.10"),
                volume=Decimal("10"),
            )
        )
    return tuple(candles)


def test_adapter_uses_decision_timeframe_not_source_timeframe():
    candles = minute_candles(180)
    dataset = SimpleNamespace(
        dataset_id="BTC/USDC:1m:fixture",
        version="sha256:" + "c" * 64,
        content_sha256="c" * 64,
        source="fixture",
        symbol="BTC/USDC",
        timeframe="1m",
    )
    run = SimpleNamespace(
        run_id="run-mtf",
        dataset=dataset,
        config=SimpleNamespace(
            system_id="balanced_v1",
            execution_assumptions={"decision_timeframe": "1h"},
        ),
        period_start=START + timedelta(hours=1),
        period_end=START + timedelta(hours=3),
    )
    opportunity = SimpleNamespace(
        opportunity_id="opp-mtf",
        snapshot_id="snap-mtf",
    )
    point = SimpleNamespace(
        observed_at=START + timedelta(hours=1),
        decision_timeframe="1h",
        opportunity=opportunity,
        feature_snapshot=SimpleNamespace(close=Decimal("100.69")),
        pipeline_result=SimpleNamespace(
            status=SimpleNamespace(value="NO_TRADE"),
            orchestration_result=SimpleNamespace(
                professor_decision=SimpleNamespace(direction="NO_TRADE"),
                trade_proposal=None,
            ),
        ),
    )
    replay = SimpleNamespace(
        backtest_result=SimpleNamespace(run=run),
        points=(point,),
    )

    report = build_forward_outcomes_report(replay, candles, horizons=(1, 2))

    assert report.source_timeframe == "1m"
    assert report.decision_timeframe == "1h"
    h1, h2 = report.records[0].horizons
    assert h1.is_complete is True
    assert h1.expected_end_at == START + timedelta(hours=2)
    assert h2.is_complete is True
    assert h2.expected_end_at == START + timedelta(hours=3)


def test_adapter_preserves_pipeline_terminal_status_and_direction():
    candles = []
    for index in range(4):
        opened = START + timedelta(hours=index)
        candles.append(
            Candle(
                symbol="BTC/USDC",
                timeframe="1h",
                open_time=opened,
                close_time=opened + timedelta(hours=1),
                open=Decimal("100"),
                high=Decimal("102"),
                low=Decimal("98"),
                close=Decimal("101"),
                volume=Decimal("10"),
            )
        )

    dataset = SimpleNamespace(
        dataset_id="BTC/USDC:1h:fixture",
        version="sha256:" + "d" * 64,
        content_sha256="d" * 64,
        source="fixture",
        symbol="BTC/USDC",
        timeframe="1h",
    )
    run = SimpleNamespace(
        run_id="run-direct",
        dataset=dataset,
        config=SimpleNamespace(system_id="balanced_v1", execution_assumptions={}),
        period_start=START + timedelta(hours=1),
        period_end=START + timedelta(hours=4),
    )
    opportunity = SimpleNamespace(opportunity_id="opp-1", snapshot_id="snap-1")
    point = SimpleNamespace(
        observed_at=START + timedelta(hours=1),
        decision_timeframe=None,
        opportunity=opportunity,
        feature_snapshot=SimpleNamespace(close=Decimal("101")),
        pipeline_result=SimpleNamespace(
            status=SimpleNamespace(value="RISK_REJECTED"),
            orchestration_result=SimpleNamespace(
                professor_decision=SimpleNamespace(direction="LONG"),
                trade_proposal=SimpleNamespace(side="LONG"),
            ),
        ),
    )
    replay = SimpleNamespace(
        backtest_result=SimpleNamespace(run=run),
        points=(point,),
    )

    report = build_forward_outcomes_report(replay, tuple(candles), horizons=(1,))
    record = report.records[0]
    assert record.terminal_status == "RISK_REJECTED"
    assert record.professor_direction == "LONG"
    assert record.proposal_side == "LONG"
