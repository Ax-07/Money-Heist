from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market.features import FeatureEngine
from app.market.features.multitimeframe import (
    build_multi_timeframe_feature_context,
)
from app.market.models import Candle
from app.market.multitimeframe import HistoricalMultiTimeframeCursor
from app.services.decision_context import (
    ContextAvailability,
    ProvenanceRecord,
    build_decision_context,
)
from app.trading.risk.models import MarketConstraints, PortfolioRiskState


START = datetime(2026, 1, 1, tzinfo=UTC)


def _market_context(hours: int = 36):
    cursor = HistoricalMultiTimeframeCursor(
        source_timeframe="1h",
        target_timeframes=("1h", "4h", "1d"),
    )
    for index in range(hours):
        opened = START + timedelta(hours=index)
        price = Decimal("100") + index
        cursor.push(
            Candle(
                symbol="BTC/USDC",
                timeframe="1h",
                open_time=opened,
                close_time=opened + timedelta(hours=1),
                open=price,
                high=price + Decimal("2"),
                low=price - Decimal("2"),
                close=price + Decimal("1"),
                volume=Decimal("1000") + index,
                is_closed=True,
            )
        )
    engine = FeatureEngine()
    as_of = START + timedelta(hours=hours)
    return build_multi_timeframe_feature_context(
        feature_engine=engine,
        mtf_cursor=cursor,
        observed_at=as_of,
        decision_timeframe="1h",
    )


def test_decision_context_is_deterministic_and_explicitly_missing():
    market = _market_context()
    first = build_decision_context(
        system_id="balanced_v1",
        as_of=market.observed_at,
        primary_timeframe="1h",
        timeframe_policy_version="mtf-utc-closed-v1",
        market=market,
    )
    second = build_decision_context(
        system_id="balanced_v1",
        as_of=market.observed_at,
        primary_timeframe="1h",
        timeframe_policy_version="mtf-utc-closed-v1",
        market=market,
    )

    assert first.context_id == second.context_id
    assert first.context_fingerprint == second.context_fingerprint
    assert first.market is market
    assert first.provenance["market"].available_at == market.observed_at
    assert first.derivatives.status is ContextAvailability.UNAVAILABLE
    assert first.statistics.status is ContextAvailability.UNAVAILABLE
    assert set(first.missing_components) == {
        "structure",
        "derivatives",
        "statistics",
        "portfolio_summary",
        "market_constraints",
        "microstructure",
    }


def test_decision_context_rejects_future_available_at():
    market = _market_context()

    with pytest.raises(ValueError, match="lookahead rejected"):
        build_decision_context(
            system_id="balanced_v1",
            as_of=market.observed_at,
            primary_timeframe="1h",
            timeframe_policy_version="mtf-utc-closed-v1",
            market=market,
            market_available_at=market.observed_at + timedelta(seconds=1),
        )


def test_provenance_rejects_observation_after_availability():
    with pytest.raises(
        ValueError,
        match="observed_at cannot be later than available_at",
    ):
        ProvenanceRecord(
            component="derivatives",
            source="fixture",
            observed_at=START + timedelta(hours=1),
            available_at=START,
        )


def test_portfolio_and_constraints_are_typed_and_fingerprinted():
    market = _market_context()
    portfolio = PortfolioRiskState(
        equity=Decimal("1000"),
        day_start_equity=Decimal("1000"),
        equity_peak=Decimal("1050"),
        daily_pnl=Decimal("-5"),
        open_positions=1,
        open_risk_amount=Decimal("10"),
        correlated_risk_amount=Decimal("2"),
        gross_exposure_amount=Decimal("200"),
    )
    constraints = MarketConstraints(
        qty_step=Decimal("0.00001"),
        min_qty=Decimal("0.0001"),
        min_notional=Decimal("10"),
        max_qty=Decimal("5"),
        max_leverage=Decimal("3"),
    )
    context = build_decision_context(
        system_id="balanced_v1",
        as_of=market.observed_at,
        primary_timeframe="1h",
        timeframe_policy_version="mtf-utc-closed-v1",
        market=market,
        portfolio_state=portfolio,
        market_constraints=constraints,
    )

    assert context.portfolio_summary is not None
    assert context.portfolio_summary.equity == Decimal("1000")
    assert context.market_constraints is not None
    assert context.market_constraints.min_notional == Decimal("10")
    assert "portfolio_summary" in context.provenance
    assert "market_constraints" in context.provenance
    assert "portfolio_summary" not in context.missing_components
    assert "market_constraints" not in context.missing_components


def test_agent_payload_is_json_safe_and_preserves_feature_numbers():
    import json
    from app.services.decision_context import decision_context_payload

    market = _market_context()
    context = build_decision_context(
        system_id="balanced_v1",
        as_of=market.observed_at,
        primary_timeframe="1h",
        timeframe_policy_version="mtf-utc-closed-v1",
        market=market,
    )
    payload = decision_context_payload(context)

    assert payload["context_id"] == context.context_id
    assert payload["context_fingerprint"] == context.context_fingerprint
    assert payload["market"]["snapshots"]["1h"]["timeframe"] == "1h"
    assert isinstance(payload["market"]["snapshots"]["1h"]["close"], float)
    json.dumps(payload, sort_keys=True)


def test_available_optional_section_requires_provenance():
    from app.services.decision_context import (
        ContextAvailability,
        OptionalContextSection,
    )

    market = _market_context()
    structure = OptionalContextSection(
        status=ContextAvailability.AVAILABLE,
        payload={"version": "fixture"},
    )

    with pytest.raises(ValueError, match="structure requires provenance"):
        build_decision_context(
            system_id="balanced_v1",
            as_of=market.observed_at,
            primary_timeframe="1h",
            timeframe_policy_version="mtf-utc-closed-v1",
            market=market,
            structure=structure,
        )
