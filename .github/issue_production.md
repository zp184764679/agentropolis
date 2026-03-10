## Overview

Implement production service — lazy time-based manufacturing with skill requirements.

Buildings accumulate production progress based on elapsed real time. Satisfaction affects rate (>=50%: 1.0x, <50%: 0.5x). Completing a recipe consumes inputs, produces outputs, and awards skill XP.

## Files

- **Modify**: `src/agentropolis/services/production.py`
- **DO NOT TOUCH**: Model files, other services

## Function Signatures (Final)

```python
async def settle_building(
    session: AsyncSession, building_id: int, now: datetime | None = None,
) -> dict:
    """Settle production progress for a single building.

    1. Load Building + Company (FOR UPDATE)
    2. If not PRODUCING, return immediately
    3. Settle NPC consumption first (call settle_npc_consumption)
    4. elapsed = now - last_progress_checkpoint_at
    5. rate = 1.0 if npc_satisfaction >= 50 else 0.5
    6. new_progress = accumulated_progress_seconds + elapsed * rate
    7. If new_progress >= recipe.duration_seconds:
       a. Load input inventory (FOR UPDATE), check availability
       b. If inputs insufficient → set IDLE, return
       c. Deduct inputs via inventory_svc.remove_resource
       d. Add outputs via inventory_svc.add_resource
       e. Award skill XP if recipe.skill_xp_reward > 0 (find agent via company.founder_agent_id)
       f. Reset progress, start next cycle (new_progress -= duration)
    8. Update checkpoint

    Returns: {"building_id", "status", "progress_pct", "completed": bool,
              "outputs": {ticker: qty} | None, "xp_awarded": int}
    """

async def settle_company_buildings(
    session: AsyncSession, company_id: int, now: datetime | None = None,
) -> dict:
    """Settle all PRODUCING buildings for a company.
    Returns: {"buildings_settled", "buildings_completed", "total_outputs": {ticker: qty}}"""

async def start_production(
    session: AsyncSession, company_id: int, building_id: int, recipe_id: int,
    now: datetime | None = None,
) -> dict:
    """Start production on a building.
    Validates: building belongs to company, is IDLE, recipe belongs to building type,
    company has sufficient inputs, agent has required skill level (if recipe.required_skill).
    Consumes inputs immediately on start.
    Returns: {"building_id", "recipe_name", "eta_seconds"}
    Raises: ValueError on validation failure"""

async def stop_production(
    session: AsyncSession, company_id: int, building_id: int,
) -> bool:
    """Stop production. Sets IDLE, resets progress. Returns True if stopped."""

async def build_building(
    session: AsyncSession, company_id: int, building_type_name: str,
) -> dict:
    """Construct new building. Deducts credits + materials.
    Building gets company.region_id automatically.
    Returns: {"building_id", "building_type", "cost_credits", "cost_materials"}
    Raises: ValueError if insufficient funds/materials, invalid type, or skill requirement not met"""

async def get_company_buildings(
    session: AsyncSession, company_id: int, now: datetime | None = None,
) -> list[dict]:
    """Get all buildings with settled status.
    Returns: [{"building_id", "building_type", "status", "active_recipe",
               "progress_pct", "eta_seconds", "region_id"}]"""

async def get_recipes(
    session: AsyncSession, building_type_name: str | None = None,
) -> list[dict]:
    """Get available recipes.
    Returns: [{"recipe_id", "name", "building_type", "inputs", "outputs",
               "duration_seconds", "required_skill", "min_skill_level", "skill_xp_reward"}]"""
```

## Implementation Rules

1. Settle NPC consumption BEFORE calculating production rate (need current satisfaction)
2. Production rate: `>= 50% satisfaction → 1.0x`, `< 50% → 0.5x`
3. Inputs consumed on `start_production` (not at completion)
4. Outputs added at completion
5. Multi-cycle: if progress exceeds duration, complete and start next cycle (carry over excess)
6. Skill check: if `recipe.required_skill` is set, look up founder agent's skill level
7. XP award: on completion, call skill_svc to add XP to founder agent
8. Building construction is instant (deduct cost, create row)
9. New buildings get `region_id = company.region_id`
10. All inventory ops through `inventory_svc` (not direct DB writes)

## Acceptance Criteria

- [ ] Lazy time-based settlement
- [ ] Satisfaction-based rate modulation
- [ ] FOR UPDATE on building and inventory rows
- [ ] Input consumption on start, output on completion
- [ ] Skill requirement validation
- [ ] XP award on completion
- [ ] Multi-cycle carry-over
- [ ] Building construction with cost deduction
- [ ] `now` parameter for testability

## Dependencies

- **Depends on**: #16 (Foundation), #17 (inventory_svc), #19 (consumption for satisfaction)
- **Blocks**: #22 (game_engine)
