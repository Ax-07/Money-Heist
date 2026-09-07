from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest

from app.market.exchange import (
    ExchangePayloadError,
    ExchangeRateLimitError,
    KRAKEN_INITIAL_SYMBOLS,
    KRAKEN_SOURCE,
    KrakenAdapterConfig,
    KrakenPublicMarketDataProvider,
    ResilientPublicHttpClient,
    RetryPolicy,
    UnsafeMarketDataError,
)
from app.market.provider import MarketDataProvider
from app.market.quality import FreshnessPolicy

from ._helpers import (
    BASE_NOW,
    FakeTransport,
    kraken,
    metadata_payload,
    ohlc_payload,
    trade_payload,
)


def run(coro):
    return asyncio.run(coro)


def provider_with(
    *responses,
    now=BASE_NOW,
    timeframes=("1m",),
    max_age=timedelta(minutes=2),
    metadata_max_age=timedelta(hours=1),
):
    transport = FakeTransport(*responses)
    client = ResilientPublicHttpClient(
        transport,
        policy=RetryPolicy(min_request_interval_seconds=0),
    )
    provider = KrakenPublicMarketDataProvider(
        client,
        config=KrakenAdapterConfig(
            freshness_policy=FreshnessPolicy(max_age=max_age),
            snapshot_timeframes=tuple(timeframes),
            metadata_max_age=metadata_max_age,
        ),
        now=lambda: now,
    )
    return provider, transport


def test_initial_universe_is_explicit_eur_spot_symbols():
    assert KRAKEN_INITIAL_SYMBOLS == ("BTC/EUR", "ETH/EUR", "SOL/EUR")


def test_provider_structurally_implements_market_data_port():
    provider, _ = provider_with()
    assert isinstance(provider, MarketDataProvider)


@pytest.mark.parametrize(
    "timeframes",
    [(), ("2m",), ("1m", "1m")],
)
def test_config_rejects_missing_unsupported_or_duplicate_timeframes(timeframes):
    with pytest.raises(ValueError):
        KrakenAdapterConfig(
            freshness_policy=FreshnessPolicy(max_age=timedelta(minutes=1)),
            snapshot_timeframes=timeframes,
            metadata_max_age=timedelta(hours=1),
        )


def test_config_rejects_non_positive_metadata_age():
    with pytest.raises(ValueError, match="metadata_max_age"):
        KrakenAdapterConfig(
            freshness_policy=FreshnessPolicy(max_age=timedelta(minutes=1)),
            snapshot_timeframes=("1m",),
            metadata_max_age=timedelta(0),
        )


def test_symbol_requires_canonical_base_quote_form():
    provider, _ = provider_with()
    with pytest.raises(ValueError, match="BASE/QUOTE"):
        run(provider.get_current_price("BTCEUR"))


def test_symbol_is_trimmed_and_uppercased_in_public_call():
    provider, transport = provider_with(kraken(trade_payload()))

    price = run(provider.get_current_price("  btc/eur  "))

    assert price.symbol == "BTC/EUR"
    _, params, _ = transport.calls[0]
    assert params == {"pair": "BTC/EUR", "assetVersion": 1, "count": 1}


def test_refresh_symbol_metadata_normalizes_exchange_values():
    provider, _ = provider_with(
        kraken(
            metadata_payload(
                pair_decimals=2,
                lot_decimals=5,
                ordermin="0.001",
                costmin="1.25",
                tick_size="0.01",
            )
        )
    )

    metadata = run(provider.refresh_symbol_metadata("BTC/EUR"))

    assert metadata.symbol == "BTC/EUR"
    assert metadata.exchange_symbol == "BTC/EUR"
    assert metadata.source == KRAKEN_SOURCE
    assert metadata.base_asset == "BTC"
    assert metadata.quote_asset == "EUR"
    assert metadata.tick_size == Decimal("0.01")
    assert metadata.qty_step == Decimal("0.00001")
    assert metadata.min_qty == Decimal("0.001")
    assert metadata.min_notional == Decimal("1.25")
    assert metadata.price_precision == 2
    assert metadata.quantity_precision == 5


def test_market_constraints_projection_does_not_invent_risk_fields():
    provider, _ = provider_with(kraken(metadata_payload()))
    run(provider.refresh_symbol_metadata("BTC/EUR"))

    constraints = provider.get_market_constraints(symbol="BTC/EUR")

    assert constraints is not None
    assert constraints.qty_step == Decimal("0.00000001")
    assert constraints.min_qty == Decimal("0.0001")
    assert constraints.min_notional == Decimal("0.5")
    assert constraints.max_qty is None
    assert constraints.max_leverage is None


def test_market_constraints_fail_closed_before_metadata_refresh():
    provider, _ = provider_with()
    assert provider.get_market_constraints(symbol="BTC/EUR") is None


def test_stale_metadata_is_not_exposed_to_risk_provider():
    provider, _ = provider_with(
        kraken(metadata_payload(), received_at=BASE_NOW - timedelta(hours=2)),
        metadata_max_age=timedelta(hours=1),
    )
    run(provider.refresh_symbol_metadata("BTC/EUR"))
    assert provider.get_market_constraints(symbol="BTC/EUR") is None


def test_offline_symbol_metadata_is_preserved_but_constraints_fail_closed():
    provider, _ = provider_with(kraken(metadata_payload(status="cancel_only")))
    metadata = run(provider.refresh_symbol_metadata("BTC/EUR"))
    assert metadata.status == "cancel_only"
    assert provider.get_market_constraints(symbol="BTC/EUR") is None


def test_metadata_missing_required_field_is_rejected():
    payload = metadata_payload()
    del payload["BTC/EUR"]["costmin"]
    provider, _ = provider_with(kraken(payload))

    with pytest.raises(ExchangePayloadError, match="costmin"):
        run(provider.refresh_symbol_metadata("BTC/EUR"))


def test_metadata_multiple_pair_results_are_rejected():
    payload = metadata_payload()
    payload["ETH/EUR"] = dict(payload["BTC/EUR"], base="ETH")
    provider, _ = provider_with(kraken(payload))

    with pytest.raises(ExchangePayloadError, match="exactly one pair"):
        run(provider.refresh_symbol_metadata("BTC/EUR"))


def test_metadata_invalid_precision_is_rejected():
    provider, _ = provider_with(kraken(metadata_payload(lot_decimals=-1)))
    with pytest.raises(ExchangePayloadError, match="lot_decimals"):
        run(provider.refresh_symbol_metadata("BTC/EUR"))


def test_kraken_api_error_is_rejected():
    from ._helpers import response

    provider, _ = provider_with(
        response({"error": ["EGeneral:Invalid arguments"], "result": {}})
    )
    with pytest.raises(ExchangePayloadError, match="Invalid arguments"):
        run(provider.refresh_symbol_metadata("BTC/EUR"))


def test_kraken_rate_limit_error_is_classified():
    from ._helpers import response

    provider, _ = provider_with(response({"error": ["EAPI:Rate limit exceeded"], "result": {}}))
    with pytest.raises(ExchangeRateLimitError):
        run(provider.refresh_symbol_metadata("BTC/EUR"))


def test_current_price_uses_timestamped_recent_trade():
    observed = BASE_NOW.timestamp() - 12.5
    provider, _ = provider_with(kraken(trade_payload(price="123.45", timestamp=observed)))

    current = run(provider.get_current_price("BTC/EUR"))

    assert current.price == Decimal("123.45")
    assert current.observed_at.timestamp() == pytest.approx(observed)
    assert current.received_at == BASE_NOW
    assert current.source == KRAKEN_SOURCE


def test_current_price_rejects_empty_trade_result():
    provider, _ = provider_with(kraken({"BTC/EUR": [], "last": "cursor"}))
    with pytest.raises(ExchangePayloadError, match="at least one trade"):
        run(provider.get_current_price("BTC/EUR"))


def test_current_price_rejects_incomplete_trade():
    provider, _ = provider_with(kraken({"BTC/EUR": [["1"]], "last": "cursor"}))
    with pytest.raises(ExchangePayloadError, match="incomplete"):
        run(provider.get_current_price("BTC/EUR"))


def test_current_price_rejects_exchange_timestamp_after_receipt():
    provider, _ = provider_with(
        kraken(trade_payload(timestamp=BASE_NOW.timestamp() + 1))
    )
    with pytest.raises(UnsafeMarketDataError, match="later than local receipt"):
        run(provider.get_current_price("BTC/EUR"))


def test_get_candles_marks_only_last_kraken_ohlc_row_open():
    provider, _ = provider_with(kraken(ohlc_payload(count=4)))

    candles = run(provider.get_candles("BTC/EUR", "1m", 10))

    assert [candle.is_closed for candle in candles] == [True, True, True, False]
    assert all(candle.timeframe == "1m" for candle in candles)
    assert all(candle.symbol == "BTC/EUR" for candle in candles)


def test_get_candles_slices_to_requested_limit_without_fabrication():
    provider, _ = provider_with(kraken(ohlc_payload(count=5)))
    candles = run(provider.get_candles("BTC/EUR", "1m", 2))
    assert len(candles) == 2
    assert candles[-1].is_closed is False


def test_get_candles_rejects_non_positive_limit_before_network():
    provider, transport = provider_with()
    with pytest.raises(ValueError, match="limit"):
        run(provider.get_candles("BTC/EUR", "1m", 0))
    assert not transport.calls


def test_get_candles_rejects_unsupported_timeframe_before_network():
    provider, transport = provider_with()
    with pytest.raises(ValueError, match="unsupported"):
        run(provider.get_candles("BTC/EUR", "2m", 10))
    assert not transport.calls


def test_get_candles_rejects_incomplete_row():
    provider, _ = provider_with(kraken({"BTC/EUR": [[BASE_NOW.timestamp()]], "last": 1}))
    with pytest.raises(ExchangePayloadError, match="incomplete"):
        run(provider.get_candles("BTC/EUR", "1m", 10))


def test_get_candles_rejects_negative_volume():
    payload = ohlc_payload(count=2)
    payload["BTC/EUR"][0][6] = "-1"
    provider, _ = provider_with(kraken(payload))
    with pytest.raises(ExchangePayloadError, match="volume"):
        run(provider.get_candles("BTC/EUR", "1m", 10))


def test_snapshot_normalizes_metadata_price_and_ohlc_into_existing_models():
    provider, transport = provider_with(
        kraken(metadata_payload()),
        kraken(trade_payload(timestamp=BASE_NOW.timestamp() - 5)),
        kraken(ohlc_payload(count=4)),
    )

    snapshot = run(provider.get_snapshot("BTC/EUR"))

    assert snapshot.symbol == "BTC/EUR"
    assert snapshot.source == KRAKEN_SOURCE
    assert snapshot.last_price == Decimal("100.25")
    assert snapshot.observed_at.timestamp() == pytest.approx(BASE_NOW.timestamp() - 5)
    assert snapshot.quality.is_valid is True
    assert len(snapshot.candles["1m"]) == 4
    assert snapshot.candles["1m"][-1].is_closed is False
    assert len(transport.calls) == 3
    assert not hasattr(snapshot, "exchange_payload")


def test_snapshot_reuses_fresh_metadata_cache_without_hidden_network_refresh():
    provider, transport = provider_with(
        kraken(metadata_payload()),
        kraken(trade_payload()),
        kraken(ohlc_payload()),
        kraken(trade_payload()),
        kraken(ohlc_payload()),
    )

    run(provider.get_snapshot("BTC/EUR"))
    run(provider.get_snapshot("BTC/EUR"))

    endpoints = [call[0].rsplit("/", 1)[-1] for call in transport.calls]
    assert endpoints == ["AssetPairs", "Trades", "OHLC", "Trades", "OHLC"]


def test_snapshot_rejects_stale_timestamped_trade():
    provider, _ = provider_with(
        kraken(metadata_payload()),
        kraken(trade_payload(timestamp=BASE_NOW.timestamp() - 3600)),
        kraken(ohlc_payload()),
        max_age=timedelta(minutes=2),
    )

    with pytest.raises(UnsafeMarketDataError, match="quality checks"):
        run(provider.get_snapshot("BTC/EUR"))


def test_snapshot_rejects_gap_in_critical_candle_series():
    payload = ohlc_payload(count=3)
    payload["BTC/EUR"][2][0] += 60  # create one missing 1-minute interval
    provider, _ = provider_with(
        kraken(metadata_payload()),
        kraken(trade_payload()),
        kraken(payload),
    )

    with pytest.raises(ExchangePayloadError, match="missing intervals"):
        run(provider.get_snapshot("BTC/EUR"))


def test_snapshot_rejects_symbol_not_online_before_price_or_ohlc_calls():
    provider, transport = provider_with(kraken(metadata_payload(status="post_only")))

    with pytest.raises(UnsafeMarketDataError, match="status"):
        run(provider.get_snapshot("BTC/EUR"))
    assert len(transport.calls) == 1


def test_snapshot_supports_multiple_explicit_timeframes():
    provider, _ = provider_with(
        kraken(metadata_payload()),
        kraken(trade_payload()),
        kraken(ohlc_payload(interval_seconds=60, count=3)),
        kraken(ohlc_payload(interval_seconds=300, count=3)),
        timeframes=("1m", "5m"),
    )

    snapshot = run(provider.get_snapshot("BTC/EUR"))

    assert tuple(snapshot.candles) == ("1m", "5m")
    assert (
        snapshot.candles["5m"][1].open_time - snapshot.candles["5m"][0].open_time
        == timedelta(minutes=5)
    )


def test_now_callback_must_be_timezone_aware():
    provider, _ = provider_with(kraken(metadata_payload()))
    run(provider.refresh_symbol_metadata("BTC/EUR"))
    provider._now = lambda: BASE_NOW.replace(tzinfo=None)
    with pytest.raises(ValueError, match="timezone-aware"):
        provider.get_cached_symbol_metadata("BTC/EUR")


def test_snapshot_rejects_stale_current_ohlc_even_when_trade_is_fresh():
    stale_ohlc = ohlc_payload(
        start_timestamp=BASE_NOW.timestamp() - 600,
        interval_seconds=60,
        count=3,
    )
    provider, _ = provider_with(
        kraken(metadata_payload()),
        kraken(trade_payload()),
        kraken(stale_ohlc),
    )

    with pytest.raises(UnsafeMarketDataError, match="OHLC candle is stale"):
        run(provider.get_snapshot("BTC/EUR"))


def test_metadata_received_in_impossible_future_is_not_reused():
    provider, _ = provider_with(
        kraken(metadata_payload(), received_at=BASE_NOW + timedelta(seconds=10))
    )
    run(provider.refresh_symbol_metadata("BTC/EUR"))
    assert provider.get_cached_symbol_metadata("BTC/EUR") is None


def test_get_candles_rejects_duplicate_timestamps():
    payload = ohlc_payload(count=3)
    payload["BTC/EUR"][1][0] = payload["BTC/EUR"][0][0]
    provider, _ = provider_with(kraken(payload))

    with pytest.raises(ExchangePayloadError, match="duplicate"):
        run(provider.get_candles("BTC/EUR", "1m", 10))


def test_snapshot_rejects_impossible_future_local_receipt_clock():
    future = BASE_NOW + timedelta(seconds=10)
    provider, _ = provider_with(
        kraken(metadata_payload(), received_at=future),
        kraken(trade_payload(timestamp=BASE_NOW.timestamp() - 1), received_at=future),
        kraken(
            ohlc_payload(start_timestamp=BASE_NOW.timestamp() - 120),
            received_at=future,
        ),
    )

    with pytest.raises(UnsafeMarketDataError, match="receipt timestamp"):
        run(provider.get_snapshot("BTC/EUR"))
