from datetime import UTC, datetime

from app.analytics import (
    AnalyticsAsOfInput,
    AnalyticsComponentVersions,
    AnalyticsLabRun,
    AnalyticsPeriodRole,
    AnalyticsSnapshot,
    build_analytics_manifest,
    manifest_to_json,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def _run() -> AnalyticsLabRun:
    return AnalyticsLabRun.create(
        source_backtest_run_id="backtest-run",
        dataset_id="dataset",
        dataset_version="sha256:dataset",
        dataset_content_sha256=SHA_A,
        dataset_source="csv",
        system_id="balanced_v1",
        symbol="BTC/USDC",
        source_timeframe="1h",
        decision_timeframe="1h",
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 1, 31, 23, tzinfo=UTC),
        period_role=AnalyticsPeriodRole.VALIDATION,
        mtf_policy_version="mtf-utc-closed-v1",
        component_versions=AnalyticsComponentVersions.foundation(),
    )


def _snapshot(run: AnalyticsLabRun, hour: int) -> AnalyticsSnapshot:
    as_of_input = AnalyticsAsOfInput(
        source_backtest_run_id=run.source_backtest_run_id,
        dataset_id=run.dataset_id,
        dataset_version=run.dataset_version,
        dataset_content_sha256=run.dataset_content_sha256,
        dataset_source=run.dataset_source,
        system_id=run.system_id,
        symbol=run.symbol,
        source_timeframe=run.source_timeframe,
        decision_timeframe=run.decision_timeframe,
        as_of=datetime(2026, 1, 2, hour, tzinfo=UTC),
        mtf_policy_version=run.mtf_policy_version,
        source_cursor_fingerprint=SHA_B,
    )
    return AnalyticsSnapshot.create(analytics_run=run, as_of_input=as_of_input)


def test_manifest_is_order_independent_and_canonical() -> None:
    run = _run()
    first = _snapshot(run, 10)
    second = _snapshot(run, 11)

    a = build_analytics_manifest(run, [second, first])
    b = build_analytics_manifest(run, [first, second])

    assert a.analytics_sha256 == b.analytics_sha256
    assert a.snapshot_count == 2
    assert a.period_role is AnalyticsPeriodRole.VALIDATION
    assert a.dataset_content_sha256 == SHA_A
    assert manifest_to_json(a) == manifest_to_json(b)


def test_empty_foundation_manifest_is_valid_and_deterministic() -> None:
    run = _run()
    first = build_analytics_manifest(run, [])
    second = build_analytics_manifest(run, [])

    assert first.snapshot_count == 0
    assert first.analytics_sha256 == second.analytics_sha256
    assert first.analytics_run_id == run.analytics_run_id
