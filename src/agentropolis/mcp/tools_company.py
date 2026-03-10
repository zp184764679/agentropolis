"""Core MCP tools for company operations."""

from __future__ import annotations

from agentropolis.mcp._shared import company_tool_context, handle_tool_error
from agentropolis.mcp.server import mcp
from agentropolis.services.company_svc import get_company_status, get_company_workers


@mcp.tool()
async def get_company_status_tool(company_api_key: str) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            return {"ok": True, "company": await get_company_status(session, company.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_company_workers_tool(company_api_key: str) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            return {"ok": True, "workers": await get_company_workers(session, company.id)}
    except Exception as exc:
        return handle_tool_error(exc)
