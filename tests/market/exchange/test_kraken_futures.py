from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.market.exchange import (
    KRAKEN_FUTURES_INITIAL_SYMBOL_MAP,
    KRAKEN_FUTURES_SOURCE,
    DerivativesPositioningSnapshot,
    KrakenFuturesAnalyticsConfig,
    KrakenFuturesAnalyticsProvider,
    PublicHttpResponse,
    ResilientPublicHttpClient,
    RetryPolicy,
    UnsafeMarketDataError,
)

BASE_NOW = datetime(2026, 9, 9, 0, 0, tzinfo=UTC)


class RoutedTransport:
    def __init__(self, payloads: Mapping[str, Any], *, received_at: datetime = BASE_NOW) -> None:
        self.payloads = dict(payloads)
        self.received_at = received_at
        self.calls: list[tuple[str, Mapping[str, str | int] | None, float]] = []

    async def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None,
        timeout_seconds: float,
    ) -> PublicHttpResponse:
        self.calls.append((url, params, timeout_seconds))
        analytics_type = url.rsplit("/", 1)[-1]
        payload = self.payloads[analytics_type]
        if isinstance(payload, BaseException):
            raise payload
        return PublicHttpResponse(
            status_code=200,
            payload=payload,
            headers={},
            received_at=self.received_at,
        )


def run(coro):
    return asyncio.run(coro)


def analytics_payload(timestamps: list[int], data: Any) -> dict[str, Any]:
    return {
        "result": {
            "timestamp": timestamps,
            "more": False,
            "data": data,
        }
    }


def default_payloads(*, timestamps: list[int] | None = None) -> dict[str, Any]:
    ts = timestamps or [
        int((BASE_NOW - timedelta(minutes=10)).timestamp()),
        int((BASE_NOW - timedelta(minutes=5)).timestamp()),
    ]
    return {
        "open-interest": analytics_payload(ts, {"openInterest": ["100", "110"]}),
        "long-short-ratio": analytics_payload(ts, {"ratio": ["0.9", "1.1"]}),
        "funding": analytics_payload(
            ts,
            {
                "rate": [
                    ["0.0001", "0.0002"],
                    ["0.0003", "0.0004"],
                    ["-0.0001", "0.0000"],
                    ["0.0002", "0.00025"],
                ]
            },
        ),
    }


def provider_with(
    payloads: Mapping[str, Any] | None = None,
    *,
    now: datetime = BASE_NOW,
    max_metric_age: timedelta = timedelta(minutes=20),
):
    transport = RoutedTransport(payloads or default_payloads())
    client = ResilientPublicHttpClient(
        transport,
        policy=RetryPolicy(max_attempts=1, min_request_interval_seconds=0),
    )
    provider = KrakenFuturesAnalyticsProvider(
        client,
        config=KrakenFuturesAnalyticsConfig(
            interval_seconds=300,
            lookback=timedelta(hours=2),
            max_metric_age=max_metric_age,
        ),
        now=lambda: now,
    )
    return provider, transport


def test_initial_futures_mapping_is_explicit_for_spot_eur_universe() -> None:
    assert KRAKEN_FUTURES_INITIAL_SYMBOL_MAP == (
        ("BTC/EUR", "PF_XBTUSD"),
        ("ETH/EUR", "PF_ETHUSD"),
        ("SOL/EUR", "PF_SOLUSD"),
    )


def test_config_rejects_invalid_interval_age_or_duplicate_mapping() -> None:
    with pytest.raises(ValueError, match="interval"):
        KrakenFuturesAnalyticsConfig(interval_seconds=120)
    with pytest.raises(ValueError, match="lookback"):
        KrakenFuturesAnalyticsConfig(lookback=timedelta(0))
    with pytest.raises(ValueError, match="max_metric_age"):
        KrakenFuturesAnalyticsConfig(max_metric_age=timedelta(0))
    with pytest.raises(ValueError, match="duplicate"):
        KrakenFuturesAnalyticsConfig(
            symbol_map=(("BTC/EUR", "PF_XBTUSD"), ("btc/eur", "PF_ETHUSD"))
        )


def test_instrument_lookup_normalizes_canonical_symbol_without_guessing() -> None:
    config = KrakenFuturesAnalyticsConfig()
    assert config.instrument_for(" btc/eur ") == "PF_XBTUSD"
    with pytest.raises(ValueError, match="configured"):
        config.instrument_for("XRP/EUR")


def test_public_analytics_normalize_real_metrics_without_liquidation_invention() -> None:
    provider, transport = provider_with()

    snapshot = run(provider.get_positioning_snapshot("BTC/EUR"))

    assert isinstance(snapshot, DerivativesPositioningSnapshot)
    assert snapshot.source == KRAKEN_FUTURES_SOURCE
    assert snapshot.symbol == "BTC/EUR"
    assert snapshot.instrument == "PF_XBTUSD"
    assert snapshot.funding_rate == Decimal("0.00025")
    assert snapshot.open_interest == Decimal("110")
    assert snapshot.open_interest_change_pct == Decimal("10.0")
    assert snapshot.long_short_ratio == Decimal("1.1")
    assert snapshot.long_liquidations_notional is None
    assert snapshot.short_liquidations_notional is None
    assert "long_liquidations_notional" in snapshot.missing_fields
    assert "short_liquidations_notional" in snapshot.missing_fields
    assert snapshot.observed_at == BASE_NOW - timedelta(minutes=5)
    assert len(transport.calls) == 3
    assert all("futures.kraken.com" in call[0] for call in transport.calls)
    assert all(call[1]["interval"] == 300 for call in transport.calls)


def test_open_interest_accepts_ohlc_rows_and_uses_close_without_guessing() -> None:
    payloads = default_payloads()
    timestamps = payloads["open-interest"]["result"]["timestamp"]
    payloads["open-interest"] = analytics_payload(
        timestamps,
        [
            ["90", "105", "85", "100"],
            ["100", "115", "95", "110"],
        ],
    )
    provider, _ = provider_with(payloads)

    snapshot = run(provider.get_positioning_snapshot("BTC/EUR"))

    assert snapshot.open_interest == Decimal("110")
    assert snapshot.open_interest_change_pct == Decimal("10.0")


def test_funding_accepts_one_ohlc_row_per_timestamp() -> None:
    payloads = default_payloads()
    timestamps = payloads["funding"]["result"]["timestamp"]
    payloads["funding"] = analytics_payload(
        timestamps,
        {
            "rate": [
                ["0.1", "0.2", "0.0", "0.15"],
                ["0.2", "0.3", "0.1", "0.25"],
            ]
        },
    )
    provider, _ = provider_with(payloads)

    snapshot = run(provider.get_positioning_snapshot("BTC/EUR"))

    assert snapshot.funding_rate == Decimal("0.25")


def test_stale_metric_is_omitted_and_never_relabelled_as_current() -> None:
    payloads = default_payloads()
    stale = [
        int((BASE_NOW - timedelta(hours=2)).timestamp()),
        int((BASE_NOW - timedelta(hours=1)).timestamp()),
    ]
    payloads["open-interest"] = analytics_payload(
        stale,
        {"openInterest": ["100", "110"]},
    )
    provider, _ = provider_with(payloads, max_metric_age=timedelta(minutes=20))

    snapshot = run(provider.get_positioning_snapshot("BTC/EUR"))

    assert snapshot.open_interest is None
    assert snapshot.open_interest_change_pct is None
    assert snapshot.funding_rate is not None
    assert snapshot.long_short_ratio is not None
    assert "open_interest" in snapshot.missing_fields


def test_one_malformed_metric_degrades_snapshot_instead_of_fabricating_value() -> None:
    payloads = default_payloads()
    payloads["funding"] = {"unexpected": "shape"}
    provider, _ = provider_with(payloads)

    snapshot = run(provider.get_positioning_snapshot("BTC/EUR"))

    assert snapshot.funding_rate is None
    assert snapshot.open_interest == Decimal("110")
    assert snapshot.long_short_ratio == Decimal("1.1")
    assert "funding_rate" in snapshot.missing_fields


def test_all_unusable_analytics_fail_closed() -> None:
    malformed = {"unexpected": "shape"}
    provider, _ = provider_with(
        {
            "open-interest": malformed,
            "long-short-ratio": malformed,
            "funding": malformed,
        }
    )

    with pytest.raises(UnsafeMarketDataError, match="no usable positioning metrics"):
        run(provider.get_positioning_snapshot("BTC/EUR"))


def test_future_exchange_timestamp_fails_closed_even_when_other_metrics_are_valid() -> None:
    payloads = default_payloads()
    future = [
        int((BASE_NOW + timedelta(minutes=1)).timestamp()),
        int((BASE_NOW + timedelta(minutes=2)).timestamp()),
    ]
    payloads["long-short-ratio"] = analytics_payload(future, {"ratio": ["1", "1.1"]})
    provider, _ = provider_with(payloads)

    with pytest.raises(UnsafeMarketDataError, match="later than local receipt"):
        run(provider.get_positioning_snapshot("BTC/EUR"))


def test_open_interest_change_is_absent_when_previous_open_interest_is_zero() -> None:
    payloads = default_payloads()
    timestamps = payloads["open-interest"]["result"]["timestamp"]
    payloads["open-interest"] = analytics_payload(
        timestamps,
        {"openInterest": ["0", "110"]},
    )
    provider, _ = provider_with(payloads)

    snapshot = run(provider.get_positioning_snapshot("BTC/EUR"))

    assert snapshot.open_interest == Decimal("110")
    assert snapshot.open_interest_change_pct is None
    assert "open_interest_change_pct" in snapshot.missing_fields
