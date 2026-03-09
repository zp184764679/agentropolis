"""Seed data for the current scaffold and minimum target-world baseline.

This defines the game's economic balance. Changes here affect all gameplay.
The seed function is idempotent - safe to run multiple times.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models import (
    BuildingType,
    GameState,
    NexusCrystalState,
    Recipe,
    Resource,
    ResourceCategory,
    SkillCategory,
    SkillDefinition,
)

# ─── Resource Definitions ────────────────────────────────────────────────────

RESOURCES = [
    {"ticker": "H2O", "name": "Water", "category": ResourceCategory.RAW, "base_price": 5.0, "description": "Extracted from underground aquifers. Essential for farming and purification."},
    {"ticker": "ORE", "name": "Iron Ore", "category": ResourceCategory.RAW, "base_price": 8.0, "description": "Raw iron ore mined from deposits. Must be smelted before use."},
    {"ticker": "C", "name": "Carbon", "category": ResourceCategory.RAW, "base_price": 6.0, "description": "Organic carbon compound. Used in smelting and construction."},
    {"ticker": "CRP", "name": "Crops", "category": ResourceCategory.RAW, "base_price": 4.0, "description": "Agricultural produce grown in farms. Raw ingredient for rations."},
    {"ticker": "RAT", "name": "Rations", "category": ResourceCategory.CONSUMABLE, "base_price": 12.0, "description": "Processed food rations. Workers consume these every tick."},
    {"ticker": "DW", "name": "Drinking Water", "category": ResourceCategory.CONSUMABLE, "base_price": 10.0, "description": "Purified water safe for consumption. Workers need this every tick."},
    {"ticker": "FE", "name": "Iron", "category": ResourceCategory.REFINED, "base_price": 25.0, "description": "Refined iron ingots. Base material for steel and machinery."},
    {"ticker": "STL", "name": "Steel", "category": ResourceCategory.REFINED, "base_price": 50.0, "description": "High-grade steel alloy. Required for advanced manufacturing."},
    {"ticker": "MCH", "name": "Machinery Parts", "category": ResourceCategory.COMPONENT, "base_price": 120.0, "description": "Precision mechanical components. High-value trade good."},
    {"ticker": "BLD", "name": "Building Materials", "category": ResourceCategory.COMPONENT, "base_price": 80.0, "description": "Prefabricated construction materials. Used to build new facilities."},
]

# ─── Building Type Definitions ───────────────────────────────────────────────

BUILDING_TYPES = [
    {"name": "extractor", "display_name": "Resource Extractor", "cost_credits": 500, "cost_materials": {}, "max_workers": 10, "storage_capacity": 250, "description": "Extracts raw resources from the ground."},
    {"name": "farm", "display_name": "Farm", "cost_credits": 400, "cost_materials": {}, "max_workers": 8, "storage_capacity": 200, "description": "Grows crops using water."},
    {"name": "food_processor", "display_name": "Food Processor", "cost_credits": 600, "cost_materials": {}, "max_workers": 6, "storage_capacity": 200, "description": "Converts crops and water into rations."},
    {"name": "water_purifier", "display_name": "Water Purifier", "cost_credits": 500, "cost_materials": {}, "max_workers": 5, "storage_capacity": 200, "description": "Purifies raw water into drinking water."},
    {"name": "smelter", "display_name": "Smelter", "cost_credits": 1200, "cost_materials": {"BLD": 5}, "max_workers": 12, "storage_capacity": 350, "description": "Smelts ore and carbon into iron."},
    {"name": "foundry", "display_name": "Foundry", "cost_credits": 1800, "cost_materials": {"BLD": 8}, "max_workers": 15, "storage_capacity": 400, "description": "Forges iron and carbon into steel."},
    {"name": "assembly_plant", "display_name": "Assembly Plant", "cost_credits": 2500, "cost_materials": {"BLD": 12, "MCH": 2}, "max_workers": 20, "storage_capacity": 500, "description": "Assembles iron and steel into machinery parts."},
    {"name": "construction_yard", "display_name": "Construction Yard", "cost_credits": 1500, "cost_materials": {"BLD": 5}, "max_workers": 10, "storage_capacity": 450, "description": "Produces building materials from steel and carbon."},
    {"name": "warehouse", "display_name": "Warehouse", "cost_credits": 900, "cost_materials": {"BLD": 3}, "max_workers": 4, "storage_capacity": 1000, "description": "Adds large regional storage capacity."},
    {"name": "nexus_refinery", "display_name": "Nexus Refinery", "cost_credits": 5000, "cost_materials": {"BLD": 12, "MCH": 4, "STL": 6}, "max_workers": 6, "storage_capacity": 300, "description": "Processes Nexus Crystal cycles in the target-world economy."},
]

# ─── Recipe Definitions ──────────────────────────────────────────────────────
# building_type_name → list of recipes

RECIPES = [
    # Extractors - no input, produce raw resources
    {"building_type": "extractor", "name": "Extract Water", "inputs": {}, "outputs": {"H2O": 10}, "duration_ticks": 1, "description": "Pump groundwater."},
    {"building_type": "extractor", "name": "Mine Iron Ore", "inputs": {}, "outputs": {"ORE": 8}, "duration_ticks": 1, "description": "Mine iron ore deposits."},
    {"building_type": "extractor", "name": "Harvest Carbon", "inputs": {}, "outputs": {"C": 6}, "duration_ticks": 1, "description": "Collect organic carbon."},
    # Farm
    {"building_type": "farm", "name": "Grow Crops", "inputs": {"H2O": 4}, "outputs": {"CRP": 12}, "duration_ticks": 2, "description": "Irrigate and grow crops."},
    # Food processor
    {"building_type": "food_processor", "name": "Produce Rations", "inputs": {"CRP": 4, "H2O": 2}, "outputs": {"RAT": 10}, "duration_ticks": 1, "description": "Process crops into rations."},
    # Water purifier
    {"building_type": "water_purifier", "name": "Purify Water", "inputs": {"H2O": 6}, "outputs": {"DW": 8}, "duration_ticks": 1, "description": "Filter and purify water."},
    # Smelter
    {"building_type": "smelter", "name": "Smelt Iron", "inputs": {"ORE": 6, "C": 2}, "outputs": {"FE": 4}, "duration_ticks": 2, "description": "Smelt ore into iron ingots."},
    # Foundry
    {"building_type": "foundry", "name": "Forge Steel", "inputs": {"FE": 4, "C": 2}, "outputs": {"STL": 3}, "duration_ticks": 2, "description": "Forge iron and carbon into steel."},
    # Assembly plant
    {"building_type": "assembly_plant", "name": "Assemble Machinery", "inputs": {"FE": 2, "STL": 1}, "outputs": {"MCH": 2}, "duration_ticks": 3, "description": "Assemble precision machinery."},
    # Construction yard
    {"building_type": "construction_yard", "name": "Make Building Materials", "inputs": {"STL": 2, "C": 3}, "outputs": {"BLD": 4}, "duration_ticks": 2, "description": "Fabricate building materials."},
]

# ─── Starter Kit (given to each new company) ─────────────────────────────────

STARTER_BUILDINGS = ["extractor", "farm", "food_processor"]
STARTER_INVENTORY = {"H2O": 100, "CRP": 50, "RAT": 200, "DW": 150}

SKILL_DEFINITIONS = [
    {"name": "Mining", "category": SkillCategory.GATHERING, "description": "Improves extraction output.", "prerequisites": {}, "xp_per_level": {"base": 100}},
    {"name": "Woodcutting", "category": SkillCategory.GATHERING, "description": "Improves lumber and gathering efficiency.", "prerequisites": {}, "xp_per_level": {"base": 100}},
    {"name": "Farming", "category": SkillCategory.GATHERING, "description": "Improves crop output.", "prerequisites": {}, "xp_per_level": {"base": 100}},
    {"name": "Smithing", "category": SkillCategory.CRAFTING, "description": "Improves smelting and heavy industry.", "prerequisites": {}, "xp_per_level": {"base": 120}},
    {"name": "Engineering", "category": SkillCategory.CRAFTING, "description": "Improves machinery and building upkeep.", "prerequisites": {}, "xp_per_level": {"base": 120}},
    {"name": "Alchemy", "category": SkillCategory.CRAFTING, "description": "Improves specialty processing.", "prerequisites": {}, "xp_per_level": {"base": 120}},
    {"name": "Trading", "category": SkillCategory.COMMERCE, "description": "Improves trade execution quality.", "prerequisites": {}, "xp_per_level": {"base": 110}},
    {"name": "Logistics", "category": SkillCategory.COMMERCE, "description": "Improves transport and storage efficiency.", "prerequisites": {}, "xp_per_level": {"base": 110}},
    {"name": "Negotiation", "category": SkillCategory.SOCIAL, "description": "Improves contract and diplomacy outcomes.", "prerequisites": {}, "xp_per_level": {"base": 110}},
    {"name": "Diplomacy", "category": SkillCategory.SOCIAL, "description": "Improves trust and treaty outcomes.", "prerequisites": {}, "xp_per_level": {"base": 110}},
    {"name": "Management", "category": SkillCategory.SOCIAL, "description": "Improves guild and workforce control.", "prerequisites": {}, "xp_per_level": {"base": 110}},
    {"name": "Melee", "category": SkillCategory.COMBAT, "description": "Primary close-combat skill.", "prerequisites": {}, "xp_per_level": {"base": 130}},
    {"name": "Tactics", "category": SkillCategory.COMBAT, "description": "Improves attack planning and defense.", "prerequisites": {}, "xp_per_level": {"base": 130}},
    {"name": "Fortification", "category": SkillCategory.COMBAT, "description": "Improves defense and building resilience.", "prerequisites": {}, "xp_per_level": {"base": 130}},
    {"name": "Command", "category": SkillCategory.SOCIAL, "description": "Improves leadership-driven bonuses.", "prerequisites": {}, "xp_per_level": {"base": 120}},
]


async def seed_game_data(session: AsyncSession) -> dict:
    """Seed resources, building types, and recipes. Idempotent.

    Returns:
        Summary dict with counts of created entities.
    """
    created = {
        "resources": 0,
        "building_types": 0,
        "recipes": 0,
        "skill_definitions": 0,
        "game_state": False,
        "nexus_state": False,
    }

    # Seed resources
    for rdata in RESOURCES:
        exists = await session.execute(
            select(Resource).where(Resource.ticker == rdata["ticker"])
        )
        if exists.scalar_one_or_none() is None:
            session.add(Resource(**rdata))
            created["resources"] += 1

    await session.flush()

    # Seed building types
    bt_map: dict[str, BuildingType] = {}
    for btdata in BUILDING_TYPES:
        result = await session.execute(
            select(BuildingType).where(BuildingType.name == btdata["name"])
        )
        bt = result.scalar_one_or_none()
        if bt is None:
            bt = BuildingType(**btdata)
            session.add(bt)
            created["building_types"] += 1
        bt_map[bt.name] = bt

    await session.flush()

    # Seed recipes
    for rdata in RECIPES:
        bt_name = rdata.pop("building_type")
        bt = bt_map.get(bt_name)
        if bt is None:
            result = await session.execute(
                select(BuildingType).where(BuildingType.name == bt_name)
            )
            bt = result.scalar_one_or_none()
        if bt is None:
            continue

        exists = await session.execute(
            select(Recipe).where(Recipe.name == rdata["name"], Recipe.building_type_id == bt.id)
        )
        if exists.scalar_one_or_none() is None:
            session.add(Recipe(building_type_id=bt.id, **rdata))
            created["recipes"] += 1
        rdata["building_type"] = bt_name  # restore for idempotency

    # Seed game state singleton
    result = await session.execute(select(GameState).where(GameState.id == 1))
    if result.scalar_one_or_none() is None:
        session.add(GameState(
            id=1,
            current_tick=0,
            tick_interval_seconds=settings.TICK_INTERVAL_SECONDS,
            is_running=False,
        ))
        created["game_state"] = True

    # Seed target skill catalog
    for sdata in SKILL_DEFINITIONS:
        result = await session.execute(
            select(SkillDefinition).where(SkillDefinition.name == sdata["name"])
        )
        if result.scalar_one_or_none() is None:
            session.add(SkillDefinition(**sdata))
            created["skill_definitions"] += 1

    # Seed NXC singleton for target-world services
    result = await session.execute(select(NexusCrystalState).where(NexusCrystalState.id == 1))
    if result.scalar_one_or_none() is None:
        session.add(NexusCrystalState(id=1))
        created["nexus_state"] = True

    await session.commit()
    return created
