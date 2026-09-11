from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.market.features.models import FeatureQuality, FeatureSnapshot, MarketRegime
from app.market.scanner.models import CandidateOpportunity, ScannerTrigger
from app.services.backtest.setup_stats import (
    DenverSetupStatsContextProvider,
    HistoricalSetupKey,
    HistoricalSetupObservation,
    HistoricalSetupStatsCatalog,
    observations_from_historical_replay,
)
from app.services.backtest.splits import BacktestPeriodRole


def make_market(*, observed_at: datetime | None = None) -> FeatureSnapshot:
    timestamp = observed_at or datetime(2026, 2, 1, tzinfo=UTC)
    return FeatureSnapshot(
        feature_version="features-v1",
        snapshot_id="snapshot-1",
        symbol="BTC/EUR",
        timeframe="1h",
        observed_at=timestamp,
        candle_count=100,
        close=100.0,
        regime=MarketRegime.BULLISH_TREND,
        quality=FeatureQuality(warmup_complete=True, closed_candle_count=100),
    )


def make_opportunity() -> CandidateOpportunity:
    created_at = datetime(2026, 2, 1, tzinfo=UTC)
    return CandidateOpportunity(
        scanner_version="scanner-v1",
        opportunity_id=str(uuid4()),
        snapshot_id="snapshot-1",
        system_id="balanced_v1",
        symbol="BTC/EUR",
        timeframe="1h",
        priority_score=80,
        triggers=(ScannerTrigger.RANGE_BREAK, ScannerTrigger.VOLUME_EXPANSION),
        created_at=created_at,
        expires_at=created_at + timedelta(hours=1),
    )


def observation(
    *,
    opportunity: CandidateOpportunity,
    market: FeatureSnapshot,
    trade_id: str,
    closed_at: datetime,
    net_pnl: str,
    period_role: BacktestPeriodRole = BacktestPeriodRole.DESIGN,
) -> HistoricalSetupObservation:
    return HistoricalSetupObservation(
        run_id=f"run-{trade_id}",
        dataset_id="dataset-1",
        strategy_fingerprint="strategy-1",
        period_role=period_role,
        opportunity_id=f"{opportunity.opportunity_id}:{trade_id}",
        trade_id=trade_id,
        setup=HistoricalSetupKey.from_market(opportunity, market),
        side="LONG",
        opened_at=closed_at - timedelta(hours=1),
        closed_at=closed_at,
        net_pnl=Decimal(net_pnl),
    )


def test_catalog_query_uses_only_closed_samples_available_as_of() -> None:
    market = make_market()
    opportunity = make_opportunity()
    first_close = datetime(2026, 1, 1, tzinfo=UTC)
    future_close = datetime(2026, 3, 1, tzinfo=UTC)
    catalog = HistoricalSetupStatsCatalog(
        (
            observation(
                opportunity=opportunity,
                market=market,
                trade_id="win",
                closed_at=first_close,
                net_pnl="3",
            ),
            observation(
                opportunity=opportunity,
                market=market,
                trade_id="future-loss",
                closed_at=future_close,
                net_pnl="-1",
                period_role=BacktestPeriodRole.OOS,
            ),
        )
    )

    before_future = catalog.query(
        opportunity=opportunity,
        market_context=market,
        as_of=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert before_future is not None
    assert before_future.sample_count == 1
    assert before_future.oos_sample_count == 0
    assert before_future.win_rate == Decimal("1")
    assert before_future.expectancy == Decimal("3")
    assert before_future.profit_factor is None
    assert before_future.profit_factor_status == "UNBOUNDED_NO_LOSSES"

    after_future = catalog.query(
        opportunity=opportunity,
        market_context=market,
        as_of=datetime(2026, 4, 1, tzinfo=UTC),
    )
    assert after_future is not None
    assert after_future.sample_count == 2
    assert after_future.oos_sample_count == 1
    assert after_future.win_rate == Decimal("0.5")
    assert after_future.expectancy == Decimal("1")
    assert after_future.profit_factor == Decimal("3")
    assert after_future.stats_id != before_future.stats_id


def test_catalog_is_content_addressed_and_round_trips_canonically() -> None:
    market = make_market()
    opportunity = make_opportunity()
    catalog = HistoricalSetupStatsCatalog(
        (
            observation(
                opportunity=opportunity,
                market=market,
                trade_id="a",
                closed_at=datetime(2026, 1, 1, tzinfo=UTC),
                net_pnl="2.5",
                period_role=BacktestPeriodRole.VALIDATION,
            ),
        )
    )

    restored = HistoricalSetupStatsCatalog.from_json(catalog.to_json())
    assert restored.catalog_id == catalog.catalog_id
    assert restored.to_json() == catalog.to_json()
    assert restored.reproducibility_assumptions == {
        "denver_setup_stats_catalog_id": catalog.catalog_id,
        "denver_setup_definition_version": "scanner-regime-v1",
        "denver_source_strategy_fingerprint": "strategy-1",
    }


def test_catalog_tamper_is_rejected() -> None:
    market = make_market()
    opportunity = make_opportunity()
    catalog = HistoricalSetupStatsCatalog(
        (
            observation(
                opportunity=opportunity,
                market=market,
                trade_id="a",
                closed_at=datetime(2026, 1, 1, tzinfo=UTC),
                net_pnl="2.5",
            ),
        )
    )
    payload = catalog.to_json().replace('"2.5"', '"99"')
    with pytest.raises(ValueError, match="catalog_id"):
        HistoricalSetupStatsCatalog.from_json(payload)


def test_context_provider_returns_real_denver_payload_for_matching_setup() -> None:
    market = make_market()
    opportunity = make_opportunity()
    catalog = HistoricalSetupStatsCatalog(
        (
            observation(
                opportunity=opportunity,
                market=market,
                trade_id="a",
                closed_at=datetime(2026, 1, 1, tzinfo=UTC),
                net_pnl="2",
            ),
            observation(
                opportunity=opportunity,
                market=market,
                trade_id="b",
                closed_at=datetime(2026, 1, 2, tzinfo=UTC),
                net_pnl="-1",
            ),
        )
    )

    provider = DenverSetupStatsContextProvider(catalog)
    contexts = provider.contexts_for(opportunity=opportunity, market_context=market)
    denver = contexts["denver"]
    assert denver["sample_count"] == 2
    assert denver["win_rate"] == 0.5
    assert denver["expectancy"] == 0.5
    assert denver["profit_factor"] == 2.0
    assert denver["max_drawdown_pct"] is None
    assert denver["regime"] == "bullish_trend"
    assert any(note.startswith("setup_id=") for note in denver["notes"])


def test_non_matching_setup_does_not_advertise_denver() -> None:
    market = make_market()
    opportunity = make_opportunity()
    catalog = HistoricalSetupStatsCatalog(
        (
            observation(
                opportunity=opportunity,
                market=market,
                trade_id="a",
                closed_at=datetime(2026, 1, 1, tzinfo=UTC),
                net_pnl="2",
            ),
        )
    )
    other = opportunity.model_copy(update={"system_id": "other-system"})
    provider = DenverSetupStatsContextProvider(catalog)
    assert provider.contexts_for(opportunity=other, market_context=market) == {}




def test_backtest_provider_requires_catalog_identity_in_execution_assumptions() -> None:
    market = make_market()
    opportunity = make_opportunity()
    catalog = HistoricalSetupStatsCatalog(
        (
            observation(
                opportunity=opportunity,
                market=market,
                trade_id="a",
                closed_at=datetime(2026, 1, 1, tzinfo=UTC),
                net_pnl="2",
            ),
        )
    )
    empty_config = SimpleNamespace(execution_assumptions={})
    with pytest.raises(ValueError, match="does not bind Denver catalog"):
        DenverSetupStatsContextProvider.for_backtest(catalog, config=empty_config)

    bound_config = SimpleNamespace(execution_assumptions=catalog.reproducibility_assumptions)
    provider = DenverSetupStatsContextProvider.for_backtest(catalog, config=bound_config)
    assert provider.reproducibility_assumptions == catalog.reproducibility_assumptions
    assert "denver" in provider.contexts_for(
        opportunity=opportunity,
        market_context=market,
    )


def test_catalog_rejects_duplicate_market_opportunity_from_reruns() -> None:
    market = make_market()
    opportunity = make_opportunity()
    first = observation(
        opportunity=opportunity,
        market=market,
        trade_id="run-a-trade",
        closed_at=datetime(2026, 1, 1, tzinfo=UTC),
        net_pnl="1",
    )
    second = HistoricalSetupObservation(
        run_id="run-b",
        dataset_id="dataset-2",
        strategy_fingerprint=first.strategy_fingerprint,
        period_role=BacktestPeriodRole.VALIDATION,
        opportunity_id=first.opportunity_id,
        trade_id="run-b-trade",
        setup=first.setup,
        side=first.side,
        opened_at=datetime(2026, 1, 1, tzinfo=UTC),
        closed_at=datetime(2026, 1, 1, 1, tzinfo=UTC),
        net_pnl=Decimal("1"),
    )
    with pytest.raises(ValueError, match="double-count"):
        HistoricalSetupStatsCatalog((first, second))

def test_catalog_rejects_mixed_strategy_fingerprints() -> None:
    market = make_market()
    opportunity = make_opportunity()
    first = observation(
        opportunity=opportunity,
        market=market,
        trade_id="a",
        closed_at=datetime(2026, 1, 1, tzinfo=UTC),
        net_pnl="1",
    )
    second = HistoricalSetupObservation(
        run_id="run-b",
        dataset_id=first.dataset_id,
        strategy_fingerprint="strategy-2",
        period_role=BacktestPeriodRole.VALIDATION,
        opportunity_id="other-opportunity",
        trade_id="b",
        setup=first.setup,
        side="LONG",
        opened_at=datetime(2026, 1, 2, tzinfo=UTC),
        closed_at=datetime(2026, 1, 3, tzinfo=UTC),
        net_pnl=Decimal("1"),
    )
    with pytest.raises(ValueError, match="strategy fingerprints"):
        HistoricalSetupStatsCatalog((first, second))

def test_batch16_closed_trade_is_joined_to_exact_executed_setup() -> None:
    market = make_market(observed_at=datetime(2026, 1, 5, tzinfo=UTC))
    opportunity = make_opportunity()
    entry_at = datetime(2026, 1, 5, tzinfo=UTC)
    proposal = SimpleNamespace(side="LONG")
    orchestration = SimpleNamespace(trade_proposal=proposal)
    pipeline_result = SimpleNamespace(
        orchestration_result=orchestration,
        order=SimpleNamespace(side=SimpleNamespace(value="BUY")),
        fill=SimpleNamespace(
            price=Decimal("100"),
            quantity=Decimal("0.5"),
            filled_at=entry_at,
        ),
    )
    point = SimpleNamespace(
        opportunity=opportunity,
        feature_snapshot=market,
        pipeline_result=pipeline_result,
    )
    run = SimpleNamespace(
        run_id="run-real-1",
        dataset=SimpleNamespace(dataset_id="dataset-real-1"),
        config=SimpleNamespace(
            canonical_payload=lambda: {"system_id": "balanced_v1", "code_version": "test"}
        ),
    )
    replay = SimpleNamespace(
        backtest_result=SimpleNamespace(run=run),
        points=(point,),
    )
    trade = SimpleNamespace(
        trade_id="closed-1",
        system_id="balanced_v1",
        symbol="BTC/EUR",
        side="LONG",
        quantity=Decimal("0.5"),
        entry_price=Decimal("100"),
        opened_at=entry_at,
        closed_at=entry_at + timedelta(hours=4),
        net_pnl=Decimal("1.75"),
    )
    evaluation = SimpleNamespace(
        report=SimpleNamespace(trading=SimpleNamespace(closed_trades=(trade,)))
    )

    observations = observations_from_historical_replay(
        replay,
        evaluation,
        period_role=BacktestPeriodRole.OOS,
    )
    assert len(observations) == 1
    item = observations[0]
    assert item.run_id == "run-real-1"
    assert item.dataset_id == "dataset-real-1"
    assert item.period_role is BacktestPeriodRole.OOS
    assert item.opportunity_id == opportunity.opportunity_id
    assert item.net_pnl == Decimal("1.75")
    assert item.setup.regime == "bullish_trend"
    assert item.setup.scanner_version == "scanner-v1"
    assert item.setup.feature_version == "features-v1"
    assert item.setup.triggers == ("range_break", "volume_expansion")
    assert item.strategy_fingerprint.startswith("strategy:")


def test_ambiguous_scaled_trade_attribution_fails_closed() -> None:
    market = make_market(observed_at=datetime(2026, 1, 5, tzinfo=UTC))
    opportunity = make_opportunity()
    entry_at = datetime(2026, 1, 5, tzinfo=UTC)
    pipeline_result = SimpleNamespace(
        orchestration_result=SimpleNamespace(trade_proposal=SimpleNamespace(side="LONG")),
        order=SimpleNamespace(side=SimpleNamespace(value="BUY")),
        fill=SimpleNamespace(
            price=Decimal("100"),
            quantity=Decimal("1"),
            filled_at=entry_at,
        ),
    )
    replay = SimpleNamespace(
        backtest_result=SimpleNamespace(
            run=SimpleNamespace(
                run_id="run-real-1",
                dataset=SimpleNamespace(dataset_id="dataset-real-1"),
                config=SimpleNamespace(
                    canonical_payload=lambda: {
                        "system_id": "balanced_v1",
                        "code_version": "test",
                    }
                ),
            )
        ),
        points=(
            SimpleNamespace(
                opportunity=opportunity,
                feature_snapshot=market,
                pipeline_result=pipeline_result,
            ),
        ),
    )
    trade = SimpleNamespace(
        trade_id="scaled-close",
        system_id="balanced_v1",
        symbol="BTC/EUR",
        side="LONG",
        quantity=Decimal("0.5"),
        entry_price=Decimal("100"),
        opened_at=entry_at,
        closed_at=entry_at + timedelta(hours=4),
        net_pnl=Decimal("1"),
    )
    evaluation = SimpleNamespace(
        report=SimpleNamespace(trading=SimpleNamespace(closed_trades=(trade,)))
    )

    with pytest.raises(ValueError, match="exactly one setup entry"):
        observations_from_historical_replay(
            replay,
            evaluation,
            period_role=BacktestPeriodRole.DESIGN,
        )


def test_ambiguous_attribution_uses_dedicated_denver_exception() -> None:
    from app.services.backtest.setup_stats import (
        HistoricalSetupAttributionError,
    )

    market = make_market(observed_at=datetime(2026, 1, 5, tzinfo=UTC))
    opportunity = make_opportunity()
    entry_at = datetime(2026, 1, 5, tzinfo=UTC)
    pipeline_result = SimpleNamespace(
        orchestration_result=SimpleNamespace(
            trade_proposal=SimpleNamespace(side="LONG")
        ),
        order=SimpleNamespace(side=SimpleNamespace(value="BUY")),
        fill=SimpleNamespace(
            price=Decimal("100"),
            quantity=Decimal("1"),
            filled_at=entry_at,
        ),
    )
    replay = SimpleNamespace(
        backtest_result=SimpleNamespace(
            run=SimpleNamespace(
                run_id="run-real-1",
                dataset=SimpleNamespace(dataset_id="dataset-real-1"),
                config=SimpleNamespace(
                    canonical_payload=lambda: {
                        "system_id": "balanced_v1",
                        "code_version": "test",
                    }
                ),
            )
        ),
        points=(
            SimpleNamespace(
                opportunity=opportunity,
                feature_snapshot=market,
                pipeline_result=pipeline_result,
            ),
        ),
    )
    trade = SimpleNamespace(
        trade_id="scaled-close",
        system_id="balanced_v1",
        symbol="BTC/EUR",
        side="LONG",
        quantity=Decimal("0.5"),
        entry_price=Decimal("100"),
        opened_at=entry_at,
        closed_at=entry_at + timedelta(hours=4),
        net_pnl=Decimal("1"),
    )
    evaluation = SimpleNamespace(
        report=SimpleNamespace(
            trading=SimpleNamespace(closed_trades=(trade,))
        )
    )

    with pytest.raises(HistoricalSetupAttributionError):
        observations_from_historical_replay(
            replay,
            evaluation,
            period_role=BacktestPeriodRole.DESIGN,
        )
