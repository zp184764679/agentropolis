"""Regression tests for market matching and order cancellation."""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import Base, Inventory, Resource
from agentropolis.services.company_svc import get_company_status, register_company
from agentropolis.services.inventory_svc import get_resource_quantity_in_region
from agentropolis.services.market_engine import (
    cancel_order,
    get_recent_trades,
    get_my_orders,
    place_buy_order,
    place_sell_order,
)
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world


async def _run_seeded_session(callback):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            await seed_game_data(session)
            await seed_world(session)
            return await callback(session)
    finally:
        await engine.dispose()


def test_market_buy_sell_match_transfers_inventory_and_records_trade() -> None:
    async def scenario(session: AsyncSession) -> None:
        buyer = await register_company(session, "Buyer Co")
        seller = await register_company(session, "Seller Co")

        await place_sell_order(session, seller["company_id"], "H2O", 5.0, 8.0)
        await place_buy_order(session, buyer["company_id"], "H2O", 5.0, 9.0)

        trades = await get_recent_trades(session, resource_ticker="H2O")
        assert len(trades) == 1
        assert trades[0]["price"] == 8.0
        assert trades[0]["quantity"] == 5.0

        buyer_h2o = (
            await session.execute(
                select(Inventory.quantity)
                .join(Resource, Inventory.resource_id == Resource.id)
                .where(
                    Inventory.company_id == buyer["company_id"],
                    Resource.ticker == "H2O",
                )
            )
        ).scalar_one()
        assert float(buyer_h2o) == 105.0

        seller_status = await get_company_status(session, seller["company_id"])
        assert seller_status["balance"] > seller["initial_balance"]

    asyncio.run(_run_seeded_session(scenario))


def test_cancel_sell_order_releases_reserved_inventory() -> None:
    async def scenario(session: AsyncSession) -> None:
        seller = await register_company(session, "Cancel Seller")
        order_id = await place_sell_order(session, seller["company_id"], "RAT", 10.0, 99.0)

        reserved_before = await get_resource_quantity_in_region(
            session,
            seller["company_id"],
            "RAT",
            region_id=seller["region_id"],
        )
        assert float(reserved_before["reserved"]) == 10.0

        cancelled = await cancel_order(session, seller["company_id"], order_id)
        assert cancelled is True

        reserved_after = await get_resource_quantity_in_region(
            session,
            seller["company_id"],
            "RAT",
            region_id=seller["region_id"],
        )
        assert float(reserved_after["reserved"]) == 0.0
        all_orders = await get_my_orders(session, seller["company_id"], status="ALL")
        cancelled_order = next(item for item in all_orders if item["order_id"] == order_id)
        assert cancelled_order["status"] == "CANCELLED"

    asyncio.run(_run_seeded_session(scenario))
