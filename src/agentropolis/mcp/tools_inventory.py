"""Inventory MCP tools for company-owned resources."""

from __future__ import annotations

from sqlalchemy import select

from agentropolis.mcp._shared import (
    agent_company_tool_context,
    handle_tool_error,
    parity_http_error,
    public_tool_context,
)
from agentropolis.mcp.server import mcp
from agentropolis.models import Resource
from agentropolis.services.inventory_svc import (
    get_inventory as get_inventory_svc,
    get_resource_quantity,
)


@mcp.tool()
async def get_inventory(agent_api_key: str) -> dict:
    try:
        async with agent_company_tool_context(
            agent_api_key,
            family="company_inventory",
        ) as (session, _agent, company):
            return {"ok": True, "items": await get_inventory_svc(session, company.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_inventory_item(agent_api_key: str, resource: str) -> dict:
    try:
        async with agent_company_tool_context(
            agent_api_key,
            family="company_inventory",
        ) as (session, _agent, company):
            try:
                payload = await get_resource_quantity(session, company.id, resource)
            except ValueError as exc:
                raise parity_http_error(
                    404,
                    str(exc),
                    error_code="inventory_resource_not_found",
                ) from exc
            return {"ok": True, "item": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_resource_info(resource: str) -> dict:
    try:
        async with public_tool_context() as session:
            result = await session.execute(
                select(Resource).where(Resource.ticker == resource.upper())
            )
            item = result.scalar_one_or_none()
            if item is None:
                raise parity_http_error(
                    404,
                    f"Unknown resource ticker: {resource}",
                    error_code="inventory_resource_not_found",
                )
            return {
                "ok": True,
                "resource": {
                    "ticker": item.ticker,
                    "name": item.name,
                    "category": item.category.value,
                    "base_price": int(item.base_price),
                    "description": item.description or "",
                },
            }
    except Exception as exc:
        return handle_tool_error(exc)
