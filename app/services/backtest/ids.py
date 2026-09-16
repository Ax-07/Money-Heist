from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from app.common.canonical import (
    canonical_json,
    stable_digest,
    stable_uuid,
)
from app.common.canonical import (
    canonicalize as _canonicalize,  # noqa: F401
)


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


__all__ = ["ReplayIdFactory", "canonical_json", "stable_digest", "stable_uuid"]
