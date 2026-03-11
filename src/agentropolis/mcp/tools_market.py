"""Market MCP tools for company-backed trading."""

from __future__ import annotations

from agentropolis.mcp._shared import (
    agent_company_tool_context,
    handle_tool_error,
    parity_http_error,
)
from agentropolis.mcp.server import mcp
from agentropolis.services import leaderboard as leaderboard_svc
from agentropolis.services import market_engine


@mcp.tool()
async def get_market_prices(agent_api_key: str) -> dict:
    try:
        async with agent_company_tool_context(
            agent_api_key,
            family="company_market",
        ) as (session, _agent, _company):
            return {"ok": True, "prices": await market_engine.get_market_prices(session)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_order_book(agent_api_key: str, resource: str) -> dict:
    try:
        async with agent_company_tool_context(
            agent_api_key,
            family="company_market",
        ) as (session, _agent, _company):
            try:
                payload = await market_engine.get_order_book(session, resource)
            except ValueError as exc:
                raise parity_http_error(
                    404,
                    str(exc),
                    error_code="market_resource_not_found",
                ) from exc
            return {"ok": True, "order_book": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_price_history(agent_api_key: str, resource: str, ticks: int = 50) -> dict:
    try:
        async with agent_company_tool_context(
            agent_api_key,
            family="company_market",
        ) as (session, _agent, _company):
            try:
                payload = await leaderboard_svc.get_price_history(session, resource, ticks=ticks)
            except ValueError as exc:
                raise parity_http_error(
                    404,
                    str(exc),
                    error_code="market_resource_not_found",
                ) from exc
            return {"ok": True, "history": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_trade_history(
    agent_api_key: str,
    resource: str | None = None,
    ticks: int = 10,
) -> dict:
    try:
        async with agent_company_tool_context(
            agent_api_key,
            family="company_market",
        ) as (session, _agent, _company):
            try:
                payload = await leaderboard_svc.get_trade_history(session, resource, ticks=ticks)
            except ValueError as exc:
                raise parity_http_error(
                    404,
                    str(exc),
                    error_code="market_resource_not_found",
                ) from exc
            return {"ok": True, "trades": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def place_buy_order(
    agent_api_key: str,
    resource: str,
    quantity: int,
    price: int,
    time_in_force: str = "GTC",
) -> dict:
    try:
        async with agent_company_tool_context(
            agent_api_key,
            family="company_market",
            mutate=True,
            operation="place_buy_order",
            spend_amount=int(quantity) * int(price),
        ) as (session, _agent, company):
            order_id = await market_engine.place_buy_order(
                session,
                company.id,
                resource,
                quantity,
                price,
                time_in_force,
            )
            await session.commit()
            orders = await market_engine.get_my_orders(session, company.id, status="ALL")
            return {"ok": True, "order": next(order for order in orders if order["order_id"] == order_id)}
    except ValueError as exc:
        return handle_tool_error(
            parity_http_error(
                400,
                str(exc),
                error_code="market_buy_invalid",
            )
        )
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def place_sell_order(
    agent_api_key: str,
    resource: str,
    quantity: int,
    price: int,
    time_in_force: str = "GTC",
) -> dict:
    try:
        async with agent_company_tool_context(
            agent_api_key,
            family="company_market",
            mutate=True,
            operation="place_sell_order",
        ) as (session, _agent, company):
            order_id = await market_engine.place_sell_order(
                session,
                company.id,
                resource,
                quantity,
                price,
                time_in_force,
            )
            await session.commit()
            orders = await market_engine.get_my_orders(session, company.id, status="ALL")
            return {"ok": True, "order": next(order for order in orders if order["order_id"] == order_id)}
    except ValueError as exc:
        return handle_tool_error(
            parity_http_error(
                400,
                str(exc),
                error_code="market_sell_invalid",
            )
        )
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def cancel_order(agent_api_key: str, order_id: int) -> dict:
    try:
        async with agent_company_tool_context(
            agent_api_key,
            family="company_market",
            mutate=True,
            operation="cancel_order",
        ) as (session, _agent, company):
            cancelled = await market_engine.cancel_order(session, company.id, order_id)
            await session.commit()
            if not cancelled:
                raise parity_http_error(
                    404,
                    "Order not found or no longer cancellable.",
                    error_code="market_order_not_cancellable",
                )
            orders = await market_engine.get_my_orders(session, company.id, status="ALL")
            return {
                "ok": True,
                "order": next(order for order in orders if order["order_id"] == order_id),
            }
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_my_orders(agent_api_key: str, status: str = "OPEN") -> dict:
    try:
        async with agent_company_tool_context(
            agent_api_key,
            family="company_market",
        ) as (session, _agent, company):
            try:
                payload = await market_engine.get_my_orders(session, company.id, status=status)
            except ValueError as exc:
                raise parity_http_error(
                    400,
                    str(exc),
                    error_code="market_order_status_invalid",
                ) from exc
            return {"ok": True, "orders": payload}
    except Exception as exc:
        return handle_tool_error(exc)
