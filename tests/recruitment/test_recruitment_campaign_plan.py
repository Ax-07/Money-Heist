from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.recruitment import (
    RecruitmentBaselineSpec,
    RecruitmentCampaignVariantKind,
    RecruitmentMetricDirection,
    RecruitmentProposal,
    RecruitmentSuccessCriterion,
    build_recruitment_campaign,
    candidate_runtime_agent_id,
    specify_recruitment_candidate,
)
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.models import BacktestConfig, BacktestRun
from app.services.backtest.splits import BacktestPeriodRole


def _candidate():
    proposal = RecruitmentProposal(
        recruitment_id="recruitment-19b-001",
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
                threshold=Decimal("0"),
                primary=True,
                rationale="Primary criterion frozen before observing OOS.",
            ),
            RecruitmentSuccessCriterion(
                metric_key="drawdown_reduction_pct",
                direction=RecruitmentMetricDirection.AT_LEAST,
                threshold=Decimal("0"),
                rationale="Candidate must not worsen the predeclared drawdown criterion.",
            ),
        ),
    )


def _source_run(*, assumptions=None, system_id="balanced_v1") -> BacktestRun:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(4):
        open_at = start + timedelta(hours=index)
        rows.append(
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
        rows,
        symbol="BTC/EUR",
        timeframe="1h",
        source="test",
    )
    config = BacktestConfig(
        system_id=system_id,
        risk_version="risk-v1",
        code_version="96b2288-test",
        execution_assumptions=assumptions or {},
    )
    return BacktestRun.create(dataset=dataset, config=config)


def test_builds_two_deterministic_twins_with_same_market_scope() -> None:
    candidate = _candidate()
    source = _source_run()

    plan = build_recruitment_campaign(
        source,
        candidate,
        role=BacktestPeriodRole.OOS,
        baseline_agents=("berlin", "tokyo", "nairobi"),
    )

    assert len(plan.variants) == 2
    assert plan.baseline.kind is RecruitmentCampaignVariantKind.BASELINE
    assert plan.with_candidate.kind is RecruitmentCampaignVariantKind.WITH_CANDIDATE
    assert plan.baseline.run.dataset == source.dataset
    assert plan.with_candidate.run.dataset == source.dataset
    assert plan.baseline.run.period_start == source.period_start
    assert plan.with_candidate.run.period_end == source.period_end
    assert plan.baseline.run.config.system_id == source.config.system_id
    assert plan.with_candidate.run.config.risk_version == source.config.risk_version
    assert plan.baseline.included_agents == ("berlin", "nairobi", "tokyo")
    assert plan.with_candidate.included_agents == tuple(
        sorted((*plan.baseline_agents, plan.candidate_agent_id))
    )
    assert plan.execute is False
    assert plan.auto_apply is False
    assert plan.registry_mutation is False
    assert plan.live_authority is False


def test_candidate_identity_is_evaluation_only_and_stable() -> None:
    candidate = _candidate()
    assert candidate_runtime_agent_id(candidate) == "candidate:recruitment-19b-001"

    left = build_recruitment_campaign(
        _source_run(),
        candidate,
        role=BacktestPeriodRole.VALIDATION,
        baseline_agents=("tokyo", "berlin"),
    )
    right = build_recruitment_campaign(
        _source_run(),
        candidate,
        role=BacktestPeriodRole.VALIDATION,
        baseline_agents=("berlin", "tokyo"),
    )
    assert left.campaign_id == right.campaign_id
    assert left.comparison_fingerprint == right.comparison_fingerprint
    assert left.success_criteria_fingerprint == right.success_criteria_fingerprint
    assert left.baseline.run.run_id == right.baseline.run.run_id
    assert left.with_candidate.run.run_id == right.with_candidate.run.run_id


def test_role_is_explicit_and_changes_campaign_identity() -> None:
    source = _source_run()
    candidate = _candidate()
    design = build_recruitment_campaign(
        source,
        candidate,
        role=BacktestPeriodRole.DESIGN,
        baseline_agents=("berlin", "tokyo"),
    )
    oos = build_recruitment_campaign(
        source,
        candidate,
        role=BacktestPeriodRole.OOS,
        baseline_agents=("berlin", "tokyo"),
    )
    assert design.campaign_id != oos.campaign_id
    assert design.role is BacktestPeriodRole.DESIGN
    assert oos.role is BacktestPeriodRole.OOS


def test_success_criteria_are_frozen_into_campaign_identity() -> None:
    source = _source_run()
    candidate = _candidate()
    plan = build_recruitment_campaign(
        source,
        candidate,
        role=BacktestPeriodRole.OOS,
        baseline_agents=("berlin", "tokyo"),
    )
    changed = candidate.model_copy(
        update={
            "success_criteria": (
                candidate.success_criteria[0].model_copy(update={"threshold": Decimal("1")}),
                candidate.success_criteria[1],
            )
        }
    )
    changed_plan = build_recruitment_campaign(
        source,
        changed,
        role=BacktestPeriodRole.OOS,
        baseline_agents=("berlin", "tokyo"),
    )
    assert plan.success_criteria_fingerprint != changed_plan.success_criteria_fingerprint
    assert plan.campaign_id != changed_plan.campaign_id


def test_rejects_baseline_system_mismatch() -> None:
    with pytest.raises(ValueError, match="system_id"):
        build_recruitment_campaign(
            _source_run(system_id="other_system"),
            _candidate(),
            role=BacktestPeriodRole.OOS,
            baseline_agents=("berlin", "tokyo"),
        )


def test_rejects_candidate_already_in_baseline() -> None:
    candidate = _candidate()
    with pytest.raises(ValueError, match="candidate runtime id"):
        build_recruitment_campaign(
            _source_run(),
            candidate,
            role=BacktestPeriodRole.OOS,
            baseline_agents=("berlin", candidate_runtime_agent_id(candidate)),
        )


def test_rejects_reserved_execution_assumptions() -> None:
    with pytest.raises(ValueError, match="reserved recruitment"):
        build_recruitment_campaign(
            _source_run(assumptions={"recruitment_campaign_id": "collision"}),
            _candidate(),
            role=BacktestPeriodRole.OOS,
            baseline_agents=("berlin", "tokyo"),
        )


def test_source_run_and_config_are_not_mutated() -> None:
    source = _source_run(assumptions={"operator_note": "frozen"})
    original_payload = source.config.canonical_payload()
    build_recruitment_campaign(
        source,
        _candidate(),
        role=BacktestPeriodRole.OOS,
        baseline_agents=("berlin", "tokyo"),
    )
    assert source.config.canonical_payload() == original_payload
    assert "recruitment_campaign_id" not in source.config.execution_assumptions
