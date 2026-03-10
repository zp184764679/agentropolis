"""Core MCP tools for production operations."""

from __future__ import annotations

from agentropolis.mcp._shared import company_tool_context, handle_tool_error
from agentropolis.mcp.server import mcp
from agentropolis.services.production import (
    build_building,
    get_building_types,
    get_company_buildings,
    get_recipes,
    start_production,
    stop_production,
)


@mcp.tool()
async def get_buildings_tool(company_api_key: str) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            return {"ok": True, "buildings": await get_company_buildings(session, company.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_recipes_tool(company_api_key: str, building_type: str | None = None) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, _company):
            return {"ok": True, "recipes": await get_recipes(session, building_type)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_building_types_tool(company_api_key: str) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, _company):
            return {"ok": True, "building_types": await get_building_types(session)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def build_building_tool(company_api_key: str, building_type: str) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            payload = await build_building(session, company.id, building_type)
            await session.commit()
            return {"ok": True, "building": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def start_production_tool(company_api_key: str, building_id: int, recipe_id: int) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            payload = await start_production(session, company.id, building_id, recipe_id)
            await session.commit()
            return {"ok": True, "production": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def stop_production_tool(company_api_key: str, building_id: int) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            stopped = await stop_production(session, company.id, building_id)
            await session.commit()
            return {"ok": bool(stopped), "building_id": building_id}
    except Exception as exc:
        return handle_tool_error(exc)
