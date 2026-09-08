from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.evaluation import (
    EquityPoint,
    EvaluationReport,
    EvaluationService,
    EvaluationSource,
    build_evaluation_source,
)

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class BacktestEvaluationBundle:
    source: EvaluationSource
    report: EvaluationReport
    equity_points: tuple[EquityPoint, ...]
    marks: dict[str, Decimal]


def equity_points_from_replay(replay_result: Any) -> tuple[EquityPoint, ...]:
    """Build a deterministic equity series from replay account snapshots.

    The initial run balance is anchored at period_start. Later timestamps are
    replaced by the latest account snapshot at that timestamp.
    """

    run = replay_result.backtest_result.run
    by_time: dict[Any, EquityPoint] = {
        run.period_start: EquityPoint(
            observed_at=run.period_start,
            equity=run.config.initial_balance,
        )
    }
    for point in replay_result.points:
        account = getattr(point, "account_state", None)
        if account is None:
            continue
        observed_at = point.observed_at
        if observed_at < run.period_start or observed_at > run.period_end:
            continue
        equity = Decimal(str(account.equity))
        if not equity.is_finite():
            raise ValueError("replay account equity must be finite")
        by_time[observed_at] = EquityPoint(
            observed_at=observed_at,
            equity=equity,
        )
    return tuple(by_time[key] for key in sorted(by_time))


def final_marks_from_replay(replay_result: Any) -> dict[str, Decimal]:
    marks: dict[str, Decimal] = {}
    for point in replay_result.points:
        feature = getattr(point, "feature_snapshot", None)
        if feature is None:
            continue
        symbol = str(getattr(feature, "symbol", "")).strip()
        close = getattr(feature, "close", None)
        if not symbol or close is None:
            continue
        mark = Decimal(str(close))
        if not mark.is_finite() or mark <= ZERO:
            raise ValueError("replay final marks must be finite and > 0")
        marks[symbol] = mark
    return dict(sorted(marks.items()))


async def evaluate_historical_replay(
    replay_result: Any,
    *,
    broker: Any,
    ai_usage_records: Iterable[Any] = (),
    paper_events: Iterable[Any] = (),
    evaluation_service: EvaluationService | None = None,
) -> BacktestEvaluationBundle:
    """Feed one completed historical replay into the existing Batch 10 Evaluation."""

    orders = await broker.get_orders()
    fills = await broker.get_fills()
    equity_points = equity_points_from_replay(replay_result)
    marks = final_marks_from_replay(replay_result)
    run = replay_result.backtest_result.run

    source = build_evaluation_source(
        orders=orders,
        fills=fills,
        pipeline_results=replay_result.pipeline_results,
        paper_events=paper_events,
        ai_usage_records=ai_usage_records,
        marks=marks,
        market_slippage_bps=run.config.market_slippage_bps,
        equity_points=equity_points,
    )
    service = evaluation_service or EvaluationService()
    return BacktestEvaluationBundle(
        source=source,
        report=service.evaluate(source),
        equity_points=equity_points,
        marks=marks,
    )


__all__ = [
    "BacktestEvaluationBundle",
    "equity_points_from_replay",
    "evaluate_historical_replay",
    "final_marks_from_replay",
]
