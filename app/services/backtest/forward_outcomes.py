from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.evaluation.forward_outcomes import (
    DEFAULT_FORWARD_HORIZONS,
    ForwardOutcomeReference,
    ForwardOutcomeReport,
    compute_forward_outcomes,
)
from app.market.models import Candle
from app.market.multitimeframe import resample_closed_candles, timeframe_interval

from .dataset import canonical_candle_rows


def _value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _row_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _source_candles(candles: Sequence[Any], run: Any) -> tuple[Candle, ...]:
    rows = canonical_candle_rows(
        candles,
        expected_symbol=run.dataset.symbol,
        expected_timeframe=run.dataset.timeframe,
    )
    return tuple(
        Candle(
            symbol=run.dataset.symbol,
            timeframe=run.dataset.timeframe,
            open_time=_row_time(row["open_time"]),
            close_time=_row_time(row["close_time"]),
            open=Decimal(row["open"]),
            high=Decimal(row["high"]),
            low=Decimal(row["low"]),
            close=Decimal(row["close"]),
            volume=Decimal(row["volume"]),
            is_closed=bool(row["is_closed"]),
        )
        for row in rows
        if _row_time(row["close_time"]) <= run.period_end
    )


def _decision_timeframe(replay_result: Any) -> str:
    run = replay_result.backtest_result.run
    point_values = {
        str(point.decision_timeframe).strip().lower()
        for point in replay_result.points
        if getattr(point, "decision_timeframe", None)
    }
    if len(point_values) > 1:
        raise ValueError("HistoricalReplayResult contains multiple decision timeframes")
    if point_values:
        return next(iter(point_values))
    configured = str(
        run.config.execution_assumptions.get("decision_timeframe", "")
    ).strip().lower()
    return configured or run.dataset.timeframe


def _decision_candles(
    *,
    replay_result: Any,
    candles: Sequence[Any],
    decision_timeframe: str,
) -> tuple[Candle, ...]:
    run = replay_result.backtest_result.run
    source = _source_candles(candles, run)
    if decision_timeframe == run.dataset.timeframe:
        return source
    return resample_closed_candles(
        source,
        target_timeframe=decision_timeframe,
        as_of=run.period_end,
    )


def _references(replay_result: Any) -> tuple[ForwardOutcomeReference, ...]:
    output: list[ForwardOutcomeReference] = []
    for point in replay_result.points:
        opportunity = getattr(point, "opportunity", None)
        if opportunity is None:
            continue

        pipeline_result = getattr(point, "pipeline_result", None)
        terminal_status = _value(getattr(pipeline_result, "status", None))
        if terminal_status is None:
            terminal_status = "MISSING_PIPELINE_RESULT"

        orchestration = getattr(pipeline_result, "orchestration_result", None)
        final_decision = getattr(orchestration, "professor_decision", None)
        trade_proposal = getattr(orchestration, "trade_proposal", None)
        output.append(
            ForwardOutcomeReference(
                opportunity_id=str(opportunity.opportunity_id),
                snapshot_id=str(opportunity.snapshot_id),
                observed_at=point.observed_at,
                reference_close=Decimal(str(point.feature_snapshot.close)),
                terminal_status=terminal_status,
                professor_direction=_value(
                    getattr(final_decision, "direction", None)
                ),
                proposal_side=_value(getattr(trade_proposal, "side", None)),
            )
        )
    return tuple(output)


def resolve_outcome_decision_timeframe(replay_result: Any) -> str:
    return _decision_timeframe(replay_result)


def build_outcome_decision_candles(
    *,
    replay_result: Any,
    candles: Sequence[Any],
    decision_timeframe: str,
) -> tuple[Candle, ...]:
    return _decision_candles(
        replay_result=replay_result,
        candles=candles,
        decision_timeframe=decision_timeframe,
    )


def build_forward_outcomes_report(
    replay_result: Any,
    candles: Sequence[Any],
    *,
    horizons: Sequence[int] = DEFAULT_FORWARD_HORIZONS,
) -> ForwardOutcomeReport:
    """Build post-hoc outcomes from the immutable market dataset after replay."""

    run = replay_result.backtest_result.run
    decision_timeframe = _decision_timeframe(replay_result)
    decision_candles = _decision_candles(
        replay_result=replay_result,
        candles=candles,
        decision_timeframe=decision_timeframe,
    )
    return compute_forward_outcomes(
        run_id=run.run_id,
        dataset_id=run.dataset.dataset_id,
        dataset_version=run.dataset.version,
        dataset_content_sha256=run.dataset.content_sha256,
        dataset_source=run.dataset.source,
        system_id=run.config.system_id,
        source_timeframe=run.dataset.timeframe,
        decision_timeframe=decision_timeframe,
        period_start=run.period_start,
        period_end=run.period_end,
        references=_references(replay_result),
        decision_candles=decision_candles,
        decision_interval=timeframe_interval(decision_timeframe),
        horizons=horizons,
    )


__all__ = [
    "ForwardOutcomeReport",
    "build_forward_outcomes_report",
    "build_outcome_decision_candles",
    "resolve_outcome_decision_timeframe",
]
