from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.dashboard.models import (
    DashboardComparison,
    DashboardDecision,
    DashboardEvent,
    DashboardOpportunity,
    DashboardSnapshot,
    DashboardSystem,
)
from app.dashboard.store import DashboardStore, get_dashboard_store


router = APIRouter(tags=["dashboard"])
_STATIC_DIR = Path(__file__).resolve().parents[2] / "dashboard" / "static"


@lru_cache(maxsize=3)
def _asset(name: str) -> str:
    return (_STATIC_DIR / name).read_text(encoding="utf-8")


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page() -> HTMLResponse:
    return HTMLResponse(_asset("dashboard.html"))


@router.get(
    "/dashboard/assets/dashboard.css",
    response_class=PlainTextResponse,
    include_in_schema=False,
)
def dashboard_css() -> PlainTextResponse:
    return PlainTextResponse(_asset("dashboard.css"), media_type="text/css")


@router.get(
    "/dashboard/assets/dashboard.js",
    response_class=PlainTextResponse,
    include_in_schema=False,
)
def dashboard_js() -> PlainTextResponse:
    return PlainTextResponse(_asset("dashboard.js"), media_type="application/javascript")


@router.get("/api/dashboard/overview", response_model=DashboardSnapshot)
def dashboard_overview(
    store: DashboardStore = Depends(get_dashboard_store),
) -> DashboardSnapshot:
    return store.get()


@router.get("/api/dashboard/systems", response_model=tuple[DashboardSystem, ...])
def dashboard_systems(
    store: DashboardStore = Depends(get_dashboard_store),
) -> tuple[DashboardSystem, ...]:
    return store.get().systems


@router.get("/api/dashboard/systems/{system_id}", response_model=DashboardSystem)
def dashboard_system(
    system_id: str,
    store: DashboardStore = Depends(get_dashboard_store),
) -> DashboardSystem:
    system = store.get().by_system_id().get(system_id)
    if system is None:
        raise HTTPException(status_code=404, detail="Unknown SHADOW system_id")
    return system


@router.get("/api/dashboard/opportunities", response_model=tuple[DashboardOpportunity, ...])
def dashboard_opportunities(
    store: DashboardStore = Depends(get_dashboard_store),
) -> tuple[DashboardOpportunity, ...]:
    return store.get().opportunities


@router.get("/api/dashboard/decisions", response_model=tuple[DashboardDecision, ...])
def dashboard_decisions(
    store: DashboardStore = Depends(get_dashboard_store),
) -> tuple[DashboardDecision, ...]:
    return store.get().decisions


@router.get("/api/dashboard/comparison", response_model=DashboardComparison)
def dashboard_comparison(
    store: DashboardStore = Depends(get_dashboard_store),
) -> DashboardComparison:
    return store.get().comparison


@router.get("/api/dashboard/events", response_model=tuple[DashboardEvent, ...])
def dashboard_events(
    limit: int = Query(default=100, ge=1, le=500),
    store: DashboardStore = Depends(get_dashboard_store),
) -> tuple[DashboardEvent, ...]:
    events = store.get().events
    return events[-limit:]


@router.head("/dashboard", include_in_schema=False)
def dashboard_head(_: Request) -> HTMLResponse:
    return HTMLResponse(content="")
