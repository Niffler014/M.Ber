"""M.Ber Web Interface Layer (Phase 8)."""

from app.interfaces.web.gateway import create_web_app, app
from app.interfaces.web.models import (
    ChatRequest,
    ChatResponse,
    TraceEvent,
    HealthResponse,
    ErrorDetail,
    ErrorResponse,
    to_public_trace_event,
)

__all__ = [
    "create_web_app",
    "app",
    "ChatRequest",
    "ChatResponse",
    "TraceEvent",
    "HealthResponse",
    "ErrorDetail",
    "ErrorResponse",
    "to_public_trace_event",
]
