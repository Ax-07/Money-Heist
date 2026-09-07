from __future__ import annotations

import asyncio
from collections.abc import Mapping

import pytest

from app.market.exchange import (
    ExchangeHttpError,
    ExchangeNetworkError,
    ExchangePayloadError,
    ExchangeRateLimitError,
    ResilientPublicHttpClient,
    RetryPolicy,
)

from ._helpers import (
    FakeTransport,
    TransportInvalidJsonError,
    TransportNetworkError,
    response,
)


def run(coro):
    return asyncio.run(coro)


class SleepRecorder:
    def __init__(self) -> None:
        self.values: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.values.append(seconds)


class Clock:
    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def __call__(self) -> float:
        if not self.values:
            raise AssertionError("clock exhausted")
        return self.values.pop(0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"max_attempts": 0}, "max_attempts"),
        ({"base_backoff_seconds": -1}, "base_backoff_seconds"),
        (
            {"base_backoff_seconds": 2, "max_backoff_seconds": 1},
            "max_backoff_seconds",
        ),
        ({"min_request_interval_seconds": -1}, "min_request_interval_seconds"),
    ],
)
def test_retry_policy_rejects_invalid_values(kwargs: Mapping[str, float | int], message: str):
    with pytest.raises(ValueError, match=message):
        RetryPolicy(**kwargs)


def test_client_returns_success_without_retry():
    transport = FakeTransport(response({"ok": True}))
    client = ResilientPublicHttpClient(
        transport,
        policy=RetryPolicy(min_request_interval_seconds=0),
    )

    result = run(client.get_json("https://example.invalid/public", params={"x": 1}))

    assert result.payload == {"ok": True}
    assert len(transport.calls) == 1
    assert transport.calls[0][1] == {"x": 1}
    assert transport.calls[0][2] == 5.0


def test_network_error_retries_with_bounded_backoff():
    sleep = SleepRecorder()
    transport = FakeTransport(
        TransportNetworkError("down"),
        TransportNetworkError("still down"),
        response({"ok": True}),
    )
    client = ResilientPublicHttpClient(
        transport,
        policy=RetryPolicy(
            max_attempts=3,
            base_backoff_seconds=0.5,
            max_backoff_seconds=1.0,
            min_request_interval_seconds=0,
        ),
        sleep=sleep,
    )

    result = run(client.get_json("https://example.invalid/public"))

    assert result.payload == {"ok": True}
    assert sleep.values == [0.5, 1.0]
    assert len(transport.calls) == 3


def test_network_error_fails_after_max_attempts():
    transport = FakeTransport(
        TransportNetworkError("one"),
        TransportNetworkError("two"),
    )
    client = ResilientPublicHttpClient(
        transport,
        policy=RetryPolicy(max_attempts=2, min_request_interval_seconds=0),
        sleep=SleepRecorder(),
    )

    with pytest.raises(ExchangeNetworkError, match="two"):
        run(client.get_json("https://example.invalid/public"))
    assert len(transport.calls) == 2


def test_invalid_json_retries_then_fails_as_payload_error():
    transport = FakeTransport(
        TransportInvalidJsonError("bad json"),
        TransportInvalidJsonError("still bad"),
    )
    client = ResilientPublicHttpClient(
        transport,
        policy=RetryPolicy(max_attempts=2, min_request_interval_seconds=0),
        sleep=SleepRecorder(),
    )

    with pytest.raises(ExchangePayloadError, match="still bad"):
        run(client.get_json("https://example.invalid/public"))


def test_http_429_uses_retry_after_but_caps_delay():
    sleep = SleepRecorder()
    transport = FakeTransport(
        response({}, status=429, headers={"Retry-After": "99"}),
        response({"ok": True}),
    )
    client = ResilientPublicHttpClient(
        transport,
        policy=RetryPolicy(
            max_attempts=2,
            max_backoff_seconds=1.5,
            min_request_interval_seconds=0,
        ),
        sleep=sleep,
    )

    result = run(client.get_json("https://example.invalid/public"))

    assert result.payload == {"ok": True}
    assert sleep.values == [1.5]


def test_http_429_fails_closed_after_bounded_retries():
    transport = FakeTransport(response({}, status=429), response({}, status=429))
    client = ResilientPublicHttpClient(
        transport,
        policy=RetryPolicy(max_attempts=2, min_request_interval_seconds=0),
        sleep=SleepRecorder(),
    )

    with pytest.raises(ExchangeRateLimitError) as exc:
        run(client.get_json("https://example.invalid/public"))
    assert exc.value.status_code == 429


def test_http_5xx_retries_then_succeeds():
    transport = FakeTransport(response({}, status=503), response({"ok": True}))
    sleep = SleepRecorder()
    client = ResilientPublicHttpClient(
        transport,
        policy=RetryPolicy(max_attempts=2, min_request_interval_seconds=0),
        sleep=sleep,
    )

    result = run(client.get_json("https://example.invalid/public"))

    assert result.payload == {"ok": True}
    assert sleep.values == [0.25]


def test_http_5xx_final_failure_is_http_error():
    transport = FakeTransport(response({}, status=500))
    client = ResilientPublicHttpClient(
        transport,
        policy=RetryPolicy(max_attempts=1, min_request_interval_seconds=0),
    )

    with pytest.raises(ExchangeHttpError) as exc:
        run(client.get_json("https://example.invalid/public"))
    assert exc.value.status_code == 500


def test_http_4xx_other_than_rate_limit_is_not_retried():
    transport = FakeTransport(response({}, status=400), response({"ok": True}))
    client = ResilientPublicHttpClient(
        transport,
        policy=RetryPolicy(max_attempts=3, min_request_interval_seconds=0),
    )

    with pytest.raises(ExchangeHttpError) as exc:
        run(client.get_json("https://example.invalid/public"))
    assert exc.value.status_code == 400
    assert len(transport.calls) == 1


def test_client_paces_calls_without_busy_loop():
    sleep = SleepRecorder()
    clock = Clock(10.0, 10.05, 10.20)
    transport = FakeTransport(response({"one": 1}), response({"two": 2}))
    client = ResilientPublicHttpClient(
        transport,
        policy=RetryPolicy(min_request_interval_seconds=0.2),
        sleep=sleep,
        monotonic=clock,
    )

    async def scenario():
        await client.get_json("https://example.invalid/one")
        return await client.get_json("https://example.invalid/two")

    result = run(scenario())

    assert result.payload == {"two": 2}
    assert sleep.values == [pytest.approx(0.15)]


def test_retry_after_invalid_value_falls_back_to_exponential_backoff():
    sleep = SleepRecorder()
    transport = FakeTransport(
        response({}, status=429, headers={"retry-after": "later"}),
        response({"ok": True}),
    )
    client = ResilientPublicHttpClient(
        transport,
        policy=RetryPolicy(max_attempts=2, min_request_interval_seconds=0),
        sleep=sleep,
    )

    run(client.get_json("https://example.invalid/public"))

    assert sleep.values == [0.25]


def test_stdlib_transport_requires_https_before_network_access():
    from app.market.exchange import StdlibJsonTransport

    with pytest.raises(ValueError, match="HTTPS"):
        run(
            StdlibJsonTransport().get_json(
                "http://example.invalid/public",
                params=None,
                timeout_seconds=1,
            )
        )
