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


class DynamicBroker:
    def __init__(self):
        self.config = SimpleNamespace(
            system_id=SYSTEM_ID,
            initial_balance=Decimal("100"),
            maker_fee_bps=Decimal("10"),
            taker_fee_bps=Decimal("20"),
            market_slippage_bps=Decimal("5"),
        )
        self.mark = Decimal("100")
        self.equity = Decimal("100")
        self.positions = []
        self.events = []

    async def process_price(self, symbol, price, *, observed_at=None):
        self.mark = Decimal(str(price))
        self.events.append(("mark", symbol, self.mark, observed_at))
        return ()

    async def get_account_state(self):
        gross = sum(position.quantity * self.mark for position in self.positions)
        return SimpleNamespace(
            system_id=SYSTEM_ID,
            equity=self.equity,
            gross_exposure=gross,
            open_positions=len(self.positions),
        )

    async def get_positions(self):
        return tuple(self.positions)

    async def set_stop_loss(self, symbol, stop_price, *, quantity=None):
        self.events.append(("stop", symbol, stop_price, quantity))
        return SimpleNamespace(symbol=symbol, stop_price=stop_price, quantity=quantity)


@dataclass(frozen=True)
class DynamicPosition:
    symbol: str
    quantity: Decimal
    average_entry: Decimal
    side: str = "LONG"

    @property
    def is_open(self):
        return self.quantity > 0


class DynamicPipeline:
    def __init__(self, *, broker, portfolio_provider):
        self.paper_broker = broker
        self.portfolio_provider = portfolio_provider
        self.calls = 0
        self.risk_states = []

    async def run(self, *, opportunity, market_context, now=None):
        del opportunity
        self.calls += 1
        self.risk_states.append(
            self.portfolio_provider.get_portfolio_state(system_id=SYSTEM_ID)
        )
        if self.calls > 1:
            return SimpleNamespace(status=SimpleNamespace(value="NO_TRADE"))

        position = DynamicPosition(
            symbol=SYMBOL,
            quantity=Decimal("1"),
            average_entry=Decimal(str(market_context.close)),
        )
        self.paper_broker.positions = [position]
        self.paper_broker.equity = Decimal("99.98")
        return SimpleNamespace(
            status=SimpleNamespace(value="EXECUTED"),
            position_after=position,
            risk_input=SimpleNamespace(
                side="LONG",
                stop_price=position.average_entry - Decimal("5"),
                proposal_id="proposal-dynamic-1",
            ),
            orchestration_result=SimpleNamespace(
                trade_proposal=SimpleNamespace(
                    targets=(position.average_entry + Decimal("10"),)
                )
            ),
            fill=SimpleNamespace(filled_at=now),
            opportunity_id="opp-dynamic-1",
        )


@sync_test
async def test_runner_refreshes_dynamic_portfolio_before_risk_and_after_execution():
    from app.services.backtest import (
        BacktestPortfolioStateProvider,
        HistoricalPositionLifecycle,
    )

    candles = [candle(index) for index in range(3)]
    run = make_run(candles)
    broker = DynamicBroker()
    provider = BacktestPortfolioStateProvider(SYSTEM_ID, Decimal("100"))
    lifecycle = HistoricalPositionLifecycle(broker=broker, system_id=SYSTEM_ID)
    pipeline = DynamicPipeline(broker=broker, portfolio_provider=provider)
    runner = HistoricalReplayRunner(
        paper_pipeline=pipeline,
        feature_engine=RecordingFeatureEngine(),
        scanner=RecordingScanner(),
        portfolio_provider=provider,
        position_lifecycle=lifecycle,
    )

    result = await runner.run(candles=candles, run=run)

    assert pipeline.risk_states[0].equity == Decimal("100")
    assert pipeline.risk_states[0].open_positions == 0
    first_point = result.points[0]
    assert first_point.portfolio_state.equity == Decimal("99.98")
    assert first_point.portfolio_state.open_positions == 1
    assert first_point.portfolio_state.open_risk_amount == Decimal("5")
    assert first_point.account_state.open_positions == 1
    first_entry_close = Decimal(str(candles[1]["close"]))
    current_candle_marks = [
        event
        for event in broker.events
        if event[0] == "mark" and event[2] in {candles[1]["open"], first_entry_close}
    ]
    stop_events = [event for event in broker.events if event[0] == "stop"]
    assert current_candle_marks
    assert stop_events
    assert broker.events.index(stop_events[0]) > broker.events.index(current_candle_marks[-1])


@sync_test
async def test_runner_rejects_dynamic_stack_not_shared_with_pipeline():
    from app.services.backtest import (
        BacktestPortfolioStateProvider,
        HistoricalPositionLifecycle,
    )

    candles = [candle(index) for index in range(3)]
    run = make_run(candles)
    broker = DynamicBroker()
    provider = BacktestPortfolioStateProvider(SYSTEM_ID, Decimal("100"))
    other_provider = BacktestPortfolioStateProvider(SYSTEM_ID, Decimal("100"))
    lifecycle = HistoricalPositionLifecycle(broker=broker, system_id=SYSTEM_ID)
    pipeline = DynamicPipeline(broker=broker, portfolio_provider=other_provider)
    runner = HistoricalReplayRunner(
        paper_pipeline=pipeline,
        feature_engine=RecordingFeatureEngine(),
        scanner=RecordingScanner(),
        portfolio_provider=provider,
        position_lifecycle=lifecycle,
    )

    with pytest.raises(ValueError, match="must use the injected backtest portfolio provider"):
        await runner.run(candles=candles, run=run)


def test_real_pipeline_shape_cannot_silently_use_static_portfolio_state():
    fake_real_pipeline = SimpleNamespace(
        paper_broker=object(),
        portfolio_provider=object(),
    )

    with pytest.raises(ValueError, match="requires the dynamic backtest portfolio"):
        HistoricalReplayRunner(
            paper_pipeline=fake_real_pipeline,
            feature_engine=RecordingFeatureEngine(),
            scanner=RecordingScanner(),
        )
