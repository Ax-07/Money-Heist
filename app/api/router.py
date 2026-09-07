from fastapi import APIRouter

from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(dashboard_router)
