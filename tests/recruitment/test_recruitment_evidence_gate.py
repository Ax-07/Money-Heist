from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.recruitment import (
    RecruitmentBaselineSpec,
    RecruitmentCampaignExecutionReport,
    RecruitmentEvidenceBasis,
    RecruitmentEvidencePurpose,
    RecruitmentGateStatus,
    RecruitmentMetricDirection,
    RecruitmentProposal,
    RecruitmentSuccessCriterion,
    RecruitmentVariantExecution,
    build_recruitment_campaign,
    evaluate_recruitment_evidence,
    specify_recruitment_candidate,
)
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.splits import BacktestPeriodRole


def _candidate(*, threshold: Decimal = Decimal("0")):
    proposal = RecruitmentProposal(
        recruitment_id="recruitment-19b-003",
        proposed_name="Marseille",
        role="liquidation_specialist",
        problem="Liquidation context is not covered by the incumbent crew.",
        hypothesis="Adding a liquidation specialist improves OOS evidence net of AI cost.",
        trigger_evidence_refs=("eval:error-family:liquidation",),
    )
    return specify_recruitment_candidate(
        proposal,
        required_data=("liquidations",),
        allowed_tools=("get_liquidation_context",),
        model_class="specialist-small",
        budget_limit_eur=Decimal("5"),
        evaluation_window="frozen DESIGN/VALIDATION/OOS windows",
        baseline=RecruitmentBaselineSpec(
            baseline_id="balanced-v1-incumbent",
            system_id="balanced_v1",
            description="Existing crew without the candidate.",
        ),
        success_criteria=(
            RecruitmentSuccessCriterion(
                metric_key="marginal_economic_net_eur",
                direction=RecruitmentMetricDirection.AT_LEAST,
                threshold=threshold,
                primary=True,
                rationale="Primary criterion frozen before observing OOS.",
            ),
        ),
    )


def _source_run() -> BacktestRun:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = []
    for index in range(3):
        open_at = start + timedelta(hours=index)
        candles.append(
            {
                "open_time": open_at,
                "close_time": open_at + timedelta(minutes=59),
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100.5"),
                "volume": Decimal("1"),
            }
        )
    dataset = DatasetRef.from_candles(
        candles,
        symbol="BTC/EUR",
        timeframe="1h",
        source="test",
    )
    return BacktestRun.create(
        dataset=dataset,
        config=BacktestConfig(
            system_id="balanced_v1",
            risk_version="risk-v1",
            code_version="96b2288-test",
        ),
    )


def _report(variant, *, dataset_id=None, role=None, processed=3, opportunities=2, marker="a"):
    return SimpleNamespace(
        role=role or variant.role,
        run_id=variant.run.run_id,
        dataset_id=dataset_id or variant.run.dataset.dataset_id,
        period_start=variant.run.period_start,
        period_end=variant.run.period_end,
        processed_candles=processed,
        opportunity_count=opportunities,
        business_sha256=(marker * 64)[:64],
    )


def _execution(plan, *, baseline_report=None, candidate_report=None, candidate_variant=None):
    candidate_variant = candidate_variant or plan.with_candidate
    baseline_execution = RecruitmentVariantExecution(
        variant=plan.baseline,
        period_report=baseline_report or _report(plan.baseline, marker="a"),
        replay_result=object(),
        evaluation_bundle=object(),
    )
    candidate_execution = RecruitmentVariantExecution(
        variant=candidate_variant,
        period_report=candidate_report or _report(candidate_variant, marker="b"),
        replay_result=object(),
        evaluation_bundle=object(),
    )
    return RecruitmentCampaignExecutionReport(
        campaign_id=plan.campaign_id,
        comparison_fingerprint=plan.comparison_fingerprint,
        recruitment_id=plan.recruitment_id,
        role=plan.role,
        executions=(baseline_execution, candidate_execution),
        execution_fingerprint="e" * 64,
    )


def _plan(role=BacktestPeriodRole.OOS):
    candidate = _candidate()
    plan = build_recruitment_campaign(
        _source_run(),
        candidate,
        role=role,
        baseline_agents=("berlin", "tokyo"),
    )
    return candidate, plan


def test_comparable_oos_campaign_is_eligible_as_promotion_evidence_only() -> None:
    candidate, plan = _plan()
    decision = evaluate_recruitment_evidence(
        plan,
        candidate,
        _execution(plan),
        purpose=RecruitmentEvidencePurpose.PROMOTION,
    )

    assert decision.status is RecruitmentGateStatus.ALLOW
    assert decision.comparable is True
    assert decision.is_out_of_sample is True
    assert decision.reason_codes == ("COMPARABLE_OOS_PROMOTION_EVIDENCE",)
    assert decision.provenance.evidence_basis is RecruitmentEvidenceBasis.SIMULATED_HISTORICAL_REPLAY_PAPER
    assert decision.provenance.baseline_run_id == plan.baseline.run.run_id
    assert decision.provenance.candidate_run_id == plan.with_candidate.run.run_id
    assert decision.auto_apply is False
    assert decision.registry_mutation is False
    assert decision.promotion_action is False
    assert decision.live_authority is False


def test_design_campaign_can_be_diagnostic_but_not_promotion_evidence() -> None:
    candidate, plan = _plan(BacktestPeriodRole.DESIGN)
    execution = _execution(plan)

    diagnostic = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.DIAGNOSTIC,
    )
    promotion = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.PROMOTION,
    )

    assert diagnostic.status is RecruitmentGateStatus.ALLOW
    assert diagnostic.is_out_of_sample is False
    assert promotion.status is RecruitmentGateStatus.BLOCK
    assert "OOS_REQUIRED_FOR_PROMOTION_EVIDENCE" in promotion.reason_codes


def test_dataset_mismatch_blocks_evidence() -> None:
    candidate, plan = _plan()
    changed_dataset = replace(plan.with_candidate.run.dataset, dataset_id="other-dataset")
    changed_run = replace(plan.with_candidate.run, dataset=changed_dataset)
    changed_variant = replace(plan.with_candidate, run=changed_run)
    execution = _execution(
        plan,
        candidate_variant=changed_variant,
        candidate_report=_report(changed_variant, marker="b"),
    )
    decision = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.DIAGNOSTIC,
    )
    assert decision.status is RecruitmentGateStatus.BLOCK
    assert "DATASET_MISMATCH" in decision.reason_codes
    assert decision.comparable is False


def test_processed_candle_mismatch_blocks_evidence() -> None:
    candidate, plan = _plan()
    execution = _execution(
        plan,
        candidate_report=_report(plan.with_candidate, processed=2, marker="b"),
    )
    decision = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.DIAGNOSTIC,
    )
    assert decision.status is RecruitmentGateStatus.BLOCK
    assert "PROCESSED_CANDLES_MISMATCH" in decision.reason_codes


def test_opportunity_count_mismatch_blocks_evidence() -> None:
    candidate, plan = _plan()
    execution = _execution(
        plan,
        candidate_report=_report(plan.with_candidate, opportunities=3, marker="b"),
    )
    decision = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.DIAGNOSTIC,
    )
    assert decision.status is RecruitmentGateStatus.BLOCK
    assert "OPPORTUNITY_COUNT_MISMATCH" in decision.reason_codes


def test_success_criteria_drift_after_planning_blocks_evidence() -> None:
    candidate, plan = _plan()
    drifted = _candidate(threshold=Decimal("1"))
    decision = evaluate_recruitment_evidence(
        plan,
        drifted,
        _execution(plan),
        purpose=RecruitmentEvidencePurpose.PROMOTION,
    )
    assert decision.status is RecruitmentGateStatus.BLOCK
    assert "SUCCESS_CRITERIA_DRIFT" in decision.reason_codes


def test_material_backtest_config_mismatch_blocks_evidence() -> None:
    candidate, plan = _plan()
    changed_config = replace(plan.with_candidate.run.config, risk_version="risk-v2")
    changed_run = replace(plan.with_candidate.run, config=changed_config)
    changed_variant = replace(plan.with_candidate, run=changed_run)
    execution = _execution(
        plan,
        candidate_variant=changed_variant,
        candidate_report=_report(changed_variant, marker="b"),
    )
    decision = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.DIAGNOSTIC,
    )
    assert decision.status is RecruitmentGateStatus.BLOCK
    assert "MATERIAL_BACKTEST_CONFIG_MISMATCH" in decision.reason_codes


def test_variant_identity_drift_blocks_evidence() -> None:
    candidate, plan = _plan()
    changed_variant = replace(plan.with_candidate, variant_id="tampered-variant")
    execution = _execution(
        plan,
        candidate_variant=changed_variant,
        candidate_report=_report(changed_variant, marker="b"),
    )
    decision = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.DIAGNOSTIC,
    )
    assert decision.status is RecruitmentGateStatus.BLOCK
    assert "CANDIDATE_VARIANT_ID_MISMATCH" in decision.reason_codes


def test_gate_fingerprint_is_deterministic() -> None:
    candidate, plan = _plan()
    execution = _execution(plan)
    left = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.PROMOTION,
    )
    right = evaluate_recruitment_evidence(
        plan,
        candidate,
        execution,
        purpose=RecruitmentEvidencePurpose.PROMOTION,
    )
    assert left.audit_fingerprint_sha256 == right.audit_fingerprint_sha256
    assert len(left.audit_fingerprint_sha256) == 64
