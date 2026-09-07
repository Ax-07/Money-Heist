import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.evaluation import EvaluationService
from app.evaluation.adapters import (
    build_evaluation_source,
    execution_records_from_paper,
    trace_from_paper_pipeline,
    traces_from_paper_events,
    usage_from_ai_gateway,
)
from app.evaluation.exports import agent_metrics_to_csv, report_to_json


NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


def enum(value):
    return SimpleNamespace(value=value)


def test_current_ai_gateway_shape_is_normalized() -> None:
    request_id = uuid4()
    record = SimpleNamespace(
        request_id=request_id,
        agent_id="berlin",
        route_id="specialist_standard",
        model_id="gpt-x",
        estimated_cost=Decimal("0.012"),
        latency_ms=123,
        attempt=1,
        created_at=NOW,
    )
    normalized = usage_from_ai_gateway(record)
    assert normalized.request_id == str(request_id)
    assert normalized.estimated_cost_eur == Decimal("0.012")
    assert normalized.route_id == "specialist_standard"


def test_paper_orders_and_fills_reconstruct_configured_market_slippage() -> None:
    order = SimpleNamespace(
        broker_order_id="o1",
        system_id="balanced_v1",
        symbol="BTCUSDT",
        side=enum("BUY"),
        order_type=enum("MARKET"),
    )
    fill = SimpleNamespace(
        fill_id="f1",
        broker_order_id="o1",
        price=Decimal("100.05"),
        quantity=Decimal("1"),
        fee=Decimal("0.1"),
        filled_at=NOW,
    )
    records = execution_records_from_paper(
        orders=(order,), fills=(fill,), market_slippage_bps=Decimal("5")
    )
    assert records[0].slippage_cost == Decimal("0.05")


def test_full_batch09_chain_is_preserved_in_trace() -> None:
    prof_request = uuid4()
    ber_request = uuid4()
    pal_request = uuid4()
    proposal_id = uuid4()
    risk_id = uuid4()

    calls = (
        SimpleNamespace(
            request_id=prof_request,
            agent_id="professor",
            phase="finalize",
            prompt_version="professor.v3",
            route_id="professor_route",
            model_id="model-pro",
        ),
        SimpleNamespace(
            request_id=ber_request,
            agent_id="berlin",
            phase="specialist",
            prompt_version="berlin.v2",
            route_id="mini",
            model_id="model-mini",
        ),
    )
    orchestration = SimpleNamespace(
        system_id="balanced_v1",
        agent_calls=calls,
        specialist_runs=(
            SimpleNamespace(
                request_id=ber_request,
                agent_id="berlin",
                analysis=SimpleNamespace(stance=enum("LONG"), confidence=0.8),
            ),
        ),
        palermo_run=SimpleNamespace(
            request_id=pal_request,
            review=SimpleNamespace(verdict="CAUTION", severity=0.6),
        ),
        professor_decision=SimpleNamespace(direction="LONG", confidence=0.75),
        trade_proposal=SimpleNamespace(proposal_id=proposal_id, professor_request_id=prof_request),
    )
    result = SimpleNamespace(
        opportunity_id="opp-1",
        source_snapshot_id="snap-1",
        orchestration_result=orchestration,
        risk_record=SimpleNamespace(
            risk_decision_id=risk_id,
            decision=SimpleNamespace(status=enum("RESIZED")),
        ),
        order_intent=SimpleNamespace(mode="PAPER"),
        order=SimpleNamespace(broker_order_id="order-1"),
        fill=SimpleNamespace(fill_id="fill-1"),
    )

    trace = trace_from_paper_pipeline(result)
    assert trace.opportunity_id == "opp-1"
    assert trace.proposal_id == str(proposal_id)
    assert trace.risk_decision_id == str(risk_id)
    assert trace.risk_status == "RESIZED"
    assert trace.broker_order_id == "order-1"
    assert trace.fill_id == "fill-1"
    assert "professor.v3" in trace.prompt_versions
    assert "berlin.v2" in trace.prompt_versions
    assert trace.observations[0].stance == "LONG"


def test_json_and_csv_exports_are_simple_and_testable() -> None:
    report = EvaluationService().evaluate(build_evaluation_source())
    payload = json.loads(report_to_json(report))
    assert payload["report_version"] == "batch10.evaluation.v1"
    csv_text = agent_metrics_to_csv(report.agents)
    assert csv_text.startswith("agent_id,call_count,attempt_count")


def test_batch09_audit_events_can_rebuild_ids_without_inventing_agent_details() -> None:
    events = (
        SimpleNamespace(
            sequence=1,
            stage="orchestration",
            opportunity_id="opp-events",
            proposal_id=None,
            source_snapshot_id="snap-events",
            created_at=NOW,
            details={
                "professor_direction": "LONG",
                "agent_request_ids": "request-a,request-b",
            },
        ),
        SimpleNamespace(
            sequence=2,
            stage="trade_proposal",
            opportunity_id="opp-events",
            proposal_id="proposal-events",
            source_snapshot_id="snap-events",
            created_at=NOW,
            details={"professor_prompt_version": "professor.v4"},
        ),
        SimpleNamespace(
            sequence=3,
            stage="risk_engine",
            opportunity_id="opp-events",
            proposal_id="proposal-events",
            source_snapshot_id="snap-events",
            created_at=NOW,
            details={"risk_decision_id": "risk-events", "risk_status": "APPROVED"},
        ),
        SimpleNamespace(
            sequence=4,
            stage="paper_execution",
            opportunity_id="opp-events",
            proposal_id="proposal-events",
            source_snapshot_id="snap-events",
            created_at=NOW,
            details={"broker_order_id": "order-events", "fill_id": "fill-events"},
        ),
    )

    trace = traces_from_paper_events(events)[0]
    assert trace.opportunity_id == "opp-events"
    assert trace.proposal_id == "proposal-events"
    assert trace.risk_decision_id == "risk-events"
    assert trace.broker_order_id == "order-events"
    assert trace.fill_id == "fill-events"
    assert trace.agent_request_ids == ("request-a", "request-b")
    assert trace.prompt_versions == ("professor.v4",)
    assert trace.agent_calls == ()
    assert trace.observations == ()
