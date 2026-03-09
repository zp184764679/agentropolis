"""Production service - manages building construction and manufacturing.

Called during the production phase of each tick.

Flow per tick:
1. For each PRODUCING building:
   a. Increment production_progress by 1 (or 0.5 if low satisfaction)
   b. If progress >= recipe.duration_ticks:
      - Consume inputs from inventory (already reserved at start)
      - Add outputs to inventory
      - Reset progress to 0
      - If continuous, start next cycle; else set to IDLE

Building construction:
- Costs credits + materials (from cost_materials JSONB)
- Instant construction (MVP simplification)
- Future: construction time in ticks

Implementation notes:
- Inventory mutations must use SELECT ... FOR UPDATE
- If inputs are insufficient at completion time, building pauses (set IDLE)
- Production start validates recipe belongs to building type
"""

from sqlalchemy.ext.asyncio import AsyncSession


async def tick_production(
    session: AsyncSession, satisfaction_map: dict[int, float]
) -> dict:
    """Advance all active productions by one tick step.

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
    """Start production on a building with given recipe.

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
    """Stop production on a building. Sets to IDLE, resets progress.

    Returns: True if stopped, False if not producing
    """
    raise NotImplementedError("Issue #2: Implement production service")


async def build_building(
    session: AsyncSession, company_id: int, building_type_name: str
) -> dict:
    """Construct a new building. Deducts credits and materials.

    Returns: {"building_id", "building_type", "cost_credits", "cost_materials"}
    Raises: ValueError if insufficient funds/materials or invalid type
    """
    raise NotImplementedError("Issue #2: Implement production service")


async def get_company_buildings(session: AsyncSession, company_id: int) -> list[dict]:
    """Get all buildings owned by a company with their status."""
    raise NotImplementedError("Issue #2: Implement production service")


async def get_recipes(
    session: AsyncSession, building_type_name: str | None = None
) -> list[dict]:
    """Get available recipes, optionally filtered by building type."""
    raise NotImplementedError("Issue #2: Implement production service")
