from __future__ import annotations

import asyncio
import json
import socket
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .auth import KrakenCredentialProvider, KrakenNonce, encode_kraken_form, sign_kraken_request
from .errors import LiveAmbiguousSubmissionError, LiveApiError, LiveExchangeRejectError, LiveTransportError


KRAKEN_PRIVATE_BASE_URL = "https://api.kraken.com"


class RawHttpSender(Protocol):
    def send(self, *, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes]: ...


class UrllibRawHttpSender:
    def send(self, *, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes]:
        request = Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed Kraken host
                return int(response.status), response.read()
        except HTTPError as exc:
            return int(exc.code), exc.read()


@dataclass(frozen=True, slots=True)
class KrakenPrivateClientConfig:
    timeout_seconds: float = 5.0
    read_max_attempts: int = 3
    backoff_seconds: float = 0.2
    min_interval_seconds: float = 0.1

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if self.read_max_attempts < 1:
            raise ValueError("read_max_attempts must be >= 1")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must be >= 0")
        if self.min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be >= 0")


class KrakenSpotPrivateRestClient:
    """Strict Spot private API allowlist. No arbitrary endpoint method is exposed."""

    _READ_PATHS = frozenset({
        "/0/private/GetApiKeyInfo",
        "/0/private/Balance",
        "/0/private/OpenOrders",
        "/0/private/ClosedOrders",
        "/0/private/TradesHistory",
    })
    _WRITE_PATHS = frozenset({"/0/private/AddOrder", "/0/private/CancelOrder"})
    _ALL_PATHS = _READ_PATHS | _WRITE_PATHS

    def __init__(
        self,
        *,
        credentials: KrakenCredentialProvider,
        nonce: KrakenNonce | None = None,
        sender: RawHttpSender | None = None,
        config: KrakenPrivateClientConfig | None = None,
        sleep: Callable[[float], object] = asyncio.sleep,
    ) -> None:
        self._credentials = credentials
        self._nonce = nonce or KrakenNonce()
        self._sender = sender or UrllibRawHttpSender()
        self._config = config or KrakenPrivateClientConfig()
        self._sleep = sleep
        self._pace_lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def get_api_key_info(self): return await self._request("/0/private/GetApiKeyInfo", {}, write=False)
    async def get_balance(self): return await self._request("/0/private/Balance", {}, write=False)
    async def get_open_orders(self, *, client_order_id: str | None = None):
        payload = {"trades": "true"}
        if client_order_id: payload["cl_ord_id"] = client_order_id
        return await self._request("/0/private/OpenOrders", payload, write=False)
    async def get_closed_orders(self, *, client_order_id: str | None = None):
        payload = {"trades": "true"}
        if client_order_id: payload["cl_ord_id"] = client_order_id
        return await self._request("/0/private/ClosedOrders", payload, write=False)
    async def get_trades_history(self): return await self._request("/0/private/TradesHistory", {"trades": "false"}, write=False)
    async def add_order(self, payload: Mapping[str, object]): return await self._request("/0/private/AddOrder", payload, write=True)
    async def cancel_order(self, *, client_order_id: str):
        return await self._request("/0/private/CancelOrder", {"txid": client_order_id}, write=True)

    async def _request(self, path: str, payload: Mapping[str, object], *, write: bool):
        if path not in self._ALL_PATHS:
            raise ValueError("private endpoint is not allowlisted")
        if write != (path in self._WRITE_PATHS):
            raise ValueError("operation class mismatch")
        credentials = self._credentials.load()
        attempts = 1 if write else self._config.read_max_attempts
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            await self._pace()
            nonce = self._nonce.next()
            request_payload = {"nonce": nonce, **dict(payload)}
            body = encode_kraken_form(request_payload)
            headers = {
                "API-Key": credentials.api_key,
                "API-Sign": sign_kraken_request(url_path=path, payload=request_payload, api_secret=credentials.api_secret),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": "money-heist-live-broker/14",
            }
            try:
                status, raw = await asyncio.to_thread(
                    self._sender.send,
                    url=KRAKEN_PRIVATE_BASE_URL + path,
                    body=body,
                    headers=headers,
                    timeout=self._config.timeout_seconds,
                )
                if status < 200 or status >= 300:
                    raise LiveTransportError(f"Kraken private HTTP status {status}")
                try:
                    doc = json.loads(raw.decode("utf-8"))
                except Exception as exc:
                    raise LiveTransportError("Kraken private response is not valid JSON") from exc
                if not isinstance(doc, Mapping) or not isinstance(doc.get("error"), list):
                    raise LiveTransportError("Kraken private response schema is invalid")
                errors = tuple(str(item) for item in doc["error"])
                if errors:
                    message = "; ".join(errors)
                    if write:
                        raise LiveExchangeRejectError(message)
                    raise LiveApiError(message)
                result = doc.get("result")
                if not isinstance(result, Mapping):
                    raise LiveTransportError("Kraken private response missing result object")
                return result
            except LiveExchangeRejectError:
                raise
            except (TimeoutError, socket.timeout, URLError, OSError, LiveTransportError) as exc:
                last_error = exc
                if write:
                    raise LiveAmbiguousSubmissionError(
                        "private write outcome is ambiguous; do not retry before reconciliation"
                    ) from exc
                if attempt < attempts:
                    await self._sleep(self._config.backoff_seconds * attempt)
        raise LiveTransportError("Kraken private read failed after bounded retries") from last_error

    async def _pace(self) -> None:
        async with self._pace_lock:
            now = time.monotonic()
            remaining = self._config.min_interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                await self._sleep(remaining)
            self._last_request_at = time.monotonic()
