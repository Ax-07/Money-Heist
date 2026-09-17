from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.routes.frontend_v2 import FrontendV2Store
from app.services.frontend_v2.analytics_overlays import (
    FrontendAnalyticsOverlayProjectionService,
    FrontendAnalyticsOverlaysProjection,
)
from app.services.frontend_v2.decision_intelligence import (
    CampaignNotFoundError,
    FrontendAnalyticsProjection,
    FrontendDecisionIntelligenceDetailProjection,
    FrontendDecisionIntelligenceProjectionService,
    FrontendScannerAnalyticsProjection,
    OpportunityNotFoundError,
)

router = APIRouter(prefix="/api/frontend/v2", tags=["frontend-v2", "decision-intelligence"])

PeriodRole = Literal["DESIGN", "VALIDATION", "OOS"]
PeriodRoleQuery = Annotated[PeriodRole, Query()]


def _frontend_store(request: Request) -> FrontendV2Store:
    store = getattr(request.app.state, "frontend_v2_store", None)
    if store is None:
        store = FrontendV2Store()
        request.app.state.frontend_v2_store = store
    return store


def _projection_service(
    store: Annotated[FrontendV2Store, Depends(_frontend_store)],
) -> FrontendDecisionIntelligenceProjectionService:
    return FrontendDecisionIntelligenceProjectionService(store)


def _overlay_service(
    store: Annotated[FrontendV2Store, Depends(_frontend_store)],
) -> FrontendAnalyticsOverlayProjectionService:
    return FrontendAnalyticsOverlayProjectionService(store)


ProjectionService = Annotated[
    FrontendDecisionIntelligenceProjectionService,
    Depends(_projection_service),
]
OverlayService = Annotated[
    FrontendAnalyticsOverlayProjectionService,
    Depends(_overlay_service),
]


def _not_found(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc) or "resource not found")


def _projection_error(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=500,
        detail=f"persisted Decision Intelligence projection is invalid: {exc}",
    )


@router.get(
    "/backtests/runs/{campaign_id}/analytics",
    response_model=FrontendAnalyticsProjection,
)
def analytics_projection(
    campaign_id: str,
    service: ProjectionService,
    role: PeriodRoleQuery = "OOS",
) -> FrontendAnalyticsProjection:
    try:
        return service.analytics(campaign_id, role)
    except CampaignNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _projection_error(exc) from exc


@router.get(
    "/backtests/runs/{campaign_id}/analytics/scanner",
    response_model=FrontendScannerAnalyticsProjection,
)
def scanner_analytics_projection(
    campaign_id: str,
    service: ProjectionService,
    role: PeriodRoleQuery = "OOS",
) -> FrontendScannerAnalyticsProjection:
    try:
        return service.scanner(campaign_id, role)
    except CampaignNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _projection_error(exc) from exc


@router.get(
    "/backtests/runs/{campaign_id}/analytics/overlays",
    response_model=FrontendAnalyticsOverlaysProjection,
)
def analytics_overlays_projection(
    campaign_id: str,
    service: OverlayService,
    role: PeriodRoleQuery = "OOS",
) -> FrontendAnalyticsOverlaysProjection:
    try:
        return service.overlays(campaign_id, role)
    except CampaignNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _projection_error(exc) from exc


@router.get(
    "/backtests/runs/{campaign_id}/opportunities/{opportunity_id}/decision-intelligence",
    response_model=FrontendDecisionIntelligenceDetailProjection,
)
def decision_intelligence_detail(
    campaign_id: str,
    opportunity_id: str,
    service: ProjectionService,
    role: PeriodRoleQuery = "OOS",
) -> FrontendDecisionIntelligenceDetailProjection:
    try:
        return service.decision_detail(campaign_id, role, opportunity_id)
    except (CampaignNotFoundError, OpportunityNotFoundError) as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _projection_error(exc) from exc


__all__ = ["router"]
