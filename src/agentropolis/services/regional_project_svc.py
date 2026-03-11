"""Regional infrastructure projects service.

Projects are funded from region treasury (copper + NXC).
When fully funded, they start construction. When complete, they apply effects.

Types:
- ROAD_IMPROVEMENT: -20% travel time for connections from this region
- MARKET_EXPANSION: -1% tax rate
- FORTIFICATION: +20% building durability for buildings in region
- TRADE_HUB: adds NPC shop to region
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models.building import Building
from agentropolis.models.npc_shop import NpcShop
from agentropolis.models.region import Region
from agentropolis.models.region import RegionConnection
from agentropolis.models.regional_project import (
    ProjectStatus,
    ProjectType,
    RegionalProject,
)

logger = logging.getLogger(__name__)

# Project definitions: type → (name, description, copper_cost, nxc_cost, effect_value, duration_seconds)
PROJECT_DEFS: dict[str, dict] = {
    "road_improvement": {
        "name": "Road Improvement",
        "description": "Improves roads, reducing travel time by 20%.",
        "copper_cost": settings.PROJECT_ROAD_IMPROVEMENT_COST,
        "nxc_cost": 0,
        "effect_value": 0.20,
        "duration_seconds": 3600,
    },
    "market_expansion": {
        "name": "Market Expansion",
        "description": "Expands the marketplace, reducing trade tax by 1%.",
        "copper_cost": settings.PROJECT_MARKET_EXPANSION_COST,
        "nxc_cost": 5,
        "effect_value": 0.01,
        "duration_seconds": 7200,
    },
    "fortification": {
        "name": "Fortification",
        "description": "Builds fortifications, increasing building durability by 20%.",
        "copper_cost": settings.PROJECT_FORTIFICATION_COST,
        "nxc_cost": 10,
        "effect_value": 0.20,
        "duration_seconds": 10800,
    },
    "trade_hub": {
        "name": "Trade Hub",
        "description": "Establishes a trade hub with NPC shops.",
        "copper_cost": settings.PROJECT_TRADE_HUB_COST,
        "nxc_cost": 25,
        "effect_value": 1.0,
        "duration_seconds": 14400,
    },
}


def _trade_hub_shop_payload() -> dict:
    return {
        "shop_type": "trade_hub",
        "buy_prices": {"ORE": 8, "CRP": 4, "FE": 22, "BLD": 75},
        "sell_prices": {"RAT": 13, "DW": 11, "BLD": 90, "MCH": 140},
        "stock": {"RAT": 180, "DW": 180, "BLD": 60, "MCH": 10},
        "restock_rate": {"RAT": 10, "DW": 10, "BLD": 3, "MCH": 1},
        "max_stock": {"RAT": 400, "DW": 400, "BLD": 120, "MCH": 25},
        "elasticity": settings.NPC_SHOP_DEFAULT_ELASTICITY,
    }


async def propose_project(
    session: AsyncSession,
    agent_id: int,
    region_id: int,
    project_type: str,
) -> dict:
    """Propose a new regional project.

    Returns: {"project_id", "project_type", "copper_cost", "nxc_cost", "status"}
    Raises: ValueError if invalid type or project already in progress
    """
    try:
        pt = ProjectType(project_type)
    except ValueError as err:
        raise ValueError(f"Invalid project type: {project_type}") from err

    definition = PROJECT_DEFS.get(project_type)
    if definition is None:
        raise ValueError(f"No definition for project type: {project_type}")

    # Check no active project of same type in region
    result = await session.execute(
        select(RegionalProject).where(
            RegionalProject.region_id == region_id,
            RegionalProject.project_type == pt,
            RegionalProject.status.in_([ProjectStatus.FUNDING, ProjectStatus.IN_PROGRESS]),
        )
    )
    if result.scalar_one_or_none() is not None:
        raise ValueError(f"Region {region_id} already has an active {project_type} project")

    # Verify region exists
    result = await session.execute(select(Region).where(Region.id == region_id))
    if result.scalar_one_or_none() is None:
        raise ValueError(f"Region {region_id} not found")

    project = RegionalProject(
        region_id=region_id,
        project_type=pt,
        name=definition["name"],
        description=definition["description"],
        copper_cost=definition["copper_cost"],
        nxc_cost=definition["nxc_cost"],
        effect_value=definition["effect_value"],
        duration_seconds=definition["duration_seconds"],
        initiated_by_agent_id=agent_id,
    )
    session.add(project)
    await session.flush()

    return {
        "project_id": project.id,
        "project_type": project_type,
        "name": definition["name"],
        "copper_cost": definition["copper_cost"],
        "nxc_cost": definition["nxc_cost"],
        "status": project.status.value,
    }


async def fund_project(
    session: AsyncSession,
    project_id: int,
    copper_amount: int = 0,
    nxc_amount: int = 0,
) -> dict:
    """Fund a project from region treasury.

    If fully funded, starts construction automatically.
    Returns: {"project_id", "copper_funded", "nxc_funded", "status"}
    """
    result = await session.execute(
        select(RegionalProject).where(RegionalProject.id == project_id).with_for_update()
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    if project.status != ProjectStatus.FUNDING:
        raise ValueError(f"Project {project_id} is not in FUNDING state")

    # Deduct from region treasury
    result = await session.execute(
        select(Region).where(Region.id == project.region_id).with_for_update()
    )
    region = result.scalar_one()

    actual_copper = min(copper_amount, region.treasury, project.copper_cost - project.copper_funded)
    if actual_copper > 0:
        region.treasury -= actual_copper
        project.copper_funded += actual_copper

    # NXC funding would require inventory operations - simplified here
    if nxc_amount > 0:
        actual_nxc = min(nxc_amount, project.nxc_cost - project.nxc_funded)
        project.nxc_funded += actual_nxc

    # Check if fully funded
    if project.copper_funded >= project.copper_cost and project.nxc_funded >= project.nxc_cost:
        project.status = ProjectStatus.IN_PROGRESS
        project.started_at = datetime.now(UTC)

    await session.flush()

    return {
        "project_id": project_id,
        "copper_funded": project.copper_funded,
        "nxc_funded": project.nxc_funded,
        "copper_remaining": project.copper_cost - project.copper_funded,
        "nxc_remaining": project.nxc_cost - project.nxc_funded,
        "status": project.status.value,
    }


async def settle_project_completions(
    session: AsyncSession,
    now: datetime | None = None,
) -> dict:
    """Check and complete projects whose construction time has elapsed. Housekeeping.

    Returns: {"completed_count", "projects": [...]}
    """
    if now is None:
        now = datetime.now(UTC)

    result = await session.execute(
        select(RegionalProject)
        .where(RegionalProject.status == ProjectStatus.IN_PROGRESS)
        .with_for_update()
    )
    projects = list(result.scalars().all())

    completed = []
    for project in projects:
        if project.started_at is None:
            continue

        elapsed = (now - project.started_at).total_seconds()
        if elapsed >= project.duration_seconds:
            project.status = ProjectStatus.COMPLETED
            project.completed_at = now

            # Apply effects
            await _apply_project_effect(session, project)
            completed.append({
                "project_id": project.id,
                "project_type": project.project_type.value,
                "region_id": project.region_id,
            })

    await session.flush()

    return {
        "completed_count": len(completed),
        "projects": completed,
    }


async def _apply_project_effect(session: AsyncSession, project: RegionalProject) -> None:
    """Apply the mechanical effect of a completed project."""
    result = await session.execute(
        select(Region).where(Region.id == project.region_id).with_for_update()
    )
    region = result.scalar_one()

    pt = project.project_type.value if hasattr(project.project_type, 'value') else str(project.project_type)

    if pt == "market_expansion":
        # Reduce tax rate
        region.tax_rate = max(0.0, region.tax_rate - project.effect_value)
    elif pt == "road_improvement":
        result = await session.execute(
            select(RegionConnection)
            .where(RegionConnection.from_region_id == project.region_id)
            .with_for_update()
        )
        for connection in result.scalars().all():
            connection.travel_time_seconds = max(
                1,
                int(round(connection.travel_time_seconds * (1.0 - project.effect_value))),
            )
    elif pt == "fortification":
        result = await session.execute(
            select(Building).where(Building.region_id == project.region_id).with_for_update()
        )
        multiplier = 1.0 + project.effect_value
        for building in result.scalars().all():
            building.max_durability = round(float(building.max_durability) * multiplier, 3)
            building.durability = min(
                float(building.max_durability),
                round(float(building.durability) * multiplier, 3),
            )
    elif pt == "trade_hub":
        result = await session.execute(
            select(NpcShop)
            .where(
                NpcShop.region_id == project.region_id,
                NpcShop.shop_type == "trade_hub",
            )
            .with_for_update()
        )
        if result.scalar_one_or_none() is None:
            session.add(NpcShop(region_id=project.region_id, **_trade_hub_shop_payload()))

    logger.info(
        "Project %d (%s) completed in region %d",
        project.id, pt, project.region_id,
    )


async def get_region_projects(
    session: AsyncSession,
    region_id: int,
) -> list[dict]:
    """Get all projects for a region.

    Returns: [{"project_id", "project_type", "status", ...}]
    """
    result = await session.execute(
        select(RegionalProject)
        .where(RegionalProject.region_id == region_id)
        .order_by(RegionalProject.created_at.desc())
    )
    projects = result.scalars().all()

    return [
        {
            "project_id": p.id,
            "region_id": p.region_id,
            "project_type": p.project_type.value if hasattr(p.project_type, 'value') else str(p.project_type),
            "name": p.name,
            "description": p.description,
            "copper_cost": p.copper_cost,
            "nxc_cost": p.nxc_cost,
            "copper_funded": p.copper_funded,
            "nxc_funded": p.nxc_funded,
            "effect_value": p.effect_value,
            "status": p.status.value if hasattr(p.status, 'value') else str(p.status),
            "started_at": p.started_at.isoformat() if p.started_at else None,
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
        }
        for p in projects
    ]
