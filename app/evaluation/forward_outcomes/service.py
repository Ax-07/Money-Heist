from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from .models import (
    ForwardOutcomeFirstHit,
    ForwardOutcomeHorizon,
    ForwardOutcomeHorizonSummary,
    ForwardOutcomeIncompleteReason,
    ForwardOutcomeRecord,
    ForwardOutcomeReference,
    ForwardOutcomeReport,
    ForwardOutcomeStatusCount,
    ForwardOutcomeSummary,
)

DEFAULT_FORWARD_HORIZONS = (1, 3, 5, 10, 20)
FORWARD_OUTCOME_POLICY_VERSION = "money-heist.forward-outcomes.close-ohlc.v1"


def _as_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _pct(value: Decimal, reference: Decimal) -> Decimal:
    return (value / reference - Decimal("1")) * Decimal("100")


def _horizon_outcome(
    *,
    reference: ForwardOutcomeReference,
    horizon_bars: int,
    interval: timedelta,
    period_end: datetime,
    candles_by_close: dict[datetime, Any],
) -> ForwardOutcomeHorizon:
    expected = tuple(
        reference.observed_at + interval * step
        for step in range(1, horizon_bars + 1)
    )
    gap_times = tuple(
        item
        for item in expected
        if item <= period_end and item not in candles_by_close
    )
    boundary_missing = sum(1 for item in expected if item > period_end)
    observed = tuple(candles_by_close[item] for item in expected if item in candles_by_close)
    complete = len(observed) == horizon_bars

    if not complete:
        if gap_times and boundary_missing:
            reason = ForwardOutcomeIncompleteReason.GAP_AND_PERIOD_END
        elif gap_times:
            reason = ForwardOutcomeIncompleteReason.GAP
        else:
            reason = ForwardOutcomeIncompleteReason.PERIOD_END
        return ForwardOutcomeHorizon(
            horizon_bars=horizon_bars,
            is_complete=False,
            bars_observed=len(observed),
            gap_count=len(gap_times),
            boundary_missing_bars=boundary_missing,
            missing_close_times=gap_times,
            expected_end_at=expected[-1],
            incomplete_reason=reason,
        )

    ordered = tuple(candles_by_close[item] for item in expected)
    last = ordered[-1]
    max_high = max(_decimal(item.high) for item in ordered)
    min_low = min(_decimal(item.low) for item in ordered)
    max_upside_at = next(
        item.close_time for item in ordered if _decimal(item.high) == max_high
    )
    max_downside_at = next(
        item.close_time for item in ordered if _decimal(item.low) == min_low
    )
    if max_upside_at < max_downside_at:
        first_hit = ForwardOutcomeFirstHit.MAX_UPSIDE
        first_hit_at = max_upside_at
    elif max_downside_at < max_upside_at:
        first_hit = ForwardOutcomeFirstHit.MAX_DOWNSIDE
        first_hit_at = max_downside_at
    else:
        first_hit = ForwardOutcomeFirstHit.SAME_CANDLE
        first_hit_at = max_upside_at

    return ForwardOutcomeHorizon(
        horizon_bars=horizon_bars,
        is_complete=True,
        bars_observed=horizon_bars,
        gap_count=0,
        boundary_missing_bars=0,
        missing_close_times=(),
        expected_end_at=expected[-1],
        return_pct=_pct(_decimal(last.close), reference.reference_close),
        max_upside_pct=_pct(max_high, reference.reference_close),
        max_downside_pct=_pct(min_low, reference.reference_close),
        max_upside_at=max_upside_at,
        max_downside_at=max_downside_at,
        first_hit=first_hit,
        first_hit_at=first_hit_at,
        incomplete_reason=None,
    )


def compute_forward_outcomes(
    *,
    run_id: str,
    dataset_id: str,
    dataset_version: str,
    dataset_content_sha256: str,
    dataset_source: str,
    system_id: str,
    source_timeframe: str,
    decision_timeframe: str,
    period_start: datetime,
    period_end: datetime,
    references: Iterable[ForwardOutcomeReference],
    decision_candles: Sequence[Any],
    decision_interval: timedelta,
    horizons: Sequence[int] = DEFAULT_FORWARD_HORIZONS,
) -> ForwardOutcomeReport:
    """Calculate post-hoc market outcomes without invoking any decision component."""

    period_start = _as_utc(period_start, field="period_start")
    period_end = _as_utc(period_end, field="period_end")
    if period_end < period_start:
        raise ValueError("period_end cannot precede period_start")
    if decision_interval <= timedelta(0):
        raise ValueError("decision_interval must be > 0")

    normalized_horizons = tuple(sorted({int(item) for item in horizons}))
    if not normalized_horizons or any(item <= 0 for item in normalized_horizons):
        raise ValueError("horizons must contain positive bar counts")

    candles_by_close: dict[datetime, Any] = {}
    for candle in decision_candles:
        close_time = _as_utc(candle.close_time, field="candle.close_time")
        if close_time > period_end:
            continue
        if close_time in candles_by_close:
            raise ValueError("decision candles must have unique close_time values")
        candles_by_close[close_time] = candle

    ordered_refs = tuple(
        sorted(
            references,
            key=lambda item: (item.observed_at, item.opportunity_id),
        )
    )
    records: list[ForwardOutcomeRecord] = []
    status_counter: Counter[str] = Counter()

    for raw_reference in ordered_refs:
        reference = raw_reference.model_copy(
            update={"observed_at": _as_utc(raw_reference.observed_at, field="observed_at")}
        )
        if reference.observed_at < period_start or reference.observed_at > period_end:
            raise ValueError("forward outcome reference must fall inside the run period")

        status_counter[reference.terminal_status] += 1
        horizon_records = tuple(
            _horizon_outcome(
                reference=reference,
                horizon_bars=horizon,
                interval=decision_interval,
                period_end=period_end,
                candles_by_close=candles_by_close,
            )
            for horizon in normalized_horizons
        )
        records.append(
            ForwardOutcomeRecord(
                opportunity_id=reference.opportunity_id,
                snapshot_id=reference.snapshot_id,
                observed_at=reference.observed_at,
                reference_close=reference.reference_close,
                terminal_status=reference.terminal_status,
                professor_direction=reference.professor_direction,
                proposal_side=reference.proposal_side,
                horizons=horizon_records,
            )
        )

    status_counts = tuple(
        ForwardOutcomeStatusCount(status=status, count=count)
        for status, count in sorted(status_counter.items())
    )
    horizon_counts = []
    for horizon in normalized_horizons:
        entries = [
            item
            for record in records
            for item in record.horizons
            if item.horizon_bars == horizon
        ]
        complete = sum(1 for item in entries if item.is_complete)
        incomplete = len(entries) - complete
        with_gaps = sum(1 for item in entries if item.gap_count > 0)
        horizon_counts.append(
            ForwardOutcomeHorizonSummary(
                horizon_bars=horizon,
                complete=complete,
                incomplete=incomplete,
                with_gaps=with_gaps,
            )
        )

    return ForwardOutcomeReport(
        policy_version=FORWARD_OUTCOME_POLICY_VERSION,
        run_id=run_id,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        dataset_content_sha256=dataset_content_sha256,
        dataset_source=dataset_source,
        system_id=system_id,
        source_timeframe=source_timeframe,
        decision_timeframe=decision_timeframe,
        period_start=period_start,
        period_end=period_end,
        horizons=normalized_horizons,
        summary=ForwardOutcomeSummary(
            opportunity_count=len(records),
            status_counts=status_counts,
            horizon_counts=tuple(horizon_counts),
        ),
        records=tuple(records),
    )


__all__ = [
    "DEFAULT_FORWARD_HORIZONS",
    "FORWARD_OUTCOME_POLICY_VERSION",
    "compute_forward_outcomes",
]
