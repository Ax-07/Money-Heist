from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.services.backtest.denver_prior import (
    DenverPriorPolicy,
    freeze_denver_prior,
)
from app.services.backtest.denver_runtime import (
    DENVER_RUNTIME_VERSION,
    DenverActivationMode,
    denver_prior_execution_assumptions,
    denver_runner_kwargs,
    validate_denver_prior_compatibility,
)
from app.services.backtest.mtf_runtime import mtf_execution_assumptions
from app.services.backtest.setup_stats import (
    HistoricalSetupKey,
    HistoricalSetupObservation,
    HistoricalSetupStatsCatalog,
)
from app.services.backtest.splits import BacktestPeriodRole


BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _prior(
    *,
    policy: DenverPriorPolicy = DenverPriorPolicy.STRICT_PRE_OOS,
):
    setup = HistoricalSetupKey(
        system_id="balanced_v1",
        symbol="BTC/USDC",
        timeframe="1h",
        scanner_version="scanner-v1",
        feature_version="feature-engine-v1",
        regime="BULLISH_TREND",
        triggers=("RANGE_BREAK",),
    )
    observation = HistoricalSetupObservation(
        run_id="source-run",
        dataset_id="source-dataset",
        strategy_fingerprint="strategy-v1",
        period_role=BacktestPeriodRole.DESIGN,
        opportunity_id="source-opportunity",
        trade_id="source-trade",
        setup=setup,
        side="LONG",
        opened_at=BASE - timedelta(days=2),
        closed_at=BASE - timedelta(days=1),
        net_pnl=Decimal("2.5"),
    )
    return freeze_denver_prior(
        HistoricalSetupStatsCatalog((observation,)),
        cutoff=BASE,
        policy=policy,
    )


def _assumptions(prior, mode=DenverActivationMode.OOS_ONLY):
    assumptions = mtf_execution_assumptions("1m")
    assumptions.update(
        denver_prior_execution_assumptions(
            prior,
            activation_mode=mode,
        )
    )
    return assumptions


def test_denver_runtime_assumptions_bind_exact_prior() -> None:
    prior = _prior()
    assumptions = _assumptions(prior)

    assert assumptions["denver_runtime_version"] == DENVER_RUNTIME_VERSION
    assert assumptions["denver_activation_mode"] == "OOS_ONLY"
    assert assumptions["denver_formal_oos"] == "true"
    assert assumptions["denver_prior_id"] == prior.prior_id


def test_denver_runtime_disabled_without_marker_or_prior() -> None:
    assumptions = mtf_execution_assumptions("1m")
    assert denver_runner_kwargs(
        assumptions,
        None,
        role=BacktestPeriodRole.OOS,
    ) == {}


def test_oos_only_injects_only_oos() -> None:
    prior = _prior()
    assumptions = _assumptions(prior)

    assert denver_runner_kwargs(
        assumptions,
        prior,
        role=BacktestPeriodRole.DESIGN,
    ) == {}
    assert denver_runner_kwargs(
        assumptions,
        prior,
        role=BacktestPeriodRole.VALIDATION,
    ) == {}

    kwargs = denver_runner_kwargs(
        assumptions,
        prior,
        role=BacktestPeriodRole.OOS,
    )
    assert kwargs["historical_denver_prior"] is prior
    assert kwargs["denver_formal_oos"] is True


def test_oos_only_requires_explicit_role() -> None:
    prior = _prior()
    with pytest.raises(ValueError, match="explicit period role"):
        denver_runner_kwargs(
            _assumptions(prior),
            prior,
            role=None,
        )


def test_all_periods_injects_same_prior() -> None:
    prior = _prior(
        policy=DenverPriorPolicy.ALL_CLOSED_BEFORE_CUTOFF,
    )
    assumptions = _assumptions(
        prior,
        DenverActivationMode.ALL_PERIODS,
    )

    for role in BacktestPeriodRole:
        kwargs = denver_runner_kwargs(
            assumptions,
            prior,
            role=role,
        )
        assert kwargs["historical_denver_prior"] is prior
        assert kwargs["denver_formal_oos"] is False


def test_tampered_prior_identity_fails_closed() -> None:
    prior = _prior()
    assumptions = _assumptions(prior)
    assumptions["denver_prior_id"] = "denver-prior:" + ("0" * 64)

    with pytest.raises(ValueError, match="denver_prior_id"):
        denver_runner_kwargs(
            assumptions,
            prior,
            role=BacktestPeriodRole.OOS,
        )


def test_injected_prior_without_runtime_marker_fails_closed() -> None:
    with pytest.raises(ValueError, match="not enabled"):
        denver_runner_kwargs(
            mtf_execution_assumptions("1m"),
            _prior(),
            role=BacktestPeriodRole.OOS,
        )


@pytest.mark.parametrize(
    ("system_id", "symbol", "decision_timeframe", "match"),
    (
        ("other", "BTC/USDC", "1h", "system_id"),
        ("balanced_v1", "ETH/USDC", "1h", "symbol"),
        ("balanced_v1", "BTC/USDC", "4h", "timeframe"),
    ),
)
def test_prior_compatibility_fails_closed(
    system_id,
    symbol,
    decision_timeframe,
    match,
) -> None:
    with pytest.raises(ValueError, match=match):
        validate_denver_prior_compatibility(
            _prior(),
            system_id=system_id,
            symbol=symbol,
            decision_timeframe=decision_timeframe,
        )
