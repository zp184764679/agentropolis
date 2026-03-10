"""End-to-end REST/MCP parity journey for the mounted gameplay surface."""

from __future__ import annotations

import asyncio

from agentropolis.mcp.tools_agent import register_agent
from agentropolis.mcp.tools_company import create_company, get_company
from agentropolis.mcp.tools_intel import get_market_intel
from agentropolis.mcp.tools_market import place_sell_order
from agentropolis.mcp.tools_strategy import autonomy_tool, briefing_tool, digest_tool
from tests.contract.parity_helpers import api_key_headers, seeded_client


def _normalized_dashboard(payload: dict) -> dict:
    normalized = dict(payload)
    normalized["generated_at"] = "<generated>"
    autonomy = dict(normalized["autonomy"])
    autonomy["hour_window_started_at"] = "<window>"
    normalized["autonomy"] = autonomy
    return normalized


def _normalized_digest(payload: dict) -> dict:
    normalized = dict(payload)
    normalized["generated_at"] = "<generated>"
    return normalized


def _assert_dashboard_equivalent(rest_payload: dict, mcp_payload: dict) -> None:
    assert _normalized_dashboard(mcp_payload)["company"] == _normalized_dashboard(rest_payload)["company"]
    assert _normalized_dashboard(mcp_payload)["autonomy"] == _normalized_dashboard(rest_payload)["autonomy"]
    assert _normalized_dashboard(mcp_payload)["goals"] == _normalized_dashboard(rest_payload)["goals"]
    assert _normalized_dashboard(mcp_payload)["decision_summary"] == _normalized_dashboard(rest_payload)["decision_summary"]
    assert _normalized_dashboard(mcp_payload)["digest_unread_count"] == _normalized_dashboard(rest_payload)["digest_unread_count"]
    for field in ("agent_id", "name", "current_region_id", "home_region_id", "personal_balance"):
        assert mcp_payload["agent"][field] == rest_payload["agent"][field]
    for field in ("health", "hunger", "thirst", "energy", "happiness", "reputation"):
        assert abs(float(mcp_payload["agent"][field]) - float(rest_payload["agent"][field])) <= 0.01


def test_rest_and_mcp_can_share_one_playable_journey() -> None:
    async def scenario() -> None:
        async with seeded_client() as (client, _session_factory):
            buyer_rest = await client.post(
                "/api/agent/register",
                json={"name": "Journey Buyer"},
            )
            assert buyer_rest.status_code == 200
            buyer_agent = buyer_rest.json()
            buyer_agent_key = buyer_agent["api_key"]

            buyer_company = await create_company(buyer_agent_key, "Journey Buyer Works")
            assert buyer_company["ok"] is True
            buyer_company_key = buyer_company["company"]["api_key"]

            seller = await register_agent("Journey Seller")
            assert seller["ok"] is True
            seller_key = seller["agent"]["api_key"]
            seller_company = await create_company(seller_key, "Journey Seller Works")
            assert seller_company["ok"] is True
            seller_company_key = seller_company["company"]["api_key"]

            rest_company = await client.get(
                "/api/agent/company",
                headers=api_key_headers(buyer_agent_key),
            )
            mcp_company = await get_company(buyer_agent_key)
            assert rest_company.status_code == 200
            assert mcp_company["company"] == rest_company.json()

            rest_autonomy_update = await client.put(
                "/api/autonomy/config",
                headers=api_key_headers(buyer_agent_key),
                json={
                    "autopilot_enabled": True,
                    "mode": "assisted",
                    "spending_limit_per_hour": 90,
                },
            )
            rest_orders_update = await client.put(
                "/api/autonomy/standing-orders",
                headers=api_key_headers(buyer_agent_key),
                json={
                    "standing_orders": {
                        "buy_rules": [{"resource": "H2O", "below_price": 7, "max_qty": 5}],
                        "sell_rules": [],
                    }
                },
            )
            assert rest_autonomy_update.status_code == 200
            assert rest_orders_update.status_code == 200

            mcp_config = await autonomy_tool(buyer_agent_key, action="get_config")
            mcp_orders = await autonomy_tool(buyer_agent_key, action="get_standing_orders")
            assert mcp_config["ok"] is True
            assert mcp_orders["ok"] is True
            assert mcp_config["config"] == rest_autonomy_update.json()
            assert mcp_orders["standing_orders"]["buy_rules"][0]["resource"] == "H2O"

            sell_order = await place_sell_order(
                seller_company_key,
                resource="H2O",
                quantity=5,
                price=6,
            )
            assert sell_order["ok"] is True

            rest_buy = await client.post(
                "/api/market/buy",
                headers=api_key_headers(buyer_company_key),
                json={"resource": "H2O", "quantity": 5, "price": 6},
            )
            assert rest_buy.status_code == 200

            rest_intel = await client.get(
                "/api/intel/market/H2O",
                headers=api_key_headers(buyer_agent_key),
            )
            rest_digest = await client.get(
                "/api/digest",
                headers=api_key_headers(buyer_agent_key),
            )
            rest_dashboard = await client.get(
                "/api/dashboard",
                headers=api_key_headers(buyer_agent_key),
            )
            assert rest_intel.status_code == 200
            assert rest_digest.status_code == 200
            assert rest_dashboard.status_code == 200

            mcp_intel = await get_market_intel(buyer_agent_key, "H2O")
            mcp_digest = await digest_tool(buyer_agent_key, action="get")
            mcp_dashboard = await briefing_tool(buyer_agent_key, section="dashboard")

            assert mcp_intel["intel"] == rest_intel.json()
            assert _normalized_digest(mcp_digest["digest"]) == _normalized_digest(rest_digest.json())
            _assert_dashboard_equivalent(rest_dashboard.json(), mcp_dashboard["briefing"])

    asyncio.run(scenario())
