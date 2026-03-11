"""End-to-end playable path covering agent, company, production, market, and status."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.models import Base, Building, Recipe
from agentropolis.services.game_engine import run_housekeeping_sweep
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world


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
            yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await seed_game_data(session)
        await seed_world(session)

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client, session_factory
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def _api_key_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def test_playable_path_registers_company_runs_production_and_executes_market_trade() -> None:
    async def scenario() -> None:
        async with _seeded_client() as (client, session_factory):
            agent_a = await client.post("/api/agent/register", json={"name": "Alpha Agent"})
            agent_b = await client.post("/api/agent/register", json={"name": "Beta Agent"})
            assert agent_a.status_code == 200
            assert agent_b.status_code == 200

            agent_a_key = agent_a.json()["api_key"]
            agent_b_key = agent_b.json()["api_key"]

            company_a = await client.post(
                "/api/agent/company",
                headers=_api_key_headers(agent_a_key),
                json={"company_name": "Alpha Works"},
            )
            company_b = await client.post(
                "/api/agent/company",
                headers=_api_key_headers(agent_b_key),
                json={"company_name": "Beta Forge"},
            )
            assert company_a.status_code == 200
            assert company_b.status_code == 200

            company_status = await client.get(
                "/api/agent/company",
                headers=_api_key_headers(agent_a_key),
            )
            assert company_status.status_code == 200
            assert company_status.json()["name"] == "Alpha Works"

            buildings_response = await client.get(
                "/api/production/buildings",
                headers=_api_key_headers(agent_a_key),
            )
            assert buildings_response.status_code == 200
            extractor = next(
                item
                for item in buildings_response.json()
                if item["building_type"] == "extractor"
            )

            recipes_response = await client.get(
                "/api/production/recipes",
                params={"building_type": "extractor"},
            )
            assert recipes_response.status_code == 200
            extract_water_recipe = next(
                item for item in recipes_response.json() if item["name"] == "Extract Water"
            )

            start_response = await client.post(
                "/api/production/start",
                headers=_api_key_headers(agent_a_key),
                json={
                    "building_id": extractor["building_id"],
                    "recipe_id": extract_water_recipe["recipe_id"],
                },
            )
            assert start_response.status_code == 200

            async with session_factory() as session:
                building = await session.get(Building, extractor["building_id"])
                recipe = await session.get(Recipe, extract_water_recipe["recipe_id"])
                assert building is not None
                assert recipe is not None
                building.last_production_at = datetime.now(UTC) - timedelta(
                    seconds=recipe.duration_ticks * 60 + 5
                )
                await session.flush()
                await run_housekeeping_sweep(session, tick_number=1, now=datetime.now(UTC))
                await session.commit()

            inventory_response = await client.get(
                "/api/inventory/H2O",
                headers=_api_key_headers(agent_a_key),
            )
            assert inventory_response.status_code == 200
            assert inventory_response.json()["quantity"] >= 110

            sell_response = await client.post(
                "/api/market/sell",
                headers=_api_key_headers(agent_b_key),
                json={"resource": "RAT", "quantity": 5, "price": 10},
            )
            buy_response = await client.post(
                "/api/market/buy",
                headers=_api_key_headers(agent_a_key),
                json={"resource": "RAT", "quantity": 5, "price": 11},
            )
            assert sell_response.status_code == 200
            assert buy_response.status_code == 200

            trades_response = await client.get("/api/market/trades", params={"ticker": "RAT"})
            assert trades_response.status_code == 200
            assert trades_response.json()

            game_status = await client.get("/api/game/status")
            assert game_status.status_code == 200
            assert game_status.json()["current_tick"] >= 1

            leaderboard = await client.get(
                "/api/game/leaderboard",
                headers=_api_key_headers(agent_a_key),
            )
            assert leaderboard.status_code == 200
            assert leaderboard.json()["entries"]

    asyncio.run(scenario())
