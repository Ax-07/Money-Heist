from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import Enum
from typing import Any

from app.common.canonical import stable_digest, stable_uuid
from app.evaluation.decision_intelligence.models import (
    DecisionIntelligenceRecord,
    DecisionIntelligenceRecordSet,
)

from .funnel_stage_models import (
    FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_POLICY_VERSION,
    FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_SCHEMA_VERSION,
    FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_SET_SCHEMA_VERSION,
    FunnelStage,
    FunnelStageAnalyticsAttributionRecord,
    FunnelStageAnalyticsAttributionSet,
)

_STAGE_ORDER = {
    FunnelStage.COMPUTE_GATE: 10,
    FunnelStage.PROFESSOR_PLAN: 20,
    FunnelStage.SPECIALIST: 30,
    FunnelStage.PALERMO: 40,
    FunnelStage.PROFESSOR_FINAL: 50,
    FunnelStage.TRADE_PROPOSAL: 60,
    FunnelStage.RISK: 70,
    FunnelStage.PAPER: 80,
}


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _text(value: Any | None) -> str | None:
    if value is None:
        return None
    return str(_value(value))


def _texts(values: Iterable[Any] | None) -> tuple[str, ...]:
    return tuple(str(_value(item)) for item in (values or ()))


def _plain(value: Any) -> Any:
    """Return canonical-friendly material without recomputing business artifacts."""
    if value is None or isinstance(value, (str, int, float, bool, datetime, Enum)):
        return value
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return tuple(_plain(item) for item in value)
    if hasattr(value, "__dict__"):
        return {
            str(key): _plain(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    return value


def _projection_fingerprint(value: Any) -> str:
    return stable_digest(_plain(value))


def _trace_status(traces: Iterable[Any], *stage_names: str) -> str | None:
    names = set(stage_names)
    matches = tuple(
        _text(getattr(item, "status", None))
        for item in traces
        if str(getattr(item, "stage", "")) in names
    )
    return matches[-1] if matches else None


def _failure_fields(failure: Any | None) -> dict[str, str | None]:
    if failure is None:
        return {
            "failure_code": None,
            "failure_stage": None,
            "failure_agent_id": None,
        }
    return {
        "failure_code": _text(getattr(failure, "code", None)),
        "failure_stage": _text(getattr(failure, "stage", None)),
        "failure_agent_id": _text(getattr(failure, "agent_id", None)),
    }


def _matching_orchestration_failure(
    record: DecisionIntelligenceRecord,
    *,
    stage_names: tuple[str, ...],
    reached: bool,
) -> Any | None:
    if not reached:
        return None
    failure = record.decision.orchestration_failure
    if failure is None:
        return None
    failure_stage = str(getattr(failure, "stage", ""))
    return failure if failure_stage in set(stage_names) else None


def _analytics_fields(record: DecisionIntelligenceRecord) -> dict[str, Any]:
    analytics = record.analytics
    if analytics.analytics_run_id != record.analytics_run_id:
        raise ValueError("Decision Intelligence AnalyticsRun identity mismatch")
    return {
        "analytics_link_id": analytics.link_id,
        "analytics_link_fingerprint": analytics.link_fingerprint,
        "analytics_link_policy_version": analytics.link_policy_version,
        "analytics_link_status": analytics.status,
        "analytics_snapshot_id": analytics.analytics_snapshot_id,
        "analytics_snapshot_fingerprint": analytics.analytics_snapshot_fingerprint,
        "analytics_as_of": analytics.analytics_as_of,
        "source_cursor_fingerprint": analytics.source_cursor_fingerprint,
        "analytics_snapshot_source_cursor_fingerprint": (
            analytics.analytics_snapshot_source_cursor_fingerprint
        ),
        "analytics_diagnostics": tuple(analytics.diagnostics),
    }


def _make_record(
    *,
    source: DecisionIntelligenceRecord,
    stage: FunnelStage,
    source_projection_path: str,
    source_projection: Any,
    reached: bool,
    stage_status: str | None = None,
    stage_result: str | None = None,
    reason_codes: tuple[str, ...] = (),
    selected_agents: tuple[str, ...] = (),
    confidence: float | None = None,
    severity: float | None = None,
    failure: Any | None = None,
    source_artifact_ref: str | None = None,
    operational_at: datetime | None = None,
    stage_instance_id: str | None = None,
    stage_instance_order: int | None = None,
    agent_id: str | None = None,
    agent_request_id: str | None = None,
    agent_prompt_version: str | None = None,
    agent_route_id: str | None = None,
    agent_model_id: str | None = None,
) -> FunnelStageAnalyticsAttributionRecord:
    analytics = _analytics_fields(source)
    identity_payload = {
        "schema": FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_SCHEMA_VERSION,
        "policy": FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_POLICY_VERSION,
        "source_backtest_run_id": source.source_backtest_run_id,
        "analytics_run_id": source.analytics_run_id,
        "decision_intelligence_record_id": source.record_id,
        "opportunity_id": source.opportunity_id,
        "stage": stage,
        "stage_instance_id": stage_instance_id,
    }
    source_projection_fingerprint = _projection_fingerprint(source_projection)
    material_payload = {
        **identity_payload,
        "stage_order": _STAGE_ORDER[stage],
        "stage_instance_order": stage_instance_order,
        "agent_id": agent_id,
        "agent_request_id": agent_request_id,
        "agent_prompt_version": agent_prompt_version,
        "agent_route_id": agent_route_id,
        "agent_model_id": agent_model_id,
        "reached": reached,
        "stage_status": stage_status,
        "stage_result": stage_result,
        "reason_codes": reason_codes,
        "selected_agents": selected_agents,
        "confidence": confidence,
        "severity": severity,
        "failure": _failure_fields(failure),
        "source_projection_path": source_projection_path,
        "source_projection_fingerprint": source_projection_fingerprint,
        "source_artifact_ref": source_artifact_ref,
        "market_as_of": source.observed_at,
        "operational_at": operational_at,
        "analytics": analytics,
    }
    return FunnelStageAnalyticsAttributionRecord(
        record_id=stable_uuid("funnel-stage-analytics-attribution", identity_payload),
        record_fingerprint=stable_digest(material_payload),
        source_backtest_run_id=source.source_backtest_run_id,
        analytics_run_id=source.analytics_run_id,
        decision_intelligence_record_id=source.record_id,
        decision_intelligence_record_fingerprint=source.record_fingerprint,
        opportunity_id=source.opportunity_id,
        system_id=source.system_id,
        symbol=source.symbol,
        decision_timeframe=source.decision_timeframe,
        stage=stage,
        stage_order=_STAGE_ORDER[stage],
        stage_instance_id=stage_instance_id,
        stage_instance_order=stage_instance_order,
        agent_id=agent_id,
        agent_request_id=agent_request_id,
        agent_prompt_version=agent_prompt_version,
        agent_route_id=agent_route_id,
        agent_model_id=agent_model_id,
        reached=reached,
        stage_status=stage_status,
        stage_result=stage_result,
        reason_codes=reason_codes,
        selected_agents=selected_agents,
        confidence=confidence,
        severity=severity,
        **_failure_fields(failure),
        source_projection_path=source_projection_path,
        source_projection_fingerprint=source_projection_fingerprint,
        source_artifact_ref=source_artifact_ref,
        source_artifact_fingerprint=None,
        market_as_of=source.observed_at,
        operational_at=operational_at,
        **analytics,
    )


def _compute_gate_record(
    source: DecisionIntelligenceRecord,
) -> FunnelStageAnalyticsAttributionRecord:
    projection = source.decision.compute_gate
    status = _trace_status(source.decision.orchestration_stages, "compute_gate")
    return _make_record(
        source=source,
        stage=FunnelStage.COMPUTE_GATE,
        source_projection_path="decision.compute_gate",
        source_projection=projection,
        reached=projection.reached,
        stage_status=status,
        stage_result=_text(projection.level) if projection.reached else None,
        reason_codes=(str(projection.reason),)
        if projection.reached and projection.reason is not None
        else (),
    )


def _professor_plan_record(
    source: DecisionIntelligenceRecord,
) -> FunnelStageAnalyticsAttributionRecord:
    projection = source.decision.professor_plan
    failure = _matching_orchestration_failure(
        source,
        stage_names=("professor_plan",),
        reached=projection.reached,
    )
    call = projection.call
    return _make_record(
        source=source,
        stage=FunnelStage.PROFESSOR_PLAN,
        source_projection_path="decision.professor_plan",
        source_projection=projection,
        reached=projection.reached,
        stage_status=projection.stage_status,
        stage_result=projection.decision if projection.reached else None,
        selected_agents=tuple(projection.selected_agents) if projection.reached else (),
        failure=failure,
        source_artifact_ref=(call.request_id if projection.reached and call is not None else None),
    )


def _specialist_records(
    source: DecisionIntelligenceRecord,
) -> tuple[FunnelStageAnalyticsAttributionRecord, ...]:
    projection = source.decision.specialists
    if not projection.reached:
        return ()

    selected = tuple(projection.selected_agents)
    if len(set(selected)) != len(selected):
        raise ValueError("Decision Intelligence specialists contain duplicate selected agents")

    runs_by_agent: dict[str, Any] = {}
    request_ids: set[str] = set()
    for run in projection.runs:
        agent_id = str(run.agent_id)
        request_id = str(run.request_id)
        if agent_id in runs_by_agent:
            raise ValueError("Decision Intelligence specialists contain duplicate run agent")
        if request_id in request_ids:
            raise ValueError("Decision Intelligence specialists contain duplicate request_id")
        request_ids.add(request_id)
        runs_by_agent[agent_id] = run
        if agent_id not in selected:
            raise ValueError("Decision Intelligence specialist run was not selected")

    failure = projection.failure
    failed_agent = (
        str(failure.agent_id)
        if failure is not None and getattr(failure, "agent_id", None) is not None
        else None
    )
    if failed_agent is not None and failed_agent not in selected:
        raise ValueError("Decision Intelligence specialist failure was not selected")

    records: list[FunnelStageAnalyticsAttributionRecord] = []
    for order, agent_id in enumerate(selected):
        run = runs_by_agent.get(agent_id)
        if run is not None:
            analysis = run.analysis
            records.append(
                _make_record(
                    source=source,
                    stage=FunnelStage.SPECIALIST,
                    source_projection_path=(
                        f"decision.specialists.runs[{agent_id}]"
                    ),
                    source_projection=run,
                    reached=True,
                    stage_status="COMPLETED",
                    stage_result=_text(getattr(analysis, "stance", None)),
                    confidence=getattr(analysis, "confidence", None),
                    source_artifact_ref=str(run.request_id),
                    stage_instance_id=agent_id,
                    stage_instance_order=order,
                    agent_id=agent_id,
                    agent_request_id=str(run.request_id),
                    agent_prompt_version=str(run.prompt_version),
                    agent_route_id=str(run.route_id),
                    agent_model_id=str(run.model_id),
                )
            )
            continue
        if failure is not None and failed_agent == agent_id:
            records.append(
                _make_record(
                    source=source,
                    stage=FunnelStage.SPECIALIST,
                    source_projection_path=(
                        f"decision.specialists.failure[{agent_id}]"
                    ),
                    source_projection={"agent_id": agent_id, "failure": _plain(failure)},
                    reached=True,
                    stage_status="FAILED",
                    failure=failure,
                    stage_instance_id=agent_id,
                    stage_instance_order=order,
                    agent_id=agent_id,
                )
            )
    return tuple(records)


def _palermo_record(
    source: DecisionIntelligenceRecord,
) -> FunnelStageAnalyticsAttributionRecord:
    projection = source.decision.palermo
    failure = _matching_orchestration_failure(
        source,
        stage_names=("palermo_red_team",),
        reached=projection.reached,
    )
    return _make_record(
        source=source,
        stage=FunnelStage.PALERMO,
        source_projection_path="decision.palermo",
        source_projection=projection,
        reached=projection.reached,
        stage_status=projection.stage_status,
        stage_result=projection.verdict if projection.reached else None,
        severity=projection.severity if projection.reached else None,
        failure=failure,
        source_artifact_ref=(
            projection.request_id if projection.reached else None
        ),
    )


def _professor_final_record(
    source: DecisionIntelligenceRecord,
) -> FunnelStageAnalyticsAttributionRecord:
    projection = source.decision.professor_final
    failure = _matching_orchestration_failure(
        source,
        stage_names=("professor_finalize",),
        reached=projection.reached,
    )
    call = projection.call
    return _make_record(
        source=source,
        stage=FunnelStage.PROFESSOR_FINAL,
        source_projection_path="decision.professor_final",
        source_projection=projection,
        reached=projection.reached,
        stage_status=projection.stage_status,
        stage_result=projection.direction if projection.reached else None,
        confidence=projection.confidence if projection.reached else None,
        failure=failure,
        source_artifact_ref=(call.request_id if projection.reached and call is not None else None),
    )


def _trade_proposal_record(
    source: DecisionIntelligenceRecord,
) -> FunnelStageAnalyticsAttributionRecord:
    projection = source.decision.trade_proposal
    return _make_record(
        source=source,
        stage=FunnelStage.TRADE_PROPOSAL,
        source_projection_path="decision.trade_proposal",
        source_projection=projection,
        reached=projection.reached,
        stage_status=projection.stage_status,
        stage_result=projection.side if projection.reached else None,
        confidence=projection.confidence if projection.reached else None,
        source_artifact_ref=(projection.proposal_id if projection.reached else None),
        operational_at=(projection.created_at if projection.reached else None),
    )


def _risk_record(
    source: DecisionIntelligenceRecord,
) -> FunnelStageAnalyticsAttributionRecord:
    projection = source.decision.risk
    return _make_record(
        source=source,
        stage=FunnelStage.RISK,
        source_projection_path="decision.risk",
        source_projection=projection,
        reached=projection.reached,
        stage_status=projection.stage_status,
        stage_result=projection.status if projection.reached else None,
        reason_codes=tuple(projection.reason_codes) if projection.reached else (),
        source_artifact_ref=(
            projection.risk_decision_id if projection.reached else None
        ),
        operational_at=(projection.created_at if projection.reached else None),
    )


def _paper_record(
    source: DecisionIntelligenceRecord,
) -> FunnelStageAnalyticsAttributionRecord:
    projection = source.decision.execution
    artifact_ref = None
    operational_at = None
    stage_result = None
    if projection.reached:
        if projection.fill is not None:
            artifact_ref = projection.fill.fill_id
            operational_at = projection.fill.filled_at
        elif projection.order is not None:
            artifact_ref = projection.order.broker_order_id
            operational_at = projection.order.updated_at
        elif projection.order_intent is not None:
            artifact_ref = projection.order_intent.client_order_id

        if projection.failure is not None:
            stage_result = _text(projection.failure.code)
        elif projection.order is not None:
            stage_result = _text(projection.order.status)
        else:
            stage_result = _text(source.decision.paper_pipeline_status)

    return _make_record(
        source=source,
        stage=FunnelStage.PAPER,
        source_projection_path="decision.execution",
        source_projection=projection,
        reached=projection.reached,
        stage_status=projection.stage_status,
        stage_result=stage_result,
        failure=projection.failure if projection.reached else None,
        source_artifact_ref=artifact_ref,
        operational_at=operational_at,
    )


def project_funnel_stage_analytics_records(
    record: DecisionIntelligenceRecord,
) -> tuple[FunnelStageAnalyticsAttributionRecord, ...]:
    """Project one canonical Decision Intelligence record into stage sidecars.

    The function accepts no Analytics run/snapshot collection. Every stage copies the already
    resolved 24B.1 reference carried by 24B.2, so operational timestamps can never trigger a
    second market-time lookup.
    """
    if record.decision_context.present and record.decision_context.as_of != record.observed_at:
        raise ValueError("DecisionContext market as_of must equal decision observed_at")
    if (
        record.analytics.analytics_as_of is not None
        and record.analytics.analytics_as_of != record.observed_at
    ):
        raise ValueError("Analytics snapshot as_of must equal decision observed_at")

    records = (
        _compute_gate_record(record),
        _professor_plan_record(record),
        *_specialist_records(record),
        _palermo_record(record),
        _professor_final_record(record),
        _trade_proposal_record(record),
        _risk_record(record),
        _paper_record(record),
    )
    return tuple(
        sorted(
            records,
            key=lambda item: (
                item.stage_order,
                item.stage_instance_order
                if item.stage_instance_order is not None
                else -1,
                item.stage_instance_id or "",
                item.record_id,
            ),
        )
    )


def build_funnel_stage_analytics_attribution(
    decision_records: DecisionIntelligenceRecordSet,
) -> FunnelStageAnalyticsAttributionSet:
    """Build deterministic stage attributions for a complete 24B.2 record set."""
    records: list[FunnelStageAnalyticsAttributionRecord] = []
    seen_decision_ids: set[str] = set()
    for source in decision_records.records:
        if source.record_id in seen_decision_ids:
            raise ValueError("Decision Intelligence set contains duplicate record_id")
        seen_decision_ids.add(source.record_id)
        if source.source_backtest_run_id != decision_records.source_backtest_run_id:
            raise ValueError("Decision Intelligence source BacktestRun mismatch")
        if source.analytics_run_id != decision_records.analytics_run_id:
            raise ValueError("Decision Intelligence AnalyticsRun mismatch")
        records.extend(project_funnel_stage_analytics_records(source))

    ordered = tuple(
        sorted(
            records,
            key=lambda item: (
                item.market_as_of,
                item.opportunity_id,
                item.stage_order,
                item.stage_instance_order
                if item.stage_instance_order is not None
                else -1,
                item.stage_instance_id or "",
                item.record_id,
            ),
        )
    )
    reached = sum(1 for item in ordered if item.reached)
    matched = sum(1 for item in ordered if item.analytics_link_status == "MATCHED")
    payload = {
        "schema": FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_SET_SCHEMA_VERSION,
        "policy": FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_POLICY_VERSION,
        "source_backtest_run_id": decision_records.source_backtest_run_id,
        "analytics_run_id": decision_records.analytics_run_id,
        "source_decision_record_set_fingerprint": decision_records.set_fingerprint,
        "stage_record_fingerprints": tuple(item.record_fingerprint for item in ordered),
    }
    return FunnelStageAnalyticsAttributionSet(
        source_backtest_run_id=decision_records.source_backtest_run_id,
        analytics_run_id=decision_records.analytics_run_id,
        source_decision_record_set_fingerprint=decision_records.set_fingerprint,
        decision_record_count=decision_records.record_count,
        covered_decision_record_count=len(seen_decision_ids),
        stage_record_count=len(ordered),
        reached_stage_count=reached,
        not_reached_stage_count=len(ordered) - reached,
        matched_analytics_stage_count=matched,
        unmatched_analytics_stage_count=len(ordered) - matched,
        records=ordered,
        set_fingerprint=stable_digest(payload),
    )


__all__ = [
    "build_funnel_stage_analytics_attribution",
    "project_funnel_stage_analytics_records",
]
