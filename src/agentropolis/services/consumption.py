"""Legacy scaffold consumption stub.

This module still documents worker upkeep in the older tick/company model.
The target plan replaces the old Worker-centric assumptions with the newer
company/agent/world model and housekeeping-friendly settlement semantics.

Do not treat the comments below as the final domain model.
"""

from sqlalchemy.ext.asyncio import AsyncSession


async def tick_consumption(session: AsyncSession) -> dict:
    """Legacy scaffold worker-consumption stub for active companies.

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
