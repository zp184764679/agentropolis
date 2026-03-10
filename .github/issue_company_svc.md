## Overview

Implement company service — Agent creates/manages Companies, balance operations, net worth.

**Key changes**: Company is now created BY an Agent (founder_agent_id). No more api_key on Company. Worker model replaced by `Company.npc_worker_count`. All money in copper (BigInteger).

## Files

- **Modify**: `src/agentropolis/services/company_svc.py`
- **DO NOT TOUCH**: Model files, auth, schemas (owned by #16)

## Function Signatures (Final)

```python
async def register_company(
    session: AsyncSession, agent_id: int, region_id: int, name: str,
) -> dict:
    """Create a new company. Agent becomes founder + CEO.
    Creates: Company (npc_worker_count=100, npc_satisfaction=100.0, last_consumption_at=now)
           + AgentEmployment (role=CEO)
           + 3 starter buildings (extractor, farm, food_processor) with region_id
           + starter inventory (H2O:100, CRP:50, RAT:200, DW:150) with region_id
    Returns: {"company_id", "name", "balance", "region_id"}
    Raises: ValueError if name taken or agent already owns a company in this region"""

async def debit_balance(
    session: AsyncSession, company_id: int, amount: int,
) -> int:
    """Debit company balance (copper) with FOR UPDATE lock.
    Returns new balance. Raises ValueError if insufficient."""

async def credit_balance(
    session: AsyncSession, company_id: int, amount: int,
) -> int:
    """Credit company balance (copper) with FOR UPDATE lock. Returns new balance."""

async def reserve_balance(
    session: AsyncSession, company_id: int, amount: int,
) -> int:
    """Reserve balance for buy orders. Returns new reserved_balance.
    Raises ValueError if insufficient available_balance."""

async def unreserve_balance(
    session: AsyncSession, company_id: int, amount: int,
) -> int:
    """Release reserved balance. Returns new reserved_balance."""

async def recalculate_net_worth(session: AsyncSession, company_id: int) -> int:
    """net_worth = balance + inventory_value + building_value (all copper)"""

async def recalculate_all_net_worths(session: AsyncSession) -> int:
    """Recalculate for all active companies. Returns count."""

async def get_company_status(session: AsyncSession, company_id: int, now: datetime | None = None) -> dict:
    """Settle NPC consumption first, then return full status.
    Returns: {"company_id", "name", "balance", "available_balance", "net_worth",
              "is_active", "npc_worker_count", "npc_satisfaction", "building_count",
              "region_id", "founder_agent_id", "created_at"}"""

async def check_bankruptcies(session: AsyncSession) -> list[int]:
    """Mark bankrupt companies (net_worth <= 0 and no assets). Returns bankrupt IDs."""
```

## Implementation Rules

1. `register_company` calls `inventory_svc.add_resource` for starter inventory
2. Balance operations use `SELECT ... FOR UPDATE`
3. `available_balance = balance - reserved_balance`
4. Net worth = balance + sum(inv.quantity * resource.base_price) + sum(building_type.cost_credits)
5. `get_company_status` calls `consumption.settle_npc_consumption()` before returning
6. Bankruptcy: `is_active = False`, `bankruptcy_at = now`

## Acceptance Criteria

- [ ] register_company creates Company + CEO employment + buildings + inventory
- [ ] All balance ops use FOR UPDATE
- [ ] reserve_balance / unreserve_balance for buy order freezing
- [ ] Net worth calculation correct
- [ ] Bankruptcy detection works
- [ ] All amounts in copper (int)

## Dependencies

- **Depends on**: #16 (Foundation), #17 (inventory_svc)
- **Blocks**: #22 (game_engine)
