"""Direct trade service - agent-to-agent item/copper exchange.

Two agents in the same region can atomically swap items and/or copper.
Both must be alive and in the same region.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models.agent import Agent
from agentropolis.models.inventory import Inventory
from agentropolis.models.resource import Resource

logger = logging.getLogger(__name__)


async def execute_direct_trade(
    session: AsyncSession,
    initiator_agent_id: int,
    target_agent_id: int,
    offer_items: dict[str, int] | None = None,
    request_items: dict[str, int] | None = None,
    offer_copper: int = 0,
    request_copper: int = 0,
) -> dict:
    """Execute an atomic direct trade between two agents in the same region.

    offer_items: items initiator gives to target {ticker: qty}
    request_items: items target gives to initiator {ticker: qty}
    offer_copper: copper initiator pays to target
    request_copper: copper target pays to initiator

    Returns: {"trade_id", "initiator_agent_id", "target_agent_id", "items_exchanged", "copper_exchanged"}
    Raises: ValueError on validation failure
    """
    if offer_items is None:
        offer_items = {}
    if request_items is None:
        request_items = {}

    if not offer_items and not request_items and offer_copper == 0 and request_copper == 0:
        raise ValueError("Trade must include at least one item or copper exchange")

    if initiator_agent_id == target_agent_id:
        raise ValueError("Cannot trade with yourself")

    # Lock both agents (ordered by ID to prevent deadlocks)
    agent_ids = sorted([initiator_agent_id, target_agent_id])
    agents = {}
    for aid in agent_ids:
        result = await session.execute(
            select(Agent).where(Agent.id == aid).with_for_update()
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise ValueError(f"Agent {aid} not found")
        if not agent.is_alive:
            raise ValueError(f"Agent {aid} is dead")
        agents[aid] = agent

    initiator = agents[initiator_agent_id]
    target = agents[target_agent_id]

    # Check same region
    if initiator.current_region_id != target.current_region_id:
        raise ValueError("Agents must be in the same region for direct trade")

    region_id = initiator.current_region_id

    # Validate copper balances
    if offer_copper > 0 and initiator.personal_balance < offer_copper:
        raise ValueError(f"Initiator insufficient copper: need {offer_copper}, have {initiator.personal_balance}")
    if request_copper > 0 and target.personal_balance < request_copper:
        raise ValueError(f"Target insufficient copper: need {request_copper}, have {target.personal_balance}")

    # Resolve resource tickers to IDs
    all_tickers = set(list(offer_items.keys()) + list(request_items.keys()))
    resource_map: dict[str, Resource] = {}
    for ticker in all_tickers:
        result = await session.execute(
            select(Resource).where(Resource.ticker == ticker)
        )
        resource = result.scalar_one_or_none()
        if resource is None:
            raise ValueError(f"Resource '{ticker}' not found")
        resource_map[ticker] = resource

    # Validate initiator has offered items
    for ticker, qty in offer_items.items():
        if qty <= 0:
            raise ValueError(f"Invalid quantity for {ticker}: {qty}")
        result = await session.execute(
            select(Inventory).where(
                Inventory.agent_id == initiator_agent_id,
                Inventory.resource_id == resource_map[ticker].id,
                Inventory.region_id == region_id,
            ).with_for_update()
        )
        inv = result.scalar_one_or_none()
        if inv is None or inv.available < qty:
            available = inv.available if inv else 0
            raise ValueError(f"Initiator insufficient {ticker}: need {qty}, have {available}")

    # Validate target has requested items
    for ticker, qty in request_items.items():
        if qty <= 0:
            raise ValueError(f"Invalid quantity for {ticker}: {qty}")
        result = await session.execute(
            select(Inventory).where(
                Inventory.agent_id == target_agent_id,
                Inventory.resource_id == resource_map[ticker].id,
                Inventory.region_id == region_id,
            ).with_for_update()
        )
        inv = result.scalar_one_or_none()
        if inv is None or inv.available < qty:
            available = inv.available if inv else 0
            raise ValueError(f"Target insufficient {ticker}: need {qty}, have {available}")

    # Execute transfers - items from initiator to target
    for ticker, qty in offer_items.items():
        rid = resource_map[ticker].id
        # Remove from initiator
        result = await session.execute(
            select(Inventory).where(
                Inventory.agent_id == initiator_agent_id,
                Inventory.resource_id == rid,
                Inventory.region_id == region_id,
            ).with_for_update()
        )
        inv = result.scalar_one()
        inv.quantity -= qty

        # Add to target (create if not exists)
        result = await session.execute(
            select(Inventory).where(
                Inventory.agent_id == target_agent_id,
                Inventory.resource_id == rid,
                Inventory.region_id == region_id,
            ).with_for_update()
        )
        target_inv = result.scalar_one_or_none()
        if target_inv is None:
            target_inv = Inventory(
                agent_id=target_agent_id,
                resource_id=rid,
                region_id=region_id,
                quantity=qty,
                reserved=0,
            )
            session.add(target_inv)
        else:
            target_inv.quantity += qty

    # Execute transfers - items from target to initiator
    for ticker, qty in request_items.items():
        rid = resource_map[ticker].id
        # Remove from target
        result = await session.execute(
            select(Inventory).where(
                Inventory.agent_id == target_agent_id,
                Inventory.resource_id == rid,
                Inventory.region_id == region_id,
            ).with_for_update()
        )
        inv = result.scalar_one()
        inv.quantity -= qty

        # Add to initiator
        result = await session.execute(
            select(Inventory).where(
                Inventory.agent_id == initiator_agent_id,
                Inventory.resource_id == rid,
                Inventory.region_id == region_id,
            ).with_for_update()
        )
        init_inv = result.scalar_one_or_none()
        if init_inv is None:
            init_inv = Inventory(
                agent_id=initiator_agent_id,
                resource_id=rid,
                region_id=region_id,
                quantity=qty,
                reserved=0,
            )
            session.add(init_inv)
        else:
            init_inv.quantity += qty

    # Transfer copper
    if offer_copper > 0:
        initiator.personal_balance -= offer_copper
        target.personal_balance += offer_copper
    if request_copper > 0:
        target.personal_balance -= request_copper
        initiator.personal_balance += request_copper

    await session.flush()

    net_copper = offer_copper - request_copper
    return {
        "trade_id": str(uuid.uuid4()),
        "initiator_agent_id": initiator_agent_id,
        "target_agent_id": target_agent_id,
        "items_exchanged": {
            "offered": offer_items,
            "received": request_items,
        },
        "copper_exchanged": net_copper,
    }
