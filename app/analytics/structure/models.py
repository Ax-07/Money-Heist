from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.analytics.provenance import normalize_identifier, normalize_sha256
from app.common.canonical import stable_digest
from app.market.structure import MARKET_STRUCTURE_VERSION, MarketStructureContextV1

ANALYTICS_STRUCTURE_SCHEMA_VERSION = "money-heist.analytics-market-structure.v1"
ANALYTICS_STRUCTURE_VERSION = "money-heist-structure-projection-v1"
ANALYTICS_STRUCTURE_IDENTITY = (
    f"{ANALYTICS_STRUCTURE_VERSION}:{MARKET_STRUCTURE_VERSION}"
)


class StructureSource(StrEnum):
    MONEY_HEIST_STRUCTURE = "MONEY_HEIST_STRUCTURE"
    CAUSAL_ZIGZAG = "CAUSAL_ZIGZAG"


@dataclass(frozen=True, slots=True)
class AnalyticsMarketStructureObservation:
    source: StructureSource
    symbol: str
    as_of: datetime
    source_cursor_fingerprint: str
    production_structure_version: str
    definition_version: str
    fingerprint: str
    context: MarketStructureContextV1
    schema_version: str = ANALYTICS_STRUCTURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_STRUCTURE_SCHEMA_VERSION:
            raise ValueError("unexpected analytics structure schema version")
        if self.source != StructureSource.MONEY_HEIST_STRUCTURE:
            raise ValueError("this projection only represents Money Heist structure")
        object.__setattr__(
            self,
            "symbol",
            normalize_identifier(self.symbol, field_name="symbol"),
        )
        object.__setattr__(
            self,
            "source_cursor_fingerprint",
            normalize_sha256(
                self.source_cursor_fingerprint,
                field_name="source_cursor_fingerprint",
            ),
        )
        object.__setattr__(
            self,
            "definition_version",
            normalize_identifier(
                self.definition_version,
                field_name="definition_version",
            ),
        )
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        object.__setattr__(self, "as_of", self.as_of.astimezone(UTC))
        object.__setattr__(
            self,
            "fingerprint",
            normalize_sha256(self.fingerprint, field_name="fingerprint"),
        )
        if self.production_structure_version != MARKET_STRUCTURE_VERSION:
            raise ValueError("unexpected production structure version")
        if self.context.symbol != self.symbol:
            raise ValueError("projection symbol differs from production context")
        if self.context.observed_at != self.as_of:
            raise ValueError("projection as_of differs from production context")
        if self.context.source_cursor_fingerprint != self.source_cursor_fingerprint:
            raise ValueError("projection cursor fingerprint differs from production context")
        if self.fingerprint != stable_digest(self.identity_payload()):
            raise ValueError("structure projection fingerprint mismatch")

    @classmethod
    def create(
        cls,
        context: MarketStructureContextV1,
    ) -> AnalyticsMarketStructureObservation:
        payload = {
            "schema_version": ANALYTICS_STRUCTURE_SCHEMA_VERSION,
            "source": StructureSource.MONEY_HEIST_STRUCTURE,
            "symbol": context.symbol,
            "as_of": context.observed_at,
            "source_cursor_fingerprint": context.source_cursor_fingerprint,
            "production_structure_version": context.version,
            "definition_version": ANALYTICS_STRUCTURE_VERSION,
            "context_fingerprint": context.context_fingerprint,
        }
        return cls(
            source=StructureSource.MONEY_HEIST_STRUCTURE,
            symbol=context.symbol,
            as_of=context.observed_at,
            source_cursor_fingerprint=context.source_cursor_fingerprint,
            production_structure_version=context.version,
            definition_version=ANALYTICS_STRUCTURE_VERSION,
            context=context,
            fingerprint=stable_digest(payload),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "symbol": self.symbol,
            "as_of": self.as_of,
            "source_cursor_fingerprint": self.source_cursor_fingerprint,
            "production_structure_version": self.production_structure_version,
            "definition_version": self.definition_version,
            "context_fingerprint": self.context.context_fingerprint,
        }


__all__ = [
    "ANALYTICS_STRUCTURE_IDENTITY",
    "ANALYTICS_STRUCTURE_SCHEMA_VERSION",
    "ANALYTICS_STRUCTURE_VERSION",
    "AnalyticsMarketStructureObservation",
    "StructureSource",
]
