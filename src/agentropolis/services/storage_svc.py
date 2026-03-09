"""Storage capacity service.

Agent: base 500 units per region
Company: sum of building storage_capacity in that region
Warehouse building adds 1000 units.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models.building import Building
from agentropolis.models.building_type import BuildingType
from agentropolis.models.inventory import Inventory

logger = logging.getLogger(__name__)


async def get_agent_storage(
    session: AsyncSession,
    agent_id: int,
    region_id: int,
) -> dict:
    """Get storage capacity and usage for an agent in a region.

    Returns: {"region_id", "capacity", "used", "available"}
    """
    capacity = settings.AGENT_BASE_STORAGE_PER_REGION

    # TODO: Add Strength skill bonus when skill_svc is available
    # capacity += strength_level * settings.AGENT_CARRY_PER_STRENGTH_LEVEL * 10

    # Calculate used
    result = await session.execute(
        select(func.coalesce(func.sum(Inventory.quantity), 0)).where(
            Inventory.agent_id == agent_id,
            Inventory.region_id == region_id,
        )
    )
    used = result.scalar() or 0

    return {
        "region_id": region_id,
        "owner_type": "agent",
        "capacity": capacity,
        "used": used,
        "available": max(0, capacity - used),
    }


async def get_company_storage(
    session: AsyncSession,
    company_id: int,
    region_id: int,
) -> dict:
    """Get storage capacity and usage for a company in a region.

    Capacity = sum of storage_capacity of all buildings in that region.
    Returns: {"region_id", "capacity", "used", "available"}
    """
    # Sum storage capacity from buildings
    result = await session.execute(
        select(func.coalesce(func.sum(BuildingType.storage_capacity), 0))
        .select_from(Building)
        .join(BuildingType)
        .where(
            Building.company_id == company_id,
            Building.region_id == region_id,
        )
    )
    capacity = result.scalar() or 0

    # Every company gets a minimum base storage
    capacity = max(capacity, settings.AGENT_BASE_STORAGE_PER_REGION)

    # Calculate used
    result = await session.execute(
        select(func.coalesce(func.sum(Inventory.quantity), 0)).where(
            Inventory.company_id == company_id,
            Inventory.region_id == region_id,
        )
    )
    used = result.scalar() or 0

    return {
        "region_id": region_id,
        "owner_type": "company",
        "capacity": capacity,
        "used": used,
        "available": max(0, capacity - used),
    }


async def check_storage_available(
    session: AsyncSession,
    amount: int,
    region_id: int,
    *,
    company_id: int | None = None,
    agent_id: int | None = None,
) -> bool:
    """Check if there is enough storage space for an amount of items.

    Returns: True if space available
    """
    if company_id is not None:
        info = await get_company_storage(session, company_id, region_id)
    elif agent_id is not None:
        info = await get_agent_storage(session, agent_id, region_id)
    else:
        raise ValueError("Must provide company_id or agent_id")

    return info["available"] >= amount
