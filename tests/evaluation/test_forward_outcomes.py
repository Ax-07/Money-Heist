from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.evaluation.forward_outcomes import (
    ForwardOutcomeFirstHit,
    ForwardOutcomeIncompleteReason,
    ForwardOutcomeReference,
    compute_forward_outcomes,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
INTERVAL = timedelta(hours=1)


def candle(step: int, *, close: str, high: str, low: str):
    close_time = START + INTERVAL * step
    return SimpleNamespace(
        close_time=close_time,
        close=Decimal(close),
        high=Decimal(high),
        low=Decimal(low),
    )


def reference(*, status: str = "NO_TRADE") -> ForwardOutcomeReference:
    return ForwardOutcomeReference(
        opportunity_id="opp-1",
        snapshot_id="snap-1",
        observed_at=START,
        reference_close=Decimal("100"),
        terminal_status=status,
    )


def build(candles, *, period_end, horizons=(1, 3, 5)):
    return compute_forward_outcomes(
        run_id="run-1",
        dataset_id="BTC/USDC:1h:fixture",
        dataset_version="sha256:" + "a" * 64,
        dataset_content_sha256="a" * 64,
        dataset_source="fixture",
        system_id="balanced_v1",
        source_timeframe="1h",
        decision_timeframe="1h",
        period_start=START,
        period_end=period_end,
        references=(reference(),),
        decision_candles=candles,
        decision_interval=INTERVAL,
        horizons=horizons,
    )


def test_forward_outcomes_publish_only_complete_horizons():
    candles = (
        candle(1, close="102", high="104", low="99"),
        candle(2, close="98", high="103", low="95"),
        candle(3, close="105", high="108", low="97"),
        candle(4, close="107", high="109", low="103"),
        candle(5, close="106", high="110", low="104"),
    )
    report = build(candles, period_end=START + INTERVAL * 5)

    h1, h3, h5 = report.records[0].horizons
    assert h1.is_complete is True
    assert h1.return_pct == Decimal("2.00")
    assert h1.max_upside_pct == Decimal("4.00")
    assert h1.max_downside_pct == Decimal("-1.00")
    assert h1.first_hit is ForwardOutcomeFirstHit.SAME_CANDLE

    assert h3.is_complete is True
    assert h3.return_pct == Decimal("5.00")
    assert h3.max_upside_pct == Decimal("8.00")
    assert h3.max_downside_pct == Decimal("-5.00")
    assert h3.first_hit is ForwardOutcomeFirstHit.MAX_DOWNSIDE
    assert h3.first_hit_at == START + INTERVAL * 2

    assert h5.is_complete is True
    assert h5.return_pct == Decimal("6.00")
    assert h5.max_upside_pct == Decimal("10.0")
    assert h5.max_downside_pct == Decimal("-5.00")


def test_gap_makes_horizon_incomplete_without_partial_price_metrics():
    candles = (
        candle(1, close="101", high="102", low="99"),
        candle(3, close="103", high="104", low="98"),
    )
    report = build(candles, period_end=START + INTERVAL * 3, horizons=(1, 3))
    h1, h3 = report.records[0].horizons

    assert h1.is_complete is True
    assert h3.is_complete is False
    assert h3.gap_count == 1
    assert h3.missing_close_times == (START + INTERVAL * 2,)
    assert h3.incomplete_reason is ForwardOutcomeIncompleteReason.GAP
    assert h3.return_pct is None
    assert h3.max_upside_pct is None
    assert h3.max_downside_pct is None


def test_period_boundary_is_not_counted_as_market_gap():
    candles = (candle(1, close="101", high="102", low="99"),)
    report = build(candles, period_end=START + INTERVAL, horizons=(3,))
    horizon = report.records[0].horizons[0]

    assert horizon.is_complete is False
    assert horizon.gap_count == 0
    assert horizon.boundary_missing_bars == 2
    assert horizon.incomplete_reason is ForwardOutcomeIncompleteReason.PERIOD_END


def test_summary_preserves_terminal_status_without_interpreting_it():
    refs = tuple(
        ForwardOutcomeReference(
            opportunity_id=f"opp-{index}",
            snapshot_id=f"snap-{index}",
            observed_at=START,
            reference_close=Decimal("100"),
            terminal_status=status,
        )
        for index, status in enumerate(
            ("NO_ANALYSIS", "NO_TRADE", "RISK_REJECTED", "EXECUTED"),
            start=1,
        )
    )
    report = compute_forward_outcomes(
        run_id="run-1",
        dataset_id="dataset",
        dataset_version="sha256:" + "b" * 64,
        dataset_content_sha256="b" * 64,
        dataset_source="fixture",
        system_id="balanced_v1",
        source_timeframe="1h",
        decision_timeframe="1h",
        period_start=START,
        period_end=START + INTERVAL,
        references=refs,
        decision_candles=(candle(1, close="101", high="102", low="99"),),
        decision_interval=INTERVAL,
        horizons=(1,),
    )

    assert report.summary.opportunity_count == 4
    assert [(item.status, item.count) for item in report.summary.status_counts] == [
        ("EXECUTED", 1),
        ("NO_ANALYSIS", 1),
        ("NO_TRADE", 1),
        ("RISK_REJECTED", 1),
    ]
