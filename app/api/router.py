from fastapi import APIRouter

from app.api.routes.backtest_dashboard import router as backtest_dashboard_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import router as health_router
from app.api.routes.recruitment import router as recruitment_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(dashboard_router)
api_router.include_router(backtest_dashboard_router)
api_router.include_router(recruitment_router)
