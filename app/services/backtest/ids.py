from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import NAMESPACE_URL, uuid5


def _canonicalize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonicalize(getattr(value, field.name))
            for field in fields(value)
            if not field.name.startswith("_")
        }
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical decimals must be finite")
        if value == 0:
            return "0"
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical datetimes must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonicalize(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return _canonicalize(Decimal(str(value)))
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        _canonicalize(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def stable_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_uuid(kind: str, value: Any) -> str:
    kind = kind.strip()
    if not kind:
        raise ValueError("kind must not be empty")
    return str(uuid5(NAMESPACE_URL, f"money-heist:{kind}:{stable_digest(value)}"))


class ReplayIdFactory:
    """Deterministic sequential IDs scoped to one replay seed."""

    def __init__(self, seed: str, *, namespace: str = "replay") -> None:
        self.seed = seed.strip()
        self.namespace = namespace.strip()
        if not self.seed:
            raise ValueError("seed must not be empty")
        if not self.namespace:
            raise ValueError("namespace must not be empty")
        self._sequence = 0

    def next(self, kind: str = "event") -> str:
        kind = kind.strip()
        if not kind:
            raise ValueError("kind must not be empty")
        self._sequence += 1
        key = f"money-heist:{self.namespace}:{self.seed}:{self._sequence}:{kind}"
        return str(uuid5(NAMESPACE_URL, key))

    def __call__(self) -> str:
        """No-argument form compatible with PaperBroker.id_factory."""
        return self.next("broker")
