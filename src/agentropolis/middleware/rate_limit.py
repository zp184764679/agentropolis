"""Authenticated request concurrency and rate-limit middleware."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from agentropolis.middleware.request_context import REQUEST_ID_HEADER
from agentropolis.services.concurrency import (
    ERROR_CODE_HEADER,
    acquire_request_slot,
    classify_authenticated_actor,
    enforce_authenticated_request_rate_limit,
)


def _concurrency_error_response(request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    headers = dict(exc.headers or {})
    if request_id and REQUEST_ID_HEADER not in headers:
        headers[REQUEST_ID_HEADER] = request_id
    error_code = headers.get(ERROR_CODE_HEADER)
    payload = {
        "detail": exc.detail,
        **({"request_id": request_id} if request_id else {}),
        **({"error_code": error_code} if error_code else {}),
    }
    return JSONResponse(
        status_code=exc.status_code,
        content=payload,
        headers=headers,
    )


class RequestConcurrencyMiddleware(BaseHTTPMiddleware):
    """Protect all authenticated requests with rate limiting and global slots."""

    async def dispatch(self, request, call_next):
        classified = classify_authenticated_actor(
            path=request.url.path,
            api_key=request.headers.get("X-API-Key"),
            admin_token=request.headers.get("X-Control-Plane-Token"),
        )
        if classified is None:
            return await call_next(request)

        actor_kind, actor_key = classified
        request.state.authenticated_actor_kind = actor_kind
        request.state.authenticated_actor_key = actor_key

        try:
            enforce_authenticated_request_rate_limit(actor_kind, actor_key)
            async with acquire_request_slot():
                request.state.concurrency_slot_class = "request"
                return await call_next(request)
        except HTTPException as exc:
            return _concurrency_error_response(request, exc)
        finally:
            if getattr(request.state, "concurrency_slot_class", None) == "request":
                request.state.concurrency_slot_class = None
