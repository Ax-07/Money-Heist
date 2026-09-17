from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.canonical import stable_digest, stable_uuid

OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION = "opportunity-analytics-exact-v1"
OPPORTUNITY_ANALYTICS_LINK_SCHEMA_VERSION = "money-heist.opportunity-analytics-link.v1"
OPPORTUNITY_ANALYTICS_LINK_SET_SCHEMA_VERSION = (
    "money-heist.opportunity-analytics-link-set.v1"
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _normalize_sha256(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a 64-character hexadecimal digest")
    return normalized


class OpportunityAnalyticsLinkStatus(StrEnum):
    MATCHED = "MATCHED"
    MISSING_ANALYTICS_SNAPSHOT = "MISSING_ANALYTICS_SNAPSHOT"
    AMBIGUOUS_ANALYTICS_SNAPSHOT = "AMBIGUOUS_ANALYTICS_SNAPSHOT"
    SOURCE_PROVENANCE_INCOMPLETE = "SOURCE_PROVENANCE_INCOMPLETE"
    SOURCE_BACKTEST_RUN_MISMATCH = "SOURCE_BACKTEST_RUN_MISMATCH"
    DATASET_MISMATCH = "DATASET_MISMATCH"
    SYSTEM_MISMATCH = "SYSTEM_MISMATCH"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
    SOURCE_TIMEFRAME_MISMATCH = "SOURCE_TIMEFRAME_MISMATCH"
    TIMEFRAME_MISMATCH = "TIMEFRAME_MISMATCH"
    AS_OF_MISMATCH = "AS_OF_MISMATCH"
    MTF_POLICY_MISMATCH = "MTF_POLICY_MISMATCH"
    CURSOR_FINGERPRINT_MISMATCH = "CURSOR_FINGERPRINT_MISMATCH"


class DecisionObservationKey(FrozenModel):
    """Generic causal identity reusable by future Scanner attribution batches."""

    source_backtest_run_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    dataset_content_sha256: str = Field(min_length=64, max_length=64)
    dataset_source: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    source_timeframe: str = Field(min_length=1)
    decision_timeframe: str = Field(min_length=1)
    observed_at: datetime
    mtf_policy_version: str | None = None
    source_cursor_fingerprint: str | None = None
    feature_snapshot_id: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    scanner_version: str = Field(min_length=1)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _as_utc(value, field_name="observed_at")

    @field_validator("dataset_content_sha256")
    @classmethod
    def normalize_dataset_sha(cls, value: str) -> str:
        normalized = _normalize_sha256(value, field_name="dataset_content_sha256")
        assert normalized is not None
        return normalized

    @field_validator("source_cursor_fingerprint")
    @classmethod
    def normalize_cursor_sha(cls, value: str | None) -> str | None:
        return _normalize_sha256(value, field_name="source_cursor_fingerprint")

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python")

    @property
    def observation_fingerprint(self) -> str:
        return stable_digest(self.canonical_payload())


class OpportunityObservationRef(FrozenModel):
    observation: DecisionObservationKey
    opportunity_id: str = Field(min_length=1)
    opportunity_fingerprint: str = Field(min_length=64, max_length=64)
    decision_context_id: str | None = None
    decision_context_fingerprint: str | None = None

    @field_validator("opportunity_fingerprint", "decision_context_fingerprint")
    @classmethod
    def normalize_fingerprints(cls, value: str | None, info) -> str | None:
        return _normalize_sha256(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_decision_context_pair(self) -> OpportunityObservationRef:
        if (self.decision_context_id is None) != (
            self.decision_context_fingerprint is None
        ):
            raise ValueError(
                "decision_context_id and decision_context_fingerprint "
                "must be set together"
            )
        return self

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python")


class AnalyticsSnapshotRef(FrozenModel):
    analytics_run_id: str = Field(min_length=1)
    analytics_snapshot_id: str = Field(min_length=1)
    analytics_snapshot_fingerprint: str = Field(min_length=64, max_length=64)
    source_backtest_run_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    dataset_content_sha256: str = Field(min_length=64, max_length=64)
    symbol: str = Field(min_length=1)
    decision_timeframe: str = Field(min_length=1)
    as_of: datetime
    mtf_policy_version: str = Field(min_length=1)
    source_cursor_fingerprint: str = Field(min_length=64, max_length=64)
    analytics_bundle_version: str = Field(min_length=1)

    @field_validator("as_of")
    @classmethod
    def normalize_as_of(cls, value: datetime) -> datetime:
        return _as_utc(value, field_name="as_of")

    @field_validator(
        "analytics_snapshot_fingerprint",
        "dataset_content_sha256",
        "source_cursor_fingerprint",
    )
    @classmethod
    def normalize_sha_fields(cls, value: str, info) -> str:
        normalized = _normalize_sha256(value, field_name=info.field_name)
        assert normalized is not None
        return normalized

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python")


class OpportunityAnalyticsLink(FrozenModel):
    schema_version: str = OPPORTUNITY_ANALYTICS_LINK_SCHEMA_VERSION
    link_policy_version: str = OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION
    link_id: str = Field(min_length=1)
    link_fingerprint: str = Field(min_length=64, max_length=64)
    analytics_run_id: str = Field(min_length=1)
    status: OpportunityAnalyticsLinkStatus
    opportunity: OpportunityObservationRef
    analytics_snapshot: AnalyticsSnapshotRef | None = None
    diagnostics: tuple[str, ...] = ()

    @field_validator("link_fingerprint")
    @classmethod
    def normalize_link_fingerprint(cls, value: str) -> str:
        normalized = _normalize_sha256(value, field_name="link_fingerprint")
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_contract(self) -> OpportunityAnalyticsLink:
        if self.schema_version != OPPORTUNITY_ANALYTICS_LINK_SCHEMA_VERSION:
            raise ValueError("unsupported opportunity analytics link schema")
        if self.link_policy_version != OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION:
            raise ValueError("unsupported opportunity analytics link policy")
        if self.status is OpportunityAnalyticsLinkStatus.MATCHED:
            if self.analytics_snapshot is None:
                raise ValueError("MATCHED link requires analytics_snapshot")
            source = self.opportunity.observation
            target = self.analytics_snapshot
            parity = (
                source.source_backtest_run_id == target.source_backtest_run_id,
                source.dataset_id == target.dataset_id,
                source.dataset_version == target.dataset_version,
                source.dataset_content_sha256 == target.dataset_content_sha256,
                source.symbol == target.symbol,
                source.decision_timeframe == target.decision_timeframe,
                source.observed_at == target.as_of,
                source.mtf_policy_version == target.mtf_policy_version,
                source.source_cursor_fingerprint
                == target.source_cursor_fingerprint,
            )
            if not all(parity):
                raise ValueError("MATCHED link must have exact source/analytics parity")
        return self

    @classmethod
    def create(
        cls,
        *,
        analytics_run_id: str,
        status: OpportunityAnalyticsLinkStatus,
        opportunity: OpportunityObservationRef,
        analytics_snapshot: AnalyticsSnapshotRef | None = None,
        diagnostics: tuple[str, ...] = (),
    ) -> OpportunityAnalyticsLink:
        diagnostics = tuple(sorted(set(diagnostics)))
        identity_payload = {
            "schema": OPPORTUNITY_ANALYTICS_LINK_SCHEMA_VERSION,
            "link_policy_version": OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION,
            "source_backtest_run_id": (
                opportunity.observation.source_backtest_run_id
            ),
            "analytics_run_id": analytics_run_id,
            "opportunity_id": opportunity.opportunity_id,
            "analytics_snapshot_id": (
                analytics_snapshot.analytics_snapshot_id
                if analytics_snapshot is not None
                else None
            ),
        }
        fingerprint_payload = {
            **identity_payload,
            "status": status,
            "opportunity": opportunity.canonical_payload(),
            "analytics_snapshot": (
                analytics_snapshot.canonical_payload()
                if analytics_snapshot is not None
                else None
            ),
            "diagnostics": diagnostics,
        }
        return cls(
            link_id=stable_uuid("opportunity-analytics-link", identity_payload),
            link_fingerprint=stable_digest(fingerprint_payload),
            analytics_run_id=analytics_run_id,
            status=status,
            opportunity=opportunity,
            analytics_snapshot=analytics_snapshot,
            diagnostics=diagnostics,
        )


class LinkStatusCount(FrozenModel):
    status: OpportunityAnalyticsLinkStatus
    count: int = Field(ge=0)


class OpportunityAnalyticsLinkSet(FrozenModel):
    schema_version: str = OPPORTUNITY_ANALYTICS_LINK_SET_SCHEMA_VERSION
    link_policy_version: str = OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION
    source_backtest_run_id: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    analytics_period_role: str = Field(min_length=1)
    total_opportunities: int = Field(ge=0)
    matched: int = Field(ge=0)
    unresolved: int = Field(ge=0)
    ambiguous: int = Field(ge=0)
    status_counts: tuple[LinkStatusCount, ...]
    links: tuple[OpportunityAnalyticsLink, ...]
    summary_fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("summary_fingerprint")
    @classmethod
    def normalize_summary_fingerprint(cls, value: str) -> str:
        normalized = _normalize_sha256(value, field_name="summary_fingerprint")
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_counts_and_order(self) -> OpportunityAnalyticsLinkSet:
        if self.total_opportunities != len(self.links):
            raise ValueError("total_opportunities must equal links length")
        if self.matched + self.unresolved != self.total_opportunities:
            raise ValueError("matched + unresolved must equal total_opportunities")
        if self.ambiguous > self.unresolved:
            raise ValueError("ambiguous cannot exceed unresolved")
        if sum(item.count for item in self.status_counts) != self.total_opportunities:
            raise ValueError("status_counts must conserve total opportunities")
        ordered_counts = tuple(
            sorted(self.status_counts, key=lambda item: item.status.value)
        )
        if ordered_counts != self.status_counts:
            raise ValueError("status_counts must be sorted deterministically")
        ordered_links = tuple(
            sorted(
                self.links,
                key=lambda item: (
                    item.opportunity.observation.observed_at,
                    item.opportunity.opportunity_id,
                    item.link_id,
                ),
            )
        )
        if ordered_links != self.links:
            raise ValueError("links must be sorted deterministically")
        return self

    @classmethod
    def create(
        cls,
        *,
        source_backtest_run_id: str,
        analytics_run_id: str,
        analytics_period_role: str,
        links: tuple[OpportunityAnalyticsLink, ...],
    ) -> OpportunityAnalyticsLinkSet:
        ordered_links = tuple(
            sorted(
                links,
                key=lambda item: (
                    item.opportunity.observation.observed_at,
                    item.opportunity.opportunity_id,
                    item.link_id,
                ),
            )
        )
        counts: dict[OpportunityAnalyticsLinkStatus, int] = {}
        for link in ordered_links:
            counts[link.status] = counts.get(link.status, 0) + 1
        status_counts = tuple(
            LinkStatusCount(status=status, count=counts[status])
            for status in sorted(counts, key=lambda item: item.value)
        )
        matched = counts.get(OpportunityAnalyticsLinkStatus.MATCHED, 0)
        ambiguous = counts.get(
            OpportunityAnalyticsLinkStatus.AMBIGUOUS_ANALYTICS_SNAPSHOT,
            0,
        )
        summary_payload = {
            "schema": OPPORTUNITY_ANALYTICS_LINK_SET_SCHEMA_VERSION,
            "link_policy_version": OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION,
            "source_backtest_run_id": source_backtest_run_id,
            "analytics_run_id": analytics_run_id,
            "analytics_period_role": analytics_period_role,
            "links": tuple(link.link_fingerprint for link in ordered_links),
        }
        return cls(
            source_backtest_run_id=source_backtest_run_id,
            analytics_run_id=analytics_run_id,
            analytics_period_role=analytics_period_role,
            total_opportunities=len(ordered_links),
            matched=matched,
            unresolved=len(ordered_links) - matched,
            ambiguous=ambiguous,
            status_counts=status_counts,
            links=ordered_links,
            summary_fingerprint=stable_digest(summary_payload),
        )


__all__ = [
    "AnalyticsSnapshotRef",
    "DecisionObservationKey",
    "LinkStatusCount",
    "OPPORTUNITY_ANALYTICS_LINK_POLICY_VERSION",
    "OPPORTUNITY_ANALYTICS_LINK_SCHEMA_VERSION",
    "OPPORTUNITY_ANALYTICS_LINK_SET_SCHEMA_VERSION",
    "OpportunityAnalyticsLink",
    "OpportunityAnalyticsLinkSet",
    "OpportunityAnalyticsLinkStatus",
    "OpportunityObservationRef",
]
