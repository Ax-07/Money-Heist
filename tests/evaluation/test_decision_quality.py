from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.common.canonical import stable_digest
from app.evaluation.decision_quality import (
    DecisionQualityIntegrityError,
    ResearchIntegrityCode,
    ResearchJoinIssue,
    ResearchJoinStatus,
    build_decision_quality_research_bundle,
)
from app.evaluation.forward_outcomes.models import (
    ForwardOutcomeFirstHit,
    ForwardOutcomeHorizon,
    ForwardOutcomeIncompleteReason,
    ForwardOutcomeRecord,
    ForwardOutcomeReport,
)
from app.evaluation.scanner_forward_outcomes.models import (
    ScannerForwardOutcomeRecord,
    ScannerForwardOutcomeReport,
    ScannerOutcomeClassification,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
HORIZONS = (1, 3, 5, 10, 20)
RUN_ID = "run-oos"
ANALYTICS_RUN_ID = "analytics-oos"
DATASET_ID = "dataset-1"
DATASET_VERSION = "dataset-v1"
DATASET_SHA = "a" * 64
SYSTEM_ID = "balanced_v1"
SYMBOL = "BTC/EUR"
SOURCE_TIMEFRAME = "1h"
DECISION_TIMEFRAME = "1h"


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


def complete_horizon(horizon: int, *, return_pct: str = "1") -> ForwardOutcomeHorizon:
    at = START + timedelta(hours=horizon)
    return ForwardOutcomeHorizon(
        horizon_bars=horizon,
        is_complete=True,
        bars_observed=horizon,
        gap_count=0,
        boundary_missing_bars=0,
        missing_close_times=(),
        expected_end_at=at,
        return_pct=Decimal(return_pct),
        max_upside_pct=Decimal("2"),
        max_downside_pct=Decimal("-1"),
        max_upside_at=at,
        max_downside_at=at,
        first_hit=ForwardOutcomeFirstHit.SAME_CANDLE,
        first_hit_at=at,
    )


def incomplete_horizon(horizon: int) -> ForwardOutcomeHorizon:
    return ForwardOutcomeHorizon(
        horizon_bars=horizon,
        is_complete=False,
        bars_observed=2,
        gap_count=0,
        boundary_missing_bars=max(horizon - 2, 1),
        missing_close_times=(),
        expected_end_at=START + timedelta(hours=horizon),
        incomplete_reason=ForwardOutcomeIncompleteReason.PERIOD_END,
    )


def horizons(*, return_pct: str = "1") -> tuple[ForwardOutcomeHorizon, ...]:
    return (
        complete_horizon(1, return_pct=return_pct),
        complete_horizon(3, return_pct=return_pct),
        incomplete_horizon(5),
        incomplete_horizon(10),
        incomplete_horizon(20),
    )


def analytics_ref(*, matched: bool = True):
    snapshot = (
        ns(
            analytics_snapshot_id="analytics-snapshot",
            analytics_snapshot_fingerprint="b" * 64,
            as_of=START,
        )
        if matched
        else None
    )
    return ns(
        status="MATCHED" if matched else "MISSING_ANALYTICS_SNAPSHOT",
        analytics_snapshot=snapshot,
        diagnostics=() if matched else ("no exact snapshot",),
    )


def observation(*, observed_at: datetime, snapshot_id: str):
    return ns(
        source_backtest_run_id=RUN_ID,
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        dataset_content_sha256=DATASET_SHA,
        dataset_source="fixture",
        system_id=SYSTEM_ID,
        symbol=SYMBOL,
        source_timeframe=SOURCE_TIMEFRAME,
        decision_timeframe=DECISION_TIMEFRAME,
        observed_at=observed_at,
        feature_snapshot_id=snapshot_id,
    )


def scanner_attribution_record(
    *,
    scan_id: str,
    observed_at: datetime,
    classification: ScannerOutcomeClassification,
    score: int,
    triggers: tuple[str, ...],
    opportunity_id: str | None = None,
    matched_analytics: bool = True,
):
    scanner = ns(
        scanner_evaluation_id=scan_id,
        snapshot_id=scan_id,
        observed_at=observed_at,
        symbol=SYMBOL,
        decision_timeframe=DECISION_TIMEFRAME,
        feature_version="features-v1",
        scanner_version="scanner-v1",
        score=score,
        candidate_threshold=35,
        score_margin=score - 35,
        triggers=triggers,
        market_regime="TREND",
        classification=classification,
        candidate_opportunity_id=opportunity_id,
    )
    return ns(
        record_id=f"scanner-attribution-{scan_id}",
        record_fingerprint=stable_digest({"scan": scan_id, "matched": matched_analytics}),
        source_backtest_run_id=RUN_ID,
        analytics_run_id=ANALYTICS_RUN_ID,
        scanner_evaluation_id=scan_id,
        observation=observation(observed_at=observed_at, snapshot_id=scan_id),
        scanner=scanner,
        analytics=analytics_ref(matched=matched_analytics),
    )


def scanner_set(*, candidate_analytics_matched: bool = True):
    records = (
        scanner_attribution_record(
            scan_id="scan-0",
            observed_at=START,
            classification=ScannerOutcomeClassification.NO_TRIGGER,
            score=0,
            triggers=(),
        ),
        scanner_attribution_record(
            scan_id="scan-1",
            observed_at=START + timedelta(hours=1),
            classification=ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD,
            score=31,
            triggers=("volume_expansion",),
        ),
        scanner_attribution_record(
            scan_id="scan-2",
            observed_at=START + timedelta(hours=2),
            classification=ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY,
            score=42,
            triggers=("breakout_candidate",),
            opportunity_id="opp-1",
            matched_analytics=candidate_analytics_matched,
        ),
    )
    return ns(
        source_backtest_run_id=RUN_ID,
        analytics_run_id=ANALYTICS_RUN_ID,
        analytics_period_role="OOS",
        records=records,
    )


def decision_record():
    return ns(
        record_id="decision-1",
        record_fingerprint="c" * 64,
        source_backtest_run_id=RUN_ID,
        analytics_run_id=ANALYTICS_RUN_ID,
        opportunity_id="opp-1",
        opportunity_fingerprint="d" * 64,
        system_id=SYSTEM_ID,
        symbol=SYMBOL,
        decision_timeframe=DECISION_TIMEFRAME,
        observed_at=START + timedelta(hours=2),
        scanner=ns(snapshot_id="scan-2"),
        analytics=ns(status="MATCHED"),
        decision=ns(
            professor_final=ns(direction="NO_TRADE"),
            palermo=ns(verdict="CAUTION"),
            risk=ns(status=None, reason_codes=()),
            trade_proposal=ns(side=None),
            paper_pipeline_status="NO_TRADE",
            orchestration_status="COMPLETED",
        ),
    )


def decision_set(*, include: bool = True):
    records = (decision_record(),) if include else ()
    return ns(
        source_backtest_run_id=RUN_ID,
        analytics_run_id=ANALYTICS_RUN_ID,
        records=records,
        set_fingerprint=stable_digest(tuple(item.record_fingerprint for item in records)),
    )


def candidate_outcome(*, return_pct: str = "1") -> ForwardOutcomeRecord:
    return ForwardOutcomeRecord(
        opportunity_id="opp-1",
        snapshot_id="scan-2",
        observed_at=START + timedelta(hours=2),
        reference_close=Decimal("100"),
        terminal_status="NO_TRADE",
        professor_direction="NO_TRADE",
        proposal_side=None,
        horizons=horizons(return_pct=return_pct),
    )


def forward_report(*, include: bool = True, run_id: str = RUN_ID, return_pct: str = "1"):
    records = (candidate_outcome(return_pct=return_pct),) if include else ()
    return ForwardOutcomeReport.model_construct(
        run_id=run_id,
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        dataset_content_sha256=DATASET_SHA,
        dataset_source="fixture",
        system_id=SYSTEM_ID,
        source_timeframe=SOURCE_TIMEFRAME,
        decision_timeframe=DECISION_TIMEFRAME,
        period_start=START,
        period_end=START + timedelta(hours=30),
        horizons=HORIZONS,
        records=records,
    )


def scanner_outcome(record) -> ScannerForwardOutcomeRecord:
    scanner = record.scanner
    return ScannerForwardOutcomeRecord(
        scan_id=scanner.scanner_evaluation_id,
        snapshot_id=scanner.snapshot_id,
        observed_at=scanner.observed_at,
        reference_close=Decimal("100"),
        classification=scanner.classification,
        score=scanner.score,
        min_priority_score=scanner.candidate_threshold,
        score_margin_to_threshold=scanner.score_margin,
        triggers=scanner.triggers,
        market_regime=scanner.market_regime,
        candidate_opportunity_id=scanner.candidate_opportunity_id,
        horizons=horizons(),
    )


def scanner_report(*, source=None, missing_scan_id: str | None = None, run_id: str = RUN_ID):
    source = source or scanner_set()
    records = tuple(
        scanner_outcome(record)
        for record in source.records
        if record.scanner_evaluation_id != missing_scan_id
    )
    return ScannerForwardOutcomeReport.model_construct(
        run_id=run_id,
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        dataset_content_sha256=DATASET_SHA,
        dataset_source="fixture",
        system_id=SYSTEM_ID,
        scanner_version="scanner-v1",
        min_priority_score=35,
        source_timeframe=SOURCE_TIMEFRAME,
        decision_timeframe=DECISION_TIMEFRAME,
        period_start=START,
        period_end=START + timedelta(hours=30),
        horizons=HORIZONS,
        records=records,
    )


def build_bundle(**overrides):
    scanners = overrides.pop("scanner_attribution", scanner_set())
    params = {
        "period_role": "OOS",
        "decision_intelligence": decision_set(),
        "scanner_attribution": scanners,
        "forward_outcomes": forward_report(),
        "scanner_forward_outcomes": scanner_report(source=scanners),
    }
    params.update(overrides)
    return build_decision_quality_research_bundle(**params)


def test_exact_candidate_and_scanner_join_preserves_causal_posthoc_separation():
    bundle = build_bundle()
    assert bundle.candidate_coverage.total == 1
    assert bundle.candidate_coverage.joined == 1
    assert bundle.scanner_coverage.total == 3
    assert bundle.scanner_coverage.joined == 3

    candidate = bundle.candidate_records[0]
    assert candidate.join_status is ResearchJoinStatus.MATCHED
    assert candidate.causal.decision.professor_final_direction == "NO_TRADE"
    assert candidate.causal.decision.palermo_verdict == "CAUTION"
    assert candidate.posthoc.future_outcome.horizons[2].is_complete is False
    assert candidate.posthoc.future_outcome.horizons[2].return_pct is None

    classifications = tuple(item.causal.scanner.classification for item in bundle.scanner_records)
    assert classifications == (
        "NO_TRIGGER",
        "TRIGGER_BELOW_CANDIDATE_THRESHOLD",
        "CANDIDATE_OPPORTUNITY",
    )
    assert bundle.scanner_records[0].causal.scanner.candidate_opportunity_id is None
    assert bundle.scanner_records[1].causal.scanner.candidate_opportunity_id is None
    assert bundle.scanner_records[2].causal.scanner.candidate_opportunity_id == "opp-1"


def test_missing_candidate_outcome_is_explicit_and_never_synthesizes_zero():
    bundle = build_bundle(forward_outcomes=forward_report(include=False))
    candidate = bundle.candidate_records[0]
    assert candidate.join_status is ResearchJoinStatus.MISSING_FORWARD_OUTCOME
    assert ResearchJoinIssue.MISSING_FORWARD_OUTCOME in candidate.join_issues
    assert candidate.posthoc.future_outcome is None
    assert candidate.posthoc.outcome_fingerprint is None
    assert bundle.candidate_coverage.missing_forward_outcome == 1


def test_missing_decision_intelligence_keeps_candidate_subject():
    bundle = build_bundle(decision_intelligence=decision_set(include=False))
    candidate = bundle.candidate_records[0]
    assert candidate.join_status is ResearchJoinStatus.MISSING_DECISION_INTELLIGENCE
    assert candidate.causal.decision is None
    assert bundle.candidate_coverage.missing_decision_intelligence == 1


def test_analytics_unmatched_does_not_discard_valid_outcome():
    scanners = scanner_set(candidate_analytics_matched=False)
    # Canonical 24B.3 requires Candidate Decision Intelligence Analytics status parity.
    decision = decision_record()
    decision.analytics.status = "MISSING_ANALYTICS_SNAPSHOT"
    decisions = ns(
        source_backtest_run_id=RUN_ID,
        analytics_run_id=ANALYTICS_RUN_ID,
        records=(decision,),
        set_fingerprint="e" * 64,
    )
    bundle = build_bundle(
        scanner_attribution=scanners,
        decision_intelligence=decisions,
        scanner_forward_outcomes=scanner_report(source=scanners),
    )
    candidate = bundle.candidate_records[0]
    assert candidate.join_status is ResearchJoinStatus.MISSING_ANALYTICS
    assert candidate.posthoc.future_outcome is not None
    assert candidate.causal.analytics.status == "MISSING_ANALYTICS_SNAPSHOT"
    assert bundle.candidate_coverage.missing_analytics == 1


def test_missing_scanner_outcome_keeps_no_trigger_record():
    scanners = scanner_set()
    bundle = build_bundle(
        scanner_attribution=scanners,
        scanner_forward_outcomes=scanner_report(source=scanners, missing_scan_id="scan-0"),
    )
    record = bundle.scanner_records[0]
    assert record.scan_id == "scan-0"
    assert record.join_status is ResearchJoinStatus.MISSING_FORWARD_OUTCOME
    assert record.posthoc.future_outcome is None
    assert bundle.scanner_coverage.missing_forward_outcome == 1


def test_cross_run_mismatch_fails_closed():
    with pytest.raises(DecisionQualityIntegrityError) as exc:
        build_bundle(forward_outcomes=forward_report(run_id="other-run"))
    assert exc.value.code is ResearchIntegrityCode.RUN_MISMATCH


def test_role_mismatch_fails_closed():
    with pytest.raises(DecisionQualityIntegrityError) as exc:
        build_bundle(period_role="DESIGN")
    assert exc.value.code is ResearchIntegrityCode.ROLE_MISMATCH


def test_candidate_scanner_outcome_identity_mismatch_fails_closed():
    scanners = scanner_set()
    report = scanner_report(source=scanners)
    broken = report.records[2].model_copy(update={"candidate_opportunity_id": "opp-other"})
    report = report.model_copy(update={"records": (*report.records[:2], broken)})
    with pytest.raises(DecisionQualityIntegrityError) as exc:
        build_bundle(scanner_attribution=scanners, scanner_forward_outcomes=report)
    assert exc.value.code is ResearchIntegrityCode.OBSERVATION_MISMATCH


def test_deterministic_ids_ordering_and_bundle_fingerprint():
    first = build_bundle()
    second = build_bundle()
    assert first.research_run.research_run_id == second.research_run.research_run_id
    assert first.bundle_fingerprint == second.bundle_fingerprint
    assert [item.record_id for item in first.candidate_records] == [
        item.record_id for item in second.candidate_records
    ]
    assert [item.record_id for item in first.scanner_records] == [
        item.record_id for item in second.scanner_records
    ]


def test_future_change_changes_posthoc_not_causal_fingerprint_or_record_id():
    first = build_bundle(forward_outcomes=forward_report(return_pct="1"))
    second = build_bundle(forward_outcomes=forward_report(return_pct="4"))
    left = first.candidate_records[0]
    right = second.candidate_records[0]
    assert left.record_id == right.record_id
    assert left.causal.causal_fingerprint == right.causal.causal_fingerprint
    assert left.posthoc.outcome_fingerprint != right.posthoc.outcome_fingerprint
    assert left.record_fingerprint != right.record_fingerprint


def test_strict_mode_requires_complete_expected_joins():
    with pytest.raises(ValueError, match="100% expected joins"):
        build_bundle(forward_outcomes=forward_report(include=False), strict=True)


def test_builder_does_not_mutate_source_artifacts():
    scanners = scanner_set()
    decisions = decision_set()
    forward = forward_report()
    scanner_forward = scanner_report(source=scanners)
    before = deepcopy((scanners, decisions, forward, scanner_forward))
    build_decision_quality_research_bundle(
        period_role="OOS",
        decision_intelligence=decisions,
        scanner_attribution=scanners,
        forward_outcomes=forward,
        scanner_forward_outcomes=scanner_forward,
    )
    assert scanners == before[0]
    assert decisions == before[1]
    assert forward == before[2]
    assert scanner_forward == before[3]


def test_optional_funnel_stage_attribution_is_validation_only():
    decisions = decision_set()
    funnel = ns(
        source_backtest_run_id=RUN_ID,
        analytics_run_id=ANALYTICS_RUN_ID,
        source_decision_record_set_fingerprint=decisions.set_fingerprint,
    )
    bundle = build_bundle(
        decision_intelligence=decisions,
        funnel_stage_attribution=funnel,
    )
    assert bundle.candidate_coverage.total == 1
    assert all("funnel" not in item.causal.model_dump() for item in bundle.candidate_records)


def test_funnel_stage_source_fingerprint_mismatch_fails_closed():
    funnel = ns(
        source_backtest_run_id=RUN_ID,
        analytics_run_id=ANALYTICS_RUN_ID,
        source_decision_record_set_fingerprint="f" * 64,
    )
    with pytest.raises(DecisionQualityIntegrityError) as exc:
        build_bundle(funnel_stage_attribution=funnel)
    assert exc.value.code is ResearchIntegrityCode.SOURCE_FINGERPRINT_MISMATCH
