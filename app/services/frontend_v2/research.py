from __future__ import annotations

import json
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.evaluation.decision_quality.evidence import (
    DecisionQualityEvidenceIndex,
    ResearchEvidenceRef,
    ResearchEvidenceSelector,
    ResearchReportType,
    decision_quality_evidence_export_name,
    funnel_decision_quality_export_name,
    scanner_filtering_quality_export_name,
)
from app.evaluation.decision_quality.funnel_quality import FunnelDecisionQualityReport
from app.evaluation.decision_quality.scanner_filtering import ScannerFilteringQualityReport
from app.services.frontend_v2.decision_intelligence import CampaignNotFoundError

PeriodRole = Literal["DESIGN", "VALIDATION", "OOS"]

FRONTEND_DECISION_QUALITY_RESEARCH_SCHEMA_VERSION = (
    "money-heist.frontend-decision-quality-research.v1"
)
FRONTEND_RESEARCH_EVIDENCE_PAGE_SCHEMA_VERSION = (
    "money-heist.frontend-research-evidence-page.v1"
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResearchEvidenceNotFoundError(LookupError):
    pass


class ProjectionArtifactStore(Protocol):
    def get(self, campaign_id: str) -> object | None: ...

    def persisted_export(self, campaign_id: str, name: str) -> str | None: ...


class FrontendDecisionQualityResearchProjection(FrozenModel):
    schema_version: str = FRONTEND_DECISION_QUALITY_RESEARCH_SCHEMA_VERSION
    campaign_id: str
    role: PeriodRole
    research_available: bool
    unavailable_reason: str | None = None
    research_run_id: str | None = None
    source_backtest_run_id: str | None = None
    analytics_run_id: str | None = None
    evidence_index_fingerprint: str | None = None
    scanner_filtering: JsonValue | None = None
    funnel_decision_quality: JsonValue | None = None

    @model_validator(mode="after")
    def validate_availability(self) -> FrontendDecisionQualityResearchProjection:
        material = (
            self.research_run_id,
            self.source_backtest_run_id,
            self.analytics_run_id,
            self.evidence_index_fingerprint,
            self.scanner_filtering,
            self.funnel_decision_quality,
        )
        if self.research_available:
            if any(value is None for value in material):
                raise ValueError("available research projection requires complete material")
            if self.unavailable_reason is not None:
                raise ValueError("available research projection cannot carry unavailable_reason")
        elif any(value is not None for value in material):
            raise ValueError("unavailable research projection cannot carry research material")
        return self


class FrontendResearchEvidencePage(FrozenModel):
    schema_version: str = FRONTEND_RESEARCH_EVIDENCE_PAGE_SCHEMA_VERSION
    campaign_id: str
    role: PeriodRole
    selector: ResearchEvidenceSelector
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    page_count: int = Field(ge=0)
    items: tuple[ResearchEvidenceRef, ...] = ()


class FrontendDecisionQualityResearchService:
    """Read-only 24D.4 projection over persisted post-run research sidecars."""

    def __init__(self, store: ProjectionArtifactStore) -> None:
        self._store = store

    def _ensure_campaign(self, campaign_id: str) -> None:
        if self._store.get(campaign_id) is None:
            raise CampaignNotFoundError(f"campaign not found: {campaign_id}")

    def _payload(self, campaign_id: str, name: str) -> str | None:
        self._ensure_campaign(campaign_id)
        return self._store.persisted_export(campaign_id, name)

    def _load_scanner(
        self, campaign_id: str, role: PeriodRole
    ) -> ScannerFilteringQualityReport | None:
        payload = self._payload(
            campaign_id, scanner_filtering_quality_export_name(role)
        )
        return (
            None
            if payload is None
            else ScannerFilteringQualityReport.model_validate_json(payload)
        )

    def _load_funnel(
        self, campaign_id: str, role: PeriodRole
    ) -> FunnelDecisionQualityReport | None:
        payload = self._payload(
            campaign_id, funnel_decision_quality_export_name(role)
        )
        return (
            None
            if payload is None
            else FunnelDecisionQualityReport.model_validate_json(payload)
        )

    def _load_evidence(
        self, campaign_id: str, role: PeriodRole
    ) -> DecisionQualityEvidenceIndex | None:
        payload = self._payload(campaign_id, decision_quality_evidence_export_name(role))
        return (
            None
            if payload is None
            else DecisionQualityEvidenceIndex.model_validate_json(payload)
        )

    def report(
        self,
        campaign_id: str,
        role: PeriodRole,
    ) -> FrontendDecisionQualityResearchProjection:
        scanner = self._load_scanner(campaign_id, role)
        funnel = self._load_funnel(campaign_id, role)
        evidence = self._load_evidence(campaign_id, role)
        if scanner is None or funnel is None or evidence is None:
            return FrontendDecisionQualityResearchProjection(
                campaign_id=campaign_id,
                role=role,
                research_available=False,
                unavailable_reason="PRECOMPUTED_RESEARCH_UNAVAILABLE",
            )

        identities = {
            (
                scanner.research_run_id,
                scanner.source_backtest_run_id,
                scanner.analytics_run_id,
                scanner.period_role,
            ),
            (
                funnel.research_run_id,
                funnel.source_backtest_run_id,
                funnel.analytics_run_id,
                funnel.period_role,
            ),
            (
                evidence.research_run_id,
                evidence.source_backtest_run_id,
                evidence.analytics_run_id,
                evidence.period_role,
            ),
        }
        if len(identities) != 1:
            raise ValueError("persisted research sidecars have inconsistent identities")
        if evidence.source_scanner_report_fingerprint != scanner.report_fingerprint:
            raise ValueError("Evidence Index Scanner fingerprint mismatch")
        if evidence.source_funnel_report_fingerprint != funnel.report_fingerprint:
            raise ValueError("Evidence Index Funnel fingerprint mismatch")

        return FrontendDecisionQualityResearchProjection(
            campaign_id=campaign_id,
            role=role,
            research_available=True,
            research_run_id=scanner.research_run_id,
            source_backtest_run_id=scanner.source_backtest_run_id,
            analytics_run_id=scanner.analytics_run_id,
            evidence_index_fingerprint=evidence.index_fingerprint,
            scanner_filtering=json.loads(scanner.to_json()),
            funnel_decision_quality=json.loads(funnel.to_json()),
        )

    def evidence(
        self,
        campaign_id: str,
        role: PeriodRole,
        *,
        report_type: ResearchReportType,
        dimension: str,
        key: str,
        stage: str | None,
        page: int,
        page_size: int,
    ) -> FrontendResearchEvidencePage:
        evidence = self._load_evidence(campaign_id, role)
        if evidence is None:
            raise ResearchEvidenceNotFoundError(
                f"precomputed research evidence unavailable: {campaign_id}/{role}"
            )
        selector = ResearchEvidenceSelector(
            report_type=report_type,
            dimension=dimension,
            key=key,
            stage=stage,
        )
        membership = next(
            (item for item in evidence.memberships if item.selector == selector),
            None,
        )
        if membership is None:
            raise ResearchEvidenceNotFoundError(
                f"research cohort not found: {report_type.value}/{stage or '-'}/{dimension}/{key}"
            )
        refs = {item.ref_id: item for item in evidence.refs}
        total = len(membership.ref_ids)
        page_count = (total + page_size - 1) // page_size if total else 0
        start = (page - 1) * page_size
        selected_ids = membership.ref_ids[start : start + page_size]
        items = tuple(refs[ref_id] for ref_id in selected_ids)
        return FrontendResearchEvidencePage(
            campaign_id=campaign_id,
            role=role,
            selector=selector,
            page=page,
            page_size=page_size,
            total=total,
            page_count=page_count,
            items=items,
        )


__all__ = [
    "FRONTEND_DECISION_QUALITY_RESEARCH_SCHEMA_VERSION",
    "FRONTEND_RESEARCH_EVIDENCE_PAGE_SCHEMA_VERSION",
    "FrontendDecisionQualityResearchProjection",
    "FrontendDecisionQualityResearchService",
    "FrontendResearchEvidencePage",
    "ResearchEvidenceNotFoundError",
]
