from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market.features.models import FeatureQuality, FeatureSnapshot, MarketRegime
from app.market.scanner.models import CandidateOpportunity, ScannerTrigger
from app.services.orchestration.task_force_report import (
    prepare_task_force_report_for_orchestration,
    task_force_report_fingerprint,
)
from app.task_force.aggregation import (
    TaskForceAggregatedFinding,
    TaskForceAggregatedMember,
    TaskForceReport,
)


NOW = datetime(2026, 9, 9, 15, 0, tzinfo=UTC)


def _opportunity() -> CandidateOpportunity:
    return CandidateOpportunity(
        scanner_version="scanner-v1",
        opportunity_id="11111111-1111-1111-1111-111111111111",
        snapshot_id="snapshot-1",
        system_id="balanced_v1",
        symbol="BTCUSDT",
        timeframe="1m",
        priority_score=80,
        triggers=(ScannerTrigger.RANGE_BREAK,),
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def _market(*, warmup_complete: bool = True) -> FeatureSnapshot:
    return FeatureSnapshot(
        feature_version="features-v1",
        snapshot_id="snapshot-1",
        source_snapshot_id="raw-1",
        symbol="BTCUSDT",
        timeframe="1m",
        observed_at=NOW + timedelta(minutes=1),
        candle_count=100,
        close=100.0,
        regime=MarketRegime.BULLISH_TREND,
        quality=FeatureQuality(
            warmup_complete=warmup_complete,
            closed_candle_count=100,
        ),
    )


def _report(*, aggregated_at: datetime | None = None) -> TaskForceReport:
    member = TaskForceAggregatedMember(
        member_id="member-berlin",
        agent_id="berlin",
        task_role="trend_regime",
        answer="Trend structure remains constructive.",
        confidence=Decimal("0.72"),
        finding_ids=("finding-1",),
        uncertainties=("Breakout follow-through is not yet confirmed.",),
        follow_up_questions=("Does volume confirm the breakout?",),
    )
    finding = TaskForceAggregatedFinding(
        member_id=member.member_id,
        agent_id=member.agent_id,
        finding_id="finding-1",
        summary="Trend regime is constructive but still conditional.",
        evidence_refs=("market_snapshot:snapshot-1",),
    )
    draft = TaskForceReport(
        task_force_id="tf-1",
        execution_run_id="run-1",
        request_id="request-1",
        system_id="balanced_v1",
        opportunity_id="11111111-1111-1111-1111-111111111111",
        objective="Investigate contradictory signals.",
        question="What evidence materially changes the thesis?",
        execution_contract_fingerprint_sha256="a" * 64,
        execution_fingerprint_sha256="b" * 64,
        members=(member,),
        findings=(finding,),
        uncertainties=member.uncertainties,
        follow_up_questions=member.follow_up_questions,
        red_team_required=False,
        red_team_present=False,
        red_team_contributions=(),
        member_actual_cost_eur=Decimal("0.10"),
        member_attempt_count=1,
        aggregated_at=aggregated_at or NOW + timedelta(minutes=5),
        report_fingerprint_sha256="0" * 64,
    )
    fingerprint = task_force_report_fingerprint(draft)
    return TaskForceReport(
        **draft.model_dump(exclude={"report_fingerprint_sha256"}),
        report_fingerprint_sha256=fingerprint,
    )


def test_valid_report_is_exposed_as_advisory_professor_payload():
    report = _report()
    result = prepare_task_force_report_for_orchestration(
        report,
        opportunity=_opportunity(),
        market_context=_market(),
        now=NOW + timedelta(minutes=10),
    )
    assert result.task_force_id == report.task_force_id
    assert result.payload["report_fingerprint_sha256"] == report.report_fingerprint_sha256
    assert result.payload["findings"][0]["finding_id"] == "finding-1"
    assert result.advisory_only is True
    assert result.trade_proposal_authority is False
    assert result.registry_mutation is False
    assert result.risk_authority is False
    assert result.live_authority is False


def test_report_fingerprint_recomputes_exact_batch20c_material():
    report = _report()
    assert task_force_report_fingerprint(report) == report.report_fingerprint_sha256


def test_report_fingerprint_excludes_aggregation_timestamp_by_design():
    first = _report(aggregated_at=NOW + timedelta(minutes=5))
    later = first.model_copy(update={"aggregated_at": NOW + timedelta(minutes=6)})
    assert task_force_report_fingerprint(first) == task_force_report_fingerprint(later)


def test_stale_or_tampered_report_fingerprint_is_rejected():
    report = _report().model_copy(update={"report_fingerprint_sha256": "f" * 64})
    with pytest.raises(ValueError, match="fingerprint"):
        prepare_task_force_report_for_orchestration(
            report,
            opportunity=_opportunity(),
            market_context=_market(),
            now=NOW + timedelta(minutes=10),
        )


def test_report_must_target_same_system():
    report = _report().model_copy(update={"system_id": "other-system"})
    with pytest.raises(ValueError, match="system_id"):
        prepare_task_force_report_for_orchestration(
            report,
            opportunity=_opportunity(),
            market_context=_market(),
            now=NOW + timedelta(minutes=10),
        )


def test_report_must_target_same_opportunity():
    report = _report().model_copy(update={"opportunity_id": "other-opportunity"})
    with pytest.raises(ValueError, match="opportunity_id"):
        prepare_task_force_report_for_orchestration(
            report,
            opportunity=_opportunity(),
            market_context=_market(),
            now=NOW + timedelta(minutes=10),
        )


def test_unscoped_report_is_not_accepted_by_main_opportunity_pipeline():
    report = _report().model_copy(update={"opportunity_id": None})
    with pytest.raises(ValueError, match="opportunity-scoped"):
        prepare_task_force_report_for_orchestration(
            report,
            opportunity=_opportunity(),
            market_context=_market(),
            now=NOW + timedelta(minutes=10),
        )


def test_report_cannot_predate_source_market_snapshot():
    report = _report(aggregated_at=NOW + timedelta(seconds=30))
    with pytest.raises(ValueError, match="market snapshot"):
        prepare_task_force_report_for_orchestration(
            report,
            opportunity=_opportunity(),
            market_context=_market(),
            now=NOW + timedelta(minutes=10),
        )


def test_report_cannot_come_from_future():
    report = _report(aggregated_at=NOW + timedelta(minutes=20))
    with pytest.raises(ValueError, match="future"):
        prepare_task_force_report_for_orchestration(
            report,
            opportunity=_opportunity(),
            market_context=_market(),
            now=NOW + timedelta(minutes=10),
        )


def test_expired_opportunity_cannot_consume_report():
    with pytest.raises(PermissionError, match="expired opportunity"):
        prepare_task_force_report_for_orchestration(
            _report(),
            opportunity=_opportunity(),
            market_context=_market(),
            now=NOW + timedelta(hours=1),
        )


def test_report_produced_at_or_after_opportunity_expiry_is_rejected():
    report = _report(aggregated_at=NOW + timedelta(hours=1))
    with pytest.raises(PermissionError, match="after opportunity expiry"):
        prepare_task_force_report_for_orchestration(
            report,
            opportunity=_opportunity(),
            market_context=_market(),
            now=NOW + timedelta(hours=1, minutes=1),
        )


def test_incomplete_market_warmup_fails_closed():
    with pytest.raises(ValueError, match="warmup"):
        prepare_task_force_report_for_orchestration(
            _report(),
            opportunity=_opportunity(),
            market_context=_market(warmup_complete=False),
            now=NOW + timedelta(minutes=10),
        )
