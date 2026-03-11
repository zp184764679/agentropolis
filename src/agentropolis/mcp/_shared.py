"""Shared helpers for MCP tool modules."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
import inspect
import logging
from time import monotonic

from fastapi import HTTPException

from agentropolis.api.auth import resolve_active_company_for_agent, resolve_agent_from_api_key
from agentropolis.api.preview_guard import (
    allow_internal_preview_family_access,
    allow_internal_preview_family_mutation,
)
from agentropolis.config import settings
from agentropolis.database import async_session
from agentropolis.mcp.metrics import record_mcp_call
from agentropolis.services.structured_logging import emit_structured_log

logger = logging.getLogger(__name__)
_ACTIVE_TOOL_CONTEXT: ContextVar[dict | None] = ContextVar("mcp_active_tool_context", default=None)


def _infer_tool_name() -> str:
    frame = inspect.currentframe()
    current = frame
    try:
        while current is not None:
            filename = str(current.f_code.co_filename or "").replace("\\", "/")
            if "/agentropolis/mcp/tools_" in filename:
                return current.f_code.co_name
            current = current.f_back
        return "unknown_tool"
    finally:
        del frame


@asynccontextmanager
async def _instrumented_tool_call(actor_kind: str):
    existing = _ACTIVE_TOOL_CONTEXT.get()
    if existing is not None:
        yield existing
        return

    tool_name = _infer_tool_name()
    token = _ACTIVE_TOOL_CONTEXT.set(
        {
            "tool_name": tool_name,
            "actor_kind": actor_kind,
        }
    )
    started = monotonic()
    ok = False
    status_code = 200
    error_code = None
    try:
        yield _ACTIVE_TOOL_CONTEXT.get()
        ok = True
    except Exception as exc:
        if isinstance(exc, HTTPException):
            status_code = int(exc.status_code)
            error_code = (exc.headers or {}).get("X-Agentropolis-Error-Code")
        else:
            status_code = 400
        raise
    finally:
        duration_ms = (monotonic() - started) * 1000
        record_mcp_call(
            tool_name=tool_name,
            actor_kind=actor_kind,
            ok=ok,
            status_code=status_code,
            duration_ms=duration_ms,
            error_code=error_code,
        )
        emit_structured_log(
            logger,
            "mcp_tool_call",
            tool_name=tool_name,
            actor_kind=actor_kind,
            ok=ok,
            status_code=status_code,
            duration_ms=round(duration_ms, 3),
            error_code=error_code,
            slow=duration_ms >= float(settings.OBSERVABILITY_SLOW_MCP_MS),
        )
        _ACTIVE_TOOL_CONTEXT.reset(token)


@asynccontextmanager
async def public_tool_context():
    async with _instrumented_tool_call("public"):
        async with async_session() as session:
            yield session


@asynccontextmanager
async def agent_tool_context(
    agent_api_key: str,
    *,
    family: str,
    mutate: bool = False,
    allow_in_degraded_mode: bool = False,
    operation: str | None = None,
    spend_amount: float | int | Callable | None = None,
):
    async with _instrumented_tool_call("agent"):
        async with async_session() as session:
            agent = await resolve_agent_from_api_key(session, agent_api_key)
            if mutate:
                resolved_spend = await _resolve_spend_amount(session, agent, spend_amount)
                await allow_internal_preview_family_mutation(
                    session,
                    agent.id,
                    family,
                    allow_in_degraded_mode=allow_in_degraded_mode,
                    operation=operation,
                    spend_amount=resolved_spend,
                )
            else:
                await allow_internal_preview_family_access(session, agent.id, family)
            yield session, agent


@asynccontextmanager
async def agent_company_tool_context(
    agent_api_key: str,
    *,
    family: str,
    mutate: bool = False,
    allow_in_degraded_mode: bool = False,
    operation: str | None = None,
    spend_amount: float | int | Callable | None = None,
):
    async with _instrumented_tool_call("agent"):
        async with async_session() as session:
            agent = await resolve_agent_from_api_key(session, agent_api_key)
            company = await resolve_active_company_for_agent(session, agent.id)
            if mutate:
                resolved_spend = await _resolve_spend_amount(session, company, spend_amount)
                await allow_internal_preview_family_mutation(
                    session,
                    agent.id,
                    family,
                    allow_in_degraded_mode=allow_in_degraded_mode,
                    operation=operation,
                    spend_amount=resolved_spend,
                )
            else:
                await allow_internal_preview_family_access(session, agent.id, family)
            yield session, agent, company


async def _resolve_spend_amount(session, actor, spend_amount) -> float | int:
    if spend_amount is None:
        return 0
    if callable(spend_amount):
        value = spend_amount(session, actor)
        if isinstance(value, Awaitable):
            return await value
        return value
    return spend_amount


def handle_tool_error(exc: Exception) -> dict:
    if isinstance(exc, HTTPException):
        return {
            "ok": False,
            "status_code": exc.status_code,
            "detail": exc.detail,
            "error_code": (exc.headers or {}).get("X-Agentropolis-Error-Code"),
        }
    return {
        "ok": False,
        "status_code": 400,
        "detail": str(exc),
        "error_code": None,
    }


def parity_http_error(
    status_code: int,
    detail: str,
    *,
    error_code: str | None = None,
) -> HTTPException:
    headers = (
        {"X-Agentropolis-Error-Code": error_code}
        if error_code is not None
        else None
    )
    return HTTPException(status_code=status_code, detail=detail, headers=headers)
