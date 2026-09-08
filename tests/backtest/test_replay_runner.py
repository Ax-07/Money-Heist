from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.backtest import (
    BacktestConfig,
    BacktestRun,
    DatasetRef,
    HistoricalReplayRunner,
    ReplayClock,
    stable_uuid,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
SYMBOL = "BTC/EUR"
TIMEFRAME = "5m"
SYSTEM_ID = "balanced_v1"


def sync_test(func):
    def wrapper():
        return asyncio.run(func())

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


def candle(index: int, *, close: Decimal | None = None, is_closed: bool = True):
    open_time = START + timedelta(minutes=5 * index)
    base = Decimal("100") + index
    close_price = close if close is not None else base + Decimal("0.25")
    return {
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "open_time": open_time,
        "close_time": open_time + timedelta(minutes=5),
        "open": base,
        "high": max(base + Decimal("1"), close_price),
        "low": min(base - Decimal("1"), close_price),
        "close": close_price,
        "volume": Decimal("1000") + index,
        "is_closed": is_closed,
    }


def make_run(candles):
    dataset = DatasetRef.from_candles(
        candles,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        source="fixture",
    )
    config = BacktestConfig(
        system_id=SYSTEM_ID,
        risk_version="batch05-risk-v1",
        feature_version="feature-engine-v1",
        scanner_version="scanner-v1",
    )
    return BacktestRun.create(dataset=dataset, config=config)


@dataclass(frozen=True)
class FeatureConfig:
    feature_version: str = "feature-engine-v1"
    warmup_bars: int = 2


class RecordingFeatureEngine:
    def __init__(self):
        self.config = FeatureConfig()
        self.calls: list[dict[str, Any]] = []

    def compute(
        self,
        candles,
        *,
        symbol,
        timeframe,
        source_snapshot_id=None,
        observed_at=None,
    ):
        del source_snapshot_id
        frozen = tuple(dict(item) for item in candles)
        self.calls.append(
            {
                "candles": frozen,
                "symbol": symbol,
                "timeframe": timeframe,
                "observed_at": observed_at,
            }
        )
        return SimpleNamespace(
            snapshot_id=stable_uuid(
                "test-feature",
                {
                    "candles": frozen,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "observed_at": observed_at,
                },
            ),
            observed_at=observed_at,
            symbol=symbol,
            timeframe=timeframe,
            close=Decimal(str(frozen[-1]["close"])),
        )


@dataclass(frozen=True)
class ScannerConfig:
    scanner_version: str = "scanner-v1"


class RecordingScanner:
    def __init__(self, *, emit: bool = True):
        self.config = ScannerConfig()
        self.emit = emit
        self.calls = []

    def scan(self, current, *, system_id, previous=None):
        self.calls.append((current, system_id, previous))
        opportunity = None
        if self.emit:
            opportunity = SimpleNamespace(
                opportunity_id=stable_uuid(
                    "test-opportunity",
                    {"snapshot_id": current.snapshot_id, "system_id": system_id},
                ),
                snapshot_id=current.snapshot_id,
                system_id=system_id,
                symbol=current.symbol,
                timeframe=current.timeframe,
            )
        return SimpleNamespace(opportunity=opportunity)


class RecordingPaperPipeline:
    def __init__(self, *, status: str = "EXECUTED"):
        self.status = status
        self.calls = []

    async def run(self, *, opportunity, market_context, now=None):
        self.calls.append((opportunity, market_context, now))
        return SimpleNamespace(status=SimpleNamespace(value=self.status))


@sync_test
async def test_runner_replays_chronologically_and_forwards_only_visible_history():
    candles = [candle(index) for index in range(4)]
    run = make_run(candles)
    feature_engine = RecordingFeatureEngine()
    scanner = RecordingScanner()
    pipeline = RecordingPaperPipeline()
    runner = HistoricalReplayRunner(
        paper_pipeline=pipeline,
        feature_engine=feature_engine,
        scanner=scanner,
    )

    result = await runner.run(candles=candles, run=run)

    assert [point.visible_candle_count for point in result.points] == [2, 3, 4]
    assert [len(call["candles"]) for call in feature_engine.calls] == [2, 3, 4]
    assert [point.observed_at for point in result.points] == [
        candles[1]["close_time"],
        candles[2]["close_time"],
        candles[3]["close_time"],
    ]
    assert all(call[2] == call[1].observed_at for call in pipeline.calls)
    assert len(pipeline.calls) == 3
    assert result.backtest_result.processed_candles == 4
    assert result.backtest_result.opportunity_count == 3
    assert result.backtest_result.executed_order_count == 3


@sync_test
async def test_future_candle_change_cannot_change_prior_replay_points():
    base = [candle(index) for index in range(5)]
    changed = [dict(item) for item in base]
    changed[-1] = candle(4, close=Decimal("150"))

    first_engine = RecordingFeatureEngine()
    second_engine = RecordingFeatureEngine()
    first = HistoricalReplayRunner(
        paper_pipeline=RecordingPaperPipeline(),
        feature_engine=first_engine,
        scanner=RecordingScanner(),
    )
    second = HistoricalReplayRunner(
        paper_pipeline=RecordingPaperPipeline(),
        feature_engine=second_engine,
        scanner=RecordingScanner(),
    )

    first_result = await first.run(candles=base, run=make_run(base))
    second_result = await second.run(candles=changed, run=make_run(changed))

    assert [point.feature_snapshot.snapshot_id for point in first_result.points[:-1]] == [
        point.feature_snapshot.snapshot_id for point in second_result.points[:-1]
    ]
    assert [call["candles"] for call in first_engine.calls[:-1]] == [
        call["candles"] for call in second_engine.calls[:-1]
    ]
    assert (
        first_result.points[-1].feature_snapshot.snapshot_id
        != second_result.points[-1].feature_snapshot.snapshot_id
    )


@sync_test
async def test_runner_rejects_dataset_content_mismatch_before_any_pipeline_call():
    candles = [candle(index) for index in range(4)]
    run = make_run(candles)
    mutated = [dict(item) for item in candles]
    mutated[-1] = candle(3, close=Decimal("140"))
    pipeline = RecordingPaperPipeline()
    runner = HistoricalReplayRunner(
        paper_pipeline=pipeline,
        feature_engine=RecordingFeatureEngine(),
        scanner=RecordingScanner(),
    )

    with pytest.raises(ValueError, match="does not match BacktestRun.dataset"):
        await runner.run(candles=mutated, run=run)

    assert pipeline.calls == []


@sync_test
async def test_runner_rejects_open_historical_candles():
    candles = [candle(0), candle(1), candle(2, is_closed=False)]
    run = make_run(candles)
    runner = HistoricalReplayRunner(
        paper_pipeline=RecordingPaperPipeline(),
        feature_engine=RecordingFeatureEngine(),
        scanner=RecordingScanner(),
    )

    with pytest.raises(ValueError, match="closed candles only"):
        await runner.run(candles=candles, run=run)


@sync_test
async def test_runner_enforces_feature_and_scanner_versions():
    candles = [candle(index) for index in range(3)]
    run = make_run(candles)
    feature_engine = RecordingFeatureEngine()
    feature_engine.config = FeatureConfig(feature_version="wrong-version")
    runner = HistoricalReplayRunner(
        paper_pipeline=RecordingPaperPipeline(),
        feature_engine=feature_engine,
        scanner=RecordingScanner(),
    )

    with pytest.raises(ValueError, match="Feature Engine version"):
        await runner.run(candles=candles, run=run)

@sync_test
async def test_runner_defaults_to_existing_feature_engine_and_scanner():
    pytest.importorskip("app.market.features")
    pytest.importorskip("app.market.scanner")

    candles = [candle(index) for index in range(36)]
    candles[-1] = candle(35, close=Decimal("180"))
    run = make_run(candles)
    pipeline = RecordingPaperPipeline()
    runner = HistoricalReplayRunner(paper_pipeline=pipeline)

    result = await runner.run(candles=candles, run=run)

    assert result.points
    assert result.points[-1].visible_candle_count == len(candles)
    assert result.points[-1].feature_snapshot.observed_at == candles[-1]["close_time"]
    assert result.backtest_result.opportunity_count >= 1
    assert pipeline.calls

@sync_test
async def test_runner_can_share_replay_clock_with_injected_pipeline_stack():
    candles = [candle(index) for index in range(3)]
    run = make_run(candles)
    clock = ReplayClock.start(run.dataset.start_at)
    pipeline = RecordingPaperPipeline()
    runner = HistoricalReplayRunner(
        paper_pipeline=pipeline,
        feature_engine=RecordingFeatureEngine(),
        scanner=RecordingScanner(),
        clock=clock,
    )

    result = await runner.run(candles=candles, run=run)

    assert clock.now() == candles[-1]["close_time"]
    assert pipeline.calls[-1][2] == clock.now()
    assert result.points[-1].observed_at == clock.now()

