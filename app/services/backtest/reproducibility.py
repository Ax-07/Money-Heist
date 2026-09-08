from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .ids import canonical_json, stable_digest


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _metric(metric: Any) -> dict[str, Any] | None:
    if metric is None:
        return None
    return {
        "value": getattr(metric, "value", None),
        "status": _value(getattr(metric, "status", None)),
        "reason": getattr(metric, "reason", None),
    }


def _mapping(values: Mapping[str, Any] | None) -> dict[str, Any]:
    if not values:
        return {}
    return {str(key): values[key] for key in sorted(values)}


def _pipeline_payload(result: Any) -> dict[str, Any] | None:
    if result is None:
        return None
    risk_record = getattr(result, "risk_record", None)
    risk = getattr(risk_record, "decision", None) if risk_record is not None else None
    fill = getattr(result, "fill", None)
    return {
        "status": _value(getattr(result, "status", None)),
        "risk": (
            {
                "status": _value(getattr(risk, "status", None)),
                "reason_codes": tuple(
                    _value(code) for code in (getattr(risk, "reason_codes", ()) or ())
                ),
                "approved_quantity": getattr(risk, "approved_quantity", None),
                "approved_risk_amount": getattr(risk, "approved_risk_amount", None),
                "approved_notional": getattr(risk, "approved_notional", None),
            }
            if risk is not None
            else None
        ),
        "fill": (
            {
                "price": getattr(fill, "price", None),
                "quantity": getattr(fill, "quantity", None),
                "fee": getattr(fill, "fee", None),
            }
            if fill is not None
            else None
        ),
    }


def _account_payload(account: Any) -> dict[str, Any] | None:
    if account is None:
        return None
    names = (
        "cash_balance",
        "equity",
        "realized_pnl",
        "unrealized_pnl",
        "fees_paid",
        "gross_exposure",
        "open_positions",
    )
    return {name: getattr(account, name, None) for name in names}


def _exit_payload(event: Any) -> dict[str, Any]:
    return {
        "reason": _value(getattr(event, "reason", None)),
        "reference_price": getattr(event, "reference_price", None),
        "fill_price": getattr(event, "fill_price", None),
        "quantity": getattr(event, "quantity", None),
        "observed_at": getattr(event, "observed_at", None),
    }


def _trading_payload(trading: Any) -> dict[str, Any]:
    scalar_names = (
        "executed_fill_count",
        "executed_order_count",
        "closed_trade_count",
        "open_position_count",
        "winning_trades",
        "losing_trades",
        "breakeven_trades",
        "execution_realized_pnl",
        "fees_paid",
        "realized_trading_net",
    )
    payload = {name: getattr(trading, name) for name in scalar_names}
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
        payload[name] = _metric(getattr(trading, name, None))
    payload["closed_trades"] = tuple(
        {
            "system_id": trade.system_id,
            "symbol": trade.symbol,
            "side": trade.side,
            "quantity": trade.quantity,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "opened_at": trade.opened_at,
            "closed_at": trade.closed_at,
            "net_pnl": trade.net_pnl,
            "fees": trade.fees,
            "slippage_cost": trade.slippage_cost,
        }
        for trade in trading.closed_trades
    )
    return payload


def business_payload(replay_result: Any, evaluation_report: Any) -> dict[str, Any]:
    run = replay_result.backtest_result.run
    points = []
    for point in replay_result.points:
        opportunity = getattr(point, "opportunity", None)
        feature = getattr(point, "feature_snapshot", None)
        points.append(
            {
                "observed_at": point.observed_at,
                "visible_candle_count": point.visible_candle_count,
                "snapshot_id": getattr(feature, "snapshot_id", None),
                "opportunity_id": getattr(opportunity, "opportunity_id", None),
                "pipeline": _pipeline_payload(getattr(point, "pipeline_result", None)),
                "account": _account_payload(getattr(point, "account_state", None)),
                "exits": tuple(_exit_payload(item) for item in point.exit_events),
            }
        )

    ai_costs = evaluation_report.ai_costs
    agent_metrics = tuple(
        {
            "agent_id": item.agent_id,
            "call_count": item.call_count,
            "attempt_count": item.attempt_count,
            "total_cost_eur": item.total_cost_eur,
            "participation_frequency": _metric(item.participation_frequency),
            "disagreement_frequency": _metric(item.disagreement_frequency),
            "average_confidence": _metric(item.average_confidence),
            "prompt_versions": item.prompt_versions,
            "route_ids": item.route_ids,
            "model_ids": item.model_ids,
        }
        for item in evaluation_report.agents
    )

    return {
        "schema": "money-heist.backtest-business.v1",
        "run_id": run.run_id,
        "dataset_id": run.dataset.dataset_id,
        "ai_mode": run.config.ai_mode,
        "counts": {
            "processed_candles": replay_result.backtest_result.processed_candles,
            "opportunity_count": replay_result.backtest_result.opportunity_count,
            "executed_order_count": replay_result.backtest_result.executed_order_count,
        },
        "points": tuple(points),
        "evaluation": {
            "report_version": evaluation_report.report_version,
            "trading": _trading_payload(evaluation_report.trading),
            "ai_costs": {
                "total_cost_eur": ai_costs.total_cost_eur,
                "by_agent": _mapping(ai_costs.by_agent),
                "by_model": _mapping(ai_costs.by_model),
                "by_route": _mapping(ai_costs.by_route),
            },
            "agents": agent_metrics,
            "economic_net": _metric(evaluation_report.economic_net),
            "self_funding_ratio": {
                "value": evaluation_report.self_funding_ratio.value,
                "status": _value(evaluation_report.self_funding_ratio.status),
                "basis": evaluation_report.self_funding_ratio.basis,
            },
        },
    }


@dataclass(frozen=True, slots=True)
class BacktestBusinessFingerprint:
    run_id: str
    dataset_id: str
    ai_mode: str
    business_sha256: str

    def canonical_payload(self) -> dict[str, str]:
        return {
            "run_id": self.run_id,
            "dataset_id": self.dataset_id,
            "ai_mode": self.ai_mode,
            "business_sha256": self.business_sha256,
        }

    def to_json(self) -> str:
        return canonical_json(self.canonical_payload())


def fingerprint_backtest(
    replay_result: Any,
    evaluation_report: Any,
) -> BacktestBusinessFingerprint:
    run = replay_result.backtest_result.run
    return BacktestBusinessFingerprint(
        run_id=run.run_id,
        dataset_id=run.dataset.dataset_id,
        ai_mode=str(_value(run.config.ai_mode)),
        business_sha256=stable_digest(
            business_payload(replay_result, evaluation_report)
        ),
    )


def assert_reproducible(
    first: BacktestBusinessFingerprint,
    second: BacktestBusinessFingerprint,
) -> None:
    if first.run_id != second.run_id:
        raise AssertionError("backtest run_id differs")
    if first.business_sha256 != second.business_sha256:
        raise AssertionError("backtest business outputs differ")


__all__ = [
    "BacktestBusinessFingerprint",
    "assert_reproducible",
    "business_payload",
    "fingerprint_backtest",
]
