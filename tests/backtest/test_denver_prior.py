from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.market.features.models import (
    FeatureQuality,
    FeatureSnapshot,
    MarketRegime,
)
from app.market.scanner.models import (
    CandidateOpportunity,
    ScannerTrigger,
)
from app.services.backtest.denver_prior import (
    DenverPriorPolicy,
    FrozenDenverPriorCatalog,
    FrozenDenverPriorContextProvider,
    freeze_denver_prior,
)
from app.services.backtest.setup_stats import (
    HistoricalSetupKey,
    HistoricalSetupObservation,
    HistoricalSetupStatsCatalog,
)
from app.services.backtest.splits import BacktestPeriodRole


BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _market(*, observed_at: datetime) -> FeatureSnapshot:
    return FeatureSnapshot(
        feature_version="features-v1",
        snapshot_id="snapshot-1",
        symbol="BTC/USDC",
        timeframe="1h",
        observed_at=observed_at,
        candle_count=100,
        close=100.0,
        regime=MarketRegime.BULLISH_TREND,
        quality=FeatureQuality(
            warmup_complete=True,
            closed_candle_count=100,
        ),
    )


def _opportunity() -> CandidateOpportunity:
    return CandidateOpportunity(
        scanner_version="scanner-v1",
        opportunity_id=str(uuid4()),
        snapshot_id="snapshot-1",
        system_id="balanced_v1",
        symbol="BTC/USDC",
        timeframe="1h",
        priority_score=80,
        triggers=(
            ScannerTrigger.RANGE_BREAK,
            ScannerTrigger.VOLUME_EXPANSION,
        ),
        created_at=BASE,
        expires_at=BASE + timedelta(hours=1),
    )


def _observation(
    *,
    opportunity: CandidateOpportunity,
    setup_market: FeatureSnapshot,
    name: str,
    closed_at: datetime,
    role: BacktestPeriodRole,
    pnl: str,
) -> HistoricalSetupObservation:
    return HistoricalSetupObservation(
        run_id=f"run-{name}",
        dataset_id="dataset-btc",
        strategy_fingerprint="strategy-frozen-1",
        period_role=role,
        opportunity_id=f"{opportunity.opportunity_id}:{name}",
        trade_id=f"trade-{name}",
        setup=HistoricalSetupKey.from_market(
            opportunity,
            setup_market,
        ),
        side="LONG",
        opened_at=closed_at - timedelta(hours=1),
        closed_at=closed_at,
        net_pnl=Decimal(pnl),
    )


def _source_catalog():
    opportunity = _opportunity()
    setup_market = _market(observed_at=BASE)
    observations = (
        _observation(
            opportunity=opportunity,
            setup_market=setup_market,
            name="design",
            closed_at=BASE + timedelta(days=1),
            role=BacktestPeriodRole.DESIGN,
            pnl="2",
        ),
        _observation(
            opportunity=opportunity,
            setup_market=setup_market,
            name="validation",
            closed_at=BASE + timedelta(days=2),
            role=BacktestPeriodRole.VALIDATION,
            pnl="-1",
        ),
        _observation(
            opportunity=opportunity,
            setup_market=setup_market,
            name="oos",
            closed_at=BASE + timedelta(days=3),
            role=BacktestPeriodRole.OOS,
            pnl="3",
        ),
        _observation(
            opportunity=opportunity,
            setup_market=setup_market,
            name="future",
            closed_at=BASE + timedelta(days=20),
            role=BacktestPeriodRole.DESIGN,
            pnl="99",
        ),
    )
    return opportunity, setup_market, HistoricalSetupStatsCatalog(
        observations
    )


def test_strict_pre_oos_prior_excludes_oos_and_future_samples() -> None:
    _, _, source = _source_catalog()
    cutoff = BASE + timedelta(days=10)

    prior = freeze_denver_prior(
        source,
        cutoff=cutoff,
        policy=DenverPriorPolicy.STRICT_PRE_OOS,
    )

    assert prior.observation_count == 2
    assert prior.source_period_roles == ("DESIGN", "VALIDATION")
    assert all(
        item.closed_at <= cutoff
        for item in prior.catalog.observations
    )
    assert all(
        item.period_role is not BacktestPeriodRole.OOS
        for item in prior.catalog.observations
    )


def test_all_closed_policy_may_keep_historical_oos_before_cutoff() -> None:
    _, _, source = _source_catalog()

    prior = freeze_denver_prior(
        source,
        cutoff=BASE + timedelta(days=10),
        policy=DenverPriorPolicy.ALL_CLOSED_BEFORE_CUTOFF,
    )

    assert prior.observation_count == 3
    assert prior.source_period_roles == (
        "DESIGN",
        "OOS",
        "VALIDATION",
    )


def test_prior_is_content_addressed_round_trip_and_tamper_safe() -> None:
    _, _, source = _source_catalog()
    prior = freeze_denver_prior(
        source,
        cutoff=BASE + timedelta(days=10),
    )

    restored = FrozenDenverPriorCatalog.from_json(prior.to_json())
    assert restored.prior_id == prior.prior_id
    assert restored.to_json() == prior.to_json()

    tampered = prior.to_json().replace(
        '"denver_prior_observation_count"',
        '"tampered_unused_key"',
    )
    # A harmless absent string should not modify the artifact.
    assert tampered == prior.to_json()

    raw = prior.to_json().replace('"2"', '"999"', 1)
    if raw != prior.to_json():
        with pytest.raises(ValueError):
            FrozenDenverPriorCatalog.from_json(raw)


def test_formal_oos_requires_strict_policy_and_preperiod_cutoff() -> None:
    _, _, source = _source_catalog()
    target_start = BASE + timedelta(days=11)

    strict = freeze_denver_prior(
        source,
        cutoff=BASE + timedelta(days=10),
        policy=DenverPriorPolicy.STRICT_PRE_OOS,
    )
    strict.validate_for_target(
        period_start=target_start,
        formal_oos=True,
    )

    all_closed = freeze_denver_prior(
        source,
        cutoff=BASE + timedelta(days=10),
        policy=DenverPriorPolicy.ALL_CLOSED_BEFORE_CUTOFF,
    )
    with pytest.raises(ValueError, match="STRICT_PRE_OOS"):
        all_closed.validate_for_target(
            period_start=target_start,
            formal_oos=True,
        )

    with pytest.raises(ValueError, match="period_start"):
        strict.validate_for_target(
            period_start=BASE + timedelta(days=9),
            formal_oos=True,
        )


def test_provider_requires_prior_identity_in_backtest_config() -> None:
    _, _, source = _source_catalog()
    prior = freeze_denver_prior(
        source,
        cutoff=BASE + timedelta(days=10),
    )
    target_start = BASE + timedelta(days=11)

    with pytest.raises(ValueError, match="does not bind"):
        FrozenDenverPriorContextProvider.for_backtest(
            prior,
            config=SimpleNamespace(execution_assumptions={}),
            period_start=target_start,
            formal_oos=True,
        )

    provider = FrozenDenverPriorContextProvider.for_backtest(
        prior,
        config=SimpleNamespace(
            execution_assumptions=prior.reproducibility_assumptions
        ),
        period_start=target_start,
        formal_oos=True,
    )
    assert provider.reproducibility_assumptions == (
        prior.reproducibility_assumptions
    )


def test_provider_uses_only_frozen_samples_and_exposes_prior_provenance() -> None:
    opportunity, setup_market, source = _source_catalog()
    cutoff = BASE + timedelta(days=10)
    prior = freeze_denver_prior(source, cutoff=cutoff)
    provider = FrozenDenverPriorContextProvider(prior)

    market = setup_market.model_copy(
        update={"observed_at": BASE + timedelta(days=11)}
    )
    contexts = provider.contexts_for(
        opportunity=opportunity,
        market_context=market,
    )
    denver = contexts["denver"]

    assert denver["sample_count"] == 2
    assert denver["oos_sample_count"] == 0
    assert denver["win_rate"] == 0.5
    assert denver["expectancy"] == 0.5
    assert any(
        note == f"prior_id={prior.prior_id}"
        for note in denver["notes"]
    )
    assert "prior_policy=STRICT_PRE_OOS" in denver["notes"]
    assert any(
        note.startswith("prior_cutoff=")
        for note in denver["notes"]
    )


def test_provider_rejects_market_time_before_prior_cutoff() -> None:
    opportunity, setup_market, source = _source_catalog()
    cutoff = BASE + timedelta(days=10)
    prior = freeze_denver_prior(source, cutoff=cutoff)
    provider = FrozenDenverPriorContextProvider(prior)

    early_market = setup_market.model_copy(
        update={"observed_at": BASE + timedelta(days=9)}
    )
    with pytest.raises(ValueError, match="later than market"):
        provider.contexts_for(
            opportunity=opportunity,
            market_context=early_market,
        )


def test_frozen_provider_context_is_anchored_to_prior_cutoff() -> None:
    opportunity, setup_market, source = _source_catalog()
    cutoff = BASE + timedelta(days=10)
    prior = freeze_denver_prior(source, cutoff=cutoff)
    provider = FrozenDenverPriorContextProvider(prior)

    market = setup_market.model_copy(
        update={"observed_at": BASE + timedelta(days=15)}
    )
    denver = provider.contexts_for(
        opportunity=opportunity,
        market_context=market,
    )["denver"]

    assert denver["as_of"] == cutoff
    assert prior.prior_fingerprint == prior.prior_id.split(":", 1)[1]
    assert len(prior.prior_fingerprint) == 64
    assert prior.reproducibility_assumptions[
        "denver_context_binding_version"
    ] == "frozen-denver-decision-context-v1"
