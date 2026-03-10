"""Tax service - trade/transport taxation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models import Region, TaxRecord


async def calculate_tax(
    session: AsyncSession, region_id: int, amount: int | float
) -> int:
    """Calculate tax amount for a transaction in a region."""
    region = (
        await session.execute(select(Region).where(Region.id == region_id))
    ).scalar_one_or_none()
    if region is None:
        raise ValueError(f"Region {region_id} not found")
    return max(int(round(float(amount) * float(region.tax_rate))), 0)


async def collect_tax(
    session: AsyncSession,
    region_id: int,
    amount: int | float,
    tax_type: str,
    *,
    payer_agent_id: int | None = None,
    payer_company_id: int | None = None,
) -> dict:
    """Collect tax and deposit to region treasury. Creates TaxRecord."""
    region = (
        await session.execute(
            select(Region).where(Region.id == region_id).with_for_update()
        )
    ).scalar_one_or_none()
    if region is None:
        raise ValueError(f"Region {region_id} not found")

    tax_amount = max(int(round(float(amount) * float(region.tax_rate))), 0)
    region.treasury = int(region.treasury) + tax_amount
    record = TaxRecord(
        tax_type=tax_type,
        payer_agent_id=payer_agent_id,
        payer_company_id=payer_company_id,
        region_id=region.id,
        amount=tax_amount,
    )
    session.add(record)
    await session.flush()
    return {
        "tax_record_id": record.id,
        "amount": tax_amount,
        "region_treasury": int(region.treasury),
    }


async def get_region_tax_history(
    session: AsyncSession, region_id: int, limit: int = 50
) -> list[dict]:
    """Get recent tax records for a region."""
    result = await session.execute(
        select(TaxRecord)
        .where(TaxRecord.region_id == region_id)
        .order_by(TaxRecord.collected_at.desc(), TaxRecord.id.desc())
        .limit(max(limit, 1))
    )
    return [
        {
            "tax_record_id": record.id,
            "tax_type": record.tax_type,
            "payer_agent_id": record.payer_agent_id,
            "payer_company_id": record.payer_company_id,
            "region_id": record.region_id,
            "amount": int(record.amount),
            "beneficiary_guild_id": record.beneficiary_guild_id,
            "collected_at": record.collected_at.isoformat() if record.collected_at else None,
        }
        for record in result.scalars().all()
    ]
