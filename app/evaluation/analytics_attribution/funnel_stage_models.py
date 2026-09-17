from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_SCHEMA_VERSION = (
    "money-heist.funnel-stage-analytics-attribution.v1"
)
FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_SET_SCHEMA_VERSION = (
    "money-heist.funnel-stage-analytics-attribution-set.v1"
)
FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_POLICY_VERSION = (
    "funnel-stage-analytics-attribution-v1"
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


class FunnelStage(StrEnum):
    COMPUTE_GATE = "COMPUTE_GATE"
    PROFESSOR_PLAN = "PROFESSOR_PLAN"
    SPECIALIST = "SPECIALIST"
    PALERMO = "PALERMO"
    PROFESSOR_FINAL = "PROFESSOR_FINAL"
    TRADE_PROPOSAL = "TRADE_PROPOSAL"
    RISK = "RISK"
    PAPER = "PAPER"


class FunnelStageAnalyticsAttributionRecord(FrozenModel):
    schema_version: str = FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_SCHEMA_VERSION
    policy_version: str = FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_POLICY_VERSION

    record_id: str = Field(min_length=1)
    record_fingerprint: str = Field(min_length=64, max_length=64)

    source_backtest_run_id: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    decision_intelligence_record_id: str = Field(min_length=1)
    decision_intelligence_record_fingerprint: str = Field(min_length=64, max_length=64)
    opportunity_id: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    decision_timeframe: str = Field(min_length=1)

    stage: FunnelStage
    stage_order: int = Field(ge=0)
    stage_instance_id: str | None = None
    stage_instance_order: int | None = Field(default=None, ge=0)
    agent_id: str | None = None
    agent_request_id: str | None = None
    agent_prompt_version: str | None = None
    agent_route_id: str | None = None
    agent_model_id: str | None = None

    reached: bool
    stage_status: str | None = None
    stage_result: str | None = None
    reason_codes: tuple[str, ...] = ()
    selected_agents: tuple[str, ...] = ()
    confidence: float | None = Field(default=None, ge=0, le=1)
    severity: float | None = Field(default=None, ge=0, le=1)

    failure_code: str | None = None
    failure_stage: str | None = None
    failure_agent_id: str | None = None

    source_projection_path: str = Field(min_length=1)
    source_projection_fingerprint: str = Field(min_length=64, max_length=64)
    source_artifact_ref: str | None = None
    source_artifact_fingerprint: str | None = None

    market_as_of: datetime
    operational_at: datetime | None = None

    analytics_link_id: str = Field(min_length=1)
    analytics_link_fingerprint: str = Field(min_length=64, max_length=64)
    analytics_link_policy_version: str = Field(min_length=1)
    analytics_link_status: str = Field(min_length=1)
    analytics_snapshot_id: str | None = None
    analytics_snapshot_fingerprint: str | None = None
    analytics_as_of: datetime | None = None
    source_cursor_fingerprint: str | None = None
    analytics_snapshot_source_cursor_fingerprint: str | None = None
    analytics_diagnostics: tuple[str, ...] = ()

    @field_validator(
        "record_fingerprint",
        "decision_intelligence_record_fingerprint",
        "source_projection_fingerprint",
        "source_artifact_fingerprint",
        "analytics_link_fingerprint",
        "analytics_snapshot_fingerprint",
        "source_cursor_fingerprint",
        "analytics_snapshot_source_cursor_fingerprint",
    )
    @classmethod
    def normalize_fingerprints(cls, value: str | None, info) -> str | None:
        return _normalize_sha256(value, field_name=info.field_name)

    @field_validator("market_as_of")
    @classmethod
    def normalize_market_as_of(cls, value: datetime) -> datetime:
        return _as_utc(value, field_name="market_as_of")

    @field_validator("operational_at", "analytics_as_of")
    @classmethod
    def normalize_optional_datetimes(cls, value: datetime | None, info) -> datetime | None:
        if value is None:
            return None
        return _as_utc(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_contract(self) -> FunnelStageAnalyticsAttributionRecord:
        if self.schema_version != FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_SCHEMA_VERSION:
            raise ValueError("unsupported funnel-stage attribution schema")
        if self.policy_version != FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_POLICY_VERSION:
            raise ValueError("unsupported funnel-stage attribution policy")

        if self.stage is FunnelStage.SPECIALIST:
            if self.stage_instance_id is None or self.stage_instance_order is None:
                raise ValueError("SPECIALIST stage requires deterministic instance identity/order")
            if self.agent_id is None or self.agent_id != self.stage_instance_id:
                raise ValueError("SPECIALIST agent_id must equal stage_instance_id")
            if not self.reached:
                raise ValueError("SPECIALIST records exist only for reached/attempted instances")
        elif any(
            value is not None
            for value in (
                self.stage_instance_id,
                self.stage_instance_order,
                self.agent_id,
                self.agent_request_id,
                self.agent_prompt_version,
                self.agent_route_id,
                self.agent_model_id,
            )
        ):
            raise ValueError("only SPECIALIST stages may carry specialist identity fields")

        if not self.reached:
            material = (
                self.stage_result,
                self.reason_codes,
                self.selected_agents,
                self.confidence,
                self.severity,
                self.failure_code,
                self.failure_stage,
                self.failure_agent_id,
                self.source_artifact_ref,
                self.source_artifact_fingerprint,
                self.operational_at,
            )
            if any(
                bool(value) if isinstance(value, tuple) else value is not None
                for value in material
            ):
                raise ValueError("not-reached stage cannot carry reached-stage facts")

        failure_values = (
            self.failure_code,
            self.failure_stage,
            self.failure_agent_id,
        )
        if self.failure_code is None and any(value is not None for value in failure_values[1:]):
            raise ValueError("failure metadata requires failure_code")

        snapshot_values = (
            self.analytics_snapshot_id,
            self.analytics_snapshot_fingerprint,
            self.analytics_as_of,
            self.analytics_snapshot_source_cursor_fingerprint,
        )
        if any(value is None for value in snapshot_values) and any(
            value is not None for value in snapshot_values
        ):
            raise ValueError("Analytics snapshot reference must be complete or absent")

        if self.analytics_link_status == "MATCHED":
            if any(value is None for value in snapshot_values):
                raise ValueError("MATCHED stage attribution requires Analytics snapshot reference")
            if self.analytics_as_of != self.market_as_of:
                raise ValueError("matched Analytics as_of must equal stage market_as_of")
            if (
                self.source_cursor_fingerprint is not None
                and self.analytics_snapshot_source_cursor_fingerprint
                != self.source_cursor_fingerprint
            ):
                raise ValueError("matched Analytics cursor must equal decision cursor")
        elif any(value is not None for value in snapshot_values):
            raise ValueError(
                "unmatched stage attribution cannot carry Analytics snapshot reference"
            )

        return self


class FunnelStageAnalyticsAttributionSet(FrozenModel):
    schema_version: str = FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_SET_SCHEMA_VERSION
    policy_version: str = FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_POLICY_VERSION

    source_backtest_run_id: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    source_decision_record_set_fingerprint: str = Field(min_length=64, max_length=64)

    decision_record_count: int = Field(ge=0)
    covered_decision_record_count: int = Field(ge=0)
    stage_record_count: int = Field(ge=0)
    reached_stage_count: int = Field(ge=0)
    not_reached_stage_count: int = Field(ge=0)
    matched_analytics_stage_count: int = Field(ge=0)
    unmatched_analytics_stage_count: int = Field(ge=0)

    records: tuple[FunnelStageAnalyticsAttributionRecord, ...]
    set_fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("source_decision_record_set_fingerprint", "set_fingerprint")
    @classmethod
    def normalize_set_fingerprints(cls, value: str, info) -> str:
        normalized = _normalize_sha256(value, field_name=info.field_name)
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_counts_order_and_scope(self) -> FunnelStageAnalyticsAttributionSet:
        if self.schema_version != FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_SET_SCHEMA_VERSION:
            raise ValueError("unsupported funnel-stage attribution-set schema")
        if self.policy_version != FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_POLICY_VERSION:
            raise ValueError("unsupported funnel-stage attribution-set policy")
        if self.stage_record_count != len(self.records):
            raise ValueError("stage_record_count must equal records length")
        if self.reached_stage_count + self.not_reached_stage_count != self.stage_record_count:
            raise ValueError("reached/not-reached counts must conserve stage records")
        if (
            self.matched_analytics_stage_count + self.unmatched_analytics_stage_count
            != self.stage_record_count
        ):
            raise ValueError("Analytics stage counts must conserve stage records")

        decision_ids = {item.decision_intelligence_record_id for item in self.records}
        if self.covered_decision_record_count != len(decision_ids):
            raise ValueError("covered_decision_record_count must match unique decision records")
        if self.covered_decision_record_count != self.decision_record_count:
            raise ValueError("every DecisionIntelligenceRecord must be covered")

        ids = tuple(item.record_id for item in self.records)
        if len(ids) != len(set(ids)):
            raise ValueError("stage attribution set cannot contain duplicate record_id")

        for item in self.records:
            if item.source_backtest_run_id != self.source_backtest_run_id:
                raise ValueError("stage record source BacktestRun mismatch")
            if item.analytics_run_id != self.analytics_run_id:
                raise ValueError("stage record AnalyticsRun mismatch")

        ordered = tuple(
            sorted(
                self.records,
                key=lambda item: (
                    item.market_as_of,
                    item.opportunity_id,
                    item.stage_order,
                    item.stage_instance_order
                    if item.stage_instance_order is not None
                    else -1,
                    item.stage_instance_id or "",
                    item.record_id,
                ),
            )
        )
        if ordered != self.records:
            raise ValueError("stage attribution records must be deterministically ordered")
        return self


__all__ = [
    "FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_POLICY_VERSION",
    "FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_SCHEMA_VERSION",
    "FUNNEL_STAGE_ANALYTICS_ATTRIBUTION_SET_SCHEMA_VERSION",
    "FunnelStage",
    "FunnelStageAnalyticsAttributionRecord",
    "FunnelStageAnalyticsAttributionSet",
]
