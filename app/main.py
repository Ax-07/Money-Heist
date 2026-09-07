import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.router import api_router
from app.config.settings import Settings, get_settings
from app.observability.logging import CorrelationIdMiddleware, configure_logging
from app.storage.database import Database

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    database = Database(resolved_settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "Money Heist API starting",
            extra={
                "event": "application_start",
                "runtime_mode": resolved_settings.runtime_mode.value,
                "app_env": resolved_settings.app_env,
            },
        )
        try:
            database.ping()
        except Exception:
            logger.error(
                "Database unavailable at startup; readiness will remain false",
                extra={"event": "database_unavailable_startup"},
                exc_info=True,
            )
        try:
            yield
        finally:
            database.dispose()
            logger.info("Money Heist API stopped", extra={"event": "application_stop"})

    app = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = database
    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(api_router)
    return app


app = create_app()
