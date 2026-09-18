from fastapi import APIRouter

from app.api.routes.backtest_dashboard import router as backtest_dashboard_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.frontend_v2 import router as frontend_v2_router
from app.api.routes.frontend_v2_decision_intelligence import (
    router as frontend_v2_decision_intelligence_router,
)
from app.api.routes.frontend_v2_research import router as frontend_v2_research_router
from app.api.routes.health import router as health_router
from app.api.routes.recruitment import router as recruitment_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(dashboard_router)
api_router.include_router(backtest_dashboard_router)
api_router.include_router(recruitment_router)
api_router.include_router(frontend_v2_router)
api_router.include_router(frontend_v2_decision_intelligence_router)
api_router.include_router(frontend_v2_research_router)
