from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.analytics import (
    AnalyticsAsOfInput,
    AnalyticsComponentVersions,
    AnalyticsLabRun,
    AnalyticsPeriodRole,
    AnalyticsSnapshot,
)
from app.evaluation.analytics_attribution import (
    OpportunityAnalyticsLinker,
    OpportunityAnalyticsLinkStatus,
    build_opportunity_observations,
    link_replay_opportunities,
)
from app.market.scanner.models import CandidateOpportunity, ScannerTrigger, ScanResult
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import (
    BacktestConfig,
    BacktestResult,
    BacktestRun,
    BacktestRunStatus,
)
from app.services.backtest.reproducibility import fingerprint_backtest

T = datetime(2026, 1, 12, 14, 0, tzinfo=UTC)
CURSOR = "a" * 64
OTHER_CURSOR = "b" * 64
DATASET_SHA = "c" * 64
POLICY = "mtf-utc-closed-v1"


def source_run() -> BacktestRun:
    dataset = DatasetRef(
        dataset_id="BTC/EUR:15m:test",
        version="sha256:test",
        content_sha256=DATASET_SHA,
        symbol="BTC/EUR",
        timeframe="15m",
        source="unit-test",
        candle_count=100,
        start_at=T - timedelta(days=2),
        end_at=T + timedelta(days=2),
    )
    config = BacktestConfig(
        system_id="balanced_v1",
        risk_version="risk-v1",
        feature_version="feature-engine-v1",
        scanner_version="scanner-v1",
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


def replay(
    *,
    run: BacktestRun | None = None,
    observed_at: datetime = T,
    cursor: str | None = CURSOR,
    decision_context: object | None = None,
    opportunity_id: str = "opp-1",
) -> SimpleNamespace:
    run = run or source_run()
    feature = SimpleNamespace(
        snapshot_id=f"feature-{opportunity_id}",
        symbol=run.dataset.symbol,
        timeframe="1h",
        observed_at=observed_at,
        feature_version=run.config.feature_version,
    )
    opportunity = CandidateOpportunity(
        scanner_version=run.config.scanner_version,
        opportunity_id=opportunity_id,
        snapshot_id=feature.snapshot_id,
        system_id=run.config.system_id,
        symbol=run.dataset.symbol,
        timeframe="1h",
        priority_score=80,
        triggers=(ScannerTrigger.RANGE_BREAK,),
        created_at=observed_at,
        expires_at=observed_at + timedelta(hours=1),
    )
    scan_result = ScanResult(
        score=80,
        triggers=(ScannerTrigger.RANGE_BREAK,),
        opportunity=opportunity,
    )
    point = SimpleNamespace(
        observed_at=observed_at,
        visible_candle_count=100,
        feature_snapshot=feature,
        scan_result=scan_result,
        opportunity=opportunity,
        decision_timeframe="1h",
        mtf_cursor_fingerprint=cursor,
        decision_context=decision_context,
        pipeline_result=None,
        account_state=None,
        exit_events=(),
    )
    result = BacktestResult(
        run=run,
        status=BacktestRunStatus.COMPLETED,
        processed_candles=1,
        opportunity_count=1,
        executed_order_count=0,
    )
    return SimpleNamespace(backtest_result=result, points=(point,))


def versions(bundle: str = "analytics-24a7-v1") -> AnalyticsComponentVersions:
    return AnalyticsComponentVersions.foundation(analytics_bundle_version=bundle)


def analytics_run(
    run: BacktestRun,
    *,
    bundle: str = "analytics-24a7-v1",
    source_backtest_run_id: str | None = None,
    dataset_id: str | None = None,
    dataset_version: str | None = None,
    dataset_sha: str | None = None,
    dataset_source: str | None = None,
    system_id: str | None = None,
    symbol: str | None = None,
    source_timeframe: str = "15m",
    decision_timeframe: str = "1h",
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    policy: str = POLICY,
) -> AnalyticsLabRun:
    return AnalyticsLabRun.create(
        source_backtest_run_id=source_backtest_run_id or run.run_id,
        dataset_id=dataset_id or run.dataset.dataset_id,
        dataset_version=dataset_version or run.dataset.version,
        dataset_content_sha256=dataset_sha or run.dataset.content_sha256,
        dataset_source=dataset_source or run.dataset.source,
        system_id=system_id or run.config.system_id,
        symbol=symbol or run.dataset.symbol,
        source_timeframe=source_timeframe,
        decision_timeframe=decision_timeframe,
        period_start=period_start or run.period_start,
        period_end=period_end or run.period_end,
        period_role=AnalyticsPeriodRole.DESIGN,
        mtf_policy_version=policy,
        component_versions=versions(bundle),
    )


def snapshot(
    analytics: AnalyticsLabRun,
    *,
    as_of: datetime = T,
    cursor: str = CURSOR,
    components: dict[str, object] | None = None,
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
        components=components,
    )


def test_opportunity_links_to_same_as_of_analytics_snapshot() -> None:
    run = source_run()
    analytics = analytics_run(run)
    target = snapshot(analytics)

    links = link_replay_opportunities(
        replay(run=run),
        analytics_run=analytics,
        snapshots=(target,),
    )

    assert links.total_opportunities == 1
    assert links.matched == 1
    link = links.links[0]
    assert link.status is OpportunityAnalyticsLinkStatus.MATCHED
    assert link.analytics_snapshot is not None
    assert link.analytics_snapshot.analytics_snapshot_id == target.snapshot_id
    assert link.analytics_snapshot.as_of == T
    assert link.analytics_snapshot.source_cursor_fingerprint == CURSOR


def test_opportunity_does_not_link_to_previous_snapshot() -> None:
    run = source_run()
    analytics = analytics_run(run)
    previous = snapshot(analytics, as_of=T - timedelta(hours=1))

    link = link_replay_opportunities(
        replay(run=run),
        analytics_run=analytics,
        snapshots=(previous,),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.MISSING_ANALYTICS_SNAPSHOT
    assert link.analytics_snapshot is None


def test_opportunity_does_not_link_to_future_snapshot() -> None:
    run = source_run()
    analytics = analytics_run(run)
    future = snapshot(analytics, as_of=T + timedelta(hours=1))

    link = link_replay_opportunities(
        replay(run=run),
        analytics_run=analytics,
        snapshots=(future,),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.MISSING_ANALYTICS_SNAPSHOT
    assert link.analytics_snapshot is None


def test_link_rejects_cursor_fingerprint_mismatch() -> None:
    run = source_run()
    analytics = analytics_run(run)
    target = snapshot(analytics, cursor=OTHER_CURSOR)

    link = link_replay_opportunities(
        replay(run=run),
        analytics_run=analytics,
        snapshots=(target,),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.CURSOR_FINGERPRINT_MISMATCH
    assert link.analytics_snapshot is not None


def test_link_rejects_timeframe_mismatch() -> None:
    run = source_run()
    analytics = analytics_run(run, decision_timeframe="4h")

    link = link_replay_opportunities(
        replay(run=run),
        analytics_run=analytics,
        snapshots=(),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.TIMEFRAME_MISMATCH


def test_link_rejects_symbol_mismatch() -> None:
    run = source_run()
    analytics = analytics_run(run, symbol="ETH/EUR")

    link = link_replay_opportunities(
        replay(run=run),
        analytics_run=analytics,
        snapshots=(),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.SYMBOL_MISMATCH


def test_link_rejects_dataset_mismatch() -> None:
    run = source_run()
    analytics = analytics_run(run, dataset_sha="d" * 64)

    link = link_replay_opportunities(
        replay(run=run),
        analytics_run=analytics,
        snapshots=(),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.DATASET_MISMATCH


def test_link_rejects_source_backtest_run_mismatch() -> None:
    run = source_run()
    analytics = analytics_run(run, source_backtest_run_id="other-run")

    link = link_replay_opportunities(
        replay(run=run),
        analytics_run=analytics,
        snapshots=(),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.SOURCE_BACKTEST_RUN_MISMATCH


def test_link_rejects_mtf_policy_mismatch() -> None:
    run = source_run()
    analytics = analytics_run(run, policy="other-policy")

    link = link_replay_opportunities(
        replay(run=run),
        analytics_run=analytics,
        snapshots=(),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.MTF_POLICY_MISMATCH


def test_link_requires_source_cursor_provenance() -> None:
    run = source_run()
    analytics = analytics_run(run)

    link = link_replay_opportunities(
        replay(run=run, cursor=None),
        analytics_run=analytics,
        snapshots=(),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.SOURCE_PROVENANCE_INCOMPLETE


def test_missing_snapshot_is_explicit() -> None:
    run = source_run()
    analytics = analytics_run(run)

    link = link_replay_opportunities(
        replay(run=run),
        analytics_run=analytics,
        snapshots=(),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.MISSING_ANALYTICS_SNAPSHOT


def test_ambiguous_snapshot_is_explicit() -> None:
    run = source_run()
    analytics = analytics_run(run)
    first = snapshot(analytics, components={"variant": "a"})
    second = snapshot(analytics, components={"variant": "b"})
    assert first.snapshot_id != second.snapshot_id

    link = link_replay_opportunities(
        replay(run=run),
        analytics_run=analytics,
        snapshots=(first, second),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.AMBIGUOUS_ANALYTICS_SNAPSHOT
    assert link.analytics_snapshot is None
    assert first.snapshot_id in link.diagnostics[0]
    assert second.snapshot_id in link.diagnostics[0]


def test_same_inputs_produce_same_link_identity_and_fingerprint() -> None:
    run = source_run()
    analytics = analytics_run(run)
    target = snapshot(analytics)
    source = replay(run=run)

    first = link_replay_opportunities(
        source,
        analytics_run=analytics,
        snapshots=(target,),
    )
    second = link_replay_opportunities(
        source,
        analytics_run=analytics,
        snapshots=(target,),
    )

    assert first == second
    assert first.links[0].link_id == second.links[0].link_id
    assert first.links[0].link_fingerprint == second.links[0].link_fingerprint
    assert first.summary_fingerprint == second.summary_fingerprint
    assert first.model_dump_json() == second.model_dump_json()


def test_different_analytics_run_changes_link_identity() -> None:
    run = source_run()
    source = replay(run=run)
    analytics_a = analytics_run(run, bundle="analytics-a")
    analytics_b = analytics_run(run, bundle="analytics-b")
    link_a = link_replay_opportunities(
        source,
        analytics_run=analytics_a,
        snapshots=(snapshot(analytics_a),),
    ).links[0]
    link_b = link_replay_opportunities(
        source,
        analytics_run=analytics_b,
        snapshots=(snapshot(analytics_b),),
    ).links[0]

    assert analytics_a.analytics_run_id != analytics_b.analytics_run_id
    assert link_a.link_id != link_b.link_id
    assert link_a.link_fingerprint != link_b.link_fingerprint
    assert run.run_id == source.backtest_result.run.run_id


def test_different_analytics_runs_do_not_change_business_fingerprint() -> None:
    run = source_run()
    source = replay(run=run)
    analytics_a = analytics_run(run, bundle="analytics-a")
    analytics_b = analytics_run(run, bundle="analytics-b")
    links_a = link_replay_opportunities(
        source,
        analytics_run=analytics_a,
        snapshots=(snapshot(analytics_a),),
    )
    links_b = link_replay_opportunities(
        source,
        analytics_run=analytics_b,
        snapshots=(snapshot(analytics_b),),
    )

    baseline = fingerprint_backtest(source, _evaluation_report())
    source.analytics_attribution = links_a
    with_a = fingerprint_backtest(source, _evaluation_report())
    source.analytics_attribution = links_b
    with_b = fingerprint_backtest(source, _evaluation_report())

    assert links_a.links[0].link_id != links_b.links[0].link_id
    assert baseline == with_a == with_b
    assert baseline.run_id == run.run_id


def test_opportunity_without_decision_context_can_match() -> None:
    run = source_run()
    analytics = analytics_run(run)

    link = link_replay_opportunities(
        replay(run=run, decision_context=None),
        analytics_run=analytics,
        snapshots=(snapshot(analytics),),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.MATCHED
    assert link.opportunity.decision_context_id is None


def test_opportunity_with_decision_context_preserves_optional_reference() -> None:
    run = source_run()
    analytics = analytics_run(run)
    context = SimpleNamespace(
        context_id="decision-context-1",
        context_fingerprint="e" * 64,
        as_of=T,
        symbol="BTC/EUR",
        primary_timeframe="1h",
        timeframe_policy_version=POLICY,
        market=SimpleNamespace(source_cursor_fingerprint=CURSOR),
    )

    link = link_replay_opportunities(
        replay(run=run, decision_context=context),
        analytics_run=analytics,
        snapshots=(snapshot(analytics),),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.MATCHED
    assert link.opportunity.decision_context_id == "decision-context-1"
    assert link.opportunity.decision_context_fingerprint == "e" * 64


def test_future_snapshot_does_not_change_link_at_t() -> None:
    run = source_run()
    analytics = analytics_run(run)
    exact = snapshot(analytics)
    future = snapshot(analytics, as_of=T + timedelta(hours=1))
    source = replay(run=run)

    before = link_replay_opportunities(
        source,
        analytics_run=analytics,
        snapshots=(exact,),
    )
    after = link_replay_opportunities(
        source,
        analytics_run=analytics,
        snapshots=(exact, future),
    )

    assert before.links[0] == after.links[0]
    assert before.summary_fingerprint == after.summary_fingerprint


def test_as_of_outside_analytics_run_is_explicit() -> None:
    run = source_run()
    analytics = analytics_run(
        run,
        period_start=T + timedelta(hours=1),
        period_end=T + timedelta(hours=2),
    )

    link = link_replay_opportunities(
        replay(run=run),
        analytics_run=analytics,
        snapshots=(),
    ).links[0]

    assert link.status is OpportunityAnalyticsLinkStatus.AS_OF_MISMATCH


def test_link_set_order_is_deterministic() -> None:
    run = source_run()
    analytics = analytics_run(run)
    first_replay = replay(run=run, observed_at=T, opportunity_id="opp-b")
    second_replay = replay(
        run=run,
        observed_at=T - timedelta(hours=1),
        opportunity_id="opp-a",
    )
    combined = SimpleNamespace(
        backtest_result=first_replay.backtest_result,
        points=(first_replay.points[0], second_replay.points[0]),
    )
    first_snapshot = snapshot(analytics, as_of=T)
    second_snapshot = snapshot(analytics, as_of=T - timedelta(hours=1))

    links = link_replay_opportunities(
        combined,
        analytics_run=analytics,
        snapshots=(first_snapshot, second_snapshot),
    )

    assert [item.opportunity.opportunity_id for item in links.links] == [
        "opp-a",
        "opp-b",
    ]


def _metric(value: Decimal | None, status: str = "AVAILABLE", reason=None):
    return SimpleNamespace(value=value, status=status, reason=reason)


def _evaluation_report() -> SimpleNamespace:
    trading = SimpleNamespace(
        executed_fill_count=0,
        executed_order_count=0,
        closed_trade_count=0,
        open_position_count=0,
        winning_trades=0,
        losing_trades=0,
        breakeven_trades=0,
        execution_realized_pnl=Decimal("0"),
        fees_paid=Decimal("0"),
        realized_trading_net=Decimal("0"),
        slippage_cost=_metric(Decimal("0")),
        gross_pnl_before_costs=_metric(Decimal("0")),
        unrealized_pnl=_metric(Decimal("0")),
        trading_net=_metric(Decimal("0")),
        gross_exposure=_metric(Decimal("0")),
        win_rate=_metric(None, "UNAVAILABLE", "NO_CLOSED_TRADES"),
        profit_factor=_metric(None, "UNAVAILABLE", "NO_CLOSED_TRADES"),
        expectancy=_metric(None, "UNAVAILABLE", "NO_CLOSED_TRADES"),
        max_drawdown_abs=_metric(Decimal("0")),
        max_drawdown_pct=_metric(Decimal("0")),
        closed_trades=(),
    )
    return SimpleNamespace(
        report_version="batch10.evaluation.v1",
        trading=trading,
        ai_costs=SimpleNamespace(
            total_cost_eur=Decimal("0"),
            by_agent={},
            by_model={},
            by_route={},
        ),
        agents=(),
        economic_net=_metric(Decimal("0")),
        self_funding_ratio=SimpleNamespace(
            value=None,
            status="UNAVAILABLE",
            basis="TRADING_NET/AI_COST",
        ),
    )


def test_link_artifacts_do_not_change_business_fingerprint() -> None:
    run = source_run()
    source = replay(run=run)
    analytics = analytics_run(run)
    link_set = link_replay_opportunities(
        source,
        analytics_run=analytics,
        snapshots=(snapshot(analytics),),
    )

    before = fingerprint_backtest(source, _evaluation_report())
    source.analytics_attribution = link_set
    after = fingerprint_backtest(source, _evaluation_report())

    assert before == after
    assert before.run_id == run.run_id


def test_observation_adapter_uses_replay_cursor_without_context_requirement() -> None:
    run = source_run()
    observations = build_opportunity_observations(replay(run=run))

    assert len(observations) == 1
    observation = observations[0].observation
    assert observation.observed_at == T
    assert observation.source_cursor_fingerprint == CURSOR
    assert observation.dataset_content_sha256 == DATASET_SHA
    assert observation.feature_version == run.config.feature_version
    assert observation.scanner_version == run.config.scanner_version


def test_linker_can_be_reused_without_recomputing_analytics() -> None:
    run = source_run()
    analytics = analytics_run(run)
    target = snapshot(analytics)
    observations = build_opportunity_observations(replay(run=run))
    linker = OpportunityAnalyticsLinker(
        analytics_run=analytics,
        snapshots=(target,),
    )

    first = linker.link_all(observations)
    second = linker.link_all(observations)

    assert first == second
