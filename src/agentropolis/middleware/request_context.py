"""Request-context middleware for lightweight tracing in the scaffold runtime."""

from __future__ import annotations

from uuid import uuid4

from agentropolis.control_contract import (
    CONTROL_CONTRACT_VERSION,
    CONTRACT_VERSION_HEADER,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

REQUEST_ID_HEADER = "X-Agentropolis-Request-ID"


def build_client_fingerprint(request: Request) -> str:
    """Return a best-effort client identifier for audit/debug purposes."""
    client = request.client
    if client is None:
        return "unknown"
    return f"{client.host}:{client.port}"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a stable request id and client fingerprint to request state."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER, uuid4().hex)
        request.state.request_id = request_id
        request.state.client_fingerprint = build_client_fingerprint(request)
        request.state.authenticated_actor_kind = None
        request.state.authenticated_actor_key = None
        request.state.concurrency_slot_class = None

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[CONTRACT_VERSION_HEADER] = CONTROL_CONTRACT_VERSION
        return response
