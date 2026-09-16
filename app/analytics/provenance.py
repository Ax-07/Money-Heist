from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


def as_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def normalize_identifier(value: str, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def normalize_sha256(value: str, *, field_name: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"{field_name} must be a 64-character hexadecimal digest")
    return digest


@dataclass(frozen=True, slots=True)
class AnalyticsObservationProvenance:
    """Causal timing contract reserved for future analytics observations."""

    source: str
    event_at: datetime
    available_at: datetime
    as_of: datetime
    source_fingerprint: str | None = None

    def __post_init__(self) -> None:
        source = normalize_identifier(self.source, field_name="source")
        event_at = as_utc(self.event_at, field_name="event_at")
        available_at = as_utc(self.available_at, field_name="available_at")
        as_of = as_utc(self.as_of, field_name="as_of")
        if event_at > available_at:
            raise ValueError("event_at cannot be later than available_at")
        if available_at > as_of:
            raise ValueError("lookahead rejected: available_at cannot be later than as_of")
        fingerprint = self.source_fingerprint
        if fingerprint is not None:
            fingerprint = normalize_sha256(
                fingerprint,
                field_name="source_fingerprint",
            )
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "event_at", event_at)
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "source_fingerprint", fingerprint)


__all__ = [
    "AnalyticsObservationProvenance",
    "as_utc",
    "normalize_identifier",
    "normalize_sha256",
]
