"""Regression tests for legacy scaffold read endpoints."""

import asyncio
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.api.auth import hash_api_key
from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.models import (
    Base,
    Building,
    BuildingType,
    Company,
    Inventory,
    Order,
    OrderStatus,
    OrderType,
    PriceHistory,
    Resource,
    Trade,
    Worker,
)
from agentropolis.services.seed import seed_game_data


def _company_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


@asynccontextmanager
async def _legacy_client():
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

    async with session_factory() as seed_session:
        await seed_game_data(seed_session)

        resources = {
            resource.ticker: resource
            for resource in (
                await seed_session.execute(select(Resource).order_by(Resource.ticker.asc()))
            ).scalars().all()
        }
        building_type = (
            await seed_session.execute(
                select(BuildingType).where(BuildingType.name == "extractor")
            )
        ).scalar_one()

        alpha_api_key = "alpha-company-key"
        beta_api_key = "beta-company-key"
        alpha = Company(
            name="Alpha Works",
            api_key_hash=hash_api_key(alpha_api_key),
            balance=2500,
            net_worth=8200,
            is_active=True,
        )
        beta = Company(
            name="Beta Forge",
            api_key_hash=hash_api_key(beta_api_key),
            balance=1700,
            net_worth=5100,
            is_active=True,
        )
        seed_session.add_all([alpha, beta])
        await seed_session.flush()

        seed_session.add_all(
            [
                Worker(company_id=alpha.id, count=14, satisfaction=92.0),
                Worker(company_id=beta.id, count=8, satisfaction=88.0),
                Building(company_id=alpha.id, building_type_id=building_type.id),
                Building(company_id=alpha.id, building_type_id=building_type.id),
                Building(company_id=beta.id, building_type_id=building_type.id),
                Inventory(
                    company_id=alpha.id,
                    resource_id=resources["ORE"].id,
                    quantity=50,
                    reserved=10,
                ),
                Inventory(
                    company_id=alpha.id,
                    resource_id=resources["H2O"].id,
                    quantity=20,
                    reserved=0,
                ),
                Inventory(
                    company_id=beta.id,
                    resource_id=resources["ORE"].id,
                    quantity=15,
                    reserved=0,
                ),
                PriceHistory(
                    resource_id=resources["ORE"].id,
                    tick=1,
                    open=10,
                    high=12,
                    low=9,
                    close=11,
                    volume=20,
                ),
                PriceHistory(
                    resource_id=resources["ORE"].id,
                    tick=2,
                    open=11,
                    high=13,
                    low=10,
                    close=12,
                    volume=25,
                ),
                PriceHistory(
                    resource_id=resources["ORE"].id,
                    tick=3,
                    open=12,
                    high=14,
                    low=11,
                    close=13,
                    volume=30,
                ),
            ]
        )
        await seed_session.flush()

        buy_order = Order(
            company_id=alpha.id,
            resource_id=resources["ORE"].id,
            order_type=OrderType.BUY,
            price=12.5,
            quantity=10,
            remaining=6,
            status=OrderStatus.OPEN,
            created_at_tick=3,
        )
        sell_order = Order(
            company_id=beta.id,
            resource_id=resources["ORE"].id,
            order_type=OrderType.SELL,
            price=14.0,
            quantity=8,
            remaining=5,
            status=OrderStatus.OPEN,
            created_at_tick=3,
        )
        seed_session.add_all([buy_order, sell_order])
        await seed_session.flush()

        seed_session.add(
            Trade(
                buy_order_id=buy_order.id,
                sell_order_id=sell_order.id,
                buyer_id=alpha.id,
                seller_id=beta.id,
                resource_id=resources["ORE"].id,
                price=13.0,
                quantity=4,
                tick_executed=3,
            )
        )
        await seed_session.commit()

    app.dependency_overrides[get_session] = override_get_session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client, {
                "alpha_api_key": alpha_api_key,
                "beta_api_key": beta_api_key,
            }
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def test_game_status_and_leaderboard_reads() -> None:
    async def scenario() -> None:
        async with _legacy_client() as (client, auth):
            status_response = await client.get("/api/game/status")
            assert status_response.status_code == 200
            assert status_response.json()["current_tick"] == 0
            assert status_response.json()["total_companies"] == 2
            assert status_response.json()["active_companies"] == 2

            public_board = await client.get("/api/game/leaderboard")
            assert public_board.status_code == 200
            assert public_board.json()["entries"][0]["company_name"] == "Alpha Works"
            assert public_board.json()["your_rank"] is None

            authed_board = await client.get(
                "/api/game/leaderboard",
                headers=_company_headers(auth["beta_api_key"]),
            )
            assert authed_board.status_code == 200
            assert authed_board.json()["your_rank"] == 2

    asyncio.run(scenario())


def test_market_read_endpoints_return_seeded_data() -> None:
    async def scenario() -> None:
        async with _legacy_client() as (client, auth):
            prices = await client.get("/api/market/prices")
            assert prices.status_code == 200
            ore_row = next(row for row in prices.json() if row["ticker"] == "ORE")
            assert ore_row["last_price"] == 13.0
            assert ore_row["best_bid"] == 12.5
            assert ore_row["best_ask"] == 14.0
            assert ore_row["spread"] == 1.5
            assert ore_row["volume_24h"] == 4.0

            orderbook = await client.get("/api/market/orderbook/ORE")
            assert orderbook.status_code == 200
            assert orderbook.json()["bids"][0]["quantity"] == 6.0
            assert orderbook.json()["asks"][0]["quantity"] == 5.0

            history = await client.get("/api/market/history/ORE")
            assert history.status_code == 200
            assert [candle["tick"] for candle in history.json()] == [1, 2, 3]

            trades = await client.get("/api/market/trades", params={"ticker": "ORE"})
            assert trades.status_code == 200
            assert trades.json()[0]["buyer"] == "Alpha Works"
            assert trades.json()[0]["seller"] == "Beta Forge"

            analysis = await client.get("/api/market/analysis/ORE")
            assert analysis.status_code == 200
            assert analysis.json()["price_trend"] == "rising"
            assert analysis.json()["total_buy_volume"] == 6.0
            assert analysis.json()["total_sell_volume"] == 5.0

            my_orders = await client.get(
                "/api/market/orders",
                headers=_company_headers(auth["alpha_api_key"]),
            )
            assert my_orders.status_code == 200
            assert my_orders.json()[0]["resource"] == "ORE"
            assert my_orders.json()[0]["status"] == "OPEN"

    asyncio.run(scenario())


def test_inventory_read_endpoints_return_company_stockpile() -> None:
    async def scenario() -> None:
        async with _legacy_client() as (client, auth):
            resource_info = await client.get("/api/inventory/info/ORE")
            assert resource_info.status_code == 200
            assert resource_info.json()["name"] == "Iron Ore"

            inventory_response = await client.get(
                "/api/inventory",
                headers=_company_headers(auth["alpha_api_key"]),
            )
            assert inventory_response.status_code == 200
            assert inventory_response.json()["total_value"] > 0
            ore_item = next(
                item for item in inventory_response.json()["items"] if item["ticker"] == "ORE"
            )
            assert ore_item["quantity"] == 50.0
            assert ore_item["reserved"] == 10.0
            assert ore_item["available"] == 40.0

            detail_response = await client.get(
                "/api/inventory/ORE",
                headers=_company_headers(auth["alpha_api_key"]),
            )
            assert detail_response.status_code == 200
            assert detail_response.json()["available"] == 40.0

    asyncio.run(scenario())
