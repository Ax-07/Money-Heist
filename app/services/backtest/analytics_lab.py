from __future__ import annotations

from app.analytics import (
    AnalyticsAsOfInput,
    AnalyticsComponentVersions,
    AnalyticsLabRun,
    AnalyticsPeriodRole,
)
from app.market.multitimeframe import HistoricalMultiTimeframeCursorState

from .models import BacktestRun
from .splits import BacktestPeriodRole


def _period_role(role: BacktestPeriodRole | AnalyticsPeriodRole | str) -> AnalyticsPeriodRole:
    if isinstance(role, AnalyticsPeriodRole):
        return role
    value = getattr(role, "value", role)
    try:
        return AnalyticsPeriodRole(str(value))
    except ValueError as exc:
        raise ValueError("period_role must be DESIGN, VALIDATION, or OOS") from exc


def _assumption(run: BacktestRun, key: str, explicit: str | None) -> str:
    if explicit is not None:
        value = explicit.strip()
        if not value:
            raise ValueError(f"{key} must not be empty")
        configured = run.config.execution_assumptions.get(key)
        if configured is not None and configured != value:
            raise ValueError(f"{key} conflicts with source BacktestRun assumptions")
        return value
    configured = str(run.config.execution_assumptions.get(key, "")).strip()
    if not configured:
        raise ValueError(f"source BacktestRun does not declare {key}")
    return configured


def build_analytics_lab_run(
    source_run: BacktestRun,
    *,
    period_role: BacktestPeriodRole | AnalyticsPeriodRole | str,
    component_versions: AnalyticsComponentVersions,
    decision_timeframe: str | None = None,
    mtf_policy_version: str | None = None,
) -> AnalyticsLabRun:
    """Derive an observation-only Analytics identity from one BacktestRun."""

    decision = _assumption(source_run, "decision_timeframe", decision_timeframe)
    policy = _assumption(source_run, "mtf_policy_version", mtf_policy_version)
    source_timeframe = str(
        source_run.config.execution_assumptions.get(
            "historical_source_timeframe",
            source_run.dataset.timeframe,
        )
    ).strip()
    if source_timeframe != source_run.dataset.timeframe:
        raise ValueError("historical source timeframe conflicts with DatasetRef")

    return AnalyticsLabRun.create(
        source_backtest_run_id=source_run.run_id,
        dataset_id=source_run.dataset.dataset_id,
        dataset_version=source_run.dataset.version,
        dataset_content_sha256=source_run.dataset.content_sha256,
        dataset_source=source_run.dataset.source,
        system_id=source_run.config.system_id,
        symbol=source_run.dataset.symbol,
        source_timeframe=source_timeframe,
        decision_timeframe=decision,
        period_start=source_run.period_start,
        period_end=source_run.period_end,
        period_role=_period_role(period_role),
        mtf_policy_version=policy,
        component_versions=component_versions,
    )


def build_analytics_as_of_input(
    source_run: BacktestRun,
    cursor_state: HistoricalMultiTimeframeCursorState,
    *,
    decision_timeframe: str | None = None,
) -> AnalyticsAsOfInput:
    """Bind Analytics to the exact causal MTF universe already visible in replay."""

    decision = _assumption(source_run, "decision_timeframe", decision_timeframe)
    policy = _assumption(source_run, "mtf_policy_version", cursor_state.policy_version)
    if cursor_state.symbol != source_run.dataset.symbol:
        raise ValueError("MTF cursor symbol does not match DatasetRef")
    if cursor_state.source_timeframe != source_run.dataset.timeframe:
        raise ValueError("MTF cursor source timeframe does not match DatasetRef")
    if not source_run.period_start <= cursor_state.as_of <= source_run.period_end:
        raise ValueError("MTF cursor as_of must stay inside the source BacktestRun period")
    if decision not in cursor_state.target_timeframes:
        raise ValueError("decision timeframe is not present in the MTF cursor")

    return AnalyticsAsOfInput(
        source_backtest_run_id=source_run.run_id,
        dataset_id=source_run.dataset.dataset_id,
        dataset_version=source_run.dataset.version,
        dataset_content_sha256=source_run.dataset.content_sha256,
        dataset_source=source_run.dataset.source,
        system_id=source_run.config.system_id,
        symbol=source_run.dataset.symbol,
        source_timeframe=cursor_state.source_timeframe,
        decision_timeframe=decision,
        as_of=cursor_state.as_of,
        mtf_policy_version=policy,
        source_cursor_fingerprint=cursor_state.cursor_fingerprint,
    )


__all__ = ["build_analytics_as_of_input", "build_analytics_lab_run"]
