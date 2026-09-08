from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

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
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class HistoricalReplayPoint:
    observed_at: datetime
    visible_candle_count: int
    feature_snapshot: Any
    scan_result: Any
    pipeline_result: Any | None = None

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


class HistoricalReplayRunner:
    """Chronological bridge from historical candles to the existing PAPER pipeline.

    The runner owns chronology only. Trading decisions remain in the existing
    Feature Engine, Scanner, orchestration, Risk Engine and Paper Broker stack.
    Historical position lifecycle, intrabar stop/target handling and dynamic
    portfolio accounting are intentionally deferred to later Batch 16 stages.
    """

    def __init__(
        self,
        *,
        paper_pipeline: PaperPipelinePort,
        feature_engine: FeatureEnginePort | None = None,
        scanner: ScannerPort | None = None,
        clock: ReplayClock | None = None,
        min_history: int | None = None,
    ) -> None:
        if feature_engine is None:
            from app.market.features import FeatureEngine

            feature_engine = FeatureEngine()
        if scanner is None:
            from app.market.scanner import DeterministicScanner

            scanner = DeterministicScanner()

        self.paper_pipeline = paper_pipeline
        self.feature_engine = feature_engine
        self.scanner = scanner
        self.clock = clock
        self.min_history = min_history

    async def run(
        self,
        *,
        candles: Sequence[Any],
        run: BacktestRun,
    ) -> HistoricalReplayResult:
        rows = self._validated_rows(candles, run)
        self._validate_component_versions(run)

        min_history = (
            self.min_history if self.min_history is not None else self._default_min_history()
        )
        if min_history <= 0:
            raise ValueError("min_history must be greater than zero")

        clock = self._clock_for_run(run)
        visible: list[dict[str, Any]] = []
        points: list[HistoricalReplayPoint] = []
        previous_feature: Any | None = None
        processed_candles = 0
        opportunity_count = 0
        executed_order_count = 0

        for row in rows:
            observed_at = self._row_close_time(row)
            if observed_at > run.period_end:
                break

            visible.append(row)
            if observed_at >= run.period_start:
                processed_candles += 1

            if len(visible) < min_history:
                continue

            clock.advance_to(observed_at)
            feature = self.feature_engine.compute(
                tuple(visible),
                symbol=run.dataset.symbol,
                timeframe=run.dataset.timeframe,
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

            opportunity = getattr(scan_result, "opportunity", None)
            pipeline_result = None
            if opportunity is not None:
                opportunity_count += 1
                pipeline_result = await self.paper_pipeline.run(
                    opportunity=opportunity,
                    market_context=feature,
                    now=clock.now(),
                )
                if self._is_executed(pipeline_result):
                    executed_order_count += 1

            points.append(
                HistoricalReplayPoint(
                    observed_at=clock.now(),
                    visible_candle_count=len(visible),
                    feature_snapshot=feature,
                    scan_result=scan_result,
                    pipeline_result=pipeline_result,
                )
            )

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

    def _default_min_history(self) -> int:
        warmup_bars = getattr(getattr(self.feature_engine, "config", None), "warmup_bars", None)
        if warmup_bars is None:
            raise ValueError(
                "feature_engine.config.warmup_bars is required when min_history is omitted"
            )
        return int(warmup_bars)

    @staticmethod
    def _row_close_time(row: dict[str, Any]) -> datetime:
        value = row["close_time"]
        if isinstance(value, datetime):
            return as_utc(value, field="close_time")
        if isinstance(value, str):
            return as_utc(
                datetime.fromisoformat(value.replace("Z", "+00:00")),
                field="close_time",
            )
        raise ValueError("canonical close_time must be datetime or ISO-8601 string")

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
