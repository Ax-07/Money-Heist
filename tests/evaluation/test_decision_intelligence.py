from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.agents.models import (
    BerlinAnalysis,
    EvidenceReference,
    PalermoReview,
    ProfessorPlan,
    SpecialistStance,
    TokyoAnalysis,
)
from app.common.canonical import stable_digest
from app.evaluation.analytics_attribution import (
    AnalyticsSnapshotRef,
    DecisionObservationKey,
    OpportunityAnalyticsLink,
    OpportunityAnalyticsLinkSet,
    OpportunityAnalyticsLinkStatus,
    OpportunityObservationRef,
)
from app.evaluation.decision_intelligence import (
    build_decision_intelligence_record_set,
)
from app.intelligence.ai_gateway import (
    AGENT_DIALOGUE_LANGUAGE,
    AGENT_DIALOGUE_LANGUAGE_VERSION,
    PROMPT_TRANSPORT_VERSION,
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
from app.services.orchestration.models import (
    AgentCallAudit,
    ComputeGateDecision,
    ComputeGateReason,
    ComputeLevel,
    OrchestrationResult,
    PalermoRunRecord,
    PipelineAuditEvent,
    PipelineFailure,
    PipelineFailureCode,
    PipelineStatus,
    ProfessorFinalDecision,
    ProfessorTradeParameters,
    SpecialistRunRecord,
    TradeProposal,
)
from app.services.paper_pipeline.models import (
    PaperOrderIntent,
    PaperPipelineEvent,
    PaperPipelineFailure,
    PaperPipelineFailureCode,
    PaperPipelineResult,
    PaperPipelineStatus,
    RiskDecisionRecord,
)
from app.trading.paper.models import (
    BrokerOrder,
    Fill,
    Liquidity,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from app.trading.risk.models import (
    RiskDecision,
    RiskDecisionStatus,
    RiskReasonCode,
    TradeProposalRiskInput,
    TradeSide,
)

T = datetime(2026, 1, 12, 14, 0, tzinfo=UTC)
POLICY = "mtf-utc-closed-v1"
CURSOR = "a" * 64
DATASET_SHA = "b" * 64
ANALYTICS_SNAPSHOT_SHA = "c" * 64
OPPORTUNITY_ID = "11111111-1111-4111-8111-111111111111"
PLAN_REQUEST = UUID("22222222-2222-4222-8222-222222222222")
BERLIN_REQUEST = UUID("33333333-3333-4333-8333-333333333333")
TOKYO_REQUEST = UUID("44444444-4444-4444-8444-444444444444")
PALERMO_REQUEST = UUID("55555555-5555-4555-8555-555555555555")
FINAL_REQUEST = UUID("66666666-6666-4666-8666-666666666666")
PROPOSAL_ID = UUID("77777777-7777-4777-8777-777777777777")
RISK_ID = UUID("88888888-8888-4888-8888-888888888888")


def source_run(*, code_version: str = "test-24b2") -> BacktestRun:
    dataset = DatasetRef(
        dataset_id="BTC/EUR:15m:24b2",
        version="sha256:24b2",
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
        code_version=code_version,
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


def opportunity(run: BacktestRun, *, opportunity_id: str = OPPORTUNITY_ID):
    feature = SimpleNamespace(
        snapshot_id=f"feature-{opportunity_id}",
        symbol=run.dataset.symbol,
        timeframe="1h",
        observed_at=T,
        feature_version=run.config.feature_version,
        regime="BULLISH_TREND",
    )
    candidate = CandidateOpportunity(
        scanner_version=run.config.scanner_version,
        opportunity_id=opportunity_id,
        snapshot_id=feature.snapshot_id,
        system_id=run.config.system_id,
        symbol=run.dataset.symbol,
        timeframe="1h",
        priority_score=82,
        triggers=(ScannerTrigger.RANGE_BREAK, ScannerTrigger.VOLUME_EXPANSION),
        created_at=T,
        expires_at=T + timedelta(hours=1),
    )
    scan = ScanResult(
        score=82,
        triggers=candidate.triggers,
        opportunity=candidate,
    )
    return feature, candidate, scan


def context_ref() -> SimpleNamespace:
    return SimpleNamespace(
        schema_version="1.0",
        context_version="decision-context-v1",
        context_id="context-24b2",
        context_fingerprint="d" * 64,
        system_id="balanced_v1",
        symbol="BTC/EUR",
        as_of=T,
        primary_timeframe="1h",
        timeframe_policy_version=POLICY,
        market=SimpleNamespace(source_cursor_fingerprint=CURSOR),
    )


def gate(*, allowed: bool = True) -> ComputeGateDecision:
    return ComputeGateDecision(
        level=(ComputeLevel.LEVEL_2_MINI_CREW if allowed else ComputeLevel.SKIP_AI),
        reason=(
            ComputeGateReason.ALLOWED_MINI_CREW
            if allowed
            else ComputeGateReason.PRIORITY_TOO_LOW
        ),
        priority_score=82,
        remaining_budget_eur=Decimal("10"),
        minimum_required_budget_eur=Decimal("0.10"),
    )


def evidence(source_key: str) -> EvidenceReference:
    return EvidenceReference(source_key=source_key, observation="Observation canonique en français")


def calls() -> tuple[AgentCallAudit, ...]:
    return (
        AgentCallAudit(
            request_id=PLAN_REQUEST,
            agent_id="professor",
            phase="professor_plan",
            prompt_version="professor-v1",
            route_id="route-professor",
            model_id="model-professor",
            estimated_cost_eur=Decimal("0.01"),
            attempts=1,
        ),
        AgentCallAudit(
            request_id=BERLIN_REQUEST,
            agent_id="berlin",
            phase="specialist_independent_round_1",
            prompt_version="berlin-v1",
            route_id="route-specialist",
            model_id="model-specialist",
            estimated_cost_eur=Decimal("0.01"),
            attempts=1,
        ),
        AgentCallAudit(
            request_id=TOKYO_REQUEST,
            agent_id="tokyo",
            phase="specialist_independent_round_1",
            prompt_version="tokyo-v1",
            route_id="route-specialist",
            model_id="model-specialist",
            estimated_cost_eur=Decimal("0.01"),
            attempts=1,
        ),
        AgentCallAudit(
            request_id=PALERMO_REQUEST,
            agent_id="palermo",
            phase="palermo_red_team",
            prompt_version="palermo-v1",
            route_id="route-palermo",
            model_id="model-palermo",
            estimated_cost_eur=Decimal("0.01"),
            attempts=1,
        ),
        AgentCallAudit(
            request_id=FINAL_REQUEST,
            agent_id="professor",
            phase="professor_finalize",
            prompt_version="professor-v1",
            route_id="route-professor",
            model_id="model-professor",
            estimated_cost_eur=Decimal("0.01"),
            attempts=1,
        ),
    )


def specialist_runs() -> tuple[SpecialistRunRecord, ...]:
    berlin = BerlinAnalysis(
        agent="berlin",
        stance=SpecialistStance.LONG,
        confidence=0.73,
        evidence=[evidence("market_context.ema_20")],
        risks=["Tendance déjà mature"],
        invalidation=["Perte du support"],
        data_gaps=[],
        regime="BULLISH_TREND",
        trend_maturity="MATURE",
        multi_timeframe_alignment="BULLISH",
    )
    tokyo = TokyoAnalysis(
        agent="tokyo",
        stance=SpecialistStance.LONG,
        confidence=0.68,
        evidence=[evidence("market_context.rsi")],
        risks=["Momentum susceptible de ralentir"],
        invalidation=["Divergence baissière"],
        data_gaps=[],
        momentum="BULLISH",
        momentum_quality="MODERATE",
        breakout_quality="CONFIRMED",
    )
    return (
        SpecialistRunRecord(
            agent_id="berlin",
            request_id=BERLIN_REQUEST,
            prompt_version="berlin-v1",
            route_id="route-specialist",
            model_id="model-specialist",
            analysis=berlin,
        ),
        SpecialistRunRecord(
            agent_id="tokyo",
            request_id=TOKYO_REQUEST,
            prompt_version="tokyo-v1",
            route_id="route-specialist",
            model_id="model-specialist",
            analysis=tokyo,
        ),
    )


def orchestration_events(*, include_proposal: bool = True) -> tuple[PipelineAuditEvent, ...]:
    rows = [
        (1, "context", "COMPLETED"),
        (2, "compute_gate", "COMPLETED"),
        (3, "professor_plan", "COMPLETED"),
        (4, "specialists_independent_round_1", "STARTED"),
        (5, "specialists_independent_round_1", "COMPLETED"),
        (6, "palermo_red_team", "COMPLETED"),
        (7, "professor_finalize", "COMPLETED"),
        (8, "trade_proposal", "COMPLETED" if include_proposal else "SKIPPED"),
    ]
    return tuple(
        PipelineAuditEvent(sequence=seq, stage=stage, status=status, created_at=T)
        for seq, stage, status in rows
    )


def make_trade_proposal(candidate: CandidateOpportunity) -> TradeProposal:
    return TradeProposal(
        proposal_id=PROPOSAL_ID,
        opportunity_id=candidate.opportunity_id,
        source_snapshot_id=candidate.snapshot_id,
        system_id=candidate.system_id,
        symbol=candidate.symbol,
        timeframe=candidate.timeframe,
        side="LONG",
        confidence=0.71,
        entry_price=Decimal("100"),
        stop_price=Decimal("95"),
        targets=(Decimal("110"),),
        expected_rr=Decimal("2"),
        thesis=("Structure haussière confirmée",),
        counter_evidence=("Momentum non extrême",),
        invalidation=("Clôture sous 95",),
        evidence=(evidence("berlin.regime"),),
        market_regime="BULLISH_TREND",
        feature_version="feature-engine-v1",
        professor_prompt_version="professor-v1",
        professor_request_id=FINAL_REQUEST,
        specialist_request_ids=(BERLIN_REQUEST, TOKYO_REQUEST),
        palermo_request_id=PALERMO_REQUEST,
        created_at=T,
        expires_at=candidate.expires_at,
    )


def make_orchestration(
    candidate: CandidateOpportunity,
    *,
    palermo_verdict: str = "CAUTION",
    no_trade: bool = False,
) -> OrchestrationResult:
    plan = ProfessorPlan(
        decision="MINI_CREW",
        selected_agents=["berlin", "tokyo"],
        rationale=["Deux expertises complémentaires"],
        request_more_analysis=False,
    )
    palermo = PalermoRunRecord(
        request_id=PALERMO_REQUEST,
        prompt_version="palermo-v1",
        route_id="route-palermo",
        model_id="model-palermo",
        review=PalermoReview(
            verdict=palermo_verdict,
            severity=0.5,
            critical_objections=["Risque de faux breakout"],
            missing_checks=[],
            conditions_to_continue=["Conserver le stop"],
        ),
    )
    if no_trade:
        final = ProfessorFinalDecision(
            direction="NO_TRADE",
            confidence=0.64,
            thesis=["Avantage insuffisant"],
            counter_evidence=["Contradiction Palermo"],
            invalidation=[],
            evidence=[],
            trade=None,
        )
        proposal = None
        status = PipelineStatus.NO_TRADE
    else:
        final = ProfessorFinalDecision(
            direction="LONG",
            confidence=0.71,
            thesis=["Structure haussière confirmée"],
            counter_evidence=["Risque de faux breakout"],
            invalidation=["Clôture sous 95"],
            evidence=[evidence("berlin.regime")],
            trade=ProfessorTradeParameters(
                entry_price=Decimal("100"),
                stop_price=Decimal("95"),
                targets=(Decimal("110"),),
                expected_rr=Decimal("2"),
            ),
        )
        proposal = make_trade_proposal(candidate)
        status = PipelineStatus.TRADE_PROPOSAL
    return OrchestrationResult(
        status=status,
        opportunity_id=candidate.opportunity_id,
        source_snapshot_id=candidate.snapshot_id,
        system_id=candidate.system_id,
        symbol=candidate.symbol,
        compute_gate=gate(),
        professor_plan=plan,
        specialist_runs=specialist_runs(),
        palermo_run=palermo,
        professor_decision=final,
        trade_proposal=proposal,
        failure=None,
        agent_calls=calls(),
        audit_events=orchestration_events(include_proposal=not no_trade),
    )


def paper_events(*, executed: bool = True) -> tuple[PaperPipelineEvent, ...]:
    rows = [
        (1, "orchestration", "COMPLETED"),
        (2, "trade_proposal", "COMPLETED"),
        (3, "risk_engine", "COMPLETED"),
    ]
    if executed:
        rows.extend(
            (
                (4, "order_intent", "COMPLETED"),
                (5, "paper_execution", "COMPLETED"),
            )
        )
    return tuple(
        PaperPipelineEvent(
            sequence=seq,
            stage=stage,
            status=status,
            opportunity_id=OPPORTUNITY_ID,
            proposal_id=str(PROPOSAL_ID),
            source_snapshot_id=f"feature-{OPPORTUNITY_ID}",
            created_at=T,
        )
        for seq, stage, status in rows
    )


def make_risk_input(candidate: CandidateOpportunity) -> TradeProposalRiskInput:
    return TradeProposalRiskInput(
        proposal_id=str(PROPOSAL_ID),
        system_id=candidate.system_id,
        symbol=candidate.symbol,
        side=TradeSide.LONG,
        entry_price=Decimal("100"),
        stop_price=Decimal("95"),
        expected_rr=Decimal("2"),
        expires_at=candidate.expires_at,
    )


def make_risk_record(
    *,
    status: RiskDecisionStatus = RiskDecisionStatus.RESIZED,
) -> RiskDecisionRecord:
    if status is RiskDecisionStatus.REJECTED:
        reasons = (RiskReasonCode.MIN_EXPECTED_RR,)
        quantity = Decimal("0")
        risk_amount = Decimal("0")
        notional = Decimal("0")
    elif status is RiskDecisionStatus.RESIZED:
        reasons = (RiskReasonCode.RESIZED_PORTFOLIO_RISK,)
        quantity = Decimal("0.5")
        risk_amount = Decimal("2.5")
        notional = Decimal("50")
    else:
        reasons = (RiskReasonCode.APPROVED,)
        quantity = Decimal("1")
        risk_amount = Decimal("5")
        notional = Decimal("100")
    return RiskDecisionRecord(
        risk_decision_id=RISK_ID,
        decision=RiskDecision(
            proposal_id=str(PROPOSAL_ID),
            status=status,
            reason_codes=reasons,
            approved_quantity=quantity,
            approved_risk_amount=risk_amount,
            approved_notional=notional,
            created_at=T,
            details={"source": "unit-test"},
        ),
    )


def make_execution(candidate: CandidateOpportunity, *, quantity: Decimal):
    intent = PaperOrderIntent(
        risk_decision_id=RISK_ID,
        system_id=candidate.system_id,
        symbol=candidate.symbol,
        side=OrderSide.BUY,
        quantity=quantity,
        client_order_id="client-24b2",
    )
    order = BrokerOrder(
        broker_order_id="order-24b2",
        client_order_id=intent.client_order_id,
        system_id=candidate.system_id,
        symbol=candidate.symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        requested_quantity=quantity,
        filled_quantity=quantity,
        status=OrderStatus.FILLED,
        created_at=T,
        updated_at=T,
        average_fill_price=Decimal("100.10"),
    )
    fill = Fill(
        fill_id="fill-24b2",
        broker_order_id=order.broker_order_id,
        price=Decimal("100.10"),
        quantity=quantity,
        fee=Decimal("0.10"),
        fee_rate_bps=Decimal("20"),
        liquidity=Liquidity.TAKER,
        filled_at=T,
    )
    position_after = Position(
        system_id=candidate.system_id,
        symbol=candidate.symbol,
        signed_quantity=quantity,
        average_entry=Decimal("100.10"),
    )
    return intent, order, fill, position_after


def pipeline_result(
    candidate: CandidateOpportunity,
    *,
    risk_status: RiskDecisionStatus = RiskDecisionStatus.RESIZED,
    palermo_verdict: str = "CAUTION",
    no_trade: bool = False,
    execution_failure: bool = False,
) -> PaperPipelineResult:
    orchestration = make_orchestration(
        candidate,
        palermo_verdict=palermo_verdict,
        no_trade=no_trade,
    )
    if no_trade:
        return PaperPipelineResult(
            status=PaperPipelineStatus.NO_TRADE,
            opportunity_id=candidate.opportunity_id,
            source_snapshot_id=candidate.snapshot_id,
            orchestration_result=orchestration,
        )

    risk_record = make_risk_record(status=risk_status)
    if risk_status is RiskDecisionStatus.REJECTED:
        return PaperPipelineResult(
            status=PaperPipelineStatus.RISK_REJECTED,
            opportunity_id=candidate.opportunity_id,
            source_snapshot_id=candidate.snapshot_id,
            orchestration_result=orchestration,
            risk_input=make_risk_input(candidate),
            risk_record=risk_record,
            audit_events=paper_events(executed=False),
        )

    intent, order, fill, position_after = make_execution(
        candidate, quantity=risk_record.decision.approved_quantity
    )
    if execution_failure:
        return PaperPipelineResult(
            status=PaperPipelineStatus.FAILED,
            opportunity_id=candidate.opportunity_id,
            source_snapshot_id=candidate.snapshot_id,
            orchestration_result=orchestration,
            risk_input=make_risk_input(candidate),
            risk_record=risk_record,
            order_intent=intent,
            failure=PaperPipelineFailure(
                code=PaperPipelineFailureCode.BROKER_EXECUTION_FAILED,
                stage="paper_broker",
                message="paper broker unavailable",
            ),
            audit_events=paper_events(executed=False),
        )
    return PaperPipelineResult(
        status=PaperPipelineStatus.EXECUTED,
        opportunity_id=candidate.opportunity_id,
        source_snapshot_id=candidate.snapshot_id,
        orchestration_result=orchestration,
        risk_input=make_risk_input(candidate),
        risk_record=risk_record,
        order_intent=intent,
        order=order,
        fill=fill,
        position_after=position_after,
        audit_events=paper_events(executed=True),
    )


def gate_stop_pipeline(candidate: CandidateOpportunity) -> PaperPipelineResult:
    orchestration = OrchestrationResult(
        status=PipelineStatus.NO_ANALYSIS,
        opportunity_id=candidate.opportunity_id,
        source_snapshot_id=candidate.snapshot_id,
        system_id=candidate.system_id,
        symbol=candidate.symbol,
        compute_gate=gate(allowed=False),
        audit_events=(
            PipelineAuditEvent(sequence=1, stage="context", status="COMPLETED", created_at=T),
            PipelineAuditEvent(sequence=2, stage="compute_gate", status="SKIPPED", created_at=T),
        ),
    )
    return PaperPipelineResult(
        status=PaperPipelineStatus.NO_ANALYSIS,
        opportunity_id=candidate.opportunity_id,
        source_snapshot_id=candidate.snapshot_id,
        orchestration_result=orchestration,
    )


def agent_failure_pipeline(candidate: CandidateOpportunity) -> PaperPipelineResult:
    plan = ProfessorPlan(
        decision="MINI_CREW",
        selected_agents=["berlin", "tokyo"],
        rationale=["Tester deux spécialistes"],
        request_more_analysis=False,
    )
    failure = PipelineFailure(
        code=PipelineFailureCode.AI_PROVIDER_ERROR,
        stage="specialists_independent_round_1",
        message="provider unavailable",
        agent_id="tokyo",
    )
    orchestration = OrchestrationResult(
        status=PipelineStatus.FAILED,
        opportunity_id=candidate.opportunity_id,
        source_snapshot_id=candidate.snapshot_id,
        system_id=candidate.system_id,
        symbol=candidate.symbol,
        compute_gate=gate(),
        professor_plan=plan,
        specialist_runs=(specialist_runs()[0],),
        failure=failure,
        agent_calls=calls()[:2],
        audit_events=(
            PipelineAuditEvent(sequence=1, stage="context", status="COMPLETED", created_at=T),
            PipelineAuditEvent(sequence=2, stage="compute_gate", status="COMPLETED", created_at=T),
            PipelineAuditEvent(
                sequence=3, stage="professor_plan", status="COMPLETED", created_at=T
            ),
            PipelineAuditEvent(
                sequence=4,
                stage="specialists_independent_round_1",
                status="STARTED",
                created_at=T,
            ),
            PipelineAuditEvent(
                sequence=5,
                stage="specialists_independent_round_1",
                status="FAILED",
                created_at=T,
            ),
        ),
    )
    return PaperPipelineResult(
        status=PaperPipelineStatus.FAILED,
        opportunity_id=candidate.opportunity_id,
        source_snapshot_id=candidate.snapshot_id,
        orchestration_result=orchestration,
        failure=PaperPipelineFailure(
            code=PaperPipelineFailureCode.ORCHESTRATION_FAILED,
            stage="orchestration",
            message="upstream orchestration failed",
        ),
    )


def replay(
    run: BacktestRun,
    *,
    pipeline: PaperPipelineResult | None,
    decision_context: object | None = None,
    opportunity_id: str = OPPORTUNITY_ID,
):
    feature, candidate, scan = opportunity(run, opportunity_id=opportunity_id)
    if pipeline is not None and pipeline.opportunity_id != candidate.opportunity_id:
        raise ValueError("pipeline fixture opportunity does not match replay opportunity")
    point = SimpleNamespace(
        observed_at=T,
        visible_candle_count=100,
        feature_snapshot=feature,
        scan_result=scan,
        opportunity=candidate,
        decision_timeframe="1h",
        mtf_cursor_fingerprint=CURSOR,
        decision_context=decision_context,
        pipeline_result=pipeline,
        account_state=None,
        exit_events=(),
    )
    result = BacktestResult(
        run=run,
        status=BacktestRunStatus.COMPLETED,
        processed_candles=1,
        opportunity_count=1,
        executed_order_count=int(
            pipeline is not None and pipeline.status is PaperPipelineStatus.EXECUTED
        ),
    )
    return SimpleNamespace(backtest_result=result, points=(point,))


def links_for(
    replay_result,
    *,
    analytics_run_id: str = "analytics-run-a",
    status: OpportunityAnalyticsLinkStatus = OpportunityAnalyticsLinkStatus.MATCHED,
    snapshot_fingerprint: str = ANALYTICS_SNAPSHOT_SHA,
) -> OpportunityAnalyticsLinkSet:
    run = replay_result.backtest_result.run
    point = replay_result.points[0]
    candidate = point.opportunity
    context = point.decision_context
    observation = DecisionObservationKey(
        source_backtest_run_id=run.run_id,
        dataset_id=run.dataset.dataset_id,
        dataset_version=run.dataset.version,
        dataset_content_sha256=run.dataset.content_sha256,
        dataset_source=run.dataset.source,
        system_id=run.config.system_id,
        symbol=candidate.symbol,
        source_timeframe=run.dataset.timeframe,
        decision_timeframe=candidate.timeframe,
        observed_at=T,
        mtf_policy_version=POLICY,
        source_cursor_fingerprint=CURSOR,
        feature_snapshot_id=candidate.snapshot_id,
        feature_version=run.config.feature_version,
        scanner_version=run.config.scanner_version,
    )
    source = OpportunityObservationRef(
        observation=observation,
        opportunity_id=candidate.opportunity_id,
        opportunity_fingerprint=stable_digest(candidate.model_dump(mode="python")),
        decision_context_id=(str(context.context_id) if context is not None else None),
        decision_context_fingerprint=(
            str(context.context_fingerprint) if context is not None else None
        ),
    )
    snapshot = None
    if status is OpportunityAnalyticsLinkStatus.MATCHED:
        snapshot = AnalyticsSnapshotRef(
            analytics_run_id=analytics_run_id,
            analytics_snapshot_id="analytics-snapshot-24b2",
            analytics_snapshot_fingerprint=snapshot_fingerprint,
            source_backtest_run_id=run.run_id,
            dataset_id=run.dataset.dataset_id,
            dataset_version=run.dataset.version,
            dataset_content_sha256=run.dataset.content_sha256,
            symbol=candidate.symbol,
            decision_timeframe=candidate.timeframe,
            as_of=T,
            mtf_policy_version=POLICY,
            source_cursor_fingerprint=CURSOR,
            analytics_bundle_version="analytics-24a7-v1",
        )
    link = OpportunityAnalyticsLink.create(
        analytics_run_id=analytics_run_id,
        status=status,
        opportunity=source,
        analytics_snapshot=snapshot,
        diagnostics=("snapshot absent",) if snapshot is None else (),
    )
    return OpportunityAnalyticsLinkSet.create(
        source_backtest_run_id=run.run_id,
        analytics_run_id=analytics_run_id,
        analytics_period_role="DESIGN",
        links=(link,),
    )


def complete_replay(*, risk_status=RiskDecisionStatus.RESIZED, decision_context=None):
    run = source_run()
    _, candidate, _ = opportunity(run)
    pipeline = pipeline_result(candidate, risk_status=risk_status)
    return replay(run, pipeline=pipeline, decision_context=decision_context)


def one_record(source, links=None):
    links = links or links_for(source)
    result = build_decision_intelligence_record_set(source, analytics_links=links)
    assert result.record_count == 1
    return result, result.records[0]


def test_complete_pipeline_record_preserves_canonical_artifacts() -> None:
    source = complete_replay(decision_context=context_ref())
    record_set, record = one_record(source)

    assert record_set.matched_analytics_count == 1
    assert record.scanner.priority_score == 82
    assert record.scanner.feature_version == "feature-engine-v1"
    assert record.scanner.market_regime == "BULLISH_TREND"
    assert record.decision_context.context_id == "context-24b2"
    assert record.decision.compute_gate.allows_ai is True
    assert record.decision.professor_plan.decision == "MINI_CREW"
    assert tuple(run.agent_id for run in record.decision.specialists.runs) == (
        "berlin",
        "tokyo",
    )
    assert record.decision.palermo.verdict == "CAUTION"
    assert record.decision.professor_final.direction == "LONG"
    assert record.decision.trade_proposal.proposal_id == str(PROPOSAL_ID)
    assert record.decision.trade_proposal.thesis == ("Structure haussière confirmée",)
    assert record.decision.risk.status == "RESIZED"
    assert record.decision.risk.reason_codes == ("RESIZED_PORTFOLIO_RISK",)
    assert record.decision.execution.order is not None
    assert record.decision.execution.fill is not None
    assert record.decision.execution.position_after is not None
    assert record.decision.execution.position_after.quantity == Decimal("0.5")
    assert record.analytics.analytics_snapshot_id == "analytics-snapshot-24b2"
    assert record.analytics.source_cursor_fingerprint == CURSOR
    assert record.analytics.analytics_snapshot_source_cursor_fingerprint == CURSOR


def test_missing_pipeline_result_still_produces_decision_record() -> None:
    run = source_run()
    source = replay(run, pipeline=None)
    _, record = one_record(source)

    assert record.decision.pipeline_result_present is False
    assert record.decision.compute_gate.reached is False
    assert record.decision.professor_plan.reached is False
    assert record.decision.execution.reached is False
    assert record.analytics.status == "MATCHED"


def test_compute_gate_stop_keeps_record_and_marks_later_stages_not_reached() -> None:
    run = source_run()
    _, candidate, _ = opportunity(run)
    source = replay(run, pipeline=gate_stop_pipeline(candidate))
    _, record = one_record(source)

    assert record.decision.compute_gate.reached is True
    assert record.decision.compute_gate.allows_ai is False
    assert record.decision.professor_plan.reached is False
    assert record.decision.specialists.reached is False
    assert record.decision.palermo.reached is False
    assert record.decision.professor_final.reached is False
    assert record.decision.risk.reached is False
    assert record.decision.execution.reached is False


def test_professor_no_trade_does_not_fabricate_trade_or_risk_artifacts() -> None:
    run = source_run()
    _, candidate, _ = opportunity(run)
    source = replay(run, pipeline=pipeline_result(candidate, no_trade=True))
    _, record = one_record(source)

    assert record.decision.professor_final.direction == "NO_TRADE"
    assert record.decision.trade_proposal.reached is False
    assert record.decision.trade_proposal.stage_status == "SKIPPED"
    assert record.decision.risk.reached is False
    assert record.decision.execution.reached is False


def test_palermo_reject_and_professor_final_remain_distinct() -> None:
    run = source_run()
    _, candidate, _ = opportunity(run)
    source = replay(
        run,
        pipeline=pipeline_result(candidate, palermo_verdict="REJECT", no_trade=True),
    )
    _, record = one_record(source)

    assert record.decision.palermo.verdict == "REJECT"
    assert record.decision.professor_final.direction == "NO_TRADE"


def test_risk_rejected_preserves_reason_and_has_no_execution() -> None:
    source = complete_replay(risk_status=RiskDecisionStatus.REJECTED)
    _, record = one_record(source)

    assert record.decision.trade_proposal.reached is True
    assert record.decision.risk.status == "REJECTED"
    assert record.decision.risk.reason_codes == ("MIN_EXPECTED_RR",)
    assert record.decision.execution.reached is False


def test_risk_resized_is_distinct_from_approved() -> None:
    source = complete_replay(risk_status=RiskDecisionStatus.RESIZED)
    _, record = one_record(source)

    assert record.decision.risk.status == "RESIZED"
    assert record.decision.risk.approved_quantity == Decimal("0.5")
    assert record.decision.trade_proposal.entry_price == Decimal("100")


def test_execution_failure_does_not_rewrite_authorized_risk() -> None:
    run = source_run()
    _, candidate, _ = opportunity(run)
    source = replay(
        run,
        pipeline=pipeline_result(
            candidate,
            risk_status=RiskDecisionStatus.APPROVED,
            execution_failure=True,
        ),
    )
    _, record = one_record(source)

    assert record.decision.risk.status == "APPROVED"
    assert record.decision.execution.reached is True
    assert record.decision.execution.order is None
    assert record.decision.execution.failure is not None
    assert record.decision.execution.failure.code == "BROKER_EXECUTION_FAILED"


def test_specialist_failure_remains_technical_failure() -> None:
    run = source_run()
    _, candidate, _ = opportunity(run)
    source = replay(run, pipeline=agent_failure_pipeline(candidate))
    _, record = one_record(source)

    assert record.decision.orchestration_status == "FAILED"
    assert record.decision.specialists.reached is True
    assert tuple(run.agent_id for run in record.decision.specialists.runs) == ("berlin",)
    assert record.decision.specialists.failure is not None
    assert record.decision.specialists.failure.agent_id == "tokyo"
    assert record.decision.professor_final.reached is False


def test_unmatched_analytics_link_keeps_decision_and_diagnostic() -> None:
    source = complete_replay()
    links = links_for(
        source,
        status=OpportunityAnalyticsLinkStatus.MISSING_ANALYTICS_SNAPSHOT,
    )
    record_set, record = one_record(source, links)

    assert record_set.unmatched_analytics_count == 1
    assert record.analytics.status == "MISSING_ANALYTICS_SNAPSHOT"
    assert record.analytics.analytics_snapshot_id is None
    assert record.analytics.source_cursor_fingerprint == CURSOR
    assert record.analytics.analytics_snapshot_source_cursor_fingerprint is None
    assert record.analytics.diagnostics == ("snapshot absent",)
    assert record.decision.professor_final.direction == "LONG"


def test_builder_never_rematches_analytics() -> None:
    source = complete_replay()
    source.points[0].analytics_snapshots = (object(), object())
    links = links_for(
        source,
        status=OpportunityAnalyticsLinkStatus.MISSING_ANALYTICS_SNAPSHOT,
    )
    _, record = one_record(source, links)

    assert record.analytics.status == "MISSING_ANALYTICS_SNAPSHOT"
    signature = inspect.signature(build_decision_intelligence_record_set)
    assert "snapshots" not in signature.parameters
    assert "analytics_run" not in signature.parameters


def test_cross_run_analytics_link_set_is_rejected() -> None:
    source_a = complete_replay()
    links_a = links_for(source_a)
    run_b = source_run(code_version="other-code-version")
    _, candidate_b, _ = opportunity(run_b)
    source_b = replay(run_b, pipeline=pipeline_result(candidate_b))

    with pytest.raises(ValueError, match="source BacktestRun"):
        build_decision_intelligence_record_set(source_b, analytics_links=links_a)


def test_cross_chain_risk_artifact_is_rejected() -> None:
    source = complete_replay()
    pipeline = source.points[0].pipeline_result
    assert pipeline is not None and pipeline.risk_record is not None
    foreign = RiskDecisionRecord(
        risk_decision_id=pipeline.risk_record.risk_decision_id,
        decision=RiskDecision(
            proposal_id="foreign-proposal",
            status=pipeline.risk_record.decision.status,
            reason_codes=pipeline.risk_record.decision.reason_codes,
            approved_quantity=pipeline.risk_record.decision.approved_quantity,
            approved_risk_amount=pipeline.risk_record.decision.approved_risk_amount,
            approved_notional=pipeline.risk_record.decision.approved_notional,
            created_at=T,
        ),
    )
    source.points[0].pipeline_result = replace(pipeline, risk_record=foreign)

    with pytest.raises(ValueError, match="RiskDecision proposal_id mismatch"):
        one_record(source)


def test_same_inputs_produce_same_record_id_fingerprint_and_json() -> None:
    source = complete_replay()
    links = links_for(source)

    first = build_decision_intelligence_record_set(source, analytics_links=links)
    second = build_decision_intelligence_record_set(source, analytics_links=links)

    assert first == second
    assert first.records[0].record_id == second.records[0].record_id
    assert first.records[0].record_fingerprint == second.records[0].record_fingerprint
    assert first.set_fingerprint == second.set_fingerprint
    assert first.model_dump_json() == second.model_dump_json()


def test_material_palermo_change_changes_record_fingerprint() -> None:
    run = source_run()
    _, candidate, _ = opportunity(run)
    source_a = replay(run, pipeline=pipeline_result(candidate, palermo_verdict="CAUTION"))
    source_b = replay(run, pipeline=pipeline_result(candidate, palermo_verdict="REJECT"))
    links = links_for(source_a)

    _, first = one_record(source_a, links)
    _, second = one_record(source_b, links)

    assert first.record_id == second.record_id
    assert first.record_fingerprint != second.record_fingerprint


def test_material_risk_change_changes_record_fingerprint() -> None:
    run = source_run()
    _, candidate, _ = opportunity(run)
    source_resized = replay(
        run, pipeline=pipeline_result(candidate, risk_status=RiskDecisionStatus.RESIZED)
    )
    source_approved = replay(
        run, pipeline=pipeline_result(candidate, risk_status=RiskDecisionStatus.APPROVED)
    )
    links = links_for(source_resized)

    _, resized = one_record(source_resized, links)
    _, approved = one_record(source_approved, links)

    assert resized.record_id == approved.record_id
    assert resized.record_fingerprint != approved.record_fingerprint


def test_material_analytics_snapshot_change_changes_record_fingerprint() -> None:
    source = complete_replay()
    links_a = links_for(source, snapshot_fingerprint="c" * 64)
    links_b = links_for(source, snapshot_fingerprint="e" * 64)

    _, first = one_record(source, links_a)
    _, second = one_record(source, links_b)

    assert first.record_id == second.record_id
    assert first.record_fingerprint != second.record_fingerprint


def test_specialist_orchestration_order_is_preserved() -> None:
    source = complete_replay()
    _, record = one_record(source)

    assert record.decision.professor_plan.selected_agents == ("berlin", "tokyo")
    assert tuple(run.agent_id for run in record.decision.specialists.runs) == (
        "berlin",
        "tokyo",
    )
    assert record.decision.trade_proposal.specialist_request_ids == (
        str(BERLIN_REQUEST),
        str(TOKYO_REQUEST),
    )


def _metric(value: Decimal | None, status: str = "AVAILABLE", reason=None):
    return SimpleNamespace(value=value, status=status, reason=reason)


def _evaluation_report() -> SimpleNamespace:
    trading = SimpleNamespace(
        executed_fill_count=1,
        executed_order_count=1,
        closed_trade_count=0,
        open_position_count=1,
        winning_trades=0,
        losing_trades=0,
        breakeven_trades=0,
        execution_realized_pnl=Decimal("0"),
        fees_paid=Decimal("0.10"),
        realized_trading_net=Decimal("-0.10"),
        slippage_cost=_metric(Decimal("0.05")),
        gross_pnl_before_costs=_metric(Decimal("0")),
        unrealized_pnl=_metric(Decimal("0")),
        trading_net=_metric(Decimal("-0.10")),
        gross_exposure=_metric(Decimal("50.05")),
        win_rate=_metric(None, "UNAVAILABLE", "NO_CLOSED_TRADES"),
        profit_factor=_metric(None, "UNAVAILABLE", "NO_CLOSED_TRADES"),
        expectancy=_metric(None, "UNAVAILABLE", "NO_CLOSED_TRADES"),
        max_drawdown_abs=_metric(Decimal("0.10")),
        max_drawdown_pct=_metric(Decimal("0.001")),
        closed_trades=(),
    )
    return SimpleNamespace(
        report_version="batch10.evaluation.v1",
        trading=trading,
        ai_costs=SimpleNamespace(
            total_cost_eur=Decimal("0.05"),
            by_agent={},
            by_model={},
            by_route={},
        ),
        agents=(),
        economic_net=_metric(Decimal("-0.15")),
        self_funding_ratio=SimpleNamespace(
            value=None,
            status="UNAVAILABLE",
            basis="TRADING_NET/AI_COST",
        ),
    )


def test_build_does_not_change_backtest_run_or_business_fingerprint() -> None:
    source = complete_replay()
    links = links_for(source)
    before = fingerprint_backtest(source, _evaluation_report())
    run_id = source.backtest_result.run.run_id

    built = build_decision_intelligence_record_set(source, analytics_links=links)
    source.decision_intelligence = built
    after = fingerprint_backtest(source, _evaluation_report())

    assert source.backtest_result.run.run_id == run_id
    assert before == after


def test_analytics_run_version_changes_decision_intelligence_not_business_run() -> None:
    source = complete_replay()
    baseline = fingerprint_backtest(source, _evaluation_report())
    run_id = source.backtest_result.run.run_id
    first = build_decision_intelligence_record_set(
        source,
        analytics_links=links_for(source, analytics_run_id="analytics-a"),
    )
    second = build_decision_intelligence_record_set(
        source,
        analytics_links=links_for(source, analytics_run_id="analytics-b"),
    )

    assert first.records[0].record_id != second.records[0].record_id
    assert first.set_fingerprint != second.set_fingerprint
    assert source.backtest_result.run.run_id == run_id
    assert fingerprint_backtest(source, _evaluation_report()) == baseline


def test_optional_decision_funnel_report_is_validation_only() -> None:
    source = complete_replay()
    run = source.backtest_result.run
    report = SimpleNamespace(
        run_id=run.run_id,
        dataset_id=run.dataset.dataset_id,
        dataset_version=run.dataset.version,
        system_id=run.config.system_id,
        counts=SimpleNamespace(candidate_opportunities=1),
    )
    result = build_decision_intelligence_record_set(
        source,
        analytics_links=links_for(source),
        decision_funnel_report=report,
    )

    assert result.record_count == 1
    assert "decision_funnel" not in result.records[0].model_dump(mode="python")


def test_french_dialogue_contract_is_preserved() -> None:
    assert AGENT_DIALOGUE_LANGUAGE == "fr-FR"
    assert AGENT_DIALOGUE_LANGUAGE_VERSION == "money-heist.agent-dialogue.fr.v1"
    assert PROMPT_TRANSPORT_VERSION == "money-heist.prompt-transport.v4"
