from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from app.market.features.multitimeframe import (
    build_multi_timeframe_feature_context,
)
from app.market.models import Candle
from app.market.structure import (
    MARKET_STRUCTURE_VERSION,
    build_market_structure_context,
)
from app.services.decision_context import (
    AGENT_CONTEXT_BINDING_VERSION,
    ContextAvailability,
    OptionalContextSection,
    ProvenanceRecord,
    RISK_CONTEXT_BINDING_VERSION,
    build_decision_context,
)
from app.market.multitimeframe import (
    HistoricalMultiTimeframeCursor,
    timeframe_interval,
)

from .clock import ReplayClock, as_utc
from .dataset import DatasetRef, canonical_candle_rows
from .models import BacktestResult, BacktestRun, BacktestRunStatus


class FeatureEnginePort(Protocol):
    config: Any

    def compute(
        self,
        candles: Sequence[Any],
        *,
        symbol: str,
        timeframe: str,
        source_snapshot_id: str | None = None,
        observed_at: datetime | None = None,
    ) -> Any: ...


class ScannerPort(Protocol):
    config: Any

    def scan(
        self,
        current: Any,
        *,
        system_id: str,
        previous: Any | None = None,
    ) -> Any: ...


class PaperPipelinePort(Protocol):
    async def run(
        self,
        *,
        opportunity: Any,
        market_context: Any,
        now: datetime | None = None,
        decision_context: Any | None = None,
    ) -> Any: ...


class DynamicPortfolioProviderPort(Protocol):
    system_id: str
    initial_balance: Decimal
    last_account_state: Any | None

    def get_portfolio_state(self, *, system_id: str) -> Any | None: ...

    async def refresh_from_broker(
        self,
        broker: Any,
        *,
        observed_at: datetime,
        open_risk_amount: Decimal,
        correlated_risk_amount: Decimal | None = None,
    ) -> Any: ...


class MarketConstraintsProviderPort(Protocol):
    def get_market_constraints(self, *, symbol: str) -> Any | None: ...


class PositionLifecyclePort(Protocol):
    broker: Any
    system_id: str

    async def process_candle_open(
        self,
        row: dict[str, Any],
        *,
        observed_at: datetime,
        policy: Any,
    ) -> tuple[Any, ...]: ...

    async def process_candle_close(
        self,
        row: dict[str, Any],
        *,
        observed_at: datetime,
        policy: Any,
    ) -> tuple[Any, ...]: ...

    async def register_execution(
        self,
        pipeline_result: Any,
        *,
        observed_at: datetime,
    ) -> Any | None: ...

    async def open_risk_amount(self) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class HistoricalReplayPoint:
    observed_at: datetime
    visible_candle_count: int
    feature_snapshot: Any
    scan_result: Any
    decision_timeframe: str | None = None
    decision_visible_candle_count: int | None = None
    mtf_cursor_fingerprint: str | None = None
    mtf_candle_counts: tuple[tuple[str, int], ...] = ()
    mtf_feature_context: Any | None = None
    market_structure_context: Any | None = None
    decision_context: Any | None = None
    decision_portfolio_state: Any | None = None
    decision_market_constraints: Any | None = None
    pipeline_result: Any | None = None
    portfolio_state: Any | None = None
    account_state: Any | None = None
    exit_events: tuple[Any, ...] = ()

    @property
    def opportunity(self) -> Any | None:
        return getattr(self.scan_result, "opportunity", None)


@dataclass(frozen=True, slots=True)
class HistoricalReplayResult:
    backtest_result: BacktestResult
    points: tuple[HistoricalReplayPoint, ...]

    @property
    def opportunities(self) -> tuple[Any, ...]:
        return tuple(point.opportunity for point in self.points if point.opportunity is not None)

    @property
    def pipeline_results(self) -> tuple[Any, ...]:
        return tuple(
            point.pipeline_result for point in self.points if point.pipeline_result is not None
        )

    @property
    def exit_events(self) -> tuple[Any, ...]:
        return tuple(event for point in self.points for event in point.exit_events)


class HistoricalReplayCancelledError(RuntimeError):
    """Raised when an operator requests cooperative replay cancellation."""


class HistoricalReplayRunner:
    """Chronological bridge from historical candles to the existing PAPER pipeline.

    Batch 16.4 couples the dynamic lifecycle to deterministic OHLC resolution.
    Gaps are resolved at candle OPEN, non-gap stop/target touches at candle CLOSE,
    and every lifecycle exit occurs before the current close-time trading decision.
    Newly executed entries are protected only after their entry candle completed,
    preserving the no-look-ahead boundary.
    """

    def __init__(
        self,
        *,
        paper_pipeline: PaperPipelinePort,
        feature_engine: FeatureEnginePort | None = None,
        scanner: ScannerPort | None = None,
        clock: ReplayClock | None = None,
        min_history: int | None = None,
        portfolio_provider: DynamicPortfolioProviderPort | None = None,
        market_constraints_provider: MarketConstraintsProviderPort | None = None,
        position_lifecycle: PositionLifecyclePort | None = None,
        decision_timeframe: str | None = None,
        mtf_timeframes: Sequence[str] = (
            "15m", "1h", "4h", "1d"
        ),
        mtf_policy_version: str = "mtf-utc-closed-v1",
        mtf_feature_context_version: str = "mtf-feature-context-v1",
        decision_context_version: str = "decision-context-v1",
        agent_context_binding_version: str = AGENT_CONTEXT_BINDING_VERSION,
        market_structure_version: str = MARKET_STRUCTURE_VERSION,
        risk_context_binding_version: str = RISK_CONTEXT_BINDING_VERSION,
    ) -> None:
        if feature_engine is None:
            from app.market.features import FeatureEngine

            feature_engine = FeatureEngine()
        if scanner is None:
            from app.market.scanner import DeterministicScanner

            scanner = DeterministicScanner()

        if (portfolio_provider is None) != (position_lifecycle is None):
            raise ValueError(
                "portfolio_provider and position_lifecycle must be injected together"
            )
        if (
            portfolio_provider is None
            and hasattr(paper_pipeline, "paper_broker")
            and hasattr(paper_pipeline, "portfolio_provider")
        ):
            raise ValueError(
                "historical replay with PaperTradingPipeline requires the dynamic "
                "backtest portfolio provider and position lifecycle"
            )

        self.paper_pipeline = paper_pipeline
        self.feature_engine = feature_engine
        self.scanner = scanner
        self.clock = clock
        self.min_history = min_history
        self.portfolio_provider = portfolio_provider
        self.market_constraints_provider = market_constraints_provider
        self.position_lifecycle = position_lifecycle
        self.decision_timeframe = (
            decision_timeframe.strip().lower()
            if decision_timeframe is not None
            else None
        )
        self.mtf_timeframes = tuple(
            item.strip().lower() for item in mtf_timeframes
        )
        self.mtf_policy_version = mtf_policy_version.strip()
        self.mtf_feature_context_version = (
            mtf_feature_context_version.strip()
        )
        self.decision_context_version = decision_context_version.strip()
        self.agent_context_binding_version = agent_context_binding_version.strip()
        self.market_structure_version = market_structure_version.strip()
        self.risk_context_binding_version = risk_context_binding_version.strip()

    async def run(
        self,
        *,
        candles: Sequence[Any],
        run: BacktestRun,
        progress_callback: Callable[[int, int, datetime], None] | None = None,
        point_callback: Callable[[HistoricalReplayPoint], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> HistoricalReplayResult:
        rows = self._validated_rows(candles, run)
        self._validate_component_versions(run)
        self._validate_dynamic_stack(run)
        self._validate_mtf_mode(run)

        min_history = (
            self.min_history if self.min_history is not None else self._default_min_history()
        )
        if min_history <= 0:
            raise ValueError("min_history must be greater than zero")

        clock = self._clock_for_run(run)
        visible: list[dict[str, Any]] = []
        points: list[HistoricalReplayPoint] = []
        previous_feature: Any | None = None
        mtf_cursor = self._mtf_cursor_for_run(run)
        processed_candles = 0
        opportunity_count = 0
        executed_order_count = 0
        work_total = sum(
            1
            for item in rows
            if self._row_time(item, "close_time") <= run.period_end
        )
        work_done = 0

        for row in rows:
            if cancel_check is not None and cancel_check():
                raise HistoricalReplayCancelledError("historical replay cancelled by operator")

            lifecycle_row = self._lifecycle_row(row, run)
            open_at = self._row_time(row, "open_time")
            observed_at = self._row_time(row, "close_time")
            if observed_at > run.period_end:
                break

            work_done += 1
            if progress_callback is not None and (
                work_done == 1 or work_done % 10 == 0 or work_done == work_total
            ):
                progress_callback(work_done, work_total, observed_at)
            if work_done % 25 == 0:
                await asyncio.sleep(0)
                if cancel_check is not None and cancel_check():
                    raise HistoricalReplayCancelledError(
                        "historical replay cancelled by operator"
                    )

            visible.append(row)
            if observed_at >= run.period_start:
                processed_candles += 1

            if self.position_lifecycle is not None and open_at < clock.now():
                raise ValueError(
                    "dynamic historical replay requires non-overlapping chronological candles"
                )
            candle_exit_events: list[Any] = []
            if self.position_lifecycle is not None:
                clock.advance_to(open_at)
                candle_exit_events.extend(
                    await self.position_lifecycle.process_candle_open(
                        lifecycle_row,
                        observed_at=clock.now(),
                        policy=run.config.intrabar_policy,
                    )
                )
                await self._refresh_dynamic_portfolio(clock.now())

            clock.advance_to(observed_at)
            if self.position_lifecycle is not None:
                candle_exit_events.extend(
                    await self.position_lifecycle.process_candle_close(
                        lifecycle_row,
                        observed_at=clock.now(),
                        policy=run.config.intrabar_policy,
                    )
                )
                await self._refresh_dynamic_portfolio(clock.now())

            mtf_state = None
            decision_visible_count: int | None = None
            if mtf_cursor is not None:
                emitted = mtf_cursor.push(
                    self._row_to_candle(row, run)
                )
                if self.decision_timeframe not in emitted:
                    continue
                decision_series = mtf_cursor.series(
                    self.decision_timeframe
                )
                decision_visible_count = len(decision_series)
                if decision_visible_count < min_history:
                    continue
                feature_input = decision_series
                feature_timeframe = self.decision_timeframe
                mtf_state = mtf_cursor.state()
            else:
                if len(visible) < min_history:
                    continue
                feature_input = tuple(visible)
                feature_timeframe = run.dataset.timeframe

            feature = self.feature_engine.compute(
                feature_input,
                symbol=run.dataset.symbol,
                timeframe=feature_timeframe,
                observed_at=clock.now(),
            )
            scan_result = self.scanner.scan(
                feature,
                system_id=run.config.system_id,
                previous=previous_feature,
            )
            previous_feature = feature

            if observed_at < run.period_start:
                continue

            mtf_feature_context = None
            market_structure_context = None
            decision_context = None
            decision_portfolio_state = None
            decision_market_constraints = None
            opportunity = getattr(scan_result, "opportunity", None)
            pipeline_result = None
            if opportunity is not None:
                opportunity_count += 1
                if mtf_cursor is not None:
                    mtf_feature_context = (
                        build_multi_timeframe_feature_context(
                            feature_engine=self.feature_engine,
                            mtf_cursor=mtf_cursor,
                            observed_at=clock.now(),
                            decision_timeframe=self.decision_timeframe,
                            decision_feature=feature,
                            context_version=self.mtf_feature_context_version,
                        )
                    )
                    market_structure_context = (
                        build_market_structure_context(
                            mtf_cursor=mtf_cursor,
                            observed_at=clock.now(),
                            version=self.market_structure_version,
                        )
                    )
                    structure_missing = tuple(
                        [
                            f"missing:{item}"
                            for item in market_structure_context.missing_timeframes
                        ]
                        + [
                            f"incomplete:{item}"
                            for item in market_structure_context.incomplete_timeframes
                        ]
                    )
                    structure_section = OptionalContextSection(
                        status=ContextAvailability.AVAILABLE,
                        payload=market_structure_context.to_payload(),
                    )
                    structure_provenance = ProvenanceRecord(
                        component="structure",
                        source="closed_ohlcv_market_structure",
                        observed_at=clock.now(),
                        available_at=clock.now(),
                        quality=(
                            "COMPLETE"
                            if market_structure_context.all_structures_ready
                            else "PARTIAL"
                        ),
                        missing_fields=structure_missing,
                        source_fingerprint=(
                            market_structure_context.context_fingerprint
                        ),
                    )
                    decision_portfolio_state = self._current_portfolio_state(
                        run.config.system_id
                    )
                    decision_market_constraints = self._current_market_constraints(
                        run.dataset.symbol
                    )
                    decision_context = build_decision_context(
                        system_id=run.config.system_id,
                        as_of=clock.now(),
                        primary_timeframe=self.decision_timeframe,
                        timeframe_policy_version=self.mtf_policy_version,
                        market=mtf_feature_context,
                        portfolio_state=decision_portfolio_state,
                        market_constraints=decision_market_constraints,
                        structure=structure_section,
                        provenance={"structure": structure_provenance},
                        context_version=self.decision_context_version,
                    )
                pipeline_kwargs = {
                    "opportunity": opportunity,
                    "market_context": feature,
                    "now": clock.now(),
                }
                if decision_context is not None:
                    pipeline_kwargs["decision_context"] = decision_context
                pipeline_result = await self.paper_pipeline.run(
                    **pipeline_kwargs
                )
                if self._is_executed(pipeline_result):
                    executed_order_count += 1
                    if self.position_lifecycle is not None:
                        await self.position_lifecycle.register_execution(
                            pipeline_result,
                            observed_at=clock.now(),
                        )
                        await self._refresh_dynamic_portfolio(clock.now())

            point = HistoricalReplayPoint(
                observed_at=clock.now(),
                visible_candle_count=len(visible),
                feature_snapshot=feature,
                decision_timeframe=self.decision_timeframe,
                decision_visible_candle_count=decision_visible_count,
                mtf_cursor_fingerprint=(
                    mtf_state.cursor_fingerprint
                    if mtf_state is not None
                    else None
                ),
                mtf_candle_counts=(
                    mtf_state.candle_counts
                    if mtf_state is not None
                    else ()
                ),
                mtf_feature_context=mtf_feature_context,
                market_structure_context=market_structure_context,
                decision_context=decision_context,
                decision_portfolio_state=decision_portfolio_state,
                decision_market_constraints=decision_market_constraints,
                scan_result=scan_result,
                pipeline_result=pipeline_result,
                portfolio_state=self._current_portfolio_state(run.config.system_id),
                account_state=self._current_account_state(),
                exit_events=tuple(candle_exit_events),
            )
            points.append(point)
            if point_callback is not None:
                point_callback(point)

        if progress_callback is not None and work_total > 0:
            progress_callback(work_total, work_total, run.period_end)

        return HistoricalReplayResult(
            backtest_result=BacktestResult(
                run=run,
                status=BacktestRunStatus.COMPLETED,
                processed_candles=processed_candles,
                opportunity_count=opportunity_count,
                executed_order_count=executed_order_count,
            ),
            points=tuple(points),
        )

    async def _refresh_dynamic_portfolio(self, observed_at: datetime) -> Any | None:
        if self.portfolio_provider is None or self.position_lifecycle is None:
            return None
        open_risk = await self.position_lifecycle.open_risk_amount()
        return await self.portfolio_provider.refresh_from_broker(
            self.position_lifecycle.broker,
            observed_at=observed_at,
            open_risk_amount=open_risk,
        )

    def _current_portfolio_state(self, system_id: str) -> Any | None:
        if self.portfolio_provider is None:
            return None
        return self.portfolio_provider.get_portfolio_state(system_id=system_id)

    def _current_market_constraints(self, symbol: str) -> Any | None:
        if self.market_constraints_provider is None:
            return None
        try:
            return self.market_constraints_provider.get_market_constraints(
                symbol=symbol
            )
        except Exception:
            # Informational agent context stays missing on a transient read
            # failure. PAPER/Risk performs its own authoritative read later.
            return None

    def _current_account_state(self) -> Any | None:
        if self.portfolio_provider is None:
            return None
        return self.portfolio_provider.last_account_state

    def _clock_for_run(self, run: BacktestRun) -> ReplayClock:
        if self.clock is None:
            return ReplayClock.start(run.dataset.start_at)
        if self.clock.now() != run.dataset.start_at:
            raise ValueError(
                "injected ReplayClock must start at BacktestRun.dataset.start_at"
            )
        return self.clock

    def _validated_rows(
        self,
        candles: Sequence[Any],
        run: BacktestRun,
    ) -> tuple[dict[str, Any], ...]:
        rows = canonical_candle_rows(
            candles,
            expected_symbol=run.dataset.symbol,
            expected_timeframe=run.dataset.timeframe,
        )
        if any(not bool(row["is_closed"]) for row in rows):
            raise ValueError("historical replay requires closed candles only")

        actual_ref = DatasetRef.from_candles(
            rows,
            symbol=run.dataset.symbol,
            timeframe=run.dataset.timeframe,
            source=run.dataset.source,
        )
        if actual_ref.content_sha256 != run.dataset.content_sha256:
            raise ValueError("historical candle content does not match BacktestRun.dataset")
        if actual_ref.candle_count != run.dataset.candle_count:
            raise ValueError("historical candle count does not match BacktestRun.dataset")
        return rows

    def _validate_component_versions(self, run: BacktestRun) -> None:
        feature_config = getattr(self.feature_engine, "config", None)
        feature_version = getattr(feature_config, "feature_version", None)
        scanner_version = getattr(getattr(self.scanner, "config", None), "scanner_version", None)
        if feature_version != run.config.feature_version:
            raise ValueError(
                "Feature Engine version does not match BacktestConfig.feature_version"
            )
        if scanner_version != run.config.scanner_version:
            raise ValueError("Scanner version does not match BacktestConfig.scanner_version")

    def _validate_mtf_mode(self, run: BacktestRun) -> None:
        if self.decision_timeframe is None:
            return
        if not self.mtf_policy_version:
            raise ValueError("mtf_policy_version must not be empty")
        if not self.mtf_feature_context_version:
            raise ValueError("mtf_feature_context_version must not be empty")
        if not self.decision_context_version:
            raise ValueError("decision_context_version must not be empty")
        if not self.agent_context_binding_version:
            raise ValueError("agent_context_binding_version must not be empty")
        if not self.market_structure_version:
            raise ValueError("market_structure_version must not be empty")
        if not self.risk_context_binding_version:
            raise ValueError("risk_context_binding_version must not be empty")
        if not self.mtf_timeframes:
            raise ValueError("mtf_timeframes must not be empty")
        if len(set(self.mtf_timeframes)) != len(self.mtf_timeframes):
            raise ValueError("mtf_timeframes must be unique")
        if self.decision_timeframe not in self.mtf_timeframes:
            raise ValueError(
                "decision_timeframe must be included in mtf_timeframes"
            )

        source_interval = timeframe_interval(run.dataset.timeframe)
        decision_interval = timeframe_interval(self.decision_timeframe)
        source_seconds = int(source_interval.total_seconds())
        decision_seconds = int(decision_interval.total_seconds())
        if decision_seconds < source_seconds:
            raise ValueError(
                "decision_timeframe cannot be smaller than dataset timeframe"
            )
        if decision_seconds % source_seconds != 0:
            raise ValueError(
                "decision_timeframe must be divisible by dataset timeframe"
            )

        expected = {
            "historical_source_timeframe": run.dataset.timeframe,
            "decision_timeframe": self.decision_timeframe,
            "mtf_timeframes": ",".join(self.mtf_timeframes),
            "mtf_policy_version": self.mtf_policy_version,
            "mtf_feature_context_version": self.mtf_feature_context_version,
            "decision_context_version": self.decision_context_version,
            "agent_context_binding_version": self.agent_context_binding_version,
            "market_structure_version": self.market_structure_version,
            "risk_context_binding_version": self.risk_context_binding_version,
            "lifecycle_timeframe": run.dataset.timeframe,
        }
        assumptions = run.config.execution_assumptions
        for key, value in expected.items():
            if assumptions.get(key) != value:
                raise ValueError(
                    "MTF replay requires execution_assumptions "
                    f"{key}={value!r}"
                )

    def _mtf_cursor_for_run(
        self,
        run: BacktestRun,
    ) -> HistoricalMultiTimeframeCursor | None:
        if self.decision_timeframe is None:
            return None
        return HistoricalMultiTimeframeCursor(
            source_timeframe=run.dataset.timeframe,
            target_timeframes=self.mtf_timeframes,
            policy_version=self.mtf_policy_version,
        )

    def _row_to_candle(
        self,
        row: dict[str, Any],
        run: BacktestRun,
    ) -> Candle:
        return Candle(
            symbol=run.dataset.symbol,
            timeframe=run.dataset.timeframe,
            open_time=self._row_time(row, "open_time"),
            close_time=self._row_time(row, "close_time"),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=Decimal(str(row["volume"])),
            is_closed=bool(row["is_closed"]),
        )

    def _validate_dynamic_stack(self, run: BacktestRun) -> None:
        pipeline_constraints_provider = getattr(
            self.paper_pipeline,
            "market_constraints_provider",
            None,
        )
        if (
            self.market_constraints_provider is not None
            and pipeline_constraints_provider is not None
            and pipeline_constraints_provider is not self.market_constraints_provider
        ):
            raise ValueError(
                "PaperTradingPipeline and HistoricalReplayRunner must share "
                "one market constraints provider"
            )
        if (
            self.decision_timeframe is not None
            and pipeline_constraints_provider is not None
            and self.market_constraints_provider is None
        ):
            raise ValueError(
                "MTF replay with PaperTradingPipeline requires the shared "
                "market constraints provider"
            )

        if self.portfolio_provider is None or self.position_lifecycle is None:
            return
        if self.portfolio_provider.system_id != run.config.system_id:
            raise ValueError("portfolio provider system_id does not match BacktestConfig")
        if self.position_lifecycle.system_id != run.config.system_id:
            raise ValueError("position lifecycle system_id does not match BacktestConfig")

        pipeline_provider = getattr(self.paper_pipeline, "portfolio_provider", None)
        if pipeline_provider is not None and pipeline_provider is not self.portfolio_provider:
            raise ValueError(
                "PaperTradingPipeline must use the injected backtest portfolio provider"
            )
        pipeline_broker = getattr(self.paper_pipeline, "paper_broker", None)
        if pipeline_broker is not None and pipeline_broker is not self.position_lifecycle.broker:
            raise ValueError("PaperTradingPipeline and lifecycle must share one PaperBroker")

        broker_config = getattr(self.position_lifecycle.broker, "config", None)
        if broker_config is None:
            return
        expected = {
            "system_id": run.config.system_id,
            "initial_balance": run.config.initial_balance,
            "maker_fee_bps": run.config.maker_fee_bps,
            "taker_fee_bps": run.config.taker_fee_bps,
            "market_slippage_bps": run.config.market_slippage_bps,
        }
        for field_name, expected_value in expected.items():
            if getattr(broker_config, field_name, None) != expected_value:
                raise ValueError(
                    f"PaperBroker config {field_name} does not match BacktestConfig"
                )
        if self.portfolio_provider.initial_balance != run.config.initial_balance:
            raise ValueError("portfolio initial_balance does not match BacktestConfig")

    def _default_min_history(self) -> int:
        warmup_bars = getattr(getattr(self.feature_engine, "config", None), "warmup_bars", None)
        if warmup_bars is None:
            raise ValueError(
                "feature_engine.config.warmup_bars is required when min_history is omitted"
            )
        return int(warmup_bars)


    @staticmethod
    def _lifecycle_row(row: dict[str, Any], run: BacktestRun) -> dict[str, Any]:
        enriched = dict(row)
        enriched["symbol"] = run.dataset.symbol
        enriched["timeframe"] = run.dataset.timeframe
        return enriched

    @staticmethod
    def _row_time(row: dict[str, Any], field_name: str) -> datetime:
        value = row[field_name]
        if isinstance(value, datetime):
            return as_utc(value, field=field_name)
        if isinstance(value, str):
            return as_utc(
                datetime.fromisoformat(value.replace("Z", "+00:00")),
                field=field_name,
            )
        raise ValueError(f"canonical {field_name} must be datetime or ISO-8601 string")

    @staticmethod
    def _is_executed(pipeline_result: Any) -> bool:
        status = getattr(pipeline_result, "status", None)
        status_value = getattr(status, "value", status)
        return status_value == "EXECUTED"


__all__ = [
    "HistoricalReplayPoint",
    "HistoricalReplayResult",
    "HistoricalReplayRunner",
    "PaperPipelinePort",
]
