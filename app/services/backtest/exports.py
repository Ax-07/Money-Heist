from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from io import StringIO
from typing import Any

from .ids import canonical_json
from .reproducibility import BacktestBusinessFingerprint, fingerprint_backtest


@dataclass(frozen=True, slots=True)
class BacktestRunManifest:
    schema_version: str
    run_id: str
    dataset_id: str
    dataset_version: str
    period_start: datetime
    period_end: datetime
    ai_mode: str
    code_version: str
    execution_model_version: str
    random_seed: int
    business_sha256: str
    evaluation_report_version: str


def build_run_manifest(replay_result: Any, evaluation_bundle: Any) -> BacktestRunManifest:
    run = replay_result.backtest_result.run
    report = evaluation_bundle.report
    fingerprint: BacktestBusinessFingerprint = fingerprint_backtest(replay_result, report)
    return BacktestRunManifest(
        schema_version="money-heist.backtest-manifest.v1",
        run_id=run.run_id,
        dataset_id=run.dataset.dataset_id,
        dataset_version=run.dataset.version,
        period_start=run.period_start,
        period_end=run.period_end,
        ai_mode=str(getattr(run.config.ai_mode, "value", run.config.ai_mode)),
        code_version=run.config.code_version,
        execution_model_version=run.config.execution_model_version,
        random_seed=run.config.random_seed,
        business_sha256=fingerprint.business_sha256,
        evaluation_report_version=report.report_version,
    )


def manifest_to_json(manifest: BacktestRunManifest) -> str:
    return canonical_json(manifest)


def split_report_to_json(report: Any) -> str:
    return canonical_json(report)


def walk_forward_report_to_json(report: Any) -> str:
    return canonical_json(report)


def equity_curve_to_csv(equity_points: Any) -> str:
    stream = StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["observed_at", "equity", "data_kind"])
    for point in sorted(equity_points, key=lambda item: item.observed_at):
        writer.writerow(
            [
                point.observed_at.isoformat(),
                Decimal(str(point.equity)),
                str(
                    getattr(
                        getattr(point, "data_kind", ""),
                        "value",
                        getattr(point, "data_kind", ""),
                    )
                ),
            ]
        )
    return stream.getvalue()


def closed_trades_to_csv(evaluation_report: Any) -> str:
    stream = StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "trade_id",
            "system_id",
            "symbol",
            "side",
            "quantity",
            "entry_price",
            "exit_price",
            "opened_at",
            "closed_at",
            "net_pnl",
            "fees",
            "slippage_cost",
        ]
    )
    trades = sorted(
        evaluation_report.trading.closed_trades,
        key=lambda item: (item.closed_at, item.trade_id),
    )
    for trade in trades:
        writer.writerow(
            [
                trade.trade_id,
                trade.system_id,
                trade.symbol,
                trade.side,
                trade.quantity,
                trade.entry_price,
                trade.exit_price,
                trade.opened_at.isoformat(),
                trade.closed_at.isoformat(),
                trade.net_pnl,
                trade.fees,
                "" if trade.slippage_cost is None else trade.slippage_cost,
            ]
        )
    return stream.getvalue()


__all__ = [
    "BacktestRunManifest",
    "build_run_manifest",
    "closed_trades_to_csv",
    "equity_curve_to_csv",
    "manifest_to_json",
    "split_report_to_json",
    "walk_forward_report_to_json",
]
