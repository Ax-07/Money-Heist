from dataclasses import replace
from datetime import UTC, datetime

from app.analytics import AnalyticsLabRun, AnalyticsPeriodRole, build_analytics_manifest
from app.analytics.patterns.integration import causal_pattern_component_versions
from app.analytics.patterns.registry import ANALYTICS_PATTERN_REGISTRY_IDENTITY

SHA = "a" * 64


def _run(component_versions):
    return AnalyticsLabRun.create(
        source_backtest_run_id="backtest-run",
        dataset_id="dataset",
        dataset_version="sha256:dataset",
        dataset_content_sha256=SHA,
        dataset_source="csv",
        system_id="balanced_v1",
        symbol="BTC/USDC",
        source_timeframe="1h",
        decision_timeframe="1h",
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 1, 31, 23, tzinfo=UTC),
        period_role=AnalyticsPeriodRole.VALIDATION,
        mtf_policy_version="mtf-utc-closed-v1",
        component_versions=component_versions,
    )


def test_pattern_registry_version_is_carried_by_analytics_manifest() -> None:
    versions = causal_pattern_component_versions()
    run = _run(versions)
    manifest = build_analytics_manifest(run, [])

    assert versions.pattern_registry_version == ANALYTICS_PATTERN_REGISTRY_IDENTITY
    assert (
        manifest.component_versions.pattern_registry_version == ANALYTICS_PATTERN_REGISTRY_IDENTITY
    )


def test_pattern_registry_version_changes_run_and_manifest_identity() -> None:
    versions = causal_pattern_component_versions()
    changed = replace(
        versions,
        pattern_registry_version="money-heist.pattern-registry.test-v2",
    )
    first_run = _run(versions)
    second_run = _run(changed)
    first_manifest = build_analytics_manifest(first_run, [])
    second_manifest = build_analytics_manifest(second_run, [])

    assert first_run.analytics_run_id != second_run.analytics_run_id
    assert first_manifest.analytics_sha256 != second_manifest.analytics_sha256
