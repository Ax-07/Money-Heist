from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.evaluation.analytics_attribution.models import (
    OpportunityAnalyticsLink,
    OpportunityAnalyticsLinkSet,
)

from .models import (
    AgentCallProjection,
    AnalyticsRefProjection,
    BerlinAnalysisProjection,
    BrokerOrderProjection,
    ComputeGateProjection,
    DecisionContextRef,
    DecisionIntelligenceRecord,
    DecisionIntelligenceRecordSet,
    DecisionProjection,
    DenverAnalysisProjection,
    EvidenceProjection,
    ExecutionProjection,
    FailureProjection,
    FillProjection,
    NairobiAnalysisProjection,
    OrderIntentProjection,
    PalermoProjection,
    PositionProjection,
    ProfessorFinalProjection,
    ProfessorPlanProjection,
    ProfessorTradeProjection,
    RioAnalysisProjection,
    RiskDetail,
    RiskInputProjection,
    RiskProjection,
    ScannerProjection,
    SpecialistAnalysisProjection,
    SpecialistRunProjection,
    SpecialistsProjection,
    StageTrace,
    TokyoAnalysisProjection,
    TradeProposalProjection,
)


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return str(_value(value))


def _texts(values: Iterable[Any] | None) -> tuple[str, ...]:
    return tuple(str(_value(item)) for item in (values or ()))


def _failure(value: Any | None) -> FailureProjection | None:
    if value is None:
        return None
    return FailureProjection(
        code=_text(getattr(value, "code", None)) or "UNKNOWN",
        stage=str(getattr(value, "stage", "unknown")),
        message=str(getattr(value, "message", "unknown failure")),
        agent_id=(
            str(value.agent_id)
            if getattr(value, "agent_id", None) is not None
            else None
        ),
    )


def _evidence(values: Iterable[Any] | None) -> tuple[EvidenceProjection, ...]:
    return tuple(
        EvidenceProjection(
            source_key=str(item.source_key),
            observation=str(item.observation),
        )
        for item in (values or ())
    )


def _call(value: Any | None) -> AgentCallProjection | None:
    if value is None:
        return None
    return AgentCallProjection(
        request_id=str(value.request_id),
        agent_id=str(value.agent_id),
        phase=str(value.phase),
        prompt_version=str(value.prompt_version),
        route_id=str(value.route_id),
        model_id=str(value.model_id),
        estimated_cost_eur=value.estimated_cost_eur,
        attempts=value.attempts,
    )


def _calls_by_request(orchestration: Any | None) -> dict[str, Any]:
    if orchestration is None:
        return {}
    result: dict[str, Any] = {}
    for item in getattr(orchestration, "agent_calls", ()) or ():
        request_id = str(item.request_id)
        if request_id in result:
            raise ValueError("orchestration contains duplicate agent call request_id")
        result[request_id] = item
    return result


def _call_by_phase(orchestration: Any | None, phase: str) -> Any | None:
    if orchestration is None:
        return None
    matches = tuple(
        item
        for item in (getattr(orchestration, "agent_calls", ()) or ())
        if str(getattr(item, "phase", "")) == phase
    )
    if len(matches) > 1:
        raise ValueError(f"orchestration contains multiple agent calls for phase {phase}")
    return matches[0] if matches else None


def _stage_traces(events: Iterable[Any] | None) -> tuple[StageTrace, ...]:
    traces = tuple(
        StageTrace(
            sequence=int(item.sequence),
            stage=str(item.stage),
            status=str(_value(item.status)),
        )
        for item in (events or ())
    )
    sequences = tuple(item.sequence for item in traces)
    if len(set(sequences)) != len(sequences):
        raise ValueError("stage trace sequence numbers must be unique")
    if sequences != tuple(sorted(sequences)):
        raise ValueError("stage traces must preserve source sequence order")
    return traces


def _stage_status(traces: tuple[StageTrace, ...], *stage_names: str) -> str | None:
    names = set(stage_names)
    matches = tuple(item.status for item in traces if item.stage in names)
    return matches[-1] if matches else None


def _stage_attempted(status: str | None) -> bool:
    return status in {"STARTED", "COMPLETED", "FAILED"}


def _project_scanner(point: Any, opportunity: Any) -> ScannerProjection:
    scan_result = getattr(point, "scan_result", None)
    if scan_result is None:
        raise ValueError("CandidateOpportunity replay point requires ScanResult")
    feature = point.feature_snapshot
    return ScannerProjection(
        snapshot_id=str(opportunity.snapshot_id),
        feature_version=str(feature.feature_version),
        scanner_version=str(opportunity.scanner_version),
        market_regime=_text(getattr(feature, "regime", None)),
        score=int(scan_result.score),
        priority_score=int(opportunity.priority_score),
        triggers=_texts(opportunity.triggers),
        observed_at=opportunity.created_at,
        expires_at=opportunity.expires_at,
    )


def _project_context(point: Any) -> DecisionContextRef:
    context = getattr(point, "decision_context", None)
    if context is None:
        return DecisionContextRef(present=False)
    market = getattr(context, "market", None)
    cursor = getattr(market, "source_cursor_fingerprint", None)
    if cursor is None:
        raise ValueError("DecisionContext is missing source_cursor_fingerprint")
    return DecisionContextRef(
        present=True,
        context_id=str(context.context_id),
        context_fingerprint=str(context.context_fingerprint),
        schema_version=str(context.schema_version),
        context_version=str(context.context_version),
        system_id=str(context.system_id),
        symbol=str(context.symbol),
        as_of=context.as_of,
        primary_timeframe=str(context.primary_timeframe),
        timeframe_policy_version=str(context.timeframe_policy_version),
        source_cursor_fingerprint=str(cursor),
    )


def _project_compute_gate(orchestration: Any | None) -> ComputeGateProjection:
    gate = getattr(orchestration, "compute_gate", None) if orchestration is not None else None
    if gate is None:
        return ComputeGateProjection(reached=False)
    return ComputeGateProjection(
        reached=True,
        level=_text(gate.level),
        reason=_text(gate.reason),
        priority_score=gate.priority_score,
        remaining_budget_eur=gate.remaining_budget_eur,
        minimum_required_budget_eur=gate.minimum_required_budget_eur,
        allows_ai=bool(gate.allows_ai),
    )


def _project_plan(
    orchestration: Any | None,
    traces: tuple[StageTrace, ...],
) -> ProfessorPlanProjection:
    if orchestration is None:
        return ProfessorPlanProjection(reached=False)
    plan = getattr(orchestration, "professor_plan", None)
    status = _stage_status(traces, "professor_plan")
    reached = plan is not None or _stage_attempted(status)
    if plan is None:
        return ProfessorPlanProjection(reached=reached, stage_status=status)
    return ProfessorPlanProjection(
        reached=True,
        stage_status=status,
        decision=str(plan.decision),
        selected_agents=tuple(str(item) for item in plan.selected_agents),
        rationale=tuple(str(item) for item in plan.rationale),
        request_more_analysis=bool(plan.request_more_analysis),
        call=_call(_call_by_phase(orchestration, "professor_plan")),
    )


def _project_specialist_analysis(analysis: Any) -> SpecialistAnalysisProjection:
    common = {
        "agent": str(analysis.agent),
        "stance": _text(analysis.stance),
        "confidence": analysis.confidence,
        "evidence": _evidence(analysis.evidence),
        "risks": tuple(str(item) for item in analysis.risks),
        "invalidation": tuple(str(item) for item in analysis.invalidation),
        "data_gaps": tuple(str(item) for item in analysis.data_gaps),
    }
    agent = str(analysis.agent)
    if agent == "berlin":
        return BerlinAnalysisProjection(
            **common,
            regime=_text(analysis.regime),
            trend_maturity=_text(analysis.trend_maturity),
            multi_timeframe_alignment=_text(analysis.multi_timeframe_alignment),
        )
    if agent == "tokyo":
        return TokyoAnalysisProjection(
            **common,
            momentum=_text(analysis.momentum),
            momentum_quality=_text(analysis.momentum_quality),
            breakout_quality=_text(analysis.breakout_quality),
        )
    if agent == "nairobi":
        return NairobiAnalysisProjection(
            **common,
            market_structure=_text(analysis.market_structure),
            liquidity_state=_text(analysis.liquidity_state),
            breakout_state=_text(analysis.breakout_state),
        )
    if agent == "rio":
        return RioAnalysisProjection(
            **common,
            positioning_regime=_text(analysis.positioning_regime),
            funding_state=_text(analysis.funding_state),
            open_interest_state=_text(analysis.open_interest_state),
            liquidation_state=_text(analysis.liquidation_state),
            squeeze_risk=_text(analysis.squeeze_risk),
            data_quality=_text(analysis.data_quality),
        )
    if agent == "denver":
        return DenverAnalysisProjection(
            **common,
            source_stats_id=str(analysis.source_stats_id),
            historical_edge=_text(analysis.historical_edge),
            sample_size_band=_text(analysis.sample_size_band),
            robustness=_text(analysis.robustness),
            oos_consistency=_text(analysis.oos_consistency),
        )
    raise ValueError(f"unsupported specialist analysis agent: {agent}")


def _project_specialists(
    orchestration: Any | None,
    traces: tuple[StageTrace, ...],
) -> SpecialistsProjection:
    if orchestration is None:
        return SpecialistsProjection(reached=False)
    plan = getattr(orchestration, "professor_plan", None)
    selected = tuple(str(item) for item in getattr(plan, "selected_agents", ()) or ())
    status = _stage_status(traces, "specialists_independent_round_1", "specialists")
    source_runs = tuple(getattr(orchestration, "specialist_runs", ()) or ())
    failure = getattr(orchestration, "failure", None)
    specialist_failure = (
        failure is not None and str(getattr(failure, "stage", "")).startswith("specialist")
    )
    reached = bool(source_runs) or specialist_failure or _stage_attempted(status)
    calls = _calls_by_request(orchestration)
    runs = tuple(
        SpecialistRunProjection(
            agent_id=str(run.agent_id),
            request_id=str(run.request_id),
            prompt_version=str(run.prompt_version),
            route_id=str(run.route_id),
            model_id=str(run.model_id),
            analysis=_project_specialist_analysis(run.analysis),
            call=_call(calls.get(str(run.request_id))),
        )
        for run in source_runs
    )
    failure_projection = _failure(failure) if specialist_failure else None
    return SpecialistsProjection(
        reached=reached,
        stage_status=status,
        selected_agents=selected if reached else (),
        runs=runs if reached else (),
        failure=failure_projection if reached else None,
    )


def _project_palermo(
    orchestration: Any | None,
    traces: tuple[StageTrace, ...],
) -> PalermoProjection:
    if orchestration is None:
        return PalermoProjection(reached=False)
    run = getattr(orchestration, "palermo_run", None)
    status = _stage_status(traces, "palermo_red_team")
    reached = run is not None or _stage_attempted(status)
    if run is None:
        return PalermoProjection(reached=reached, stage_status=status)
    review = run.review
    calls = _calls_by_request(orchestration)
    return PalermoProjection(
        reached=True,
        stage_status=status,
        request_id=str(run.request_id),
        prompt_version=str(run.prompt_version),
        route_id=str(run.route_id),
        model_id=str(run.model_id),
        verdict=str(review.verdict),
        severity=review.severity,
        critical_objections=tuple(str(item) for item in review.critical_objections),
        missing_checks=tuple(str(item) for item in review.missing_checks),
        conditions_to_continue=tuple(str(item) for item in review.conditions_to_continue),
        call=_call(calls.get(str(run.request_id))),
    )


def _project_professor_trade(value: Any | None) -> ProfessorTradeProjection | None:
    if value is None:
        return None
    return ProfessorTradeProjection(
        entry_price=value.entry_price,
        stop_price=value.stop_price,
        targets=tuple(value.targets),
        expected_rr=value.expected_rr,
    )


def _project_final(
    orchestration: Any | None,
    traces: tuple[StageTrace, ...],
) -> ProfessorFinalProjection:
    if orchestration is None:
        return ProfessorFinalProjection(reached=False)
    decision = getattr(orchestration, "professor_decision", None)
    status = _stage_status(traces, "professor_finalize")
    reached = decision is not None or _stage_attempted(status)
    if decision is None:
        return ProfessorFinalProjection(reached=reached, stage_status=status)
    call = _call_by_phase(orchestration, "professor_finalize")
    return ProfessorFinalProjection(
        reached=True,
        stage_status=status,
        direction=str(decision.direction),
        confidence=decision.confidence,
        thesis=tuple(str(item) for item in decision.thesis),
        counter_evidence=tuple(str(item) for item in decision.counter_evidence),
        invalidation=tuple(str(item) for item in decision.invalidation),
        evidence=_evidence(decision.evidence),
        trade=_project_professor_trade(decision.trade),
        call=_call(call),
    )


def _project_trade_proposal(
    orchestration: Any | None,
    traces: tuple[StageTrace, ...],
) -> TradeProposalProjection:
    if orchestration is None:
        return TradeProposalProjection(reached=False)
    proposal = getattr(orchestration, "trade_proposal", None)
    status = _stage_status(traces, "trade_proposal")
    if proposal is None:
        return TradeProposalProjection(reached=False, stage_status=status)
    return TradeProposalProjection(
        reached=True,
        stage_status=status,
        proposal_id=str(proposal.proposal_id),
        side=str(proposal.side),
        confidence=proposal.confidence,
        entry_price=proposal.entry_price,
        stop_price=proposal.stop_price,
        targets=tuple(proposal.targets),
        expected_rr=proposal.expected_rr,
        market_regime=str(proposal.market_regime),
        feature_version=str(proposal.feature_version),
        professor_prompt_version=str(proposal.professor_prompt_version),
        professor_request_id=str(proposal.professor_request_id),
        specialist_request_ids=tuple(str(item) for item in proposal.specialist_request_ids),
        palermo_request_id=str(proposal.palermo_request_id),
        thesis=tuple(str(item) for item in proposal.thesis),
        counter_evidence=tuple(str(item) for item in proposal.counter_evidence),
        invalidation=tuple(str(item) for item in proposal.invalidation),
        evidence=_evidence(proposal.evidence),
        created_at=proposal.created_at,
        expires_at=proposal.expires_at,
    )


def _project_risk_input(value: Any | None) -> RiskInputProjection | None:
    if value is None:
        return None
    return RiskInputProjection(
        proposal_id=str(value.proposal_id),
        system_id=str(value.system_id),
        symbol=str(value.symbol),
        side=_text(value.side),
        entry_price=value.entry_price,
        stop_price=value.stop_price,
        expected_rr=value.expected_rr,
        expires_at=value.expires_at,
        requested_leverage=value.requested_leverage,
    )


def _project_risk(
    pipeline_result: Any | None,
    traces: tuple[StageTrace, ...],
) -> RiskProjection:
    if pipeline_result is None:
        return RiskProjection(reached=False)
    record = getattr(pipeline_result, "risk_record", None)
    if record is None:
        return RiskProjection(
            reached=False,
            stage_status=_stage_status(traces, "risk_engine"),
        )
    decision = record.decision
    details = tuple(
        RiskDetail(key=str(key), value=str(decision.details[key]))
        for key in sorted(decision.details)
    )
    return RiskProjection(
        reached=True,
        stage_status=_stage_status(traces, "risk_engine"),
        risk_input=_project_risk_input(getattr(pipeline_result, "risk_input", None)),
        risk_decision_id=str(record.risk_decision_id),
        status=_text(decision.status),
        reason_codes=_texts(decision.reason_codes),
        approved_quantity=decision.approved_quantity,
        approved_risk_amount=decision.approved_risk_amount,
        approved_notional=decision.approved_notional,
        created_at=decision.created_at,
        details=details,
    )


def _project_order_intent(value: Any | None) -> OrderIntentProjection | None:
    if value is None:
        return None
    return OrderIntentProjection(
        risk_decision_id=str(value.risk_decision_id),
        system_id=str(value.system_id),
        symbol=str(value.symbol),
        side=_text(value.side),
        quantity=value.quantity,
        client_order_id=str(value.client_order_id),
        mode=str(value.mode),
        order_type=_text(value.order_type),
    )


def _project_order(value: Any | None) -> BrokerOrderProjection | None:
    if value is None:
        return None
    return BrokerOrderProjection(
        broker_order_id=str(value.broker_order_id),
        client_order_id=str(value.client_order_id),
        system_id=str(value.system_id),
        symbol=str(value.symbol),
        side=_text(value.side),
        order_type=_text(value.order_type),
        requested_quantity=value.requested_quantity,
        filled_quantity=value.filled_quantity,
        status=_text(value.status),
        created_at=value.created_at,
        updated_at=value.updated_at,
        limit_price=value.limit_price,
        average_fill_price=value.average_fill_price,
        reject_reason=value.reject_reason,
        trigger=value.trigger,
    )


def _project_fill(value: Any | None) -> FillProjection | None:
    if value is None:
        return None
    return FillProjection(
        fill_id=str(value.fill_id),
        broker_order_id=str(value.broker_order_id),
        price=value.price,
        quantity=value.quantity,
        fee=value.fee,
        fee_rate_bps=value.fee_rate_bps,
        liquidity=_text(value.liquidity),
        filled_at=value.filled_at,
    )


def _project_position(value: Any | None) -> PositionProjection | None:
    if value is None:
        return None
    return PositionProjection(
        system_id=str(value.system_id),
        symbol=str(value.symbol),
        side=_text(value.side),
        signed_quantity=value.signed_quantity,
        quantity=value.quantity,
        average_entry=value.average_entry,
    )


def _project_execution(
    pipeline_result: Any | None,
    traces: tuple[StageTrace, ...],
) -> ExecutionProjection:
    if pipeline_result is None:
        return ExecutionProjection(reached=False)
    intent = getattr(pipeline_result, "order_intent", None)
    order = getattr(pipeline_result, "order", None)
    fill = getattr(pipeline_result, "fill", None)
    position_before = getattr(pipeline_result, "position_before", None)
    position_after = getattr(pipeline_result, "position_after", None)
    reached = any(item is not None for item in (intent, order, fill, position_after))
    status = _stage_status(traces, "paper_execution")
    if reached and status is None:
        status = _text(getattr(pipeline_result, "status", None))
    pipeline_failure = getattr(pipeline_result, "failure", None)
    execution_failure = None
    if reached and pipeline_failure is not None:
        execution_failure = _failure(pipeline_failure)
    return ExecutionProjection(
        reached=reached,
        stage_status=status,
        order_intent=_project_order_intent(intent) if reached else None,
        order=_project_order(order) if reached else None,
        fill=_project_fill(fill) if reached else None,
        position_before=_project_position(position_before) if reached else None,
        position_after=_project_position(position_after) if reached else None,
        failure=execution_failure,
    )


def _project_decision(point: Any) -> DecisionProjection:
    pipeline_result = getattr(point, "pipeline_result", None)
    if pipeline_result is None:
        return DecisionProjection(
            pipeline_result_present=False,
            compute_gate=ComputeGateProjection(reached=False),
            professor_plan=ProfessorPlanProjection(reached=False),
            specialists=SpecialistsProjection(reached=False),
            palermo=PalermoProjection(reached=False),
            professor_final=ProfessorFinalProjection(reached=False),
            trade_proposal=TradeProposalProjection(reached=False),
            risk=RiskProjection(reached=False),
            execution=ExecutionProjection(reached=False),
        )

    orchestration = getattr(pipeline_result, "orchestration_result", None)
    orchestration_traces = _stage_traces(
        getattr(orchestration, "audit_events", ()) if orchestration is not None else ()
    )
    paper_traces = _stage_traces(getattr(pipeline_result, "audit_events", ()))
    return DecisionProjection(
        pipeline_result_present=True,
        paper_pipeline_status=_text(getattr(pipeline_result, "status", None)),
        orchestration_status=_text(getattr(orchestration, "status", None)),
        orchestration_failure=_failure(getattr(orchestration, "failure", None)),
        paper_pipeline_failure=_failure(getattr(pipeline_result, "failure", None)),
        orchestration_stages=orchestration_traces,
        paper_pipeline_stages=paper_traces,
        compute_gate=_project_compute_gate(orchestration),
        professor_plan=_project_plan(orchestration, orchestration_traces),
        specialists=_project_specialists(orchestration, orchestration_traces),
        palermo=_project_palermo(orchestration, orchestration_traces),
        professor_final=_project_final(orchestration, orchestration_traces),
        trade_proposal=_project_trade_proposal(orchestration, orchestration_traces),
        risk=_project_risk(pipeline_result, paper_traces),
        execution=_project_execution(pipeline_result, paper_traces),
    )


def _project_analytics(link: OpportunityAnalyticsLink) -> AnalyticsRefProjection:
    snapshot = link.analytics_snapshot
    return AnalyticsRefProjection(
        link_id=link.link_id,
        link_fingerprint=link.link_fingerprint,
        link_policy_version=link.link_policy_version,
        status=_text(link.status),
        analytics_run_id=link.analytics_run_id,
        analytics_snapshot_id=(snapshot.analytics_snapshot_id if snapshot is not None else None),
        analytics_snapshot_fingerprint=(
            snapshot.analytics_snapshot_fingerprint if snapshot is not None else None
        ),
        analytics_as_of=(snapshot.as_of if snapshot is not None else None),
        source_cursor_fingerprint=link.opportunity.observation.source_cursor_fingerprint,
        analytics_snapshot_source_cursor_fingerprint=(
            snapshot.source_cursor_fingerprint if snapshot is not None else None
        ),
        diagnostics=tuple(str(item) for item in link.diagnostics),
    )


def _validate_point_chain(point: Any, link: OpportunityAnalyticsLink) -> None:
    opportunity = getattr(point, "opportunity", None)
    feature = getattr(point, "feature_snapshot", None)
    if opportunity is None or feature is None:
        raise ValueError("Decision Intelligence requires CandidateOpportunity and FeatureSnapshot")

    source = link.opportunity
    observation = source.observation
    scan_result = getattr(point, "scan_result", None)
    if scan_result is None:
        raise ValueError("Decision Intelligence requires the canonical ScanResult")
    checks = (
        (str(source.opportunity_id) == str(opportunity.opportunity_id), "opportunity_id"),
        (str(observation.feature_snapshot_id) == str(feature.snapshot_id), "feature_snapshot_id"),
        (str(opportunity.snapshot_id) == str(feature.snapshot_id), "snapshot_id"),
        (str(observation.feature_version) == str(feature.feature_version), "feature_version"),
        (str(observation.scanner_version) == str(opportunity.scanner_version), "scanner_version"),
        (scan_result.score == opportunity.priority_score, "scanner score"),
        (tuple(scan_result.triggers) == tuple(opportunity.triggers), "scanner triggers"),
        (
            str(scan_result.opportunity.opportunity_id) == str(opportunity.opportunity_id),
            "ScanResult opportunity_id",
        ),
        (str(observation.system_id) == str(opportunity.system_id), "system_id"),
        (str(observation.symbol) == str(opportunity.symbol), "symbol"),
        (str(observation.decision_timeframe) == str(opportunity.timeframe), "timeframe"),
        (observation.observed_at == point.observed_at, "observed_at"),
        (observation.observed_at == feature.observed_at, "feature observed_at"),
        (observation.observed_at == opportunity.created_at, "opportunity created_at"),
        (
            observation.source_cursor_fingerprint
            == getattr(point, "mtf_cursor_fingerprint", None),
            "source cursor fingerprint",
        ),
    )
    for valid, name in checks:
        if not valid:
            raise ValueError(f"Decision Intelligence source mismatch: {name}")

    context = getattr(point, "decision_context", None)
    if context is None:
        if (
            source.decision_context_id is not None
            or source.decision_context_fingerprint is not None
        ):
            raise ValueError("Analytics link references a missing DecisionContext")
    else:
        if str(context.context_id) != str(source.decision_context_id):
            raise ValueError("DecisionContext ID does not match 24B.1 link")
        if str(context.context_fingerprint) != str(source.decision_context_fingerprint):
            raise ValueError("DecisionContext fingerprint does not match 24B.1 link")
        if context.as_of != observation.observed_at:
            raise ValueError("DecisionContext as_of does not match decision observation")

    pipeline_result = getattr(point, "pipeline_result", None)
    if pipeline_result is None:
        return
    if str(pipeline_result.opportunity_id) != str(opportunity.opportunity_id):
        raise ValueError("PaperPipelineResult opportunity_id mismatch")
    if str(pipeline_result.source_snapshot_id) != str(opportunity.snapshot_id):
        raise ValueError("PaperPipelineResult source_snapshot_id mismatch")

    orchestration = getattr(pipeline_result, "orchestration_result", None)
    if orchestration is not None:
        orchestration_checks = (
            (
                str(orchestration.opportunity_id) == str(opportunity.opportunity_id),
                "opportunity_id",
            ),
            (str(orchestration.source_snapshot_id) == str(opportunity.snapshot_id), "snapshot_id"),
            (str(orchestration.system_id) == str(opportunity.system_id), "system_id"),
            (str(orchestration.symbol) == str(opportunity.symbol), "symbol"),
        )
        for valid, name in orchestration_checks:
            if not valid:
                raise ValueError(f"OrchestrationResult {name} mismatch")

        proposal = getattr(orchestration, "trade_proposal", None)
        if proposal is not None:
            proposal_checks = (
                (str(proposal.opportunity_id) == str(opportunity.opportunity_id), "opportunity_id"),
                (str(proposal.source_snapshot_id) == str(opportunity.snapshot_id), "snapshot_id"),
                (str(proposal.system_id) == str(opportunity.system_id), "system_id"),
                (str(proposal.symbol) == str(opportunity.symbol), "symbol"),
                (str(proposal.timeframe) == str(opportunity.timeframe), "timeframe"),
            )
            for valid, name in proposal_checks:
                if not valid:
                    raise ValueError(f"TradeProposal {name} mismatch")

    proposal = getattr(orchestration, "trade_proposal", None) if orchestration is not None else None
    risk_input = getattr(pipeline_result, "risk_input", None)
    risk_record = getattr(pipeline_result, "risk_record", None)
    if risk_input is not None:
        if proposal is None:
            raise ValueError("Risk input cannot exist without TradeProposal")
        risk_checks = (
            (str(risk_input.proposal_id) == str(proposal.proposal_id), "proposal_id"),
            (str(risk_input.system_id) == str(opportunity.system_id), "system_id"),
            (str(risk_input.symbol) == str(opportunity.symbol), "symbol"),
            (_text(risk_input.side) == str(proposal.side), "side"),
        )
        for valid, name in risk_checks:
            if not valid:
                raise ValueError(f"Risk input {name} mismatch")
    if risk_record is not None:
        if proposal is None:
            raise ValueError("RiskDecision cannot exist without TradeProposal")
        if str(risk_record.decision.proposal_id) != str(proposal.proposal_id):
            raise ValueError("RiskDecision proposal_id mismatch")
        if risk_input is None:
            raise ValueError("RiskDecision cannot exist without Risk input")

    intent = getattr(pipeline_result, "order_intent", None)
    order = getattr(pipeline_result, "order", None)
    fill = getattr(pipeline_result, "fill", None)
    if intent is not None:
        if risk_record is None:
            raise ValueError("OrderIntent cannot exist without RiskDecision")
        if str(intent.risk_decision_id) != str(risk_record.risk_decision_id):
            raise ValueError("OrderIntent risk_decision_id mismatch")
        if _text(risk_record.decision.status) == "REJECTED":
            raise ValueError("Risk REJECTED cannot produce OrderIntent")
        if intent.quantity != risk_record.decision.approved_quantity:
            raise ValueError("OrderIntent quantity does not match Risk approved_quantity")
        if str(intent.system_id) != str(opportunity.system_id):
            raise ValueError("OrderIntent system_id mismatch")
        if str(intent.symbol) != str(opportunity.symbol):
            raise ValueError("OrderIntent symbol mismatch")
    if order is not None:
        if intent is None:
            raise ValueError("BrokerOrder cannot exist without OrderIntent")
        if str(order.client_order_id) != str(intent.client_order_id):
            raise ValueError("BrokerOrder client_order_id mismatch")
        if order.requested_quantity != intent.quantity:
            raise ValueError("BrokerOrder requested_quantity does not match OrderIntent")
        if str(order.system_id) != str(opportunity.system_id):
            raise ValueError("BrokerOrder system_id mismatch")
        if str(order.symbol) != str(opportunity.symbol):
            raise ValueError("BrokerOrder symbol mismatch")
    if fill is not None:
        if order is None:
            raise ValueError("Fill cannot exist without BrokerOrder")
        if str(fill.broker_order_id) != str(order.broker_order_id):
            raise ValueError("Fill broker_order_id mismatch")

    for name in ("position_before", "position_after"):
        position = getattr(pipeline_result, name, None)
        if position is None:
            continue
        if str(position.system_id) != str(opportunity.system_id):
            raise ValueError(f"{name} system_id mismatch")
        if str(position.symbol) != str(opportunity.symbol):
            raise ValueError(f"{name} symbol mismatch")


def _link_index(link_set: OpportunityAnalyticsLinkSet) -> dict[str, OpportunityAnalyticsLink]:
    result: dict[str, OpportunityAnalyticsLink] = {}
    for link in link_set.links:
        opportunity_id = link.opportunity.opportunity_id
        if opportunity_id in result:
            raise ValueError("Analytics link set contains duplicate opportunity_id")
        result[opportunity_id] = link
    return result


def _validate_funnel_report(replay_result: Any, report: Any | None, candidate_count: int) -> None:
    if report is None:
        return
    run = replay_result.backtest_result.run
    checks = (
        (str(report.run_id) == str(run.run_id), "run_id"),
        (str(report.dataset_id) == str(run.dataset.dataset_id), "dataset_id"),
        (str(report.dataset_version) == str(run.dataset.version), "dataset_version"),
        (str(report.system_id) == str(run.config.system_id), "system_id"),
        (int(report.counts.candidate_opportunities) == candidate_count, "candidate count"),
    )
    for valid, name in checks:
        if not valid:
            raise ValueError(f"DecisionFunnelReport {name} mismatch")


def build_decision_intelligence_record(
    *,
    point: Any,
    link: OpportunityAnalyticsLink,
) -> DecisionIntelligenceRecord:
    """Project one persisted replay decision chain plus its canonical 24B.1 link."""

    _validate_point_chain(point, link)
    opportunity = point.opportunity
    observation = link.opportunity.observation
    return DecisionIntelligenceRecord.create(
        source_backtest_run_id=observation.source_backtest_run_id,
        analytics_run_id=link.analytics_run_id,
        opportunity_id=str(opportunity.opportunity_id),
        opportunity_fingerprint=link.opportunity.opportunity_fingerprint,
        system_id=str(opportunity.system_id),
        symbol=str(opportunity.symbol),
        decision_timeframe=str(opportunity.timeframe),
        observed_at=observation.observed_at,
        scanner=_project_scanner(point, opportunity),
        decision_context=_project_context(point),
        decision=_project_decision(point),
        analytics=_project_analytics(link),
    )


def build_decision_intelligence_record_set(
    replay_result: Any,
    *,
    analytics_links: OpportunityAnalyticsLinkSet,
    decision_funnel_report: Any | None = None,
) -> DecisionIntelligenceRecordSet:
    """Build one read-only record per CandidateOpportunity without re-running services."""

    backtest_result = replay_result.backtest_result
    run = backtest_result.run
    if _text(getattr(backtest_result, "status", None)) != "COMPLETED":
        raise ValueError("Decision Intelligence requires a completed Historical Replay")
    if analytics_links.source_backtest_run_id != run.run_id:
        raise ValueError("Analytics link set source BacktestRun does not match replay")

    points = tuple(point for point in replay_result.points if point.opportunity is not None)
    opportunity_ids = tuple(str(point.opportunity.opportunity_id) for point in points)
    if len(set(opportunity_ids)) != len(opportunity_ids):
        raise ValueError("replay contains duplicate CandidateOpportunity.opportunity_id")

    links = _link_index(analytics_links)
    for link in links.values():
        if link.opportunity.observation.source_backtest_run_id != run.run_id:
            raise ValueError("Analytics link observation BacktestRun does not match replay")
        if link.analytics_run_id != analytics_links.analytics_run_id:
            raise ValueError("Analytics link analytics_run_id does not match link set")
    if set(links) != set(opportunity_ids):
        missing = sorted(set(opportunity_ids) - set(links))
        extra = sorted(set(links) - set(opportunity_ids))
        raise ValueError(
            "Analytics link coverage must be exactly one-to-one with replay opportunities; "
            f"missing={missing}, extra={extra}"
        )

    _validate_funnel_report(replay_result, decision_funnel_report, len(points))
    records = tuple(
        build_decision_intelligence_record(
            point=point,
            link=links[str(point.opportunity.opportunity_id)],
        )
        for point in points
    )
    return DecisionIntelligenceRecordSet.create(
        source_backtest_run_id=str(run.run_id),
        analytics_run_id=analytics_links.analytics_run_id,
        records=records,
    )


__all__ = [
    "build_decision_intelligence_record",
    "build_decision_intelligence_record_set",
]
