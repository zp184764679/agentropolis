"""Company service - registration, balance operations, net worth.

Handles:
- Company registration (generates API key, creates starter buildings/inventory)
- Balance debit/credit with row-level locking
- Net worth recalculation (balance + inventory value + building value)
- Bankruptcy detection (net_worth <= 0 and no assets)

Implementation notes:
- API key generated as secrets.token_hex(32), stored as SHA-256 hash
- Registration creates: Company + Worker + starter buildings + starter inventory
- Balance operations MUST use SELECT ... FOR UPDATE
- Net worth = balance + sum(inventory.quantity * resource.last_price) + sum(building.type.cost_credits)
"""

from sqlalchemy.ext.asyncio import AsyncSession


async def register_company(session: AsyncSession, name: str) -> dict:
    """Register a new company with starter kit.

    Creates: Company, Worker (100), 3 starter buildings (extractor, farm, food_processor),
    starter inventory (H2O:100, CRP:50, RAT:200, DW:150).

    Returns: {"company_id", "api_key" (plaintext, only time it's returned), "name", "balance"}
    Raises: ValueError if name already taken
    """
    raise NotImplementedError("Issue #4: Implement company service")


async def debit_balance(session: AsyncSession, company_id: int, amount: float) -> float:
    """Debit company balance with FOR UPDATE lock.

    Returns: new balance
    Raises: ValueError if insufficient balance
    """
    raise NotImplementedError("Issue #4: Implement company service")


async def credit_balance(session: AsyncSession, company_id: int, amount: float) -> float:
    """Credit company balance with FOR UPDATE lock.

    Returns: new balance
    """
    raise NotImplementedError("Issue #4: Implement company service")


async def recalculate_net_worth(session: AsyncSession, company_id: int) -> float:
    """Recalculate and update a company's net worth.

    net_worth = balance + inventory_value + building_value
    """
    raise NotImplementedError("Issue #4: Implement company service")


async def recalculate_all_net_worths(session: AsyncSession) -> int:
    """Recalculate net worth for all active companies. Returns count updated."""
    raise NotImplementedError("Issue #4: Implement company service")


async def get_company_status(session: AsyncSession, company_id: int) -> dict:
    """Get full company status including balance, workers, buildings."""
    raise NotImplementedError("Issue #4: Implement company service")


async def check_bankruptcies(session: AsyncSession) -> list[int]:
    """Detect and mark bankrupt companies. Returns list of bankrupt company IDs."""
    raise NotImplementedError("Issue #4: Implement company service")
