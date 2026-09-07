import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.domain.enums import LogLevel

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)

_RESERVED_LOG_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }

        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _RESERVED_LOG_RECORD_FIELDS:
                continue
            if key in payload:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: LogLevel | str) -> None:
    normalized_level = level.value if isinstance(level, LogLevel) else str(level).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(normalized_level)

    # Uvicorn conserve ses loggers mais propage vers notre formatter JSON.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True


class CorrelationIdMiddleware:
    """ASGI middleware minimal sans dépendance additionnelle."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        incoming = headers.get(b"x-correlation-id", b"").decode("ascii", errors="ignore").strip()
        correlation_id = incoming[:128] if incoming else str(uuid4())
        token = correlation_id_var.set(correlation_id)

        async def send_with_correlation_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-correlation-id", correlation_id.encode("utf-8")))
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation_id)
        finally:
            correlation_id_var.reset(token)
