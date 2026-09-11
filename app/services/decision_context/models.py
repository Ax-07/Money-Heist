from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.market.features.multitimeframe import MultiTimeframeFeatureContext
from app.trading.risk.models import MarketConstraints, PortfolioRiskState


AGENT_CONTEXT_BINDING_VERSION = "decision-context-agent-binding-v1"


class ContextAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


def _as_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _canonicalize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonicalize(getattr(value, field.name))
            for field in fields(value)
            if not field.name.startswith("_")
        }
    if hasattr(value, "model_dump"):
        return _canonicalize(value.model_dump(mode="json"))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical decimals must be finite")
        if value == 0:
            return "0"
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return _as_utc(value, field="canonical datetime").isoformat().replace(
            "+00:00", "Z"
        )
    if isinstance(value, StrEnum):
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


def _stable_digest(value: Any) -> str:
    encoded = json.dumps(
        _canonicalize(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_safe_payload(value: Any) -> Any:
    """Serialize DecisionContext content for agent input without changing floats."""
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_safe_payload(getattr(value, field.name))
            for field in fields(value)
            if not field.name.startswith("_")
        }
    if hasattr(value, "model_dump"):
        return _json_safe_payload(value.model_dump(mode="json"))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("payload decimals must be finite")
        return format(value, "f")
    if isinstance(value, datetime):
        return _as_utc(value, field="payload datetime").isoformat().replace(
            "+00:00", "Z"
        )
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe_payload(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_json_safe_payload(item) for item in value]
    if value is None or isinstance(value, (str, int, bool, float)):
        return value
    raise TypeError(f"unsupported payload value: {type(value).__name__}")


def decision_context_payload(context: DecisionContextV1) -> dict[str, Any]:
    """Return the stable JSON-safe representation supplied to AI agents."""
    if not isinstance(context, DecisionContextV1):
        raise TypeError("context must be DecisionContextV1")
    payload = _json_safe_payload(context)
    if not isinstance(payload, dict):
        raise TypeError("DecisionContext payload must serialize to a mapping")
    return payload

@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    component: str
    source: str
    observed_at: datetime
    available_at: datetime
    quality: str = "UNKNOWN"
    missing_fields: tuple[str, ...] = ()
    source_fingerprint: str | None = None

    def __post_init__(self) -> None:
        component = self.component.strip()
        source = self.source.strip()
        quality = self.quality.strip().upper()
        observed_at = _as_utc(self.observed_at, field="observed_at")
        available_at = _as_utc(self.available_at, field="available_at")
        missing = tuple(sorted(str(item).strip() for item in self.missing_fields if str(item).strip()))

        if not component:
            raise ValueError("provenance component must not be empty")
        if not source:
            raise ValueError("provenance source must not be empty")
        if not quality:
            raise ValueError("provenance quality must not be empty")
        if observed_at > available_at:
            raise ValueError("provenance observed_at cannot be later than available_at")
        if self.source_fingerprint is not None:
            fingerprint = self.source_fingerprint.strip().lower()
            if len(fingerprint) != 64 or any(
                char not in "0123456789abcdef" for char in fingerprint
            ):
                raise ValueError(
                    "source_fingerprint must be a 64-character hex digest"
                )
            object.__setattr__(self, "source_fingerprint", fingerprint)

        object.__setattr__(self, "component", component)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "quality", quality)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(self, "missing_fields", missing)


@dataclass(frozen=True, slots=True)
class OptionalContextSection:
    status: ContextAvailability
    payload: Mapping[str, Any] | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        reason = self.reason.strip() if self.reason is not None else None
        if self.status is ContextAvailability.AVAILABLE:
            if self.payload is None:
                raise ValueError("AVAILABLE context section requires payload")
            frozen = MappingProxyType(dict(sorted(self.payload.items())))
            object.__setattr__(self, "payload", frozen)
        else:
            if self.payload is not None:
                raise ValueError("UNAVAILABLE context section cannot carry payload")
            if not reason:
                raise ValueError("UNAVAILABLE context section requires reason")
        object.__setattr__(self, "reason", reason)

    @classmethod
    def unavailable(cls, reason: str) -> OptionalContextSection:
        return cls(
            status=ContextAvailability.UNAVAILABLE,
            payload=None,
            reason=reason,
        )


@dataclass(frozen=True, slots=True)
class PortfolioSummary:
    equity: Decimal
    day_start_equity: Decimal
    equity_peak: Decimal
    daily_pnl: Decimal
    open_positions: int
    open_risk_amount: Decimal
    correlated_risk_amount: Decimal
    gross_exposure_amount: Decimal

    @classmethod
    def from_state(cls, state: PortfolioRiskState) -> PortfolioSummary:
        return cls(
            equity=state.equity,
            day_start_equity=state.day_start_equity,
            equity_peak=state.equity_peak,
            daily_pnl=state.daily_pnl,
            open_positions=state.open_positions,
            open_risk_amount=state.open_risk_amount,
            correlated_risk_amount=state.correlated_risk_amount,
            gross_exposure_amount=state.gross_exposure_amount,
        )


@dataclass(frozen=True, slots=True)
class MarketConstraintsSummary:
    qty_step: Decimal
    min_qty: Decimal
    min_notional: Decimal
    max_qty: Decimal | None
    max_leverage: Decimal | None

    @classmethod
    def from_constraints(
        cls,
        constraints: MarketConstraints,
    ) -> MarketConstraintsSummary:
        return cls(
            qty_step=constraints.qty_step,
            min_qty=constraints.min_qty,
            min_notional=constraints.min_notional,
            max_qty=constraints.max_qty,
            max_leverage=constraints.max_leverage,
        )


@dataclass(frozen=True, slots=True)
class DecisionContextV1:
    schema_version: str
    context_version: str
    context_id: str
    context_fingerprint: str
    system_id: str
    symbol: str
    as_of: datetime
    primary_timeframe: str
    timeframe_policy_version: str
    market: MultiTimeframeFeatureContext
    structure: OptionalContextSection
    derivatives: OptionalContextSection
    statistics: OptionalContextSection
    portfolio_summary: PortfolioSummary | None
    market_constraints: MarketConstraintsSummary | None
    microstructure: OptionalContextSection
    provenance: Mapping[str, ProvenanceRecord]
    missing_components: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != "1.0":
            raise ValueError("DecisionContextV1 schema_version must be '1.0'")
        context_version = self.context_version.strip()
        system_id = self.system_id.strip()
        symbol = self.symbol.strip()
        primary = self.primary_timeframe.strip().lower()
        policy = self.timeframe_policy_version.strip()
        if not all((context_version, system_id, symbol, primary, policy)):
            raise ValueError("DecisionContext identity fields must not be empty")

        as_of = _as_utc(self.as_of, field="as_of")
        if self.market.symbol != symbol:
            raise ValueError("market context symbol does not match DecisionContext")
        if self.market.observed_at != as_of:
            raise ValueError("market context observed_at must equal DecisionContext as_of")
        if self.market.decision_timeframe != primary:
            raise ValueError(
                "market decision timeframe must equal DecisionContext primary_timeframe"
            )

        frozen_provenance = MappingProxyType(dict(sorted(self.provenance.items())))
        for key, record in frozen_provenance.items():
            if record.component != key:
                raise ValueError(
                    "provenance mapping key must match ProvenanceRecord.component"
                )
            if record.available_at > as_of:
                raise ValueError(
                    f"lookahead rejected: {key}.available_at is later than DecisionContext.as_of"
                )

        market_provenance = frozen_provenance.get("market")
        if market_provenance is None:
            raise ValueError("DecisionContext requires market provenance")
        if (
            market_provenance.source_fingerprint
            != self.market.context_fingerprint
        ):
            raise ValueError(
                "market provenance fingerprint must match MTF feature context"
            )
        if self.portfolio_summary is not None and "portfolio_summary" not in frozen_provenance:
            raise ValueError(
                "portfolio_summary requires provenance"
            )
        if self.market_constraints is not None and "market_constraints" not in frozen_provenance:
            raise ValueError(
                "market_constraints requires provenance"
            )

        for name in ("structure", "derivatives", "statistics", "microstructure"):
            section = getattr(self, name)
            if (
                section.status is ContextAvailability.AVAILABLE
                and name not in frozen_provenance
            ):
                raise ValueError(f"{name} requires provenance")

        expected_missing = set()
        for name in ("structure", "derivatives", "statistics", "microstructure"):
            if getattr(self, name).status is ContextAvailability.UNAVAILABLE:
                expected_missing.add(name)
        if self.portfolio_summary is None:
            expected_missing.add("portfolio_summary")
        if self.market_constraints is None:
            expected_missing.add("market_constraints")
        if set(self.missing_components) != expected_missing:
            raise ValueError(
                "missing_components must exactly match unavailable DecisionContext sections"
            )

        payload = _decision_payload(
            schema_version=self.schema_version,
            context_version=context_version,
            system_id=system_id,
            symbol=symbol,
            as_of=as_of,
            primary_timeframe=primary,
            timeframe_policy_version=policy,
            market=self.market,
            structure=self.structure,
            derivatives=self.derivatives,
            statistics=self.statistics,
            portfolio_summary=self.portfolio_summary,
            market_constraints=self.market_constraints,
            microstructure=self.microstructure,
            provenance=frozen_provenance,
            missing_components=tuple(sorted(expected_missing)),
        )
        expected_fingerprint = _stable_digest(payload)
        if self.context_fingerprint != expected_fingerprint:
            raise ValueError("DecisionContext fingerprint does not match content")
        expected_id = str(
            uuid5(
                NAMESPACE_URL,
                f"money-heist:decision-context:{expected_fingerprint}",
            )
        )
        if self.context_id != expected_id:
            raise ValueError("DecisionContext id does not match fingerprint")

        object.__setattr__(self, "context_version", context_version)
        object.__setattr__(self, "system_id", system_id)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "primary_timeframe", primary)
        object.__setattr__(self, "timeframe_policy_version", policy)
        object.__setattr__(self, "provenance", frozen_provenance)
        object.__setattr__(
            self,
            "missing_components",
            tuple(sorted(expected_missing)),
        )


def _decision_payload(
    *,
    schema_version: str,
    context_version: str,
    system_id: str,
    symbol: str,
    as_of: datetime,
    primary_timeframe: str,
    timeframe_policy_version: str,
    market: MultiTimeframeFeatureContext,
    structure: OptionalContextSection,
    derivatives: OptionalContextSection,
    statistics: OptionalContextSection,
    portfolio_summary: PortfolioSummary | None,
    market_constraints: MarketConstraintsSummary | None,
    microstructure: OptionalContextSection,
    provenance: Mapping[str, ProvenanceRecord],
    missing_components: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema": "money-heist.decision-context.v1",
        "schema_version": schema_version,
        "context_version": context_version,
        "system_id": system_id,
        "symbol": symbol,
        "as_of": as_of,
        "primary_timeframe": primary_timeframe,
        "timeframe_policy_version": timeframe_policy_version,
        "market": market,
        "structure": structure,
        "derivatives": derivatives,
        "statistics": statistics,
        "portfolio_summary": portfolio_summary,
        "market_constraints": market_constraints,
        "microstructure": microstructure,
        "provenance": provenance,
        "missing_components": missing_components,
    }


def build_decision_context(
    *,
    system_id: str,
    as_of: datetime,
    primary_timeframe: str,
    timeframe_policy_version: str,
    market: MultiTimeframeFeatureContext,
    portfolio_state: PortfolioRiskState | None = None,
    market_constraints: MarketConstraints | None = None,
    structure: OptionalContextSection | None = None,
    derivatives: OptionalContextSection | None = None,
    statistics: OptionalContextSection | None = None,
    microstructure: OptionalContextSection | None = None,
    provenance: Mapping[str, ProvenanceRecord] | None = None,
    market_available_at: datetime | None = None,
    context_version: str = "decision-context-v1",
) -> DecisionContextV1:
    """Build one immutable, anti-lookahead DecisionContext.

    Batch 16.21d intentionally leaves non-market domains unavailable unless
    deterministic inputs are explicitly supplied by later parity batches.
    """

    as_of = _as_utc(as_of, field="as_of")
    if market.observed_at != as_of:
        raise ValueError(
            "market.observed_at must equal DecisionContext as_of"
        )

    structure = structure or OptionalContextSection.unavailable(
        "market-structure parity not wired yet"
    )
    derivatives = derivatives or OptionalContextSection.unavailable(
        "historical derivatives context unavailable"
    )
    statistics = statistics or OptionalContextSection.unavailable(
        "historical statistics context not frozen for this decision"
    )
    microstructure = microstructure or OptionalContextSection.unavailable(
        "microstructure source unavailable"
    )

    portfolio_summary = (
        PortfolioSummary.from_state(portfolio_state)
        if portfolio_state is not None
        else None
    )
    constraints_summary = (
        MarketConstraintsSummary.from_constraints(market_constraints)
        if market_constraints is not None
        else None
    )

    quality = (
        "COMPLETE"
        if market.all_warmups_complete
        else "PARTIAL"
    )
    market_missing = tuple(
        [f"missing:{item}" for item in market.missing_timeframes]
        + [
            f"warmup:{item}"
            for item in market.warmup_incomplete_timeframes
        ]
    )
    provenance_map: dict[str, ProvenanceRecord] = {
        "market": ProvenanceRecord(
            component="market",
            source="multi_timeframe_feature_context",
            observed_at=market.observed_at,
            available_at=market_available_at or market.observed_at,
            quality=quality,
            missing_fields=market_missing,
            source_fingerprint=market.context_fingerprint,
        )
    }
    if portfolio_summary is not None:
        provenance_map["portfolio_summary"] = ProvenanceRecord(
            component="portfolio_summary",
            source="portfolio_risk_state",
            observed_at=as_of,
            available_at=as_of,
            quality="CURRENT",
        )
    if constraints_summary is not None:
        provenance_map["market_constraints"] = ProvenanceRecord(
            component="market_constraints",
            source="market_constraints_provider",
            observed_at=as_of,
            available_at=as_of,
            quality="CURRENT",
        )
    if provenance:
        provenance_map.update(provenance)

    missing = set()
    for name, section in {
        "structure": structure,
        "derivatives": derivatives,
        "statistics": statistics,
        "microstructure": microstructure,
    }.items():
        if section.status is ContextAvailability.UNAVAILABLE:
            missing.add(name)
    if portfolio_summary is None:
        missing.add("portfolio_summary")
    if constraints_summary is None:
        missing.add("market_constraints")

    payload = _decision_payload(
        schema_version="1.0",
        context_version=context_version.strip(),
        system_id=system_id.strip(),
        symbol=market.symbol,
        as_of=as_of,
        primary_timeframe=primary_timeframe.strip().lower(),
        timeframe_policy_version=timeframe_policy_version.strip(),
        market=market,
        structure=structure,
        derivatives=derivatives,
        statistics=statistics,
        portfolio_summary=portfolio_summary,
        market_constraints=constraints_summary,
        microstructure=microstructure,
        provenance=provenance_map,
        missing_components=tuple(sorted(missing)),
    )
    fingerprint = _stable_digest(payload)
    context_id = str(
        uuid5(
            NAMESPACE_URL,
            f"money-heist:decision-context:{fingerprint}",
        )
    )

    return DecisionContextV1(
        schema_version="1.0",
        context_version=context_version,
        context_id=context_id,
        context_fingerprint=fingerprint,
        system_id=system_id,
        symbol=market.symbol,
        as_of=as_of,
        primary_timeframe=primary_timeframe,
        timeframe_policy_version=timeframe_policy_version,
        market=market,
        structure=structure,
        derivatives=derivatives,
        statistics=statistics,
        portfolio_summary=portfolio_summary,
        market_constraints=constraints_summary,
        microstructure=microstructure,
        provenance=provenance_map,
        missing_components=tuple(sorted(missing)),
    )
