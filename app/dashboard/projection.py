from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.shadow.identities import default_shadow_systems

from .models import (
    DashboardAIUsage,
    DashboardAccount,
    DashboardAgentMetric,
    DashboardAvailability,
    DashboardBatch10,
    DashboardComparison,
    DashboardComparisonMetric,
    DashboardCounterfactual,
    DashboardDecision,
    DashboardEvent,
    DashboardEventKind,
    DashboardEventSeverity,
    DashboardFill,
    DashboardMetric,
    DashboardOpportunity,
    DashboardOrder,
    DashboardPairwiseDelta,
    DashboardPosition,
    DashboardProfessorDecision,
    DashboardProvenance,
    DashboardRiskDecision,
    DashboardSnapshot,
    DashboardSystem,
    DashboardTradeProposal,
)


ZERO = Decimal("0")


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    try:
        converted = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return converted if converted.is_finite() else None


def _unavailable_metric(name: str, reason: str, *, unit: str | None = None) -> DashboardMetric:
    return DashboardMetric(
        name=name,
        availability=DashboardAvailability.UNAVAILABLE,
        reason=reason,
        unit=unit,
        provenance=DashboardProvenance.UNAVAILABLE,
    )


def _value_metric(
    name: str,
    value: Any,
    *,
    unit: str | None = None,
    provenance: DashboardProvenance = DashboardProvenance.SHADOW_PAPER,
) -> DashboardMetric:
    decimal_value = _decimal(value)
    if decimal_value is None:
        return _unavailable_metric(name, "source metric is unavailable", unit=unit)
    return DashboardMetric(
        name=name,
        value=decimal_value,
        availability=DashboardAvailability.AVAILABLE,
        unit=unit,
        provenance=provenance,
    )


def _batch10_metric(name: str, raw: Any, *, unit: str | None = None) -> DashboardMetric:
    if raw is None:
        return _unavailable_metric(name, "Batch 10 metric is unavailable", unit=unit)

    if hasattr(raw, "status") and hasattr(raw, "value"):
        status = _enum_value(getattr(raw, "status", None))
        value = _decimal(getattr(raw, "value", None))
        reason = getattr(raw, "reason", None)
        if status == "AVAILABLE" and value is not None:
            return DashboardMetric(
                name=name,
                value=value,
                availability=DashboardAvailability.AVAILABLE,
                unit=unit,
                provenance=DashboardProvenance.SHADOW_PAPER,
            )
        if status in {"UNBOUNDED", "ZERO_AI_COST"}:
            return DashboardMetric(
                name=name,
                value=value,
                availability=DashboardAvailability.UNBOUNDED,
                unit=unit,
                reason=reason or status,
                provenance=DashboardProvenance.SHADOW_PAPER,
            )
        return DashboardMetric(
            name=name,
            value=value,
            availability=DashboardAvailability.UNAVAILABLE,
            unit=unit,
            reason=reason or status or "Batch 10 metric is unavailable",
            provenance=DashboardProvenance.UNAVAILABLE,
        )

    return _value_metric(name, raw, unit=unit)


def _self_funding_metric(raw: Any) -> DashboardMetric:
    if raw is None:
        return _unavailable_metric(
            "self_funding_ratio", "Batch 10 ratio is unavailable", unit="x"
        )
    status = _enum_value(getattr(raw, "status", None))
    value = _decimal(
        getattr(
            raw,
            "value",
            raw if isinstance(raw, (Decimal, int, float, str)) else None,
        )
    )
    basis = getattr(raw, "basis", None)
    if status in {None, "AVAILABLE"} and value is not None:
        return DashboardMetric(
            name="self_funding_ratio",
            value=value,
            availability=DashboardAvailability.AVAILABLE,
            unit="x",
            reason=basis,
        )
    if status == "ZERO_AI_COST":
        return DashboardMetric(
            name="self_funding_ratio",
            value=value,
            availability=DashboardAvailability.UNBOUNDED,
            unit="x",
            reason=basis or status,
        )
    return DashboardMetric(
        name="self_funding_ratio",
        value=value,
        availability=DashboardAvailability.UNAVAILABLE,
        unit="x",
        reason=basis or status or "Batch 10 ratio is unavailable",
        provenance=DashboardProvenance.UNAVAILABLE,
    )


def _empty_comparison() -> DashboardComparison:
    metrics = {}
    for name in ("realized_pnl", "trading_net", "economic_net", "ai_cost", "self_funding_ratio"):
        metrics[name] = DashboardComparisonMetric(
            metric=name,
            availability=DashboardAvailability.UNAVAILABLE,
            values={identity.system_id: None for identity in default_shadow_systems()},
        )
    return DashboardComparison(metrics=metrics)


def seeded_dashboard_snapshot(
    *, clock: Any | None = None, reason: str = "No SHADOW fleet result has been observed yet"
) -> DashboardSnapshot:
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    systems = tuple(_empty_system(identity, reason) for identity in default_shadow_systems())
    return DashboardSnapshot(
        generated_at=now,
        system_state="NO_OBSERVED_SHADOW_RUN",
        systems=systems,
        comparison=_empty_comparison(),
    )


def _empty_system(identity: Any, reason: str) -> DashboardSystem:
    return DashboardSystem(
        system_id=identity.system_id,
        family=_enum_value(identity.family) or "UNKNOWN",
        display_name=identity.display_name,
        aliases=tuple(identity.aliases),
        mode=identity.mode,
        execution_mode="PAPER",
        account=DashboardAccount(availability=DashboardAvailability.UNAVAILABLE, reason=reason),
        positions_availability=DashboardAvailability.UNAVAILABLE,
        positions_reason=reason,
        orders_availability=DashboardAvailability.UNAVAILABLE,
        orders_reason=reason,
        fills_availability=DashboardAvailability.UNAVAILABLE,
        fills_reason=reason,
        ai_usage=DashboardAIUsage(
            availability=DashboardAvailability.UNAVAILABLE,
            reason=reason,
            record_count=0,
        ),
        batch10=DashboardBatch10(status="UNAVAILABLE", failure=reason),
    )


class ShadowDashboardProjector:
    """Read-only projection from Batch 11 runtime/result objects to Dashboard V1 models.

    The projector never calls the Risk Engine, orchestration or broker mutation methods.
    It only consumes Batch 11 results and the public PAPER broker read methods.
    """

    def __init__(self, *, clock: Any | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def capture(self, *, runner: Any, fleet_result: Any) -> DashboardSnapshot:
        runtime_by_system = {runtime.identity.system_id: runtime for runtime in runner.runtimes}
        systems: list[DashboardSystem] = []
        opportunities: list[DashboardOpportunity] = []
        decisions: list[DashboardDecision] = []
        events: list[DashboardEvent] = []

        for result in fleet_result.systems:
            system_id = result.identity.system_id
            opportunities.append(self._opportunity(result, fleet_result.root_opportunity_id))
            runtime = runtime_by_system.get(system_id)
            if runtime is None:
                system = _empty_system(result.identity, "SHADOW runtime is unavailable")
                systems.append(system)
                missing_decision = self._decision(result)
                if missing_decision is not None:
                    decisions.append(missing_decision)
                events.append(
                    self._event(
                        event_id=f"runtime-missing:{system_id}",
                        kind=DashboardEventKind.SECURITY,
                        severity=DashboardEventSeverity.ERROR,
                        system_id=system_id,
                        opportunity_id=result.context.derived_opportunity_id,
                        source="dashboard_projection",
                        stage="runtime_lookup",
                        status="FAILED",
                        code="SHADOW_RUNTIME_UNAVAILABLE",
                        message="Result has no matching SHADOW runtime",
                    )
                )
                continue

            account, account_reason = await self._account(runtime.paper_broker)
            positions, positions_availability, positions_reason = await self._positions(
                runtime.paper_broker
            )
            orders, orders_availability, orders_reason = await self._orders(runtime.paper_broker)
            fills, fills_availability, fills_reason = await self._fills(runtime.paper_broker)
            decision = self._decision(result)
            if decision is not None:
                decisions.append(decision)
            ai_usage = self._ai_usage(result)
            batch10 = self._batch10(result)
            events.extend(self._events(result))

            systems.append(
                DashboardSystem(
                    system_id=system_id,
                    family=_enum_value(result.identity.family) or "UNKNOWN",
                    display_name=result.identity.display_name,
                    aliases=tuple(result.identity.aliases),
                    mode=result.identity.mode,
                    execution_mode="PAPER",
                    account=account,
                    positions_availability=positions_availability,
                    positions_reason=positions_reason,
                    positions=positions,
                    orders_availability=orders_availability,
                    orders_reason=orders_reason,
                    orders=orders,
                    fills_availability=fills_availability,
                    fills_reason=fills_reason,
                    fills=fills,
                    latest_decision=decision,
                    ai_usage=ai_usage,
                    batch10=batch10,
                )
            )
            if account_reason is not None:
                events.append(
                    self._event(
                        event_id=(
                            f"account-unavailable:{system_id}:"
                            f"{fleet_result.root_opportunity_id}"
                        ),
                        kind=DashboardEventKind.SECURITY,
                        severity=DashboardEventSeverity.WARNING,
                        system_id=system_id,
                        opportunity_id=result.context.derived_opportunity_id,
                        source="paper_broker",
                        stage="account_read",
                        status="UNAVAILABLE",
                        code="ACCOUNT_STATE_UNAVAILABLE",
                        message=account_reason,
                    )
                )

        return DashboardSnapshot(
            generated_at=self._clock(),
            system_state=self._system_state(systems),
            root_correlation_id=str(fleet_result.root_correlation_id),
            root_opportunity_id=str(fleet_result.root_opportunity_id),
            root_snapshot_id=str(fleet_result.root_snapshot_id),
            systems=tuple(systems),
            opportunities=tuple(opportunities),
            decisions=tuple(decisions),
            comparison=self._comparison(fleet_result.comparison),
            events=tuple(events),
        )


    def _opportunity(self, result: Any, root_opportunity_id: Any) -> DashboardOpportunity:
        opportunity = result.opportunity
        return DashboardOpportunity(
            system_id=result.identity.system_id,
            opportunity_id=str(
                getattr(opportunity, "opportunity_id", result.context.derived_opportunity_id)
            ),
            root_opportunity_id=str(root_opportunity_id),
            source_snapshot_id=str(
                getattr(opportunity, "snapshot_id", result.context.root_snapshot_id)
            ),
            symbol=str(getattr(opportunity, "symbol", "UNKNOWN")),
            timeframe=str(getattr(opportunity, "timeframe", "UNKNOWN")),
            priority_score=getattr(opportunity, "priority_score", None),
            triggers=tuple(
                _enum_value(trigger) or "UNKNOWN"
                for trigger in tuple(getattr(opportunity, "triggers", ()))
            ),
            created_at=getattr(opportunity, "created_at", None),
            expires_at=getattr(opportunity, "expires_at", None),
        )

    async def _account(self, broker: Any) -> tuple[DashboardAccount, str | None]:
        try:
            account = await broker.get_account_state()
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            return (
                DashboardAccount(availability=DashboardAvailability.UNAVAILABLE, reason=reason),
                reason,
            )
        return (
            DashboardAccount(
                availability=DashboardAvailability.AVAILABLE,
                initial_balance=account.initial_balance,
                cash_balance=account.cash_balance,
                equity=account.equity,
                realized_pnl=account.realized_pnl,
                unrealized_pnl=account.unrealized_pnl,
                fees_paid=account.fees_paid,
                gross_exposure=account.gross_exposure,
                open_positions=account.open_positions,
            ),
            None,
        )

    async def _positions(
        self, broker: Any
    ) -> tuple[tuple[DashboardPosition, ...], DashboardAvailability, str | None]:
        try:
            positions = await broker.get_positions()
        except Exception as exc:
            return (), DashboardAvailability.UNAVAILABLE, f"{type(exc).__name__}: {exc}"
        projected = tuple(
            DashboardPosition(
                system_id=position.system_id,
                symbol=position.symbol,
                side=_enum_value(position.side),
                quantity=position.quantity,
                average_entry=position.average_entry,
                realized_pnl=position.realized_pnl,
            )
            for position in positions
        )
        return projected, DashboardAvailability.AVAILABLE, None

    async def _orders(
        self, broker: Any
    ) -> tuple[tuple[DashboardOrder, ...], DashboardAvailability, str | None]:
        try:
            orders = await broker.get_orders()
        except Exception as exc:
            return (), DashboardAvailability.UNAVAILABLE, f"{type(exc).__name__}: {exc}"
        projected = tuple(
            DashboardOrder(
                broker_order_id=order.broker_order_id,
                client_order_id=order.client_order_id,
                system_id=order.system_id,
                symbol=order.symbol,
                side=_enum_value(order.side) or "UNKNOWN",
                order_type=_enum_value(order.order_type) or "UNKNOWN",
                requested_quantity=order.requested_quantity,
                filled_quantity=order.filled_quantity,
                status=_enum_value(order.status) or "UNKNOWN",
                limit_price=order.limit_price,
                average_fill_price=order.average_fill_price,
                reject_reason=order.reject_reason,
                trigger=order.trigger,
                created_at=order.created_at,
                updated_at=order.updated_at,
            )
            for order in orders
        )
        return projected, DashboardAvailability.AVAILABLE, None

    async def _fills(
        self, broker: Any
    ) -> tuple[tuple[DashboardFill, ...], DashboardAvailability, str | None]:
        try:
            fills = await broker.get_fills()
        except Exception as exc:
            return (), DashboardAvailability.UNAVAILABLE, f"{type(exc).__name__}: {exc}"
        projected = tuple(
            DashboardFill(
                fill_id=fill.fill_id,
                broker_order_id=fill.broker_order_id,
                price=fill.price,
                quantity=fill.quantity,
                fee=fill.fee,
                liquidity=_enum_value(fill.liquidity) or "UNKNOWN",
                filled_at=fill.filled_at,
            )
            for fill in fills
        )
        return projected, DashboardAvailability.AVAILABLE, None

    def _decision(self, result: Any) -> DashboardDecision | None:
        paper_result = result.paper_result
        if paper_result is None:
            failure = result.failure
            return DashboardDecision(
                system_id=result.identity.system_id,
                opportunity_id=result.context.derived_opportunity_id,
                source_snapshot_id=result.context.root_snapshot_id,
                pipeline_status="FAILED",
                branch_status=_enum_value(result.status) or "FAILED",
                failure_code=getattr(failure, "error_type", None),
                failure_stage=getattr(failure, "stage", None),
                failure_message=getattr(failure, "message", None),
            )

        orchestration = getattr(paper_result, "orchestration_result", None)
        professor = None
        proposal = None
        if orchestration is not None:
            raw_professor = getattr(orchestration, "professor_decision", None)
            if raw_professor is not None:
                professor = DashboardProfessorDecision(
                    direction=str(raw_professor.direction),
                    confidence=float(raw_professor.confidence),
                    thesis=tuple(raw_professor.thesis),
                    counter_evidence=tuple(raw_professor.counter_evidence),
                    invalidation=tuple(raw_professor.invalidation),
                )
            raw_proposal = getattr(orchestration, "trade_proposal", None)
            if raw_proposal is not None:
                proposal = DashboardTradeProposal(
                    proposal_id=str(raw_proposal.proposal_id),
                    opportunity_id=str(raw_proposal.opportunity_id),
                    source_snapshot_id=str(raw_proposal.source_snapshot_id),
                    system_id=str(raw_proposal.system_id),
                    symbol=str(raw_proposal.symbol),
                    timeframe=str(raw_proposal.timeframe),
                    side=str(raw_proposal.side),
                    confidence=float(raw_proposal.confidence),
                    entry_price=raw_proposal.entry_price,
                    stop_price=raw_proposal.stop_price,
                    targets=tuple(raw_proposal.targets),
                    expected_rr=raw_proposal.expected_rr,
                    market_regime=str(raw_proposal.market_regime),
                    expires_at=raw_proposal.expires_at,
                )

        risk = None
        raw_record = getattr(paper_result, "risk_record", None)
        if raw_record is not None:
            raw_decision = raw_record.decision
            risk = DashboardRiskDecision(
                risk_decision_id=str(raw_record.risk_decision_id),
                proposal_id=str(raw_decision.proposal_id),
                status=_enum_value(raw_decision.status) or "UNKNOWN",
                reason_codes=tuple(
                    _enum_value(code) or "UNKNOWN" for code in raw_decision.reason_codes
                ),
                approved_quantity=raw_decision.approved_quantity,
                approved_risk_amount=raw_decision.approved_risk_amount,
                approved_notional=raw_decision.approved_notional,
                created_at=raw_decision.created_at,
            )

        failure = getattr(paper_result, "failure", None)
        failure_code = _enum_value(getattr(failure, "code", None)) if failure is not None else None
        return DashboardDecision(
            system_id=result.identity.system_id,
            opportunity_id=str(paper_result.opportunity_id),
            source_snapshot_id=str(paper_result.source_snapshot_id),
            pipeline_status=_enum_value(paper_result.status) or "UNKNOWN",
            branch_status=_enum_value(result.status) or "UNKNOWN",
            professor=professor,
            proposal=proposal,
            risk=risk,
            failure_code=failure_code,
            failure_stage=getattr(failure, "stage", None),
            failure_message=getattr(failure, "message", None),
        )

    def _ai_usage(self, result: Any) -> DashboardAIUsage:
        if result.failure is not None and result.failure.stage == "ai_usage":
            return DashboardAIUsage(
                availability=DashboardAvailability.UNAVAILABLE,
                reason=result.failure.message,
                record_count=0,
            )

        total = ZERO
        by_agent: dict[str, Decimal] = defaultdict(lambda: ZERO)
        by_model: dict[str, Decimal] = defaultdict(lambda: ZERO)
        missing_cost = False
        records = tuple(result.ai_usage)
        for scoped in records:
            usage = scoped.usage
            cost = _decimal(
                getattr(usage, "estimated_cost_eur", getattr(usage, "estimated_cost", None))
            )
            if cost is None:
                missing_cost = True
                continue
            total += cost
            agent = str(getattr(usage, "agent_id", "unknown"))
            model = str(getattr(usage, "model_id", "unknown"))
            by_agent[agent] += cost
            by_model[model] += cost

        availability = (
            DashboardAvailability.PARTIAL if missing_cost else DashboardAvailability.AVAILABLE
        )
        return DashboardAIUsage(
            availability=availability,
            reason="One or more AI usage records have no cost" if missing_cost else None,
            record_count=len(records),
            total_cost_eur=total,
            by_agent_eur=dict(sorted(by_agent.items())),
            by_model_eur=dict(sorted(by_model.items())),
        )

    def _batch10(self, result: Any) -> DashboardBatch10:
        evaluation = result.evaluation
        status = _enum_value(evaluation.status) or "UNAVAILABLE"
        if status != "COMPLETED":
            failure = getattr(evaluation, "failure", None)
            message = getattr(failure, "message", None) or f"Batch 10 evaluation status: {status}"
            metrics = {
                name: _unavailable_metric(name, message)
                for name in (
                    "realized_pnl",
                    "trading_net",
                    "economic_net",
                    "ai_cost",
                    "self_funding_ratio",
                    "max_drawdown_abs",
                    "max_drawdown_pct",
                )
            }
            return DashboardBatch10(status=status, metrics=metrics, failure=message)

        metrics: dict[str, DashboardMetric] = {}
        report = evaluation.report
        snapshot = evaluation.metrics

        if snapshot is not None:
            metrics.update(
                {
                    "realized_pnl": _value_metric(
                        "realized_pnl", snapshot.realized_pnl, unit="currency"
                    ),
                    "trading_net": _value_metric(
                        "trading_net", snapshot.trading_net, unit="currency"
                    ),
                    "economic_net": _value_metric(
                        "economic_net", snapshot.economic_net, unit="currency"
                    ),
                    "ai_cost": _value_metric("ai_cost", snapshot.ai_cost, unit="EUR"),
                    "self_funding_ratio": _value_metric(
                        "self_funding_ratio", snapshot.self_funding_ratio, unit="x"
                    ),
                }
            )

        agents: list[DashboardAgentMetric] = []
        counterfactuals: list[DashboardCounterfactual] = []
        if report is not None and not isinstance(report, dict):
            trading = getattr(report, "trading", None)
            if trading is not None:
                simple_values = {
                    "executed_fill_count": getattr(trading, "executed_fill_count", None),
                    "executed_order_count": getattr(trading, "executed_order_count", None),
                    "closed_trade_count": getattr(trading, "closed_trade_count", None),
                    "open_position_count": getattr(trading, "open_position_count", None),
                    "winning_trades": getattr(trading, "winning_trades", None),
                    "losing_trades": getattr(trading, "losing_trades", None),
                    "breakeven_trades": getattr(trading, "breakeven_trades", None),
                    "execution_realized_pnl": getattr(trading, "execution_realized_pnl", None),
                    "fees_paid": getattr(trading, "fees_paid", None),
                    "realized_trading_net": getattr(trading, "realized_trading_net", None),
                }
                for name, value in simple_values.items():
                    metrics[name] = _value_metric(name, value)
                for name in (
                    "slippage_cost",
                    "gross_pnl_before_costs",
                    "unrealized_pnl",
                    "trading_net",
                    "gross_exposure",
                    "win_rate",
                    "profit_factor",
                    "expectancy",
                    "max_drawdown_abs",
                    "max_drawdown_pct",
                ):
                    metrics[name] = _batch10_metric(name, getattr(trading, name, None))

            ai_costs = getattr(report, "ai_costs", None)
            if ai_costs is not None:
                metrics["ai_cost"] = _value_metric(
                    "ai_cost", getattr(ai_costs, "total_cost_eur", None), unit="EUR"
                )
                for name in (
                    "average_cost_per_opportunity",
                    "average_cost_per_risk_decision",
                    "average_cost_per_executed_trade",
                ):
                    metrics[name] = _batch10_metric(
                        name, getattr(ai_costs, name, None), unit="EUR"
                    )

            metrics["economic_net"] = _batch10_metric(
                "economic_net", getattr(report, "economic_net", None), unit="currency"
            )
            metrics["self_funding_ratio"] = _self_funding_metric(
                getattr(report, "self_funding_ratio", None)
            )

            for agent in tuple(getattr(report, "agents", ())):
                agents.append(
                    DashboardAgentMetric(
                        agent_id=agent.agent_id,
                        call_count=agent.call_count,
                        attempt_count=agent.attempt_count,
                        total_cost_eur=agent.total_cost_eur,
                        average_cost_eur=_batch10_metric(
                            "average_cost_eur", agent.average_cost_eur, unit="EUR"
                        ),
                        average_latency_ms=_batch10_metric(
                            "average_latency_ms", agent.average_latency_ms, unit="ms"
                        ),
                        participation_frequency=_batch10_metric(
                            "participation_frequency", agent.participation_frequency
                        ),
                        disagreement_frequency=_batch10_metric(
                            "disagreement_frequency", agent.disagreement_frequency
                        ),
                        average_confidence=_batch10_metric(
                            "average_confidence", agent.average_confidence
                        ),
                    )
                )
            for item in tuple(getattr(report, "counterfactual_outcomes", ())):
                counterfactuals.append(
                    DashboardCounterfactual(
                        opportunity_id=item.opportunity_id,
                        label=item.label,
                        hypothetical_pnl=item.hypothetical_pnl,
                        notes=tuple(item.notes),
                    )
                )

        elif isinstance(report, dict):
            for name, value in report.items():
                if name in {
                    "realized_pnl",
                    "trading_net",
                    "economic_net",
                    "ai_cost",
                    "self_funding_ratio",
                }:
                    metrics[name] = _value_metric(name, value)

        required = (
            "realized_pnl",
            "trading_net",
            "economic_net",
            "ai_cost",
            "self_funding_ratio",
            "max_drawdown_abs",
            "max_drawdown_pct",
        )
        for name in required:
            metrics.setdefault(
                name, _unavailable_metric(name, "Metric not exposed by Batch 10 report")
            )
        return DashboardBatch10(
            status=status,
            metrics=dict(sorted(metrics.items())),
            agents=tuple(agents),
            counterfactuals=tuple(counterfactuals),
        )

    def _comparison(self, comparison: Any) -> DashboardComparison:
        metrics: dict[str, DashboardComparisonMetric] = {}
        for name, raw in comparison.metrics.items():
            availability_name = _enum_value(raw.availability) or "UNAVAILABLE"
            availability = DashboardAvailability(availability_name)
            pairwise = tuple(
                DashboardPairwiseDelta(
                    left_system_id=item.left_system_id,
                    right_system_id=item.right_system_id,
                    left_value=item.left_value,
                    right_value=item.right_value,
                    delta_right_minus_left=item.delta_right_minus_left,
                )
                for item in raw.pairwise_deltas
            )
            metrics[name] = DashboardComparisonMetric(
                metric=name,
                availability=availability,
                values=dict(raw.values),
                pairwise_deltas=pairwise,
            )
        return DashboardComparison(metrics=dict(sorted(metrics.items())))

    def _events(self, result: Any) -> list[DashboardEvent]:
        system_id = result.identity.system_id
        opportunity_id = result.context.derived_opportunity_id
        events: list[DashboardEvent] = []
        paper_result = result.paper_result

        if paper_result is not None:
            for event in tuple(getattr(paper_result, "audit_events", ())):
                events.append(
                    self._event(
                        event_id=(
                            f"paper:{system_id}:{opportunity_id}:"
                            f"{getattr(event, 'sequence', len(events) + 1)}"
                        ),
                        kind=DashboardEventKind.AUDIT,
                        severity=(
                            DashboardEventSeverity.ERROR
                            if str(getattr(event, "status", "")) == "FAILED"
                            else DashboardEventSeverity.INFO
                        ),
                        system_id=system_id,
                        opportunity_id=opportunity_id,
                        source="paper_pipeline",
                        stage=getattr(event, "stage", None),
                        status=str(getattr(event, "status", "UNKNOWN")),
                        created_at=getattr(event, "created_at", None),
                        details=dict(getattr(event, "details", {})),
                    )
                )

            orchestration = getattr(paper_result, "orchestration_result", None)
            if orchestration is not None:
                for event in tuple(getattr(orchestration, "audit_events", ())):
                    status = str(getattr(event, "status", "UNKNOWN"))
                    events.append(
                        self._event(
                            event_id=(
                                f"orchestration:{system_id}:{opportunity_id}:"
                                f"{getattr(event, 'sequence', len(events) + 1)}"
                            ),
                            kind=DashboardEventKind.AUDIT,
                            severity=(
                                DashboardEventSeverity.ERROR
                                if status == "FAILED"
                                else DashboardEventSeverity.INFO
                            ),
                            system_id=system_id,
                            opportunity_id=opportunity_id,
                            source="orchestration",
                            stage=getattr(event, "stage", None),
                            status=status,
                            created_at=getattr(event, "created_at", None),
                            details=dict(getattr(event, "details", {})),
                        )
                    )

            risk_record = getattr(paper_result, "risk_record", None)
            if risk_record is not None:
                decision = risk_record.decision
                reason_codes = [
                    _enum_value(code) or "UNKNOWN" for code in decision.reason_codes
                ]
                events.append(
                    self._event(
                        event_id=f"risk:{system_id}:{risk_record.risk_decision_id}",
                        kind=DashboardEventKind.RISK,
                        severity=(
                            DashboardEventSeverity.WARNING
                            if _enum_value(decision.status) == "REJECTED"
                            else DashboardEventSeverity.INFO
                        ),
                        system_id=system_id,
                        opportunity_id=opportunity_id,
                        source="risk_engine",
                        stage="risk_decision",
                        status=_enum_value(decision.status),
                        code=",".join(reason_codes),
                        message="Deterministic Risk Engine decision",
                        created_at=decision.created_at,
                        details={"reason_codes": reason_codes},
                    )
                )

            kill_switch = getattr(paper_result, "kill_switch_state", None)
            if kill_switch is not None and getattr(kill_switch, "blocks_new_trades", False):
                events.append(
                    self._event(
                        event_id=f"kill-switch:{system_id}:{opportunity_id}",
                        kind=DashboardEventKind.SECURITY,
                        severity=DashboardEventSeverity.CRITICAL,
                        system_id=system_id,
                        opportunity_id=opportunity_id,
                        source="risk_context",
                        stage="kill_switch",
                        status="ACTIVE",
                        code="KILL_SWITCH_ACTIVE",
                        message=getattr(kill_switch, "reason", None),
                        created_at=getattr(kill_switch, "activated_at", None),
                    )
                )

        if result.failure is not None:
            events.append(
                self._event(
                    event_id=f"branch-failure:{system_id}:{opportunity_id}",
                    kind=DashboardEventKind.SECURITY,
                    severity=DashboardEventSeverity.ERROR,
                    system_id=system_id,
                    opportunity_id=opportunity_id,
                    source="shadow_runtime",
                    stage=result.failure.stage,
                    status="FAILED",
                    code=result.failure.error_type,
                    message=result.failure.message,
                )
            )

        evaluation = result.evaluation
        if _enum_value(evaluation.status) == "FAILED":
            failure = evaluation.failure
            events.append(
                self._event(
                    event_id=f"evaluation-failure:{system_id}:{opportunity_id}",
                    kind=DashboardEventKind.EVALUATION,
                    severity=DashboardEventSeverity.WARNING,
                    system_id=system_id,
                    opportunity_id=opportunity_id,
                    source="batch10_evaluation",
                    stage=getattr(failure, "stage", "evaluation"),
                    status="FAILED",
                    code=getattr(failure, "error_type", "EvaluationFailure"),
                    message=getattr(failure, "message", "Batch 10 evaluation failed"),
                )
            )
        return events

    def _event(
        self,
        *,
        event_id: str,
        kind: DashboardEventKind,
        severity: DashboardEventSeverity,
        source: str,
        system_id: str | None = None,
        opportunity_id: str | None = None,
        stage: str | None = None,
        status: str | None = None,
        code: str | None = None,
        message: str | None = None,
        created_at: datetime | None = None,
        details: dict[str, Any] | None = None,
    ) -> DashboardEvent:
        return DashboardEvent(
            event_id=event_id,
            kind=kind,
            severity=severity,
            system_id=system_id,
            opportunity_id=opportunity_id,
            source=source,
            stage=stage,
            status=status,
            code=code,
            message=message,
            created_at=created_at or self._clock(),
            details=details or {},
        )

    @staticmethod
    def _system_state(systems: list[DashboardSystem]) -> str:
        if not systems:
            return "UNAVAILABLE"
        if any(
            system.latest_decision and system.latest_decision.pipeline_status == "FAILED"
            for system in systems
        ):
            return "DEGRADED"
        if any(
            system.account.availability is DashboardAvailability.UNAVAILABLE
            for system in systems
        ):
            return "PARTIAL"
        return "OBSERVABLE"
