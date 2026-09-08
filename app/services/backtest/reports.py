from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from .reproducibility import fingerprint_backtest
from .splits import BacktestPeriodRole, BacktestSplitPlan


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


@dataclass(frozen=True, slots=True)
class BacktestMetricSnapshot:
    value: Decimal | None
    status: str
    reason: str | None = None

    @classmethod
    def from_metric(cls, metric: Any) -> BacktestMetricSnapshot:
        raw_value = getattr(metric, "value", None)
        value = Decimal(str(raw_value)) if raw_value is not None else None
        return cls(
            value=value,
            status=str(_value(getattr(metric, "status", "UNKNOWN"))),
            reason=getattr(metric, "reason", None),
        )


@dataclass(frozen=True, slots=True)
class BacktestPeriodReport:
    role: BacktestPeriodRole
    run_id: str
    dataset_id: str
    period_start: datetime
    period_end: datetime
    processed_candles: int
    opportunity_count: int
    executed_order_count: int
    closed_trade_count: int
    trading_net: BacktestMetricSnapshot
    max_drawdown_pct: BacktestMetricSnapshot
    ai_cost_eur: Decimal
    economic_net: BacktestMetricSnapshot
    self_funding_ratio: Decimal | None
    self_funding_status: str
    business_sha256: str

    @property
    def is_out_of_sample(self) -> bool:
        return self.role is BacktestPeriodRole.OOS

    @classmethod
    def from_evaluation(
        cls,
        role: BacktestPeriodRole,
        replay_result: Any,
        evaluation_bundle: Any,
    ) -> BacktestPeriodReport:
        result = replay_result.backtest_result
        run = result.run
        report = evaluation_bundle.report
        fingerprint = fingerprint_backtest(replay_result, report)
        ratio = report.self_funding_ratio
        ratio_value = getattr(ratio, "value", None)
        return cls(
            role=role,
            run_id=run.run_id,
            dataset_id=run.dataset.dataset_id,
            period_start=run.period_start,
            period_end=run.period_end,
            processed_candles=result.processed_candles,
            opportunity_count=result.opportunity_count,
            executed_order_count=result.executed_order_count,
            closed_trade_count=report.trading.closed_trade_count,
            trading_net=BacktestMetricSnapshot.from_metric(report.trading.trading_net),
            max_drawdown_pct=BacktestMetricSnapshot.from_metric(
                report.trading.max_drawdown_pct
            ),
            ai_cost_eur=Decimal(str(report.ai_costs.total_cost_eur)),
            economic_net=BacktestMetricSnapshot.from_metric(report.economic_net),
            self_funding_ratio=(
                Decimal(str(ratio_value)) if ratio_value is not None else None
            ),
            self_funding_status=str(_value(getattr(ratio, "status", "UNKNOWN"))),
            business_sha256=fingerprint.business_sha256,
        )


@dataclass(frozen=True, slots=True)
class BacktestSplitReport:
    split_id: str
    design: BacktestPeriodReport
    validation: BacktestPeriodReport
    oos: BacktestPeriodReport

    def __post_init__(self) -> None:
        if self.design.role is not BacktestPeriodRole.DESIGN:
            raise ValueError("design report must have DESIGN role")
        if self.validation.role is not BacktestPeriodRole.VALIDATION:
            raise ValueError("validation report must have VALIDATION role")
        if self.oos.role is not BacktestPeriodRole.OOS:
            raise ValueError("oos report must have OOS role")
        if len({self.design.dataset_id, self.validation.dataset_id, self.oos.dataset_id}) != 1:
            raise ValueError("split reports must use the same dataset")

    @classmethod
    def create(
        cls,
        plan: BacktestSplitPlan,
        *,
        design: BacktestPeriodReport,
        validation: BacktestPeriodReport,
        oos: BacktestPeriodReport,
    ) -> BacktestSplitReport:
        expected = (
            (plan.design, design),
            (plan.validation, validation),
            (plan.oos, oos),
        )
        for period, report in expected:
            if report.dataset_id != plan.dataset.dataset_id:
                raise ValueError("period report dataset does not match split plan")
            if report.period_start != period.start_at or report.period_end != period.end_at:
                raise ValueError("period report bounds do not match split plan")
        return cls(plan.split_id, design, validation, oos)

    @property
    def out_of_sample(self) -> BacktestPeriodReport:
        """Explicit OOS result; never silently merged with design/validation metrics."""

        return self.oos


@dataclass(frozen=True, slots=True)
class WalkForwardReport:
    plan_id: str
    windows: tuple[BacktestSplitReport, ...]

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("plan_id must not be empty")
        if not self.windows:
            raise ValueError("walk-forward report requires at least one window")

    @property
    def oos_reports(self) -> tuple[BacktestPeriodReport, ...]:
        return tuple(window.oos for window in self.windows)


__all__ = [
    "BacktestMetricSnapshot",
    "BacktestPeriodReport",
    "BacktestSplitReport",
    "WalkForwardReport",
]
