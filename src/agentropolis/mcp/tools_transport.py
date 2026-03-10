"""Transport MCP tools for the local preview surface."""

from __future__ import annotations

from agentropolis.mcp._shared import (
    agent_tool_context,
    handle_tool_error,
    parity_http_error,
)
from agentropolis.mcp.server import mcp
from agentropolis.services.transport_svc import (
    create_transport as create_transport_svc,
    estimate_transport_cost as estimate_transport_cost_svc,
    get_my_transports as get_my_transports_svc,
    get_transport_status as get_transport_status_svc,
)


@mcp.tool()
async def create_transport(
    agent_api_key: str,
    from_region_id: int,
    to_region_id: int,
    items: dict[str, int],
    transport_type: str = "backpack",
) -> dict:
    try:
        async with agent_tool_context(
            agent_api_key,
            family="transport",
            mutate=True,
            operation="transport_create",
            spend_amount=lambda session, _agent: estimate_transport_cost_svc(
                session,
                from_region_id=from_region_id,
                to_region_id=to_region_id,
                items=items,
                transport_type=transport_type,
            ),
        ) as (session, agent):
            payload = await create_transport_svc(
                session,
                from_region_id,
                to_region_id,
                items,
                transport_type,
                agent_id=agent.id,
            )
            await session.commit()
            return {"ok": True, "transport": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_transport_status(agent_api_key: str, transport_id: int) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="transport") as (session, agent):
            try:
                payload = await get_transport_status_svc(session, transport_id)
            except ValueError as exc:
                raise parity_http_error(404, str(exc)) from exc
            if payload["owner_agent_id"] != agent.id:
                raise parity_http_error(404, "Transport not found")
            return {"ok": True, "transport": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_my_transports(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="transport") as (session, agent):
            return {
                "ok": True,
                "transports": await get_my_transports_svc(session, agent_id=agent.id),
            }
    except Exception as exc:
        return handle_tool_error(exc)
