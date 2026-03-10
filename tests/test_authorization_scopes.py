"""Authorization scope and delegation baseline tests."""

from __future__ import annotations

import asyncio

import pytest

from agentropolis.config import settings
from agentropolis.control_contract import build_control_contract_catalog
from agentropolis.mcp.tools_agent import get_agent_status, register_agent
from agentropolis.mcp.tools_company import create_company
from agentropolis.mcp.tools_market import place_sell_order
from agentropolis.mcp.tools_inventory import get_inventory
from agentropolis.runtime_meta import build_runtime_metadata
from tests.contract.parity_helpers import admin_headers, api_key_headers, seeded_client


def test_authorization_catalog_exposes_resource_rules_and_delegation_model() -> None:
    authorization = build_control_contract_catalog()["authorization"]

    assert authorization["actor_kinds"] == ["public", "agent", "company", "admin"]
    assert any(
        rule["resource"] == "company_operations"
        and "company_market" in rule["scope_families"]
        and "company_production" in rule["scope_families"]
        for rule in authorization["resource_rules"]
    )
    assert any(
        rule["rule"] == "company_mutations_obey_founder_agent_preview_policy"
        and rule["effect"] == "delegated_preview_policy_check"
        for rule in authorization["delegation_rules"]
    )
    assert any(
        rule["rule"] == "company_keys_do_not_upgrade_to_agent_identity"
        and "agent_self" in rule["applies_to_families"]
        for rule in authorization["delegation_rules"]
    )


def test_runtime_metadata_surfaces_authorization_summary() -> None:
    surface = build_runtime_metadata()["authorization_surface"]

    assert surface["catalog_source"] == "/meta/contract"
    assert surface["resource_rule_count"] >= 5
    assert surface["delegation_rule_count"] >= 3
    assert "company_market" in surface["rest_scope_families"]
    assert "company_market" in surface["mcp_scope_families"]
    assert "founder-agent preview policy" in surface["company_act_as_rule"]
    assert "Guilds, treaties, and warfare contracts" in surface["guild_actor_model"]


def test_rest_and_mcp_reject_cross_actor_keys_consistently() -> None:
    async def scenario() -> None:
        async with seeded_client() as (client, _session_factory):
            created_agent = await register_agent("Authz Cross Actor")
            assert created_agent["ok"] is True
            agent_key = created_agent["agent"]["api_key"]

            created_company = await create_company(agent_key, "Authz Cross Actor Works")
            assert created_company["ok"] is True
            company_key = created_company["company"]["api_key"]

            rest_agent_with_company = await client.get(
                "/api/agent/status",
                headers=api_key_headers(company_key),
            )
            rest_inventory_with_agent = await client.get(
                "/api/inventory",
                headers=api_key_headers(agent_key),
            )

            mcp_agent_with_company = await get_agent_status(company_key)
            mcp_inventory_with_agent = await get_inventory(agent_key)

            assert rest_agent_with_company.status_code == 401
            assert rest_agent_with_company.json()["error_code"] == "auth_agent_api_key_invalid"
            assert mcp_agent_with_company["ok"] is False
            assert mcp_agent_with_company["status_code"] == 401
            assert mcp_agent_with_company["error_code"] == "auth_agent_api_key_invalid"
            assert mcp_agent_with_company["detail"] == rest_agent_with_company.json()["detail"]

            assert rest_inventory_with_agent.status_code == 401
            assert rest_inventory_with_agent.json()["error_code"] == "auth_company_api_key_invalid"
            assert mcp_inventory_with_agent["ok"] is False
            assert mcp_inventory_with_agent["status_code"] == 401
            assert mcp_inventory_with_agent["error_code"] == "auth_company_api_key_invalid"
            assert mcp_inventory_with_agent["detail"] == rest_inventory_with_agent.json()["detail"]

    asyncio.run(scenario())


def test_company_key_mutations_still_obey_founder_agent_scope_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")

    async def scenario() -> None:
        async with seeded_client() as (client, _session_factory):
            created_agent = await register_agent("Authz Founder")
            assert created_agent["ok"] is True
            agent_id = created_agent["agent"]["agent_id"]
            agent_key = created_agent["agent"]["api_key"]

            created_company = await create_company(agent_key, "Founder Policy Works")
            assert created_company["ok"] is True
            company_key = created_company["company"]["api_key"]

            policy_update = await client.put(
                f"/meta/control-plane/agents/{agent_id}/policy",
                headers=admin_headers(),
                json={"allowed_families": ["agent_self"]},
            )
            assert policy_update.status_code == 200

            rest_sell = await client.post(
                "/api/market/sell",
                headers=api_key_headers(company_key),
                json={"resource": "H2O", "quantity": 1, "price": 10},
            )
            mcp_sell = await place_sell_order(company_key, "H2O", 1, 10)

            assert rest_sell.status_code == 403
            assert rest_sell.json()["error_code"] == "preview_company_market_access_denied"
            assert mcp_sell["ok"] is False
            assert mcp_sell["status_code"] == 403
            assert mcp_sell["error_code"] == "preview_company_market_access_denied"
            assert mcp_sell["detail"] == rest_sell.json()["detail"]

    asyncio.run(scenario())
