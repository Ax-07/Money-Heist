from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.canonical import canonical_json, stable_digest, stable_uuid
from app.evaluation.forward_outcomes.models import ForwardOutcomeRecord
from app.evaluation.scanner_forward_outcomes.models import ScannerForwardOutcomeRecord

DECISION_QUALITY_RESEARCH_POLICY_VERSION = "decision-quality-research-exact-join-v1"
DECISION_QUALITY_RESEARCH_HORIZONS = (1, 3, 5, 10, 20)
DECISION_QUALITY_RESEARCH_RUN_SCHEMA_VERSION = "money-heist.decision-quality-research-run.v1"
CANDIDATE_RESEARCH_RECORD_SCHEMA_VERSION = "money-heist.candidate-research-record.v1"
SCANNER_RESEARCH_RECORD_SCHEMA_VERSION = "money-heist.scanner-research-record.v1"
DECISION_QUALITY_RESEARCH_BUNDLE_SCHEMA_VERSION = "money-heist.decision-quality-research-bundle.v1"


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


class ResearchJoinStatus(StrEnum):
    MATCHED = "MATCHED"
    MISSING_DECISION_INTELLIGENCE = "MISSING_DECISION_INTELLIGENCE"
    MISSING_FORWARD_OUTCOME = "MISSING_FORWARD_OUTCOME"
    MISSING_ANALYTICS = "MISSING_ANALYTICS"


class ResearchJoinIssue(StrEnum):
    MISSING_DECISION_INTELLIGENCE = "MISSING_DECISION_INTELLIGENCE"
    MISSING_FORWARD_OUTCOME = "MISSING_FORWARD_OUTCOME"
    MISSING_ANALYTICS = "MISSING_ANALYTICS"


class ResearchIntegrityCode(StrEnum):
    RUN_MISMATCH = "RUN_MISMATCH"
    ROLE_MISMATCH = "ROLE_MISMATCH"
    DATASET_MISMATCH = "DATASET_MISMATCH"
    SYSTEM_MISMATCH = "SYSTEM_MISMATCH"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
    TIMEFRAME_MISMATCH = "TIMEFRAME_MISMATCH"
    OBSERVATION_MISMATCH = "OBSERVATION_MISMATCH"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    DUPLICATE_ID = "DUPLICATE_ID"
    HORIZON_MISMATCH = "HORIZON_MISMATCH"
    CANDIDATE_INCONSISTENCY = "CANDIDATE_INCONSISTENCY"
    SOURCE_FINGERPRINT_MISMATCH = "SOURCE_FINGERPRINT_MISMATCH"


class AnalyticsResearchRef(FrozenModel):
    attribution_record_id: str = Field(min_length=1)
    attribution_record_fingerprint: str = Field(min_length=64, max_length=64)
    analytics_run_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    analytics_snapshot_id: str | None = None
    analytics_snapshot_fingerprint: str | None = None
    analytics_as_of: datetime | None = None
    diagnostics: tuple[str, ...] = ()

    @field_validator("attribution_record_fingerprint", "analytics_snapshot_fingerprint")
    @classmethod
    def normalize_fingerprints(cls, value: str | None, info) -> str | None:
        return _normalize_sha256(value, field_name=info.field_name)

    @field_validator("analytics_as_of")
    @classmethod
    def normalize_as_of(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _as_utc(value, field_name="analytics_as_of")

    @model_validator(mode="after")
    def validate_snapshot_reference(self) -> AnalyticsResearchRef:
        snapshot_values = (
            self.analytics_snapshot_id,
            self.analytics_snapshot_fingerprint,
            self.analytics_as_of,
        )
        if any(value is None for value in snapshot_values) and any(
            value is not None for value in snapshot_values
        ):
            raise ValueError("Analytics snapshot reference must be complete or absent")
        if self.status == "MATCHED" and any(value is None for value in snapshot_values):
            raise ValueError("MATCHED Analytics reference requires a complete snapshot reference")
        if self.status != "MATCHED" and any(value is not None for value in snapshot_values):
            raise ValueError("unmatched Analytics reference cannot carry a snapshot reference")
        if tuple(sorted(set(self.diagnostics))) != self.diagnostics:
            raise ValueError("Analytics diagnostics must be sorted and unique")
        return self


class ScannerResearchProjection(FrozenModel):
    scanner_evaluation_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    classification: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)
    candidate_threshold: int = Field(ge=0, le=100)
    score_margin: int = Field(ge=-100, le=100)
    triggers: tuple[str, ...] = ()
    market_regime: str | None = None
    candidate_opportunity_id: str | None = None

    @model_validator(mode="after")
    def validate_scanner_identity(self) -> ScannerResearchProjection:
        if self.scanner_evaluation_id != self.snapshot_id:
            raise ValueError("scanner_evaluation_id must equal snapshot_id")
        if self.score_margin != self.score - self.candidate_threshold:
            raise ValueError("score_margin must equal score - candidate_threshold")
        if tuple(sorted(set(self.triggers))) != self.triggers:
            raise ValueError("triggers must be sorted and unique")
        if self.classification == "NO_TRIGGER":
            if self.triggers or self.candidate_opportunity_id is not None:
                raise ValueError("NO_TRIGGER cannot contain triggers or a candidate")
        elif self.classification == "TRIGGER_BELOW_CANDIDATE_THRESHOLD":
            if not self.triggers or self.candidate_opportunity_id is not None:
                raise ValueError("below-threshold Scanner record has invalid candidate state")
            if self.score >= self.candidate_threshold:
                raise ValueError("below-threshold Scanner record requires score < threshold")
        elif self.classification == "CANDIDATE_OPPORTUNITY":
            if not self.triggers or self.candidate_opportunity_id is None:
                raise ValueError("candidate Scanner record requires triggers and opportunity id")
            if self.score < self.candidate_threshold:
                raise ValueError("candidate Scanner record requires score >= threshold")
        else:
            raise ValueError("unsupported Scanner classification")
        return self


class CandidateDecisionResearchRef(FrozenModel):
    record_id: str = Field(min_length=1)
    record_fingerprint: str = Field(min_length=64, max_length=64)
    opportunity_fingerprint: str = Field(min_length=64, max_length=64)
    professor_final_direction: str | None = None
    palermo_verdict: str | None = None
    risk_status: str | None = None
    risk_reason_codes: tuple[str, ...] = ()
    paper_pipeline_status: str | None = None
    orchestration_status: str | None = None

    @field_validator("record_fingerprint", "opportunity_fingerprint")
    @classmethod
    def normalize_fingerprints(cls, value: str, info) -> str:
        normalized = _normalize_sha256(value, field_name=info.field_name)
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_reason_codes(self) -> CandidateDecisionResearchRef:
        if tuple(sorted(set(self.risk_reason_codes))) != self.risk_reason_codes:
            raise ValueError("risk_reason_codes must be sorted and unique")
        return self


class ResearchSourceIdentity(FrozenModel):
    source_backtest_run_id: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    period_role: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    dataset_content_sha256: str = Field(min_length=64, max_length=64)
    dataset_source: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    source_timeframe: str = Field(min_length=1)
    decision_timeframe: str = Field(min_length=1)

    @field_validator("dataset_content_sha256")
    @classmethod
    def normalize_dataset_sha(cls, value: str) -> str:
        normalized = _normalize_sha256(value, field_name="dataset_content_sha256")
        assert normalized is not None
        return normalized

    @field_validator("period_role")
    @classmethod
    def validate_period_role(cls, value: str) -> str:
        if value not in {"DESIGN", "VALIDATION", "OOS"}:
            raise ValueError("period_role must be DESIGN, VALIDATION or OOS")
        return value


class CandidateCausalBlock(FrozenModel):
    source: ResearchSourceIdentity
    opportunity_id: str = Field(min_length=1)
    observed_at: datetime
    scanner: ScannerResearchProjection
    analytics: AnalyticsResearchRef
    decision: CandidateDecisionResearchRef | None = None
    causal_fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _as_utc(value, field_name="observed_at")

    @field_validator("causal_fingerprint")
    @classmethod
    def normalize_causal_fingerprint(cls, value: str) -> str:
        normalized = _normalize_sha256(value, field_name="causal_fingerprint")
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_candidate_reference(self) -> CandidateCausalBlock:
        if self.scanner.candidate_opportunity_id != self.opportunity_id:
            raise ValueError("Candidate causal Scanner reference must match opportunity_id")
        return self


class ScannerCausalBlock(FrozenModel):
    source: ResearchSourceIdentity
    scan_id: str = Field(min_length=1)
    observed_at: datetime
    scanner: ScannerResearchProjection
    analytics: AnalyticsResearchRef
    causal_fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _as_utc(value, field_name="observed_at")

    @field_validator("causal_fingerprint")
    @classmethod
    def normalize_causal_fingerprint(cls, value: str) -> str:
        normalized = _normalize_sha256(value, field_name="causal_fingerprint")
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_scan_reference(self) -> ScannerCausalBlock:
        if self.scan_id != self.scanner.scanner_evaluation_id:
            raise ValueError("Scanner causal scan_id must equal scanner_evaluation_id")
        return self


class CandidatePosthocBlock(FrozenModel):
    future_outcome: ForwardOutcomeRecord | None = None
    outcome_fingerprint: str | None = None

    @field_validator("outcome_fingerprint")
    @classmethod
    def normalize_outcome_fingerprint(cls, value: str | None) -> str | None:
        return _normalize_sha256(value, field_name="outcome_fingerprint")

    @model_validator(mode="after")
    def validate_pair(self) -> CandidatePosthocBlock:
        if (self.future_outcome is None) != (self.outcome_fingerprint is None):
            raise ValueError("future_outcome and outcome_fingerprint must be present together")
        return self


class ScannerPosthocBlock(FrozenModel):
    future_outcome: ScannerForwardOutcomeRecord | None = None
    outcome_fingerprint: str | None = None

    @field_validator("outcome_fingerprint")
    @classmethod
    def normalize_outcome_fingerprint(cls, value: str | None) -> str | None:
        return _normalize_sha256(value, field_name="outcome_fingerprint")

    @model_validator(mode="after")
    def validate_pair(self) -> ScannerPosthocBlock:
        if (self.future_outcome is None) != (self.outcome_fingerprint is None):
            raise ValueError("future_outcome and outcome_fingerprint must be present together")
        return self


class CandidateResearchRecord(FrozenModel):
    schema_version: str = CANDIDATE_RESEARCH_RECORD_SCHEMA_VERSION
    policy_version: str = DECISION_QUALITY_RESEARCH_POLICY_VERSION
    research_run_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    record_fingerprint: str = Field(min_length=64, max_length=64)
    period_role: str = Field(min_length=1)
    opportunity_id: str = Field(min_length=1)
    causal: CandidateCausalBlock
    posthoc: CandidatePosthocBlock
    join_status: ResearchJoinStatus
    join_issues: tuple[ResearchJoinIssue, ...] = ()

    @field_validator("record_fingerprint")
    @classmethod
    def normalize_record_fingerprint(cls, value: str) -> str:
        normalized = _normalize_sha256(value, field_name="record_fingerprint")
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_contract(self) -> CandidateResearchRecord:
        if self.schema_version != CANDIDATE_RESEARCH_RECORD_SCHEMA_VERSION:
            raise ValueError("unsupported Candidate research record schema")
        if self.policy_version != DECISION_QUALITY_RESEARCH_POLICY_VERSION:
            raise ValueError("unsupported Decision Quality research policy")
        if self.period_role != self.causal.source.period_role:
            raise ValueError("Candidate period_role must match causal source")
        if self.opportunity_id != self.causal.opportunity_id:
            raise ValueError("Candidate opportunity_id must match causal block")
        if tuple(sorted(set(self.join_issues), key=lambda item: item.value)) != self.join_issues:
            raise ValueError("join_issues must be sorted and unique")
        if self.join_status is ResearchJoinStatus.MATCHED and self.join_issues:
            raise ValueError("MATCHED record cannot contain join issues")
        if self.join_status is not ResearchJoinStatus.MATCHED and not self.join_issues:
            raise ValueError("unmatched record requires join issues")
        return self


class ScannerResearchRecord(FrozenModel):
    schema_version: str = SCANNER_RESEARCH_RECORD_SCHEMA_VERSION
    policy_version: str = DECISION_QUALITY_RESEARCH_POLICY_VERSION
    research_run_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    record_fingerprint: str = Field(min_length=64, max_length=64)
    period_role: str = Field(min_length=1)
    scan_id: str = Field(min_length=1)
    causal: ScannerCausalBlock
    posthoc: ScannerPosthocBlock
    join_status: ResearchJoinStatus
    join_issues: tuple[ResearchJoinIssue, ...] = ()

    @field_validator("record_fingerprint")
    @classmethod
    def normalize_record_fingerprint(cls, value: str) -> str:
        normalized = _normalize_sha256(value, field_name="record_fingerprint")
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_contract(self) -> ScannerResearchRecord:
        if self.schema_version != SCANNER_RESEARCH_RECORD_SCHEMA_VERSION:
            raise ValueError("unsupported Scanner research record schema")
        if self.policy_version != DECISION_QUALITY_RESEARCH_POLICY_VERSION:
            raise ValueError("unsupported Decision Quality research policy")
        if self.period_role != self.causal.source.period_role:
            raise ValueError("Scanner period_role must match causal source")
        if self.scan_id != self.causal.scan_id:
            raise ValueError("Scanner scan_id must match causal block")
        if tuple(sorted(set(self.join_issues), key=lambda item: item.value)) != self.join_issues:
            raise ValueError("join_issues must be sorted and unique")
        if self.join_status is ResearchJoinStatus.MATCHED and self.join_issues:
            raise ValueError("MATCHED record cannot contain join issues")
        if self.join_status is not ResearchJoinStatus.MATCHED and not self.join_issues:
            raise ValueError("unmatched record requires join issues")
        return self


class ResearchOutcomeDefinition(FrozenModel):
    forward_outcome_schema_version: str = Field(min_length=1)
    forward_outcome_policy_version: str = Field(min_length=1)
    scanner_forward_outcome_schema_version: str = Field(min_length=1)
    scanner_forward_outcome_policy_version: str = Field(min_length=1)
    horizons: tuple[int, ...]

    @model_validator(mode="after")
    def validate_horizons(self) -> ResearchOutcomeDefinition:
        if self.horizons != DECISION_QUALITY_RESEARCH_HORIZONS:
            raise ValueError("Decision Quality research requires canonical H1/H3/H5/H10/H20")
        return self


class DecisionQualityResearchRun(FrozenModel):
    schema_version: str = DECISION_QUALITY_RESEARCH_RUN_SCHEMA_VERSION
    policy_version: str = DECISION_QUALITY_RESEARCH_POLICY_VERSION
    research_run_id: str = Field(min_length=1)
    run_fingerprint: str = Field(min_length=64, max_length=64)
    source: ResearchSourceIdentity
    outcome_definition: ResearchOutcomeDefinition

    @field_validator("run_fingerprint")
    @classmethod
    def normalize_run_fingerprint(cls, value: str) -> str:
        normalized = _normalize_sha256(value, field_name="run_fingerprint")
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_versions(self) -> DecisionQualityResearchRun:
        if self.schema_version != DECISION_QUALITY_RESEARCH_RUN_SCHEMA_VERSION:
            raise ValueError("unsupported Decision Quality research-run schema")
        if self.policy_version != DECISION_QUALITY_RESEARCH_POLICY_VERSION:
            raise ValueError("unsupported Decision Quality research policy")
        return self

    @classmethod
    def create(
        cls,
        *,
        source: ResearchSourceIdentity,
        outcome_definition: ResearchOutcomeDefinition,
    ) -> DecisionQualityResearchRun:
        identity_payload = {
            "schema": DECISION_QUALITY_RESEARCH_RUN_SCHEMA_VERSION,
            "policy_version": DECISION_QUALITY_RESEARCH_POLICY_VERSION,
            "source_backtest_run_id": source.source_backtest_run_id,
            "analytics_run_id": source.analytics_run_id,
            "period_role": source.period_role,
            "dataset_id": source.dataset_id,
            "dataset_version": source.dataset_version,
            "dataset_content_sha256": source.dataset_content_sha256,
            "system_id": source.system_id,
            "symbol": source.symbol,
            "source_timeframe": source.source_timeframe,
            "decision_timeframe": source.decision_timeframe,
            "outcome_definition": outcome_definition.model_dump(mode="python"),
        }
        fingerprint_payload = {
            **identity_payload,
            "source": source.model_dump(mode="python"),
        }
        return cls(
            research_run_id=stable_uuid("decision-quality-research-run", identity_payload),
            run_fingerprint=stable_digest(fingerprint_payload),
            source=source,
            outcome_definition=outcome_definition,
        )


class CandidateJoinCoverage(FrozenModel):
    total: int = Field(ge=0)
    joined: int = Field(ge=0)
    missing_decision_intelligence: int = Field(ge=0)
    missing_forward_outcome: int = Field(ge=0)
    missing_analytics: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> CandidateJoinCoverage:
        if self.joined > self.total:
            raise ValueError("candidate joined cannot exceed total")
        return self


class ScannerJoinCoverage(FrozenModel):
    total: int = Field(ge=0)
    joined: int = Field(ge=0)
    missing_forward_outcome: int = Field(ge=0)
    missing_analytics: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> ScannerJoinCoverage:
        if self.joined > self.total:
            raise ValueError("scanner joined cannot exceed total")
        return self


class DecisionQualityResearchBundle(FrozenModel):
    schema_version: str = DECISION_QUALITY_RESEARCH_BUNDLE_SCHEMA_VERSION
    policy_version: str = DECISION_QUALITY_RESEARCH_POLICY_VERSION
    research_run: DecisionQualityResearchRun
    candidate_records: tuple[CandidateResearchRecord, ...]
    scanner_records: tuple[ScannerResearchRecord, ...]
    candidate_coverage: CandidateJoinCoverage
    scanner_coverage: ScannerJoinCoverage
    bundle_fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("bundle_fingerprint")
    @classmethod
    def normalize_bundle_fingerprint(cls, value: str) -> str:
        normalized = _normalize_sha256(value, field_name="bundle_fingerprint")
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_contract(self) -> DecisionQualityResearchBundle:
        if self.schema_version != DECISION_QUALITY_RESEARCH_BUNDLE_SCHEMA_VERSION:
            raise ValueError("unsupported Decision Quality research bundle schema")
        if self.policy_version != DECISION_QUALITY_RESEARCH_POLICY_VERSION:
            raise ValueError("unsupported Decision Quality research policy")
        if self.candidate_coverage.total != len(self.candidate_records):
            raise ValueError("candidate coverage total must equal record count")
        if self.scanner_coverage.total != len(self.scanner_records):
            raise ValueError("scanner coverage total must equal record count")
        run_id = self.research_run.research_run_id
        if any(item.research_run_id != run_id for item in self.candidate_records):
            raise ValueError("candidate record research_run_id mismatch")
        if any(item.research_run_id != run_id for item in self.scanner_records):
            raise ValueError("scanner record research_run_id mismatch")
        candidate_order = tuple(
            sorted(
                self.candidate_records,
                key=lambda item: (item.causal.observed_at, item.opportunity_id, item.record_id),
            )
        )
        scanner_order = tuple(
            sorted(
                self.scanner_records,
                key=lambda item: (item.causal.observed_at, item.scan_id, item.record_id),
            )
        )
        if candidate_order != self.candidate_records:
            raise ValueError("candidate records must be sorted deterministically")
        if scanner_order != self.scanner_records:
            raise ValueError("scanner records must be sorted deterministically")
        return self

    @classmethod
    def create(
        cls,
        *,
        research_run: DecisionQualityResearchRun,
        candidate_records: tuple[CandidateResearchRecord, ...],
        scanner_records: tuple[ScannerResearchRecord, ...],
    ) -> DecisionQualityResearchBundle:
        candidates = tuple(
            sorted(
                candidate_records,
                key=lambda item: (item.causal.observed_at, item.opportunity_id, item.record_id),
            )
        )
        scanners = tuple(
            sorted(
                scanner_records,
                key=lambda item: (item.causal.observed_at, item.scan_id, item.record_id),
            )
        )
        candidate_coverage = CandidateJoinCoverage(
            total=len(candidates),
            joined=sum(item.join_status is ResearchJoinStatus.MATCHED for item in candidates),
            missing_decision_intelligence=sum(
                ResearchJoinIssue.MISSING_DECISION_INTELLIGENCE in item.join_issues
                for item in candidates
            ),
            missing_forward_outcome=sum(
                ResearchJoinIssue.MISSING_FORWARD_OUTCOME in item.join_issues
                for item in candidates
            ),
            missing_analytics=sum(
                ResearchJoinIssue.MISSING_ANALYTICS in item.join_issues for item in candidates
            ),
        )
        scanner_coverage = ScannerJoinCoverage(
            total=len(scanners),
            joined=sum(item.join_status is ResearchJoinStatus.MATCHED for item in scanners),
            missing_forward_outcome=sum(
                ResearchJoinIssue.MISSING_FORWARD_OUTCOME in item.join_issues
                for item in scanners
            ),
            missing_analytics=sum(
                ResearchJoinIssue.MISSING_ANALYTICS in item.join_issues for item in scanners
            ),
        )
        fingerprint_payload = {
            "schema": DECISION_QUALITY_RESEARCH_BUNDLE_SCHEMA_VERSION,
            "policy_version": DECISION_QUALITY_RESEARCH_POLICY_VERSION,
            "research_run_fingerprint": research_run.run_fingerprint,
            "candidate_records": tuple(item.record_fingerprint for item in candidates),
            "scanner_records": tuple(item.record_fingerprint for item in scanners),
            "candidate_coverage": candidate_coverage.model_dump(mode="python"),
            "scanner_coverage": scanner_coverage.model_dump(mode="python"),
        }
        return cls(
            research_run=research_run,
            candidate_records=candidates,
            scanner_records=scanners,
            candidate_coverage=candidate_coverage,
            scanner_coverage=scanner_coverage,
            bundle_fingerprint=stable_digest(fingerprint_payload),
        )

    def to_json(self) -> str:
        return canonical_json(self.model_dump(mode="python"))


__all__ = [
    "AnalyticsResearchRef",
    "CANDIDATE_RESEARCH_RECORD_SCHEMA_VERSION",
    "CandidateCausalBlock",
    "CandidateDecisionResearchRef",
    "CandidateJoinCoverage",
    "CandidatePosthocBlock",
    "CandidateResearchRecord",
    "DECISION_QUALITY_RESEARCH_BUNDLE_SCHEMA_VERSION",
    "DECISION_QUALITY_RESEARCH_HORIZONS",
    "DECISION_QUALITY_RESEARCH_POLICY_VERSION",
    "DECISION_QUALITY_RESEARCH_RUN_SCHEMA_VERSION",
    "DecisionQualityResearchBundle",
    "DecisionQualityResearchRun",
    "ResearchIntegrityCode",
    "ResearchJoinIssue",
    "ResearchJoinStatus",
    "ResearchOutcomeDefinition",
    "ResearchSourceIdentity",
    "SCANNER_RESEARCH_RECORD_SCHEMA_VERSION",
    "ScannerCausalBlock",
    "ScannerJoinCoverage",
    "ScannerPosthocBlock",
    "ScannerResearchProjection",
    "ScannerResearchRecord",
]
