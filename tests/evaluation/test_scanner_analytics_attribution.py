from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.analytics import (
    AnalyticsAsOfInput,
    AnalyticsComponentVersions,
    AnalyticsLabRun,
    AnalyticsPeriodRole,
    AnalyticsSnapshot,
)
from app.evaluation.analytics_attribution import (
    OpportunityAnalyticsLinkStatus,
    build_scanner_analytics_attribution,
    link_replay_opportunities,
)
from app.evaluation.scanner_forward_outcomes import (
    ScannerOutcomeClassification as ForwardScannerOutcomeClassification,
)
from app.evaluation.scanner_observations import ScannerOutcomeClassification
from app.market.scanner.models import CandidateOpportunity, ScannerTrigger, ScanResult
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import (
    BacktestConfig,
    BacktestResult,
    BacktestRun,
    BacktestRunStatus,
)

T = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
CURSORS = ("a" * 64, "b" * 64, "c" * 64)
DATASET_SHA = "d" * 64
POLICY = "mtf-utc-closed-v1"
THRESHOLD = 35


def source_run(
    *,
    scanner_version: str = "scanner-v1",
    dataset_sha: str = DATASET_SHA,
) -> BacktestRun:
    dataset = DatasetRef(
        dataset_id="BTC/EUR:15m:scanner-attribution",
        version=f"sha256:{dataset_sha}",
        content_sha256=dataset_sha,
        symbol="BTC/EUR",
        timeframe="15m",
        source="unit-test",
        candle_count=500,
        start_at=T - timedelta(days=2),
        end_at=T + timedelta(days=2),
    )
    config = BacktestConfig(
        system_id="balanced_v1",
        risk_version="risk-v1",
        feature_version="feature-engine-v1",
        scanner_version=scanner_version,
        execution_assumptions={
            "decision_timeframe": "1h",
            "historical_source_timeframe": "15m",
            "mtf_policy_version": POLICY,
        },
    )
    return BacktestRun.create(
        dataset=dataset,
        config=config,
        period_start=T - timedelta(days=1),
        period_end=T + timedelta(days=1),
    )


def replay_point(
    run: BacktestRun,
    *,
    step: int,
    score: int,
    triggers: tuple[ScannerTrigger, ...] = (),
    candidate: bool = False,
    cursor: str | None = None,
) -> SimpleNamespace:
    observed_at = T + timedelta(hours=step)
    snapshot_id = f"feature-{step}"
    feature = SimpleNamespace(
        snapshot_id=snapshot_id,
        symbol=run.dataset.symbol,
        timeframe="1h",
        observed_at=observed_at,
        feature_version=run.config.feature_version,
        regime=SimpleNamespace(value="range"),
    )
    opportunity = None
    if candidate:
        opportunity = CandidateOpportunity(
            scanner_version=run.config.scanner_version,
            opportunity_id=f"opp-{step}",
            snapshot_id=snapshot_id,
            system_id=run.config.system_id,
            symbol=run.dataset.symbol,
            timeframe="1h",
            priority_score=score,
            triggers=triggers,
            created_at=observed_at,
            expires_at=observed_at + timedelta(hours=1),
        )
    scan_result = ScanResult(
        score=score,
        triggers=triggers,
        opportunity=opportunity,
    )
    return SimpleNamespace(
        observed_at=observed_at,
        visible_candle_count=100 + step,
        feature_snapshot=feature,
        scan_result=scan_result,
        opportunity=opportunity,
        decision_timeframe="1h",
        mtf_cursor_fingerprint=cursor,
        decision_context=None,
        pipeline_result=None,
        account_state=None,
        exit_events=(),
    )


def replay(
    run: BacktestRun | None = None,
    *,
    cursors: tuple[str | None, ...] = CURSORS,
) -> SimpleNamespace:
    run = run or source_run()
    points = (
        replay_point(run, step=0, score=0, cursor=cursors[0]),
        replay_point(
            run,
            step=1,
            score=20,
            triggers=(ScannerTrigger.VOLUME_EXPANSION,),
            cursor=cursors[1],
        ),
        replay_point(
            run,
            step=2,
            score=35,
            triggers=(ScannerTrigger.RANGE_BREAK,),
            candidate=True,
            cursor=cursors[2],
        ),
    )
    result = BacktestResult(
        run=run,
        status=BacktestRunStatus.COMPLETED,
        processed_candles=len(points),
        opportunity_count=1,
        executed_order_count=0,
    )
    return SimpleNamespace(backtest_result=result, points=points)


def one_point_replay(
    run: BacktestRun,
    *,
    cursor: str | None = CURSORS[0],
) -> SimpleNamespace:
    point = replay_point(run, step=0, score=0, cursor=cursor)
    result = BacktestResult(
        run=run,
        status=BacktestRunStatus.COMPLETED,
        processed_candles=1,
        opportunity_count=0,
        executed_order_count=0,
    )
    return SimpleNamespace(backtest_result=result, points=(point,))


def versions(bundle: str = "analytics-24a7-v1") -> AnalyticsComponentVersions:
    return AnalyticsComponentVersions.foundation(analytics_bundle_version=bundle)


def analytics_run(
    run: BacktestRun,
    *,
    bundle: str = "analytics-24a7-v1",
    role: AnalyticsPeriodRole = AnalyticsPeriodRole.DESIGN,
) -> AnalyticsLabRun:
    return AnalyticsLabRun.create(
        source_backtest_run_id=run.run_id,
        dataset_id=run.dataset.dataset_id,
        dataset_version=run.dataset.version,
        dataset_content_sha256=run.dataset.content_sha256,
        dataset_source=run.dataset.source,
        system_id=run.config.system_id,
        symbol=run.dataset.symbol,
        source_timeframe=run.dataset.timeframe,
        decision_timeframe="1h",
        period_start=run.period_start,
        period_end=run.period_end,
        period_role=role,
        mtf_policy_version=POLICY,
        component_versions=versions(bundle),
    )


def snapshot(
    analytics: AnalyticsLabRun,
    *,
    as_of: datetime,
    cursor: str,
) -> AnalyticsSnapshot:
    as_of_input = AnalyticsAsOfInput(
        source_backtest_run_id=analytics.source_backtest_run_id,
        dataset_id=analytics.dataset_id,
        dataset_version=analytics.dataset_version,
        dataset_content_sha256=analytics.dataset_content_sha256,
        dataset_source=analytics.dataset_source,
        system_id=analytics.system_id,
        symbol=analytics.symbol,
        source_timeframe=analytics.source_timeframe,
        decision_timeframe=analytics.decision_timeframe,
        as_of=as_of,
        mtf_policy_version=analytics.mtf_policy_version,
        source_cursor_fingerprint=cursor,
    )
    return AnalyticsSnapshot.create(
        analytics_run=analytics,
        as_of_input=as_of_input,
        components={},
    )


def exact_snapshots(analytics: AnalyticsLabRun) -> tuple[AnalyticsSnapshot, ...]:
    return tuple(
        snapshot(
            analytics,
            as_of=T + timedelta(hours=index),
            cursor=CURSORS[index],
        )
        for index in range(3)
    )


def test_23a4_reexports_the_neutral_scanner_classification() -> None:
    assert ForwardScannerOutcomeClassification is ScannerOutcomeClassification


def test_every_scanner_evaluation_is_attributed_and_counts_are_conserved() -> None:
    run = source_run()
    analytics = analytics_run(run)
    result = build_scanner_analytics_attribution(
        replay(run),
        analytics_run=analytics,
        snapshots=exact_snapshots(analytics),
        min_priority_score=THRESHOLD,
    )

    assert result.total_scanner_evaluations == 3
    assert result.matched_analytics == 3
    assert result.unmatched_analytics == 0
    assert result.no_trigger_count == 1
    assert result.below_threshold_count == 1
    assert result.candidate_count == 1
    assert [item.scanner.classification for item in result.records] == [
        ScannerOutcomeClassification.NO_TRIGGER,
        ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD,
        ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY,
    ]
    assert [item.scanner_evaluation_id for item in result.records] == [
        "feature-0",
        "feature-1",
        "feature-2",
    ]
    assert [item.scanner.score_margin for item in result.records] == [-35, -15, 0]


def test_exact_as_of_matching_never_falls_back_to_previous_or_future_snapshot() -> None:
    run = source_run()
    analytics = analytics_run(run)
    source = one_point_replay(run)
    previous = snapshot(
        analytics,
        as_of=T - timedelta(hours=1),
        cursor=CURSORS[0],
    )
    future = snapshot(
        analytics,
        as_of=T + timedelta(hours=1),
        cursor=CURSORS[0],
    )

    for candidate in (previous, future):
        record = build_scanner_analytics_attribution(
            source,
            analytics_run=analytics,
            snapshots=(candidate,),
            min_priority_score=THRESHOLD,
        ).records[0]
        assert (
            record.analytics.status
            is OpportunityAnalyticsLinkStatus.MISSING_ANALYTICS_SNAPSHOT
        )
        assert record.analytics.analytics_snapshot is None


def test_cursor_fingerprint_mismatch_is_explicit_and_preserves_snapshot_ref() -> None:
    run = source_run()
    analytics = analytics_run(run)
    wrong_cursor_snapshot = snapshot(
        analytics,
        as_of=T,
        cursor="e" * 64,
    )
    record = build_scanner_analytics_attribution(
        one_point_replay(run),
        analytics_run=analytics,
        snapshots=(wrong_cursor_snapshot,),
        min_priority_score=THRESHOLD,
    ).records[0]

    assert (
        record.analytics.status
        is OpportunityAnalyticsLinkStatus.CURSOR_FINGERPRINT_MISMATCH
    )
    assert record.analytics.analytics_snapshot is not None
    assert record.analytics.analytics_snapshot.analytics_snapshot_id == (
        wrong_cursor_snapshot.snapshot_id
    )


def test_missing_source_cursor_is_explicit_provenance_failure() -> None:
    run = source_run()
    analytics = analytics_run(run)
    record = build_scanner_analytics_attribution(
        one_point_replay(run, cursor=None),
        analytics_run=analytics,
        snapshots=(),
        min_priority_score=THRESHOLD,
    ).records[0]

    assert (
        record.analytics.status
        is OpportunityAnalyticsLinkStatus.SOURCE_PROVENANCE_INCOMPLETE
    )


def test_candidate_record_can_reference_exact_24b1_and_24b2_artifacts() -> None:
    run = source_run()
    source = replay(run)
    analytics = analytics_run(run)
    snapshots = exact_snapshots(analytics)
    opportunity_links = link_replay_opportunities(
        source,
        analytics_run=analytics,
        snapshots=snapshots,
    )
    candidate_link = opportunity_links.links[0]
    fake_decision_record = SimpleNamespace(
        record_id="decision-record-1",
        source_backtest_run_id=run.run_id,
        analytics_run_id=analytics.analytics_run_id,
        opportunity_id="opp-2",
        observed_at=T + timedelta(hours=2),
        scanner=SimpleNamespace(snapshot_id="feature-2"),
        analytics=SimpleNamespace(
            status="MATCHED",
            analytics_snapshot_id=candidate_link.analytics_snapshot.analytics_snapshot_id,
        ),
    )
    decision_set = SimpleNamespace(
        source_backtest_run_id=run.run_id,
        analytics_run_id=analytics.analytics_run_id,
        records=(fake_decision_record,),
    )

    result = build_scanner_analytics_attribution(
        source,
        analytics_run=analytics,
        snapshots=snapshots,
        min_priority_score=THRESHOLD,
        opportunity_links=opportunity_links,
        decision_intelligence_records=decision_set,
    )
    candidate = result.records[-1]

    assert candidate.scanner.candidate_opportunity_id == "opp-2"
    assert candidate.analytics.opportunity_analytics_link_id == candidate_link.link_id
    assert candidate.analytics.decision_intelligence_record_id == "decision-record-1"
    assert candidate.analytics.status is OpportunityAnalyticsLinkStatus.MATCHED


def test_supplied_24b1_link_set_must_cover_candidate_rows() -> None:
    run = source_run()
    source = replay(run)
    analytics = analytics_run(run)
    empty_source = one_point_replay(run)
    empty_links = link_replay_opportunities(
        empty_source,
        analytics_run=analytics,
        snapshots=exact_snapshots(analytics),
    )
    assert empty_links.total_opportunities == 0

    with pytest.raises(ValueError, match="missing its 24B.1 link"):
        build_scanner_analytics_attribution(
            source,
            analytics_run=analytics,
            snapshots=exact_snapshots(analytics),
            min_priority_score=THRESHOLD,
            opportunity_links=empty_links,
        )


@pytest.mark.parametrize(
    "role",
    (
        AnalyticsPeriodRole.DESIGN,
        AnalyticsPeriodRole.VALIDATION,
        AnalyticsPeriodRole.OOS,
    ),
)
def test_analytics_period_role_is_preserved_strictly(role: AnalyticsPeriodRole) -> None:
    run = source_run()
    analytics = analytics_run(run, role=role)
    result = build_scanner_analytics_attribution(
        replay(run),
        analytics_run=analytics,
        snapshots=exact_snapshots(analytics),
        min_priority_score=THRESHOLD,
    )

    assert result.analytics_period_role == role.value
    assert all(item.analytics_run_id == analytics.analytics_run_id for item in result.records)


def test_same_inputs_produce_same_ids_fingerprints_and_json() -> None:
    run = source_run()
    source = replay(run)
    analytics = analytics_run(run)
    snapshots = exact_snapshots(analytics)

    first = build_scanner_analytics_attribution(
        source,
        analytics_run=analytics,
        snapshots=snapshots,
        min_priority_score=THRESHOLD,
    )
    second = build_scanner_analytics_attribution(
        source,
        analytics_run=analytics,
        snapshots=tuple(reversed(snapshots)),
        min_priority_score=THRESHOLD,
    )

    assert first == second
    assert first.set_fingerprint == second.set_fingerprint
    assert [item.record_id for item in first.records] == [
        item.record_id for item in second.records
    ]
    assert [item.record_fingerprint for item in first.records] == [
        item.record_fingerprint for item in second.records
    ]
    assert first.model_dump_json() == second.model_dump_json()


def test_scanner_dataset_and_analytics_versions_change_attribution_identity() -> None:
    base_run = source_run()
    base_analytics = analytics_run(base_run, bundle="analytics-a")
    base = build_scanner_analytics_attribution(
        replay(base_run),
        analytics_run=base_analytics,
        snapshots=exact_snapshots(base_analytics),
        min_priority_score=THRESHOLD,
    )

    scanner_run = source_run(scanner_version="scanner-v2")
    scanner_analytics = analytics_run(scanner_run, bundle="analytics-a")
    scanner_changed = build_scanner_analytics_attribution(
        replay(scanner_run),
        analytics_run=scanner_analytics,
        snapshots=exact_snapshots(scanner_analytics),
        min_priority_score=THRESHOLD,
    )

    dataset_run = source_run(dataset_sha="f" * 64)
    dataset_analytics = analytics_run(dataset_run, bundle="analytics-a")
    dataset_changed = build_scanner_analytics_attribution(
        replay(dataset_run),
        analytics_run=dataset_analytics,
        snapshots=exact_snapshots(dataset_analytics),
        min_priority_score=THRESHOLD,
    )

    analytics_changed_run = analytics_run(base_run, bundle="analytics-b")
    analytics_changed = build_scanner_analytics_attribution(
        replay(base_run),
        analytics_run=analytics_changed_run,
        snapshots=exact_snapshots(analytics_changed_run),
        min_priority_score=THRESHOLD,
    )

    assert base_run.run_id != scanner_run.run_id
    assert base_run.run_id != dataset_run.run_id
    assert base_analytics.analytics_run_id != analytics_changed_run.analytics_run_id
    assert base.records[0].record_id != scanner_changed.records[0].record_id
    assert base.records[0].record_id != dataset_changed.records[0].record_id
    assert base.records[0].record_id != analytics_changed.records[0].record_id


def test_duplicate_scanner_evaluation_id_is_rejected() -> None:
    run = source_run()
    first = replay_point(run, step=0, score=0, cursor=CURSORS[0])
    second = replay_point(run, step=0, score=0, cursor=CURSORS[0])
    result = BacktestResult(
        run=run,
        status=BacktestRunStatus.COMPLETED,
        processed_candles=2,
        opportunity_count=0,
        executed_order_count=0,
    )
    source = SimpleNamespace(backtest_result=result, points=(first, second))
    analytics = analytics_run(run)

    with pytest.raises(ValueError, match="duplicate Scanner evaluation id"):
        build_scanner_analytics_attribution(
            source,
            analytics_run=analytics,
            snapshots=(),
            min_priority_score=THRESHOLD,
        )
