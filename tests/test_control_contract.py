"""Control-contract and authorization catalog tests."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.control_contract import (
    CONTRACT_VERSION_HEADER,
    CONTROL_CONTRACT_VERSION,
    build_control_contract_catalog,
)
from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.middleware import REQUEST_ID_HEADER
from agentropolis.mcp.server import mcp
from agentropolis.models import Base
from agentropolis.runtime_meta import build_runtime_metadata
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from scripts.export_contract_snapshot import build_contract_snapshot

ERROR_CODE_HEADER = "X-Agentropolis-Error-Code"


@asynccontextmanager
async def _seeded_client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await seed_game_data(session)
        await seed_world(session)
        await session.commit()

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def test_control_contract_catalog_matches_runtime_and_mcp_registry() -> None:
    catalog = build_control_contract_catalog()
    runtime_meta = build_runtime_metadata()
    registry_names = set(mcp._tool_manager._tools)
    scope_names = {entry["tool_name"] for entry in catalog["authorization"]["mcp_tool_scopes"]}

    assert catalog["version"] == CONTROL_CONTRACT_VERSION
    assert catalog["minimum_contract_frozen"] is True
    assert catalog["transport"]["mcp"] == "streamable-http"
    assert catalog["headers"]["contract_version"] == CONTRACT_VERSION_HEADER
    assert catalog["headers"]["request_id"] == "X-Agentropolis-Request-ID"
    assert catalog["execution_semantics"]["job_model"]["states"][-1] == "dead_letter"
    assert catalog["execution_semantics"]["backfill_policy"]["auto_gap_detection"] is True
    assert any(
        entry["route"] == "/meta/execution/jobs/housekeeping-backfill"
        for entry in catalog["execution_semantics"]["async_acceptance"]
    )
    assert catalog["error_taxonomy"]["auth_api_key_missing"] == (
        "X-API-Key header is required for this operation."
    )
    assert catalog["error_taxonomy"]["auth_agent_api_key_invalid"] == (
        "Presented agent API key is invalid or inactive."
    )
    assert catalog["error_taxonomy"]["agent_company_not_found"] == (
        "Authenticated agent does not have an active company."
    )
    assert len(catalog["authorization"]["mcp_tool_scopes"]) == 60
    assert catalog["parity_surface"]["mode"] == "semantic_parity_subset"
    assert "npc" in catalog["parity_surface"]["mcp_only_groups"]
    assert any(
        entry["path"] == "/api/company/status"
        for entry in catalog["parity_surface"]["rest_only_operations"]
    )
    assert any(
        entry["operation"] == "place_buy_order"
        for entry in catalog["authorization"]["dangerous_operations"]
    )
    market_tool = next(
        entry
        for entry in catalog["authorization"]["mcp_tool_scopes"]
        if entry["tool_name"] == "place_buy_order"
    )
    assert market_tool["dangerous_operation"] is True
    assert market_tool["dangerous_operation_codes"] == ["place_buy_order"]
    assert scope_names == registry_names
    assert any(group["prefix"] == "/meta/contract" for group in catalog["authorization"]["rest_route_scopes"])
    assert any(group["prefix"] == "/meta/execution" for group in catalog["authorization"]["rest_route_scopes"])
    assert runtime_meta["control_contract_surface"]["endpoint"] == "/meta/contract"
    assert runtime_meta["control_contract_surface"]["version"] == CONTROL_CONTRACT_VERSION
    assert runtime_meta["parity_surface"]["catalog_source"] == "/meta/contract"
    assert "notifications" in runtime_meta["parity_surface"]["mcp_only_groups"]

    snapshot = build_contract_snapshot()
    assert snapshot["control_contract"]["version"] == CONTROL_CONTRACT_VERSION
    assert snapshot["control_contract"]["authorization"]["mcp_tool_scopes"][0]["tool_name"]


def test_meta_contract_and_auth_failures_use_stable_contract_headers() -> None:
    async def scenario() -> None:
        async with _seeded_client() as client:
            contract = await client.get("/meta/contract")
            assert contract.status_code == 200
            assert contract.headers[CONTRACT_VERSION_HEADER] == CONTROL_CONTRACT_VERSION
            assert contract.json()["version"] == CONTROL_CONTRACT_VERSION
            assert len(contract.json()["authorization"]["mcp_tool_scopes"]) == 60

            missing_agent_key = await client.get("/api/agent/status")
            assert missing_agent_key.status_code == 401
            assert missing_agent_key.headers[CONTRACT_VERSION_HEADER] == CONTROL_CONTRACT_VERSION
            assert missing_agent_key.headers[ERROR_CODE_HEADER] == "auth_api_key_missing"
            assert missing_agent_key.headers[REQUEST_ID_HEADER]
            assert missing_agent_key.json()["error_code"] == "auth_api_key_missing"
            assert missing_agent_key.json()["request_id"] == missing_agent_key.headers[REQUEST_ID_HEADER]

            invalid_agent_key = await client.get(
                "/api/agent/status",
                headers={"X-API-Key": "not-a-real-agent-key"},
            )
            assert invalid_agent_key.status_code == 401
            assert invalid_agent_key.headers[ERROR_CODE_HEADER] == "auth_agent_api_key_invalid"
            assert invalid_agent_key.json()["error_code"] == "auth_agent_api_key_invalid"

            invalid_inventory_key = await client.get(
                "/api/inventory",
                headers={"X-API-Key": "not-a-real-agent-key"},
            )
            assert invalid_inventory_key.status_code == 401
            assert invalid_inventory_key.headers[ERROR_CODE_HEADER] == "auth_agent_api_key_invalid"
            assert invalid_inventory_key.json()["error_code"] == "auth_agent_api_key_invalid"

    asyncio.run(scenario())
