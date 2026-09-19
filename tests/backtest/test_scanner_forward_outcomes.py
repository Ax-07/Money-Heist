from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.market.models import Candle
from app.services.backtest.scanner_forward_outcomes import (
    build_scanner_forward_outcomes_report,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def candles() -> tuple[Candle, ...]:
    output = []
    for index in range(4):
        opened = START + timedelta(hours=index)
        output.append(
            Candle(
                symbol="BTC/USDC",
                timeframe="1h",
                open_time=opened,
                close_time=opened + timedelta(hours=1),
                open=Decimal("100"),
                high=Decimal("102"),
                low=Decimal("98"),
                close=Decimal("101"),
                volume=Decimal("10"),
            )
        )
    return tuple(output)


def point(
    step: int,
    *,
    score: int,
    triggers=(),
    candidate=False,
):
    observed = START + timedelta(hours=step)
    snapshot_id = f"snap-{step}"
    opportunity = None
    if candidate:
        opportunity = SimpleNamespace(
            opportunity_id=f"opp-{step}",
            snapshot_id=snapshot_id,
            priority_score=score,
        )
    scan = SimpleNamespace(
        score=score,
        triggers=tuple(SimpleNamespace(value=item) for item in triggers),
        opportunity=opportunity,
    )
    return SimpleNamespace(
        observed_at=observed,
        decision_timeframe=None,
        feature_snapshot=SimpleNamespace(
            snapshot_id=snapshot_id,
            close=Decimal("101"),
            regime=SimpleNamespace(value="range"),
        ),
        scan_result=scan,
        opportunity=opportunity,
    )


def replay():
    dataset = SimpleNamespace(
        dataset_id="dataset-1",
        version="sha256:" + "a" * 64,
        content_sha256="a" * 64,
        source="fixture",
        symbol="BTC/USDC",
        timeframe="1h",
    )
    run = SimpleNamespace(
        run_id="run-1",
        dataset=dataset,
        config=SimpleNamespace(
            system_id="balanced_v1",
            scanner_version="scanner-v1",
            execution_assumptions={},
        ),
        period_start=START + timedelta(hours=1),
        period_end=START + timedelta(hours=4),
    )
    return SimpleNamespace(
        backtest_result=SimpleNamespace(run=run),
        points=(
            point(1, score=0),
            point(2, score=20, triggers=("volume_expansion",)),
            point(3, score=35, triggers=("range_break",), candidate=True),
        ),
    )


def funnel(*, scanner_evaluations=3, no_trigger=1, triggered=2, candidates=1):
    return SimpleNamespace(
        run_id="run-1",
        dataset_id="dataset-1",
        system_id="balanced_v1",
        counts=SimpleNamespace(
            scanner_evaluations=scanner_evaluations,
            scanner_no_trigger=no_trigger,
            scanner_triggered=triggered,
            candidate_opportunities=candidates,
        ),
    )


def test_adapter_matches_decision_funnel_scanner_conservation():
    report = build_scanner_forward_outcomes_report(
        replay(),
        candles(),
        funnel(),
        scanner_version="scanner-v1",
        min_priority_score=35,
        horizons=(1,),
    )
    assert report.summary.scanner_evaluations == 3
    assert report.summary.no_trigger == 1
    assert report.summary.trigger_below_candidate_threshold == 1
    assert report.summary.candidate_opportunities == 1
    assert [item.classification.value for item in report.records] == [
        "NO_TRIGGER",
        "TRIGGER_BELOW_CANDIDATE_THRESHOLD",
        "CANDIDATE_OPPORTUNITY",
    ]


def test_adapter_rejects_funnel_count_mismatch():
    with pytest.raises(ValueError, match="do not conserve"):
        build_scanner_forward_outcomes_report(
            replay(),
            candles(),
            funnel(scanner_evaluations=4),
            scanner_version="scanner-v1",
            min_priority_score=35,
            horizons=(1,),
        )


def test_adapter_rejects_wrong_scanner_provenance():
    with pytest.raises(ValueError, match="scanner_version"):
        build_scanner_forward_outcomes_report(
            replay(),
            candles(),
            funnel(),
            scanner_version="scanner-v2",
            min_priority_score=35,
            horizons=(1,),
        )
