from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.evaluation.analytics_attribution.funnel_stage_models import (
    FunnelStage,
    FunnelStageAnalyticsAttributionRecord,
    FunnelStageAnalyticsAttributionSet,
)
from app.evaluation.decision_quality.evidence import (
    ResearchReportType,
    build_decision_quality_evidence_index,
)
from app.evaluation.decision_quality.funnel_quality import (
    FunnelDecisionQualityCohort,
    FunnelDecisionQualityDimension,
    FunnelDecisionQualityReport,
)
from app.evaluation.decision_quality.models import (
    DecisionQualityResearchBundle,
    DecisionQualityResearchRun,
    ResearchSourceIdentity,
    ScannerCausalBlock,
    ScannerPosthocBlock,
    ScannerResearchProjection,
    ScannerResearchRecord,
)
from app.evaluation.decision_quality.scanner_filtering import (
    ScannerFilteringCohort,
    ScannerFilteringDimension,
    ScannerFilteringQualityReport,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def _bundle(*, posthoc_marker: str = "unchanged") -> DecisionQualityResearchBundle:
    source = ResearchSourceIdentity(
        source_backtest_run_id="run-oos",
        analytics_run_id="analytics-oos",
        period_role="OOS",
        dataset_id="dataset",
        dataset_version="v1",
        dataset_content_sha256=SHA_A,
        dataset_source="fixture",
        system_id="balanced_v1",
        symbol="BTC/EUR",
        source_timeframe="1h",
        decision_timeframe="1h",
    )
    run = DecisionQualityResearchRun.model_construct(
        research_run_id="research-oos",
        run_fingerprint=SHA_B,
        source=source,
    )
    records = []
    for index, classification in enumerate(
        ("NO_TRIGGER", "CANDIDATE_OPPORTUNITY"),
        start=1,
    ):
        scan_id = f"scan-{index}"
        projection = ScannerResearchProjection(
            scanner_evaluation_id=scan_id,
            snapshot_id=scan_id,
            classification=classification,
            score=20 if index == 1 else 50,
            candidate_threshold=35,
            score_margin=-15 if index == 1 else 15,
            triggers=() if index == 1 else ("RANGE_BREAK",),
            market_regime="RANGE" if index == 1 else "TREND",
            candidate_opportunity_id=None if index == 1 else "opp-2",
        )
        causal = ScannerCausalBlock.model_construct(
            source=source,
            scan_id=scan_id,
            observed_at=NOW + timedelta(hours=index),
            scanner=projection,
            causal_fingerprint=SHA_B if index == 1 else SHA_C,
        )
        records.append(
            ScannerResearchRecord.model_construct(
                research_run_id="research-oos",
                record_id=f"scanner-record-{index}",
                record_fingerprint=SHA_C if index == 1 else SHA_D,
                period_role="OOS",
                scan_id=scan_id,
                causal=causal,
                posthoc=ScannerPosthocBlock.model_construct(
                    future_outcome=posthoc_marker,
                    outcome_fingerprint=SHA_A,
                ),
            )
        )
    return DecisionQualityResearchBundle.model_construct(
        research_run=run,
        candidate_records=(),
        scanner_records=tuple(records),
        bundle_fingerprint=SHA_A,
    )


def _stage_set() -> FunnelStageAnalyticsAttributionSet:
    record = FunnelStageAnalyticsAttributionRecord.model_construct(
        record_id="stage-final-opp-2",
        record_fingerprint=SHA_B,
        source_backtest_run_id="run-oos",
        analytics_run_id="analytics-oos",
        decision_intelligence_record_id="di-2",
        opportunity_id="opp-2",
        stage=FunnelStage.PROFESSOR_FINAL,
        reached=True,
        stage_status="COMPLETED",
        stage_result="LONG",
        reason_codes=(),
        market_as_of=NOW + timedelta(hours=2),
        operational_at=NOW + timedelta(hours=2, seconds=1),
        agent_id=None,
    )
    return FunnelStageAnalyticsAttributionSet.model_construct(
        source_backtest_run_id="run-oos",
        analytics_run_id="analytics-oos",
        set_fingerprint=SHA_C,
        records=(record,),
    )


def _scanner_report() -> ScannerFilteringQualityReport:
    return ScannerFilteringQualityReport.model_construct(
        research_run_id="research-oos",
        source_backtest_run_id="run-oos",
        analytics_run_id="analytics-oos",
        period_role="OOS",
        source_bundle_fingerprint=SHA_A,
        report_fingerprint=SHA_B,
        cohorts=(
            ScannerFilteringCohort.model_construct(
                dimension=ScannerFilteringDimension.CLASSIFICATION,
                key="CANDIDATE_OPPORTUNITY",
                scanner_count=1,
                cohort_fingerprint=SHA_C,
            ),
            ScannerFilteringCohort.model_construct(
                dimension=ScannerFilteringDimension.TRIGGER,
                key="RANGE_BREAK",
                scanner_count=1,
                cohort_fingerprint=SHA_D,
            ),
        ),
    )


def _funnel_report() -> FunnelDecisionQualityReport:
    return FunnelDecisionQualityReport.model_construct(
        research_run_id="research-oos",
        source_backtest_run_id="run-oos",
        analytics_run_id="analytics-oos",
        period_role="OOS",
        source_bundle_fingerprint=SHA_A,
        source_funnel_stage_set_fingerprint=SHA_C,
        report_fingerprint=SHA_D,
        cohorts=(
            FunnelDecisionQualityCohort.model_construct(
                stage=FunnelStage.PROFESSOR_FINAL,
                dimension=FunnelDecisionQualityDimension.STAGE_RESULT,
                key="LONG",
                observation_count=1,
                member_refs=("stage-final-opp-2",),
                cohort_fingerprint=SHA_B,
            ),
        ),
    )


def test_evidence_membership_is_causal_deterministic_and_deduplicated() -> None:
    first = build_decision_quality_evidence_index(
        bundle=_bundle(posthoc_marker="A"),
        scanner_report=_scanner_report(),
        funnel_report=_funnel_report(),
        funnel_stage_attribution=_stage_set(),
    )
    second = build_decision_quality_evidence_index(
        bundle=_bundle(posthoc_marker="B"),
        scanner_report=_scanner_report(),
        funnel_report=_funnel_report(),
        funnel_stage_attribution=_stage_set(),
    )

    assert first.to_json() == second.to_json()
    assert first.index_fingerprint == second.index_fingerprint
    assert len(first.refs) == 3
    assert len({item.ref_id for item in first.refs}) == 3

    candidate = next(
        item
        for item in first.memberships
        if item.selector.report_type is ResearchReportType.SCANNER_FILTERING
        and item.selector.dimension == "CLASSIFICATION"
    )
    trigger = next(
        item
        for item in first.memberships
        if item.selector.report_type is ResearchReportType.SCANNER_FILTERING
        and item.selector.dimension == "TRIGGER"
    )
    funnel = next(
        item
        for item in first.memberships
        if item.selector.report_type is ResearchReportType.FUNNEL_DECISION_QUALITY
    )

    assert len(candidate.ref_ids) == 1
    assert trigger.ref_ids == candidate.ref_ids
    assert len(funnel.ref_ids) == 1
    funnel_ref = next(item for item in first.refs if item.ref_id == funnel.ref_ids[0])
    assert funnel_ref.navigation_at == NOW + timedelta(hours=2, seconds=1)
    scanner_ref = next(item for item in first.refs if item.ref_id == candidate.ref_ids[0])
    assert scanner_ref.navigation_at == scanner_ref.observed_at


def test_evidence_builder_does_not_mutate_source_report_json() -> None:
    scanner = _scanner_report()
    funnel = _funnel_report()
    before_scanner = scanner.to_json()
    before_funnel = funnel.to_json()

    build_decision_quality_evidence_index(
        bundle=_bundle(),
        scanner_report=scanner,
        funnel_report=funnel,
        funnel_stage_attribution=_stage_set(),
    )

    assert scanner.to_json() == before_scanner
    assert funnel.to_json() == before_funnel
