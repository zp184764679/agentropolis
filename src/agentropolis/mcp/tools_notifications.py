"""Notification MCP tools for the local preview surface."""

from __future__ import annotations

from agentropolis.mcp._shared import agent_tool_context, handle_tool_error
from agentropolis.mcp.server import mcp
from agentropolis.services.notification_svc import (
    get_notifications as get_notifications_svc,
    mark_read,
)


@mcp.tool()
async def get_notifications(
    agent_api_key: str,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            return {
                "ok": True,
                "notifications": await get_notifications_svc(
                    session,
                    agent.id,
                    unread_only=unread_only,
                    limit=limit,
                    offset=offset,
                ),
            }
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def mark_notification_read(agent_api_key: str, notification_id: int) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy", mutate=True) as (session, agent):
            marked = await mark_read(session, agent.id, notification_id)
            await session.commit()
            return {"ok": bool(marked), "notification_id": notification_id}
    except Exception as exc:
        return handle_tool_error(exc)
