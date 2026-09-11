from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.market.multitimeframe import resample_closed_candles
from app.services.backtest import (
    BacktestConfig,
    BacktestRun,
    DatasetRef,
    HistoricalReplayRunner,
    stable_uuid,
)


START = datetime(2026, 9, 1, tzinfo=UTC)
SYMBOL = "BTC/USDC"
SYSTEM_ID = "balanced_v1"


def _sync_test(func):
    def wrapper():
        return asyncio.run(func())

    wrapper.__name__ = func.__name__
    return wrapper


def _minute_candles(count: int):
    output = []
    for index in range(count):
        opened = START + timedelta(minutes=index)
        price = Decimal("100") + Decimal(index) / Decimal("10")
        output.append(
            {
                "symbol": SYMBOL,
                "timeframe": "1m",
                "open_time": opened,
                "close_time": opened + timedelta(minutes=1),
                "open": price,
                "high": price + Decimal("1"),
                "low": price - Decimal("1"),
                "close": price + Decimal("0.25"),
                "volume": Decimal("10") + index,
                "is_closed": True,
            }
        )
    return output


def _as_candle(item):
    from app.market.models import Candle

    return Candle(**item)


def _run(candles, *, timeframe, assumptions=None):
    dataset = DatasetRef.from_candles(
        candles,
        symbol=SYMBOL,
        timeframe=timeframe,
        source="fixture",
    )
    config = BacktestConfig(
        system_id=SYSTEM_ID,
        risk_version="batch05-risk-v1",
        feature_version="feature-engine-v1",
        scanner_version="scanner-v1",
        execution_assumptions=assumptions or {},
    )
    return BacktestRun.create(dataset=dataset, config=config)


@dataclass(frozen=True)
class _FeatureConfig:
    feature_version: str = "feature-engine-v1"
    warmup_bars: int = 1


class _FeatureEngine:
    def __init__(self):
        self.config = _FeatureConfig()
        self.calls = []

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
        frozen = tuple(candles)
        last = frozen[-1]
        close = last["close"] if isinstance(last, dict) else last.close
        self.calls.append(
            {
                "count": len(frozen),
                "timeframe": timeframe,
                "observed_at": observed_at,
                "close": Decimal(str(close)),
            }
        )
        return SimpleNamespace(
            snapshot_id=stable_uuid(
                "mtf-test-feature",
                {
                    "count": len(frozen),
                    "timeframe": timeframe,
                    "observed_at": observed_at,
                    "close": close,
                },
            ),
            observed_at=observed_at,
            symbol=symbol,
            timeframe=timeframe,
            close=Decimal(str(close)),
        )


@dataclass(frozen=True)
class _ScannerConfig:
    scanner_version: str = "scanner-v1"


class _Scanner:
    def __init__(self):
        self.config = _ScannerConfig()
        self.calls = []

    def scan(self, current, *, system_id, previous=None):
        self.calls.append(
            (
                current.observed_at,
                current.timeframe,
                current.close,
                previous.observed_at if previous else None,
            )
        )
        return SimpleNamespace(opportunity=None)


class _Pipeline:
    async def run(self, *, opportunity, market_context, now=None):
        raise AssertionError(
            "pipeline must not run when scanner emits no opportunity"
        )


def _mtf_assumptions():
    return {
        "historical_source_timeframe": "1m",
        "decision_timeframe": "1h",
        "mtf_timeframes": "15m,1h,4h,1d",
        "mtf_policy_version": "mtf-utc-closed-v1",
        "mtf_feature_context_version": "mtf-feature-context-v1",
        "decision_context_version": "decision-context-v1",
        "agent_context_binding_version": "decision-context-agent-binding-v1",
        "market_structure_version": "market-structure-v1",
        "risk_context_binding_version": "portfolio-market-constraints-v1",
        "lifecycle_timeframe": "1m",
    }


@_sync_test
async def test_mtf_runner_scans_only_on_closed_1h_decision_candles():
    candles = _minute_candles(120)
    engine = _FeatureEngine()
    scanner = _Scanner()
    runner = HistoricalReplayRunner(
        paper_pipeline=_Pipeline(),
        feature_engine=engine,
        scanner=scanner,
        decision_timeframe="1h",
        mtf_timeframes=("15m", "1h", "4h", "1d"),
        min_history=1,
    )

    result = await runner.run(
        candles=candles,
        run=_run(
            candles,
            timeframe="1m",
            assumptions=_mtf_assumptions(),
        ),
    )

    assert len(result.points) == 2
    assert [call["timeframe"] for call in engine.calls] == ["1h", "1h"]
    assert [call["count"] for call in engine.calls] == [1, 2]
    assert [point.observed_at for point in result.points] == [
        START + timedelta(hours=1),
        START + timedelta(hours=2),
    ]
    assert [point.visible_candle_count for point in result.points] == [60, 120]
    assert [
        point.decision_visible_candle_count for point in result.points
    ] == [1, 2]
    assert result.backtest_result.processed_candles == 120
    assert dict(result.points[-1].mtf_candle_counts) == {
        "15m": 8,
        "1h": 2,
        "4h": 0,
        "1d": 0,
    }
    assert result.points[-1].mtf_cursor_fingerprint


@_sync_test
async def test_1m_mtf_decision_series_matches_direct_1h_replay():
    minute = _minute_candles(180)
    hourly = resample_closed_candles(
        tuple(_as_candle(item) for item in minute),
        target_timeframe="1h",
    )

    direct_engine = _FeatureEngine()
    direct_scanner = _Scanner()
    direct_runner = HistoricalReplayRunner(
        paper_pipeline=_Pipeline(),
        feature_engine=direct_engine,
        scanner=direct_scanner,
        min_history=1,
    )
    await direct_runner.run(
        candles=hourly,
        run=_run(hourly, timeframe="1h"),
    )

    mtf_engine = _FeatureEngine()
    mtf_scanner = _Scanner()
    mtf_runner = HistoricalReplayRunner(
        paper_pipeline=_Pipeline(),
        feature_engine=mtf_engine,
        scanner=mtf_scanner,
        decision_timeframe="1h",
        mtf_timeframes=("15m", "1h", "4h", "1d"),
        min_history=1,
    )
    await mtf_runner.run(
        candles=minute,
        run=_run(
            minute,
            timeframe="1m",
            assumptions=_mtf_assumptions(),
        ),
    )

    assert mtf_engine.calls == direct_engine.calls
    assert mtf_scanner.calls == direct_scanner.calls


class _OneOpportunityScanner:
    def __init__(self):
        self.config = _ScannerConfig()
        self.emitted = False

    def scan(self, current, *, system_id, previous=None):
        del previous
        opportunity = None
        if not self.emitted:
            self.emitted = True
            opportunity = SimpleNamespace(
                opportunity_id="mtf-feature-context-opportunity",
                snapshot_id=current.snapshot_id,
                system_id=system_id,
                symbol=current.symbol,
                timeframe=current.timeframe,
            )
        return SimpleNamespace(opportunity=opportunity)


class _RecordingPipeline:
    def __init__(self):
        self.calls = []

    async def run(
        self,
        *,
        opportunity,
        market_context,
        now=None,
        decision_context=None,
    ):
        self.calls.append((opportunity, market_context, now, decision_context))
        return SimpleNamespace(status=SimpleNamespace(value="NO_TRADE"))


@_sync_test
async def test_mtf_feature_context_is_built_only_for_opportunity_and_pipeline_stays_1h():
    from app.market.features import FeatureEngine

    candles = _minute_candles(36 * 60)
    pipeline = _RecordingPipeline()
    scanner = _OneOpportunityScanner()
    runner = HistoricalReplayRunner(
        paper_pipeline=pipeline,
        feature_engine=FeatureEngine(),
        scanner=scanner,
        decision_timeframe="1h",
        mtf_timeframes=("15m", "1h", "4h", "1d"),
    )

    result = await runner.run(
        candles=candles,
        run=_run(
            candles,
            timeframe="1m",
            assumptions=_mtf_assumptions(),
        ),
    )

    opportunity_points = [
        point for point in result.points if point.opportunity is not None
    ]
    assert len(opportunity_points) == 1
    point = opportunity_points[0]
    context = point.mtf_feature_context
    assert context is not None
    assert context.decision_timeframe == "1h"
    assert context.decision_snapshot is point.feature_snapshot
    assert set(context.snapshots) == {"15m", "1h", "4h", "1d"}
    assert "1d" in context.warmup_incomplete_timeframes
    assert len(pipeline.calls) == 1
    assert pipeline.calls[0][1] is point.feature_snapshot
    assert pipeline.calls[0][1].timeframe == "1h"


@_sync_test
async def test_decision_context_is_frozen_on_opportunity_without_changing_pipeline_input():
    from app.market.features import FeatureEngine
    from app.services.decision_context import ContextAvailability

    candles = _minute_candles(36 * 60)
    pipeline = _RecordingPipeline()
    scanner = _OneOpportunityScanner()
    runner = HistoricalReplayRunner(
        paper_pipeline=pipeline,
        feature_engine=FeatureEngine(),
        scanner=scanner,
        decision_timeframe="1h",
        mtf_timeframes=("15m", "1h", "4h", "1d"),
    )

    result = await runner.run(
        candles=candles,
        run=_run(
            candles,
            timeframe="1m",
            assumptions=_mtf_assumptions(),
        ),
    )

    point = next(point for point in result.points if point.opportunity is not None)
    context = point.decision_context
    assert context is not None
    assert context.market is point.mtf_feature_context
    assert context.as_of == point.observed_at
    assert context.primary_timeframe == "1h"
    assert context.derivatives.status is ContextAvailability.UNAVAILABLE
    assert context.statistics.status is ContextAvailability.UNAVAILABLE
    assert context.portfolio_summary is None
    assert context.market_constraints is None
    assert context.context_fingerprint
    assert len(pipeline.calls) == 1
    assert pipeline.calls[0][1] is point.feature_snapshot
    assert pipeline.calls[0][1].timeframe == "1h"
    assert pipeline.calls[0][3] is context


@_sync_test
async def test_market_structure_is_available_in_frozen_decision_context():
    from app.market.features import FeatureEngine
    from app.services.decision_context import ContextAvailability

    candles = _minute_candles(36 * 60)
    pipeline = _RecordingPipeline()
    scanner = _OneOpportunityScanner()
    runner = HistoricalReplayRunner(
        paper_pipeline=pipeline,
        feature_engine=FeatureEngine(),
        scanner=scanner,
        decision_timeframe="1h",
        mtf_timeframes=("15m", "1h", "4h", "1d"),
    )

    result = await runner.run(
        candles=candles,
        run=_run(
            candles,
            timeframe="1m",
            assumptions=_mtf_assumptions(),
        ),
    )

    point = next(point for point in result.points if point.opportunity is not None)
    structure = point.market_structure_context
    context = point.decision_context
    assert structure is not None
    assert context is not None
    assert context.structure.status is ContextAvailability.AVAILABLE
    assert "structure" not in context.missing_components
    assert context.provenance["structure"].source_fingerprint == (
        structure.context_fingerprint
    )
    assert (
        context.structure.payload["context_fingerprint"]
        == structure.context_fingerprint
    )
    assert context.microstructure.status is ContextAvailability.UNAVAILABLE
    for summary in structure.timeframes.values():
        assert summary.orderbook_available is False
        assert summary.liquidation_data_available is False

class _StaticPortfolioProvider:
    def __init__(self, state):
        self.system_id = SYSTEM_ID
        self.initial_balance = state.equity
        self.last_account_state = None
        self.state = state

    def get_portfolio_state(self, *, system_id):
        return self.state if system_id == self.system_id else None

    async def refresh_from_broker(
        self,
        broker,
        *,
        observed_at,
        open_risk_amount,
        correlated_risk_amount=None,
    ):
        del broker, observed_at, open_risk_amount, correlated_risk_amount
        return self.state


class _StaticLifecycle:
    def __init__(self):
        self.broker = object()
        self.system_id = SYSTEM_ID

    async def process_candle_open(self, row, *, observed_at, policy):
        del row, observed_at, policy
        return ()

    async def process_candle_close(self, row, *, observed_at, policy):
        del row, observed_at, policy
        return ()

    async def register_execution(self, pipeline_result, *, observed_at):
        del pipeline_result, observed_at
        return None

    async def open_risk_amount(self):
        return Decimal("0")


class _StaticMarketConstraintsProvider:
    def __init__(self, constraints):
        self.constraints = constraints
        self.calls = 0

    def get_market_constraints(self, *, symbol):
        self.calls += 1
        return self.constraints if symbol == SYMBOL else None


@_sync_test
async def test_decision_context_freezes_portfolio_and_market_constraints_pre_ai():
    from app.market.features import FeatureEngine
    from app.trading.risk.models import MarketConstraints, PortfolioRiskState

    portfolio_state = PortfolioRiskState(
        equity=Decimal("987.65"),
        day_start_equity=Decimal("1000"),
        equity_peak=Decimal("1025"),
        daily_pnl=Decimal("-12.35"),
        open_positions=2,
        open_risk_amount=Decimal("7.5"),
        correlated_risk_amount=Decimal("5"),
        gross_exposure_amount=Decimal("320"),
    )
    constraints = MarketConstraints(
        qty_step=Decimal("0.00001"),
        min_qty=Decimal("0.0001"),
        min_notional=Decimal("10"),
        max_qty=Decimal("5"),
        max_leverage=Decimal("2"),
    )
    portfolio = _StaticPortfolioProvider(portfolio_state)
    lifecycle = _StaticLifecycle()
    market_constraints = _StaticMarketConstraintsProvider(constraints)
    pipeline = _RecordingPipeline()
    scanner = _OneOpportunityScanner()
    candles = _minute_candles(36 * 60)

    runner = HistoricalReplayRunner(
        paper_pipeline=pipeline,
        feature_engine=FeatureEngine(),
        scanner=scanner,
        portfolio_provider=portfolio,
        position_lifecycle=lifecycle,
        market_constraints_provider=market_constraints,
        decision_timeframe="1h",
        mtf_timeframes=("15m", "1h", "4h", "1d"),
    )

    result = await runner.run(
        candles=candles,
        run=_run(
            candles,
            timeframe="1m",
            assumptions=_mtf_assumptions(),
        ),
    )

    point = next(point for point in result.points if point.opportunity is not None)
    context = point.decision_context
    assert context is not None
    assert point.decision_portfolio_state is portfolio_state
    assert point.decision_market_constraints is constraints

    summary = context.portfolio_summary
    assert summary is not None
    assert summary.equity == portfolio_state.equity
    assert summary.daily_pnl == portfolio_state.daily_pnl
    assert summary.open_positions == portfolio_state.open_positions
    assert summary.open_risk_amount == portfolio_state.open_risk_amount
    assert summary.gross_exposure_amount == portfolio_state.gross_exposure_amount

    market = context.market_constraints
    assert market is not None
    assert market.qty_step == constraints.qty_step
    assert market.min_qty == constraints.min_qty
    assert market.min_notional == constraints.min_notional
    assert market.max_qty == constraints.max_qty
    assert market.max_leverage == constraints.max_leverage

    assert "portfolio_summary" not in context.missing_components
    assert "market_constraints" not in context.missing_components
    assert context.provenance["portfolio_summary"].source == "portfolio_risk_state"
    assert context.provenance["market_constraints"].source == "market_constraints_provider"
    assert pipeline.calls[0][3] is context
    assert market_constraints.calls == 1
