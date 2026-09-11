from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.market.features.models import FeatureSnapshot
from app.market.scanner.models import CandidateOpportunity

from .ids import canonical_json, stable_digest
from .setup_stats import (
    SETUP_DEFINITION_VERSION,
    HistoricalSetupStatsCatalog,
)
from .splits import BacktestPeriodRole


FROZEN_DENVER_PRIOR_VERSION = "frozen-denver-prior-v1"
FROZEN_DENVER_PRIOR_SCHEMA = "money-heist.denver-prior.v1"


class DenverPriorPolicy(StrEnum):
    """Policy describing which already-closed samples may enter a frozen prior."""

    STRICT_PRE_OOS = "STRICT_PRE_OOS"
    ALL_CLOSED_BEFORE_CUTOFF = "ALL_CLOSED_BEFORE_CUTOFF"


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _utc(value, field_name="datetime").isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class FrozenDenverPriorCatalog:
    """Content-addressed, immutable Denver prior frozen before a target period."""

    catalog: HistoricalSetupStatsCatalog
    cutoff: datetime
    policy: DenverPriorPolicy
    version: str = FROZEN_DENVER_PRIOR_VERSION

    def __post_init__(self) -> None:
        cutoff = _utc(self.cutoff, field_name="cutoff")
        object.__setattr__(self, "cutoff", cutoff)

        if self.version != FROZEN_DENVER_PRIOR_VERSION:
            raise ValueError("unsupported frozen Denver prior version")
        if not self.catalog.observations:
            raise ValueError("frozen Denver prior requires at least one observation")

        future = tuple(
            item
            for item in self.catalog.observations
            if item.closed_at > cutoff
        )
        if future:
            raise ValueError(
                "frozen Denver prior contains observations after cutoff"
            )

        if self.policy is DenverPriorPolicy.STRICT_PRE_OOS:
            forbidden = tuple(
                item
                for item in self.catalog.observations
                if item.period_role is BacktestPeriodRole.OOS
            )
            if forbidden:
                raise ValueError(
                    "STRICT_PRE_OOS prior cannot contain OOS observations"
                )

    @property
    def prior_id(self) -> str:
        return "denver-prior:" + stable_digest(self.canonical_payload())

    @property
    def observation_count(self) -> int:
        return len(self.catalog.observations)

    @property
    def source_run_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted({item.run_id for item in self.catalog.observations})
        )

    @property
    def source_dataset_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted({item.dataset_id for item in self.catalog.observations})
        )

    @property
    def source_period_roles(self) -> tuple[str, ...]:
        return tuple(
            sorted({item.period_role.value for item in self.catalog.observations})
        )

    @property
    def reproducibility_assumptions(self) -> dict[str, str]:
        assumptions = {
            "denver_prior_version": self.version,
            "denver_prior_id": self.prior_id,
            "denver_prior_policy": self.policy.value,
            "denver_prior_cutoff": _iso(self.cutoff),
            "denver_prior_catalog_id": self.catalog.catalog_id,
            "denver_setup_definition_version": SETUP_DEFINITION_VERSION,
            "denver_prior_observation_count": str(self.observation_count),
        }
        if self.catalog.strategy_fingerprint is not None:
            assumptions["denver_source_strategy_fingerprint"] = (
                self.catalog.strategy_fingerprint
            )
        return assumptions

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": FROZEN_DENVER_PRIOR_SCHEMA,
            "version": self.version,
            "policy": self.policy.value,
            "cutoff": self.cutoff,
            "catalog": json.loads(self.catalog.to_json()),
        }

    def to_json(self) -> str:
        payload = dict(self.canonical_payload())
        payload["prior_id"] = self.prior_id
        return canonical_json(payload)

    @classmethod
    def from_json(cls, payload: str) -> "FrozenDenverPriorCatalog":
        raw = json.loads(payload)
        if raw.get("schema") != FROZEN_DENVER_PRIOR_SCHEMA:
            raise ValueError("unsupported frozen Denver prior schema")
        if raw.get("version") != FROZEN_DENVER_PRIOR_VERSION:
            raise ValueError("unsupported frozen Denver prior version")

        catalog_payload = canonical_json(raw.get("catalog"))
        catalog = HistoricalSetupStatsCatalog.from_json(catalog_payload)
        prior = cls(
            catalog=catalog,
            cutoff=datetime.fromisoformat(
                str(raw["cutoff"]).replace("Z", "+00:00")
            ),
            policy=DenverPriorPolicy(str(raw["policy"])),
            version=str(raw["version"]),
        )
        if raw.get("prior_id") != prior.prior_id:
            raise ValueError("frozen Denver prior_id does not match content")
        return prior

    def validate_for_target(
        self,
        *,
        period_start: datetime,
        formal_oos: bool,
    ) -> None:
        start = _utc(period_start, field_name="period_start")
        if self.cutoff > start:
            raise ValueError(
                "Denver prior cutoff cannot be later than target period_start"
            )
        if (
            formal_oos
            and self.policy is not DenverPriorPolicy.STRICT_PRE_OOS
        ):
            raise ValueError(
                "formal OOS requires STRICT_PRE_OOS Denver prior policy"
            )


def freeze_denver_prior(
    source: HistoricalSetupStatsCatalog,
    *,
    cutoff: datetime,
    policy: DenverPriorPolicy = DenverPriorPolicy.STRICT_PRE_OOS,
) -> FrozenDenverPriorCatalog:
    """Freeze an existing historical catalog under an explicit anti-contamination policy."""

    frozen_cutoff = _utc(cutoff, field_name="cutoff")
    eligible = []
    for item in source.observations:
        if item.closed_at > frozen_cutoff:
            continue
        if (
            policy is DenverPriorPolicy.STRICT_PRE_OOS
            and item.period_role is BacktestPeriodRole.OOS
        ):
            continue
        eligible.append(item)

    if not eligible:
        raise ValueError(
            "no Denver observations are eligible for the requested prior"
        )
    return FrozenDenverPriorCatalog(
        catalog=HistoricalSetupStatsCatalog(tuple(eligible)),
        cutoff=frozen_cutoff,
        policy=policy,
    )


class FrozenDenverPriorContextProvider:
    """Read-only Denver provider backed only by one pre-frozen prior artifact."""

    def __init__(self, prior: FrozenDenverPriorCatalog) -> None:
        self.prior = prior

    @classmethod
    def for_backtest(
        cls,
        prior: FrozenDenverPriorCatalog,
        *,
        config: Any,
        period_start: datetime,
        formal_oos: bool,
    ) -> "FrozenDenverPriorContextProvider":
        prior.validate_for_target(
            period_start=period_start,
            formal_oos=formal_oos,
        )
        actual = dict(
            getattr(config, "execution_assumptions", {}) or {}
        )
        expected = prior.reproducibility_assumptions
        missing = sorted(key for key in expected if key not in actual)
        mismatched = sorted(
            key
            for key, value in expected.items()
            if key in actual and actual[key] != value
        )
        if missing or mismatched:
            details = []
            if missing:
                details.append("missing=" + ",".join(missing))
            if mismatched:
                details.append("mismatched=" + ",".join(mismatched))
            raise ValueError(
                "BacktestConfig.execution_assumptions does not bind "
                "frozen Denver prior: "
                + "; ".join(details)
            )
        return cls(prior)

    @property
    def reproducibility_assumptions(self) -> dict[str, str]:
        return self.prior.reproducibility_assumptions

    def contexts_for(
        self,
        *,
        opportunity: CandidateOpportunity,
        market_context: FeatureSnapshot,
    ) -> dict[str, Any]:
        observed_at = _utc(
            market_context.observed_at,
            field_name="market_context.observed_at",
        )
        if observed_at < self.prior.cutoff:
            raise ValueError(
                "Denver prior cutoff is later than market observed_at"
            )

        stats = self.prior.catalog.query(
            opportunity=opportunity,
            market_context=market_context,
            as_of=observed_at,
        )
        if stats is None:
            return {}

        payload = stats.to_denver_context_payload()
        payload["notes"] = tuple(payload.get("notes", ())) + (
            f"prior_id={self.prior.prior_id}",
            f"prior_policy={self.prior.policy.value}",
            f"prior_cutoff={_iso(self.prior.cutoff)}",
        )
        return {"denver": payload}


__all__ = [
    "DenverPriorPolicy",
    "FROZEN_DENVER_PRIOR_SCHEMA",
    "FROZEN_DENVER_PRIOR_VERSION",
    "FrozenDenverPriorCatalog",
    "FrozenDenverPriorContextProvider",
    "freeze_denver_prior",
]
