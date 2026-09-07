from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from app.market.exchange.models import PublicHttpResponse
from app.market.exchange.transport import TransportInvalidJsonError, TransportNetworkError


UTC = timezone.utc
BASE_NOW = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)


class FakeTransport:
    def __init__(self, *outcomes: PublicHttpResponse | Exception) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, Mapping[str, str | int] | None, float]] = []

    async def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None,
        timeout_seconds: float,
    ) -> PublicHttpResponse:
        self.calls.append((url, params, timeout_seconds))
        if not self.outcomes:
            raise AssertionError("fake transport exhausted")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response(
    payload: Any,
    *,
    status: int = 200,
    received_at: datetime = BASE_NOW,
    headers: Mapping[str, str] | None = None,
) -> PublicHttpResponse:
    return PublicHttpResponse(
        status_code=status,
        payload=payload,
        headers=dict(headers or {}),
        received_at=received_at,
    )


def kraken(payload: Any, *, received_at: datetime = BASE_NOW) -> PublicHttpResponse:
    return response({"error": [], "result": payload}, received_at=received_at)


def metadata_payload(
    *,
    pair: str = "BTC/EUR",
    base: str = "BTC",
    quote: str = "EUR",
    status: str = "online",
    pair_decimals: int = 1,
    lot_decimals: int = 8,
    ordermin: str = "0.0001",
    costmin: str = "0.5",
    tick_size: str = "0.1",
) -> dict[str, Any]:
    return {
        pair: {
            "base": base,
            "quote": quote,
            "pair_decimals": pair_decimals,
            "lot_decimals": lot_decimals,
            "ordermin": ordermin,
            "costmin": costmin,
            "tick_size": tick_size,
            "status": status,
        }
    }


def trade_payload(
    *,
    pair: str = "BTC/EUR",
    price: str = "100.25",
    timestamp: float | None = None,
) -> dict[str, Any]:
    ts = timestamp if timestamp is not None else BASE_NOW.timestamp() - 10
    return {pair: [[price, "0.01", ts, "b", "m", "", 1]], "last": "cursor"}


def ohlc_payload(
    *,
    pair: str = "BTC/EUR",
    start_timestamp: float | None = None,
    interval_seconds: int = 60,
    count: int = 3,
) -> dict[str, Any]:
    start = (
        start_timestamp
        if start_timestamp is not None
        else BASE_NOW.timestamp() - (count * interval_seconds)
    )
    rows = []
    for index in range(count):
        ts = start + index * interval_seconds
        base = 100 + index
        rows.append(
            [
                ts,
                str(base),
                str(base + 2),
                str(base - 1),
                str(base + 1),
                str(base + 0.5),
                "12.5",
                8,
            ]
        )
    return {pair: rows, "last": int(start + count * interval_seconds)}


__all__ = [
    "BASE_NOW",
    "FakeTransport",
    "TransportInvalidJsonError",
    "TransportNetworkError",
    "kraken",
    "metadata_payload",
    "ohlc_payload",
    "response",
    "trade_payload",
]
