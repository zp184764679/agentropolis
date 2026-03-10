"""Shared helpers for MCP tool modules."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import HTTPException

from agentropolis.api.auth import resolve_agent_from_api_key, resolve_company_from_api_key
from agentropolis.api.preview_guard import (
    allow_internal_preview_family_access,
    allow_internal_preview_family_mutation,
)
from agentropolis.database import async_session


@asynccontextmanager
async def agent_tool_context(
    agent_api_key: str,
    *,
    family: str,
    mutate: bool = False,
):
    async with async_session() as session:
        agent = await resolve_agent_from_api_key(session, agent_api_key)
        if mutate:
            await allow_internal_preview_family_mutation(session, agent.id, family)
        else:
            await allow_internal_preview_family_access(session, agent.id, family)
        yield session, agent


@asynccontextmanager
async def company_tool_context(company_api_key: str):
    async with async_session() as session:
        company = await resolve_company_from_api_key(session, company_api_key)
        yield session, company


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
