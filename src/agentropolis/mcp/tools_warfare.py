"""Warfare MCP tools for the local preview surface."""

from __future__ import annotations

from agentropolis.mcp._shared import (
    agent_tool_context,
    handle_tool_error,
    parity_http_error,
)
from agentropolis.mcp.server import mcp
from agentropolis.services import warfare_svc


@mcp.tool()
async def create_contract(
    agent_api_key: str,
    mission_type: str,
    target_region_id: int,
    reward_per_agent: int,
    max_agents: int,
    target_building_id: int | None = None,
    target_transport_id: int | None = None,
    mission_duration_seconds: int = 3600,
    expires_in_seconds: int = 1800,
) -> dict:
    try:
        async with agent_tool_context(
            agent_api_key,
            family="warfare",
            mutate=True,
            operation="contract_create_activate_execute_cancel",
            spend_amount=reward_per_agent * max_agents,
        ) as (session, agent):
            created = await warfare_svc.create_contract(
                session,
                employer_agent_id=agent.id,
                mission_type=mission_type,
                target_region_id=target_region_id,
                reward_per_agent=reward_per_agent,
                max_agents=max_agents,
                target_building_id=target_building_id,
                target_transport_id=target_transport_id,
                mission_duration_seconds=mission_duration_seconds,
                expires_in_seconds=expires_in_seconds,
            )
            payload = await warfare_svc.get_contract(session, created["contract_id"])
            await session.commit()
            return {"ok": True, "contract": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def list_contracts(
    agent_api_key: str,
    region_id: int | None = None,
    status: str | None = None,
    mission_type: str | None = None,
    limit: int = 50,
) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="warfare") as (session, _agent):
            payload = await warfare_svc.list_contracts(
                session,
                region_id=region_id,
                status=status,
                mission_type=mission_type,
                limit=limit,
            )
            return {"ok": True, "contracts": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def contract_action_tool(
    agent_api_key: str,
    action: str = "get",
    contract_id: int | None = None,
) -> dict:
    mutate = action in {"enlist", "activate", "cancel", "execute"}
    try:
        async with agent_tool_context(
            agent_api_key,
            family="warfare",
            mutate=mutate,
            operation="contract_create_activate_execute_cancel" if mutate else None,
        ) as (session, agent):
            if contract_id is None:
                raise ValueError("contract_id is required")

            if action == "get":
                payload = await warfare_svc.get_contract(session, contract_id)
                if payload is None:
                    raise parity_http_error(404, "Contract not found")
                return {"ok": True, "contract": payload}
            if action == "enlist":
                payload = await warfare_svc.enlist_in_contract(session, agent.id, contract_id)
                await session.commit()
                return {
                    "ok": True,
                    "message": (
                        f"Enlisted as {payload['role']} "
                        f"({payload['enlisted_count']}/{payload['max_agents']})"
                    ),
                    "result": payload,
                }

            if action == "activate":
                contract = await warfare_svc.get_contract(session, contract_id)
                if contract is None:
                    raise parity_http_error(404, "Contract not found")
                if contract["employer_agent_id"] != agent.id:
                    raise parity_http_error(403, "Only the employer can activate")
                payload = await warfare_svc.activate_contract(session, contract_id)
                await session.commit()
                return {
                    "ok": True,
                    "message": f"Contract activated with {payload['active_agents']} agents",
                    "result": payload,
                }
            if action == "cancel":
                payload = await warfare_svc.cancel_contract(session, agent.id, contract_id)
                await session.commit()
                return {
                    "ok": True,
                    "message": (
                        f"Contract cancelled. Refund: {payload['refund']}, fee: {payload['fee']}"
                    ),
                    "result": payload,
                }
            if action == "execute":
                contract = await warfare_svc.get_contract(session, contract_id)
                if contract is None:
                    raise parity_http_error(404, "Contract not found")
                if contract["employer_agent_id"] != agent.id:
                    raise parity_http_error(403, "Only the employer can execute")
                mission_type = contract["mission_type"]
                if mission_type == "sabotage_building":
                    payload = await warfare_svc.execute_sabotage(session, contract_id)
                elif mission_type == "raid_transport":
                    payload = await warfare_svc.execute_transport_raid(session, contract_id)
                else:
                    raise ValueError(f"Cannot execute {mission_type} contracts")
                await session.commit()
                return {"ok": True, "result": payload}
            raise ValueError("Unsupported action for contract_action_tool")
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_region_threats(agent_api_key: str, region_id: int) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="warfare") as (session, _agent):
            return {"ok": True, "threats": await warfare_svc.get_region_threats(session, region_id)}
    except Exception as exc:
        return handle_tool_error(exc)
