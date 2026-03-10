"""Production MCP tools for company build/produce flows."""

from __future__ import annotations

from agentropolis.mcp._shared import company_tool_context, handle_tool_error
from agentropolis.mcp.server import mcp
from agentropolis.services.production import (
    build_building as build_building_svc,
    get_building_types as get_building_types_svc,
    get_recipes as get_recipes_svc,
    start_production as start_production_svc,
    stop_production as stop_production_svc,
)


@mcp.tool()
async def get_recipes(company_api_key: str, building_type: str | None = None) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, _company):
            return {"ok": True, "recipes": await get_recipes_svc(session, building_type)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_building_types(company_api_key: str) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, _company):
            return {"ok": True, "building_types": await get_building_types_svc(session)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def build_building(company_api_key: str, building_type: str) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            payload = await build_building_svc(session, company.id, building_type)
            await session.commit()
            return {"ok": True, "building": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def start_production(
    company_api_key: str,
    building_id: int,
    recipe_id: int,
) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            payload = await start_production_svc(session, company.id, building_id, recipe_id)
            await session.commit()
            return {"ok": True, "production": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def stop_production(company_api_key: str, building_id: int) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            stopped = await stop_production_svc(session, company.id, building_id)
            await session.commit()
            return {"ok": True, "stopped": bool(stopped), "building_id": building_id}
    except Exception as exc:
        return handle_tool_error(exc)
