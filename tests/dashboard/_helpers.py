from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.services.shadow.identities import default_shadow_systems


NOW = datetime(2026, 9, 7, 17, 0, tzinfo=timezone.utc)


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


class FakeBroker:
    def __init__(self, system_id: str, *, fail_account: bool = False):
        self.system_id = system_id
        self.fail_account = fail_account
        self.account = ns(
            system_id=system_id,
            initial_balance=Decimal("100"),
            cash_balance=Decimal("91.5"),
            equity=Decimal("101.25"),
            realized_pnl=Decimal("1.5"),
            unrealized_pnl=Decimal("0.25"),
            fees_paid=Decimal("0.10"),
            gross_exposure=Decimal("10"),
            open_positions=1,
        )
        self.positions = (
            ns(
                system_id=system_id,
                symbol="BTCUSDT",
                side=ns(value="LONG"),
                quantity=Decimal("0.001"),
                average_entry=Decimal("100000"),
                realized_pnl=Decimal("1.5"),
            ),
        )
        self.orders = (
            ns(
                broker_order_id=f"order-{system_id}",
                client_order_id=f"client-{system_id}",
                system_id=system_id,
                symbol="BTCUSDT",
                side=ns(value="BUY"),
                order_type=ns(value="MARKET"),
                requested_quantity=Decimal("0.001"),
                filled_quantity=Decimal("0.001"),
                status=ns(value="FILLED"),
                limit_price=None,
                average_fill_price=Decimal("100000"),
                reject_reason=None,
                trigger=None,
                created_at=NOW,
                updated_at=NOW,
            ),
        )
        self.fills = (
            ns(
                fill_id=f"fill-{system_id}",
                broker_order_id=f"order-{system_id}",
                price=Decimal("100000"),
                quantity=Decimal("0.001"),
                fee=Decimal("0.10"),
                liquidity=ns(value="TAKER"),
                filled_at=NOW,
            ),
        )

    async def get_account_state(self):
        if self.fail_account:
            raise RuntimeError("mark unavailable")
        return self.account

    async def get_positions(self):
        return self.positions

    async def get_orders(self):
        return self.orders

    async def get_fills(self):
        return self.fills


def fake_runner(*, fail_account_system: str | None = None):
    runtimes = []
    for identity in default_shadow_systems():
        runtimes.append(
            ns(
                identity=identity,
                paper_broker=FakeBroker(
                    identity.system_id,
                    fail_account=identity.system_id == fail_account_system,
                ),
            )
        )
    return ns(runtimes=tuple(runtimes))


def _metric(value, status="AVAILABLE", reason=None):
    return ns(value=value, status=ns(value=status), reason=reason)


def fake_evaluation_report():
    trading = ns(
        executed_fill_count=2,
        executed_order_count=2,
        closed_trade_count=1,
        open_position_count=1,
        winning_trades=1,
        losing_trades=0,
        breakeven_trades=0,
        execution_realized_pnl=Decimal("2"),
        fees_paid=Decimal("0.20"),
        realized_trading_net=Decimal("1.8"),
        slippage_cost=_metric(Decimal("0.05")),
        gross_pnl_before_costs=_metric(Decimal("2.05")),
        unrealized_pnl=_metric(Decimal("0.25")),
        trading_net=_metric(Decimal("2.05")),
        gross_exposure=_metric(Decimal("10")),
        win_rate=_metric(Decimal("1")),
        profit_factor=_metric(None, "UNBOUNDED", "no losing trades"),
        expectancy=_metric(Decimal("1.8")),
        max_drawdown_abs=_metric(Decimal("0.4")),
        max_drawdown_pct=_metric(Decimal("0.004")),
    )
    ai_costs = ns(
        total_cost_eur=Decimal("0.30"),
        average_cost_per_opportunity=_metric(Decimal("0.30")),
        average_cost_per_risk_decision=_metric(Decimal("0.30")),
        average_cost_per_executed_trade=_metric(Decimal("0.30")),
    )
    agent = ns(
        agent_id="berlin",
        call_count=1,
        attempt_count=1,
        total_cost_eur=Decimal("0.08"),
        average_cost_eur=_metric(Decimal("0.08")),
        average_latency_ms=_metric(Decimal("120")),
        participation_frequency=_metric(Decimal("1")),
        disagreement_frequency=_metric(Decimal("0")),
        average_confidence=_metric(Decimal("0.7")),
    )
    counterfactual = ns(
        opportunity_id="root-1",
        label="palermo_veto_simulation",
        hypothetical_pnl=Decimal("-1.2"),
        notes=("simulated only",),
    )
    return ns(
        trading=trading,
        ai_costs=ai_costs,
        agents=(agent,),
        counterfactual_outcomes=(counterfactual,),
        economic_net=_metric(Decimal("1.75")),
        self_funding_ratio=ns(
            value=Decimal("6.833333"),
            status=ns(value="AVAILABLE"),
            basis="trading_net / ai_cost",
        ),
    )


def fake_fleet_result(
    *, pipeline_status: str = "EXECUTED", evaluation_status: str = "COMPLETED"
):
    systems = []
    comparison_values = {}
    for index, identity in enumerate(default_shadow_systems(), start=1):
        professor = ns(
            direction="LONG",
            confidence=0.72,
            thesis=["trend"],
            counter_evidence=["volatility"],
            invalidation=["break below support"],
        )
        proposal = ns(
            proposal_id=f"proposal-{index}",
            opportunity_id=f"derived-{index}",
            source_snapshot_id="snap-1",
            system_id=identity.system_id,
            symbol="BTCUSDT",
            timeframe="1h",
            side="LONG",
            confidence=0.72,
            entry_price=Decimal("100000"),
            stop_price=Decimal("99000"),
            targets=(Decimal("102000"),),
            expected_rr=Decimal("2"),
            market_regime="trend",
            expires_at=NOW,
        )
        orchestration = ns(
            professor_decision=professor,
            trade_proposal=proposal,
            audit_events=(
                ns(
                    sequence=1,
                    stage="professor",
                    status="COMPLETED",
                    details={},
                    created_at=NOW,
                ),
            ),
        )
        risk_decision = ns(
            proposal_id=f"proposal-{index}",
            status=ns(value="APPROVED"),
            reason_codes=(ns(value="APPROVED"),),
            approved_quantity=Decimal("0.001"),
            approved_risk_amount=Decimal("1"),
            approved_notional=Decimal("100"),
            created_at=NOW,
        )
        paper_result = ns(
            status=ns(value=pipeline_status),
            opportunity_id=f"derived-{index}",
            source_snapshot_id="snap-1",
            orchestration_result=orchestration,
            risk_record=ns(risk_decision_id=f"risk-{index}", decision=risk_decision),
            kill_switch_state=ns(blocks_new_trades=False),
            failure=None,
            audit_events=(
                ns(
                    sequence=1,
                    stage="paper",
                    status="COMPLETED",
                    details={},
                    created_at=NOW,
                ),
            ),
        )
        report = fake_evaluation_report()
        snapshot = ns(
            realized_pnl=Decimal(str(index)),
            trading_net=Decimal(str(index + 1)),
            economic_net=Decimal(str(index)) - Decimal("0.3"),
            ai_cost=Decimal("0.3"),
            self_funding_ratio=Decimal(str(index + 1)) / Decimal("0.3"),
        )
        evaluation = ns(
            status=ns(value=evaluation_status),
            metrics=snapshot if evaluation_status == "COMPLETED" else None,
            report=report if evaluation_status == "COMPLETED" else None,
            failure=(
                None
                if evaluation_status == "COMPLETED"
                else ns(
                    stage="evaluation",
                    error_type="EvalError",
                    message="evaluation unavailable",
                )
            ),
        )
        usage = ns(
            agent_id="berlin",
            model_id="mock-model",
            estimated_cost_eur=Decimal("0.08"),
        )
        opportunity = ns(
            opportunity_id=f"derived-{index}",
            snapshot_id="snap-1",
            system_id=identity.system_id,
            symbol="BTCUSDT",
            timeframe="1h",
            priority_score=80 + index,
            triggers=(ns(value="range_break"),),
            created_at=NOW,
            expires_at=NOW,
        )
        systems.append(
            ns(
                identity=identity,
                opportunity=opportunity,
                context=ns(
                    derived_opportunity_id=f"derived-{index}",
                    root_snapshot_id="snap-1",
                ),
                status=ns(value="COMPLETED"),
                paper_result=paper_result,
                ai_usage=(ns(system_id=identity.system_id, usage=usage),),
                evaluation=evaluation,
                failure=None,
            )
        )
        comparison_values[identity.system_id] = snapshot

    comparisons = {}
    for metric in (
        "realized_pnl",
        "trading_net",
        "economic_net",
        "ai_cost",
        "self_funding_ratio",
    ):
        values = {
            system_id: getattr(snapshot, metric)
            for system_id, snapshot in comparison_values.items()
        }
        comparisons[metric] = ns(
            metric=metric,
            availability=ns(value="AVAILABLE"),
            values=values,
            pairwise_deltas=(),
        )

    return ns(
        root_correlation_id="corr-1",
        root_opportunity_id="root-1",
        root_snapshot_id="snap-1",
        systems=tuple(systems),
        comparison=ns(metrics=comparisons),
    )
