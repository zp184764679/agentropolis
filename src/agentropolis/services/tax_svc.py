"""Tax service - trade/transport taxation."""

from sqlalchemy.ext.asyncio import AsyncSession


async def calculate_tax(
    session: AsyncSession, region_id: int, amount: int
) -> int:
    """Calculate tax amount for a transaction in a region.

    Returns: tax amount (copper)
    """
    raise NotImplementedError("Issue #27: Implement tax service")


async def collect_tax(
    session: AsyncSession,
    region_id: int,
    amount: int,
    tax_type: str,
    *,
    payer_agent_id: int | None = None,
    payer_company_id: int | None = None,
) -> dict:
    """Collect tax and deposit to region treasury. Creates TaxRecord.

    Returns: {"tax_record_id", "amount", "region_treasury": int}
    """
    raise NotImplementedError("Issue #27: Implement tax service")


async def get_region_tax_history(
    session: AsyncSession, region_id: int, limit: int = 50
) -> list[dict]:
    """Get recent tax records for a region."""
    raise NotImplementedError("Issue #27: Implement tax service")
