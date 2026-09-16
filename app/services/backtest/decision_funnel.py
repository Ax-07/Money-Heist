from __future__ import annotations

from typing import Any

from app.evaluation.decision_funnel import (
    DecisionFunnelObservationCounts,
    DecisionFunnelReport,
    aggregate_decision_funnel,
)


def build_decision_funnel_report(
    replay_result: Any,
    evaluation_bundle: Any,
) -> DecisionFunnelReport:
    """Adapt one completed Historical Replay to the generic post-hoc funnel aggregator."""

    run = replay_result.backtest_result.run
    raw_observation_counts = getattr(replay_result, "observation_counts", None)
    observation_counts = DecisionFunnelObservationCounts(
        pre_scanner_warmup_skipped=int(
            getattr(raw_observation_counts, "pre_scanner_warmup_skipped", 0)
        ),
        pre_scanner_not_decision_close_skipped=int(
            getattr(
                raw_observation_counts,
                "pre_scanner_not_decision_close_skipped",
                0,
            )
        ),
    )
    report = evaluation_bundle.report
    trading = report.trading
    source = evaluation_bundle.source
    return aggregate_decision_funnel(
        run_id=run.run_id,
        dataset_id=run.dataset.dataset_id,
        dataset_version=run.dataset.version,
        system_id=run.config.system_id,
        period_start=run.period_start,
        period_end=run.period_end,
        candles_evaluated=replay_result.backtest_result.processed_candles,
        observation_counts=observation_counts,
        replay_points=replay_result.points,
        closed_trades=int(trading.closed_trade_count),
        broker_executions=source.executions,
    )


__all__ = ["DecisionFunnelReport", "build_decision_funnel_report"]
