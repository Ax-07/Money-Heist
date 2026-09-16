from datetime import UTC, datetime, timedelta

import pytest

from app.analytics import (
    AnalyticsAsOfInput,
    AnalyticsComponentVersions,
    AnalyticsLabRun,
    AnalyticsObservationProvenance,
    AnalyticsPeriodRole,
    AnalyticsSnapshot,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
RUN_ID = "source-backtest-run"


def _versions(bundle: str = "analytics-lab-foundation-v1") -> AnalyticsComponentVersions:
    return AnalyticsComponentVersions.foundation(analytics_bundle_version=bundle)


def _run(bundle: str = "analytics-lab-foundation-v1") -> AnalyticsLabRun:
    return AnalyticsLabRun.create(
        source_backtest_run_id=RUN_ID,
        dataset_id="BTC/USDC:1h:dataset",
        dataset_version="sha256:dataset",
        dataset_content_sha256=SHA_A,
        dataset_source="historical-csv",
        system_id="balanced_v1",
        symbol="BTC/USDC",
        source_timeframe="1h",
        decision_timeframe="1h",
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 1, 31, 23, tzinfo=UTC),
        period_role=AnalyticsPeriodRole.OOS,
        mtf_policy_version="mtf-utc-closed-v1",
        component_versions=_versions(bundle),
    )


def _as_of() -> AnalyticsAsOfInput:
    return AnalyticsAsOfInput(
        source_backtest_run_id=RUN_ID,
        dataset_id="BTC/USDC:1h:dataset",
        dataset_version="sha256:dataset",
        dataset_content_sha256=SHA_A,
        dataset_source="historical-csv",
        system_id="balanced_v1",
        symbol="BTC/USDC",
        source_timeframe="1h",
        decision_timeframe="1h",
        as_of=datetime(2026, 1, 10, 12, tzinfo=UTC),
        mtf_policy_version="mtf-utc-closed-v1",
        source_cursor_fingerprint=SHA_B,
    )


def test_timezone_awareness_is_required() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        AnalyticsAsOfInput(
            source_backtest_run_id=RUN_ID,
            dataset_id="dataset",
            dataset_version="v1",
            dataset_content_sha256=SHA_A,
            dataset_source="source",
            system_id="balanced_v1",
            symbol="BTC/USDC",
            source_timeframe="1h",
            decision_timeframe="1h",
            as_of=datetime(2026, 1, 1),
            mtf_policy_version="mtf-utc-closed-v1",
            source_cursor_fingerprint=SHA_B,
        )


def test_blank_identifiers_and_invalid_sha_are_rejected() -> None:
    with pytest.raises(ValueError, match="system_id must not be empty"):
        AnalyticsAsOfInput(
            source_backtest_run_id=RUN_ID,
            dataset_id="dataset",
            dataset_version="v1",
            dataset_content_sha256=SHA_A,
            dataset_source="source",
            system_id=" ",
            symbol="BTC/USDC",
            source_timeframe="1h",
            decision_timeframe="1h",
            as_of=datetime(2026, 1, 1, tzinfo=UTC),
            mtf_policy_version="mtf-utc-closed-v1",
            source_cursor_fingerprint=SHA_B,
        )

    with pytest.raises(ValueError, match="64-character"):
        AnalyticsAsOfInput(
            source_backtest_run_id=RUN_ID,
            dataset_id="dataset",
            dataset_version="v1",
            dataset_content_sha256="not-a-sha",
            dataset_source="source",
            system_id="balanced_v1",
            symbol="BTC/USDC",
            source_timeframe="1h",
            decision_timeframe="1h",
            as_of=datetime(2026, 1, 1, tzinfo=UTC),
            mtf_policy_version="mtf-utc-closed-v1",
            source_cursor_fingerprint=SHA_B,
        )


def test_invalid_component_version_and_period_are_rejected() -> None:
    with pytest.raises(ValueError, match="indicator_registry_version"):
        AnalyticsComponentVersions(
            analytics_bundle_version="v1",
            indicator_registry_version=" ",
            event_registry_version="none",
            structure_version="none",
            zigzag_version="none",
            pattern_registry_version="none",
            context_engine_version="none",
            sequence_engine_version="none",
        )

    with pytest.raises(ValueError, match="period_role"):
        AnalyticsLabRun.create(
            source_backtest_run_id=RUN_ID,
            dataset_id="dataset",
            dataset_version="v1",
            dataset_content_sha256=SHA_A,
            dataset_source="source",
            system_id="balanced_v1",
            symbol="BTC/USDC",
            source_timeframe="1h",
            decision_timeframe="1h",
            period_start=datetime(2026, 1, 1, tzinfo=UTC),
            period_end=datetime(2026, 1, 2, tzinfo=UTC),
            period_role="TRAIN",
            mtf_policy_version="mtf-utc-closed-v1",
            component_versions=_versions(),
        )


def test_invalid_period_bounds_are_rejected() -> None:
    with pytest.raises(ValueError, match="period_end"):
        AnalyticsLabRun.create(
            source_backtest_run_id=RUN_ID,
            dataset_id="dataset",
            dataset_version="v1",
            dataset_content_sha256=SHA_A,
            dataset_source="source",
            system_id="balanced_v1",
            symbol="BTC/USDC",
            source_timeframe="1h",
            decision_timeframe="1h",
            period_start=datetime(2026, 1, 2, tzinfo=UTC),
            period_end=datetime(2026, 1, 1, tzinfo=UTC),
            period_role=AnalyticsPeriodRole.DESIGN,
            mtf_policy_version="mtf-utc-closed-v1",
            component_versions=_versions(),
        )


def test_same_inputs_are_deterministic_and_material_version_changes_identity() -> None:
    first = _run()
    second = _run()
    changed = _run("analytics-lab-foundation-v2")

    assert first.analytics_run_id == second.analytics_run_id
    assert first.identity_sha256 == second.identity_sha256
    assert changed.analytics_run_id != first.analytics_run_id
    assert changed.identity_sha256 != first.identity_sha256


def test_snapshot_preserves_provenance_and_is_deterministic() -> None:
    run = _run()
    as_of_input = _as_of()
    first = AnalyticsSnapshot.create(
        analytics_run=run,
        as_of_input=as_of_input,
        components={},
    )
    second = AnalyticsSnapshot.create(
        analytics_run=run,
        as_of_input=as_of_input,
        components={},
    )

    assert first.snapshot_id == second.snapshot_id
    assert first.dataset_content_sha256 == SHA_A
    assert first.source_cursor_fingerprint == SHA_B
    assert first.as_of == as_of_input.as_of
    assert first.mtf_policy_version == "mtf-utc-closed-v1"
    assert dict(first.components) == {}


def test_snapshot_rejects_mismatched_visible_universe() -> None:
    run = _run()
    wrong = AnalyticsAsOfInput(
        **{
            **_as_of().canonical_payload(),
            "source_cursor_fingerprint": "c" * 64,
            "dataset_content_sha256": "d" * 64,
        }
    )
    with pytest.raises(ValueError, match="dataset_content_sha256"):
        AnalyticsSnapshot.create(analytics_run=run, as_of_input=wrong)


def test_future_observation_availability_is_rejected() -> None:
    as_of = datetime(2026, 1, 10, 12, tzinfo=UTC)
    with pytest.raises(ValueError, match="lookahead rejected"):
        AnalyticsObservationProvenance(
            source="future-event",
            event_at=as_of,
            available_at=as_of + timedelta(seconds=1),
            as_of=as_of,
        )


def test_schema_and_policy_versions_are_strict() -> None:
    run = _run()
    with pytest.raises(ValueError, match="schema_version"):
        AnalyticsLabRun(
            analytics_run_id=run.analytics_run_id,
            identity_sha256=run.identity_sha256,
            source_backtest_run_id=run.source_backtest_run_id,
            dataset_id=run.dataset_id,
            dataset_version=run.dataset_version,
            dataset_content_sha256=run.dataset_content_sha256,
            dataset_source=run.dataset_source,
            system_id=run.system_id,
            symbol=run.symbol,
            source_timeframe=run.source_timeframe,
            decision_timeframe=run.decision_timeframe,
            period_start=run.period_start,
            period_end=run.period_end,
            period_role=run.period_role,
            mtf_policy_version=run.mtf_policy_version,
            component_versions=run.component_versions,
            schema_version="money-heist.analytics-run.v999",
        )
