"""Notification and perishable-decay tests for issues #41 and #42."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import Base, Inventory, Notification, Resource
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.company_svc import register_company
from agentropolis.services.decay_svc import settle_inventory_decay
from agentropolis.services.game_engine import run_housekeeping_sweep
from agentropolis.services.notification_svc import (
    get_notifications,
    mark_all_read,
    mark_read,
    notify,
    prune_old_notifications,
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


def test_notification_read_and_prune_flow() -> None:
    async def scenario(session: AsyncSession) -> None:
        agent = await register_agent(session, "Notification Agent", None)

        first_id = await notify(session, agent["agent_id"], "general", "First", "hello")
        second_id = await notify(session, agent["agent_id"], "general", "Second", "world")

        payload = await get_notifications(session, agent["agent_id"])
        assert payload["unread_count"] == 2
        assert [item["notification_id"] for item in payload["notifications"]] == [second_id, first_id]

        assert await mark_read(session, agent["agent_id"], first_id) is True
        unread_only = await get_notifications(session, agent["agent_id"], unread_only=True)
        assert unread_only["unread_count"] == 1

        assert await mark_all_read(session, agent["agent_id"]) == 1
        assert (await get_notifications(session, agent["agent_id"]))["unread_count"] == 0

        old_notification = await session.get(Notification, first_id)
        assert old_notification is not None
        old_notification.created_at = datetime.now(UTC) - timedelta(days=60)

        pruned = await prune_old_notifications(session, now=datetime.now(UTC))
        assert pruned == 1

    asyncio.run(_run_seeded_session(scenario))


def test_perishable_decay_respects_reserved_quantity() -> None:
    async def scenario(session: AsyncSession) -> None:
        founder = await register_agent(session, "Decay Founder", None)
        company = await register_company(
            session,
            "Decay Works",
            founder_agent_id=founder["agent_id"],
        )

        resource = (
            await session.execute(select(Resource).where(Resource.ticker == "RAT"))
        ).scalar_one()
        inventory = (
            await session.execute(
                select(Inventory)
                .where(
                    Inventory.company_id == company["company_id"],
                    Inventory.resource_id == resource.id,
                )
            )
        ).scalar_one()

        inventory.quantity = 20
        inventory.reserved = 19
        inventory.last_decay_at = datetime.now(UTC) - timedelta(hours=2)
        resource.decay_rate_per_hour = 1.0

        result = await settle_inventory_decay(session, inventory.id, now=datetime.now(UTC))
        assert result["resource_ticker"] == "RAT"
        assert result["qty_lost"] == 1
        assert float(inventory.quantity) == 19.0

    asyncio.run(_run_seeded_session(scenario))


def test_housekeeping_prunes_notifications_and_settles_decay() -> None:
    async def scenario(session: AsyncSession) -> None:
        founder = await register_agent(session, "Maintenance Founder", None)
        company = await register_company(
            session,
            "Maintenance Works",
            founder_agent_id=founder["agent_id"],
        )

        notification_id = await notify(
            session,
            founder["agent_id"],
            "general",
            "Old Notification",
            "to prune",
        )
        notification = await session.get(Notification, notification_id)
        assert notification is not None
        notification.created_at = datetime.now(UTC) - timedelta(days=45)

        resource = (
            await session.execute(select(Resource).where(Resource.ticker == "RAT"))
        ).scalar_one()
        inventory = (
            await session.execute(
                select(Inventory)
                .where(
                    Inventory.company_id == company["company_id"],
                    Inventory.resource_id == resource.id,
                )
            )
        ).scalar_one()
        inventory.quantity = 40
        inventory.reserved = 0
        inventory.last_decay_at = datetime.now(UTC) - timedelta(hours=5)
        resource.decay_rate_per_hour = 0.1

        summary = await run_housekeeping_sweep(session, now=datetime.now(UTC))
        assert summary["admin"]["notifications_pruned"] == 1
        assert summary["admin"]["perishable_decay"]["items_processed"] >= 1
        assert summary["admin"]["perishable_decay"]["total_qty_lost"] >= 1

    asyncio.run(_run_seeded_session(scenario))
