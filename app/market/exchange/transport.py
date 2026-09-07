from __future__ import annotations

import asyncio
import json
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from typing import Any, Awaitable, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .models import (
    ExchangeHttpError,
    ExchangeNetworkError,
    ExchangePayloadError,
    ExchangeRateLimitError,
    PublicHttpResponse,
)


class TransportNetworkError(OSError):
    pass


class TransportInvalidJsonError(ValueError):
    pass


class JsonTransport(Protocol):
    async def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None,
        timeout_seconds: float,
    ) -> PublicHttpResponse: ...


def _headers_to_dict(headers: Message | Mapping[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    if isinstance(headers, Message):
        return {key.lower(): value for key, value in headers.items()}
    return {str(key).lower(): str(value) for key, value in headers.items()}


class StdlibJsonTransport:
    """Small public GET transport; intentionally has no auth/header secret support."""

    def __init__(self, *, user_agent: str = "money-heist-market-data/1") -> None:
        if not user_agent.strip():
            raise ValueError("user_agent must not be blank")
        self._user_agent = user_agent

    async def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None,
        timeout_seconds: float,
    ) -> PublicHttpResponse:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if urlsplit(url).scheme.lower() != "https":
            raise ValueError("public exchange transport requires HTTPS")
        return await asyncio.to_thread(
            self._get_json_sync,
            url,
            dict(params or {}),
            timeout_seconds,
        )

    def _get_json_sync(
        self,
        url: str,
        params: Mapping[str, str | int],
        timeout_seconds: float,
    ) -> PublicHttpResponse:
        query = urlencode(params)
        full_url = f"{url}?{query}" if query else url
        request = Request(
            full_url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": self._user_agent,
            },
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read()
                received_at = datetime.now(timezone.utc)
                return PublicHttpResponse(
                    status_code=int(response.status),
                    payload=self._decode_json(body),
                    headers=_headers_to_dict(response.headers),
                    received_at=received_at,
                )
        except HTTPError as exc:
            body = exc.read()
            received_at = datetime.now(timezone.utc)
            try:
                payload = self._decode_json(body)
            except TransportInvalidJsonError:
                payload = None
            return PublicHttpResponse(
                status_code=int(exc.code),
                payload=payload,
                headers=_headers_to_dict(exc.headers),
                received_at=received_at,
            )
        except (URLError, TimeoutError, socket.timeout, OSError) as exc:
            raise TransportNetworkError(str(exc)) from exc

    @staticmethod
    def _decode_json(body: bytes) -> Any:
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TransportInvalidJsonError("response body is not valid UTF-8 JSON") from exc


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    timeout_seconds: float = 5.0
    max_attempts: int = 3
    base_backoff_seconds: float = 0.25
    max_backoff_seconds: float = 2.0
    min_request_interval_seconds: float = 0.20

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be > 0")
        if self.base_backoff_seconds < 0:
            raise ValueError("base_backoff_seconds must be >= 0")
        if self.max_backoff_seconds < self.base_backoff_seconds:
            raise ValueError("max_backoff_seconds must be >= base_backoff_seconds")
        if self.min_request_interval_seconds < 0:
            raise ValueError("min_request_interval_seconds must be >= 0")


class ResilientPublicHttpClient:
    """Bounded retry/backoff/pacing wrapper for unauthenticated public endpoints."""

    def __init__(
        self,
        transport: JsonTransport,
        *,
        policy: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._transport = transport
        self.policy = policy or RetryPolicy()
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_started_at: float | None = None
        self._pace_lock = asyncio.Lock()

    async def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> PublicHttpResponse:
        last_network_error: Exception | None = None
        for attempt in range(1, self.policy.max_attempts + 1):
            await self._pace()
            try:
                response = await self._transport.get_json(
                    url,
                    params=params,
                    timeout_seconds=self.policy.timeout_seconds,
                )
            except (TransportNetworkError, TransportInvalidJsonError) as exc:
                last_network_error = exc
                if attempt == self.policy.max_attempts:
                    if isinstance(exc, TransportInvalidJsonError):
                        raise ExchangePayloadError(str(exc)) from exc
                    raise ExchangeNetworkError(str(exc)) from exc
                await self._sleep(self._backoff(attempt, None))
                continue

            status = response.status_code
            if 200 <= status < 300:
                return response
            if status == 429:
                if attempt == self.policy.max_attempts:
                    raise ExchangeRateLimitError(status, "public API rate limit exceeded")
                await self._sleep(self._backoff(attempt, response.headers))
                continue
            if 500 <= status < 600:
                if attempt == self.policy.max_attempts:
                    raise ExchangeHttpError(status, f"public API server error {status}")
                await self._sleep(self._backoff(attempt, response.headers))
                continue
            raise ExchangeHttpError(status, f"public API returned HTTP {status}")

        raise ExchangeNetworkError(str(last_network_error or "request failed"))

    async def _pace(self) -> None:
        interval = self.policy.min_request_interval_seconds
        if interval <= 0:
            return
        async with self._pace_lock:
            now = self._monotonic()
            if self._last_started_at is not None:
                remaining = interval - (now - self._last_started_at)
                if remaining > 0:
                    await self._sleep(remaining)
                    now = self._monotonic()
            self._last_started_at = now

    def _backoff(self, attempt: int, headers: Mapping[str, str] | None) -> float:
        retry_after = self._retry_after(headers)
        if retry_after is not None:
            return min(retry_after, self.policy.max_backoff_seconds)
        value = self.policy.base_backoff_seconds * (2 ** (attempt - 1))
        return min(value, self.policy.max_backoff_seconds)

    @staticmethod
    def _retry_after(headers: Mapping[str, str] | None) -> float | None:
        if not headers:
            return None
        raw = headers.get("retry-after") or headers.get("Retry-After")
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return max(0.0, value)
