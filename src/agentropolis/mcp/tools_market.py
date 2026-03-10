"""Core MCP tools for market operations."""

from __future__ import annotations

from agentropolis.mcp._shared import company_tool_context, handle_tool_error
from agentropolis.mcp.server import mcp
from agentropolis.services import leaderboard as leaderboard_svc
from agentropolis.services import market_engine


@mcp.tool()
async def get_market_prices_tool(company_api_key: str) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, _company):
            return {"ok": True, "prices": await market_engine.get_market_prices(session)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_order_book_tool(company_api_key: str, resource: str) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, _company):
            return {"ok": True, "order_book": await market_engine.get_order_book(session, resource)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_price_history_tool(company_api_key: str, resource: str, ticks: int = 50) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, _company):
            return {"ok": True, "history": await leaderboard_svc.get_price_history(session, resource, ticks=ticks)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def place_buy_order_tool(
    company_api_key: str,
    resource: str,
    quantity: float,
    price: float,
) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            order_id = await market_engine.place_buy_order(
                session,
                company.id,
                resource,
                quantity,
                price,
            )
            await session.commit()
            orders = await market_engine.get_my_orders(session, company.id, status="ALL")
            return {"ok": True, "order": next(order for order in orders if order["order_id"] == order_id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def place_sell_order_tool(
    company_api_key: str,
    resource: str,
    quantity: float,
    price: float,
) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            order_id = await market_engine.place_sell_order(
                session,
                company.id,
                resource,
                quantity,
                price,
            )
            await session.commit()
            orders = await market_engine.get_my_orders(session, company.id, status="ALL")
            return {"ok": True, "order": next(order for order in orders if order["order_id"] == order_id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def cancel_order_tool(company_api_key: str, order_id: int) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            cancelled = await market_engine.cancel_order(session, company.id, order_id)
            await session.commit()
            return {"ok": bool(cancelled), "order_id": order_id}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_my_orders_tool(company_api_key: str, status: str = "OPEN") -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, company):
            return {"ok": True, "orders": await market_engine.get_my_orders(session, company.id, status=status)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_market_analysis_tool(company_api_key: str, resource: str) -> dict:
    try:
        async with company_tool_context(company_api_key) as (session, _company):
            return {"ok": True, "analysis": await leaderboard_svc.get_market_analysis(session, resource)}
    except Exception as exc:
        return handle_tool_error(exc)
