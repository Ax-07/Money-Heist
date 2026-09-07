from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LiveAuthorization:
    authorized: bool
    source: str
    reason: str


class LiveAuthorizationProvider(Protocol):
    def get_authorization(self, *, system_id: str) -> LiveAuthorization: ...


class DenyAllLiveAuthorization:
    """Batch 14 production default: there is deliberately no env-based enable switch."""

    def get_authorization(self, *, system_id: str) -> LiveAuthorization:
        return LiveAuthorization(
            authorized=False,
            source="batch14_structural_lock",
            reason="LIVE activation belongs to Batch 15",
        )


@dataclass(frozen=True, slots=True)
class StaticLiveAuthorization:
    """Injection-only helper for deterministic tests; not wired from environment."""

    authorized: bool
    source: str = "injected_test_authorization"
    reason: str = "explicit test fixture"

    def get_authorization(self, *, system_id: str) -> LiveAuthorization:
        return LiveAuthorization(self.authorized, self.source, self.reason)
