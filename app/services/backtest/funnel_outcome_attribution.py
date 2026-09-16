from __future__ import annotations

from typing import Any

from app.evaluation.funnel_outcome_attribution import (
    FunnelOutcomeAttributionReport,
    FunnelOutcomeSubject,
    aggregate_funnel_outcome_attribution,
)
from app.evaluation.forward_outcomes import ForwardOutcomeReport


def _value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _sorted_values(values: Any) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                text
                for item in tuple(values or ())
                if (text := _value(item)) is not None
            }
        )
    )


def _subject_from_point(point: Any) -> FunnelOutcomeSubject:
    opportunity = getattr(point, "opportunity", None)
    if opportunity is None:
        raise ValueError("attribution subjects require CandidateOpportunity points")

    pipeline_result = getattr(point, "pipeline_result", None)
    terminal_status = _value(getattr(pipeline_result, "status", None))
    if terminal_status is None:
        terminal_status = "MISSING_PIPELINE_RESULT"

    orchestration = getattr(pipeline_result, "orchestration_result", None)
    gate = getattr(orchestration, "compute_gate", None)
    professor_plan = getattr(orchestration, "professor_plan", None)
    professor_decision = getattr(orchestration, "professor_decision", None)
    proposal = getattr(orchestration, "trade_proposal", None)
    orchestration_failure = getattr(orchestration, "failure", None)

    risk_record = getattr(pipeline_result, "risk_record", None)
    risk_decision = getattr(risk_record, "decision", None)
    pipeline_failure = getattr(pipeline_result, "failure", None)

    feature = getattr(point, "feature_snapshot", None)
    return FunnelOutcomeSubject(
        opportunity_id=str(opportunity.opportunity_id),
        observed_at=point.observed_at,
        terminal_status=terminal_status,
        market_regime=_value(getattr(feature, "regime", None)),
        scanner_triggers=_sorted_values(getattr(opportunity, "triggers", ())),
        compute_gate_reason=_value(getattr(gate, "reason", None)),
        professor_plan_decision=_value(getattr(professor_plan, "decision", None)),
        selected_agents=_sorted_values(getattr(professor_plan, "selected_agents", ())),
        orchestration_failure_code=_value(
            getattr(orchestration_failure, "code", None)
        ),
        professor_direction=_value(
            getattr(professor_decision, "direction", None)
        ),
        proposal_side=_value(getattr(proposal, "side", None)),
        risk_status=_value(getattr(risk_decision, "status", None)),
        risk_reason_codes=_sorted_values(
            getattr(risk_decision, "reason_codes", ())
        ),
        paper_pipeline_failure_code=_value(
            getattr(pipeline_failure, "code", None)
        ),
    )


def build_funnel_outcome_attribution_report(
    replay_result: Any,
    decision_funnel: Any,
    forward_outcomes: ForwardOutcomeReport,
) -> FunnelOutcomeAttributionReport:
    """Build a post-hoc candidate-stage attribution report from existing outputs."""

    run = replay_result.backtest_result.run
    if forward_outcomes.run_id != run.run_id:
        raise ValueError("Forward Outcomes run_id does not match replay")
    if decision_funnel.run_id != run.run_id:
        raise ValueError("Decision Funnel run_id does not match replay")
    if forward_outcomes.dataset_id != run.dataset.dataset_id:
        raise ValueError("Forward Outcomes dataset_id does not match replay")
    if decision_funnel.dataset_id != run.dataset.dataset_id:
        raise ValueError("Decision Funnel dataset_id does not match replay")
    if forward_outcomes.system_id != run.config.system_id:
        raise ValueError("Forward Outcomes system_id does not match replay")
    if decision_funnel.system_id != run.config.system_id:
        raise ValueError("Decision Funnel system_id does not match replay")

    subjects = tuple(
        _subject_from_point(point)
        for point in replay_result.points
        if getattr(point, "opportunity", None) is not None
    )
    candidate_count = int(decision_funnel.counts.candidate_opportunities)
    return aggregate_funnel_outcome_attribution(
        forward_outcomes=forward_outcomes,
        subjects=subjects,
        candidate_opportunity_count=candidate_count,
    )


__all__ = [
    "FunnelOutcomeAttributionReport",
    "build_funnel_outcome_attribution_report",
]
