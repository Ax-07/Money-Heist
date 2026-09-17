from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.analytics.models import AnalyticsLabRun, AnalyticsPeriodRole
from app.analytics.pattern_calibration import (
    PATTERN_CALIBRATION_VERSION,
    PatternCalibrationRun,
    PatternSourceComparison,
    calibrate_pattern_sources,
    merge_pattern_calibration_reports,
    pattern_calibration_report_to_json,
)
from app.analytics.patterns import causal_pattern_component_versions
from app.analytics.patterns.models import PatternPivot
from app.analytics.structure import StructureSource
from app.market.models import Candle

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(i: int, close=105, high=106, low=104) -> Candle:
    start = BASE + timedelta(hours=i)
    return Candle(
        symbol="BTC/EUR",
        timeframe="1h",
        open_time=start,
        close_time=start + timedelta(hours=1),
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("10"),
        is_closed=True,
    )


def _pivot(
    pid: str,
    kind: str,
    price: float,
    index: int,
    confirmed_index: int,
    *,
    source: StructureSource = StructureSource.CAUSAL_ZIGZAG,
) -> PatternPivot:
    hex_char = pid[0] if pid[0] in "abcdef" else "a"
    return PatternPivot(
        pivot_id=pid,
        kind=kind,
        price=Decimal(str(price)),
        pivot_at=BASE + timedelta(hours=index + 1),
        confirmed_at=BASE + timedelta(hours=confirmed_index + 1),
        symbol="BTC/EUR",
        timeframe="1h",
        source=source,
        source_fingerprint=hex_char * 64,
        source_cursor_fingerprint="b" * 64,
        atr_at_pivot=Decimal("4"),
        candle_index=index,
        confirmed_index=confirmed_index,
    )


def _run(role: AnalyticsPeriodRole = AnalyticsPeriodRole.DESIGN) -> AnalyticsLabRun:
    return AnalyticsLabRun.create(
        source_backtest_run_id="backtest-1",
        dataset_id="dataset-1",
        dataset_version="v1",
        dataset_content_sha256="a" * 64,
        dataset_source="historical-csv",
        system_id="balanced-v1",
        symbol="BTC/EUR",
        source_timeframe="1h",
        decision_timeframe="1h",
        period_start=BASE,
        period_end=BASE + timedelta(hours=40),
        period_role=role,
        mtf_policy_version="mtf-v1",
        component_versions=causal_pattern_component_versions(),
    )


def _series() -> tuple[Candle, ...]:
    candles = [_candle(i) for i in range(30)]
    candles[4] = _candle(4, 110, 111, 109)
    candles[7] = _candle(7, 100, 101, 99)
    candles[10] = _candle(10, 110, 111, 109)
    candles[13] = _candle(13, 98, 99, 97)
    return tuple(candles)


def _valid(source=StructureSource.CAUSAL_ZIGZAG):
    return (
        _pivot("a1", "HIGH", 110, 4, 5, source=source),
        _pivot("b2", "LOW", 100, 7, 8, source=source),
        _pivot("c3", "HIGH", 110, 10, 11, source=source),
    )


def test_rejected_candidate_preserves_multiple_rule_evidence() -> None:
    pivots = (
        _pivot("a1", "HIGH", 110, 4, 5),
        _pivot("b2", "LOW", 109, 7, 8),
        _pivot("c3", "HIGH", 116, 10, 11),
    )
    report = calibrate_pattern_sources(
        analytics_run=_run(),
        candles=_series(),
        pivots_by_source={StructureSource.CAUSAL_ZIGZAG: pivots},
        as_of=BASE + timedelta(hours=14),
    )
    candidate = report.sources[0].diagnostics[0]
    assert candidate.accepted is False
    assert {reason.value for reason in candidate.rejection_reasons} >= {
        "OUTER_LEVELS_TOO_FAR_APART",
        "INTERMEDIATE_RETRACEMENT_TOO_SHALLOW",
    }
    mismatch = next(
        rule
        for rule in candidate.rule_evaluations
        if rule.rule_id == "DOUBLE.MAX_LEVEL_MISMATCH"
    )
    assert mismatch.passed is False
    assert mismatch.observed["level_mismatch_atr"] > mismatch.required["maximum_atr"]


def test_accepted_candidate_links_canonical_pattern_id() -> None:
    report = calibrate_pattern_sources(
        analytics_run=_run(),
        candles=_series(),
        pivots_by_source={StructureSource.CAUSAL_ZIGZAG: _valid()},
        as_of=BASE + timedelta(hours=14),
    )
    candidate = report.sources[0].diagnostics[0]
    assert candidate.accepted is True
    assert candidate.pattern_id in report.sources[0].accepted_pattern_ids
    assert candidate.rejection_reasons == ()


def test_source_comparison_uses_same_rules_without_ranking() -> None:
    source_a = _valid(StructureSource.CAUSAL_ZIGZAG)
    source_b = (
        _pivot("d1", "HIGH", 110, 4, 5, source=StructureSource.MONEY_HEIST_STRUCTURE),
        _pivot("e2", "LOW", 108, 7, 8, source=StructureSource.MONEY_HEIST_STRUCTURE),
        _pivot("f3", "HIGH", 120, 10, 11, source=StructureSource.MONEY_HEIST_STRUCTURE),
    )
    report = calibrate_pattern_sources(
        analytics_run=_run(),
        candles=_series(),
        pivots_by_source={
            StructureSource.CAUSAL_ZIGZAG: source_a,
            StructureSource.MONEY_HEIST_STRUCTURE: source_b,
        },
        as_of=BASE + timedelta(hours=14),
    )
    assert report.comparison.same_pattern_registry_version is True
    summaries = {item.pivot_source: item for item in report.comparison.sources}
    assert summaries["CAUSAL_ZIGZAG"].accepted_count == 1
    assert summaries["MONEY_HEIST_STRUCTURE"].rejected_count == 1
    assert not hasattr(report.comparison, "winner")
    assert not hasattr(report.comparison, "rank")


def test_future_pivot_is_invisible_before_confirmation() -> None:
    pivots = (
        _pivot("a1", "HIGH", 110, 4, 5),
        _pivot("b2", "LOW", 100, 7, 8),
        _pivot("c3", "HIGH", 110, 10, 20),
    )
    report = calibrate_pattern_sources(
        analytics_run=_run(),
        candles=_series(),
        pivots_by_source={StructureSource.CAUSAL_ZIGZAG: pivots},
        as_of=BASE + timedelta(hours=14),
    )
    assert report.sources[0].summary.candidate_count == 0


def test_prefix_invariance_and_future_extreme() -> None:
    candles = _series()
    cutoff = BASE + timedelta(hours=14)
    full = calibrate_pattern_sources(
        analytics_run=_run(),
        candles=candles,
        pivots_by_source={StructureSource.CAUSAL_ZIGZAG: _valid()},
        as_of=cutoff,
    )
    future = list(candles)
    future[20] = _candle(20, 105, 1000, 1)
    changed = calibrate_pattern_sources(
        analytics_run=_run(),
        candles=tuple(future),
        pivots_by_source={StructureSource.CAUSAL_ZIGZAG: _valid()},
        as_of=cutoff,
    )
    prefix = calibrate_pattern_sources(
        analytics_run=_run(),
        candles=tuple(c for c in candles if c.close_time <= cutoff),
        pivots_by_source={StructureSource.CAUSAL_ZIGZAG: _valid()},
        as_of=cutoff,
    )

    def sig(report):
        return [
            (d.candidate_id, d.candidate_fingerprint, d.rejection_reasons)
            for d in report.sources[0].diagnostics
        ]

    assert sig(full) == sig(changed) == sig(prefix)


def test_repeated_as_of_merge_does_not_duplicate_candidate() -> None:
    run = _run()
    reports = [
        calibrate_pattern_sources(
            analytics_run=run,
            candles=_series(),
            pivots_by_source={StructureSource.CAUSAL_ZIGZAG: _valid()},
            as_of=BASE + timedelta(hours=hour),
        )
        for hour in (14, 15, 16)
    ]
    merged = merge_pattern_calibration_reports(reports)
    assert merged.sources[0].summary.candidate_count == 1


def test_comparison_rejects_mixed_registry_versions() -> None:
    with pytest.raises(ValueError, match="identical Pattern Registry"):
        PatternSourceComparison.create([], pattern_registry_versions=["registry-a", "registry-b"])


def test_calibration_version_changes_only_calibration_identity() -> None:
    run = _run()
    a = PatternCalibrationRun.create(run, pivot_sources=["CAUSAL_ZIGZAG"])
    b = PatternCalibrationRun.create(
        run,
        pivot_sources=["CAUSAL_ZIGZAG"],
        calibration_version=PATTERN_CALIBRATION_VERSION + ".test",
    )
    assert a.analytics_run_id == b.analytics_run_id == run.analytics_run_id
    assert a.source_backtest_run_id == b.source_backtest_run_id == run.source_backtest_run_id
    assert a.calibration_run_id != b.calibration_run_id


def test_period_role_and_json_serialization_are_stable() -> None:
    report = calibrate_pattern_sources(
        analytics_run=_run(AnalyticsPeriodRole.OOS),
        candles=_series(),
        pivots_by_source={StructureSource.CAUSAL_ZIGZAG: _valid()},
        as_of=BASE + timedelta(hours=14),
    )
    assert report.period_role is AnalyticsPeriodRole.OOS
    assert pattern_calibration_report_to_json(report) == pattern_calibration_report_to_json(report)
