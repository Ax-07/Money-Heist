from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.canonical import canonical_json, stable_digest, stable_uuid
from app.evaluation.analytics_attribution.funnel_stage_models import (
    FunnelStage,
    FunnelStageAnalyticsAttributionRecord,
    FunnelStageAnalyticsAttributionSet,
)

from .funnel_quality import (
    FunnelDecisionQualityDimension,
    FunnelDecisionQualityReport,
)
from .models import DecisionQualityResearchBundle, ScannerResearchRecord
from .scanner_filtering import (
    ScannerFilteringDimension,
    ScannerFilteringQualityReport,
)

DECISION_QUALITY_EVIDENCE_INDEX_SCHEMA_VERSION = (
    "money-heist.decision-quality-evidence-index.v1"
)
DECISION_QUALITY_EVIDENCE_REF_SCHEMA_VERSION = (
    "money-heist.decision-quality-evidence-ref.v1"
)
DECISION_QUALITY_EVIDENCE_MEMBERSHIP_SCHEMA_VERSION = (
    "money-heist.decision-quality-evidence-membership.v1"
)
DECISION_QUALITY_EVIDENCE_POLICY_VERSION = "decision-quality-causal-evidence-index-v1"

_STAGE_ORDER: Final = {stage: index for index, stage in enumerate(FunnelStage)}
_SCANNER_DIMENSION_ORDER: Final = {
    dimension: index for index, dimension in enumerate(ScannerFilteringDimension)
}
_FUNNEL_DIMENSION_ORDER: Final = {
    dimension: index for index, dimension in enumerate(FunnelDecisionQualityDimension)
}


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DecisionQualityEvidenceError(ValueError):
    """Fail-closed Evidence Index contract error."""


class ResearchReportType(StrEnum):
    SCANNER_FILTERING = "SCANNER_FILTERING"
    FUNNEL_DECISION_QUALITY = "FUNNEL_DECISION_QUALITY"


class ResearchEvidenceSubjectType(StrEnum):
    SCANNER_OBSERVATION = "SCANNER_OBSERVATION"
    FUNNEL_STAGE = "FUNNEL_STAGE"


class ResearchEvidenceSelector(FrozenModel):
    report_type: ResearchReportType
    dimension: str = Field(min_length=1)
    key: str = Field(min_length=1)
    stage: FunnelStage | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> ResearchEvidenceSelector:
        if self.report_type is ResearchReportType.SCANNER_FILTERING:
            if self.stage is not None:
                raise ValueError("Scanner selector cannot carry a funnel stage")
            ScannerFilteringDimension(self.dimension)
        else:
            if self.stage is None:
                raise ValueError("Funnel selector requires a stage")
            FunnelDecisionQualityDimension(self.dimension)
        return self


class ResearchEvidenceRef(FrozenModel):
    schema_version: str = DECISION_QUALITY_EVIDENCE_REF_SCHEMA_VERSION
    ref_id: str = Field(min_length=1)
    subject_type: ResearchEvidenceSubjectType
    source_record_id: str = Field(min_length=1)
    source_record_fingerprint: str = Field(min_length=64, max_length=64)
    opportunity_id: str | None = None
    scan_id: str | None = None
    stage_record_id: str | None = None
    stage: FunnelStage | None = None
    observed_at: datetime
    navigation_at: datetime
    object_type: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    details: dict[str, str] = Field(default_factory=dict)


class ResearchEvidenceMembership(FrozenModel):
    schema_version: str = DECISION_QUALITY_EVIDENCE_MEMBERSHIP_SCHEMA_VERSION
    selector: ResearchEvidenceSelector
    source_cohort_fingerprint: str = Field(min_length=64, max_length=64)
    ref_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_unique_refs(self) -> ResearchEvidenceMembership:
        if len(set(self.ref_ids)) != len(self.ref_ids):
            raise ValueError("Evidence membership cannot duplicate refs")
        return self


class DecisionQualityEvidenceIndex(FrozenModel):
    schema_version: str = DECISION_QUALITY_EVIDENCE_INDEX_SCHEMA_VERSION
    policy_version: str = DECISION_QUALITY_EVIDENCE_POLICY_VERSION
    index_id: str = Field(min_length=1)
    research_run_id: str = Field(min_length=1)
    source_backtest_run_id: str = Field(min_length=1)
    analytics_run_id: str = Field(min_length=1)
    period_role: str = Field(min_length=1)
    source_bundle_fingerprint: str = Field(min_length=64, max_length=64)
    source_scanner_report_fingerprint: str = Field(min_length=64, max_length=64)
    source_funnel_report_fingerprint: str = Field(min_length=64, max_length=64)
    source_funnel_stage_set_fingerprint: str = Field(min_length=64, max_length=64)
    refs: tuple[ResearchEvidenceRef, ...]
    memberships: tuple[ResearchEvidenceMembership, ...]
    index_fingerprint: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_contract(self) -> DecisionQualityEvidenceIndex:
        if self.period_role not in {"DESIGN", "VALIDATION", "OOS"}:
            raise ValueError("period_role must be DESIGN, VALIDATION or OOS")
        ref_ids = tuple(item.ref_id for item in self.refs)
        if len(set(ref_ids)) != len(ref_ids):
            raise ValueError("Evidence Index cannot duplicate refs")
        selectors = tuple(_selector_identity(item.selector) for item in self.memberships)
        if len(set(selectors)) != len(selectors):
            raise ValueError("Evidence Index cannot duplicate selectors")
        known = set(ref_ids)
        if any(ref_id not in known for item in self.memberships for ref_id in item.ref_ids):
            raise ValueError("Evidence membership references unknown refs")
        if self.refs != tuple(sorted(self.refs, key=_ref_sort_key)):
            raise ValueError("Evidence refs must be deterministically sorted")
        if self.memberships != tuple(sorted(self.memberships, key=_membership_sort_key)):
            raise ValueError("Evidence memberships must be deterministically sorted")
        return self

    def to_json(self) -> str:
        return canonical_json(self.model_dump(mode="python"))


def decision_quality_research_export_name(role: str) -> str:
    return f"decision-quality-research-{str(role).lower()}.json"


def scanner_filtering_quality_export_name(role: str) -> str:
    return f"scanner-filtering-quality-{str(role).lower()}.json"


def funnel_decision_quality_export_name(role: str) -> str:
    return f"funnel-decision-quality-{str(role).lower()}.json"


def decision_quality_evidence_export_name(role: str) -> str:
    return f"decision-quality-evidence-{str(role).lower()}.json"


def _selector_identity(selector: ResearchEvidenceSelector) -> tuple[str, str, str, str]:
    return (
        selector.report_type.value,
        "" if selector.stage is None else selector.stage.value,
        selector.dimension,
        selector.key,
    )


def _selector_sort_key(selector: ResearchEvidenceSelector) -> tuple[int, int, int, str]:
    if selector.report_type is ResearchReportType.SCANNER_FILTERING:
        return (
            0,
            -1,
            _SCANNER_DIMENSION_ORDER[ScannerFilteringDimension(selector.dimension)],
            selector.key,
        )
    assert selector.stage is not None
    return (
        1,
        _STAGE_ORDER[selector.stage],
        _FUNNEL_DIMENSION_ORDER[FunnelDecisionQualityDimension(selector.dimension)],
        selector.key,
    )


def _membership_sort_key(
    membership: ResearchEvidenceMembership,
) -> tuple[int, int, int, str]:
    return _selector_sort_key(membership.selector)


def _ref_sort_key(ref: ResearchEvidenceRef) -> tuple[datetime, str]:
    return (ref.navigation_at, ref.ref_id)


def _scanner_values(
    record: ScannerResearchRecord,
) -> dict[ScannerFilteringDimension, tuple[str, ...]]:
    scanner = record.causal.scanner
    output: dict[ScannerFilteringDimension, tuple[str, ...]] = {
        ScannerFilteringDimension.CLASSIFICATION: (scanner.classification,),
        ScannerFilteringDimension.SCORE: (str(scanner.score),),
        ScannerFilteringDimension.SCORE_MARGIN: (str(scanner.score_margin),),
        ScannerFilteringDimension.TRIGGER: tuple(scanner.triggers),
    }
    output[ScannerFilteringDimension.MARKET_REGIME] = (
        () if scanner.market_regime is None else (scanner.market_regime,)
    )
    return output


def _scanner_ref(record: ScannerResearchRecord) -> ResearchEvidenceRef:
    scanner = record.causal.scanner
    details = {
        "classification": scanner.classification,
        "score": str(scanner.score),
        "score_margin": str(scanner.score_margin),
    }
    if scanner.market_regime is not None:
        details["market_regime"] = scanner.market_regime
    if scanner.triggers:
        details["triggers"] = ",".join(scanner.triggers)
    return ResearchEvidenceRef(
        ref_id=stable_uuid(
            "decision-quality-scanner-evidence-ref",
            {
                "research_run_id": record.research_run_id,
                "record_id": record.record_id,
                "causal_fingerprint": record.causal.causal_fingerprint,
            },
        ),
        subject_type=ResearchEvidenceSubjectType.SCANNER_OBSERVATION,
        source_record_id=record.record_id,
        source_record_fingerprint=record.causal.causal_fingerprint,
        opportunity_id=scanner.candidate_opportunity_id,
        scan_id=record.scan_id,
        observed_at=record.causal.observed_at,
        navigation_at=record.causal.observed_at,
        object_type="ScannerEvaluation",
        object_id=scanner.scanner_evaluation_id,
        label=f"{scanner.classification} · score {scanner.score}",
        details=details,
    )


def _funnel_object_type(stage: FunnelStage) -> str:
    mapping = {
        FunnelStage.COMPUTE_GATE: "ComputeGate",
        FunnelStage.PROFESSOR_PLAN: "ProfessorPlan",
        FunnelStage.SPECIALIST: "SpecialistAnalysis",
        FunnelStage.PALERMO: "PalermoReview",
        FunnelStage.PROFESSOR_FINAL: "ProfessorFinal",
        FunnelStage.TRADE_PROPOSAL: "TradeProposal",
        FunnelStage.RISK: "RiskDecision",
        FunnelStage.PAPER: "PaperExecution",
    }
    return mapping[stage]


def _funnel_ref(
    research_run_id: str,
    record: FunnelStageAnalyticsAttributionRecord,
) -> ResearchEvidenceRef:
    navigation_at = record.operational_at or record.market_as_of
    result = record.stage_result or record.stage_status or (
        "REACHED" if record.reached else "NOT_REACHED"
    )
    details = {
        "stage": record.stage.value,
        "reached": "true" if record.reached else "false",
        "result": result,
    }
    if record.agent_id is not None:
        details["agent_id"] = record.agent_id
    if record.reason_codes:
        details["reason_codes"] = ",".join(record.reason_codes)
    return ResearchEvidenceRef(
        ref_id=stable_uuid(
            "decision-quality-funnel-evidence-ref",
            {
                "research_run_id": research_run_id,
                "record_id": record.record_id,
                "record_fingerprint": record.record_fingerprint,
            },
        ),
        subject_type=ResearchEvidenceSubjectType.FUNNEL_STAGE,
        source_record_id=record.record_id,
        source_record_fingerprint=record.record_fingerprint,
        opportunity_id=record.opportunity_id,
        stage_record_id=record.record_id,
        stage=record.stage,
        observed_at=record.market_as_of,
        navigation_at=navigation_at,
        object_type=_funnel_object_type(record.stage),
        object_id=record.record_id,
        label=f"{record.stage.value} · {result}",
        details=details,
    )


def _validate_sources(
    *,
    bundle: DecisionQualityResearchBundle,
    scanner_report: ScannerFilteringQualityReport,
    funnel_report: FunnelDecisionQualityReport,
    funnel_stage_attribution: FunnelStageAnalyticsAttributionSet,
) -> None:
    source = bundle.research_run.source
    shared = (
        scanner_report.research_run_id,
        funnel_report.research_run_id,
    )
    if any(value != bundle.research_run.research_run_id for value in shared):
        raise DecisionQualityEvidenceError("report research_run_id mismatch")
    if scanner_report.source_bundle_fingerprint != bundle.bundle_fingerprint:
        raise DecisionQualityEvidenceError("Scanner report bundle fingerprint mismatch")
    if funnel_report.source_bundle_fingerprint != bundle.bundle_fingerprint:
        raise DecisionQualityEvidenceError("Funnel report bundle fingerprint mismatch")
    if funnel_report.source_funnel_stage_set_fingerprint != funnel_stage_attribution.set_fingerprint:
        raise DecisionQualityEvidenceError("Funnel report stage-set fingerprint mismatch")
    if funnel_stage_attribution.source_backtest_run_id != source.source_backtest_run_id:
        raise DecisionQualityEvidenceError("Funnel stage-set BacktestRun mismatch")
    if funnel_stage_attribution.analytics_run_id != source.analytics_run_id:
        raise DecisionQualityEvidenceError("Funnel stage-set AnalyticsRun mismatch")
    for report in (scanner_report, funnel_report):
        if report.source_backtest_run_id != source.source_backtest_run_id:
            raise DecisionQualityEvidenceError("report BacktestRun mismatch")
        if report.analytics_run_id != source.analytics_run_id:
            raise DecisionQualityEvidenceError("report AnalyticsRun mismatch")
        if report.period_role != source.period_role:
            raise DecisionQualityEvidenceError("report period_role mismatch")


def build_decision_quality_evidence_index(
    *,
    bundle: DecisionQualityResearchBundle,
    scanner_report: ScannerFilteringQualityReport,
    funnel_report: FunnelDecisionQualityReport,
    funnel_stage_attribution: FunnelStageAnalyticsAttributionSet,
) -> DecisionQualityEvidenceIndex:
    """Build refs-only cohort membership from causal source facts.

    This function deliberately never reads Candidate/Scanner posthoc outcomes. Membership
    is reconstructed from causal Scanner facts or from the exact funnel stage record ids
    already emitted by 24D.3.
    """

    _validate_sources(
        bundle=bundle,
        scanner_report=scanner_report,
        funnel_report=funnel_report,
        funnel_stage_attribution=funnel_stage_attribution,
    )
    source = bundle.research_run.source

    refs: dict[str, ResearchEvidenceRef] = {}
    scanner_ref_by_record: dict[str, str] = {}
    for record in bundle.scanner_records:
        ref = _scanner_ref(record)
        refs[ref.ref_id] = ref
        scanner_ref_by_record[record.record_id] = ref.ref_id

    funnel_ref_by_stage_record: dict[str, str] = {}
    for record in funnel_stage_attribution.records:
        ref = _funnel_ref(bundle.research_run.research_run_id, record)
        refs[ref.ref_id] = ref
        funnel_ref_by_stage_record[record.record_id] = ref.ref_id

    memberships: list[ResearchEvidenceMembership] = []

    for cohort in scanner_report.cohorts:
        dimension = ScannerFilteringDimension(cohort.dimension)
        matching = []
        for record in bundle.scanner_records:
            if cohort.key in _scanner_values(record)[dimension]:
                matching.append(scanner_ref_by_record[record.record_id])
        ordered_refs = tuple(sorted(matching, key=lambda ref_id: _ref_sort_key(refs[ref_id])))
        if len(ordered_refs) != cohort.scanner_count:
            raise DecisionQualityEvidenceError(
                f"Scanner cohort membership count mismatch for {dimension.value}/{cohort.key}"
            )
        memberships.append(
            ResearchEvidenceMembership(
                selector=ResearchEvidenceSelector(
                    report_type=ResearchReportType.SCANNER_FILTERING,
                    dimension=dimension.value,
                    key=cohort.key,
                ),
                source_cohort_fingerprint=cohort.cohort_fingerprint,
                ref_ids=ordered_refs,
            )
        )

    for cohort in funnel_report.cohorts:
        missing = [record_id for record_id in cohort.member_refs if record_id not in funnel_ref_by_stage_record]
        if missing:
            raise DecisionQualityEvidenceError(
                f"Funnel cohort references unknown stage records: {missing[:3]}"
            )
        ordered_refs = tuple(
            sorted(
                (funnel_ref_by_stage_record[record_id] for record_id in cohort.member_refs),
                key=lambda ref_id: _ref_sort_key(refs[ref_id]),
            )
        )
        if len(ordered_refs) != cohort.observation_count:
            raise DecisionQualityEvidenceError(
                f"Funnel cohort membership count mismatch for {cohort.stage.value}/{cohort.dimension.value}/{cohort.key}"
            )
        memberships.append(
            ResearchEvidenceMembership(
                selector=ResearchEvidenceSelector(
                    report_type=ResearchReportType.FUNNEL_DECISION_QUALITY,
                    stage=cohort.stage,
                    dimension=cohort.dimension.value,
                    key=cohort.key,
                ),
                source_cohort_fingerprint=cohort.cohort_fingerprint,
                ref_ids=ordered_refs,
            )
        )

    ordered_refs = tuple(sorted(refs.values(), key=_ref_sort_key))
    ordered_memberships = tuple(sorted(memberships, key=_membership_sort_key))
    identity = {
        "schema": DECISION_QUALITY_EVIDENCE_INDEX_SCHEMA_VERSION,
        "policy": DECISION_QUALITY_EVIDENCE_POLICY_VERSION,
        "research_run_id": bundle.research_run.research_run_id,
        "period_role": source.period_role,
        "source_bundle_fingerprint": bundle.bundle_fingerprint,
        "source_scanner_report_fingerprint": scanner_report.report_fingerprint,
        "source_funnel_report_fingerprint": funnel_report.report_fingerprint,
        "source_funnel_stage_set_fingerprint": funnel_stage_attribution.set_fingerprint,
    }
    index_id = stable_uuid("decision-quality-evidence-index", identity)
    fingerprint = stable_digest(
        {
            **identity,
            "index_id": index_id,
            "refs": tuple(item.model_dump(mode="python") for item in ordered_refs),
            "memberships": tuple(
                item.model_dump(mode="python") for item in ordered_memberships
            ),
        }
    )
    return DecisionQualityEvidenceIndex(
        index_id=index_id,
        research_run_id=bundle.research_run.research_run_id,
        source_backtest_run_id=source.source_backtest_run_id,
        analytics_run_id=source.analytics_run_id,
        period_role=source.period_role,
        source_bundle_fingerprint=bundle.bundle_fingerprint,
        source_scanner_report_fingerprint=scanner_report.report_fingerprint,
        source_funnel_report_fingerprint=funnel_report.report_fingerprint,
        source_funnel_stage_set_fingerprint=funnel_stage_attribution.set_fingerprint,
        refs=ordered_refs,
        memberships=ordered_memberships,
        index_fingerprint=fingerprint,
    )


__all__ = [
    "DECISION_QUALITY_EVIDENCE_INDEX_SCHEMA_VERSION",
    "DECISION_QUALITY_EVIDENCE_POLICY_VERSION",
    "DecisionQualityEvidenceError",
    "DecisionQualityEvidenceIndex",
    "ResearchEvidenceMembership",
    "ResearchEvidenceRef",
    "ResearchEvidenceSelector",
    "ResearchEvidenceSubjectType",
    "ResearchReportType",
    "build_decision_quality_evidence_index",
    "decision_quality_evidence_export_name",
    "decision_quality_research_export_name",
    "funnel_decision_quality_export_name",
    "scanner_filtering_quality_export_name",
]
