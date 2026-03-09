"""NXC Mining Service - Nexus Crystal production, difficulty, and halving.

NXC (Nexus Crystal) is the ultimate scarce resource in Agentropolis,
modeled after Bitcoin's mining mechanics:

- Hard cap: 21,000,000 NXC
- Refining cycle: 300 seconds (5 minutes)
- Halving interval: 2016 cycles = 168 hours = 1 week
- Initial base yield: 50 NXC/cycle (solo refinery)
- Dynamic difficulty: adjusts hourly based on actual vs target emission
- Input cost: STL:3 + MCH:1 + C:5 per cycle

Key functions:
- calculate_nxc_yield: Dynamic output per refinery per cycle
- adjust_difficulty: Hourly difficulty recalibration
- check_halving: Halve base yield every 2016 cycles
- update_active_refineries: Count active nexus refineries
- get_nxc_stats: Global NXC state for API

Dependencies: #16 (Foundation), #20 (Production)
File owner: Issue #38
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models.nexus_state import NexusCrystalState


async def get_nxc_state(session: AsyncSession) -> NexusCrystalState:
    """Get the singleton NexusCrystalState row, creating if absent."""
    result = await session.execute(
        select(NexusCrystalState).where(NexusCrystalState.id == 1)
    )
    state = result.scalar_one_or_none()
    if state is None:
        state = NexusCrystalState(id=1)
        session.add(state)
        await session.flush()
    return state


async def calculate_nxc_yield(session: AsyncSession) -> int:
    """Calculate NXC output for a single refinery cycle.

    Formula: raw_yield = (base_yield / active_refineries) * difficulty
    Clamped to [1, remaining_to_cap].
    Returns 0 if hard cap reached.
    """
    state = await get_nxc_state(session)

    if state.total_mined >= state.hard_cap:
        return 0

    active = max(1, state.active_refineries)
    raw_yield = (state.current_base_yield / active) * state.current_difficulty
    yield_amount = max(1, int(raw_yield))

    remaining = state.hard_cap - state.total_mined
    return min(yield_amount, remaining)


async def record_nxc_mined(session: AsyncSession, amount: int) -> None:
    """Record that NXC was mined (called after production settlement)."""
    state = await get_nxc_state(session)
    state.total_mined += amount
    state.cycles_since_genesis += 1


async def adjust_difficulty(
    session: AsyncSession, now: datetime | None = None
) -> dict:
    """Adjust mining difficulty based on actual vs target emission rate.

    Called hourly by housekeeping. If actual emission exceeds target,
    difficulty decreases (harder). If below target, difficulty increases (easier).

    Returns: {"old_difficulty", "new_difficulty", "actual_mined", "target"}
    """
    if now is None:
        from datetime import UTC

        now = datetime.now(UTC)

    state = await get_nxc_state(session)
    old_difficulty = state.current_difficulty

    if state.difficulty_adjusted_at is None:
        state.difficulty_adjusted_at = now
        return {
            "old_difficulty": old_difficulty,
            "new_difficulty": old_difficulty,
            "actual_mined": 0,
            "target": state.target_emission_per_hour,
        }

    # Calculate actual mined since last adjustment
    # This is approximate — in production, query actual NXC production logs
    elapsed_hours = (now - state.difficulty_adjusted_at).total_seconds() / 3600
    if elapsed_hours < 0.5:
        # Too soon to adjust
        return {
            "old_difficulty": old_difficulty,
            "new_difficulty": old_difficulty,
            "actual_mined": 0,
            "target": state.target_emission_per_hour,
        }

    # Estimate: cycles_per_hour * yield_per_cycle * active_refineries
    cycles_per_hour = 3600 / 300  # 12 cycles/hour
    estimated_per_cycle = (
        (state.current_base_yield / max(1, state.active_refineries))
        * state.current_difficulty
    )
    actual_mined_per_hour = int(
        estimated_per_cycle * max(1, state.active_refineries) * cycles_per_hour
    )

    if actual_mined_per_hour == 0:
        state.difficulty_adjusted_at = now
        return {
            "old_difficulty": old_difficulty,
            "new_difficulty": old_difficulty,
            "actual_mined": 0,
            "target": state.target_emission_per_hour,
        }

    ratio = actual_mined_per_hour / state.target_emission_per_hour
    state.current_difficulty = max(0.1, state.current_difficulty / ratio)
    state.difficulty_adjusted_at = now

    return {
        "old_difficulty": old_difficulty,
        "new_difficulty": state.current_difficulty,
        "actual_mined": actual_mined_per_hour,
        "target": state.target_emission_per_hour,
    }


async def check_halving(session: AsyncSession, now: datetime | None = None) -> dict:
    """Check and apply halving if cycle threshold reached.

    Halving occurs every cycles_per_halving (default 2016) cycles.
    Base yield is halved (minimum 1).

    Returns: {"halved": bool, "new_base_yield": int, "halvings_applied": int}
    """
    if now is None:
        from datetime import UTC

        now = datetime.now(UTC)

    state = await get_nxc_state(session)
    halved = False

    threshold = (state.halvings_applied + 1) * state.cycles_per_halving
    if state.cycles_since_genesis >= threshold:
        state.current_base_yield = max(1, state.current_base_yield // 2)
        state.halvings_applied += 1
        state.last_halving_at = now
        halved = True

    return {
        "halved": halved,
        "new_base_yield": state.current_base_yield,
        "halvings_applied": state.halvings_applied,
    }


async def update_active_refineries(session: AsyncSession) -> int:
    """Count and update the number of active nexus refineries.

    Queries buildings with type='nexus_refinery' and status='producing'.
    Called during housekeeping sweep.

    Returns: active refinery count
    """
    from agentropolis.models.building import Building, BuildingStatus
    from agentropolis.models.building_type import BuildingType

    result = await session.execute(
        select(Building)
        .join(BuildingType)
        .where(
            BuildingType.name == "nexus_refinery",
            Building.status == BuildingStatus.PRODUCING,
        )
    )
    count = len(result.scalars().all())

    state = await get_nxc_state(session)
    state.active_refineries = count
    return count


async def get_nxc_stats(session: AsyncSession) -> dict:
    """Get global NXC state for API responses.

    Returns: {
        "total_mined", "hard_cap", "remaining",
        "current_base_yield", "current_difficulty",
        "active_refineries", "halvings_applied",
        "cycles_since_genesis", "cycles_per_halving",
        "next_halving_cycle", "mining_active": bool,
    }
    """
    state = await get_nxc_state(session)
    next_halving = (state.halvings_applied + 1) * state.cycles_per_halving

    return {
        "total_mined": state.total_mined,
        "hard_cap": state.hard_cap,
        "remaining": state.hard_cap - state.total_mined,
        "current_base_yield": state.current_base_yield,
        "current_difficulty": state.current_difficulty,
        "active_refineries": state.active_refineries,
        "halvings_applied": state.halvings_applied,
        "cycles_since_genesis": state.cycles_since_genesis,
        "cycles_per_halving": state.cycles_per_halving,
        "next_halving_cycle": next_halving,
        "cycles_until_halving": max(0, next_halving - state.cycles_since_genesis),
        "mining_active": state.total_mined < state.hard_cap,
    }
