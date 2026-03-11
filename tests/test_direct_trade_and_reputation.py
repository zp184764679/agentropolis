"""Direct trade and reputation tests for issues #45 and #46."""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import Agent, Base, Inventory, NpcShop, Resource
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.direct_trade_svc import execute_direct_trade
from agentropolis.services.npc_shop_svc import calculate_dynamic_price, get_effective_prices
from agentropolis.services.reputation_svc import (
    adjust_reputation,
    check_shop_access,
    get_reputation_modifier,
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


def test_direct_trade_swaps_items_and_copper_atomically() -> None:
    async def scenario(session: AsyncSession) -> None:
        initiator = await register_agent(session, "Trader Initiator", None)
        target = await register_agent(session, "Trader Target", None)

        result = await execute_direct_trade(
            session,
            initiator["agent_id"],
            target["agent_id"],
            offer_items={"RAT": 2},
            request_items={"DW": 1},
            offer_copper=100,
            request_copper=25,
        )
        assert result["initiator_agent_id"] == initiator["agent_id"]
        assert result["target_agent_id"] == target["agent_id"]
        assert result["copper_exchanged"] == 75

        initiator_model = await session.get(Agent, initiator["agent_id"])
        target_model = await session.get(Agent, target["agent_id"])
        assert initiator_model is not None
        assert target_model is not None
        assert int(initiator_model.personal_balance) == initiator["balance"] - 75
        assert int(target_model.personal_balance) == target["balance"] + 75

        inventory_rows = await session.execute(
            select(Inventory.agent_id, Resource.ticker, Inventory.quantity)
            .join(Resource, Resource.id == Inventory.resource_id)
            .where(Inventory.agent_id.in_((initiator["agent_id"], target["agent_id"])))
        )
        by_owner: dict[int, dict[str, float]] = {}
        for agent_id, ticker, quantity in inventory_rows.all():
            by_owner.setdefault(agent_id, {})[ticker] = float(quantity)

        assert by_owner[initiator["agent_id"]]["RAT"] == 6.0
        assert by_owner[initiator["agent_id"]]["DW"] == 9.0
        assert by_owner[target["agent_id"]]["RAT"] == 10.0
        assert by_owner[target["agent_id"]]["DW"] == 7.0

    asyncio.run(_run_seeded_session(scenario))


def test_direct_trade_rejects_cross_region_and_invalid_empty_trade() -> None:
    async def scenario(session: AsyncSession) -> None:
        initiator = await register_agent(session, "Trader Split One", None)
        target = await register_agent(session, "Trader Split Two", None)
        target_model = await session.get(Agent, target["agent_id"])
        assert target_model is not None
        target_model.current_region_id += 1

        try:
            await execute_direct_trade(
                session,
                initiator["agent_id"],
                target["agent_id"],
                offer_items={"RAT": 1},
            )
        except ValueError as exc:
            assert "same region" in str(exc)
        else:
            raise AssertionError("Expected cross-region trade to fail")

        try:
            await execute_direct_trade(session, initiator["agent_id"], target["agent_id"])
        except ValueError as exc:
            assert "at least one item or copper exchange" in str(exc)
        else:
            raise AssertionError("Expected empty trade to fail")

    asyncio.run(_run_seeded_session(scenario))


def test_reputation_modifiers_access_and_shop_prices() -> None:
    async def scenario(session: AsyncSession) -> None:
        agent = await register_agent(session, "Reputation Agent", None)
        agent_model = await session.get(Agent, agent["agent_id"])
        assert agent_model is not None

        assert get_reputation_modifier(100) == 0.9
        assert get_reputation_modifier(0) == 1.0
        assert get_reputation_modifier(-100) == 1.2
        assert check_shop_access(-49.0) is True
        assert check_shop_access(-50.0) is True
        assert check_shop_access(-51.0) is False

        assert await adjust_reputation(session, agent["agent_id"], 250.0) == 100.0
        assert await adjust_reputation(session, agent["agent_id"], -250.0) == -100.0

        session.add(
            NpcShop(
                region_id=agent["current_region_id"],
                shop_type="general_store",
                buy_prices={"RAT": 100},
                sell_prices={"RAT": 80},
                stock={"RAT": 50},
                max_stock={"RAT": 100},
            )
        )
        await session.flush()

        shop = (
            await session.execute(select(NpcShop).order_by(NpcShop.id.desc()).limit(1))
        ).scalar_one()
        neutral = await get_effective_prices(session, shop.id, reputation=0.0, agent_id=agent["agent_id"])
        respected = await get_effective_prices(session, shop.id, reputation=80.0, agent_id=agent["agent_id"])
        notorious = await get_effective_prices(session, shop.id, reputation=-40.0, agent_id=agent["agent_id"])

        assert respected["buy_prices"]["RAT"] < neutral["buy_prices"]["RAT"]
        assert notorious["buy_prices"]["RAT"] > neutral["buy_prices"]["RAT"]

        try:
            await get_effective_prices(session, shop.id, reputation=-60.0, agent_id=agent["agent_id"])
        except ValueError as exc:
            assert "too low" in str(exc)
        else:
            raise AssertionError("Expected banned reputation to block shop access")

    asyncio.run(_run_seeded_session(scenario))


def test_npc_dynamic_pricing_responds_to_stock_pressure_and_clamps() -> None:
    assert calculate_dynamic_price(100, current_stock=100, max_stock=100, elasticity=0.5) == 100
    assert calculate_dynamic_price(100, current_stock=0, max_stock=100, elasticity=0.5) == 150
    assert calculate_dynamic_price(100, current_stock=200, max_stock=100, elasticity=2.0) == 50
    assert calculate_dynamic_price(100, current_stock=0, max_stock=100, elasticity=5.0) == 200
