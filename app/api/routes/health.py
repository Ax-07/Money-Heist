import logging

from fastapi import APIRouter, HTTPException, Request, status

from app.domain.models import HealthResponse, ReadinessResponse
from app.services.health import HealthService

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


def _health_service(request: Request) -> HealthService:
    return HealthService(settings=request.app.state.settings, database=request.app.state.database)


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return _health_service(request).liveness()


@router.get("/ready", response_model=ReadinessResponse)
def ready(request: Request) -> ReadinessResponse:
    try:
        return _health_service(request).readiness()
    except Exception as exc:  # readiness doit convertir l'indisponibilité en 503 explicite.
        logger.error(
            "Database readiness check failed",
            extra={"event": "database_not_ready"},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_not_ready",
        ) from exc
