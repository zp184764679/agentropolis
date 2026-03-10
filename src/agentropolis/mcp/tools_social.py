"""Social and diplomacy MCP tools for the local preview surface."""

from __future__ import annotations

from agentropolis.mcp._shared import (
    agent_tool_context,
    handle_tool_error,
    parity_http_error,
)
from agentropolis.mcp.server import mcp
from agentropolis.services.diplomacy_svc import (
    accept_treaty,
    get_relationships,
    get_treaties,
    propose_treaty,
    set_relationship,
)
from agentropolis.services.guild_svc import (
    create_guild as create_guild_svc,
    get_guild_info,
    join_guild as join_guild_svc,
    leave_guild as leave_guild_svc,
    list_guilds as list_guilds_svc,
)


@mcp.tool()
async def create_guild(
    agent_api_key: str,
    name: str,
    home_region_id: int,
) -> dict:
    try:
        async with agent_tool_context(
            agent_api_key,
            family="social",
            mutate=True,
            operation="guild_create",
        ) as (session, agent):
            payload = await create_guild_svc(session, agent.id, name, home_region_id)
            await session.commit()
            return {"ok": True, "guild": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_guild(agent_api_key: str, guild_id: int) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="social") as (session, _agent):
            try:
                payload = await get_guild_info(session, guild_id)
            except ValueError as exc:
                raise parity_http_error(404, str(exc)) from exc
            return {"ok": True, "guild": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def list_guilds(agent_api_key: str, region_id: int | None = None) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="social") as (session, _agent):
            return {"ok": True, "guilds": await list_guilds_svc(session, region_id=region_id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def join_guild(agent_api_key: str, guild_id: int) -> dict:
    try:
        async with agent_tool_context(
            agent_api_key,
            family="social",
            mutate=True,
            operation="guild_join_leave",
        ) as (session, agent):
            payload = await join_guild_svc(session, agent.id, guild_id)
            await session.commit()
            return {
                "ok": True,
                "message": f"Joined guild {payload['guild_id']} as {payload['rank']}.",
                "membership": payload,
            }
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def leave_guild(agent_api_key: str, guild_id: int) -> dict:
    try:
        async with agent_tool_context(
            agent_api_key,
            family="social",
            mutate=True,
            operation="guild_join_leave",
        ) as (session, agent):
            await leave_guild_svc(session, agent.id, guild_id)
            await session.commit()
            return {
                "ok": True,
                "message": f"Left guild {guild_id}.",
                "guild_id": guild_id,
            }
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def treaty_tool(
    agent_api_key: str,
    action: str = "list",
    treaty_id: int | None = None,
    treaty_type: str | None = None,
    target_agent_id: int | None = None,
    target_guild_id: int | None = None,
    terms: dict | None = None,
    duration_hours: int = 24,
    active_only: bool = True,
) -> dict:
    mutate = action in {"propose", "accept"}
    try:
        async with agent_tool_context(
            agent_api_key,
            family="social",
            mutate=mutate,
            operation="treaty_propose_accept" if mutate else None,
        ) as (session, agent):
            if action == "list":
                return {
                    "ok": True,
                    "treaties": await get_treaties(session, agent_id=agent.id, active_only=active_only),
                }
            if action == "propose":
                if treaty_type is None:
                    raise ValueError("treaty_type is required for propose")
                payload = await propose_treaty(
                    session,
                    treaty_type,
                    party_a_agent_id=agent.id,
                    party_b_agent_id=target_agent_id,
                    party_b_guild_id=target_guild_id,
                    terms=terms,
                    duration_hours=duration_hours,
                )
                await session.commit()
                return {"ok": True, "treaty": payload}
            if action == "accept":
                if treaty_id is None:
                    raise ValueError("treaty_id is required for accept")
                try:
                    payload = await accept_treaty(session, treaty_id, agent.id)
                except ValueError as exc:
                    status_code = 404 if "not found" in str(exc).lower() else 400
                    raise parity_http_error(status_code, str(exc)) from exc
                await session.commit()
                return {"ok": True, "treaty": payload}
            raise ValueError("Unsupported action for treaty_tool")
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def relationship_tool(
    agent_api_key: str,
    action: str = "list",
    target_agent_id: int | None = None,
    relation_type: str | None = None,
    trust_delta: int = 0,
) -> dict:
    mutate = action == "set"
    try:
        async with agent_tool_context(
            agent_api_key,
            family="social",
            mutate=mutate,
            operation="relationship_set" if mutate else None,
        ) as (session, agent):
            if action == "list":
                return {"ok": True, "relationships": await get_relationships(session, agent.id)}
            if action == "set":
                if target_agent_id is None or relation_type is None:
                    raise ValueError("target_agent_id and relation_type are required for set")
                payload = await set_relationship(
                    session,
                    agent.id,
                    target_agent_id,
                    relation_type,
                    trust_delta=trust_delta,
                )
                await session.commit()
                return {"ok": True, "relationship": payload}
            raise ValueError("Unsupported action for relationship_tool")
    except Exception as exc:
        return handle_tool_error(exc)
