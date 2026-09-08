from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .clock import as_utc
from .dataset import DatasetRef, canonical_candle_rows
from .ids import stable_uuid
from .models import BacktestConfig
from .reports import BacktestSplitReport, WalkForwardReport
from .splits import BacktestRunSet, BacktestSplitPlan


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    index: int
    window_id: str
    split: BacktestSplitPlan

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("walk-forward window index must be >= 1")
        if not self.window_id.strip():
            raise ValueError("window_id must not be empty")

    def runs(self, config: BacktestConfig) -> BacktestRunSet:
        return self.split.runs(config)


@dataclass(frozen=True, slots=True)
class WalkForwardPlan:
    plan_id: str
    dataset: DatasetRef
    design_bars: int
    validation_bars: int
    oos_bars: int
    step_bars: int
    windows: tuple[WalkForwardWindow, ...]

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("plan_id must not be empty")
        if not self.windows:
            raise ValueError("walk-forward plan requires at least one complete window")

    def run_sets(self, config: BacktestConfig) -> tuple[BacktestRunSet, ...]:
        """Create runs with one fixed config; V1 deliberately exposes no optimizer."""

        return tuple(window.runs(config) for window in self.windows)


WalkForwardSplitExecutor = Callable[
    [WalkForwardWindow, BacktestRunSet],
    Awaitable[BacktestSplitReport],
]


async def execute_walk_forward(
    plan: WalkForwardPlan,
    *,
    config: BacktestConfig,
    execute_split: WalkForwardSplitExecutor,
) -> WalkForwardReport:
    """Execute windows sequentially with one frozen config and explicit OOS reports."""

    reports: list[BacktestSplitReport] = []
    for window in plan.windows:
        run_set = window.runs(config)
        report = await execute_split(window, run_set)
        if report.split_id != window.split.split_id:
            raise ValueError("walk-forward executor returned report for the wrong split")
        reports.append(report)
    return WalkForwardReport(plan_id=plan.plan_id, windows=tuple(reports))


def _close_time(row: dict[str, Any]) -> datetime:
    value = row["close_time"]
    if isinstance(value, datetime):
        return as_utc(value, field="close_time")
    if isinstance(value, str):
        return as_utc(
            datetime.fromisoformat(value.replace("Z", "+00:00")),
            field="close_time",
        )
    raise ValueError("canonical close_time must be datetime or ISO-8601 string")


def build_walk_forward_plan(
    candles: Any,
    *,
    dataset: DatasetRef,
    design_bars: int,
    validation_bars: int,
    oos_bars: int,
    step_bars: int | None = None,
) -> WalkForwardPlan:
    """Build rolling DESIGN → VALIDATION → OOS windows on exact candle boundaries."""

    for field_name, value in (
        ("design_bars", design_bars),
        ("validation_bars", validation_bars),
        ("oos_bars", oos_bars),
    ):
        if value <= 0:
            raise ValueError(f"{field_name} must be > 0")
    step = oos_bars if step_bars is None else step_bars
    if step <= 0:
        raise ValueError("step_bars must be > 0")

    rows = canonical_candle_rows(
        candles,
        expected_symbol=dataset.symbol,
        expected_timeframe=dataset.timeframe,
    )
    actual = DatasetRef.from_candles(
        rows,
        symbol=dataset.symbol,
        timeframe=dataset.timeframe,
        source=dataset.source,
    )
    if actual.content_sha256 != dataset.content_sha256:
        raise ValueError("walk-forward candles do not match DatasetRef")

    span = design_bars + validation_bars + oos_bars
    close_times = tuple(_close_time(row) for row in rows)
    windows: list[WalkForwardWindow] = []
    start = 0
    while start + span <= len(rows):
        design_start = start
        validation_start = design_start + design_bars
        oos_start = validation_start + validation_bars
        end = oos_start + oos_bars

        split = BacktestSplitPlan.create(
            dataset=dataset,
            design_start=close_times[design_start],
            design_end=close_times[validation_start - 1],
            validation_start=close_times[validation_start],
            validation_end=close_times[oos_start - 1],
            oos_start=close_times[oos_start],
            oos_end=close_times[end - 1],
            label_prefix=f"wf-{len(windows) + 1:03d}",
        )
        window_payload = {
            "schema": "money-heist.walk-forward-window.v1",
            "index": len(windows) + 1,
            "split_id": split.split_id,
            "start_bar": start,
            "end_bar_exclusive": end,
        }
        windows.append(
            WalkForwardWindow(
                index=len(windows) + 1,
                window_id=stable_uuid("walk-forward-window", window_payload),
                split=split,
            )
        )
        start += step

    if not windows:
        raise ValueError("dataset does not contain one complete walk-forward window")

    plan_payload = {
        "schema": "money-heist.walk-forward-plan.v1",
        "dataset": dataset.canonical_payload(),
        "design_bars": design_bars,
        "validation_bars": validation_bars,
        "oos_bars": oos_bars,
        "step_bars": step,
        "window_ids": tuple(window.window_id for window in windows),
    }
    return WalkForwardPlan(
        plan_id=stable_uuid("walk-forward-plan", plan_payload),
        dataset=dataset,
        design_bars=design_bars,
        validation_bars=validation_bars,
        oos_bars=oos_bars,
        step_bars=step,
        windows=tuple(windows),
    )


__all__ = [
    "WalkForwardPlan",
    "WalkForwardSplitExecutor",
    "WalkForwardWindow",
    "build_walk_forward_plan",
    "execute_walk_forward",
]
