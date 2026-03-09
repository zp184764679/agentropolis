"""Legacy scaffold production stub.

This module still assumes a tick-phased production loop and company-centric
control surface. The target plan moves production toward the real-time world
kernel with settlement integrated into housekeeping/lazy progression.

Keep signatures stable for the scaffold, but do not treat this docstring as the
final production architecture.
"""

from sqlalchemy.ext.asyncio import AsyncSession


async def tick_production(
    session: AsyncSession, satisfaction_map: dict[int, float]
) -> dict:
    """Legacy scaffold production-step stub.

    Args:
        session: DB session
        satisfaction_map: {company_id: satisfaction_pct} for productivity modifier

    Returns:
        {"buildings_advanced": int, "buildings_completed": int, "outputs": {ticker: total_qty}}
    """
    raise NotImplementedError("Issue #2: Implement production service")


async def start_production(
    session: AsyncSession, company_id: int, building_id: int, recipe_id: int
) -> dict:
    """Legacy scaffold production-start stub.

    Validates:
    - Building belongs to company
    - Building is IDLE
    - Recipe belongs to building's type
    - Company has sufficient input materials

    Returns: {"building_id", "recipe", "eta_ticks"}
    Raises: ValueError on validation failure
    """
    raise NotImplementedError("Issue #2: Implement production service")


async def stop_production(session: AsyncSession, company_id: int, building_id: int) -> bool:
    """Legacy scaffold production-stop stub.

    Returns: True if stopped, False if not producing
    """
    raise NotImplementedError("Issue #2: Implement production service")


async def build_building(
    session: AsyncSession, company_id: int, building_type_name: str
) -> dict:
    """Legacy scaffold building-construction stub.

    Returns: {"building_id", "building_type", "cost_credits", "cost_materials"}
    Raises: ValueError if insufficient funds/materials or invalid type
    """
    raise NotImplementedError("Issue #2: Implement production service")


async def get_company_buildings(session: AsyncSession, company_id: int) -> list[dict]:
    """Legacy scaffold company-building query stub."""
    raise NotImplementedError("Issue #2: Implement production service")


async def get_recipes(
    session: AsyncSession, building_type_name: str | None = None
) -> list[dict]:
    """Legacy scaffold recipe-query stub."""
    raise NotImplementedError("Issue #2: Implement production service")
