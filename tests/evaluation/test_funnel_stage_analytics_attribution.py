from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.evaluation.analytics_attribution.funnel_stage_attribution import (
    build_funnel_stage_analytics_attribution,
    project_funnel_stage_analytics_records,
)
from app.evaluation.analytics_attribution.funnel_stage_models import FunnelStage

T = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
CURSOR = "a" * 64
LINK_FP = "b" * 64
SNAPSHOT_FP = "c" * 64
DECISION_FP = "d" * 64
SET_FP = "e" * 64
SOURCE_RUN = "backtest-run-24b4"
ANALYTICS_RUN = "analytics-run-24b4"
OPPORTUNITY = "opportunity-24b4"
DECISION_RECORD_ID = "decision-record-24b4"


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


def analytics_ref(*, matched: bool = True, analytics_run_id: str = ANALYTICS_RUN):
    return ns(
        link_id=f"link-{analytics_run_id}",
        link_fingerprint=LINK_FP,
        link_policy_version="opportunity-analytics-exact-v1",
        status="MATCHED" if matched else "MISSING_ANALYTICS_SNAPSHOT",
        analytics_run_id=analytics_run_id,
        analytics_snapshot_id=(f"snapshot-{analytics_run_id}" if matched else None),
        analytics_snapshot_fingerprint=(SNAPSHOT_FP if matched else None),
        analytics_as_of=(T if matched else None),
        source_cursor_fingerprint=CURSOR,
        analytics_snapshot_source_cursor_fingerprint=(CURSOR if matched else None),
        diagnostics=() if matched else ("no exact AnalyticsSnapshot",),
    )


def fixed_projection(*, reached: bool, stage_status: str | None = None, **kwargs):
    return ns(reached=reached, stage_status=stage_status, **kwargs)


def full_record(
    *,
    analytics_run_id: str = ANALYTICS_RUN,
    matched: bool = True,
    record_fingerprint: str = DECISION_FP,
):
    plan_call = ns(request_id="plan-request")
    final_call = ns(request_id="final-request")
    berlin = ns(
        agent_id="berlin",
        request_id="berlin-request",
        prompt_version="berlin-v6",
        route_id="specialist",
        model_id="model-a",
        analysis=ns(agent="berlin", stance="LONG", confidence=0.72),
        call=None,
    )
    tokyo = ns(
        agent_id="tokyo",
        request_id="tokyo-request",
        prompt_version="tokyo-v6",
        route_id="specialist",
        model_id="model-a",
        analysis=ns(agent="tokyo", stance="NEUTRAL", confidence=0.61),
        call=None,
    )
    decision = ns(
        paper_pipeline_status="EXECUTED",
        orchestration_status="TRADE_PROPOSAL",
        orchestration_failure=None,
        paper_pipeline_failure=None,
        orchestration_stages=(
            ns(sequence=1, stage="compute_gate", status="COMPLETED"),
            ns(sequence=2, stage="professor_plan", status="COMPLETED"),
            ns(sequence=3, stage="specialists_independent_round_1", status="STARTED"),
            ns(sequence=4, stage="specialists_independent_round_1", status="COMPLETED"),
            ns(sequence=5, stage="palermo_red_team", status="COMPLETED"),
            ns(sequence=6, stage="professor_finalize", status="COMPLETED"),
            ns(sequence=7, stage="trade_proposal", status="COMPLETED"),
        ),
        paper_pipeline_stages=(
            ns(sequence=1, stage="orchestration", status="COMPLETED"),
            ns(sequence=2, stage="trade_proposal", status="COMPLETED"),
            ns(sequence=3, stage="risk_engine", status="COMPLETED"),
            ns(sequence=4, stage="order_intent", status="COMPLETED"),
            ns(sequence=5, stage="paper_execution", status="COMPLETED"),
        ),
        compute_gate=ns(
            reached=True,
            level="LEVEL_2_MINI_CREW",
            reason="ALLOWED_MINI_CREW",
            priority_score=82,
            remaining_budget_eur="10",
            minimum_required_budget_eur="0.1",
            allows_ai=True,
        ),
        professor_plan=fixed_projection(
            reached=True,
            stage_status="COMPLETED",
            decision="MINI_CREW",
            selected_agents=("berlin", "tokyo"),
            rationale=("Complémentarité",),
            request_more_analysis=False,
            call=plan_call,
        ),
        specialists=fixed_projection(
            reached=True,
            stage_status="COMPLETED",
            selected_agents=("berlin", "tokyo"),
            runs=(berlin, tokyo),
            failure=None,
        ),
        palermo=fixed_projection(
            reached=True,
            stage_status="COMPLETED",
            request_id="palermo-request",
            prompt_version="palermo-v4",
            route_id="palermo",
            model_id="model-a",
            verdict="CAUTION",
            severity=0.5,
            critical_objections=("Faux breakout",),
            missing_checks=(),
            conditions_to_continue=("Stop maintenu",),
            call=None,
        ),
        professor_final=fixed_projection(
            reached=True,
            stage_status="COMPLETED",
            direction="LONG",
            confidence=0.71,
            thesis=("Structure haussière",),
            counter_evidence=(),
            invalidation=("Sous support",),
            evidence=(),
            trade=ns(entry_price="100", stop_price="95", targets=("110",), expected_rr="2"),
            call=final_call,
        ),
        trade_proposal=fixed_projection(
            reached=True,
            stage_status="COMPLETED",
            proposal_id="proposal-24b4",
            side="LONG",
            confidence=0.71,
            created_at=T + timedelta(seconds=2),
        ),
        risk=fixed_projection(
            reached=True,
            stage_status="COMPLETED",
            risk_decision_id="risk-24b4",
            status="RESIZED",
            reason_codes=("RESIZED_QTY_STEP",),
            created_at=T + timedelta(seconds=6),
        ),
        execution=fixed_projection(
            reached=True,
            stage_status="COMPLETED",
            order_intent=ns(client_order_id="client-order-24b4"),
            order=ns(
                broker_order_id="broker-order-24b4",
                client_order_id="client-order-24b4",
                status="FILLED",
                created_at=T + timedelta(seconds=6),
                updated_at=T + timedelta(seconds=7),
            ),
            fill=ns(
                fill_id="fill-24b4",
                broker_order_id="broker-order-24b4",
                filled_at=T + timedelta(seconds=7),
            ),
            position_before=None,
            position_after=ns(system_id="balanced_v1", symbol="BTC/EUR", quantity="0.1"),
            failure=None,
        ),
    )
    return ns(
        record_id=DECISION_RECORD_ID,
        record_fingerprint=record_fingerprint,
        source_backtest_run_id=SOURCE_RUN,
        analytics_run_id=analytics_run_id,
        opportunity_id=OPPORTUNITY,
        opportunity_fingerprint="f" * 64,
        system_id="balanced_v1",
        symbol="BTC/EUR",
        decision_timeframe="1h",
        observed_at=T,
        decision_context=ns(present=True, as_of=T),
        decision=decision,
        analytics=analytics_ref(matched=matched, analytics_run_id=analytics_run_id),
    )


def record_set(record, *, set_fingerprint: str = SET_FP):
    return ns(
        source_backtest_run_id=record.source_backtest_run_id,
        analytics_run_id=record.analytics_run_id,
        record_count=1,
        records=(record,),
        set_fingerprint=set_fingerprint,
    )


def by_stage(records, stage: FunnelStage):
    return tuple(item for item in records if item.stage is stage)


def test_full_path_projects_canonical_stages_and_same_analytics_snapshot() -> None:
    result = build_funnel_stage_analytics_attribution(record_set(full_record()))

    assert result.decision_record_count == 1
    assert result.covered_decision_record_count == 1
    assert result.stage_record_count == 9
    assert [item.stage for item in result.records] == [
        FunnelStage.COMPUTE_GATE,
        FunnelStage.PROFESSOR_PLAN,
        FunnelStage.SPECIALIST,
        FunnelStage.SPECIALIST,
        FunnelStage.PALERMO,
        FunnelStage.PROFESSOR_FINAL,
        FunnelStage.TRADE_PROPOSAL,
        FunnelStage.RISK,
        FunnelStage.PAPER,
    ]
    specialists = by_stage(result.records, FunnelStage.SPECIALIST)
    assert [item.stage_instance_id for item in specialists] == ["berlin", "tokyo"]
    assert specialists[0].agent_request_id == "berlin-request"
    assert specialists[0].agent_prompt_version == "berlin-v6"
    assert specialists[0].agent_route_id == "specialist"
    assert specialists[0].agent_model_id == "model-a"
    assert {item.analytics_snapshot_id for item in result.records} == {f"snapshot-{ANALYTICS_RUN}"}
    assert {item.market_as_of for item in result.records} == {T}


def test_operational_time_never_changes_market_or_analytics_as_of() -> None:
    result = build_funnel_stage_analytics_attribution(record_set(full_record()))
    proposal = by_stage(result.records, FunnelStage.TRADE_PROPOSAL)[0]
    risk = by_stage(result.records, FunnelStage.RISK)[0]
    paper = by_stage(result.records, FunnelStage.PAPER)[0]

    assert proposal.operational_at == T + timedelta(seconds=2)
    assert risk.operational_at == T + timedelta(seconds=6)
    assert paper.operational_at == T + timedelta(seconds=7)
    for item in (proposal, risk, paper):
        assert item.market_as_of == T
        assert item.analytics_as_of == T
        assert item.analytics_snapshot_id == f"snapshot-{ANALYTICS_RUN}"


def test_compute_gate_stop_materializes_fixed_not_reached_stages() -> None:
    source = full_record()
    source.decision.compute_gate = ns(
        reached=True,
        level="SKIP_AI",
        reason="PRIORITY_TOO_LOW",
        priority_score=20,
        remaining_budget_eur="10",
        minimum_required_budget_eur="0.1",
        allows_ai=False,
    )
    source.decision.orchestration_stages = (
        ns(sequence=1, stage="compute_gate", status="SKIPPED"),
    )
    source.decision.professor_plan = fixed_projection(
        reached=False,
        stage_status=None,
        decision=None,
        selected_agents=(),
        rationale=(),
        request_more_analysis=None,
        call=None,
    )
    source.decision.specialists = fixed_projection(
        reached=False,
        stage_status=None,
        selected_agents=(),
        runs=(),
        failure=None,
    )
    source.decision.palermo = fixed_projection(
        reached=False, stage_status=None, request_id=None, verdict=None, severity=None
    )
    source.decision.professor_final = fixed_projection(
        reached=False, stage_status=None, direction=None, confidence=None, call=None
    )
    source.decision.trade_proposal = fixed_projection(
        reached=False,
        stage_status=None,
        proposal_id=None,
        side=None,
        confidence=None,
        created_at=None,
    )
    source.decision.risk = fixed_projection(
        reached=False,
        stage_status=None,
        risk_decision_id=None,
        status=None,
        reason_codes=(),
        created_at=None,
    )
    source.decision.execution = fixed_projection(
        reached=False,
        stage_status=None,
        order_intent=None,
        order=None,
        fill=None,
        position_before=None,
        position_after=None,
        failure=None,
    )
    source.decision.paper_pipeline_status = "NO_ANALYSIS"

    records = project_funnel_stage_analytics_records(source)
    assert len(records) == 7
    gate = by_stage(records, FunnelStage.COMPUTE_GATE)[0]
    assert gate.reached is True
    assert gate.stage_status == "SKIPPED"
    assert gate.stage_result == "SKIP_AI"
    for stage in (
        FunnelStage.PROFESSOR_PLAN,
        FunnelStage.PALERMO,
        FunnelStage.PROFESSOR_FINAL,
        FunnelStage.TRADE_PROPOSAL,
        FunnelStage.RISK,
        FunnelStage.PAPER,
    ):
        assert by_stage(records, stage)[0].reached is False


def test_professor_plan_no_analysis_stops_later_stages_without_fabrication() -> None:
    source = full_record()
    source.decision.paper_pipeline_status = "NO_ANALYSIS"
    source.decision.orchestration_status = "NO_ANALYSIS"
    source.decision.orchestration_stages = (
        ns(sequence=1, stage="compute_gate", status="COMPLETED"),
        ns(sequence=2, stage="professor_plan", status="COMPLETED"),
        ns(sequence=3, stage="specialists", status="SKIPPED"),
    )
    source.decision.paper_pipeline_stages = (
        ns(sequence=1, stage="orchestration", status="COMPLETED"),
    )
    source.decision.professor_plan = fixed_projection(
        reached=True,
        stage_status="COMPLETED",
        decision="NO_ANALYSIS",
        selected_agents=(),
        rationale=("Analyse supplémentaire non justifiée",),
        request_more_analysis=False,
        call=ns(request_id="plan-request"),
    )
    source.decision.specialists = fixed_projection(
        reached=False,
        stage_status="SKIPPED",
        selected_agents=(),
        runs=(),
        failure=None,
    )
    source.decision.palermo = fixed_projection(
        reached=False, stage_status=None, request_id=None, verdict=None, severity=None
    )
    source.decision.professor_final = fixed_projection(
        reached=False, stage_status=None, direction=None, confidence=None, call=None
    )
    source.decision.trade_proposal = fixed_projection(
        reached=False,
        stage_status=None,
        proposal_id=None,
        side=None,
        confidence=None,
        created_at=None,
    )
    source.decision.risk = fixed_projection(
        reached=False,
        stage_status=None,
        risk_decision_id=None,
        status=None,
        reason_codes=(),
        created_at=None,
    )
    source.decision.execution = fixed_projection(
        reached=False,
        stage_status=None,
        order_intent=None,
        order=None,
        fill=None,
        position_before=None,
        position_after=None,
        failure=None,
    )

    records = project_funnel_stage_analytics_records(source)
    assert len(records) == 7
    plan = by_stage(records, FunnelStage.PROFESSOR_PLAN)[0]
    assert plan.reached is True
    assert plan.stage_result == "NO_ANALYSIS"
    assert not by_stage(records, FunnelStage.SPECIALIST)
    for stage in (
        FunnelStage.PALERMO,
        FunnelStage.PROFESSOR_FINAL,
        FunnelStage.TRADE_PROPOSAL,
        FunnelStage.RISK,
        FunnelStage.PAPER,
    ):
        assert by_stage(records, stage)[0].reached is False


def test_professor_plan_technical_failure_is_not_not_reached() -> None:
    source = full_record()
    failure = ns(
        code="AI_PROVIDER_ERROR",
        stage="professor_plan",
        message="provider failure",
        agent_id="professor",
    )
    source.decision.paper_pipeline_status = "FAILED"
    source.decision.orchestration_status = "FAILED"
    source.decision.orchestration_failure = failure
    source.decision.orchestration_stages = (
        ns(sequence=1, stage="compute_gate", status="COMPLETED"),
        ns(sequence=2, stage="professor_plan", status="FAILED"),
    )
    source.decision.professor_plan = fixed_projection(
        reached=True,
        stage_status="FAILED",
        decision=None,
        selected_agents=(),
        rationale=(),
        request_more_analysis=None,
        call=None,
    )
    source.decision.specialists = fixed_projection(
        reached=False,
        stage_status=None,
        selected_agents=(),
        runs=(),
        failure=None,
    )
    source.decision.palermo = fixed_projection(
        reached=False, stage_status=None, request_id=None, verdict=None, severity=None
    )
    source.decision.professor_final = fixed_projection(
        reached=False, stage_status=None, direction=None, confidence=None, call=None
    )
    source.decision.trade_proposal = fixed_projection(
        reached=False,
        stage_status=None,
        proposal_id=None,
        side=None,
        confidence=None,
        created_at=None,
    )
    source.decision.risk = fixed_projection(
        reached=False,
        stage_status=None,
        risk_decision_id=None,
        status=None,
        reason_codes=(),
        created_at=None,
    )
    source.decision.execution = fixed_projection(
        reached=False,
        stage_status=None,
        order_intent=None,
        order=None,
        fill=None,
        position_before=None,
        position_after=None,
        failure=None,
    )

    records = project_funnel_stage_analytics_records(source)
    plan = by_stage(records, FunnelStage.PROFESSOR_PLAN)[0]
    assert plan.reached is True
    assert plan.stage_status == "FAILED"
    assert plan.failure_code == "AI_PROVIDER_ERROR"
    assert plan.failure_agent_id == "professor"
    assert by_stage(records, FunnelStage.PALERMO)[0].reached is False


def test_professor_final_short_is_preserved() -> None:
    source = full_record()
    source.decision.professor_final.direction = "SHORT"
    source.decision.trade_proposal.side = "SHORT"

    records = project_funnel_stage_analytics_records(source)
    assert by_stage(records, FunnelStage.PROFESSOR_FINAL)[0].stage_result == "SHORT"
    assert by_stage(records, FunnelStage.TRADE_PROPOSAL)[0].stage_result == "SHORT"


def test_selected_specialist_failure_is_distinct_from_unselected_agents() -> None:
    source = full_record()
    berlin = source.decision.specialists.runs[0]
    failure = ns(
        code="AI_PROVIDER_ERROR",
        stage="specialist_independent_round_1",
        message="provider failure",
        agent_id="tokyo",
    )
    source.decision.specialists = fixed_projection(
        reached=True,
        stage_status="FAILED",
        selected_agents=("berlin", "tokyo"),
        runs=(berlin,),
        failure=failure,
    )
    source.decision.orchestration_failure = failure

    specialists = by_stage(
        project_funnel_stage_analytics_records(source), FunnelStage.SPECIALIST
    )
    assert [item.stage_instance_id for item in specialists] == ["berlin", "tokyo"]
    assert specialists[0].stage_status == "COMPLETED"
    assert specialists[0].stage_result == "LONG"
    assert specialists[1].stage_status == "FAILED"
    assert specialists[1].failure_code == "AI_PROVIDER_ERROR"
    assert "nairobi" not in {item.stage_instance_id for item in specialists}


@pytest.mark.parametrize("verdict", ["CLEAR", "CAUTION", "REJECT"])
def test_palermo_verdict_is_preserved_without_scoring(verdict: str) -> None:
    source = full_record()
    source.decision.palermo.verdict = verdict
    record = by_stage(
        project_funnel_stage_analytics_records(source), FunnelStage.PALERMO
    )[0]
    assert record.stage_result == verdict
    assert record.severity == 0.5


def test_final_no_trade_keeps_risk_and_paper_not_reached() -> None:
    source = full_record()
    source.decision.professor_final.direction = "NO_TRADE"
    source.decision.trade_proposal = fixed_projection(
        reached=False,
        stage_status="SKIPPED",
        proposal_id=None,
        side=None,
        confidence=None,
        created_at=None,
    )
    source.decision.risk = fixed_projection(
        reached=False,
        stage_status=None,
        risk_decision_id=None,
        status=None,
        reason_codes=(),
        created_at=None,
    )
    source.decision.execution = fixed_projection(
        reached=False,
        stage_status=None,
        order_intent=None,
        order=None,
        fill=None,
        position_before=None,
        position_after=None,
        failure=None,
    )
    source.decision.paper_pipeline_status = "NO_TRADE"

    records = project_funnel_stage_analytics_records(source)
    assert by_stage(records, FunnelStage.PROFESSOR_FINAL)[0].stage_result == "NO_TRADE"
    assert by_stage(records, FunnelStage.RISK)[0].reached is False
    assert by_stage(records, FunnelStage.PAPER)[0].reached is False


@pytest.mark.parametrize("risk_status", ["APPROVED", "RESIZED"])
def test_risk_authorized_results_are_preserved(risk_status: str) -> None:
    source = full_record()
    source.decision.risk.status = risk_status
    record = by_stage(project_funnel_stage_analytics_records(source), FunnelStage.RISK)[0]
    assert record.reached is True
    assert record.stage_result == risk_status


def test_risk_rejected_does_not_fabricate_paper_execution() -> None:
    source = full_record()
    source.decision.risk.status = "REJECTED"
    source.decision.risk.reason_codes = ("MIN_EXPECTED_RR",)
    source.decision.execution = fixed_projection(
        reached=False,
        stage_status=None,
        order_intent=None,
        order=None,
        fill=None,
        position_before=None,
        position_after=None,
        failure=None,
    )
    source.decision.paper_pipeline_status = "RISK_REJECTED"

    records = project_funnel_stage_analytics_records(source)
    risk = by_stage(records, FunnelStage.RISK)[0]
    paper = by_stage(records, FunnelStage.PAPER)[0]
    assert risk.stage_result == "REJECTED"
    assert risk.reason_codes == ("MIN_EXPECTED_RR",)
    assert paper.reached is False


def test_paper_failure_remains_execution_failure_not_risk_rejection() -> None:
    source = full_record()
    failure = ns(
        code="BROKER_EXECUTION_FAILED",
        stage="paper_broker",
        message="broker failed",
        agent_id=None,
    )
    source.decision.execution = fixed_projection(
        reached=True,
        stage_status="FAILED",
        order_intent=ns(client_order_id="client-order-24b4"),
        order=None,
        fill=None,
        position_before=None,
        position_after=None,
        failure=failure,
    )
    source.decision.paper_pipeline_status = "FAILED"
    source.decision.paper_pipeline_failure = failure

    paper = by_stage(
        project_funnel_stage_analytics_records(source), FunnelStage.PAPER
    )[0]
    assert paper.reached is True
    assert paper.stage_result == "BROKER_EXECUTION_FAILED"
    assert paper.failure_code == "BROKER_EXECUTION_FAILED"
    assert paper.stage_result != "REJECTED"


def test_unmatched_analytics_is_propagated_to_every_stage_without_rematching() -> None:
    source = full_record(matched=False)
    records = project_funnel_stage_analytics_records(source)
    assert records
    assert {item.analytics_link_status for item in records} == {
        "MISSING_ANALYTICS_SNAPSHOT"
    }
    assert {item.analytics_snapshot_id for item in records} == {None}
    assert all(item.analytics_diagnostics == ("no exact AnalyticsSnapshot",) for item in records)


def test_same_inputs_are_deterministic() -> None:
    source = full_record()
    first = build_funnel_stage_analytics_attribution(record_set(source))
    second = build_funnel_stage_analytics_attribution(record_set(deepcopy(source)))

    assert first.set_fingerprint == second.set_fingerprint
    assert [item.record_id for item in first.records] == [item.record_id for item in second.records]
    assert [item.record_fingerprint for item in first.records] == [
        item.record_fingerprint for item in second.records
    ]


def test_material_palermo_change_only_changes_palermo_stage_fingerprint() -> None:
    baseline = full_record()
    changed = deepcopy(baseline)
    changed.record_fingerprint = "1" * 64
    changed.decision.palermo.verdict = "REJECT"

    before = project_funnel_stage_analytics_records(baseline)
    after = project_funnel_stage_analytics_records(changed)
    before_by_id = {item.record_id: item for item in before}
    after_by_id = {item.record_id: item for item in after}
    assert before_by_id.keys() == after_by_id.keys()

    changed_ids = {
        record_id
        for record_id in before_by_id
        if before_by_id[record_id].record_fingerprint
        != after_by_id[record_id].record_fingerprint
    }
    assert len(changed_ids) == 1
    only = after_by_id[changed_ids.pop()]
    assert only.stage is FunnelStage.PALERMO


def test_analytics_reference_change_changes_stage_attribution_not_source_projection() -> None:
    first_source = full_record()
    second_source = deepcopy(first_source)
    second_source.analytics_run_id = "analytics-run-24b4-v2"
    second_source.analytics = analytics_ref(
        matched=True, analytics_run_id="analytics-run-24b4-v2"
    )

    first = project_funnel_stage_analytics_records(first_source)
    second = project_funnel_stage_analytics_records(second_source)
    assert [item.source_projection_fingerprint for item in first] == [
        item.source_projection_fingerprint for item in second
    ]
    assert all(
        left.record_fingerprint != right.record_fingerprint
        for left, right in zip(first, second, strict=True)
    )
    assert first_source.source_backtest_run_id == second_source.source_backtest_run_id


def test_cross_run_contamination_is_rejected() -> None:
    source = full_record()
    source_set = record_set(source)
    source.source_backtest_run_id = "other-backtest-run"
    with pytest.raises(ValueError, match="BacktestRun mismatch"):
        build_funnel_stage_analytics_attribution(source_set)


def test_duplicate_specialist_runs_are_rejected() -> None:
    source = full_record()
    berlin = source.decision.specialists.runs[0]
    source.decision.specialists.runs = (berlin, berlin)
    with pytest.raises(ValueError, match="duplicate run agent"):
        project_funnel_stage_analytics_records(source)


def test_projection_does_not_mutate_decision_record_identity_or_fingerprint() -> None:
    source = full_record()
    before = (
        source.source_backtest_run_id,
        source.record_id,
        source.record_fingerprint,
        source.opportunity_id,
    )
    build_funnel_stage_analytics_attribution(record_set(source))
    after = (
        source.source_backtest_run_id,
        source.record_id,
        source.record_fingerprint,
        source.opportunity_id,
    )
    assert after == before


def test_duplicate_specialist_request_ids_are_rejected() -> None:
    source = full_record()
    berlin, tokyo = source.decision.specialists.runs
    tokyo.request_id = berlin.request_id
    with pytest.raises(ValueError, match="duplicate request_id"):
        project_funnel_stage_analytics_records(source)
