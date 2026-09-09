from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.evaluation.models import AgentMetrics, Metric
from app.recruitment import (
    RecruitmentAdvisoryAction,
    RecruitmentBaselineSpec,
    RecruitmentCampaignExecutionReport,
    RecruitmentCandidateState,
    RecruitmentCriterionEvaluationStatus,
    RecruitmentEvidencePurpose,
    RecruitmentLifecycleRecord,
    RecruitmentMetricDirection,
    RecruitmentProposal,
    RecruitmentSuccessCriterion,
    RecruitmentVariantExecution,
    bridge_recruitment_to_ablation,
    build_candidate_evidence_package,
    build_candidate_reputation_evidence,
    build_recruitment_campaign,
    evaluate_recruitment_advisory,
    evaluate_recruitment_evidence,
    specify_recruitment_candidate,
)
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.reports import BacktestMetricSnapshot, BacktestPeriodReport
from app.services.backtest.splits import BacktestPeriodRole


def _criterion(
    metric_key: str = "marginal_economic_net_eur",
    *,
    direction: RecruitmentMetricDirection = RecruitmentMetricDirection.AT_LEAST,
    threshold: str = "0",
    primary: bool = True,
) -> RecruitmentSuccessCriterion:
    return RecruitmentSuccessCriterion(
        metric_key=metric_key,
        direction=direction,
        threshold=Decimal(threshold),
        primary=primary,
        rationale="Frozen before OOS evaluation.",
    )


def _candidate(
    *,
    budget: str = "5",
    criteria: tuple[RecruitmentSuccessCriterion, ...] | None = None,
):
    proposal = RecruitmentProposal(
        recruitment_id="recruitment-19d-001",
        proposed_name="Marseille",
        role="liquidation_specialist",
        problem="Liquidation context is not covered by the incumbent crew.",
        hypothesis="The candidate improves OOS economic evidence net of AI cost.",
        trigger_evidence_refs=("eval:error-family:liquidation",),
    )
    return specify_recruitment_candidate(
        proposal,
        required_data=("liquidations",),
        allowed_tools=("get_liquidation_context",),
        model_class="specialist-small",
        budget_limit_eur=Decimal(budget),
        evaluation_window="frozen DESIGN/VALIDATION/OOS windows",
        baseline=RecruitmentBaselineSpec(
            baseline_id="balanced-v1-incumbent",
            system_id="balanced_v1",
            description="Existing crew without the candidate.",
        ),
        success_criteria=criteria or (_criterion(),),
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


def _snapshot(value: str) -> BacktestMetricSnapshot:
    return BacktestMetricSnapshot(value=Decimal(value), status="AVAILABLE")


def _period_report(variant, *, with_candidate: bool, ai_cost: str | None = None):
    if with_candidate:
        trading_net = "13"
        economic_net = "11"
        drawdown = "9"
        total_ai = ai_cost or "3.5"
        closed = 3
        marker = "b"
    else:
        trading_net = "10"
        economic_net = "8"
        drawdown = "12"
        total_ai = ai_cost or "2"
        closed = 2
        marker = "a"
    return BacktestPeriodReport(
        role=variant.role,
        run_id=variant.run.run_id,
        dataset_id=variant.run.dataset.dataset_id,
        period_start=variant.run.period_start,
        period_end=variant.run.period_end,
        processed_candles=3,
        opportunity_count=2,
        executed_order_count=closed,
        closed_trade_count=closed,
        trading_net=_snapshot(trading_net),
        max_drawdown_pct=_snapshot(drawdown),
        ai_cost_eur=Decimal(total_ai),
        economic_net=_snapshot(economic_net),
        self_funding_ratio=None,
        self_funding_status="UNAVAILABLE",
        business_sha256=marker * 64,
    )


def _agent_metrics(
    agent_id: str,
    *,
    cost: str = "1.2",
    average_confidence: Metric | None = None,
) -> AgentMetrics:
    return AgentMetrics(
        agent_id=agent_id,
        call_count=4,
        attempt_count=4,
        total_cost_eur=Decimal(cost),
        average_cost_eur=Metric.available(Decimal(cost) / Decimal("4")),
        average_latency_ms=Metric.available(Decimal("120")),
        participation_frequency=Metric.available(Decimal("0.8")),
        disagreement_frequency=Metric.available(Decimal("0.25")),
        average_confidence=average_confidence or Metric.available(Decimal("0.7")),
        stance_counts={"LONG": 3, "NEUTRAL": 1},
        final_decision_counts={"TRADE": 2, "NO_TRADE": 2},
        prompt_versions=("candidate-v1",),
        route_ids=("specialist",),
        model_ids=("specialist-small",),
    )


def _eval_bundle(*, total_cost: str, agents=(), by_agent=None, version: str = "batch10.v1"):
    return SimpleNamespace(
        report=SimpleNamespace(
            report_version=version,
            agents=tuple(agents),
            ai_costs=SimpleNamespace(
                total_cost_eur=Decimal(total_cost),
                by_agent={} if by_agent is None else dict(by_agent),
            ),
        )
    )


def _package(
    *,
    role: BacktestPeriodRole = BacktestPeriodRole.OOS,
    budget: str = "5",
    criteria: tuple[RecruitmentSuccessCriterion, ...] | None = None,
    direct_candidate_cost: str = "1.2",
    with_total_cost: str = "3.5",
    average_confidence: Metric | None = None,
):
    candidate = _candidate(budget=budget, criteria=criteria)
    plan = build_recruitment_campaign(
        _source_run(),
        candidate,
        role=role,
        baseline_agents=("berlin", "tokyo"),
    )
    metrics = _agent_metrics(
        plan.candidate_agent_id,
        cost=direct_candidate_cost,
        average_confidence=average_confidence,
    )
    baseline = RecruitmentVariantExecution(
        variant=plan.baseline,
        period_report=_period_report(plan.baseline, with_candidate=False),
        replay_result=object(),
        evaluation_bundle=_eval_bundle(
            total_cost="2",
            agents=(),
            by_agent={"berlin": Decimal("2")},
        ),
    )
    with_candidate = RecruitmentVariantExecution(
        variant=plan.with_candidate,
        period_report=_period_report(
            plan.with_candidate,
            with_candidate=True,
            ai_cost=with_total_cost,
        ),
        replay_result=object(),
        evaluation_bundle=_eval_bundle(
            total_cost=with_total_cost,
            agents=(metrics,),
            by_agent={
                plan.candidate_agent_id: Decimal(direct_candidate_cost),
                "berlin": Decimal(with_total_cost) - Decimal(direct_candidate_cost),
            },
        ),
    )
    execution = RecruitmentCampaignExecutionReport(
        campaign_id=plan.campaign_id,
        comparison_fingerprint=plan.comparison_fingerprint,
        recruitment_id=plan.recruitment_id,
        role=plan.role,
        executions=(baseline, with_candidate),
        execution_fingerprint="e" * 64,
    )
    purpose = (
        RecruitmentEvidencePurpose.PROMOTION
        if role is BacktestPeriodRole.OOS
        else RecruitmentEvidencePurpose.DIAGNOSTIC
    )
    gate = evaluate_recruitment_evidence(plan, candidate, execution, purpose=purpose)
    bridge = bridge_recruitment_to_ablation(plan, candidate, execution, gate)
    reputation = build_candidate_reputation_evidence(
        plan,
        candidate,
        execution,
        gate,
        bridge,
    )
    return build_candidate_evidence_package(
        plan,
        candidate,
        execution,
        gate,
        bridge,
        reputation,
    )


def _lifecycle(package, state: RecruitmentCandidateState) -> RecruitmentLifecycleRecord:
    return RecruitmentLifecycleRecord(
        recruitment_id=package.recruitment_id,
        proposed_name="Marseille",
        current_state=state,
        revision=2,
    )


def test_shadow_all_frozen_criteria_pass_recommends_probation() -> None:
    package = _package()
    report = evaluate_recruitment_advisory(
        package,
        _lifecycle(package, RecruitmentCandidateState.SHADOW),
    )

    assert report.action is RecruitmentAdvisoryAction.PROBATION
    assert report.evidence_sufficient is True
    assert report.criteria_all_passed is True
    assert report.criteria[0].status is RecruitmentCriterionEvaluationStatus.PASS
    assert report.criteria[0].observed_value == Decimal("3")
    assert report.auto_apply is False
    assert report.lifecycle_transition_applied is False
    assert report.registry_mutation is False
    assert report.promotion_applied is False
    assert report.live_authority is False


def test_probation_all_frozen_criteria_pass_recommends_promotion_only() -> None:
    package = _package()
    report = evaluate_recruitment_advisory(
        package,
        _lifecycle(package, RecruitmentCandidateState.PROBATION),
    )

    assert report.action is RecruitmentAdvisoryAction.RECOMMEND_PROMOTION
    assert "PROBATION_EVIDENCE_SUPPORTS_PROMOTION_RECOMMENDATION" in report.reason_codes
    assert report.promotion_applied is False


def test_candidate_state_cannot_skip_shadow_even_when_criteria_pass() -> None:
    package = _package()
    report = evaluate_recruitment_advisory(
        package,
        _lifecycle(package, RecruitmentCandidateState.CANDIDATE),
    )

    assert report.action is RecruitmentAdvisoryAction.EXTEND
    assert report.criteria_all_passed is True
    assert "SHADOW_STAGE_REQUIRED_BEFORE_PROBATION" in report.reason_codes


def test_any_failed_required_criterion_rejects_candidate() -> None:
    criteria = (
        _criterion(),
        _criterion(
            "average_confidence",
            threshold="0.9",
            primary=False,
        ),
    )
    package = _package(criteria=criteria)
    report = evaluate_recruitment_advisory(
        package,
        _lifecycle(package, RecruitmentCandidateState.SHADOW),
    )

    assert report.action is RecruitmentAdvisoryAction.REJECT
    assert report.criteria[0].status is RecruitmentCriterionEvaluationStatus.PASS
    assert report.criteria[1].status is RecruitmentCriterionEvaluationStatus.FAIL
    assert "CRITERION_FAILED:average_confidence" in report.reason_codes


def test_unsupported_pre_registered_metric_fails_closed_to_extend() -> None:
    package = _package(criteria=(_criterion("profit_factor"),))
    report = evaluate_recruitment_advisory(
        package,
        _lifecycle(package, RecruitmentCandidateState.SHADOW),
    )

    assert report.action is RecruitmentAdvisoryAction.EXTEND
    assert report.evidence_sufficient is False
    assert report.criteria[0].status is RecruitmentCriterionEvaluationStatus.UNSUPPORTED
    assert "CRITERION_UNSUPPORTED:profit_factor" in report.reason_codes


def test_unavailable_supported_metric_fails_closed_to_extend() -> None:
    package = _package(
        criteria=(_criterion("average_confidence"),),
        average_confidence=Metric.unavailable("NO_CONFIDENCE_OBSERVATIONS"),
    )
    report = evaluate_recruitment_advisory(
        package,
        _lifecycle(package, RecruitmentCandidateState.SHADOW),
    )

    assert report.action is RecruitmentAdvisoryAction.EXTEND
    assert report.criteria[0].status is RecruitmentCriterionEvaluationStatus.UNAVAILABLE
    assert "CRITERION_UNAVAILABLE:average_confidence" in report.reason_codes


def test_design_diagnostic_evidence_never_evaluates_oos_success_thresholds() -> None:
    package = _package(role=BacktestPeriodRole.DESIGN)
    report = evaluate_recruitment_advisory(
        package,
        _lifecycle(package, RecruitmentCandidateState.SHADOW),
    )

    assert package.purpose is RecruitmentEvidencePurpose.DIAGNOSTIC
    assert report.action is RecruitmentAdvisoryAction.EXTEND
    assert report.evidence_sufficient is False
    assert report.criteria[0].status is RecruitmentCriterionEvaluationStatus.UNAVAILABLE
    assert report.criteria[0].observed_value is None
    assert "PROMOTION_GRADE_OOS_EVIDENCE_REQUIRED" in report.reason_codes


def test_candidate_budget_exceeded_rejects_even_if_success_criteria_pass() -> None:
    package = _package(
        budget="1",
        direct_candidate_cost="1.2",
        with_total_cost="3.5",
    )
    report = evaluate_recruitment_advisory(
        package,
        _lifecycle(package, RecruitmentCandidateState.SHADOW),
    )

    assert package.reputation_evidence.costs.candidate_direct_cost_within_budget is False
    assert report.criteria_all_passed is True
    assert report.action is RecruitmentAdvisoryAction.REJECT
    assert "CANDIDATE_BUDGET_EXCEEDED" in report.reason_codes


def test_drawdown_increase_metric_is_negative_of_batch18_drawdown_reduction() -> None:
    package = _package(
        criteria=(
            _criterion(
                "drawdown_increase_pct",
                direction=RecruitmentMetricDirection.AT_MOST,
                threshold="0",
            ),
        )
    )
    report = evaluate_recruitment_advisory(
        package,
        _lifecycle(package, RecruitmentCandidateState.SHADOW),
    )

    assert report.criteria[0].observed_value == Decimal("-3")
    assert report.criteria[0].status is RecruitmentCriterionEvaluationStatus.PASS
    assert report.action is RecruitmentAdvisoryAction.PROBATION


def test_same_inputs_produce_same_advisory_fingerprint() -> None:
    package = _package()
    lifecycle = _lifecycle(package, RecruitmentCandidateState.SHADOW)

    first = evaluate_recruitment_advisory(package, lifecycle)
    second = evaluate_recruitment_advisory(package, lifecycle)

    assert first == second
    assert first.audit_fingerprint_sha256 == second.audit_fingerprint_sha256


def test_advisory_contract_detects_tampering_with_stale_fingerprint() -> None:
    package = _package()
    report = evaluate_recruitment_advisory(
        package,
        _lifecycle(package, RecruitmentCandidateState.SHADOW),
    )

    with pytest.raises(ValueError, match="fingerprint does not match payload"):
        replace(report, action=RecruitmentAdvisoryAction.REJECT)


def test_lifecycle_identity_mismatch_is_rejected() -> None:
    package = _package()
    lifecycle = RecruitmentLifecycleRecord(
        recruitment_id="other-recruitment",
        proposed_name="Other",
        current_state=RecruitmentCandidateState.SHADOW,
    )

    with pytest.raises(ValueError, match="different recruitment ids"):
        evaluate_recruitment_advisory(package, lifecycle)


def test_terminal_recruitment_states_are_not_re_advised() -> None:
    package = _package()

    for state in (
        RecruitmentCandidateState.REJECTED,
        RecruitmentCandidateState.PROMOTION_RECOMMENDED,
    ):
        with pytest.raises(ValueError, match="requires CANDIDATE, SHADOW, or PROBATION"):
            evaluate_recruitment_advisory(package, _lifecycle(package, state))
