from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.dashboard.backtest import (
    AIInput,
    BacktestAIMode,
    BacktestDashboardService,
    CampaignRequest,
    DatasetInput,
    ExecutionInput,
    MarketConstraintsInput,
    RiskInput,
    SplitInput,
)


def test_campaign_budget_is_created_once_and_reused_for_walk_forward() -> None:
    run_campaign = inspect.getsource(BacktestDashboardService.run_campaign)
    execute_run = inspect.getsource(BacktestDashboardService._execute_run)

    assert run_campaign.count("campaign_budget = AIBudgetLedger(request.ai.hard_budget_eur)") == 1
    assert run_campaign.count("budget=campaign_budget") == 2
    assert "AIBudgetLedger(" not in execute_run


def test_reasoning_effort_is_versioned_in_backtest_assumptions() -> None:
    source = inspect.getsource(BacktestDashboardService._backtest_config)
    assert '"ai_reasoning_effort": request.ai.reasoning_effort' in source


def test_live_eval_rejects_stale_default_code_version() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    split = SplitInput(
        design_start=start,
        design_end=start + timedelta(hours=1),
        validation_start=start + timedelta(hours=2),
        validation_end=start + timedelta(hours=3),
        oos_start=start + timedelta(hours=4),
        oos_end=start + timedelta(hours=5),
    )

    with pytest.raises(ValidationError, match="immutable execution.code_version"):
        CampaignRequest(
            dataset=DatasetInput(csv_text="x"),
            split=split,
            risk=RiskInput(),
            market=MarketConstraintsInput(
                qty_step=Decimal("0.001"),
                min_qty=Decimal("0.001"),
                min_notional=Decimal("1"),
            ),
            ai=AIInput(
                mode=BacktestAIMode.LIVE_EVAL,
                model_id="gpt-5.6-luna",
                input_per_million_eur=Decimal("1"),
                output_per_million_eur=Decimal("1"),
            ),
            execution=ExecutionInput(),
        )
