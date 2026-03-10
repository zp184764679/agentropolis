"""Migration-phase production service for company-owned buildings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agentropolis.config import settings
from agentropolis.models import Building, BuildingStatus, BuildingType, Company, Recipe
from agentropolis.services.company_svc import debit_balance, get_agent_company
from agentropolis.services.inventory_svc import (
    add_resource,
    get_resource_quantity_in_region,
    remove_resource,
)


def _coerce_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def _duration_seconds(recipe: Recipe) -> int:
    return max(int(recipe.duration_ticks) * int(settings.TICK_INTERVAL_SECONDS), 1)


async def _get_company_for_validation(session: AsyncSession, company_id: int) -> Company:
    result = await session.execute(
        select(Company).where(Company.id == company_id).with_for_update()
    )
    company = result.scalar_one_or_none()
    if company is None:
        raise ValueError(f"Company {company_id} not found")
    if not company.is_active:
        raise ValueError(f"Company {company_id} is inactive")
    if company.region_id is None:
        raise ValueError(f"Company {company_id} does not have an operating region")
    return company


async def _get_building_for_update(
    session: AsyncSession,
    *,
    company_id: int,
    building_id: int,
) -> Building:
    result = await session.execute(
        select(Building)
        .where(Building.id == building_id, Building.company_id == company_id)
        .with_for_update()
    )
    building = result.scalar_one_or_none()
    if building is None:
        raise ValueError(f"Building {building_id} not found for company {company_id}")
    return building


async def _get_recipe_for_building(
    session: AsyncSession,
    *,
    recipe_id: int,
    building_type_id: int,
) -> Recipe:
    result = await session.execute(
        select(Recipe).where(
            Recipe.id == recipe_id,
            Recipe.building_type_id == building_type_id,
        )
    )
    recipe = result.scalar_one_or_none()
    if recipe is None:
        raise ValueError(f"Recipe {recipe_id} is not valid for this building")
    return recipe


async def _settle_building(
    session: AsyncSession,
    building: Building,
    *,
    now: datetime,
) -> dict:
    if building.status != BuildingStatus.PRODUCING or building.active_recipe_id is None:
        return {"cycles_completed": 0, "status": building.status.value}

    recipe = (
        await session.execute(select(Recipe).where(Recipe.id == building.active_recipe_id))
    ).scalar_one_or_none()
    if recipe is None:
        building.status = BuildingStatus.IDLE
        building.active_recipe_id = None
        building.production_progress = 0
        building.last_production_at = now
        await session.flush()
        return {"cycles_completed": 0, "status": building.status.value}

    last_production_at = building.last_production_at or building.updated_at
    if last_production_at is None:
        last_production_at = now
    if last_production_at.tzinfo is None:
        last_production_at = last_production_at.replace(tzinfo=UTC)

    cycle_seconds = _duration_seconds(recipe)
    elapsed_seconds = max(0.0, (now - last_production_at).total_seconds())
    completed_cycles = int(elapsed_seconds // cycle_seconds)
    progress_seconds = int(elapsed_seconds % cycle_seconds)
    if completed_cycles <= 0:
        building.production_progress = progress_seconds
        await session.flush()
        return {
            "cycles_completed": 0,
            "status": building.status.value,
            "active_recipe": recipe.name,
            "progress_seconds": progress_seconds,
        }

    outputs: dict[str, float] = {}
    completed = 0
    company = await _get_company_for_validation(session, building.company_id)

    for _ in range(completed_cycles):
        try:
            for ticker, quantity in (recipe.inputs or {}).items():
                await remove_resource(
                    session,
                    company.id,
                    ticker,
                    float(quantity),
                    region_id=building.region_id or company.region_id,
                )
        except ValueError:
            building.status = BuildingStatus.IDLE
            building.active_recipe_id = None
            building.production_progress = 0
            building.last_production_at = now
            await session.flush()
            return {
                "cycles_completed": completed,
                "status": building.status.value,
                "active_recipe": None,
                "progress_seconds": 0,
                "outputs": outputs,
            }

        for ticker, quantity in (recipe.outputs or {}).items():
            await add_resource(
                session,
                company.id,
                ticker,
                float(quantity),
                region_id=building.region_id or company.region_id,
            )
            outputs[ticker] = outputs.get(ticker, 0.0) + float(quantity)
        completed += 1

    building.last_production_at = last_production_at + timedelta(
        seconds=completed_cycles * cycle_seconds
    )
    building.production_progress = progress_seconds
    await session.flush()
    return {
        "cycles_completed": completed,
        "status": building.status.value,
        "active_recipe": recipe.name,
        "progress_seconds": progress_seconds,
        "outputs": outputs,
    }


async def tick_production(
    session: AsyncSession, satisfaction_map: dict[int, float]
) -> dict:
    """Legacy scaffold production-step entrypoint backed by housekeeping settlement."""
    result = await session.execute(
        select(Building)
        .where(Building.status == BuildingStatus.PRODUCING)
        .with_for_update()
    )
    buildings = list(result.scalars().all())
    total_outputs: dict[str, float] = {}
    completed = 0

    for building in buildings:
        settled = await _settle_building(session, building, now=_coerce_now())
        completed += settled.get("cycles_completed", 0)
        for ticker, quantity in (settled.get("outputs") or {}).items():
            total_outputs[ticker] = total_outputs.get(ticker, 0.0) + float(quantity)

    return {
        "buildings_advanced": len(buildings),
        "buildings_completed": completed,
        "outputs": total_outputs,
    }


async def start_production(
    session: AsyncSession, company_id: int, building_id: int, recipe_id: int
) -> dict:
    """Start production on a building with a recipe."""
    company = await _get_company_for_validation(session, company_id)
    building = await _get_building_for_update(session, company_id=company_id, building_id=building_id)
    if building.status != BuildingStatus.IDLE:
        raise ValueError(f"Building {building_id} is not idle")

    recipe = await _get_recipe_for_building(
        session,
        recipe_id=recipe_id,
        building_type_id=building.building_type_id,
    )

    for ticker, quantity in (recipe.inputs or {}).items():
        stock = await get_resource_quantity_in_region(
            session,
            company.id,
            ticker,
            region_id=building.region_id or company.region_id,
        )
        if float(stock["available"]) < float(quantity):
            raise ValueError(
                f"Cannot start recipe '{recipe.name}': need {float(quantity):.4f} {ticker}, "
                f"available {float(stock['available']):.4f}"
            )

    now = _coerce_now()
    building.active_recipe_id = recipe.id
    building.status = BuildingStatus.PRODUCING
    building.last_production_at = now
    building.production_progress = 0
    await session.flush()
    return {
        "building_id": building.id,
        "recipe": recipe.name,
        "eta_ticks": recipe.duration_ticks,
    }


async def stop_production(session: AsyncSession, company_id: int, building_id: int) -> bool:
    """Stop production on a building."""
    building = await _get_building_for_update(session, company_id=company_id, building_id=building_id)
    await _settle_building(session, building, now=_coerce_now())
    if building.status != BuildingStatus.PRODUCING:
        return False
    building.status = BuildingStatus.IDLE
    building.active_recipe_id = None
    building.production_progress = 0
    building.last_production_at = _coerce_now()
    await session.flush()
    return True


async def estimate_build_building_cost(
    session: AsyncSession,
    building_type_name: str,
) -> int:
    """Return the credit spend for constructing one building of the given type."""
    building_type = (
        await session.execute(
            select(BuildingType).where(BuildingType.name == building_type_name)
        )
    ).scalar_one_or_none()
    if building_type is None:
        raise ValueError(f"Unknown building type: {building_type_name}")
    return int(round(float(building_type.cost_credits)))


async def build_building(
    session: AsyncSession, company_id: int, building_type_name: str
) -> dict:
    """Construct a new building."""
    company = await _get_company_for_validation(session, company_id)
    building_type = (
        await session.execute(
            select(BuildingType).where(BuildingType.name == building_type_name)
        )
    ).scalar_one_or_none()
    if building_type is None:
        raise ValueError(f"Unknown building type: {building_type_name}")

    await debit_balance(session, company_id, float(building_type.cost_credits))
    for ticker, quantity in (building_type.cost_materials or {}).items():
        await remove_resource(
            session,
            company_id,
            ticker,
            float(quantity),
            region_id=company.region_id,
        )

    building = Building(
        company_id=company_id,
        agent_id=company.founder_agent_id,
        region_id=company.region_id,
        building_type_id=building_type.id,
        status=BuildingStatus.IDLE,
        production_progress=0,
    )
    session.add(building)
    await session.flush()
    return {
        "building_id": building.id,
        "building_type": building_type.name,
        "cost_credits": float(building_type.cost_credits),
        "cost_materials": building_type.cost_materials or {},
    }


async def get_company_buildings(session: AsyncSession, company_id: int) -> list[dict]:
    """Get all buildings for a company."""
    result = await session.execute(
        select(Building)
        .options(selectinload(Building.building_type))
        .where(Building.company_id == company_id)
        .order_by(Building.id.asc())
    )
    buildings = list(result.scalars().all())
    now = _coerce_now()
    items: list[dict] = []
    for building in buildings:
        active_recipe = None
        recipe_duration = None
        progress = int(building.production_progress or 0)
        if building.active_recipe_id is not None:
            recipe = (
                await session.execute(select(Recipe).where(Recipe.id == building.active_recipe_id))
            ).scalar_one_or_none()
            if recipe is not None:
                active_recipe = recipe.name
                recipe_duration = recipe.duration_ticks
                if building.status == BuildingStatus.PRODUCING:
                    last_production_at = building.last_production_at or building.updated_at
                    if last_production_at is not None:
                        if last_production_at.tzinfo is None:
                            last_production_at = last_production_at.replace(tzinfo=UTC)
                        progress = min(
                            int((now - last_production_at).total_seconds()),
                            _duration_seconds(recipe),
                        )

        items.append(
            {
                "building_id": building.id,
                "building_type": building.building_type.name if building.building_type else "",
                "status": building.status.value,
                "active_recipe": active_recipe,
                "production_progress": progress,
                "recipe_duration": recipe_duration,
            }
        )
    return items


async def get_recipes(
    session: AsyncSession, building_type_name: str | None = None
) -> list[dict]:
    """Get recipes, optionally filtered by building type."""
    stmt = select(Recipe).order_by(Recipe.id.asc())
    if building_type_name is not None:
        building_type = (
            await session.execute(
                select(BuildingType).where(BuildingType.name == building_type_name)
            )
        ).scalar_one_or_none()
        if building_type is None:
            raise ValueError(f"Unknown building type: {building_type_name}")
        stmt = stmt.where(Recipe.building_type_id == building_type.id)

    recipes = list((await session.execute(stmt)).scalars().all())
    building_types = {}
    if recipes:
        type_ids = {recipe.building_type_id for recipe in recipes}
        types_result = await session.execute(
            select(BuildingType).where(BuildingType.id.in_(tuple(type_ids)))
        )
        building_types = {item.id: item.name for item in types_result.scalars().all()}

    return [
        {
            "recipe_id": recipe.id,
            "name": recipe.name,
            "building_type": building_types.get(recipe.building_type_id, ""),
            "inputs": recipe.inputs or {},
            "outputs": recipe.outputs or {},
            "duration_ticks": recipe.duration_ticks,
        }
        for recipe in recipes
    ]


async def get_building_types(session: AsyncSession) -> list[dict]:
    """Get all constructible building types."""
    result = await session.execute(select(BuildingType).order_by(BuildingType.name.asc()))
    return [
        {
            "name": building_type.name,
            "display_name": building_type.display_name,
            "cost_credits": float(building_type.cost_credits),
            "cost_materials": building_type.cost_materials or {},
            "max_workers": building_type.max_workers,
            "description": building_type.description or "",
        }
        for building_type in result.scalars().all()
    ]


async def get_agent_company_buildings(session: AsyncSession, agent_id: int) -> list[dict]:
    """Convenience helper for agent-owned company preview reads."""
    company = await get_agent_company(session, agent_id)
    if company is None:
        raise ValueError(f"Agent {agent_id} does not have an active company")
    return await get_company_buildings(session, company["company_id"])


async def settle_all_buildings(
    session: AsyncSession, now: datetime | None = None
) -> dict:
    """Housekeeping helper that settles all producing buildings."""
    timestamp = _coerce_now(now)
    result = await session.execute(
        select(Building)
        .where(Building.status == BuildingStatus.PRODUCING)
        .with_for_update()
    )
    buildings = list(result.scalars().all())
    outputs: dict[str, float] = {}
    cycles_completed = 0
    for building in buildings:
        settled = await _settle_building(session, building, now=timestamp)
        cycles_completed += int(settled.get("cycles_completed", 0))
        for ticker, quantity in (settled.get("outputs") or {}).items():
            outputs[ticker] = outputs.get(ticker, 0.0) + float(quantity)
    return {
        "buildings_processed": len(buildings),
        "cycles_completed": cycles_completed,
        "outputs": outputs,
    }
