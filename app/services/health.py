from app import __version__
from app.config.settings import Settings
from app.domain.models import HealthResponse, ReadinessResponse
from app.ports.database import DatabaseHealthPort


class HealthService:
    def __init__(self, settings: Settings, database: DatabaseHealthPort) -> None:
        self.settings = settings
        self.database = database

    def liveness(self) -> HealthResponse:
        return HealthResponse(service=self.settings.app_name, version=__version__)

    def readiness(self) -> ReadinessResponse:
        self.database.ping()
        return ReadinessResponse(status="ready", database="ok")
