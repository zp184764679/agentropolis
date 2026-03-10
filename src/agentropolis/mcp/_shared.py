"""Shared helpers for MCP tool modules."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import HTTPException

from agentropolis.api.auth import resolve_agent_from_api_key, resolve_company_from_api_key
from agentropolis.api.preview_guard import (
    allow_internal_company_family_mutation,
    allow_internal_preview_family_access,
    allow_internal_preview_family_mutation,
)
from agentropolis.database import async_session


@asynccontextmanager
async def public_tool_context():
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
async def company_tool_context(
    company_api_key: str,
    *,
    family: str | None = None,
    mutate: bool = False,
    allow_in_degraded_mode: bool = False,
    operation: str | None = None,
    spend_amount: float | int | Callable | None = None,
):
    async with async_session() as session:
        company = await resolve_company_from_api_key(session, company_api_key)
        if mutate:
            if family is None:
                raise ValueError("family is required for mutating company tools")
            resolved_spend = await _resolve_spend_amount(session, company, spend_amount)
            await allow_internal_company_family_mutation(
                session,
                company,
                family,
                operation=operation,
                allow_in_degraded_mode=allow_in_degraded_mode,
                spend_amount=resolved_spend,
            )
        yield session, company


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
