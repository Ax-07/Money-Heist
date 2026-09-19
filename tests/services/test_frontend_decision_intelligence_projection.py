from datetime import UTC, datetime

import pytest

from app.services.frontend_v2.decision_intelligence import (
    CampaignNotFoundError,
    FrontendAnalyticsProjection,
    FrontendAnalyticsRefProjection,
    FrontendDecisionContextProjection,
    FrontendDecisionIntelligenceBundle,
    FrontendDecisionIntelligenceProjectionService,
    FrontendDecisionRecordProjection,
    FrontendFunnelStageProjection,
    FrontendOpportunityAnalyticsLinkProjection,
    FrontendScannerAnalyticsProjection,
    FrontendScannerEvaluationProjection,
    OpportunityNotFoundError,
    bundle_to_json,
    projection_export_name,
)

T = datetime(2026, 9, 17, 12, tzinfo=UTC)
SHA = "a" * 64


class FakeStore:
    def __init__(self, *, exists: bool = True, payload: str | None = None) -> None:
        self.exists = exists
        self.payload = payload

    def get(self, campaign_id: str) -> object | None:
        return object() if self.exists else None

    def persisted_export(self, campaign_id: str, name: str) -> str | None:
        assert name == projection_export_name("OOS")
        return self.payload


def _analytics_ref() -> FrontendAnalyticsRefProjection:
    return FrontendAnalyticsRefProjection(
        status="MATCHED",
        analytics_run_id="analytics-run",
        analytics_snapshot_id="snapshot-1",
        analytics_snapshot_fingerprint=SHA,
        analytics_as_of=T,
        source_cursor_fingerprint=SHA,
    )


def _scanner() -> FrontendScannerEvaluationProjection:
    return FrontendScannerEvaluationProjection(
        record_id="scanner-record",
        scanner_evaluation_id="feature-1",
        observed_at=T,
        symbol="BTC/EUR",
        decision_timeframe="1h",
        classification="CANDIDATE_OPPORTUNITY",
        score=80,
        priority_score=80,
        candidate_threshold=70,
        score_margin=10,
        triggers=("breakout",),
        candidate_opportunity_id="opp-1",
        analytics=_analytics_ref(),
    )


def _bundle() -> FrontendDecisionIntelligenceBundle:
    scanner = _scanner()
    decision = FrontendDecisionRecordProjection(
        record_id="decision-1",
        record_fingerprint=SHA,
        source_backtest_run_id="run-1",
        analytics_run_id="analytics-run",
        opportunity_id="opp-1",
        opportunity_fingerprint=SHA,
        system_id="balanced_v1",
        symbol="BTC/EUR",
        decision_timeframe="1h",
        observed_at=T,
        scanner=scanner,
        decision_context=FrontendDecisionContextProjection(present=False),
        decision={"professor_final": {"direction": "NO_TRADE"}},
        analytics=_analytics_ref(),
    )
    stage = FrontendFunnelStageProjection(
        record_id="stage-1",
        record_fingerprint=SHA,
        decision_intelligence_record_id="decision-1",
        opportunity_id="opp-1",
        stage="PROFESSOR_FINAL",
        stage_order=50,
        reached=True,
        stage_status="COMPLETED",
        stage_result="NO_TRADE",
        market_as_of=T,
        source_projection_fingerprint=SHA,
        analytics=_analytics_ref(),
    )
    link = FrontendOpportunityAnalyticsLinkProjection(
        link_id="link-1",
        link_fingerprint=SHA,
        status="MATCHED",
        opportunity_id="opp-1",
        opportunity_fingerprint=SHA,
        observed_at=T,
        decision_timeframe="1h",
        analytics_snapshot_id="snapshot-1",
        analytics_snapshot_fingerprint=SHA,
        analytics_as_of=T,
    )
    return FrontendDecisionIntelligenceBundle(
        campaign_id="campaign-1",
        role="OOS",
        analytics=FrontendAnalyticsProjection(
            campaign_id="campaign-1",
            role="OOS",
            analytics_available=False,
            unavailable_reason="TEST_NO_RUN_IDENTITY",
        ),
        scanner=FrontendScannerAnalyticsProjection(
            campaign_id="campaign-1",
            role="OOS",
            analytics_available=True,
            source_backtest_run_id="run-1",
            analytics_run_id="analytics-run",
            total_scanner_evaluations=1,
            matched_analytics=1,
            records=(scanner,),
            candidate_count=1,
        ),
        opportunity_links=(link,),
        decisions=(decision,),
        funnel_stages=(stage,),
    )


def test_missing_campaign_is_404_semantic() -> None:
    service = FrontendDecisionIntelligenceProjectionService(FakeStore(exists=False))
    with pytest.raises(CampaignNotFoundError):
        service.analytics("missing", "OOS")


def test_old_campaign_without_analytics_is_explicitly_available_false() -> None:
    service = FrontendDecisionIntelligenceProjectionService(FakeStore())
    analytics = service.analytics("campaign-1", "OOS")
    scanner = service.scanner("campaign-1", "OOS")
    detail = service.decision_detail("campaign-1", "OOS", "any-opportunity")

    assert analytics.analytics_available is False
    assert analytics.unavailable_reason == "PRECOMPUTED_ANALYTICS_UNAVAILABLE"
    assert scanner.analytics_available is False
    assert detail.decision_intelligence_available is False


def test_bundle_round_trip_and_opportunity_detail_are_deterministic() -> None:
    bundle = _bundle()
    service = FrontendDecisionIntelligenceProjectionService(
        FakeStore(payload=bundle_to_json(bundle))
    )

    first = service.decision_detail("campaign-1", "OOS", "opp-1")
    second = service.decision_detail("campaign-1", "OOS", "opp-1")

    assert first == second
    assert first.decision_intelligence_available is True
    assert first.record is not None
    assert first.record.decision["professor_final"]["direction"] == "NO_TRADE"
    assert first.funnel_stages[0].market_as_of == T
    assert first.funnel_stages[0].operational_at is None


def test_unknown_opportunity_is_not_hidden_when_bundle_exists() -> None:
    service = FrontendDecisionIntelligenceProjectionService(
        FakeStore(payload=bundle_to_json(_bundle()))
    )
    with pytest.raises(OpportunityNotFoundError):
        service.decision_detail("campaign-1", "OOS", "missing-opportunity")


def test_bundle_rejects_unstable_funnel_ordering() -> None:
    bundle = _bundle()
    late = bundle.funnel_stages[0].model_copy(update={"record_id": "late", "stage_order": 80})
    early = bundle.funnel_stages[0].model_copy(update={"record_id": "early", "stage_order": 10})
    with pytest.raises(ValueError, match="deterministically sorted"):
        FrontendDecisionIntelligenceBundle(
            campaign_id=bundle.campaign_id,
            role=bundle.role,
            analytics=bundle.analytics,
            scanner=bundle.scanner,
            opportunity_links=bundle.opportunity_links,
            decisions=bundle.decisions,
            funnel_stages=(late, early),
        )
