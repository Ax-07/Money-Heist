from __future__ import annotations

import base64
import hashlib
import hmac
import os
import threading
import time
from dataclasses import dataclass
from typing import Mapping, Protocol
from urllib.parse import urlencode


@dataclass(frozen=True, slots=True, repr=False)
class KrakenCredentials:
    api_key: str
    api_secret: str

    def __post_init__(self) -> None:
        if not self.api_key.strip() or not self.api_secret.strip():
            raise ValueError("Kraken credentials must not be blank")

    def __repr__(self) -> str:
        return "KrakenCredentials(api_key=<redacted>, api_secret=<redacted>)"


class KrakenCredentialProvider(Protocol):
    def load(self) -> KrakenCredentials: ...


class EnvironmentKrakenCredentialProvider:
    """Credentials boundary only. Loading credentials never authorizes LIVE execution."""

    API_KEY_ENV = "MONEY_HEIST_KRAKEN_API_KEY"
    API_SECRET_ENV = "MONEY_HEIST_KRAKEN_API_SECRET"

    def load(self) -> KrakenCredentials:
        key = os.getenv(self.API_KEY_ENV, "")
        secret = os.getenv(self.API_SECRET_ENV, "")
        return KrakenCredentials(api_key=key, api_secret=secret)


class KrakenNonce:
    """Process-local monotonically increasing nonce generator for one API key."""

    def __init__(self, clock_ns=time.time_ns) -> None:
        self._clock_ns = clock_ns
        self._lock = threading.Lock()
        self._last = 0

    def next(self) -> int:
        candidate = self._clock_ns() // 1_000_000
        with self._lock:
            value = max(candidate, self._last + 1)
            self._last = value
            return value


def encode_kraken_form(payload: Mapping[str, object]) -> bytes:
    return urlencode([(key, str(value)) for key, value in payload.items()]).encode("utf-8")


def sign_kraken_request(*, url_path: str, payload: Mapping[str, object], api_secret: str) -> str:
    """Kraken Spot REST API-Sign: HMAC-SHA512(path + SHA256(nonce + POST data))."""

    if "nonce" not in payload:
        raise ValueError("nonce is required for Kraken private authentication")
    postdata = encode_kraken_form(payload)
    encoded = str(payload["nonce"]).encode("utf-8") + postdata
    digest = hashlib.sha256(encoded).digest()
    try:
        secret = base64.b64decode(api_secret, validate=True)
    except Exception as exc:
        raise ValueError("Kraken API secret must be valid base64") from exc
    mac = hmac.new(secret, url_path.encode("utf-8") + digest, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode("ascii")
