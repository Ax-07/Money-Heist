from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.agents.models import DenverAnalysis, DenverContext, RioAnalysis, RioContext
from app.dashboard.backtest import (
    AIInput,
    BacktestDashboardService,
    CampaignRequest,
    DatasetInput,
    ExecutionInput,
    MarketConstraintsInput,
    RiskInput,
    SplitInput,
    WalkForwardInput,
    DeterministicBacktestMockProvider,
)
from app.intelligence.ai_gateway.models import ProviderRequest
from app.market.exchange.kraken_futures import (
    KrakenFuturesAnalyticsConfig,
    KrakenFuturesAnalyticsProvider,
)
from app.market.exchange.transport import (
    ResilientPublicHttpClient,
    RetryPolicy,
    StdlibJsonTransport,
)
from app.services.backtest import (
    BacktestAIMode,
    BacktestPeriodRole,
    DenverSetupStatsContextProvider,
    HistoricalSetupStatsCatalog,
    observations_from_historical_replay,
)
from app.services.backtest.advanced_mock import (
    DeterministicAdvancedSpecialistMockProvider,
)
from app.services.orchestration.rio_contexts import KrakenFuturesRioContextProvider


class CapturingBacktestDashboardService(BacktestDashboardService):
    """Smoke-only service that retains internal run executions for Denver validation."""

    def __init__(self) -> None:
        super().__init__(history_limit=5)
        self.captured_executions: dict[BacktestPeriodRole, object] = {}

    async def _execute_run(self, **kwargs):  # type: ignore[override]
        execution = await super()._execute_run(**kwargs)
        role = kwargs["role"]
        self.captured_executions[role] = execution
        return execution


def quick_split_indices(
    candle_count: int,
    target_test_bars: int = 100,
) -> tuple[int, int, int, int]:
    warmup_bars = 35
    minimum_test_bars = 6

    if candle_count < warmup_bars + minimum_test_bars:
        raise ValueError(
            f"need at least {warmup_bars + minimum_test_bars} candles; got {candle_count}"
        )

    start = warmup_bars
    test_bars = min(target_test_bars, candle_count - start)
    design_bars = max(1, int(test_bars * 0.60))
    validation_boundary_bars = max(design_bars + 1, int(test_bars * 0.80))

    design_end = start + design_bars - 1
    validation_end = start + validation_boundary_bars - 1
    end = start + test_bars - 1
    return start, design_end, validation_end, end


def quick_split(preview, target_test_bars: int = 100) -> SplitInput:
    axis = preview.candle_close_ms
    start, design_end, validation_end, end = quick_split_indices(
        preview.candle_count,
        target_test_bars,
    )

    def at(index: int) -> datetime:
        return datetime.fromtimestamp(axis[index] / 1000, tz=UTC)

    return SplitInput(
        design_start=at(start),
        design_end=at(design_end),
        validation_start=at(design_end + 1),
        validation_end=at(validation_end),
        oos_start=at(validation_end + 1),
        oos_end=at(end),
    )



def denver_attempt_sizes(candle_count: int) -> tuple[int, ...]:
    warmup_bars = 35
    available = candle_count - warmup_bars
    if available < 6:
        return ()

    candidates = (100, 200, 400, 800, available)
    return tuple(
        size
        for index, size in enumerate(candidates)
        if 6 <= size <= available and size not in candidates[:index]
    )

def _json_dumps(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        default=lambda value: value.isoformat()
        if hasattr(value, "isoformat")
        else str(value),
    )


async def _advanced_mock_analysis(
    *,
    schema_name: str,
    agent_id: str,
    specialist_context: dict,
) -> str:
    provider = DeterministicAdvancedSpecialistMockProvider(
        DeterministicBacktestMockProvider()
    )
    request = ProviderRequest(
        request_id=uuid4(),
        system_id="balanced_v1",
        agent_id=agent_id,
        model_id="mock-backtest-v1",
        input_text=_json_dumps({"specialist_context": specialist_context}),
        schema_name=schema_name,
        json_schema={},
        max_output_tokens=1200,
        timeout_seconds=5,
    )
    response = await provider.complete(request)
    return response.output_text


async def smoke_denver(
    *,
    csv_path: Path,
    symbol: str,
    timeframe: str,
    source: str,
) -> None:
    print("\n=== DENVER / HISTORICAL SETUP STATS ===")
    csv_text = csv_path.read_text(encoding="utf-8-sig")

    dataset = DatasetInput(
        csv_text=csv_text,
        symbol=symbol,
        timeframe=timeframe,
        source=source,
    )
    preview_service = CapturingBacktestDashboardService()
    preview = preview_service.preview_dataset(dataset)
    if not preview.is_valid:
        raise RuntimeError("dataset is invalid; Denver smoke test aborted")

    attempts = denver_attempt_sizes(preview.candle_count)
    if not attempts:
        raise RuntimeError("dataset is too short for the Denver smoke test")

    observation = None
    source_execution = None
    total_closed = 0
    total_ambiguous = 0

    for target_bars in attempts:
        service = CapturingBacktestDashboardService()
        request = CampaignRequest(
            dataset=dataset,
            split=quick_split(preview, target_bars),
            risk=RiskInput(),
            market=MarketConstraintsInput(
                qty_step=Decimal("0.00001"),
                min_qty=Decimal("0.00001"),
                min_notional=Decimal("5"),
                max_qty=Decimal("9000"),
                max_leverage=Decimal("1"),
            ),
            ai=AIInput(
                mode=BacktestAIMode.MOCK,
                model_id="mock-backtest-v1",
                hard_budget_eur=Decimal("1"),
            ),
            execution=ExecutionInput(
                initial_balance=Decimal("100"),
                code_version="batch16.11-v3-advanced-specialist-smoke",
            ),
            walk_forward=WalkForwardInput(enabled=False),
        )

        summary = await service.run_campaign(request)
        attempt_closed = 0
        attempt_ambiguous = 0

        for role in BacktestPeriodRole:
            execution = service.captured_executions[role]
            for trade in execution.evaluation.report.trading.closed_trades:
                attempt_closed += 1
                single_trade_evaluation = SimpleNamespace(
                    report=SimpleNamespace(
                        trading=SimpleNamespace(closed_trades=(trade,))
                    )
                )
                try:
                    resolved = observations_from_historical_replay(
                        execution.replay,
                        single_trade_evaluation,
                        period_role=role,
                    )
                except ValueError as exc:
                    if "cannot be attributed to exactly one setup entry" not in str(exc):
                        raise
                    attempt_ambiguous += 1
                    continue

                if len(resolved) != 1:
                    raise RuntimeError(
                        "strict Denver attribution returned an unexpected observation count"
                    )
                observation = resolved[0]
                source_execution = execution
                break
            if observation is not None:
                break

        total_closed += attempt_closed
        total_ambiguous += attempt_ambiguous

        print(
            "attempt:",
            target_bars,
            "bars | campaign:",
            summary.campaign_id,
            "| closed_trades_seen:",
            attempt_closed,
            "| ambiguous_skipped:",
            attempt_ambiguous,
            "| strict_observation:",
            "YES" if observation is not None else "NO",
        )

        if observation is not None:
            break

    if observation is None or source_execution is None:
        raise RuntimeError(
            "Denver smoke test found no strictly attributable closed trade across "
            f"{len(attempts)} replay windows "
            f"(closed={total_closed}, ambiguous={total_ambiguous}). "
            "This strategy/dataset produces only position outcomes that Denver v1 "
            "cannot assign to one setup without guessing. Production attribution "
            "remains fail-closed."
        )

    catalog = HistoricalSetupStatsCatalog((observation,))
    print("catalog:", catalog.catalog_id)

    point = next(
        point
        for point in source_execution.replay.points
        if point.opportunity is not None
        and point.opportunity.opportunity_id == observation.opportunity_id
    )

    market_after_close = point.feature_snapshot.model_copy(
        update={"observed_at": max(point.feature_snapshot.observed_at, observation.closed_at)}
    )
    provider = DenverSetupStatsContextProvider(catalog)
    contexts = provider.contexts_for(
        opportunity=point.opportunity,
        market_context=market_after_close,
    )
    if "denver" not in contexts:
        raise RuntimeError("grounded Denver context was not available for the selected setup")

    denver_context = DenverContext.model_validate(contexts["denver"])
    payload = denver_context.model_dump(mode="json", exclude_none=True)
    payload["sample_size_band"] = denver_context.sample_size_band

    output_text = await _advanced_mock_analysis(
        schema_name="DenverAnalysis",
        agent_id="denver",
        specialist_context=payload,
    )
    analysis = DenverAnalysis.model_validate_json(output_text)

    print("stats_id:", denver_context.stats_id)
    print("sample_count:", denver_context.sample_count)
    print("sample_size_band:", denver_context.sample_size_band)
    print("expectancy:", denver_context.expectancy)
    print("profit_factor:", denver_context.profit_factor)
    print(
        "analysis:",
        analysis.stance.value,
        "| historical_edge:",
        analysis.historical_edge,
        "| robustness:",
        analysis.robustness,
    )
    print("DENVER_SMOKE=PASS")


def kraken_config_for_symbol(symbol: str) -> KrakenFuturesAnalyticsConfig:
    normalized = symbol.strip().upper()
    base = normalized.split("/", 1)[0] if "/" in normalized else normalized
    if base != "BTC":
        raise ValueError(
            "this smoke harness currently maps only BTC spot symbols to PF_XBTUSD"
        )
    return KrakenFuturesAnalyticsConfig(
        interval_seconds=300,
        symbol_map=((normalized, "PF_XBTUSD"),),
    )


async def smoke_rio(*, symbol: str) -> None:
    print("\n=== RIO / LIVE PUBLIC KRAKEN FUTURES CONTEXT ===")
    http = ResilientPublicHttpClient(
        StdlibJsonTransport(user_agent="money-heist-rio-smoke/1"),
        policy=RetryPolicy(
            timeout_seconds=5,
            max_attempts=2,
            base_backoff_seconds=0.25,
            max_backoff_seconds=1.0,
            min_request_interval_seconds=0.20,
        ),
    )
    analytics = KrakenFuturesAnalyticsProvider(
        http,
        config=kraken_config_for_symbol(symbol),
    )
    provider = KrakenFuturesRioContextProvider(analytics)

    snapshot = await provider.refresh(symbol)
    decision_time = datetime.now(UTC)
    contexts = provider.contexts_for(
        opportunity=SimpleNamespace(symbol=symbol),
        market_context=SimpleNamespace(symbol=symbol, observed_at=decision_time),
    )
    if "rio" not in contexts:
        diagnostic = provider.diagnostic_for(
            symbol=symbol,
            decision_time=decision_time,
        )
        raise RuntimeError(f"Rio context unavailable: {diagnostic}")

    rio_context = contexts["rio"]
    if not isinstance(rio_context, RioContext):
        rio_context = RioContext.model_validate(rio_context)

    output_text = await _advanced_mock_analysis(
        schema_name="RioAnalysis",
        agent_id="rio",
        specialist_context=rio_context.model_dump(mode="json", exclude_none=True),
    )
    analysis = RioAnalysis.model_validate_json(output_text)

    print("source:", rio_context.source)
    print("instrument:", rio_context.instrument)
    print("observed_at:", rio_context.observed_at.isoformat())
    print("data_quality:", rio_context.data_quality)
    print("funding_rate:", rio_context.funding_rate)
    print("open_interest:", rio_context.open_interest)
    print("open_interest_change_pct:", rio_context.open_interest_change_pct)
    print("long_short_ratio:", rio_context.long_short_ratio)
    print("missing_fields:", ", ".join(rio_context.missing_fields) or "none")
    print(
        "analysis:",
        analysis.stance.value,
        "| funding:",
        analysis.funding_state,
        "| OI:",
        analysis.open_interest_state,
        "| quality:",
        analysis.data_quality,
    )
    print("RIO_SMOKE=PASS")


async def async_main(args: argparse.Namespace) -> None:
    csv_path = Path(args.csv).resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)

    if not args.skip_denver:
        await smoke_denver(
            csv_path=csv_path,
            symbol=args.symbol,
            timeframe=args.timeframe,
            source=args.source,
        )
    if not args.skip_rio_live:
        await smoke_rio(symbol=args.symbol)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Grounded smoke validation for Denver historical statistics and "
            "Rio public Kraken Futures context. No live trading."
        )
    )
    parser.add_argument("--csv", required=True, help="Path to the OHLCV CSV used by the dashboard")
    parser.add_argument("--symbol", default="BTC/USDC")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--source", default="binance_spot_csv")
    parser.add_argument(
        "--skip-denver",
        action="store_true",
        help="Skip historical Denver integration and run Rio only",
    )
    parser.add_argument(
        "--skip-rio-live",
        action="store_true",
        help="Run only Denver and avoid public network access",
    )
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
