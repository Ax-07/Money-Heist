from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from .models import (
    DecisionFunnelCounts,
    DecisionFunnelObservationCounts,
    DecisionFunnelPostHoc,
    DecisionFunnelReasonCount,
    DecisionFunnelReport,
)


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    raw = _value(value)
    return str(raw)


def _bool_attr(value: Any, name: str, default: bool = False) -> bool:
    if value is None:
        return default
    raw = getattr(value, name, default)
    return bool(raw() if callable(raw) else raw)


def _reason(counter: Counter[tuple[str, str]], stage: str, code: str, amount: int = 1) -> None:
    if amount <= 0:
        return
    counter[(stage, code)] += amount


def aggregate_decision_funnel(
    *,
    run_id: str,
    dataset_id: str,
    dataset_version: str,
    system_id: str,
    period_start: datetime,
    period_end: datetime,
    candles_evaluated: int,
    observation_counts: DecisionFunnelObservationCounts,
    replay_points: Iterable[Any],
    closed_trades: int,
    broker_executions: Iterable[Any] = (),
) -> DecisionFunnelReport:
    """Build a read-only, deterministic funnel from outputs already emitted by the pipeline.

    This function never calls Scanner, agents, Risk, broker or lifecycle services. It only
    normalizes immutable replay/evaluation outputs after the decision path has completed.
    """

    points = tuple(replay_points)
    executions = tuple(broker_executions)
    reasons: Counter[tuple[str, str]] = Counter()

    if observation_counts.pre_scanner_warmup_skipped:
        _reason(
            reasons,
            "REPLAY",
            "WARMUP_INCOMPLETE",
            observation_counts.pre_scanner_warmup_skipped,
        )
    if observation_counts.pre_scanner_not_decision_close_skipped:
        _reason(
            reasons,
            "REPLAY",
            "NOT_DECISION_TIMEFRAME_CLOSE",
            observation_counts.pre_scanner_not_decision_close_skipped,
        )

    scanner_no_trigger = 0
    scanner_triggered = 0
    candidate_opportunities = 0
    compute_gate_allowed = 0
    compute_gate_blocked = 0
    ai_orchestrations_triggered = 0
    professor_plan_no_analysis = 0
    orchestration_failed = 0
    professor_no_trade = 0
    trade_proposals_created = 0
    risk_rejected = 0
    risk_resized = 0
    risk_approved = 0
    paper_pipeline_failed = 0
    duplicate_execution_blocked = 0
    orders_submitted = 0
    fills = 0

    for point in points:
        scan_result = getattr(point, "scan_result", None)
        triggers = tuple(getattr(scan_result, "triggers", ()) or ())
        opportunity = getattr(point, "opportunity", None)
        if opportunity is None and scan_result is not None:
            opportunity = getattr(scan_result, "opportunity", None)

        if triggers:
            scanner_triggered += 1
        else:
            scanner_no_trigger += 1
            _reason(reasons, "SCANNER", "NO_TRIGGER")

        if opportunity is None:
            if triggers:
                _reason(reasons, "SCANNER", "TRIGGER_BELOW_CANDIDATE_THRESHOLD")
            continue

        candidate_opportunities += 1
        pipeline_result = getattr(point, "pipeline_result", None)
        if pipeline_result is None:
            _reason(reasons, "REPLAY", "PIPELINE_RESULT_MISSING")
            continue

        orchestration = getattr(pipeline_result, "orchestration_result", None)
        if orchestration is not None:
            gate = getattr(orchestration, "compute_gate", None)
            if gate is not None:
                allows_ai = _bool_attr(gate, "allows_ai")
                gate_reason = _text(getattr(gate, "reason", None)) or "UNKNOWN"
                _reason(reasons, "COMPUTE_GATE", gate_reason)
                if allows_ai:
                    compute_gate_allowed += 1
                else:
                    compute_gate_blocked += 1

            failure = getattr(orchestration, "failure", None)
            failure_stage = _text(getattr(failure, "stage", None)) if failure is not None else None
            if (
                gate is not None
                and _bool_attr(gate, "allows_ai")
                and failure_stage != "specialist_contexts"
            ):
                ai_orchestrations_triggered += 1

            professor_plan = getattr(orchestration, "professor_plan", None)
            if _text(getattr(professor_plan, "decision", None)) == "NO_ANALYSIS":
                professor_plan_no_analysis += 1
                _reason(reasons, "PROFESSOR_PLAN", "NO_ANALYSIS")

            orchestration_status = _text(getattr(orchestration, "status", None))
            if orchestration_status == "FAILED":
                orchestration_failed += 1
            if failure is not None:
                _reason(
                    reasons,
                    "ORCHESTRATION",
                    _text(getattr(failure, "code", None)) or "UNKNOWN",
                )

            professor_decision = getattr(orchestration, "professor_decision", None)
            if _text(getattr(professor_decision, "direction", None)) == "NO_TRADE":
                professor_no_trade += 1
                _reason(reasons, "PROFESSOR_FINAL", "NO_TRADE")

            if getattr(orchestration, "trade_proposal", None) is not None:
                trade_proposals_created += 1

        risk_record = getattr(pipeline_result, "risk_record", None)
        risk_decision = getattr(risk_record, "decision", None) if risk_record is not None else None
        if risk_decision is not None:
            risk_status = _text(getattr(risk_decision, "status", None))
            if risk_status == "REJECTED":
                risk_rejected += 1
            elif risk_status == "RESIZED":
                risk_resized += 1
            elif risk_status == "APPROVED":
                risk_approved += 1
            for code in tuple(getattr(risk_decision, "reason_codes", ()) or ()):
                _reason(reasons, "RISK", _text(code) or "UNKNOWN")

        pipeline_status = _text(getattr(pipeline_result, "status", None))
        if pipeline_status == "FAILED":
            paper_pipeline_failed += 1
        elif pipeline_status == "DUPLICATE_BLOCKED":
            duplicate_execution_blocked += 1

        pipeline_failure = getattr(pipeline_result, "failure", None)
        if pipeline_failure is not None:
            _reason(
                reasons,
                "PAPER_PIPELINE",
                _text(getattr(pipeline_failure, "code", None)) or "UNKNOWN",
            )

        if getattr(pipeline_result, "order", None) is not None:
            orders_submitted += 1
        if getattr(pipeline_result, "fill", None) is not None:
            fills += 1

    reason_counts = tuple(
        DecisionFunnelReasonCount(stage=stage, code=code, count=count)
        for (stage, code), count in sorted(reasons.items())
    )
    broker_order_ids = {
        str(getattr(execution, "broker_order_id", ""))
        for execution in executions
        if getattr(execution, "broker_order_id", None) is not None
    }

    return DecisionFunnelReport(
        run_id=run_id,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        system_id=system_id,
        period_start=period_start,
        period_end=period_end,
        observation_counts=observation_counts,
        counts=DecisionFunnelCounts(
            candles_evaluated=candles_evaluated,
            scanner_evaluations=len(points),
            scanner_no_trigger=scanner_no_trigger,
            scanner_triggered=scanner_triggered,
            candidate_opportunities=candidate_opportunities,
            compute_gate_allowed=compute_gate_allowed,
            compute_gate_blocked=compute_gate_blocked,
            ai_orchestrations_triggered=ai_orchestrations_triggered,
            professor_plan_no_analysis=professor_plan_no_analysis,
            orchestration_failed=orchestration_failed,
            professor_no_trade=professor_no_trade,
            trade_proposals_created=trade_proposals_created,
            risk_rejected=risk_rejected,
            risk_resized=risk_resized,
            risk_approved=risk_approved,
            paper_pipeline_failed=paper_pipeline_failed,
            duplicate_execution_blocked=duplicate_execution_blocked,
            orders_submitted=orders_submitted,
            fills=fills,
        ),
        reason_counts=reason_counts,
        post_hoc=DecisionFunnelPostHoc(
            closed_trades=closed_trades,
            broker_orders_total=len(broker_order_ids),
            broker_fills_total=len(executions),
        ),
    )
