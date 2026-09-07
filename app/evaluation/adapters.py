from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from .models import (
    AgentCallEntry,
    AgentObservation,
    AIUsageEntry,
    CounterfactualOutcome,
    EquityPoint,
    EvaluationSource,
    ExecutionRecord,
    OpportunityTrace,
    ZERO,
)

BPS_DENOMINATOR = Decimal("10000")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


def usage_from_ai_gateway(record: Any) -> AIUsageEntry:
    """Normalize the current Batch 06 AIUsageRecord without changing that contract."""

    return AIUsageEntry(
        request_id=str(record.request_id),
        agent_id=str(record.agent_id),
        route_id=str(record.route_id),
        model_id=str(record.model_id),
        estimated_cost_eur=Decimal(str(record.estimated_cost)),
        latency_ms=int(record.latency_ms) if record.latency_ms is not None else None,
        attempt=int(record.attempt),
        created_at=getattr(record, "created_at", None),
    )


def execution_records_from_paper(
    *,
    orders: Iterable[Any],
    fills: Iterable[Any],
    market_slippage_bps: Decimal | None,
) -> tuple[ExecutionRecord, ...]:
    """Join public PaperBroker orders/fills into deterministic evaluation records."""

    order_by_id = {str(order.broker_order_id): order for order in orders}
    records = []
    for fill in fills:
        order = order_by_id.get(str(fill.broker_order_id))
        if order is None:
            raise ValueError(f"fill {fill.fill_id} has no matching broker order")

        order_type = _text(order.order_type)
        side = _text(order.side)
        if order_type == "LIMIT":
            slippage = ZERO
        elif order_type == "MARKET":
            slippage = _market_slippage_cost(
                side=side,
                fill_price=Decimal(str(fill.price)),
                quantity=Decimal(str(fill.quantity)),
                market_slippage_bps=market_slippage_bps,
            )
        else:
            raise ValueError(f"unsupported paper order type: {order_type}")

        records.append(
            ExecutionRecord(
                fill_id=str(fill.fill_id),
                broker_order_id=str(fill.broker_order_id),
                system_id=str(order.system_id),
                symbol=str(order.symbol),
                side=str(side),
                order_type=str(order_type),
                quantity=Decimal(str(fill.quantity)),
                price=Decimal(str(fill.price)),
                fee=Decimal(str(fill.fee)),
                filled_at=fill.filled_at,
                slippage_cost=slippage,
            )
        )
    return tuple(records)


def _market_slippage_cost(
    *,
    side: str | None,
    fill_price: Decimal,
    quantity: Decimal,
    market_slippage_bps: Decimal | None,
) -> Decimal | None:
    if market_slippage_bps is None:
        return None
    if market_slippage_bps < ZERO:
        raise ValueError("market_slippage_bps must be >= 0")
    rate = market_slippage_bps / BPS_DENOMINATOR
    if side == "BUY":
        reference_mark = fill_price / (Decimal("1") + rate)
        return (fill_price - reference_mark) * quantity
    if side == "SELL":
        if rate >= Decimal("1"):
            raise ValueError("SELL slippage rate must be < 100%")
        reference_mark = fill_price / (Decimal("1") - rate)
        return (reference_mark - fill_price) * quantity
    raise ValueError(f"unsupported order side: {side}")


def trace_from_paper_pipeline(result: Any) -> OpportunityTrace:
    """Normalize Batch 09 result/audit into a read-only evaluation trace."""

    orchestration = getattr(result, "orchestration_result", None)
    proposal = getattr(orchestration, "trade_proposal", None) if orchestration is not None else None
    professor_decision = (
        getattr(orchestration, "professor_decision", None) if orchestration is not None else None
    )
    final_decision = _text(getattr(professor_decision, "direction", None))

    calls = []
    raw_calls = tuple(getattr(orchestration, "agent_calls", ()) or ()) if orchestration else ()
    for call in raw_calls:
        calls.append(
            AgentCallEntry(
                request_id=str(call.request_id),
                agent_id=str(call.agent_id),
                opportunity_id=str(result.opportunity_id),
                phase=str(call.phase),
                prompt_version=str(call.prompt_version) if call.prompt_version else None,
                route_id=str(call.route_id) if call.route_id else None,
                model_id=str(call.model_id) if call.model_id else None,
            )
        )

    observations = []
    if orchestration is not None:
        for run in tuple(getattr(orchestration, "specialist_runs", ()) or ()):
            analysis = run.analysis
            observations.append(
                AgentObservation(
                    request_id=str(run.request_id),
                    agent_id=str(run.agent_id),
                    opportunity_id=str(result.opportunity_id),
                    phase="specialist",
                    stance=_text(getattr(analysis, "stance", None)),
                    confidence=Decimal(str(analysis.confidence)),
                    final_decision=final_decision,
                )
            )

        palermo = getattr(orchestration, "palermo_run", None)
        if palermo is not None:
            observations.append(
                AgentObservation(
                    request_id=str(palermo.request_id),
                    agent_id="palermo",
                    opportunity_id=str(result.opportunity_id),
                    phase="red_team",
                    stance=_text(getattr(palermo.review, "verdict", None)),
                    confidence=None,
                    final_decision=final_decision,
                )
            )

        if professor_decision is not None:
            professor_request_id = _professor_final_request_id(proposal, raw_calls)
            if professor_request_id is not None:
                observations.append(
                    AgentObservation(
                        request_id=professor_request_id,
                        agent_id="professor",
                        opportunity_id=str(result.opportunity_id),
                        phase="final_decision",
                        stance=final_decision,
                        confidence=Decimal(str(professor_decision.confidence)),
                        final_decision=final_decision,
                    )
                )

    risk_record = getattr(result, "risk_record", None)
    risk_decision_id = (
        str(risk_record.risk_decision_id) if risk_record is not None else None
    )
    risk_status = (
        _text(getattr(risk_record.decision, "status", None)) if risk_record is not None else None
    )
    order = getattr(result, "order", None)
    fill = getattr(result, "fill", None)
    order_intent = getattr(result, "order_intent", None)
    if order_intent is not None and getattr(order_intent, "mode", "PAPER") != "PAPER":
        raise ValueError("Batch 10 evaluation trace accepts PAPER execution only")

    prompt_versions = tuple(
        sorted({call.prompt_version for call in calls if call.prompt_version is not None})
    )
    return OpportunityTrace(
        opportunity_id=str(result.opportunity_id),
        source_snapshot_id=str(result.source_snapshot_id),
        system_id=(str(orchestration.system_id) if orchestration is not None else None),
        final_decision=final_decision,
        proposal_id=(str(proposal.proposal_id) if proposal is not None else None),
        risk_decision_id=risk_decision_id,
        risk_status=risk_status,
        broker_order_id=(str(order.broker_order_id) if order is not None else None),
        fill_id=(str(fill.fill_id) if fill is not None else None),
        prompt_versions=prompt_versions,
        agent_calls=tuple(calls),
        observations=tuple(observations),
        agent_request_ids=tuple(str(call.request_id) for call in raw_calls),
    )


def traces_from_paper_events(events: Iterable[Any]) -> tuple[OpportunityTrace, ...]:
    """Rebuild trace IDs from Batch 09 audit hooks when rich results are unavailable.

    The event contract does not identify each specialist beside its request ID, so this
    adapter preserves the request IDs for cost attribution but does not invent agent calls
    or specialist observations.
    """

    grouped: dict[str, list[Any]] = {}
    for event in events:
        opportunity_id = str(event.opportunity_id)
        grouped.setdefault(opportunity_id, []).append(event)

    traces = []
    for opportunity_id, opportunity_events in sorted(grouped.items()):
        ordered = sorted(opportunity_events, key=lambda item: (item.sequence, item.created_at))
        first = ordered[0]
        final_decision = None
        proposal_id = None
        risk_decision_id = None
        risk_status = None
        broker_order_id = None
        fill_id = None
        prompt_versions: set[str] = set()
        request_ids: set[str] = set()

        for event in ordered:
            details = dict(getattr(event, "details", {}) or {})
            if getattr(event, "proposal_id", None) is not None:
                proposal_id = str(event.proposal_id)
            if event.stage == "orchestration":
                direction = details.get("professor_direction")
                if direction:
                    final_decision = direction
                raw_ids = details.get("agent_request_ids", "")
                request_ids.update(item for item in raw_ids.split(",") if item)
            elif event.stage == "trade_proposal":
                version = details.get("professor_prompt_version")
                if version:
                    prompt_versions.add(version)
            elif event.stage == "risk_engine":
                risk_decision_id = details.get("risk_decision_id") or risk_decision_id
                risk_status = details.get("risk_status") or risk_status
            elif event.stage == "paper_execution":
                broker_order_id = details.get("broker_order_id") or broker_order_id
                fill_id = details.get("fill_id") or fill_id

        traces.append(
            OpportunityTrace(
                opportunity_id=opportunity_id,
                source_snapshot_id=str(first.source_snapshot_id),
                system_id=None,
                final_decision=final_decision,
                proposal_id=proposal_id,
                risk_decision_id=risk_decision_id,
                risk_status=risk_status,
                broker_order_id=broker_order_id,
                fill_id=fill_id,
                prompt_versions=tuple(sorted(prompt_versions)),
                agent_request_ids=tuple(sorted(request_ids)),
            )
        )
    return tuple(traces)


def _professor_final_request_id(proposal: Any, calls: tuple[Any, ...]) -> str | None:
    if proposal is not None and getattr(proposal, "professor_request_id", None) is not None:
        return str(proposal.professor_request_id)
    professor_calls = [call for call in calls if str(call.agent_id) == "professor"]
    if not professor_calls:
        return None
    final_calls = [call for call in professor_calls if "final" in str(call.phase).lower()]
    return str((final_calls or professor_calls)[-1].request_id)


def build_evaluation_source(
    *,
    orders: Iterable[Any] = (),
    fills: Iterable[Any] = (),
    pipeline_results: Iterable[Any] = (),
    paper_events: Iterable[Any] = (),
    ai_usage_records: Iterable[Any] = (),
    marks: Mapping[str, Decimal] | None = None,
    market_slippage_bps: Decimal | None = None,
    equity_points: Iterable[EquityPoint] = (),
    counterfactual_outcomes: Iterable[CounterfactualOutcome] = (),
) -> EvaluationSource:
    """Build a rebuildable source from existing Batch 06/09 data without mutating either."""

    rich_traces = tuple(trace_from_paper_pipeline(item) for item in pipeline_results)
    seen_opportunities = {trace.opportunity_id for trace in rich_traces}
    event_traces = tuple(
        trace
        for trace in traces_from_paper_events(paper_events)
        if trace.opportunity_id not in seen_opportunities
    )

    return EvaluationSource(
        executions=execution_records_from_paper(
            orders=orders,
            fills=fills,
            market_slippage_bps=market_slippage_bps,
        ),
        marks=dict(marks or {}),
        equity_points=tuple(equity_points),
        ai_usage=tuple(usage_from_ai_gateway(item) for item in ai_usage_records),
        opportunity_traces=rich_traces + event_traces,
        counterfactual_outcomes=tuple(counterfactual_outcomes),
    )
