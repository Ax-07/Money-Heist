from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from app.dashboard.backtest import (
    BacktestCapabilities,
    BacktestDashboardError,
    BacktestDashboardService,
    CampaignRequest,
    CampaignSummary,
    DatasetInput,
    DatasetPreview,
    get_backtest_dashboard_service,
)

BacktestService = Annotated[
    BacktestDashboardService,
    Depends(get_backtest_dashboard_service),
]


router = APIRouter(tags=["backtest-dashboard"])
_STATIC_DIR = Path(__file__).resolve().parents[2] / "dashboard" / "static"


class CacheImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    payload: str = Field(min_length=1)


@lru_cache(maxsize=3)
def _asset(name: str) -> str:
    return (_STATIC_DIR / name).read_text(encoding="utf-8")


@router.get("/dashboard/backtest", response_class=HTMLResponse, include_in_schema=False)
def backtest_page() -> HTMLResponse:
    return HTMLResponse(_asset("backtest.html"))


@router.get(
    "/dashboard/assets/backtest.css",
    response_class=PlainTextResponse,
    include_in_schema=False,
)
def backtest_css() -> PlainTextResponse:
    return PlainTextResponse(_asset("backtest.css"), media_type="text/css")


@router.get(
    "/dashboard/assets/backtest.js",
    response_class=PlainTextResponse,
    include_in_schema=False,
)
def backtest_js() -> PlainTextResponse:
    return PlainTextResponse(_asset("backtest.js"), media_type="application/javascript")


@router.get("/api/dashboard/backtest/capabilities", response_model=BacktestCapabilities)
def capabilities(
    service: BacktestService,
) -> BacktestCapabilities:
    return service.capabilities()


@router.post("/api/dashboard/backtest/dataset/preview", response_model=DatasetPreview)
def preview_dataset(
    payload: DatasetInput,
    service: BacktestService,
) -> DatasetPreview:
    try:
        return service.preview_dataset(payload)
    except (BacktestDashboardError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/dashboard/backtest/runs", response_model=CampaignSummary)
async def run_campaign(
    payload: CampaignRequest,
    service: BacktestService,
) -> CampaignSummary:
    try:
        return await service.run_campaign(payload)
    except (BacktestDashboardError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/dashboard/backtest/runs", response_model=tuple[CampaignSummary, ...])
def list_campaigns(
    service: BacktestService,
) -> tuple[CampaignSummary, ...]:
    return service.list_campaigns()


@router.get("/api/dashboard/backtest/runs/{campaign_id}", response_model=CampaignSummary)
def get_campaign(
    campaign_id: str,
    service: BacktestService,
) -> CampaignSummary:
    result = service.get_campaign(campaign_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown backtest campaign_id")
    return result


@router.get("/api/dashboard/backtest/runs/{campaign_id}/exports/{name}")
def get_export(
    campaign_id: str,
    name: str,
    service: BacktestService,
) -> Response:
    result = service.get_export(campaign_id, name)
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown backtest export")
    media_type, content = result
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/api/dashboard/backtest/ai-cache")
def export_ai_cache(
    service: BacktestService,
) -> Response:
    return Response(
        content=service.export_cache(),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="backtest-ai-cache.json"'},
    )


@router.post("/api/dashboard/backtest/ai-cache")
def import_ai_cache(
    payload: CacheImportRequest,
    service: BacktestService,
) -> dict[str, int]:
    try:
        return {"cache_entries": service.import_cache(payload.payload)}
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["router"]
