from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.routes.frontend_v2 import FrontendV2Store
from app.evaluation.decision_quality.evidence import ResearchReportType
from app.services.frontend_v2.decision_intelligence import CampaignNotFoundError
from app.services.frontend_v2.research import (
    FrontendDecisionQualityResearchProjection,
    FrontendDecisionQualityResearchService,
    FrontendResearchEvidencePage,
    ResearchEvidenceNotFoundError,
)

router = APIRouter(prefix="/api/frontend/v2", tags=["frontend-v2", "research"])

PeriodRole = Literal["DESIGN", "VALIDATION", "OOS"]
PeriodRoleQuery = Annotated[PeriodRole, Query()]


def _frontend_store(request: Request) -> FrontendV2Store:
    store = getattr(request.app.state, "frontend_v2_store", None)
    if store is None:
        store = FrontendV2Store()
        request.app.state.frontend_v2_store = store
    return store


def _research_service(
    store: Annotated[FrontendV2Store, Depends(_frontend_store)],
) -> FrontendDecisionQualityResearchService:
    return FrontendDecisionQualityResearchService(store)


ResearchService = Annotated[
    FrontendDecisionQualityResearchService,
    Depends(_research_service),
]


def _not_found(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc) or "resource not found")


def _projection_error(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=500,
        detail=f"persisted Decision Quality research projection is invalid: {exc}",
    )


@router.get(
    "/backtests/runs/{campaign_id}/research/decision-quality",
    response_model=FrontendDecisionQualityResearchProjection,
)
def decision_quality_research(
    campaign_id: str,
    service: ResearchService,
    role: PeriodRoleQuery = "OOS",
) -> FrontendDecisionQualityResearchProjection:
    try:
        return service.report(campaign_id, role)
    except CampaignNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _projection_error(exc) from exc


@router.get(
    "/backtests/runs/{campaign_id}/research/evidence",
    response_model=FrontendResearchEvidencePage,
)
def research_evidence(
    campaign_id: str,
    service: ResearchService,
    report_type: Annotated[ResearchReportType, Query()],
    dimension: Annotated[str, Query(min_length=1)],
    key: Annotated[str, Query(min_length=1)],
    role: PeriodRoleQuery = "OOS",
    stage: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> FrontendResearchEvidencePage:
    try:
        return service.evidence(
            campaign_id,
            role,
            report_type=report_type,
            dimension=dimension,
            key=key,
            stage=stage,
            page=page,
            page_size=page_size,
        )
    except (CampaignNotFoundError, ResearchEvidenceNotFoundError) as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _projection_error(exc) from exc


__all__ = ["router"]
