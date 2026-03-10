"""Core MCP tools for inventory reads."""

from __future__ import annotations

from agentropolis.mcp._shared import company_tool_context, handle_tool_error
from agentropolis.mcp.server import mcp
from agentropolis.services.inventory_svc import get_inventory, get_resource_quantity


@mcp.tool()
async def get_inventory_tool(company_api_key: str) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            return {"ok": True, "items": await get_inventory(session, company.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_inventory_item_tool(company_api_key: str, resource: str) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            return {"ok": True, "item": await get_resource_quantity(session, company.id, resource)}
    except Exception as exc:
        return handle_tool_error(exc)
