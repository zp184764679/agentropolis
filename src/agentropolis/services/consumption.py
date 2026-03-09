"""Consumption service - worker upkeep and satisfaction management.

Called first in each tick, before production and matching.

Per tick, each company's workers consume:
- RAT: count * WORKER_RAT_PER_TICK
- DW:  count * WORKER_DW_PER_TICK

Satisfaction rules:
- If both RAT and DW are fully supplied: satisfaction recovers by RECOVERY_RATE (cap 100)
- If either is insufficient: satisfaction drops by DECAY_RATE (floor 0)
- Partial supply: proportional penalty
- satisfaction < LOW_SATISFACTION_THRESHOLD (50%): production runs at 50% speed
- satisfaction == 0: lose WORKER_ATTRITION_RATE fraction of workers (rounded down, min 1 lost)

Implementation notes:
- Inventory deductions use SELECT ... FOR UPDATE
- If inventory has less than needed, consume all available (partial feeding)
- Satisfaction is stored as float 0-100 on Worker model
"""

from sqlalchemy.ext.asyncio import AsyncSession


async def tick_consumption(session: AsyncSession) -> dict:
    """Process worker consumption for all active companies.

    Returns:
        {
            "companies_processed": int,
            "total_rat_consumed": float,
            "total_dw_consumed": float,
            "workers_lost": int,
            "satisfaction_map": {company_id: satisfaction_pct},
        }
    """
    raise NotImplementedError("Issue #3: Implement consumption service")
