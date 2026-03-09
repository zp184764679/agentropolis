"""World seed service - minimum regional world bootstrap for agent-auth flows."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models import NpcShop, Region, RegionConnection, RegionType, SafetyTier

WORLD_REGIONS = [
    {
        "name": "Nexus Capital",
        "safety_tier": SafetyTier.CORE,
        "region_type": RegionType.CAPITAL,
        "price_coefficient": 1.00,
        "tax_rate": 0.05,
        "treasury": 1_000_000,
        "resource_specializations": {"service": 1.2},
        "description": "Safe capital hub and initial bootstrap region.",
    },
    {
        "name": "Iron Vale",
        "safety_tier": SafetyTier.RESOURCE,
        "region_type": RegionType.TOWN,
        "price_coefficient": 0.95,
        "tax_rate": 0.06,
        "treasury": 250_000,
        "resource_specializations": {"ORE": 1.3, "FE": 1.1},
        "description": "Mining-heavy valley with ore specialization.",
    },
    {
        "name": "Greenreach",
        "safety_tier": SafetyTier.BORDER,
        "region_type": RegionType.TOWN,
        "price_coefficient": 0.98,
        "tax_rate": 0.04,
        "treasury": 200_000,
        "resource_specializations": {"CRP": 1.3, "H2O": 1.2},
        "description": "Agricultural region and food logistics hub.",
    },
    {
        "name": "Frontier Gate",
        "safety_tier": SafetyTier.BORDER,
        "region_type": RegionType.OUTPOST,
        "price_coefficient": 1.08,
        "tax_rate": 0.07,
        "treasury": 150_000,
        "resource_specializations": {"BLD": 1.2, "STL": 1.1},
        "description": "Volatile frontier staging area.",
    },
]

WORLD_CONNECTIONS = [
    ("Nexus Capital", "Iron Vale", 300, "road", False, 10),
    ("Nexus Capital", "Greenreach", 240, "road", False, 5),
    ("Iron Vale", "Frontier Gate", 420, "trail", False, 35),
    ("Greenreach", "Frontier Gate", 360, "road", False, 25),
]

WORLD_SHOPS = {
    "Nexus Capital": {
        "shop_type": "general",
        "buy_prices": {"ORE": 7, "CRP": 4, "BLD": 70},
        "sell_prices": {"RAT": 14, "DW": 12, "BLD": 95},
        "stock": {"RAT": 500, "DW": 500, "BLD": 120},
        "restock_rate": {"RAT": 20, "DW": 20, "BLD": 5},
        "max_stock": {"RAT": 1000, "DW": 1000, "BLD": 200},
    },
    "Iron Vale": {
        "shop_type": "industrial",
        "buy_prices": {"ORE": 9, "C": 5, "FE": 24},
        "sell_prices": {"DW": 13, "RAT": 15},
        "stock": {"DW": 120, "RAT": 120},
        "restock_rate": {"DW": 10, "RAT": 10},
        "max_stock": {"DW": 300, "RAT": 300},
    },
    "Greenreach": {
        "shop_type": "agri",
        "buy_prices": {"CRP": 5, "H2O": 4},
        "sell_prices": {"RAT": 13, "DW": 11},
        "stock": {"RAT": 220, "DW": 220},
        "restock_rate": {"RAT": 12, "DW": 12},
        "max_stock": {"RAT": 400, "DW": 400},
    },
}


async def seed_world(session: AsyncSession, world_seed: str = "default") -> dict:
    """Seed the minimum world graph required by agent/world services.

    Returns: {"world_seed", "regions_created", "connections_created", "shops_created"}
    """
    created = {
        "world_seed": world_seed,
        "regions_created": 0,
        "connections_created": 0,
        "shops_created": 0,
    }

    region_map: dict[str, Region] = {}
    for region_data in WORLD_REGIONS:
        result = await session.execute(
            select(Region).where(Region.name == region_data["name"])
        )
        region = result.scalar_one_or_none()
        if region is None:
            region = Region(**region_data)
            session.add(region)
            created["regions_created"] += 1
            await session.flush()
        region_map[region.name] = region

    for from_name, to_name, travel_time, terrain, is_portal, danger in WORLD_CONNECTIONS:
        from_region = region_map[from_name]
        to_region = region_map[to_name]
        for origin, destination in ((from_region, to_region), (to_region, from_region)):
            result = await session.execute(
                select(RegionConnection).where(
                    RegionConnection.from_region_id == origin.id,
                    RegionConnection.to_region_id == destination.id,
                )
            )
            if result.scalar_one_or_none() is None:
                session.add(
                    RegionConnection(
                        from_region_id=origin.id,
                        to_region_id=destination.id,
                        travel_time_seconds=travel_time,
                        terrain_type=terrain,
                        is_portal=is_portal,
                        danger_level=danger,
                    )
                )
                created["connections_created"] += 1

    for region_name, shop_data in WORLD_SHOPS.items():
        region = region_map[region_name]
        result = await session.execute(
            select(NpcShop).where(
                NpcShop.region_id == region.id,
                NpcShop.shop_type == shop_data["shop_type"],
            )
        )
        if result.scalar_one_or_none() is None:
            session.add(NpcShop(region_id=region.id, **shop_data))
            created["shops_created"] += 1

    await session.commit()
    return created
